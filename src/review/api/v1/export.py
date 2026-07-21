"""Export endpoints — T055.

POST /api/v1/songs/<song_id>/export                  — start export
GET  /api/v1/songs/<song_id>/export/status           — SSE progress
GET  /api/v1/songs/<song_id>/export/download-package — zip: .xsq + committed layout files
GET  /api/v1/songs/<song_id>/export/mapping          — prop-theme mapping table
"""
from __future__ import annotations

import datetime
import json
import random
import string
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request, send_file, stream_with_context

from . import api_v1
from .layout import get_committed_layout
from src.paths import get_committed_networks_xml_path
from src.review.storage.library import load_library
from src.review.storage.assignments import load_session


_exports: dict[str, "_ExportState"] = {}
_exports_lock = threading.Lock()
# Also track latest export per song_id
_song_exports: dict[str, str] = {}  # song_id → export_id


class _ExportState:
    def __init__(self, export_id: str) -> None:
        self.export_id = export_id
        self.started_at = _now_iso()
        self.status = "running"
        self.events: list[dict] = []
        self.output_path: str | None = None
        self.lock = threading.Lock()

    def push(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _export_id() -> str:
    return "exp_" + "".join(random.choices(string.ascii_letters + string.digits, k=5))


def _run_export(state: "_ExportState", song: dict, session: dict,
                layout: dict, destination_name: str, fmt: str,
                genre: str = "pop", occasion: str = "general",
                include_extra_timing: bool = True,
                vocal_diarization: bool = False) -> None:
    """Run the export in a background thread."""
    try:
        state.push({"stage": "building_plan", "progress": 0.1})

        from src.evaluation.generator_runner import GeneratorError, run as run_generator

        source_paths = song.get("source_paths") or []
        audio_path = source_paths[0] if source_paths else ""
        layout_xml_path = layout.get("xml_path")
        if not layout_xml_path:
            # Do NOT fall through to generator_runner's global-settings fallback —
            # that resolves whatever xLights layout happens to be configured
            # machine-wide, which silently generates against the wrong layout
            # instead of the repo-committed one (see bug-172 follow-up).
            raise GeneratorError(
                "layout/xlights_rgbeffects.xml is missing from the repo checkout."
            )

        # Honor the user's per-section theme picks from the Theme screen
        # instead of letting the generator auto-select every section.
        theme_overrides = {
            a["section_index"]: a["theme_id"]
            for a in session.get("assignments", [])
            if a.get("theme_id") and "section_index" in a
        }

        # The already-classified section roles/energies (verse/chorus/...)
        # from the Theme screen -- written by analysis.py at analyze/commit
        # time as "<audio_stem>_story.json". Without this, build_plan()
        # silently re-derives unclassified section energies straight from
        # raw detector boundaries, and role labels are just the raw
        # segmentino/QM-segmenter letters (fixed 2026-07-21: this was the
        # actual root cause of "Sections" showing N1/A_1/qm_boundary
        # instead of verse/chorus in the exported .xsq).
        story_path = None
        if audio_path:
            candidate = Path(audio_path).parent / (Path(audio_path).stem + "_story.json")
            if candidate.exists():
                story_path = candidate

        # Surface the lyric/vocal track build in the render UI: report what
        # the session carries before the generator embeds it.
        lyrics = session.get("lyrics") or []
        words = session.get("words") or []
        phonemes = session.get("phonemes") or []
        # words carry a "speaker" tag (0=lead, 1=backup) from
        # src.analyzer.vocal_diarization -- surface whether a confident
        # second voice was actually found, since the accept-gate silently
        # collapses everything to speaker 0 otherwise (no other way to see
        # this from the Export screen).
        backup_word_count = sum(1 for w in words if w.get("speaker", 0) == 1)
        detail = (
            f"{len(lyrics)} lyric lines · {len(words)} words · {len(phonemes)} phonemes"
            if (lyrics or words) else
            "no lyrics in session — skipping vocal tracks"
        )
        if words:
            detail += (
                f" · backup singer detected ({backup_word_count} words)"
                if backup_word_count else
                " · no second voice detected"
            )
        # PhonemeAnalyzer discards the ENTIRE pasted lyrics text and
        # re-transcribes the whole song from scratch when fewer than 50% of
        # the pasted words aligned to the audio -- surface that here so
        # "why is it making up words when I provided lyrics" is answerable
        # from the Export screen instead of a silent, discarded warning.
        lyrics_warnings = session.get("lyrics_warnings") or []
        if lyrics_warnings:
            detail += " · ⚠ " + "; ".join(lyrics_warnings)
        state.push({
            "stage": "lyric_tracks",
            "progress": 0.25,
            "detail": detail,
        })

        state.push({"stage": "placing_effects", "progress": 0.4})

        def _placement_progress(detail: str, frac: float) -> None:
            # frac is the placement pass's own 0-1 progress; map it into the
            # 0.4-0.85 band this stage occupies in the overall export.
            state.push({
                "stage": "placing_effects",
                "progress": round(0.4 + 0.45 * max(0.0, min(frac, 1.0)), 3),
                "detail": detail,
            })

        xsq_bytes = run_generator(
            song_id=song["song_id"],
            audio_path=audio_path,
            audio_hash=song["song_id"],
            layout_path=layout_xml_path,
            theme_overrides=theme_overrides,
            lyrics=lyrics or None,
            words=words or None,
            phonemes=phonemes or None,
            genre=genre,
            occasion=occasion,
            video_path=song.get("video_path"),
            ignored_image_words=session.get("ignored_image_words") or None,
            include_extra_timing=include_extra_timing,
            title_override=song.get("title"),
            artist_override=song.get("artist"),
            vocal_diarization=vocal_diarization,
            story_path=story_path,
            progress_cb=_placement_progress,
        )

        state.push({"stage": "writing_xsq", "progress": 0.9})

        tmp_dir = tempfile.mkdtemp(prefix="xonset_export_")
        output_path = str(Path(tmp_dir) / (destination_name or "output.xsq"))
        Path(output_path).write_bytes(xsq_bytes)

        with state.lock:
            state.output_path = output_path
            state.status = "done"

        state.push({
            "stage": "done",
            "output_path": output_path,
            "bytes": len(xsq_bytes),
        })
    except GeneratorError as exc:
        with state.lock:
            state.status = "failed"
        state.push({"stage": "failed", "error": str(exc)})
    except Exception as exc:
        with state.lock:
            state.status = "failed"
        state.push({"stage": "failed", "error": str(exc)})


@api_v1.route("/songs/<song_id>/export", methods=["POST"])
def start_export(song_id: str):
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    # Layout is a fixed file committed to the repo (layout/xlights_rgbeffects.xml)
    layout = get_committed_layout()
    if layout is None:
        return jsonify({"error": {"code": "layout_missing",
                                   "message": "layout/xlights_rgbeffects.xml is missing from the repo"}}), 409

    # Check theming complete
    if song.get("status") not in ("themed",):
        session = load_session(song_id)
        missing: list[int] = []
        if session:
            for a in session.get("assignments", []):
                if not a.get("theme_id") or not a.get("user_confirmed"):
                    missing.append(a["section_index"])
        else:
            missing = []
        return jsonify({"error": {
            "code": "incomplete_theming",
            "message": f"{len(missing)} sections still need a theme.",
            "details": {"missing_sections": missing},
        }}), 409

    # Check source file
    source_paths = song.get("source_paths") or []
    source_path = source_paths[0] if source_paths else ""
    if source_path and not Path(source_path).exists():
        return jsonify({"error": {"code": "source_file_missing",
                                   "message": "Audio source not found on disk"}}), 409

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "incomplete_theming",
                                   "message": "No session data"}}), 409

    body = request.get_json(silent=True) or {}
    fmt = body.get("format", "xsq")
    include_extra_timing = bool(body.get("include_extra_timing", True))
    # Default True per explicit user request (2026-07-21, see
    # GenerationConfig.vocal_diarization) -- no Export screen checkbox yet;
    # opt out per-export via the POST body if it causes problems.
    vocal_diarization = bool(body.get("vocal_diarization", True))
    default_name = Path(source_path).stem if source_path else song.get("title", song_id)
    destination_name = body.get("destination_name", f"{default_name}_AI.xsq")

    # Dashboard-wide genre/occasion preferences steer auto theme selection
    # for sections without a user override ("pop"/"general" = generator
    # defaults when unset).
    prefs = lib.get("preferences", {}) or {}
    genre = prefs.get("genre") or "pop"
    occasion = prefs.get("occasion") or "general"

    exp_id = _export_id()
    state = _ExportState(exp_id)

    with _exports_lock:
        _exports[exp_id] = state
        _song_exports[song_id] = exp_id

    t = threading.Thread(
        target=_run_export,
        args=(state, song, session, layout, destination_name, fmt, genre, occasion,
              include_extra_timing, vocal_diarization),
        daemon=True,
    )
    t.start()

    return jsonify({"export_id": exp_id, "started_at": state.started_at}), 202


@api_v1.route("/songs/<song_id>/export/status", methods=["GET"])
def export_status(song_id: str):
    with _exports_lock:
        exp_id = _song_exports.get(song_id)
        state = _exports.get(exp_id) if exp_id else None

    if state is None:
        return jsonify({"error": {"code": "run_not_found",
                                   "message": "No export run found"}}), 404

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


@api_v1.route("/songs/<song_id>/export/download-package", methods=["GET"])
def download_export_package(song_id: str):
    with _exports_lock:
        exp_id = _song_exports.get(song_id)
        state = _exports.get(exp_id) if exp_id else None

    if state is None or state.status != "done" or not state.output_path:
        return jsonify({"error": {"code": "export_not_ready",
                                   "message": "No completed export found for this song"}}), 404

    xsq_path = Path(state.output_path)
    if not xsq_path.exists():
        return jsonify({"error": {"code": "file_missing",
                                   "message": "Exported file is no longer available"}}), 404

    layout = get_committed_layout()
    if layout is None:
        return jsonify({"error": {"code": "layout_missing",
                                   "message": "layout/xlights_rgbeffects.xml is missing from the repo"}}), 409

    rgbeffects_path = Path(layout["xml_path"])
    networks_path = get_committed_networks_xml_path()

    # .xsqz is xLights' own recognized extension for a zipped sequence
    # package (.xsq + supporting layout files) — same zip container, just
    # the extension xLights knows to unpack on import.
    package_path = xsq_path.with_suffix(".xsqz")
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(xsq_path, arcname=xsq_path.name)
        zf.write(rgbeffects_path, arcname=rgbeffects_path.name)
        if networks_path.exists():
            zf.write(networks_path, arcname=networks_path.name)

    return send_file(package_path, as_attachment=True, download_name=package_path.name)


@api_v1.route("/songs/<song_id>/export/mapping", methods=["GET"])
def export_mapping(song_id: str):
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    layout = get_committed_layout()
    if layout is None:
        return jsonify({"error": {"code": "layout_missing",
                                   "message": "layout/xlights_rgbeffects.xml is missing from the repo"}}), 409

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "incomplete_theming",
                                   "message": "No session data"}}), 409

    assignments = session.get("assignments", [])
    theme_by_section: dict[int, str] = {
        a["section_index"]: a.get("theme_id", "") for a in assignments
    }

    props = []
    for p in layout.get("props", []):
        props.append({
            **p,
            "theme_colors_by_section": [
                {"section_index": idx, "theme_id": tid, "colors": []}
                for idx, tid in theme_by_section.items()
            ],
        })

    return jsonify({"props": props}), 200
