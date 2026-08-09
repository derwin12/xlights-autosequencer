"""GET/POST/DELETE /api/v1/songs/<song_id>/moving-head-keywords — per-song
lyric-word-triggered Moving Head accents (GenerationConfig.moving_head_keyword_motions).

Three built-in words (shake/bounce/spin) each map to their own physical
motion by default. Users can add custom words from a song's own lyrics,
assigning each to one of the four existing motions (shake/bounce/spin/
flash -- "flash" points every head straight up at full white, the same
pose used for the song-ending flash), or remove any word (built-in or
custom) to disable it for this song. Stored as
``moving_head_keyword_motions`` in the song's session JSON, consumed at
export time (``GenerationConfig.moving_head_keyword_motions``) -- same
per-song-override pattern as ``ignored_image_occurrences`` in images.py
(though this one is still word-level, not per-occurrence).

Also hosts per-song manual triggers (``/songs/<song_id>/moving-head-timestamps``,
2026-08-09): pins a Moving Head accent to an explicit ``mm:ss`` timestamp
independent of any lyric keyword (Extras screen). Stored as
``moving_head_manual_triggers`` (each ``{"start_ms", "motion"}``) and folded
into the same trigger stream as ``moving_head_keyword_motions`` at export
time (see ``moving_head.place_moving_head_keyword_accents``'s
``manual_triggers`` parameter, ``GenerationConfig.moving_head_manual_triggers``).
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1

_DEFAULT_KEYWORD_MOTIONS: dict[str, str] = {"shake": "shake", "spin": "spin", "bounce": "bounce"}
_VALID_MOTIONS = {"shake", "bounce", "spin", "flash"}


def _load_keyword_motions(song_id: str) -> dict[str, str]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    stored = session.get("moving_head_keyword_motions")
    if stored is None:
        return dict(_DEFAULT_KEYWORD_MOTIONS)
    return {str(k): str(v) for k, v in stored.items()}


def _save_keyword_motions(song_id: str, motions: dict[str, str]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["moving_head_keyword_motions"] = motions
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/moving-head-keywords", methods=["GET"])
def list_moving_head_keywords(song_id: str):
    return jsonify({"keywords": _load_keyword_motions(song_id)}), 200


@api_v1.route("/songs/<song_id>/moving-head-keywords", methods=["POST"])
def add_moving_head_keyword(song_id: str):
    body = request.get_json(silent=True) or {}
    word = str(body.get("word") or "").strip().lower()
    motion = str(body.get("motion") or "").strip().lower()
    if not word:
        return jsonify({"error": {"code": "missing_word", "message": "A word is required"}}), 400
    if motion not in _VALID_MOTIONS:
        return jsonify({"error": {
            "code": "invalid_motion",
            "message": f"motion must be one of {sorted(_VALID_MOTIONS)}",
        }}), 400

    motions = _load_keyword_motions(song_id)
    motions[word] = motion
    _save_keyword_motions(song_id, motions)
    return jsonify({"created": True, "keywords": motions}), 200


@api_v1.route("/songs/<song_id>/moving-head-keywords/<word>", methods=["DELETE"])
def remove_moving_head_keyword(song_id: str, word: str):
    token = word.strip().lower()
    motions = _load_keyword_motions(song_id)
    if token not in motions:
        return jsonify({"error": {
            "code": "not_found",
            "message": f"'{token}' is not a configured keyword for this song",
        }}), 404
    del motions[token]
    _save_keyword_motions(song_id, motions)
    return jsonify({"removed": True, "keywords": motions}), 200


def _load_manual_triggers(song_id: str) -> list[dict]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    return [
        {"start_ms": o.get("start_ms"), "motion": str(o.get("motion", ""))}
        for o in session.get("moving_head_manual_triggers", [])
    ]


def _save_manual_triggers(song_id: str, triggers: list[dict]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["moving_head_manual_triggers"] = triggers
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/moving-head-timestamps", methods=["GET"])
def list_manual_triggers(song_id: str):
    return jsonify({"triggers": _load_manual_triggers(song_id)}), 200


@api_v1.route("/songs/<song_id>/moving-head-timestamps", methods=["PUT"])
def set_manual_trigger(song_id: str):
    """Pin a Moving Head accent to an explicit timestamp (Extras screen's
    mm:ss entry), independent of any lyric keyword. Idempotent: PUT-ing the
    same ``start_ms`` again replaces the prior entry rather than duplicating
    it.
    """
    body = request.get_json(silent=True) or {}
    start_ms = body.get("start_ms")
    motion = str(body.get("motion") or "").strip().lower()
    if start_ms is None:
        return jsonify({"error": {"code": "missing_start_ms", "message": "start_ms is required"}}), 400
    if motion not in _VALID_MOTIONS:
        return jsonify({"error": {
            "code": "invalid_motion",
            "message": f"motion must be one of {sorted(_VALID_MOTIONS)}",
        }}), 400

    triggers = [t for t in _load_manual_triggers(song_id) if t["start_ms"] != start_ms]
    triggers.append({"start_ms": start_ms, "motion": motion})
    triggers.sort(key=lambda t: t["start_ms"])
    _save_manual_triggers(song_id, triggers)
    return jsonify({"set": True, "triggers": triggers}), 200


@api_v1.route("/songs/<song_id>/moving-head-timestamps/<int:start_ms>", methods=["DELETE"])
def clear_manual_trigger(song_id: str, start_ms: int):
    triggers = _load_manual_triggers(song_id)
    if not any(t["start_ms"] == start_ms for t in triggers):
        return jsonify({"error": {"code": "not_found",
                                   "message": f"No manual trigger at {start_ms}ms"}}), 404
    triggers = [t for t in triggers if t["start_ms"] != start_ms]
    _save_manual_triggers(song_id, triggers)
    return jsonify({"cleared": True, "triggers": triggers}), 200
