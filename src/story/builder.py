"""Song story builder — top-level orchestration for the song story tool.

Calls all foundational modules in order and assembles a complete SongStory dict.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
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

# ── Genius label → our role vocabulary ────────────────────────────────────────

_GENIUS_ROLE_MAP = {
    "intro": "intro",
    "verse": "verse",
    "chorus": "chorus",
    "hook": "chorus",
    "refrain": "chorus",
    "pre-chorus": "pre_chorus",
    "pre chorus": "pre_chorus",
    "post-chorus": "post_chorus",
    "post chorus": "post_chorus",
    "bridge": "bridge",
    "outro": "outro",
    "interlude": "interlude",
    "instrumental": "instrumental_break",
    "guitar solo": "instrumental_break",
    "solo": "instrumental_break",
    "sax solo": "instrumental_break",
    "piano solo": "instrumental_break",
    "drum solo": "instrumental_break",
    "break": "instrumental_break",
    "rap": "verse",
}


def _normalize_genius_label(label: str) -> str:
    """Convert a Genius section label like 'Verse 1' or 'Chorus: feat. X' to our role."""
    raw = label.lower().strip()
    # Strip artist/feature annotations: "Chorus: Ray Parker Jr." → "chorus"
    if ":" in raw:
        raw = raw.split(":")[0].strip()
    # Strip parenthetical: "Verse (Remix)" → "verse"
    raw = raw.split("(")[0].strip()

    # Exact match
    if raw in _GENIUS_ROLE_MAP:
        return _GENIUS_ROLE_MAP[raw]
    # Prefix match (e.g. "verse 1" → "verse")
    for key, role in _GENIUS_ROLE_MAP.items():
        if raw.startswith(key):
            return role
    return "verse"  # safe default for unknown Genius labels


def _try_genius_sections(
    audio_path: str,
    duration_ms: int,
) -> list[tuple[int, int, str]] | None:
    """Try to get section boundaries from Genius lyrics.

    Returns list of (start_ms, end_ms, role) on success, or None.

    whisperx and lyricsgenius live in .venv-vamp — run the pipeline there
    via subprocess to avoid import issues in the main venv.
    """
    token = os.environ.get("GENIUS_API_TOKEN", "")
    if not token:
        return None

    import subprocess as _sp

    repo_root = Path(__file__).resolve().parents[2]
    vamp_python = repo_root / ".venv-vamp" / "bin" / "python"
    if not vamp_python.exists():
        return None

    # Small script to run inside .venv-vamp
    script = f'''
import json, os, sys
sys.path.insert(0, {str(repo_root)!r})
os.environ["GENIUS_API_TOKEN"] = {token!r}
from pathlib import Path
from src.analyzer.genius_segments import GeniusSegmentAnalyzer
audio_path = {str(audio_path)!r}
audio_p = Path(audio_path)
stem_dir = audio_p.parent / "stems"
if not stem_dir.exists():
    stem_dir = audio_p.parent / ".stems"
analyzer = GeniusSegmentAnalyzer()
structure, _phonemes, warnings = analyzer.run(
    audio_path=audio_path,
    token=os.environ["GENIUS_API_TOKEN"],
    stem_dir=stem_dir if stem_dir.exists() else None,
    duration_ms={duration_ms},
)
if structure is None or not structure.segments:
    print(json.dumps({{"ok": False, "warnings": warnings}}))
else:
    segs = [{{"label": s.label, "start_ms": s.start_ms, "end_ms": s.end_ms}}
            for s in structure.segments]
    print(json.dumps({{"ok": True, "segments": segs, "warnings": warnings}}))
'''
    env = {**os.environ, "GENIUS_API_TOKEN": token}
    # Pass through override artist/title if set (from user prompt)
    for key in ("_GENIUS_OVERRIDE_ARTIST", "_GENIUS_OVERRIDE_TITLE"):
        if key in os.environ:
            env[key] = os.environ[key]

    try:
        proc = _sp.run(
            [str(vamp_python), "-c", script],
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if proc.returncode != 0:
            import sys
            print(f"[genius subprocess stderr]\n{proc.stderr[:500]}", file=sys.stderr)
            return None
        data = json.loads(proc.stdout.strip().split("\n")[-1])
        if not data.get("ok"):
            return None
        result: list[tuple[int, int, str]] = []
        for seg in data["segments"]:
            role = _normalize_genius_label(seg["label"])
            result.append((seg["start_ms"], seg["end_ms"], role))
        return result
    except Exception:
        return None


def _genius_quality_ok(
    genius_sections: list[tuple[int, int, str]],
    duration_ms: int,
) -> bool:
    """Return True if Genius sections are good enough to use as primary source.

    Rejects Genius data when:
    - Too few sections (<3 for songs >60s)
    - Any single section covers >60% of the song
    - Fewer than 2 distinct roles (e.g. all mapped to "verse")
    - Most sections are very short (<3s), suggesting bad alignment
    """
    if not genius_sections:
        return False

    n = len(genius_sections)
    dur_s = duration_ms / 1000.0

    # Too few sections for a non-trivial song
    if dur_s > 60 and n < 3:
        return False

    # Any section covers >60% of total duration
    for start, end, _role in genius_sections:
        if (end - start) > duration_ms * 0.6:
            return False

    # Need at least 2 distinct roles
    roles = set(r for _, _, r in genius_sections)
    if len(roles) < 2:
        return False

    # Most sections are too short (bad alignment)
    short_count = sum(1 for s, e, _ in genius_sections if (e - s) < 3_000)
    if short_count > n * 0.5:
        return False

    return True


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

    # ── Step 2: Try Genius lyrics as primary section source ─────────────────
    # When Genius API is available, it provides ground-truth section labels
    # (chorus, verse, bridge, etc.) with WhisperX-aligned timestamps.
    # Fall back to segmentino + energy heuristics when Genius isn't available.
    genius_sections = _try_genius_sections(audio_path, duration_ms)
    genius_ok = genius_sections and _genius_quality_ok(genius_sections, duration_ms)
    section_source = "genius" if genius_ok else "heuristic"

    if genius_ok:
        # Use Genius sections directly as our section boundaries + roles
        sections_ms = [(s, e) for s, e, _r in genius_sections]
        roles = [{"role": r, "confidence": 0.95} for _s, _e, r in genius_sections]

        # Post-process: detect implicit intro before first Genius section.
        # Genius sections start at the first lyric, but there's often an
        # instrumental intro before that.
        if sections_ms and sections_ms[0][0] > 3_000:
            sections_ms.insert(0, (0, sections_ms[0][0]))
            roles.insert(0, {"role": "intro", "confidence": 0.90})

        # Post-process: detect an implicit outro at the end.
        # Genius often has no [Outro] tag — the last section runs to the song end.
        # If the energy drops significantly in the tail, split off an outro.
        if len(sections_ms) >= 2 and roles[-1]["role"] != "outro":
            last_start, last_end = sections_ms[-1]
            last_dur = last_end - last_start
            energy_curves = hierarchy.get("energy_curves", {})
            full_mix = energy_curves.get("full_mix", {})
            fm_vals = full_mix.get("values", [])
            fm_fps = float(full_mix.get("fps") or full_mix.get("sample_rate") or 10)

            if fm_vals and last_dur > 15_000:
                # Compare energy in first half vs last 15 seconds of this section
                mid_ms = last_start + (last_dur // 2)
                first_si = int(last_start / 1000 * fm_fps)
                mid_si = int(mid_ms / 1000 * fm_fps)
                tail_si = int((last_end - 15_000) / 1000 * fm_fps)
                end_si = int(last_end / 1000 * fm_fps)

                first_chunk = fm_vals[first_si:mid_si]
                tail_chunk = fm_vals[tail_si:end_si]

                if first_chunk and tail_chunk:
                    first_mean = sum(first_chunk) / len(first_chunk)
                    tail_mean = sum(tail_chunk) / len(tail_chunk)

                    # If tail energy < 60% of first half → split off outro
                    if first_mean > 5 and tail_mean < first_mean * 0.6:
                        # Find the crossover point: scan backwards to find where
                        # energy drops below 70% of first-half mean
                        threshold = first_mean * 0.7
                        split_idx = end_si
                        for idx in range(end_si - 1, mid_si, -1):
                            if idx < len(fm_vals) and fm_vals[idx] >= threshold:
                                split_idx = idx + 1
                                break
                        split_ms = int(split_idx / fm_fps * 1000)
                        # Clamp to reasonable range
                        split_ms = max(mid_ms, min(split_ms, last_end - 5_000))

                        sections_ms[-1] = (last_start, split_ms)
                        sections_ms.append((split_ms, last_end))
                        roles.append({"role": "outro", "confidence": 0.80})
    else:
        # Fallback: segmentino boundaries + energy/vocal heuristics
        raw_sections: list[dict] = hierarchy.get("sections") or []
        raw_boundaries: list[int] = [int(s["time_ms"]) for s in raw_sections if "time_ms" in s]
        # Build a time→label map so we can propagate labels through merging
        boundary_label: dict[int, str] = {
            int(s["time_ms"]): s["label"]
            for s in raw_sections
            if "time_ms" in s and s.get("label")
        }
        boundaries_ms: list[int] = sorted(set([0] + raw_boundaries))

        # ── Step 3: Merge sections ────────────────────────────────────────────
        sections_ms = merge_sections(boundaries_ms, duration_ms)

        # Derive dominant segmentino label for each merged section.
        def _dominant_label(start_ms: int, end_ms: int) -> str | None:
            candidates = [
                (t, boundary_label[t])
                for t in boundary_label
                if start_ms <= t < end_ms
            ]
            if not candidates:
                before = [(t, boundary_label[t]) for t in boundary_label if t <= start_ms]
                if before:
                    return max(before, key=lambda x: x[0])[1]
                return None
            return min(candidates, key=lambda x: x[0])[1]

        section_labels: list[str | None] = [
            _dominant_label(start, end) for start, end in sections_ms
        ]

        # ── Step 4: Classify roles ────────────────────────────────────────────
        roles = classify_section_roles(sections_ms, hierarchy, section_labels)

        # ── Step 4b: Merge consecutive same-role sections ─────────────────────
        merged_sections: list[tuple[int, int]] = []
        merged_roles: list[dict] = []
        for sec, role in zip(sections_ms, roles):
            if merged_sections and merged_roles[-1]["role"] == role["role"]:
                prev_start = merged_sections[-1][0]
                merged_sections[-1] = (prev_start, sec[1])
                if role["confidence"] > merged_roles[-1]["confidence"]:
                    merged_roles[-1] = role
            else:
                merged_sections.append(sec)
                merged_roles.append(role)

        sections_ms = merged_sections
        roles = merged_roles

    # ── Step 5: Profile each section ──────────────────────────────────────────
    profiles: list[dict] = [
        profile_section(start, end, hierarchy)
        for start, end in sections_ms
    ]

    # ── Step 5b: Normalize energy within the song ─────────────────────────────
    # Raw energy_score values are absolute (0–100 from the curve generator).
    # Songs with a narrow dynamic range (e.g. classical) can have all sections
    # score 30–50, making them all "low". Rescale so the song's own min→0 and
    # max→100, preserving relative dynamics.
    raw_scores = [p["character"]["energy_score"] for p in profiles]
    if raw_scores:
        e_min = min(raw_scores)
        e_max = max(raw_scores)
        e_range = e_max - e_min
        for p in profiles:
            char = p["character"]
            raw = char["energy_score"]
            if e_range > 0:
                char["energy_score"] = int(round((raw - e_min) / e_range * 100))
            else:
                char["energy_score"] = 50  # all sections identical energy
            # Also rescale peak
            raw_peak = char["energy_peak"]
            if e_range > 0:
                char["energy_peak"] = int(min(100, max(0, round((raw_peak - e_min) / e_range * 100))))
            # Re-derive energy_level from normalized score
            s = char["energy_score"]
            char["energy_level"] = "low" if s <= 33 else ("medium" if s <= 66 else "high")

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
            "section_source": section_source,
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
