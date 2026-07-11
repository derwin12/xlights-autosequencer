"""Analysis endpoints — T047.

POST /api/v1/songs/<song_id>/analyze         — start analysis (returns run_id)
GET  /api/v1/songs/<song_id>/analyze/status  — SSE progress stream
GET  /api/v1/songs/<song_id>/analysis        — fetch completed result
"""
from __future__ import annotations

import datetime
import json
import random
import string
import threading
import time
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request, stream_with_context

from . import api_v1
from src.review.storage.library import load_library, save_library
from src.review.storage.assignments import load_session, save_session, save_full_session


# In-memory run registry. Maps song_id → RunState.
_runs: dict[str, "_RunState"] = {}
_runs_lock = threading.Lock()


class _RunState:
    def __init__(self, run_id: str, song_id: str, force: bool = False) -> None:
        self.run_id = run_id
        self.song_id = song_id
        self.started_at = _now_iso()
        self.status = "running"  # "running" | "done" | "failed"
        self.events: list[dict] = []
        self.result: dict | None = None
        self.force = force  # True → do NOT persist to session until commit
        self.committed = False  # True after analyze/commit called
        self.pending_sections: list[dict] | None = None
        self.pending_assignments: list[dict] | None = None
        self.lock = threading.Lock()

    def push(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id() -> str:
    return "run_" + "".join(random.choices(string.ascii_letters + string.digits, k=5))


def _default_overrides() -> dict:
    return {
        "brightness": 1.0,
        "hit_strength": 0.5,
        "dwell_time": 1.0,
        "color_shift": 0.0,
    }


_KIND_TO_THEME: dict[str, str] = {
    "intro": "shimmer-wash",
    "verse": "driving-pulse",
    "chorus": "peak-flash",
    "solo": "solo-chase",
    "bridge": "bridge-burn",
    "outro": "shimmer-wash",
    "unknown": "neutral-glow",
}


def _auto_assign_defaults(song_id: str, sections: list[dict]) -> list[dict]:
    """Build default ThemeAssignment list from sections per FR-012a."""
    assignments = []
    for sec in sections:
        kind = sec.get("kind", "unknown")
        theme_id = _KIND_TO_THEME.get(kind, "neutral-glow")
        assignments.append({
            "section_index": sec["index"],
            "theme_id": theme_id,
            "overrides": _default_overrides(),
            "user_confirmed": False,
        })
    return assignments


def _analyze_stub(state: "_RunState", source_path: str, song_id: str) -> None:
    """Fast stub used in tests (XLIGHT_STUB_ANALYSIS=1) and when no audio file present."""
    import time as _time
    import numpy as np
    import librosa as _librosa

    _t0 = _time.monotonic()
    state.push({"detector": "beats", "library": "librosa", "status": "running", "progress": 0.0})
    state.push({"detector": "sections", "library": "librosa", "status": "queued", "progress": 0.0})
    state.push({"overall": {"status": "running", "progress": 0.1, "eta_ms": 2000, "elapsed_ms": 0}})

    sections: list[dict] = []
    beats_list: list[dict] = []
    bars_list: list[int] = []
    peaks: list[float] = []
    duration_ms = 0

    src = Path(source_path) if source_path else None
    if src and src.exists():
        try:
            y, sr = _librosa.load(str(src), sr=22050, mono=True)
            duration_ms = int(len(y) / sr * 1000)
            tempo_arr, beat_frames = _librosa.beat.beat_track(y=y, sr=sr)
            beat_times = _librosa.frames_to_time(beat_frames, sr=sr)
            for i, t in enumerate(beat_times):
                beats_list.append({"t_ms": int(t * 1000), "bar": i // 4 + 1, "beat": i % 4 + 1})
            bars_list = [b["t_ms"] for b in beats_list if b["beat"] == 1]
            hop = max(1, len(y) // 8000)
            peak_vals = [float(np.max(np.abs(y[j:j + hop]))) for j in range(0, len(y), hop)]
            max_p = max(peak_vals) if peak_vals else 1.0
            peaks = [v / max_p for v in peak_vals[:8000]]
            seg_dur = duration_ms // 4
            kinds = ["intro", "verse", "chorus", "outro"]
            for i in range(4):
                sections.append({"index": i, "start_ms": i * seg_dur,
                                  "end_ms": (i + 1) * seg_dur if i < 3 else duration_ms,
                                  "kind": kinds[i], "label": kinds[i].capitalize()})
        except Exception as exc:
            state.push({"log": {"at_ms": 0, "level": "warn", "message": f"stub analysis failed: {exc}"}})

    if not sections:
        sections = [{"index": 0, "start_ms": 0, "end_ms": max(duration_ms, 1000),
                     "kind": "unknown", "label": "Full Song"}]

    state.push({"detector": "beats", "library": "librosa", "status": "done", "confidence": 0.85})
    state.push({"detector": "sections", "library": "librosa", "status": "done", "confidence": 0.75})
    state.push({"overall": {"status": "running", "progress": 0.9, "eta_ms": 500,
                             "elapsed_ms": int((_time.monotonic() - _t0) * 1000)}})

    detectors = [
        {"name": "beats", "library": "librosa", "status": "done", "confidence": 0.85, "error": None},
        {"name": "sections", "library": "librosa", "status": "done", "confidence": 0.75, "error": None},
    ]
    result: dict[str, Any] = {
        "song_id": song_id, "detected_sections": sections, "alt_boundaries": [],
        "beats": beats_list, "bars": bars_list, "impacts": [], "drops": [],
        "peaks": peaks, "detectors": detectors, "completed_at": _now_iso(),
        "pipeline_version": "stub",
    }

    assignments = _auto_assign_defaults(song_id, sections)
    if not state.force:
        try:
            save_full_session(song_id, {"sections": sections, "detected_sections": sections,
                                         "assignments": assignments, "ghost_boundaries": []})
        except Exception:
            pass
        try:
            lib = load_library()
            for s in lib["songs"]:
                if s["song_id"] == song_id:
                    s["status"] = "analyzed"
                    break
            save_library(lib)
        except Exception:
            pass
    else:
        with state.lock:
            state.pending_sections = sections
            state.pending_assignments = assignments

    with state.lock:
        state.result = result
        state.status = "done"
    state.push({"overall": {"status": "done", "progress": 1.0, "eta_ms": 0,
                             "elapsed_ms": int((_time.monotonic() - _t0) * 1000)}})


def _analyze_in_background(state: "_RunState", source_path: str, song_id: str,
                            audio_bytes: bytes | None) -> None:
    """Run the full hierarchy analysis pipeline in a background thread.

    Calls run_orchestrator() with a progress_callback that streams SSE events,
    then runs build_song_story() for section role classification, and persists
    the result to the session file.

    Set XLIGHT_STUB_ANALYSIS=1 to use the fast stub (used by tests).
    """
    import os
    if os.environ.get("XLIGHT_STUB_ANALYSIS") == "1":
        _analyze_stub(state, source_path, song_id)
        return

    import time as _time
    _t0 = _time.monotonic()

    try:
        src = Path(source_path) if source_path else None
        if not src or not src.exists():
            raise FileNotFoundError(f"Audio file not found: {source_path}")

        # ── Announce pipeline start ──────────────────────────────────────────
        state.push({"overall": {"status": "running", "progress": 0.02,
                                "eta_ms": 90000, "elapsed_ms": 0}})
        state.push({"detector": "capabilities", "library": "system",
                    "status": "running", "progress": 0.0})

        from src.analyzer.capabilities import detect_capabilities
        caps = detect_capabilities()
        cap_label = (f"vamp={'✓' if caps.get('vamp') else '✗'}  "
                     f"madmom={'✓' if caps.get('madmom') else '✗'}  "
                     f"demucs={'✓' if caps.get('demucs') else '✗'}")
        state.push({"detector": "capabilities", "library": "system",
                    "status": "done", "confidence": 1.0,
                    "note": cap_label})
        state.push({"log": {"at_ms": 0, "level": "info", "message": cap_label}})

        # ── Stems (announced separately — can be 1-2 min) ───────────────────
        state.push({"detector": "stems (demucs)", "library": "demucs",
                    "status": "running" if caps.get("demucs") else "skipped",
                    "progress": 0.0})
        state.push({"overall": {"status": "running", "progress": 0.05,
                                "eta_ms": 85000,
                                "elapsed_ms": int((_time.monotonic() - _t0) * 1000)}})

        # ── Build SSE-streaming progress callback ────────────────────────────
        # The orchestrator calls progress_callback(index, total, name, mark_count)
        # after each algorithm finishes.  We map that to detector SSE events.
        _algo_total: list[int] = [1]  # mutable container so closure can write it
        _stems_announced = [False]
        _mark_counts: dict[str, int] = {}  # per-stem display_name → mark_count

        def _progress(index: int, total: int, name: str, mark_count: int) -> None:
            if total != _algo_total[0]:
                _algo_total[0] = total

            # Announce stems done on first algorithm callback
            if not _stems_announced[0]:
                _stems_announced[0] = True
                state.push({"detector": "stems (demucs)", "library": "demucs",
                            "status": "done", "confidence": 1.0})

            # Preserve the full name including :stem suffix so per-stem runs
            # don't overwrite each other. Format in UI as "aubio_onset (drums)".
            base_name, _, stem_suffix = name.partition(":")
            display_name = f"{base_name} ({stem_suffix})" if stem_suffix else base_name

            # Map algorithm name → library label
            lib = "librosa"
            if any(x in base_name for x in ("qm_", "segmentino", "chordino", "beatroot", "aubio", "bbc_")):
                lib = "vamp"
            elif "madmom" in base_name:
                lib = "madmom"

            _mark_counts[display_name] = mark_count

            elapsed_ms = int((_time.monotonic() - _t0) * 1000)
            # Reserve first 10% for setup, last 5% for story; algorithms fill 10-90%
            frac = 0.10 + 0.80 * (index / max(total, 1))

            state.push({"detector": display_name, "library": lib,
                        "status": "done", "confidence": None,
                        "marks": mark_count})
            state.push({"overall": {"status": "running",
                                    "progress": round(frac, 3),
                                    "eta_ms": max(0, int((1.0 - frac) / max(frac, 0.01) * elapsed_ms)),
                                    "elapsed_ms": elapsed_ms}})

        # ── Run full orchestrator ────────────────────────────────────────────
        from src.analyzer.orchestrator import run_orchestrator
        hierarchy = run_orchestrator(
            audio_path=str(src),
            fresh=state.force,
            progress_callback=_progress,
        )

        elapsed_ms = int((_time.monotonic() - _t0) * 1000)
        state.push({"overall": {"status": "running", "progress": 0.90,
                                "eta_ms": 5000, "elapsed_ms": elapsed_ms}})

        # ── Story builder — section roles ────────────────────────────────────
        state.push({"detector": "song story (roles)", "library": "story",
                    "status": "running", "progress": 0.0})
        try:
            from src.story.builder import build_song_story
            story = build_song_story(hierarchy.to_dict(), str(src))
            story_sections = story.get("sections", [])
            # Surface Step-15c capability skips (one entry per skipped fix
            # per song) on HierarchyResult.warnings so the analyze-step API
            # payload's existing ``warnings`` field carries them to the UI's
            # warnings panel. Per-section non-fires do NOT produce warnings
            # — those are silent.
            hierarchy.warnings.extend(story.get("refinement_warnings") or [])
            state.push({"detector": "song story (roles)", "library": "story",
                        "status": "done", "confidence": 1.0,
                        "marks": len(story_sections)})
        except Exception as exc:
            state.push({"detector": "song story (roles)", "library": "story",
                        "status": "failed", "error": str(exc)})
            state.push({"log": {"at_ms": elapsed_ms, "level": "warn",
                                "message": f"Story builder failed: {exc}"}})
            story = None
            story_sections = []

        # ── Build sections list for the UI ───────────────────────────────────
        # Prefer story sections (have role labels); fall back to hierarchy sections
        sections: list[dict] = []
        if story_sections:
            for i, sec in enumerate(story_sections):
                # Story builder uses float seconds (start/end); fall back to _ms if present
                start_ms = int(sec["start"] * 1000) if "start" in sec else sec.get("start_ms", 0)
                end_ms = int(sec["end"] * 1000) if "end" in sec else sec.get("end_ms", 0)
                # `agreement_score` was added in PR #84 and counts independent
                # source corroborations of the section's start boundary
                # (segmentino, QM, energy events, key changes, stem entries,
                # …). Legacy stories written before PR #84 lack the field;
                # default to 0 per the spec contract
                # ("Legacy story without agreement_score defaults to 0").
                # `low_confidence` is the boolean the UI renders against; the
                # raw integer is kept for tooltips and inspector display.
                # Threshold ≤ 0 — 0 means "no other source corroborates this
                # boundary". Original design proposed ≤ 1 but corpus
                # measurement on 16 songs / 145 sections showed that flagged
                # 38% of all sections, drowning the signal. Distribution:
                #   0: 11.0%   1: 26.9%   2: 28.3%   3: 24.1%   4: 9.0%   5: 0.7%
                # Flagging only score=0 (the 11% of genuinely uncorroborated
                # boundaries) keeps the indicator meaningful. See
                # https://github.com/bobbyfriday/xlight-autosequencer/pull/108#issuecomment-4320505368
                agreement_score = int(sec.get("agreement_score", 0))
                low_confidence = agreement_score <= 0
                # `boundary_refinements` is the per-section list of
                # human-readable notes describing any lyric-anchored
                # refinements applied during the story builder's Step 15c.
                # Legacy stories written before schema 1.1.0 lack the field;
                # default to [] per OpenSpec change
                # ``lyric-anchored-boundary-refinement``.
                refinements = list(sec.get("boundary_refinements") or [])
                section_payload = {
                    "index": i,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "kind": sec.get("role", "unknown"),
                    "label": sec.get("role", "unknown").replace("_", " ").title(),
                    "agreement_score": agreement_score,
                    "low_confidence": low_confidence,
                    "boundary_refinements": refinements,
                    "low_refined": len(refinements) > 0,
                }
                # `chorus_ssm_supported` is set on Chorus sections by the SSM
                # validator (when SSM produced groups). Per spec, an absent
                # field defaults to True downstream — we copy through so the
                # frontend can decide its own treatment.
                if "chorus_ssm_supported" in sec:
                    section_payload["chorus_ssm_supported"] = bool(
                        sec["chorus_ssm_supported"]
                    )
                sections.append(section_payload)
        else:
            # Fall back to raw hierarchy section marks. No story builder ran,
            # so there are no agreement scores; default the new fields the
            # same way legacy stories do (score 0, low_confidence true). The
            # frontend's section-list rendering reads `low_confidence` and
            # this keeps the display consistent across both paths.
            for i, mark in enumerate(hierarchy.sections):
                sections.append({
                    "index": i,
                    "start_ms": mark.time_ms,
                    "end_ms": (hierarchy.sections[i + 1].time_ms
                               if i + 1 < len(hierarchy.sections)
                               else hierarchy.duration_ms),
                    "kind": mark.label or "unknown",
                    "label": (mark.label or "unknown").replace("_", " ").title(),
                    "agreement_score": 0,
                    "low_confidence": True,
                    "boundary_refinements": [],
                    "low_refined": False,
                })

        if not sections:
            sections = [{"index": 0, "start_ms": 0, "end_ms": hierarchy.duration_ms,
                         "kind": "unknown", "label": "Full Song",
                         "agreement_score": 0, "low_confidence": True}]

        # ── Build beats list ─────────────────────────────────────────────────
        beats_list: list[dict] = []
        if hierarchy.beats:
            for i, mark in enumerate(hierarchy.beats.marks):
                beats_list.append({
                    "t_ms": mark.time_ms,
                    "bar": i // 4 + 1,
                    "beat": int(mark.label) if mark.label and mark.label.isdigit() else (i % 4 + 1),
                })

        bars_list = [m.time_ms for m in (hierarchy.bars.marks if hierarchy.bars else [])]

        # ── Waveform peaks from audio (8000 points for detail) ──────────────
        _PEAK_COUNT = 8000
        peaks: list[float] = []
        try:
            import numpy as np
            import librosa as _librosa
            y, sr = _librosa.load(str(src), sr=22050, mono=True)
            hop = max(1, len(y) // _PEAK_COUNT)
            peak_vals = [float(np.max(np.abs(y[j:j + hop]))) for j in range(0, len(y), hop)]
            max_p = max(peak_vals) if peak_vals else 1.0
            peaks = [v / max_p for v in peak_vals[:_PEAK_COUNT]]
        except Exception:
            # Fallback to energy curve if librosa fails
            energy_curve = hierarchy.energy_curves.get("full_mix")
            if energy_curve and energy_curve.values:
                vals = energy_curve.values
                step = max(1, len(vals) // _PEAK_COUNT)
                sampled = vals[::step][:_PEAK_COUNT]
                max_v = max(sampled) if sampled else 1.0
                peaks = [v / max_v for v in sampled]

        # ── Impacts + drops from L0 ──────────────────────────────────────────
        impacts_list = [{"t_ms": m.time_ms, "label": m.label or "impact"}
                        for m in hierarchy.energy_impacts]
        drops_list = [{"t_ms": m.time_ms, "label": m.label or "drop"}
                      for m in hierarchy.energy_drops]

        # ── Per-stem onset events (real detected timestamps) ─────────────────
        onsets_dict: dict[str, list[int]] = {
            stem: [m.time_ms for m in track.marks]
            for stem, track in hierarchy.events.items()
        }

        # ── Sub-beat grids (half-bars and eighth notes) ──────────────────────
        half_bars_list = [m.time_ms for m in (hierarchy.half_bars.marks if hierarchy.half_bars else [])]
        eighth_notes_list = [m.time_ms for m in (hierarchy.eighth_notes.marks if hierarchy.eighth_notes else [])]

        # Fill tail gap when beat tracker truncates before song end
        beats_list, bars_list, half_bars_list, eighth_notes_list = _extrapolate_grid(
            beats_list, bars_list, half_bars_list, eighth_notes_list,
            duration_ms=hierarchy.duration_ms,
            estimated_bpm=hierarchy.estimated_bpm,
        )

        # ── Section boundary timestamps (raw detector output, not classified) ─
        section_boundaries_list = [m.time_ms for m in hierarchy.sections]

        # ── Chord change + key change timestamps ─────────────────────────────
        chord_changes_list = [m.time_ms for m in (hierarchy.chords.marks if hierarchy.chords else [])]
        key_changes_list = [m.time_ms for m in (hierarchy.key_changes.marks if hierarchy.key_changes else [])]

        # ── Synced lyric lines (display track, not a boundary-detection signal) ─
        lyrics_list = list((story or {}).get("lyrics") or [])

        # ── Value curves (BBC energy per stem + spectral flux) ───────────────
        # Downsample to ≤2000 points each to keep the response size manageable.
        # Adjust fps proportionally so (len(values) / fps) still equals the
        # original curve's duration — otherwise the frontend would place the
        # curve over the wrong time range.
        def _downsample(vc, target: int = 2000) -> dict:
            if len(vc.values) <= target:
                return {"fps": vc.fps, "values": vc.values}
            step = len(vc.values) / target
            new_values = [vc.values[min(len(vc.values) - 1, int(i * step))]
                           for i in range(target)]
            new_fps = vc.fps * target / len(vc.values)
            return {"fps": new_fps, "values": new_values}

        curves_out: dict[str, dict] = {}
        for stem, vc in hierarchy.energy_curves.items():
            key = f"bbc_energy ({stem})" if stem != "full_mix" else "bbc_energy"
            curves_out[key] = _downsample(vc)
        if hierarchy.spectral_flux is not None:
            curves_out["bbc_spectral_flux"] = _downsample(hierarchy.spectral_flux)

        # ── Detectors summary list ───────────────────────────────────────────
        # bbc_energy / bbc_spectral_flux produce value curves rather than
        # discrete timing marks. They're tagged kind="curve" so the UI can
        # render them as a line chart instead of tick marks.
        _CURVE_DETECTORS = {"bbc_energy", "bbc_spectral_flux"}

        detectors: list[dict] = []
        for algo_name in hierarchy.algorithms_run:
            base_name, _, stem_suffix = algo_name.partition(":")
            display = f"{base_name} ({stem_suffix})" if stem_suffix else base_name
            lib = "librosa"
            if any(x in base_name for x in ("qm_", "segmentino", "chordino", "beatroot", "aubio", "bbc_")):
                lib = "vamp"
            elif "madmom" in base_name:
                lib = "madmom"
            elif "story" in base_name:
                lib = "story"
            kind = "curve" if base_name in _CURVE_DETECTORS else "marks"
            detectors.append({"name": display, "library": lib,
                               "status": "done", "confidence": None,
                               "marks": _mark_counts.get(display),
                               "kind": kind,
                               "error": None})

        # Add story detector
        detectors.append({"name": "song_story", "library": "story",
                           "status": "done" if story else "failed",
                           "confidence": None,
                           "marks": len(story_sections) if story else None,
                           "error": None})

        # Add lyrics detector (kind="lyrics" so the frontend renders labeled
        # blocks rather than tick marks; empty is a normal "no match" outcome,
        # not a failure — syncedlyrics frequently has no result for a song).
        detectors.append({"name": "lyrics", "library": "story",
                           "status": "done" if story else "failed",
                           "confidence": None,
                           "marks": len(lyrics_list),
                           "kind": "lyrics",
                           "error": None})

        pipeline_version = f"full-{hierarchy.schema_version}"

        story_global = (story or {}).get("global", {})

        result: dict[str, Any] = {
            "song_id": song_id,
            "detected_sections": sections,
            "alt_boundaries": [],
            "beats": beats_list,
            "bars": bars_list,
            "half_bars": half_bars_list,
            "eighth_notes": eighth_notes_list,
            "impacts": impacts_list,
            "drops": drops_list,
            "onsets": onsets_dict,
            "section_boundaries": section_boundaries_list,
            "chord_changes": chord_changes_list,
            "key_changes": key_changes_list,
            "lyrics": lyrics_list,
            "value_curves": curves_out,
            "peaks": peaks,
            "detectors": detectors,
            "completed_at": _now_iso(),
            "pipeline_version": pipeline_version,
            "estimated_bpm": hierarchy.estimated_bpm,
            "capabilities": hierarchy.capabilities,
            "warnings": hierarchy.warnings,
            "section_source": story_global.get("section_source"),
        }

        # ── Persist to session (unless force=True — wait for commit) ─────────
        assignments = _auto_assign_defaults(song_id, sections)
        if not state.force:
            try:
                save_full_session(song_id, {
                    "sections": sections,
                    "detected_sections": sections,
                    "assignments": assignments,
                    "ghost_boundaries": [],
                    "lyrics": lyrics_list,
                })
            except Exception:
                pass
            try:
                lib = load_library()
                for s in lib["songs"]:
                    if s["song_id"] == song_id:
                        s["status"] = "analyzed"
                        break
                save_library(lib)
            except Exception:
                pass
        else:
            with state.lock:
                state.pending_sections = sections
                state.pending_assignments = assignments

        with state.lock:
            state.result = result
            state.status = "done"

        total_elapsed_ms = int((_time.monotonic() - _t0) * 1000)
        state.push({"overall": {"status": "done", "progress": 1.0,
                                "eta_ms": 0, "elapsed_ms": total_elapsed_ms}})

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        with state.lock:
            state.status = "failed"
        state.push({"overall": {"status": "failed", "progress": 0.0,
                                "eta_ms": 0, "elapsed_ms": 0,
                                "error": str(exc)}})
        state.push({"log": {"at_ms": 0, "level": "error",
                            "message": f"{exc}\n{tb[:500]}}}"}})


@api_v1.route("/songs/<song_id>/analyze", methods=["POST"])
def start_analyze(song_id: str):
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    source_paths = song.get("source_paths") or []
    source_path = source_paths[0] if source_paths else ""
    if not source_path:
        return jsonify({"error": {"code": "source_file_missing",
                                   "message": "No audio file — please re-import the song"}}), 409
    if not Path(source_path).exists():
        return jsonify({"error": {"code": "source_file_missing",
                                   "message": "Audio source not found on disk"}}), 409

    body = request.get_json(silent=True) or {}
    force = bool(body.get("force", False))

    with _runs_lock:
        existing = _runs.get(song_id)
        if existing and existing.status == "running":
            return jsonify({"run_id": existing.run_id,
                            "started_at": existing.started_at}), 202
        # Start new run
        state = _RunState(_run_id(), song_id, force=force)
        _runs[song_id] = state

    # Audio bytes not needed since we use the file path directly.
    t = threading.Thread(
        target=_analyze_in_background,
        args=(state, source_path, song_id, None),
        daemon=True,
    )
    t.start()

    return jsonify({"run_id": state.run_id, "started_at": state.started_at}), 202


@api_v1.route("/songs/<song_id>/analyze/commit", methods=["POST"])
def commit_analyze(song_id: str):
    """Apply a pending force re-analysis result after user confirms the mapping (FR-013a)."""
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    body = request.get_json(silent=True) or {}
    run_id = body.get("run_id")
    if not run_id:
        return jsonify({"error": {"code": "missing_field",
                                   "message": "run_id is required"}}), 400

    assignment_mapping = body.get("assignment_mapping", [])

    # Find the run
    with _runs_lock:
        state = _runs.get(song_id)

    if state is None or state.run_id != run_id:
        # Also search for any run with this run_id (could have been replaced)
        matching = None
        with _runs_lock:
            for sid, s in _runs.items():
                if s.run_id == run_id and sid == song_id:
                    matching = s
                    break
        state = matching

    if state is None:
        return jsonify({"error": {"code": "run_not_found",
                                   "message": "No run found with this run_id"}}), 404

    if state.committed:
        return jsonify({"error": {"code": "already_committed",
                                   "message": "This run has already been committed"}}), 409

    with state.lock:
        pending_sections = state.pending_sections
        pending_assignments = state.pending_assignments
        result = state.result

    if pending_sections is None and result is not None:
        # Non-force run — use detected_sections from result
        pending_sections = result.get("detected_sections", [])
        pending_assignments = _auto_assign_defaults(song_id, pending_sections)

    if pending_sections is None:
        return jsonify({"error": {"code": "run_not_found",
                                   "message": "Run result not yet available"}}), 404

    # Apply assignment_mapping: carry over themes from old assignments where specified
    session = load_session(song_id)
    old_assignments = session.get("assignments", []) if session else []
    # Carry the lyrics track through re-persistence — it's produced once by
    # the story builder and isn't recomputed on this commit path.
    lyrics_list = (result.get("lyrics") if result else None) or \
        (session.get("lyrics") if session else None) or []

    final_assignments = list(pending_assignments)  # start from suggested defaults
    for entry in assignment_mapping:
        new_idx = entry.get("new_section_index")
        old_idx = entry.get("inherited_from_old_index")
        action = entry.get("action", "")
        if new_idx is None or new_idx >= len(final_assignments):
            continue
        if action in ("kept", "shifted") and old_idx is not None and old_idx < len(old_assignments):
            old_a = old_assignments[old_idx]
            final_assignments[new_idx] = {
                "section_index": new_idx,
                "theme_id": old_a.get("theme_id"),
                "overrides": old_a.get("overrides", _default_overrides()),
                "user_confirmed": False,
            }

    # Persist
    try:
        save_full_session(song_id, {
            "sections": pending_sections,
            "detected_sections": pending_sections,
            "assignments": final_assignments,
            "ghost_boundaries": [],
            "lyrics": lyrics_list,
        })
    except Exception as exc:
        return jsonify({"error": {"code": "internal_error", "message": str(exc)}}), 500

    # Update song status
    try:
        lib2 = load_library()
        for s in lib2["songs"]:
            if s["song_id"] == song_id:
                s["status"] = "analyzed"
                break
        from src.review.storage.library import save_library
        save_library(lib2)
    except Exception:
        pass

    with state.lock:
        state.committed = True

    return jsonify({
        "sections": pending_sections,
        "assignments": final_assignments,
    }), 200


@api_v1.route("/songs/<song_id>/analyze/status", methods=["GET"])
def analyze_status(song_id: str):
    with _runs_lock:
        state = _runs.get(song_id)

    if state is None:
        return jsonify({"error": {"code": "run_not_found",
                                   "message": "No run found for song"}}), 404

    def _gen():
        idx = 0
        while True:
            with state.lock:
                n = len(state.events)
                status = state.status

            while idx < n:
                yield f"data: {json.dumps(state.events[idx])}\n\n"
                idx += 1

            if status != "running":
                return
            time.sleep(0.05)

    return Response(
        stream_with_context(_gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_v1.route("/songs/<song_id>/analysis", methods=["GET"])
def get_analysis(song_id: str):
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    if song.get("status") == "draft":
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "Song has not been analyzed yet"}}), 409

    with _runs_lock:
        state = _runs.get(song_id)

    if state is not None and state.result is not None:
        return jsonify(state.result), 200

    # State lost (e.g. server restart) — rebuild response from cached hierarchy JSON
    source_paths: list[str] = song.get("source_paths", [])
    src = next((Path(p) for p in source_paths if Path(p).exists()), None)
    if src is not None:
        hierarchy_path = src.parent / src.stem / f"{src.stem}_hierarchy.json"
        if hierarchy_path.exists():
            try:
                rebuilt = _rebuild_analysis_from_cache(song_id, src, hierarchy_path)
                if rebuilt is not None:
                    return jsonify(rebuilt), 200
            except Exception:
                pass

    # Last-resort fallback: empty shell from session
    session = load_session(song_id)
    if session and "sections" in session:
        return jsonify({
            "song_id": song_id,
            "detected_sections": session["sections"],
            "alt_boundaries": [], "beats": [], "bars": [], "impacts": [],
            "drops": [], "peaks": [], "detectors": [],
            "completed_at": _now_iso(), "pipeline_version": "stub",
        }), 200
    return jsonify({"error": {"code": "not_analyzed",
                               "message": "Analysis result not available"}}), 409


def _extrapolate_grid(beats_list: list[dict], bars_list: list[int],
                       half_bars_list: list[int], eighth_notes_list: list[int],
                       duration_ms: int, estimated_bpm: float,
                       ) -> tuple[list[dict], list[int], list[int], list[int]]:
    """Extend beats/bars forward at constant BPM to cover the full song duration.

    Some beat trackers (notably librosa.beat_track) truncate output before the
    true song end. We fill the trailing gap using the stable interval from the
    detected beats so the UI shows a continuous grid.

    Extrapolated beats are tagged with `extrapolated: True` so the UI can
    render them with reduced opacity.
    """
    if not beats_list or estimated_bpm <= 0 or duration_ms <= 0:
        return beats_list, bars_list, half_bars_list, eighth_notes_list

    # Use detected median beat interval when available, else compute from BPM
    if len(beats_list) >= 2:
        deltas = [beats_list[i + 1]["t_ms"] - beats_list[i]["t_ms"]
                  for i in range(len(beats_list) - 1)]
        deltas.sort()
        beat_interval_ms = deltas[len(deltas) // 2]
    else:
        beat_interval_ms = int(60_000 / estimated_bpm)

    if beat_interval_ms <= 0:
        return beats_list, bars_list, half_bars_list, eighth_notes_list

    last_beat = beats_list[-1]
    gap_ms = duration_ms - last_beat["t_ms"]
    # Only extrapolate if the gap is more than one bar (4 beats)
    if gap_ms < 4 * beat_interval_ms:
        return beats_list, bars_list, half_bars_list, eighth_notes_list

    next_t = last_beat["t_ms"] + beat_interval_ms
    next_bar = last_beat["bar"]
    next_beat_num = last_beat["beat"] + 1
    if next_beat_num > 4:
        next_beat_num = 1
        next_bar += 1

    new_beats: list[dict] = []
    while next_t <= duration_ms:
        new_beats.append({
            "t_ms": next_t,
            "bar": next_bar,
            "beat": next_beat_num,
            "extrapolated": True,
        })
        if next_beat_num == 1:
            bars_list.append(next_t)
        if next_beat_num in (1, 3):
            half_bars_list.append(next_t)
        eighth_notes_list.append(next_t)
        eighth_notes_list.append(next_t + beat_interval_ms // 2)
        next_t += beat_interval_ms
        next_beat_num += 1
        if next_beat_num > 4:
            next_beat_num = 1
            next_bar += 1

    beats_list = beats_list + new_beats
    bars_list.sort()
    half_bars_list.sort()
    eighth_notes_list = sorted(e for e in eighth_notes_list if e <= duration_ms)
    return beats_list, bars_list, half_bars_list, eighth_notes_list


def _rebuild_analysis_from_cache(song_id: str, src: Path,
                                  hierarchy_path: Path) -> dict | None:
    """Rebuild the analysis response from a cached hierarchy JSON on disk.

    Invoked when in-memory `state.result` is absent (e.g. after server restart).
    Mirrors the response shape produced by `_analyze_in_background`.
    """
    from src.analyzer.result import HierarchyResult
    import json as _json

    data = _json.loads(hierarchy_path.read_text())
    hierarchy = HierarchyResult.from_dict(data)

    # Beats / bars / half-bars / eighth notes
    beats_list: list[dict] = []
    if hierarchy.beats:
        for i, mark in enumerate(hierarchy.beats.marks):
            beats_list.append({
                "t_ms": mark.time_ms,
                "bar": i // 4 + 1,
                "beat": int(mark.label) if mark.label and mark.label.isdigit() else (i % 4 + 1),
            })
    bars_list = [m.time_ms for m in (hierarchy.bars.marks if hierarchy.bars else [])]
    half_bars_list = [m.time_ms for m in (hierarchy.half_bars.marks if hierarchy.half_bars else [])]
    eighth_notes_list = [m.time_ms for m in (hierarchy.eighth_notes.marks if hierarchy.eighth_notes else [])]

    # Extrapolate beats / bars forward at stable BPM when the detector output
    # stops more than 1 bar before the song end. Librosa beat_track sometimes
    # truncates the tail even when drums are present. We mark extrapolated
    # points with `extrapolated: True` so the UI can render them differently.
    beats_list, bars_list, half_bars_list, eighth_notes_list = _extrapolate_grid(
        beats_list, bars_list, half_bars_list, eighth_notes_list,
        duration_ms=hierarchy.duration_ms,
        estimated_bpm=hierarchy.estimated_bpm,
    )

    # Peaks — compute from audio file
    _PEAK_COUNT = 8000
    peaks: list[float] = []
    try:
        import numpy as np
        import librosa as _librosa
        y, _sr = _librosa.load(str(src), sr=22050, mono=True)
        hop = max(1, len(y) // _PEAK_COUNT)
        peak_vals = [float(np.max(np.abs(y[j:j + hop]))) for j in range(0, len(y), hop)]
        max_p = max(peak_vals) if peak_vals else 1.0
        peaks = [v / max_p for v in peak_vals[:_PEAK_COUNT]]
    except Exception:
        pass

    # L0 impacts/drops
    impacts_list = [{"t_ms": m.time_ms, "label": m.label or "impact"}
                    for m in hierarchy.energy_impacts]
    drops_list = [{"t_ms": m.time_ms, "label": m.label or "drop"}
                  for m in hierarchy.energy_drops]

    # Per-stem onsets + section/chord/key timestamps
    onsets_dict = {stem: [m.time_ms for m in track.marks]
                   for stem, track in hierarchy.events.items()}
    section_boundaries_list = [m.time_ms for m in hierarchy.sections]
    chord_changes_list = [m.time_ms for m in (hierarchy.chords.marks if hierarchy.chords else [])]
    key_changes_list = [m.time_ms for m in (hierarchy.key_changes.marks if hierarchy.key_changes else [])]

    # Value curves — downsample and scale fps so duration is preserved
    def _downsample(vc, target: int = 2000) -> dict:
        if len(vc.values) <= target:
            return {"fps": vc.fps, "values": vc.values}
        step = len(vc.values) / target
        new_values = [vc.values[min(len(vc.values) - 1, int(i * step))]
                       for i in range(target)]
        new_fps = vc.fps * target / len(vc.values)
        return {"fps": new_fps, "values": new_values}

    curves_out: dict[str, dict] = {}
    for stem, vc in hierarchy.energy_curves.items():
        key = f"bbc_energy ({stem})" if stem != "full_mix" else "bbc_energy"
        curves_out[key] = _downsample(vc)
    if hierarchy.spectral_flux is not None:
        curves_out["bbc_spectral_flux"] = _downsample(hierarchy.spectral_flux)

    # Per-stem mark counts — enumerate from the raw hierarchy event tracks
    # (the progress callback's _mark_counts isn't available from cached data)
    mark_counts_by_display: dict[str, int] = {}
    for stem, track in hierarchy.events.items():
        # aubio_onset is the primary onset algo; name it per stem
        mark_counts_by_display[f"aubio_onset ({stem})"] = len(track.marks)

    # Detectors list
    _CURVE_DETECTORS = {"bbc_energy", "bbc_spectral_flux"}
    detectors: list[dict] = []
    for algo_name in hierarchy.algorithms_run:
        base_name, _, stem_suffix = algo_name.partition(":")
        display = f"{base_name} ({stem_suffix})" if stem_suffix else base_name
        lib_tag = "librosa"
        if any(x in base_name for x in ("qm_", "segmentino", "chordino", "beatroot", "aubio", "bbc_")):
            lib_tag = "vamp"
        elif "madmom" in base_name:
            lib_tag = "madmom"
        elif "story" in base_name:
            lib_tag = "story"
        kind = "curve" if base_name in _CURVE_DETECTORS else "marks"
        # Mark counts: from event tracks for onset-type detectors, else from
        # hierarchy.beats/bars/etc. where applicable
        marks = mark_counts_by_display.get(display)
        if marks is None:
            if "beat" in base_name and hierarchy.beats:
                marks = len(hierarchy.beats.marks)
            elif "bar" in base_name and hierarchy.bars:
                marks = len(hierarchy.bars.marks)
        detectors.append({"name": display, "library": lib_tag,
                           "status": "done", "confidence": None,
                           "marks": marks, "kind": kind, "error": None})

    detectors.append({"name": "lyrics", "library": "story", "status": "done",
                       "confidence": None, "marks": len(lyrics_list),
                       "kind": "lyrics", "error": None})

    # Sections — load from session if available, else derive from hierarchy.
    # Both paths need to expose `agreement_score` + `low_confidence` so the
    # Analyze screen renders the same low-confidence indicator regardless of
    # whether sections came from a fresh story builder run, a persisted
    # session, or a hierarchy fallback.
    session = load_session(song_id)
    lyrics_list = list((session or {}).get("lyrics") or [])
    if session and "sections" in session:
        sections = []
        for sec in session["sections"]:
            # Persisted sessions written before this change lack
            # agreement_score; default to 0 / low_confidence=True per spec.
            agreement_score = int(sec.get("agreement_score", 0))
            payload = dict(sec)
            payload["agreement_score"] = agreement_score
            payload["low_confidence"] = bool(
                sec.get("low_confidence", agreement_score <= 1)
            )
            # Default boundary_refinements to [] for legacy sessions that
            # predate schema 1.1.0.
            refinements = list(sec.get("boundary_refinements") or [])
            payload["boundary_refinements"] = refinements
            payload["low_refined"] = len(refinements) > 0
            sections.append(payload)
    else:
        sections = []
        for i, mark in enumerate(hierarchy.sections):
            sections.append({
                "index": i,
                "start_ms": mark.time_ms,
                "end_ms": (hierarchy.sections[i + 1].time_ms
                           if i + 1 < len(hierarchy.sections)
                           else hierarchy.duration_ms),
                "kind": mark.label or "unknown",
                "label": (mark.label or "unknown").replace("_", " ").title(),
                # Hierarchy-only fallback: no story builder, no agreement
                # score. Default mirrors the legacy-story default.
                "agreement_score": 0,
                "low_confidence": True,
                "boundary_refinements": [],
                "low_refined": False,
            })
        if not sections:
            sections = [{"index": 0, "start_ms": 0, "end_ms": hierarchy.duration_ms,
                         "kind": "unknown", "label": "Full Song",
                         "agreement_score": 0, "low_confidence": True,
                         "boundary_refinements": [], "low_refined": False}]

    return {
        "song_id": song_id,
        "detected_sections": sections,
        "alt_boundaries": [],
        "beats": beats_list,
        "bars": bars_list,
        "half_bars": half_bars_list,
        "eighth_notes": eighth_notes_list,
        "impacts": impacts_list,
        "drops": drops_list,
        "onsets": onsets_dict,
        "section_boundaries": section_boundaries_list,
        "chord_changes": chord_changes_list,
        "key_changes": key_changes_list,
        "lyrics": lyrics_list,
        "value_curves": curves_out,
        "peaks": peaks,
        "detectors": detectors,
        "completed_at": _now_iso(),
        "pipeline_version": f"cached-{hierarchy.schema_version}",
        "estimated_bpm": hierarchy.estimated_bpm,
        "capabilities": hierarchy.capabilities,
        "warnings": hierarchy.warnings,
    }


@api_v1.route("/songs/<song_id>/stem-peaks", methods=["GET"])
def get_stem_peaks(song_id: str):
    """
    Return waveform peaks for each available stem of a song.
    Response: { "stems": { "drums": [0.0..1.0, ...], "bass": [...], ... } }
    Each stem array has up to 8000 samples normalized 0.0-1.0.
    Returns 404 if song not found, 200 with empty stems dict if no stems cached.
    """
    import numpy as np

    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": "song not found"}), 404

    source_paths: list[str] = song.get("source_paths", [])
    src = next((Path(p) for p in source_paths if Path(p).exists()), None)
    if src is None:
        return jsonify({"stems": {}}), 200

    # Stems are cached in one of two locations (StemCache convention):
    #   1. <parent>/stems/                                       (legacy/primary)
    #   2. <parent>/<filename_without_ext>/stems/                (preferred)
    candidates = [
        src.parent / "stems",
        src.parent / src.stem / "stems",
    ]
    stems_dir = next((d for d in candidates if d.exists()), None)
    if stems_dir is None:
        return jsonify({"stems": {}}), 200

    _STEM_PEAK_COUNT = 8000
    stem_names = ["drums", "bass", "vocals", "guitar", "piano", "other"]
    result_stems: dict[str, list[float]] = {}

    try:
        import librosa as _librosa
        for name in stem_names:
            # Try .mp3 first (what StemCache writes), then .wav
            for ext in (".mp3", ".wav"):
                stem_path = stems_dir / f"{name}{ext}"
                if stem_path.exists():
                    try:
                        y, _ = _librosa.load(str(stem_path), sr=22050, mono=True)
                        hop = max(1, len(y) // _STEM_PEAK_COUNT)
                        peak_vals = [float(np.max(np.abs(y[j:j + hop]))) for j in range(0, len(y), hop)]
                        max_p = max(peak_vals) if peak_vals else 1.0
                        if max_p > 0:
                            result_stems[name] = [v / max_p for v in peak_vals[:_STEM_PEAK_COUNT]]
                    except Exception:
                        pass
                    break
    except ImportError:
        pass

    return jsonify({"stems": result_stems}), 200


@api_v1.route("/songs/<song_id>/peaks", methods=["GET"])
def get_peaks_window(song_id: str):
    """
    Compute waveform peaks for a specific time window at render resolution.

    Query params:
        start_ms (int, default 0) — window start time
        end_ms   (int, required)  — window end time
        count    (int, default 2000, max 8000) — number of peak samples to return
        stem     (str, optional)  — stem name (drums/bass/vocals/...); full mix if omitted

    Returns { "peaks": [0.0..1.0, ...], "start_ms": N, "end_ms": N }.

    Unlike /analysis which returns full-song peaks at fixed resolution, this
    endpoint loads only the requested window and computes peaks at the caller's
    desired resolution — so zooming in yields proportionally more detail.
    """
    import numpy as np

    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": "song not found"}), 404

    try:
        start_ms = int(request.args.get("start_ms", 0))
        end_ms = int(request.args.get("end_ms", 0))
        count = min(max(int(request.args.get("count", 2000)), 100), 8000)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid params"}), 400

    if end_ms <= start_ms:
        return jsonify({"error": "end_ms must be > start_ms"}), 400

    stem = request.args.get("stem")
    source_paths: list[str] = song.get("source_paths", [])
    src = next((Path(p) for p in source_paths if Path(p).exists()), None)
    if src is None:
        return jsonify({"peaks": [], "start_ms": start_ms, "end_ms": end_ms}), 200

    # Resolve audio file — stem if requested and cached, else source audio
    audio_file: Path | None = src
    if stem:
        candidates = [src.parent / "stems", src.parent / src.stem / "stems"]
        stem_file: Path | None = None
        for stems_dir in candidates:
            if not stems_dir.exists():
                continue
            for ext in (".mp3", ".wav"):
                p = stems_dir / f"{stem}{ext}"
                if p.exists():
                    stem_file = p
                    break
            if stem_file is not None:
                break
        if stem_file is None:
            return jsonify({"peaks": [], "start_ms": start_ms, "end_ms": end_ms}), 200
        audio_file = stem_file

    try:
        import librosa as _librosa
        duration_s = (end_ms - start_ms) / 1000.0
        offset_s = start_ms / 1000.0
        y, _sr = _librosa.load(str(audio_file), sr=22050, mono=True,
                               offset=offset_s, duration=duration_s)
        if len(y) == 0:
            return jsonify({"peaks": [], "start_ms": start_ms, "end_ms": end_ms}), 200
        hop = max(1, len(y) // count)
        peak_vals = [float(np.max(np.abs(y[j:j + hop]))) for j in range(0, len(y), hop)]
        max_p = max(peak_vals) if peak_vals else 1.0
        peaks = [v / max_p for v in peak_vals[:count]] if max_p > 0 else peak_vals[:count]
    except Exception as exc:  # noqa: BLE001 — endpoint-level guard, we want to surface the error
        return jsonify({"error": f"peaks computation failed: {exc}"}), 500

    return jsonify({"peaks": peaks, "start_ms": start_ms, "end_ms": end_ms}), 200
