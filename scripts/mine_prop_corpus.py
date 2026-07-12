#!/usr/bin/env python3
"""Mine existing xLights sequences for a prop family's effect/timing/audio patterns.

Generalized from the arch-only miner: the prop family is selected with
--family/--tokens/--exclude-tokens (defaults reproduce the original arch
mining exactly). Read-only against every .xsq/.xsqz file — nothing under the
scanned show folder is ever written to. Walks a show folder, finds every
sequence, and for each one:

  - Parses the sequence XML for effect placements on the family's models and
    model groups (never modifies the file).
  - Parses xlights_rgbeffects.xml for matching models and modelGroups so
    e.g. "Group - Snowflakes" (a group) and "HFlake1" (individual models)
    are both captured. Group members that are submodels ("Model/Submodel")
    match on the full member string.
  - Locates the referenced audio file (only the basename is stored in the
    .xsq) by searching the show folder tree.
  - Runs a librosa-only beat/energy pass on that audio (no vamp/madmom
    dependency) and correlates effect boundaries against beats and energy.
  - Optionally correlates against song section labels (verse/chorus/etc)
    read from a --section-cache directory of per-song JSON files shaped
    like the mcp__xlights__get_song_structure tool's response
    ({"sections": [{"label", "start_time", "end_time", "energy_level",
    "confidence"}, ...]}, times in seconds). That MCP tool is only callable
    interactively, so populating the cache is a separate step from running
    this script.

Writes one data.json + summary.md per song under the output corpus
directory, plus a cross-song INDEX.md.

Usage:
    # arches (original behavior)
    python scripts/mine_prop_corpus.py "E:\\2023\\ShowFolder3D" \\
        --out docs/arch_sequencing_corpus \\
        --section-cache docs/arch_sequencing_corpus/_section_cache

    # snowflakes
    python scripts/mine_prop_corpus.py "E:\\2023\\ShowFolder3D" \\
        --family snowflake --tokens flake,snowburst \\
        --out docs/snowflake_sequencing_corpus \\
        --section-cache docs/arch_sequencing_corpus/_section_cache
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_ZIP_MAGIC = b"PK"

# Prop-family matching config — set from CLI args in main(). Defaults
# reproduce the original arch corpus miner: "Triple Arches" is a separate
# prop family from the "Arches" family and shouldn't be blended into the
# same corpus (user-requested exclusion).
_PROP_TOKENS: tuple[str, ...] = ("arch",)
_EXCLUDED_ELEMENT_TOKENS: tuple[str, ...] = ("triple arch",)
_FAMILY_LABEL = "arch"

_PALETTE_CHECKBOX_RE = re.compile(r"C_CHECKBOX_Palette(\d+)=1")
_PALETTE_COLOR_RE = re.compile(r"C_BUTTON_Palette(\d+)=(#[0-9A-Fa-f]{6})")

_BEAT_ALIGN_THRESHOLDS_MS = (25, 50, 100, 250, 500)

_DURATION_BUCKET_ORDER = [
    "<0.25s", "0.25-0.5s", "0.5-1s", "1-2s", "2-4s", "4-8s",
    "8-16s", "16-30s", "30-60s", "60s+",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PropElement:
    name: str
    kind: str  # "model" or "group"
    member_models: tuple[str, ...] = ()


@dataclass
class EffectPlacement:
    element: str
    kind: str
    layer_index: int
    effect_name: str
    start_ms: int
    end_ms: int
    palette_colors: tuple[str, ...]
    layer_method: str = ""  # T_CHOICE_LayerMethod from EffectDB, e.g. "2 is Unmask"
    blend_role: str = "other"  # "white_base" | "color_mask" | "other"

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class SongMining:
    xsq_path: Path
    song_title: str = ""
    duration_ms: int = 0
    media_filename: str = ""
    audio_path: Path | None = None
    prop_elements: list[PropElement] = field(default_factory=list)
    placements: list[EffectPlacement] = field(default_factory=list)
    tempo_bpm: float | None = None
    beat_times_ms: list[int] = field(default_factory=list)
    audio_correlation: str = "not_attempted"  # "beats_only" | "audio_missing" | "failed"
    custom_timing_tracks: dict[str, list[int]] = field(default_factory=dict)  # track name -> sorted mark start_ms
    sections: list[dict] = field(default_factory=list)  # get_song_structure "sections" entries, ms-based
    section_correlation: str = "not_attempted"  # "loaded" | "not_cached"


# ---------------------------------------------------------------------------
# Layout parsing (family models + family model groups)
# ---------------------------------------------------------------------------

def find_layout_xml(show_folder: Path) -> Path | None:
    top_level = show_folder / "xlights_rgbeffects.xml"
    if top_level.exists():
        return top_level
    candidates = sorted(
        p for p in show_folder.rglob("xlights_rgbeffects.xml")
        if not _is_excluded(p, show_folder)
    )
    return candidates[0] if candidates else None


def _matches_prop_token(name: str) -> bool:
    lower = name.lower()
    return any(token in lower for token in _PROP_TOKENS)


def _is_excluded_element_name(name: str) -> bool:
    lower = name.lower()
    return any(token in lower for token in _EXCLUDED_ELEMENT_TOKENS)


def parse_prop_layout(layout_path: Path) -> dict[str, PropElement]:
    """Return prop-family elements keyed by name: individual matching models,
    plus any modelGroup whose own name matches a family token or whose
    members are majority family models. Elements matching
    _EXCLUDED_ELEMENT_TOKENS are dropped entirely."""
    tree = ET.parse(layout_path)
    root = tree.getroot()

    family_models: set[str] = set()
    for model_el in root.findall(".//model"):
        name = model_el.get("name", "")
        if not name:
            continue
        if _matches_prop_token(name) and not _is_excluded_element_name(name):
            family_models.add(name)

    elements: dict[str, PropElement] = {
        name: PropElement(name=name, kind="model") for name in family_models
    }

    for group_el in root.findall(".//modelGroup"):
        group_name = group_el.get("name", "")
        if _is_excluded_element_name(group_name):
            continue
        members_raw = group_el.get("models", "")
        members = tuple(
            m.strip() for m in members_raw.split(",")
            if m.strip() and not _is_excluded_element_name(m)
        )
        name_matches = _matches_prop_token(group_name)
        # Membership alone only counts a group as family when family props are
        # the majority of its members — otherwise whole-house/whole-yard
        # umbrella groups that merely include one matching prop among 100+
        # other props would be misclassified and swamp the corpus with noise.
        family_member_count = sum(1 for m in members if _matches_prop_token(m))
        majority_family_members = bool(members) and family_member_count / len(members) > 0.5
        if group_name and (name_matches or majority_family_members):
            elements[group_name] = PropElement(
                name=group_name, kind="group", member_models=members,
            )

    return elements


# ---------------------------------------------------------------------------
# Sequence (.xsq) parsing — read-only
# ---------------------------------------------------------------------------

def _parse_palette_text(text: str) -> tuple[str, ...]:
    active_slots = {int(m.group(1)) for m in _PALETTE_CHECKBOX_RE.finditer(text)}
    colors: dict[int, str] = {}
    for m in _PALETTE_COLOR_RE.finditer(text):
        slot = int(m.group(1))
        if not active_slots or slot in active_slots:
            colors[slot] = m.group(2).upper()
    return tuple(colors[k] for k in sorted(colors))


def _parse_effect_db_settings(text: str) -> dict[str, str]:
    """Parse an EffectDB entry's comma-separated key=value settings string."""
    settings: dict[str, str] = {}
    for part in text.split(","):
        if "=" in part:
            key, _, value = part.partition("=")
            settings[key] = value
    return settings


_WHITE_COLOR = "#FFFFFF"


def classify_blend_role(palette_colors: tuple[str, ...], layer_method: str) -> str:
    """Classify a placement's role in the white-base/color-mask technique.

    T_CHOICE_LayerMethod is only present in EffectDB at all when the effect
    uses a non-default blend (Normal-blended effects omit the key entirely).
    Across the corpus, the white base sometimes carries an explicit
    "Unmask"-style LayerMethod and sometimes uses plain Normal blend with no
    LayerMethod at all — whether it needs masking depends on what else is
    stacked with it, not on its own role. So a solid white placement is
    always "white_base" regardless of blend. The color overlay, by
    contrast, only counts as a deliberate "color_mask" when it carries an
    explicit non-default LayerMethod — a solid non-white color with plain
    Normal blend is just an ordinarily-colored effect, not a recolor mask.
    Anything else (multi-color palettes, sparkle-only effects, etc.) is
    "other"."""
    if len(palette_colors) == 1 and palette_colors[0] == _WHITE_COLOR:
        return "white_base"
    if len(palette_colors) == 1 and palette_colors[0] != _WHITE_COLOR and layer_method.strip():
        return "color_mask"
    return "other"


def load_xsq_root(xsq_path: Path) -> ET.Element:
    data = xsq_path.read_bytes()
    if data[:2] == _ZIP_MAGIC:
        import io

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xsq_name = next((n for n in zf.namelist() if n.endswith(".xsq")), None)
            if xsq_name is None:
                raise ValueError(f"No .xsq member found inside {xsq_path.name!r}")
            data = zf.read(xsq_name)
    return ET.fromstring(data)


def extract_package(package_path: Path, extract_root: Path) -> Path | None:
    """Extract a self-contained show package (.xsqz/.zip containing its own
    xlights_rgbeffects.xml alongside the sequence and audio) and return the
    extraction directory. Returns None for zips that are just a bare zipped
    .xsq with no embedded layout — those are handled by load_xsq_root against
    the scanned show folder's layout instead."""
    with zipfile.ZipFile(package_path) as zf:
        names = zf.namelist()
        if not any(n.endswith("xlights_rgbeffects.xml") for n in names):
            return None
        dest = extract_root / slugify(package_path.stem)
        if not dest.exists():
            zf.extractall(dest)
        return dest


def find_package_xsq(package_dir: Path) -> Path | None:
    """The sequence inside an extracted package — largest non-backup .xsq
    (packages occasionally carry stray/backup copies)."""
    candidates = [
        p for p in package_dir.rglob("*.xsq")
        if not _is_excluded(p, package_dir)
    ]
    return max(candidates, key=lambda p: p.stat().st_size, default=None)


def mine_sequence(xsq_path: Path, prop_elements: dict[str, PropElement]) -> SongMining:
    root = load_xsq_root(xsq_path)
    song = SongMining(xsq_path=xsq_path)

    head = root.find("head")
    if head is not None:
        song_el = head.find("song")
        if song_el is not None and song_el.text:
            song.song_title = song_el.text
        media_el = head.find("mediaFile")
        if media_el is not None and media_el.text:
            song.media_filename = media_el.text
        dur_el = head.find("sequenceDuration")
        if dur_el is not None and dur_el.text:
            song.duration_ms = round(float(dur_el.text) * 1000)

    palettes: list[tuple[str, ...]] = []
    cp_el = root.find("ColorPalettes")
    if cp_el is not None:
        for cp in cp_el.findall("ColorPalette"):
            palettes.append(_parse_palette_text(cp.text or ""))

    effect_db_settings: list[dict[str, str]] = []
    edb_el = root.find("EffectDB")
    if edb_el is not None:
        for e in edb_el.findall("Effect"):
            effect_db_settings.append(_parse_effect_db_settings(e.text or ""))

    ee = root.find("ElementEffects")
    if ee is not None:
        for elem_el in ee.findall("Element"):
            if elem_el.get("type") == "timing":
                track_name = elem_el.get("name", "")
                marks = sorted(
                    int(eff_el.get("startTime", "0"))
                    for layer_el in elem_el.findall("EffectLayer")
                    for eff_el in layer_el.findall("Effect")
                )
                if track_name and marks:
                    song.custom_timing_tracks[track_name] = marks
                continue
            if elem_el.get("type") != "model":
                continue
            name = elem_el.get("name", "")
            if name not in prop_elements:
                continue
            kind = prop_elements[name].kind
            for layer_index, layer_el in enumerate(elem_el.findall("EffectLayer")):
                for eff_el in layer_el.findall("Effect"):
                    eff_name = eff_el.get("name")
                    if eff_name is None:
                        continue
                    start_ms = int(eff_el.get("startTime", "0"))
                    end_ms = int(eff_el.get("endTime", "0"))
                    pal_idx = int(eff_el.get("palette", "-1") or "-1")
                    colors = palettes[pal_idx] if 0 <= pal_idx < len(palettes) else ()
                    ref_idx = int(eff_el.get("ref", "-1") or "-1")
                    settings = effect_db_settings[ref_idx] if 0 <= ref_idx < len(effect_db_settings) else {}
                    layer_method = settings.get("T_CHOICE_LayerMethod", "")
                    if start_ms < end_ms:
                        song.placements.append(EffectPlacement(
                            element=name, kind=kind, layer_index=layer_index,
                            effect_name=eff_name, start_ms=start_ms, end_ms=end_ms,
                            palette_colors=colors, layer_method=layer_method,
                            blend_role=classify_blend_role(colors, layer_method),
                        ))

    song.prop_elements = [
        el for name, el in prop_elements.items()
        if any(p.element == name for p in song.placements)
    ]
    return song


# ---------------------------------------------------------------------------
# Audio location + beats-only analysis
# ---------------------------------------------------------------------------

_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

# xLights auto-saves a timestamped snapshot of the whole show folder (layout +
# every sequence) into Backup/<timestamp>_OnStart/ on each session. Directory
# names to exclude everywhere we walk the show folder so we mine each song
# once from its live copy, not hundreds of times from backup snapshots.
_EXCLUDED_DIR_NAMES = {"backup"}


def _is_excluded(path: Path, show_folder: Path) -> bool:
    rel_parts = path.relative_to(show_folder).parts
    return any(part.lower() in _EXCLUDED_DIR_NAMES for part in rel_parts[:-1])


def find_audio_file(show_folder: Path, media_filename: str) -> Path | None:
    if not media_filename:
        return None
    target = media_filename.lower()
    stem = Path(media_filename).stem.lower()
    candidates = []
    for path in show_folder.rglob("*"):
        if _is_excluded(path, show_folder):
            continue
        if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS:
            if path.name.lower() == target or path.stem.lower() == stem:
                candidates.append(path)
    return candidates[0] if candidates else None


def section_cache_path(cache_dir: Path, audio_path: Path) -> Path:
    return cache_dir / f"{slugify(audio_path.stem)}.json"


def load_sections(cache_dir: Path, audio_path: Path) -> list[dict] | None:
    """Load cached mcp__xlights__get_song_structure output for this audio
    file, converting its second-based times to ms to match the rest of this
    script. Returns None if no cache entry exists yet."""
    cache_path = section_cache_path(cache_dir, audio_path)
    if not cache_path.exists():
        return None
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    sections = []
    for s in raw.get("sections", []):
        sections.append({
            "label": s.get("label", "unknown"),
            "start_ms": round(s["start_time"] * 1000),
            "end_ms": round(s["end_time"] * 1000),
            "energy_level": s.get("energy_level"),
            "confidence": s.get("confidence"),
        })
    return sections


def section_at_time(sections: list[dict], t_ms: int) -> dict | None:
    for s in sections:
        if s["start_ms"] <= t_ms < s["end_ms"]:
            return s
    return None


def analyze_beats_and_energy(audio_path: Path) -> tuple[float | None, list[int], np.ndarray, float]:
    """Librosa-only beat tracking + coarse energy envelope.

    Returns (tempo_bpm, beat_times_ms, energy_curve, hop_seconds). No
    vamp/madmom dependency — deliberately degraded quality, see design note
    in the module docstring: section/energy detection needs the real
    vamp/madmom pipeline for anything beyond a coarse RMS envelope.
    """
    import librosa

    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times_ms = [round(t * 1000) for t in librosa.frames_to_time(beat_frames, sr=sr)]

    hop_length = 2048
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    hop_seconds = hop_length / sr
    # librosa >=0.10 returns tempo as a 1-element ndarray rather than a scalar.
    tempo_val = float(np.asarray(tempo).reshape(-1)[0]) if tempo is not None else None
    return tempo_val, beat_times_ms, rms, hop_seconds


def energy_bucket(rms: np.ndarray, hop_seconds: float, time_s: float) -> str:
    if rms.size == 0:
        return "unknown"
    idx = min(int(time_s / hop_seconds), rms.size - 1)
    value = rms[idx]
    low, high = np.percentile(rms, [33, 66])
    if value <= low:
        return "low"
    if value <= high:
        return "mid"
    return "high"


def nearest_beat_distance_ms(beat_times_ms: list[int], t_ms: int) -> int | None:
    if not beat_times_ms:
        return None
    return min(abs(t_ms - b) for b in beat_times_ms)


_TIMING_TRACK_ALIGNMENT_THRESHOLD_MS = 50
# A track with too few marks can look artificially well-aligned (e.g. a
# handful of section-boundary marks that happen to sit near a few effect
# starts by chance). Require enough marks that alignment reflects a real
# rhythm/timing track, not noise.
_MIN_MARKS_FOR_ALIGNMENT_CANDIDACY = 20


def best_aligned_timing_track(
    placements: list[EffectPlacement], custom_timing_tracks: dict[str, list[int]],
) -> tuple[str | None, dict[str, float]]:
    """For each custom timing track, compute the fraction of placement start
    times within _TIMING_TRACK_ALIGNMENT_THRESHOLD_MS of a mark on that
    track, and return (best track name or None, all tracks' scores).

    This is how we discovered that a song's actual rhythm driver can be a
    hand-tapped track (e.g. "Low Bumps") rather than the generic beat grid —
    see docs/arch_sequencing_corpus session notes on "Beautiful People".
    """
    starts = [p.start_ms for p in placements]
    scores: dict[str, float] = {}
    for track_name, marks in custom_timing_tracks.items():
        if len(marks) < _MIN_MARKS_FOR_ALIGNMENT_CANDIDACY or not starts:
            continue
        aligned = sum(
            1 for s in starts
            if min(abs(s - m) for m in marks) <= _TIMING_TRACK_ALIGNMENT_THRESHOLD_MS
        )
        scores[track_name] = aligned / len(starts)
    best = max(scores, key=scores.get) if scores else None
    return best, scores


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def bucket_duration(dur_s: float) -> str:
    if dur_s < 0.25:
        return "<0.25s"
    if dur_s < 0.5:
        return "0.25-0.5s"
    if dur_s < 1.0:
        return "0.5-1s"
    if dur_s < 2.0:
        return "1-2s"
    if dur_s < 4.0:
        return "2-4s"
    if dur_s < 8.0:
        return "4-8s"
    if dur_s < 16.0:
        return "8-16s"
    if dur_s < 30.0:
        return "16-30s"
    if dur_s < 60.0:
        return "30-60s"
    return "60s+"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "untitled"


def song_to_dict(song: SongMining) -> dict:
    effect_counts = Counter(p.effect_name for p in song.placements)
    duration_buckets = Counter(bucket_duration(p.duration_ms / 1000.0) for p in song.placements)

    beat_alignment = {}
    if song.audio_correlation == "beats_only":
        for threshold in _BEAT_ALIGN_THRESHOLDS_MS:
            aligned = sum(
                1 for p in song.placements
                if (d := nearest_beat_distance_ms(song.beat_times_ms, p.start_ms)) is not None
                and d <= threshold
            )
            beat_alignment[str(threshold)] = aligned / max(len(song.placements), 1)

    section_label_counts = Counter()
    if song.section_correlation == "loaded":
        for p in song.placements:
            section = section_at_time(song.sections, p.start_ms)
            section_label_counts[section["label"] if section else "no_section_match"] += 1

    blend_role_counts = Counter(p.blend_role for p in song.placements)

    best_track, track_scores = best_aligned_timing_track(song.placements, song.custom_timing_tracks)

    return {
        "xsq_path": str(song.xsq_path),
        "prop_family": _FAMILY_LABEL,
        "song_title": song.song_title,
        "duration_ms": song.duration_ms,
        "media_filename": song.media_filename,
        "audio_path": str(song.audio_path) if song.audio_path else None,
        "audio_correlation": song.audio_correlation,
        "tempo_bpm": song.tempo_bpm,
        "prop_elements": [
            {"name": el.name, "kind": el.kind, "member_models": list(el.member_models)}
            for el in song.prop_elements
        ],
        "placement_count": len(song.placements),
        "effect_usage": dict(effect_counts.most_common()),
        "duration_bucket_histogram": {b: duration_buckets.get(b, 0) for b in _DURATION_BUCKET_ORDER if duration_buckets.get(b, 0)},
        "beat_alignment_pct_within_ms": beat_alignment,
        "section_correlation": song.section_correlation,
        "placement_count_by_section_label": dict(section_label_counts.most_common()),
        "blend_role_counts": dict(blend_role_counts.most_common()),
        "custom_timing_track_names": list(song.custom_timing_tracks),
        "best_aligned_timing_track": best_track,
        "timing_track_alignment_pct": track_scores,
        "placements": [
            {
                "element": p.element,
                "kind": p.kind,
                "layer_index": p.layer_index,
                "effect_name": p.effect_name,
                "layer_method": p.layer_method,
                "blend_role": p.blend_role,
                "start_ms": p.start_ms,
                "end_ms": p.end_ms,
                "duration_ms": p.duration_ms,
                "palette_colors": list(p.palette_colors),
                "beat_distance_ms": nearest_beat_distance_ms(song.beat_times_ms, p.start_ms)
                if song.audio_correlation == "beats_only" else None,
                "section": (
                    section_at_time(song.sections, p.start_ms)
                    if song.section_correlation == "loaded" else None
                ),
            }
            for p in sorted(song.placements, key=lambda p: p.start_ms)
        ],
    }


def write_song_summary_md(song: SongMining, out_dir: Path) -> None:
    lines = []
    lines.append(f"# {_FAMILY_LABEL.capitalize()} sequencing summary: {song.xsq_path.name}")
    lines.append("")
    lines.append(f"- Song title: {song.song_title or '(unknown)'}")
    lines.append(f"- Duration: {song.duration_ms/1000:.1f}s")
    lines.append(f"- Media file: {song.media_filename or '(none)'}")
    lines.append(f"- Audio located: {song.audio_path if song.audio_path else 'NOT FOUND'}")
    lines.append(f"- Audio correlation: {song.audio_correlation}")
    if song.tempo_bpm:
        lines.append(f"- Estimated tempo: {song.tempo_bpm:.1f} BPM")
    lines.append("")

    lines.append(f"## {_FAMILY_LABEL.capitalize()} elements found")
    for el in song.prop_elements:
        if el.kind == "group":
            lines.append(f"- **{el.name}** (group) -> {', '.join(el.member_models) or '(no members resolved)'}")
        else:
            lines.append(f"- **{el.name}** (model)")
    lines.append("")

    effect_counts = Counter(p.effect_name for p in song.placements)
    total = len(song.placements)
    lines.append(f"## Effect vocabulary ({total} placements)")
    for name, count in effect_counts.most_common():
        pct = count / max(total, 1) * 100
        lines.append(f"- {name}: {count} ({pct:.0f}%)")
    lines.append("")

    best_track, track_scores = best_aligned_timing_track(song.placements, song.custom_timing_tracks)
    if track_scores:
        lines.append(f"## Custom timing track alignment (within {_TIMING_TRACK_ALIGNMENT_THRESHOLD_MS}ms)")
        for name, pct in sorted(track_scores.items(), key=lambda kv: -kv[1]):
            marker = " <- best" if name == best_track else ""
            lines.append(f"- {name}: {pct*100:.0f}%{marker}")
        lines.append("")

    group_placements = [p for p in song.placements if p.kind == "group"]
    white_base = [p for p in group_placements if p.blend_role == "white_base"]
    color_mask = [p for p in group_placements if p.blend_role == "color_mask"]
    if white_base or color_mask:
        lines.append(f"## White-base / color-mask layering technique (on {_FAMILY_LABEL} groups)")
        lines.append(
            f"- White-base placements (solid white, plain blend): {len(white_base)} "
            f"— effects: {', '.join(sorted({p.effect_name for p in white_base})) or '(none)'}"
        )
        lines.append(
            f"- Color-mask placements (solid color, mask-like blend): {len(color_mask)} "
            f"— effects: {', '.join(sorted({p.effect_name for p in color_mask})) or '(none)'}"
        )
        if color_mask:
            mask_colors = Counter(p.palette_colors[0] for p in color_mask)
            lines.append(f"- Mask colors used: {', '.join(f'{c}({n})' for c, n in mask_colors.most_common())}")
        if white_base and color_mask:
            lines.append(
                "- Both present -> this song likely uses a white base chase recolored by a "
                "mask-blended color layer (see layer_method on individual placements in data.json)."
            )
    lines.append("")

    if song.audio_correlation == "beats_only":
        lines.append("## Beat alignment (effect start vs nearest beat)")
        for threshold in _BEAT_ALIGN_THRESHOLDS_MS:
            aligned = sum(
                1 for p in song.placements
                if (d := nearest_beat_distance_ms(song.beat_times_ms, p.start_ms)) is not None
                and d <= threshold
            )
            pct = aligned / max(total, 1) * 100
            lines.append(f"- within {threshold}ms: {aligned}/{total} ({pct:.0f}%)")
        lines.append("")

    if song.section_correlation == "loaded":
        lines.append("## Effect placements by song section")
        section_counts = Counter()
        section_effect_by_label: dict[str, Counter] = defaultdict(Counter)
        for p in song.placements:
            section = section_at_time(song.sections, p.start_ms)
            label = section["label"] if section else "no_section_match"
            section_counts[label] += 1
            section_effect_by_label[label][p.effect_name] += 1
        for label, count in section_counts.most_common():
            pct = count / max(total, 1) * 100
            top_effects = ", ".join(f"{n}({c})" for n, c in section_effect_by_label[label].most_common(3))
            lines.append(f"- {label}: {count} placements ({pct:.0f}%) — top effects: {top_effects}")
        lines.append("")

    lines.append("## Duration distribution")
    duration_buckets = Counter(bucket_duration(p.duration_ms / 1000.0) for p in song.placements)
    for b in _DURATION_BUCKET_ORDER:
        count = duration_buckets.get(b, 0)
        if count:
            lines.append(f"- {b}: {count}")
    lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def rebuild_index_md(out_root: Path) -> int:
    """Regenerate INDEX.md from every <song slug>/data.json under out_root,
    so successive mining runs against different show folders merge into one
    corpus index instead of the last run clobbering the others. Returns the
    number of songs indexed."""
    songs: list[tuple[str, dict]] = []
    for data_path in sorted(out_root.glob("*/data.json")):
        songs.append((data_path.parent.name, json.loads(data_path.read_text(encoding="utf-8"))))

    lines = [f"# {_FAMILY_LABEL.capitalize()} sequencing corpus — index", ""]
    lines.append(f"Songs mined: {len(songs)}")
    audio_found = sum(1 for _, s in songs if s.get("audio_path"))
    lines.append(f"Audio located: {audio_found}/{len(songs)}")
    lines.append("")

    all_effects: Counter = Counter()
    for _, s in songs:
        all_effects.update(s.get("effect_usage", {}))

    lines.append("## Effect usage across all mined songs")
    total = sum(all_effects.values())
    for name, count in all_effects.most_common():
        pct = count / max(total, 1) * 100
        lines.append(f"- {name}: {count} ({pct:.0f}%)")
    lines.append("")

    songs_with_sections = [(slug, s) for slug, s in songs if s.get("section_correlation") == "loaded"]
    if songs_with_sections:
        lines.append(f"## Effect usage by song section (across {len(songs_with_sections)} songs with section data)")
        by_label: dict[str, Counter] = defaultdict(Counter)
        placements_per_label: Counter = Counter()
        for _, s in songs_with_sections:
            for p in s.get("placements", []):
                section = p.get("section")
                label = section["label"] if section else "no_section_match"
                by_label[label][p["effect_name"]] += 1
                placements_per_label[label] += 1
        for label, count in placements_per_label.most_common():
            top_effects = ", ".join(f"{n}({c})" for n, c in by_label[label].most_common(5))
            lines.append(f"- **{label}** ({count} placements): {top_effects}")
        lines.append("")

    lines.append("## Per-song detail")
    for slug, s in songs:
        xsq_name = Path(s.get("xsq_path", slug)).name
        lines.append(
            f"- [{xsq_name}]({slug}/summary.md) — {s.get('placement_count', 0)} placements, "
            f"audio {'found' if s.get('audio_path') else 'MISSING'}"
        )
    lines.append("")

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    return len(songs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global _PROP_TOKENS, _EXCLUDED_ELEMENT_TOKENS, _FAMILY_LABEL

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("show_folder", type=Path, help="Show folder containing .xsq sequences")
    parser.add_argument(
        "--family", type=str, default="arch",
        help="Prop family label used in reports and the default output directory (default: arch)",
    )
    parser.add_argument(
        "--tokens", type=str, default=None,
        help="Comma-separated case-insensitive name tokens that identify the family's "
             "models/groups (default: the family label itself)",
    )
    parser.add_argument(
        "--exclude-tokens", type=str, default=None,
        help="Comma-separated tokens that exclude an element even when it matches "
             "(default for arch: 'triple arch'; otherwise none)",
    )
    parser.add_argument("--out", type=Path, default=None,
                        help="Output corpus directory (default: docs/<family>_sequencing_corpus)")
    parser.add_argument("--skip-audio", action="store_true", help="Skip beat/energy analysis (structure-only mining)")
    parser.add_argument("--limit", type=int, default=None, help="Mine only the first N sequences found (for trial runs)")
    parser.add_argument("--only", type=str, default=None, help="Mine only sequences whose filename contains this substring (case-insensitive)")
    parser.add_argument(
        "--section-cache", type=Path, default=None,
        help="Directory of per-song mcp__xlights__get_song_structure JSON responses, "
             "named <slugified audio stem>.json. When a song's audio has no cache "
             "entry yet, its path is printed so it can be fetched and added.",
    )
    args = parser.parse_args()

    _FAMILY_LABEL = args.family.strip().lower()
    _PROP_TOKENS = tuple(
        t.strip().lower() for t in (args.tokens or _FAMILY_LABEL).split(",") if t.strip()
    )
    if args.exclude_tokens is not None:
        _EXCLUDED_ELEMENT_TOKENS = tuple(
            t.strip().lower() for t in args.exclude_tokens.split(",") if t.strip()
        )
    elif _FAMILY_LABEL != "arch":
        _EXCLUDED_ELEMENT_TOKENS = ()
    out_root: Path = args.out or Path(f"docs/{slugify(_FAMILY_LABEL)}_sequencing_corpus")

    show_folder: Path = args.show_folder
    if not show_folder.exists():
        raise SystemExit(f"Show folder not found: {show_folder}")

    print(f"Prop family: {_FAMILY_LABEL} (tokens: {', '.join(_PROP_TOKENS)}; "
          f"excluded: {', '.join(_EXCLUDED_ELEMENT_TOKENS) or '(none)'})")

    layout_path = find_layout_xml(show_folder)
    prop_elements: dict[str, PropElement] = {}
    if layout_path is not None:
        prop_elements = parse_prop_layout(layout_path)
        print(f"Layout: {layout_path}")
        print(f"{_FAMILY_LABEL} elements in layout: {len(prop_elements)} -> {sorted(prop_elements)}")
    else:
        print(f"No top-level xlights_rgbeffects.xml under {show_folder} — "
              f"only self-contained packages (with embedded layouts) can be mined")

    # Top-level only — don't descend into subdirectories (Backup/, Audio/,
    # etc.) when looking for sequences. .xsqz/.zip may be either a bare
    # zipped .xsq or a full show package with its own layout + audio.
    xsq_paths = sorted(
        p for ext in ("*.xsq", "*.xsqz", "*.zip")
        for p in show_folder.glob(ext)
    )
    print(f"Found {len(xsq_paths)} sequence file(s)")
    if args.only is not None:
        xsq_paths = [p for p in xsq_paths if args.only.lower() in p.name.lower()]
        print(f"Filtered to {len(xsq_paths)} sequence(s) matching {args.only!r}")
    if args.limit is not None:
        xsq_paths = xsq_paths[:args.limit]
        print(f"Limiting to first {len(xsq_paths)} sequence(s)")

    extract_root = Path(tempfile.mkdtemp(prefix="prop_corpus_pkg_"))
    mined: list[SongMining] = []
    for xsq_path in xsq_paths:
        mine_path = xsq_path
        elements = prop_elements
        audio_root = show_folder
        if xsq_path.suffix.lower() in (".xsqz", ".zip"):
            try:
                package_dir = extract_package(xsq_path, extract_root)
            except zipfile.BadZipFile:
                print(f"  SKIP {xsq_path.name}: not a valid zip archive")
                continue
            if package_dir is not None:
                pkg_layout = find_layout_xml(package_dir)
                elements = parse_prop_layout(pkg_layout)
                inner_xsq = find_package_xsq(package_dir)
                if inner_xsq is None:
                    print(f"  SKIP {xsq_path.name}: package has no .xsq inside")
                    continue
                mine_path = inner_xsq
                audio_root = package_dir
                print(f"  {xsq_path.name}: self-contained package — "
                      f"embedded layout has {len(elements)} {_FAMILY_LABEL} element(s)")

        if mine_path is xsq_path and not elements:
            print(f"  SKIP {xsq_path.name}: no layout to resolve {_FAMILY_LABEL} elements against")
            continue

        try:
            song = mine_sequence(mine_path, elements)
        except ET.ParseError as exc:
            print(f"  SKIP {xsq_path.name}: malformed XML ({exc})")
            continue
        song.xsq_path = xsq_path  # report the scanned file, not the temp extraction

        if not song.placements:
            print(f"  {xsq_path.name}: no {_FAMILY_LABEL} effect placements, skipping")
            continue

        song.audio_path = find_audio_file(audio_root, song.media_filename)
        if not args.skip_audio and song.audio_path is None:
            print(f"  {xsq_path.name}: no audio found, skipping")
            continue

        if args.skip_audio:
            song.audio_correlation = "not_attempted"
        else:
            try:
                tempo, beat_times_ms, rms, hop_seconds = analyze_beats_and_energy(song.audio_path)
                song.tempo_bpm = tempo
                song.beat_times_ms = beat_times_ms
                song.audio_correlation = "beats_only"
            except Exception as exc:  # librosa/audio decode failures — keep mining other songs
                print(f"  {xsq_path.name}: audio analysis failed ({exc})")
                song.audio_correlation = "failed"

        if args.section_cache is not None and song.audio_path is not None:
            cached = load_sections(args.section_cache, song.audio_path)
            if cached is not None:
                song.sections = cached
                song.section_correlation = "loaded"
            else:
                song.section_correlation = "not_cached"
                print(
                    f"  {xsq_path.name}: no section cache entry — fetch "
                    f"get_song_structure for {song.audio_path} and save to "
                    f"{section_cache_path(args.section_cache, song.audio_path)}"
                )

        mined.append(song)
        slug = slugify(song.song_title or xsq_path.stem)
        song_dir = out_root / slug
        song_dir.mkdir(parents=True, exist_ok=True)
        (song_dir / "data.json").write_text(json.dumps(song_to_dict(song), indent=2), encoding="utf-8")
        write_song_summary_md(song, song_dir)
        print(f"  {xsq_path.name}: {len(song.placements)} placements, audio_correlation={song.audio_correlation}")

    indexed = rebuild_index_md(out_root)
    print(f"\nMined {len(mined)} song(s) this run; INDEX.md now covers {indexed} song(s) in {out_root}")


if __name__ == "__main__":
    main()
