"""Assignment endpoints — T051.

GET  /api/v1/songs/<song_id>/assignments
PUT  /api/v1/songs/<song_id>/assignments/<section_index>
POST /api/v1/songs/<song_id>/assignments/accept-all
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1
from .themes import _load_themes
from src.review.storage.library import load_library, save_library
from src.review.storage.assignments import load_session, save_session

_DEFAULT_OVERRIDES = {
    "brightness": 1.0,
    "hit_strength": 0.5,
    "dwell_time": 1.0,
    "color_shift": 0.0,
}


def _valid_theme_ids() -> set[str]:
    """Real theme catalog IDs (built-in + custom), loaded live so this never goes stale."""
    return {theme["theme_id"] for theme in _load_themes()}


def _get_song_or_error(song_id: str):
    """Return (song, None) or (None, error_response)."""
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return None, None, (jsonify({"error": {"code": "song_not_found",
                                                "message": "Song not found"}}), 404)
    return song, lib, None


@api_v1.route("/songs/<song_id>/assignments", methods=["GET"])
def get_assignments(song_id: str):
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    if song.get("status") == "draft":
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "Song has not been analyzed yet"}}), 409

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No session data available"}}), 409

    return jsonify({
        "assignments": session.get("assignments", []),
        "song_status": song.get("status", "analyzed"),
    }), 200


@api_v1.route("/songs/<song_id>/assignments/<int:section_index>", methods=["PUT"])
def put_assignment(song_id: str, section_index: int):
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    theme_id = body.get("theme_id")
    overrides_patch = body.get("overrides") or {}

    if theme_id and theme_id not in _valid_theme_ids():
        return jsonify({"error": {"code": "theme_not_found",
                                   "message": f"Theme '{theme_id}' not found"}}), 404

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No session data available"}}), 409

    assignments = session.get("assignments", [])
    sections = session.get("sections", [])

    assignment = next((a for a in assignments if a["section_index"] == section_index), None)
    if assignment is None:
        return jsonify({"error": {"code": "section_not_found",
                                   "message": f"Section {section_index} not found"}}), 404

    # FR-032a: changing theme_id resets overrides to defaults first
    if theme_id and theme_id != assignment.get("theme_id"):
        assignment["overrides"] = dict(_DEFAULT_OVERRIDES)
        assignment["theme_id"] = theme_id
        assignment["user_confirmed"] = True

    # Apply any explicit override patches
    if overrides_patch:
        for k, v in overrides_patch.items():
            if k in assignment["overrides"]:
                assignment["overrides"][k] = v

    if theme_id:
        assignment["user_confirmed"] = True

    save_session(song_id, sections, assignments)

    # Check if all sections now confirmed — flip status to "themed"
    all_confirmed = all(
        a.get("user_confirmed") and a.get("theme_id")
        for a in assignments
    )
    song_status = song.get("status", "analyzed")
    if all_confirmed and song_status == "analyzed":
        for s in lib["songs"]:
            if s["song_id"] == song_id:
                s["status"] = "themed"
                song_status = "themed"
                break
        save_library(lib)

    return jsonify({
        "assignment": assignment,
        "song_status": song_status,
    }), 200


@api_v1.route("/songs/<song_id>/assignments/accept-all", methods=["POST"])
def accept_all_assignments(song_id: str):
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No session data available"}}), 409

    assignments = session.get("assignments", [])
    sections = session.get("sections", [])

    # Check all assignments have a theme_id
    incomplete = [a for a in assignments if not a.get("theme_id")]
    if incomplete:
        return jsonify({"error": {"code": "incomplete_assignments",
                                   "message": "Some sections have no theme assigned"}}), 409

    count = 0
    for a in assignments:
        if not a.get("user_confirmed"):
            a["user_confirmed"] = True
            count += 1
        else:
            count += 1  # count all confirmed

    save_session(song_id, sections, assignments)

    # Flip song status to "themed"
    for s in lib["songs"]:
        if s["song_id"] == song_id:
            s["status"] = "themed"
            break
    save_library(lib)

    return jsonify({"song_status": "themed", "confirmed_count": count}), 200
