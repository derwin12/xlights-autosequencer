"""GET/POST/DELETE /api/v1/songs/<song_id>/moving-head-keywords — per-song
lyric-word-triggered Moving Head accents (GenerationConfig.moving_head_keyword_motions).

Three built-in words (shake/bounce/spin) each map to their own physical
motion by default. Users can add custom words from a song's own lyrics,
assigning each to one of the three existing motions, or remove any word
(built-in or custom) to disable it for this song. Stored as
``moving_head_keyword_motions`` in the song's session JSON, consumed at
export time (``GenerationConfig.moving_head_keyword_motions``) -- same
per-song-override pattern as ``ignored_image_words`` in images.py.
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1

_DEFAULT_KEYWORD_MOTIONS: dict[str, str] = {"shake": "shake", "spin": "spin", "bounce": "bounce"}
_VALID_MOTIONS = {"shake", "bounce", "spin"}


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
