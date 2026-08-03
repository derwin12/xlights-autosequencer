"""GET/POST/DELETE /api/v1/songs/<song_id>/shadow-words — per-song
lyric-occurrence-triggered Shadow Text accents
(GenerationConfig.shadow_text_occurrences).

Tagging a word "shadow" from the Pictures screen fires a two-layer Text
effect (the word in the song's anchor palette color 1, an offset copy in
color 2 behind it) for that ONE lyric occurrence, on the same Matrix/Mega
Tree targets Pictures effects use. Stored as ``shadow_text_occurrences``
(each ``{"word", "start_ms"}``) in the song's session JSON, consumed at
export time (``GenerationConfig.shadow_text_occurrences``) -- same
per-occurrence, per-song-override pattern as ``ignored_image_occurrences``
in images.py.
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1


def _load_shadow_occurrences(song_id: str) -> list[dict]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    return [
        {"word": str(o.get("word", "")), "start_ms": o.get("start_ms")}
        for o in session.get("shadow_text_occurrences", [])
    ]


def _save_shadow_occurrences(song_id: str, occurrences: list[dict]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["shadow_text_occurrences"] = occurrences
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/shadow-words", methods=["GET"])
def list_shadow_words(song_id: str):
    return jsonify({"occurrences": _load_shadow_occurrences(song_id)}), 200


@api_v1.route("/songs/<song_id>/shadow-words", methods=["POST"])
def add_shadow_word(song_id: str):
    body = request.get_json(silent=True) or {}
    word = str(body.get("word") or "").strip().lower()
    start_ms = body.get("start_ms")
    if not word:
        return jsonify({"error": {"code": "missing_word", "message": "A word is required"}}), 400
    if start_ms is None:
        return jsonify({"error": {"code": "missing_start_ms", "message": "start_ms is required"}}), 400

    occurrences = _load_shadow_occurrences(song_id)
    if not any(o["word"] == word and o["start_ms"] == start_ms for o in occurrences):
        occurrences.append({"word": word, "start_ms": start_ms})
        _save_shadow_occurrences(song_id, occurrences)
    return jsonify({"created": True, "occurrences": occurrences}), 200


@api_v1.route("/songs/<song_id>/shadow-words/<word>/<int:start_ms>", methods=["DELETE"])
def remove_shadow_word(song_id: str, word: str, start_ms: int):
    token = word.strip().lower()
    occurrences = _load_shadow_occurrences(song_id)
    if not any(o["word"] == token and o["start_ms"] == start_ms for o in occurrences):
        return jsonify({"error": {
            "code": "not_found",
            "message": f"'{token}' at {start_ms}ms is not a shadow occurrence for this song",
        }}), 404
    occurrences = [o for o in occurrences if not (o["word"] == token and o["start_ms"] == start_ms)]
    _save_shadow_occurrences(song_id, occurrences)
    return jsonify({"removed": True, "occurrences": occurrences}), 200
