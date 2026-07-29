"""GET/POST/DELETE /api/v1/songs/<song_id>/shadow-words — per-song
lyric-word-triggered Shadow Text accents (GenerationConfig.shadow_text_words).

Tagging a word "shadow" from the Pictures screen fires a two-layer Text
effect (the word in the song's anchor palette color 1, an offset copy in
color 2 behind it) wherever that word is sung, on the same Matrix/Mega Tree
targets Pictures effects use. Stored as ``shadow_text_words`` in the song's
session JSON, consumed at export time
(``GenerationConfig.shadow_text_words``) -- same per-song-override pattern
as ``ignored_image_words`` in images.py.
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1


def _load_shadow_words(song_id: str) -> list[str]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    return [str(w) for w in session.get("shadow_text_words", [])]


def _save_shadow_words(song_id: str, words: list[str]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["shadow_text_words"] = words
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/shadow-words", methods=["GET"])
def list_shadow_words(song_id: str):
    return jsonify({"words": _load_shadow_words(song_id)}), 200


@api_v1.route("/songs/<song_id>/shadow-words", methods=["POST"])
def add_shadow_word(song_id: str):
    body = request.get_json(silent=True) or {}
    word = str(body.get("word") or "").strip().lower()
    if not word:
        return jsonify({"error": {"code": "missing_word", "message": "A word is required"}}), 400

    words = _load_shadow_words(song_id)
    if word not in words:
        words.append(word)
        _save_shadow_words(song_id, words)
    return jsonify({"created": True, "words": words}), 200


@api_v1.route("/songs/<song_id>/shadow-words/<word>", methods=["DELETE"])
def remove_shadow_word(song_id: str, word: str):
    token = word.strip().lower()
    words = _load_shadow_words(song_id)
    if token not in words:
        return jsonify({"error": {
            "code": "not_found",
            "message": f"'{token}' is not a shadow word for this song",
        }}), 404
    words = [w for w in words if w != token]
    _save_shadow_words(song_id, words)
    return jsonify({"removed": True, "words": words}), 200
