"""Export endpoints — T055.

POST /api/v1/songs/<song_id>/export         — start export
GET  /api/v1/songs/<song_id>/export/status  — SSE progress
GET  /api/v1/songs/<song_id>/export/mapping — prop-theme mapping table
"""
from __future__ import annotations

import datetime
import json
import random
import string
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request, send_file, stream_with_context

from . import api_v1
from src.review.storage.library import load_library, save_library
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
                layout: dict, destination_name: str, fmt: str) -> None:
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
            # instead of this song's actual imported one (see bug-172 follow-up).
            raise GeneratorError(
                "This layout was imported before file persistence was added. "
                "Re-import your xlights_rgbeffects.xml via the Export screen's "
                "Import Layout button, then try exporting again."
            )

        # Honor the user's per-section theme picks from the Theme screen
        # instead of letting the generator auto-select every section.
        theme_overrides = {
            a["section_index"]: a["theme_id"]
            for a in session.get("assignments", [])
            if a.get("theme_id") and "section_index" in a
        }

        state.push({"stage": "placing_effects", "progress": 0.4})

        xsq_bytes = run_generator(
            song_id=song["song_id"],
            audio_path=audio_path,
            audio_hash=song["song_id"],
            layout_path=layout_xml_path,
            theme_overrides=theme_overrides,
            lyrics=session.get("lyrics"),
        )

        state.push({"stage": "writing_xml", "progress": 0.9})

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

    # Check layout
    layout = lib.get("layout")
    if layout is None:
        return jsonify({"error": {"code": "layout_required",
                                   "message": "No xLights layout has been imported"}}), 409

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
    default_name = Path(source_path).stem if source_path else song.get("title", song_id)
    destination_name = body.get("destination_name", f"{default_name}.xsq")

    exp_id = _export_id()
    state = _ExportState(exp_id)

    with _exports_lock:
        _exports[exp_id] = state
        _song_exports[song_id] = exp_id

    t = threading.Thread(
        target=_run_export,
        args=(state, song, session, layout, destination_name, fmt),
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


@api_v1.route("/songs/<song_id>/export/download", methods=["GET"])
def download_export(song_id: str):
    with _exports_lock:
        exp_id = _song_exports.get(song_id)
        state = _exports.get(exp_id) if exp_id else None

    if state is None or state.status != "done" or not state.output_path:
        return jsonify({"error": {"code": "export_not_ready",
                                   "message": "No completed export found for this song"}}), 404

    output_path = Path(state.output_path)
    if not output_path.exists():
        return jsonify({"error": {"code": "file_missing",
                                   "message": "Exported file is no longer available"}}), 404

    return send_file(output_path, as_attachment=True, download_name=output_path.name)


@api_v1.route("/songs/<song_id>/export/mapping", methods=["GET"])
def export_mapping(song_id: str):
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    layout = lib.get("layout")
    if layout is None:
        return jsonify({"error": {"code": "layout_required",
                                   "message": "No layout imported"}}), 409

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
