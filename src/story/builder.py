"""Song story builder — top-level orchestration for the song story tool.

Calls all foundational modules in order and assembles a complete SongStory dict.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

from src.story.section_merger import merge_sections
from src.story.section_classifier import classify_section_roles
from src.story.section_profiler import profile_section
from src.story.moment_classifier import classify_moments
from src.story.energy_arc import detect_energy_arc
from src.story.lighting_mapper import map_lighting
from src.story.stem_curves import extract_stem_curves

SCHEMA_VERSION = "1.0.0"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS.mmm."""
    total_ms = round(seconds * 1000)
    minutes = total_ms // 60_000
    remaining = total_ms % 60_000
    secs = remaining // 1000
    millis = remaining % 1000
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def _compute_moment_pattern(moments_in_section: list[dict]) -> str:
    """Return the dominant pattern among moments in a section, or 'isolated'."""
    if not moments_in_section:
        return "isolated"
    pattern_counts: dict[str, int] = {}
    for m in moments_in_section:
        p = m.get("pattern", "isolated")
        pattern_counts[p] = pattern_counts.get(p, 0) + 1
    # Return the most common pattern
    return max(pattern_counts, key=lambda p: pattern_counts[p])


# ── Main builder ───────────────────────────────────────────────────────────────

def build_song_story(hierarchy: dict, audio_path: str) -> dict:
    """Orchestrate all foundational modules to produce a complete song story dict.

    Parameters
    ----------
    hierarchy:
        HierarchyResult-compatible dict (from HierarchyResult.to_dict()).
    audio_path:
        Path to the source audio file (used for title/artist extraction).

    Returns
    -------
    A complete song story dict matching schema_version 1.0.0.
    """
    # ── Step 1: Extract metadata from hierarchy ────────────────────────────────
    source_hash: str = hierarchy.get("source_hash", "")
    duration_ms: int = int(hierarchy.get("duration_ms", 0))
    estimated_bpm: float = float(hierarchy.get("estimated_bpm", 120.0))
    source_file: str = hierarchy.get("source_file", audio_path)
    stems_available: list[str] = list(hierarchy.get("stems_available") or [])

    # ── Step 2: Extract section boundaries ────────────────────────────────────
    raw_sections: list[dict] = hierarchy.get("sections") or []
    raw_boundaries: list[int] = [int(s["time_ms"]) for s in raw_sections if "time_ms" in s]
    # Deduplicate; always include 0
    boundaries_ms: list[int] = sorted(set([0] + raw_boundaries))

    # ── Step 3: Merge sections ─────────────────────────────────────────────────
    sections_ms: list[tuple[int, int]] = merge_sections(boundaries_ms, duration_ms)

    # ── Step 4: Classify roles ─────────────────────────────────────────────────
    roles: list[dict] = classify_section_roles(sections_ms, hierarchy)

    # ── Step 5: Profile each section ──────────────────────────────────────────
    profiles: list[dict] = [
        profile_section(start, end, hierarchy)
        for start, end in sections_ms
    ]

    # ── Step 6: Compute energy arc ────────────────────────────────────────────
    energy_curves: dict = hierarchy.get("energy_curves") or {}
    full_mix_curve: dict = energy_curves.get("full_mix") or {}
    full_mix_values: list[float] = full_mix_curve.get("values") or []
    arc_shape: str = detect_energy_arc(full_mix_values)

    # ── Step 7: Detect moments ────────────────────────────────────────────────
    moments: list[dict] = classify_moments(hierarchy, sections_ms)

    # ── Step 8: Map lighting for each section ─────────────────────────────────
    # Build per-section lighting dicts (moment_count/moment_pattern updated later)
    section_lightings: list[dict] = []
    for i, (role_info, profile) in enumerate(zip(roles, profiles)):
        role = role_info["role"]
        energy_level = profile["character"]["energy_level"]
        lighting = map_lighting(role, energy_level)
        section_lightings.append(lighting)

    # ── Step 9: Extract stem curves ───────────────────────────────────────────
    stem_curves: dict = extract_stem_curves(hierarchy, duration_ms)

    # ── Step 10: Compute global properties ────────────────────────────────────
    # Tempo stability via CV of beat intervals
    beats_track: dict = hierarchy.get("beats") or {}
    beat_marks: list[dict] = beats_track.get("marks") or []
    tempo_stability: str = "steady"
    if len(beat_marks) >= 2:
        beat_times = [m["time_ms"] for m in beat_marks if "time_ms" in m]
        beat_times.sort()
        if len(beat_times) >= 2:
            intervals = [
                beat_times[i + 1] - beat_times[i]
                for i in range(len(beat_times) - 1)
            ]
            mean_interval = sum(intervals) / len(intervals)
            if mean_interval > 0:
                variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
                cv = math.sqrt(variance) / mean_interval
                if cv < 0.05:
                    tempo_stability = "steady"
                elif cv < 0.15:
                    tempo_stability = "variable"
                else:
                    tempo_stability = "free"

    # Key from essentia_features
    essentia: dict = hierarchy.get("essentia_features") or {}
    key_root: str = essentia.get("key", "C")
    key_scale: str = essentia.get("key_scale", "major")
    key: str = f"{key_root} {key_scale}"
    key_confidence: float = float(essentia.get("key_strength", 0.5))

    # Vocal coverage: fraction of full_mix energy frames where vocals RMS > 0.05
    vocals_curve: dict = energy_curves.get("vocals") or {}
    vocals_values: list[float] = vocals_curve.get("values") or []
    if vocals_values:
        vocal_frames_above = sum(1 for v in vocals_values if v > 0.05)
        vocal_coverage: float = float(vocal_frames_above / len(vocals_values))
    else:
        vocal_coverage = 0.0

    # Harmonic/percussive ratio: use song-wide stem means
    harmonic_stems = ("guitar", "piano", "bass", "vocals")
    percussive_stems = ("drums",)

    def _curve_mean(stem_name: str) -> float:
        c = energy_curves.get(stem_name) or {}
        vals = c.get("values") or []
        return float(sum(vals) / len(vals)) if vals else 0.0

    harmonic_energy = sum(_curve_mean(s) for s in harmonic_stems)
    percussive_energy = _curve_mean("drums")
    if percussive_energy > 0:
        harmonic_percussive_ratio: float = float(harmonic_energy / percussive_energy)
    else:
        harmonic_percussive_ratio = float(harmonic_energy * 2.0) if harmonic_energy > 0 else 1.0

    # Onset density avg: total onsets / duration_seconds
    duration_seconds: float = duration_ms / 1000.0
    events: dict = hierarchy.get("events") or {}
    total_onsets: int = 0
    for stem_events in events.values():
        if isinstance(stem_events, dict):
            total_onsets += len(stem_events.get("marks") or [])
    onset_density_avg: float = float(total_onsets / duration_seconds) if duration_seconds > 0 else 0.0

    # ── Step 11: Assemble song identity ───────────────────────────────────────
    audio_p = Path(audio_path)
    title: str = audio_p.stem
    artist: str = "Unknown"
    genre: str | None = None

    # ── Step 12: Try reading ID3 tags via mutagen ──────────────────────────────
    try:
        import mutagen  # type: ignore
        from mutagen.id3 import ID3  # type: ignore
        tags = ID3(audio_path)
        if "TIT2" in tags and str(tags["TIT2"]).strip():
            title = str(tags["TIT2"]).strip()
        if "TPE1" in tags and str(tags["TPE1"]).strip():
            artist = str(tags["TPE1"]).strip()
        if "TCON" in tags and str(tags["TCON"]).strip():
            genre = str(tags["TCON"]).strip()
    except Exception:
        # mutagen not available, file not readable, or no ID3 tags — use defaults
        pass

    duration_formatted: str = _fmt_time(duration_seconds)

    # ── Step 13: Assign moments to sections ───────────────────────────────────
    # Build a mapping from section index → moments within that section
    section_moments: list[list[dict]] = [[] for _ in sections_ms]
    for moment in moments:
        moment_time_ms = moment["time"] * 1000.0
        for idx, (start, end) in enumerate(sections_ms):
            if start <= moment_time_ms < end:
                section_moments[idx].append(moment)
                break

    # ── Step 14: Update lighting with moment data ──────────────────────────────
    for i, lighting in enumerate(section_lightings):
        moments_here = section_moments[i]
        lighting["moment_count"] = len(moments_here)
        lighting["moment_pattern"] = _compute_moment_pattern(moments_here)

    # ── Step 15: Assemble sections list ───────────────────────────────────────
    sections_out: list[dict] = []
    for i, ((start_ms, end_ms), role_info, profile, lighting) in enumerate(
        zip(sections_ms, roles, profiles, section_lightings), start=1
    ):
        start_sec = start_ms / 1000.0
        end_sec = end_ms / 1000.0
        duration_sec = end_sec - start_sec

        section_dict: dict[str, Any] = {
            "id": f"s{i:02d}",
            "role": role_info["role"],
            "role_confidence": round(float(role_info["confidence"]), 4),
            "start": round(start_sec, 3),
            "end": round(end_sec, 3),
            "start_fmt": _fmt_time(start_sec),
            "end_fmt": _fmt_time(end_sec),
            "duration": round(duration_sec, 3),
            "character": profile["character"],
            "stems": profile["stems"],
            "lighting": lighting,
            "overrides": {
                "role": None,
                "energy_level": None,
                "mood": None,
                "theme": None,
                "focus_stem": None,
                "intensity": None,
                "notes": None,
                "is_highlight": False,
            },
        }
        sections_out.append(section_dict)

    # ── Assemble the complete story dict ──────────────────────────────────────
    story: dict = {
        "schema_version": SCHEMA_VERSION,
        "song": {
            "title": title,
            "artist": artist,
            "file": str(audio_path),
            "source_hash": source_hash,
            "duration_seconds": round(duration_seconds, 3),
            "duration_formatted": duration_formatted,
        },
        "global": {
            "tempo_bpm": round(estimated_bpm, 2),
            "tempo_stability": tempo_stability,
            "key": key,
            "key_confidence": round(key_confidence, 4),
            "energy_arc": arc_shape,
            "vocal_coverage": round(vocal_coverage, 4),
            "harmonic_percussive_ratio": round(harmonic_percussive_ratio, 4),
            "onset_density_avg": round(onset_density_avg, 4),
            "stems_available": stems_available,
        },
        "preferences": {
            "mood": None,
            "theme": None,
            "focus_stem": None,
            "intensity": 1.0,
            "occasion": "general",
            "genre": genre,
        },
        "sections": sections_out,
        "moments": moments,
        "stems": stem_curves,
        "review": {
            "status": "draft",
            "reviewed_at": None,
            "reviewer_notes": None,
        },
    }

    return story


# ── File I/O ───────────────────────────────────────────────────────────────────

def write_song_story(story: dict, output_path: str) -> None:
    """Write story dict as pretty-printed JSON to output_path.

    Raises FileExistsError if file exists and story already has
    review.status=="reviewed" (overwrite protection for reviewed stories).
    """
    p = Path(output_path)
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        if existing.get("review", {}).get("status") == "reviewed":
            raise FileExistsError(
                f"Cannot overwrite reviewed story: {output_path}. "
                "Use --force to overwrite."
            )

    p.write_text(
        json.dumps(story, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_song_story(path: str) -> dict:
    """Load song story JSON from path.

    Raises FileNotFoundError if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Song story not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def write_edits(edits: dict, path: str) -> None:
    """Write edits dict as pretty-printed JSON to path."""
    Path(path).write_text(
        json.dumps(edits, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_edits(path: str) -> dict:
    """Load edits dict from path.

    Raises FileNotFoundError if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Edits file not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


# ── Merge ──────────────────────────────────────────────────────────────────────

def merge_story_with_edits(base: dict, edits: dict) -> dict:
    """Deep-copy base dict, apply edits, and return a merged story.

    Supported edit actions:
    - rename: update section["role"] and re-run lighting mapper
    - override: update section["overrides"] with edit["overrides"]
    - split, merge, boundary: skipped for MVP (structural edits)

    Moment edits:
    - dismissed: True/False — find moment by id, set dismissed accordingly.

    Sets review.status="reviewed" on the merged result.
    """
    merged: dict = copy.deepcopy(base)

    # Apply song-wide preferences
    preferences_edit = edits.get("preferences")
    if preferences_edit and isinstance(preferences_edit, dict):
        merged.setdefault("preferences", {}).update(preferences_edit)

    # Build a section lookup by id
    section_by_id: dict[str, dict] = {
        s["id"]: s for s in merged.get("sections", [])
    }

    # Apply section edits
    for edit in edits.get("section_edits", []):
        sid = edit.get("section_id") or edit.get("id")
        action = edit.get("action")
        section = section_by_id.get(sid)
        if section is None:
            continue  # Unknown section — skip

        if action == "rename":
            new_role = edit.get("new_role") or edit.get("role")
            if new_role:
                section["role"] = new_role
                # Re-run lighting mapper for this section
                energy_level = section["character"]["energy_level"]
                new_lighting = map_lighting(new_role, energy_level)
                # Preserve moment_count and moment_pattern from existing lighting
                new_lighting["moment_count"] = section["lighting"].get("moment_count", 0)
                new_lighting["moment_pattern"] = section["lighting"].get("moment_pattern", "isolated")
                section["lighting"] = new_lighting
            # Also apply any overrides included with the rename
            if "overrides" in edit:
                section.setdefault("overrides", {}).update(edit["overrides"])

        elif action == "override":
            if "overrides" in edit:
                section.setdefault("overrides", {}).update(edit["overrides"])

        elif action in ("split", "merge", "boundary"):
            # Structural edits require a full rebuild — skip for MVP
            pass

    # Apply moment edits
    moment_by_id: dict[str, dict] = {
        m["id"]: m for m in merged.get("moments", [])
    }
    for medit in edits.get("moment_edits", []):
        mid = medit.get("moment_id") or medit.get("id")
        moment = moment_by_id.get(mid)
        if moment is None:
            continue
        if "dismissed" in medit:
            moment["dismissed"] = bool(medit["dismissed"])

    # Update review state
    merged.setdefault("review", {})["status"] = "reviewed"
    merged["review"]["reviewer_notes"] = edits.get("reviewer_notes")

    return merged
