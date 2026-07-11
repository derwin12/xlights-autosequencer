"""Song story builder — top-level orchestration for the song story tool.

Calls all foundational modules in order and assembles a complete SongStory dict.
"""
from __future__ import annotations

import copy
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.analyzer.boundary_cluster import (
    AgreementCluster,
    agreement_score_at,
    build_clusters_for_hierarchy,
)
from src.story.section_merger import merge_sections
from src.story.section_classifier import classify_section_roles
from src.story.section_profiler import profile_section
from src.story.moment_classifier import classify_moments
from src.story.energy_arc import detect_energy_arc
from src.story.lighting_mapper import map_lighting
from src.story.stem_curves import extract_stem_curves

SCHEMA_VERSION = "1.1.0"


def _portable_audio_path(audio_path: str | Path) -> str:
    """Return a show-dir-relative path for storage in story JSON.

    Falls back to the absolute path string if the show dir is not known or
    the audio file lives outside the show dir.
    """
    from src.paths import to_show_relative
    return to_show_relative(audio_path)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _discover_vocals_stem(audio_path: str) -> Path | None:
    """Find a cached vocals stem next to ``audio_path``, or None if absent."""
    audio_p = Path(audio_path)
    for stem_dir in (
        audio_p.parent / "stems",
        audio_p.parent / ".stems",
        audio_p.parent / audio_p.stem / "stems",
        audio_p.parent / audio_p.stem / ".stems",
    ):
        for ext in ("mp3", "wav"):
            candidate = stem_dir / f"vocals.{ext}"
            if candidate.exists():
                return candidate
    return None


def _try_free_transcription(audio_path: str, duration_ms: int) -> list[dict]:
    """Run a standalone WhisperX free-transcription pass for boundary refinement.

    No reference lyrics are involved — the model transcribes whatever it
    hears. Used as ground-truth "is anyone audibly singing here" evidence by
    ``src.story.boundary_refinement`` (Fix 3: split a pre-vocal instrumental
    lead-in off a vocal section).

    Returns a list of {label, start_ms, end_ms} dicts, or [] when whisperx
    isn't available, no vocals stem/audio can be read, or the subprocess fails.

    whisperx lives in .venv-vamp — run it there via subprocess to avoid
    import issues in the main venv (same pattern as the retired Genius
    pipeline).
    """
    import subprocess as _sp
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    vamp_python = (
        Path(os.environ["XLIGHT_VENV_VAMP"])
        if os.environ.get("XLIGHT_VENV_VAMP")
        else repo_root / ".venv-vamp" / "bin" / "python"
    )
    if not vamp_python.exists():
        return []

    vocals_path = _discover_vocals_stem(audio_path)
    transcribe_path = str(vocals_path) if vocals_path is not None else str(audio_path)
    duration_s = duration_ms / 1000.0 if duration_ms > 0 else 0.0

    script = f'''
import json, os, sys
sys.path.insert(0, {str(repo_root)!r})
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
try:
    import torch
    _orig_torch_load = torch.load
    def _torch_load_compat(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_torch_load(*args, **kwargs)
    torch.load = _torch_load_compat
except Exception:
    pass
from src.analyzer.free_transcription import transcribe_free
words = transcribe_free(
    {transcribe_path!r}, language="en", device="cpu",
    duration_s={duration_s!r} or None,
)
print(json.dumps([
    {{"label": w.label, "start_ms": int(w.start_ms), "end_ms": int(w.end_ms)}}
    for w in words
]))
'''
    try:
        proc = _sp.run(
            [str(vamp_python), "-c", script],
            capture_output=True, text=True, timeout=600,
        )
    except Exception as exc:
        print(f"[free-transcription subprocess exception: {exc}]", file=sys.stderr)
        return []

    if proc.returncode != 0:
        print(f"[free-transcription subprocess stderr]\n{proc.stderr[:800]}", file=sys.stderr)
        return []
    try:
        return json.loads(proc.stdout.strip().split("\n")[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        print(f"[free-transcription subprocess: could not parse stdout: {exc}]", file=sys.stderr)
        return []




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

def build_song_story(
    hierarchy: dict,
    audio_path: str,
) -> dict:
    """Orchestrate all foundational modules to produce a complete song story dict.

    Parameters
    ----------
    hierarchy:
        HierarchyResult-compatible dict (from HierarchyResult.to_dict()).
    audio_path:
        Path to the source audio file (used for title/artist extraction).

    Returns
    -------
    A complete song story dict matching schema_version 1.1.0.

    Changes since 1.0.0 (additive only — readers SHALL default missing
    fields per the conventions in
    ``openspec/changes/lyric-anchored-boundary-refinement/specs/``):

    - Each ``sections[i]`` gains an optional ``boundary_refinements:
      list[str]`` field describing any lyric-anchored refinements applied
      to that section's boundaries (or ``[]`` when none fired).
    """
    # ── Step 1: Extract metadata from hierarchy ────────────────────────────────
    source_hash: str = hierarchy.get("source_hash", "")
    duration_ms: int = int(hierarchy.get("duration_ms", 0))
    estimated_bpm: float = float(hierarchy.get("estimated_bpm", 120.0))
    source_file: str = hierarchy.get("source_file", audio_path)
    stems_available: list[str] = list(hierarchy.get("stems_available") or [])

    # ── Step 2a: Build multi-source agreement clusters ──────────────────────
    # Used to score each final section by how many independent sources
    # corroborate its start boundary. See src.analyzer.boundary_cluster.
    bar_ms = int(round(60_000.0 / max(estimated_bpm, 1.0) * 4))
    clusters: list[AgreementCluster] = build_clusters_for_hierarchy(
        hierarchy, bar_ms,
    )

    # ── Step 2: Section boundaries — segmentino + energy heuristics ─────────
    section_source = "heuristic"

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

        # Agreement score: how many independent sources corroborate this
        # section's start boundary (QM, segmentino, stem_entry:*, energy
        # impact/drop, key_change, chord_density). 0 = only this section
        # source agrees; 3+ = strong multi-source consensus. Used by the
        # review UI to surface low-confidence sections.
        agreement_score = agreement_score_at(start_ms, clusters, tolerance_ms=bar_ms)

        section_dict: dict[str, Any] = {
            "id": f"s{i:02d}",
            "role": role_info["role"],
            "role_confidence": round(float(role_info["confidence"]), 4),
            "agreement_score": int(agreement_score),
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

    # ── Step 15b: SSM Chorus validator ────────────────────────────────────────
    # Per design D1 in
    # ``openspec/changes/agreement-score-operationalization/design.md``,
    # SSM is a Chorus validator only — it cannot promote a Verse to a
    # Chorus or vice versa. We tag every Chorus section with
    # ``chorus_ssm_supported``: True iff at least one other Chorus is
    # in the same repetition group, OR if the section's time-span
    # overlaps any group with two-or-more members (the latter covers
    # the case where the SSM detects a repeat but the heuristic classifier
    # only labels one of the occurrences as Chorus).
    #
    # Tri-state ``repetition_groups`` source semantics (see HierarchyResult
    # docstring): None = SSM skipped/errored; [] = SSM ran, no groups;
    # populated list = groups detected. For both None and [] we default
    # every Chorus to supported per spec ("absence of evidence is not
    # evidence of absence").
    rg_data = hierarchy.get("repetition_groups")
    repetition_groups: list[dict] = []
    if isinstance(rg_data, list):
        repetition_groups = rg_data
    has_ssm_evidence = bool(repetition_groups)

    if has_ssm_evidence:
        # Build a quick index: section_index → list of group_ids it
        # overlaps.  Overlap = section's [start_ms, end_ms] intersects
        # any group member's [start_ms, end_ms].
        section_to_groups: dict[int, list[int]] = {}
        for sec_idx, ((sec_start_ms, sec_end_ms), _role_info, _profile, _lighting) in enumerate(
            zip(sections_ms, roles, profiles, section_lightings)
        ):
            overlap_groups: list[int] = []
            for group in repetition_groups:
                gid = int(group.get("id", -1))
                members = group.get("members") or []
                for member in members:
                    # Member is [start_ms, end_ms] (list after JSON
                    # round-trip) or (start_ms, end_ms) tuple.
                    if not member or len(member) != 2:
                        continue
                    m_start, m_end = int(member[0]), int(member[1])
                    if m_start < sec_end_ms and m_end > sec_start_ms:
                        overlap_groups.append(gid)
                        break
            section_to_groups[sec_idx] = overlap_groups

        # Group sizes (number of distinct member spans) for the overlap
        # rule: a Chorus is supported by any group with ≥ 2 members
        # that it overlaps.
        group_sizes: dict[int, int] = {
            int(g.get("id", -1)): len(g.get("members") or [])
            for g in repetition_groups
        }

        # Choruses sharing groups with each other.
        chorus_indices = [
            i for i, sec in enumerate(sections_out) if sec.get("role") == "chorus"
        ]

        for sec_idx in chorus_indices:
            my_groups = set(section_to_groups.get(sec_idx, []))
            supported = False
            # Rule (a): another Chorus shares a group.
            for other_idx in chorus_indices:
                if other_idx == sec_idx:
                    continue
                if my_groups & set(section_to_groups.get(other_idx, [])):
                    supported = True
                    break
            # Rule (b): overlap any group with ≥ 2 members.
            if not supported:
                for gid in my_groups:
                    if group_sizes.get(gid, 0) >= 2:
                        supported = True
                        break
            sections_out[sec_idx]["chorus_ssm_supported"] = supported
    else:
        # No SSM evidence available → spec default: every Chorus is
        # supported (absence of evidence is not evidence of absence).
        for sec in sections_out:
            if sec.get("role") == "chorus":
                sec["chorus_ssm_supported"] = True

    # ── Step 15c: Lyric-anchored boundary refinement ──────────────────────────
    # OpenSpec change ``lyric-anchored-boundary-refinement``. Fix 3 (split a
    # pre-vocal instrumental lead-in off a vocal section) runs on a standalone
    # WhisperX free-transcription pass. Fix 1 (merge short post_chorus tails)
    # and Fix 2 (relabel/split bridges whose sung content opens with the
    # chorus first-line hook) need forced-aligned lyric text and a known
    # chorus body — sourced from ``syncedlyrics`` (token-free, multi-provider
    # lookup; Genius provider excluded — see
    # docs/segment-classification-changelog.md) since the retired Genius
    # integration no longer supplies them.
    from src.analyzer.phonemes import WordMark
    from src.analyzer.synced_lyrics import get_boundary_refinement_inputs
    from src.story.boundary_refinement import refine_section_boundaries

    free_words_raw = _try_free_transcription(audio_path, duration_ms)
    free_marks = [
        WordMark(label=w["label"], start_ms=int(w["start_ms"]), end_ms=int(w["end_ms"]))
        for w in free_words_raw
    ]
    forced_marks, chorus_body, lyric_line_marks = get_boundary_refinement_inputs(
        title, artist, duration_ms
    )
    sections_out, refinement_notes = refine_section_boundaries(
        sections_out,
        forced_words=forced_marks,
        free_words=free_marks,
        chorus_body=chorus_body,
    )
    refinement_warnings: list[str] = []
    if not free_marks:
        refinement_warnings.append(
            "boundary refinement skipped: Fix 3 — no free-transcription "
            "word marks (whisperx unavailable or no vocals)"
        )
    if not chorus_body:
        refinement_warnings.append(
            "boundary refinement skipped: Fix 2 — no synced lyrics found "
            "(no chorus body to match against)"
        )
    if not forced_marks:
        refinement_warnings.append(
            "boundary refinement skipped: Fix 1 — no synced lyrics found "
            "(no forced-aligned word marks)"
        )

    # ── Assemble the complete story dict ──────────────────────────────────────
    story: dict = {
        "schema_version": SCHEMA_VERSION,
        "song": {
            "title": title,
            "artist": artist,
            "file": _portable_audio_path(audio_path),
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
        # Synced-lyrics line track for the Timeline UI (Fix 1/2 above reuse
        # the same fetch — see get_boundary_refinement_inputs). One entry
        # per LRC line: {t_ms, duration_ms, text}. Empty when no match.
        "lyrics": [
            {"t_ms": m.time_ms, "duration_ms": m.duration_ms, "text": m.label}
            for m in lyric_line_marks
        ],
        "review": {
            "status": "draft",
            "reviewed_at": None,
            "reviewer_notes": None,
        },
        # Capability-skip warnings from Step 15c boundary refinement (one
        # entry per skipped fix per song; per-section non-fires are silent).
        # Empty list when refinement ran cleanly or the feature flag is off.
        # The analyze-step API merges these into ``HierarchyResult.warnings``
        # so they surface in the UI's warnings panel — see OpenSpec change
        # ``lyric-anchored-boundary-refinement`` §7.
        "refinement_warnings": refinement_warnings,
    }

    return story


# ── File I/O ───────────────────────────────────────────────────────────────────

# Default number of historical _story.json snapshots to keep per song.
# Override with the XLIGHT_STORY_HISTORY_MAX environment variable.
DEFAULT_STORY_HISTORY_MAX = 5


def _story_history_dir(story_path: Path) -> Path:
    """Return the per-song history directory for a given story path.

    Layout: ``<song_dir>/<stem>.history/`` where ``stem`` is the story file's
    name without the ``.json`` suffix (so ``foo_story.json`` archives go to
    ``foo_story.history/``). Multiple stories in the same dir don't collide.
    """
    return story_path.parent / f"{story_path.stem}.history"


def _story_history_max() -> int:
    """Read the retention cap from the environment, falling back to default."""
    raw = os.environ.get("XLIGHT_STORY_HISTORY_MAX")
    if raw is None or raw.strip() == "":
        return DEFAULT_STORY_HISTORY_MAX
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_STORY_HISTORY_MAX
    return max(0, n)


def _archive_existing_story(story_path: Path, *, max_entries: int) -> Path | None:
    """Move an existing story file into the per-song history directory.

    Returns the archived snapshot path (inside the history dir), or ``None`` if
    no existing file was found. After archiving, oldest snapshots beyond
    ``max_entries`` are deleted.

    The timestamp uses ISO-8601 with ``Z`` suffix and ``-`` separators
    (filesystem-safe), e.g. ``2026-04-25T19-24-31Z.json``.
    """
    if not story_path.exists():
        return None
    if max_entries <= 0:
        # Retention disabled — drop the previous file without archiving.
        story_path.unlink(missing_ok=True)
        return None

    history_dir = _story_history_dir(story_path)
    history_dir.mkdir(parents=True, exist_ok=True)

    # ISO-8601 UTC timestamp, colons replaced with ``-`` for filesystem safety.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base_ts = now.strftime("%Y-%m-%dT%H-%M-%SZ")

    # Avoid overwrite collisions when the same second produces two archives
    # (rapid back-to-back overwrites in tests / scripts).
    candidate = history_dir / f"{base_ts}.json"
    if candidate.exists():
        suffix = 1
        while True:
            candidate = history_dir / f"{base_ts}-{suffix:02d}.json"
            if not candidate.exists():
                break
            suffix += 1

    story_path.rename(candidate)
    _prune_story_history(history_dir, max_entries=max_entries)
    return candidate


def _prune_story_history(history_dir: Path, *, max_entries: int) -> list[Path]:
    """Delete oldest snapshots until at most ``max_entries`` remain.

    Returns the list of deleted paths.
    """
    if not history_dir.exists():
        return []
    snapshots = sorted(
        (p for p in history_dir.iterdir() if p.is_file() and p.suffix == ".json"),
        key=lambda p: p.name,
    )
    excess = len(snapshots) - max_entries
    if excess <= 0:
        return []
    deleted: list[Path] = []
    for old in snapshots[:excess]:
        try:
            old.unlink()
            deleted.append(old)
        except OSError:
            # Best-effort cleanup — leave residue if filesystem refuses.
            pass
    return deleted


def list_story_history(story_path: str | Path) -> list[Path]:
    """List archived story snapshots for ``story_path``, oldest first.

    Returns an empty list if no history dir exists.
    """
    history_dir = _story_history_dir(Path(story_path))
    if not history_dir.exists():
        return []
    return sorted(
        (p for p in history_dir.iterdir() if p.is_file() and p.suffix == ".json"),
        key=lambda p: p.name,
    )


def resolve_history_entry(story_path: str | Path, ref: str) -> Path:
    """Resolve a history reference (timestamp prefix or ``current``) to a path.

    - ``"current"`` → the live ``_story.json`` path
    - any other value → the unique archived snapshot whose filename starts
      with the given prefix (e.g. ``2026-04-25`` matches today's snapshots).
      Raises ``FileNotFoundError`` if no match, or ``ValueError`` if ambiguous.
    """
    sp = Path(story_path)
    if ref == "current":
        if not sp.exists():
            raise FileNotFoundError(f"No current story at {sp}")
        return sp
    history_dir = _story_history_dir(sp)
    if not history_dir.exists():
        raise FileNotFoundError(
            f"No history directory for {sp} (looked at {history_dir})"
        )
    matches = [
        p for p in history_dir.iterdir()
        if p.is_file() and p.suffix == ".json" and p.name.startswith(ref)
    ]
    if not matches:
        raise FileNotFoundError(
            f"No history entry for {sp.name} matching {ref!r}"
        )
    if len(matches) > 1:
        names = ", ".join(sorted(m.name for m in matches))
        raise ValueError(
            f"Ambiguous history reference {ref!r}: matches {names}"
        )
    return matches[0]


def write_song_story(story: dict, output_path: str) -> None:
    """Write story dict as pretty-printed JSON to output_path.

    Raises FileExistsError if file exists and story already has
    review.status=="reviewed" (overwrite protection for reviewed stories).

    Before overwriting an existing non-reviewed story, the previous version is
    archived to ``<output_dir>/<stem>.history/<ISO-timestamp>.json`` and the
    history is pruned to the most recent ``XLIGHT_STORY_HISTORY_MAX`` entries
    (default ``DEFAULT_STORY_HISTORY_MAX``).
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
        # Archive the prior version before overwriting.
        _archive_existing_story(p, max_entries=_story_history_max())

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
