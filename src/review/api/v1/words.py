"""Word attribution editing — view and correct per-singer lyric attribution.

GET /api/v1/songs/<song_id>/words
    -> {"words": [...], "phonemes": [...], "singers": [...]}

PUT /api/v1/songs/<song_id>/words
    body: {"words": [{"label","start_ms","end_ms","singers":[str],"backing":bool}, ...]}
    Replaces the session word array, re-propagates attribution onto phonemes by
    time-containment, and persists. The next export reflects the edits.
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1
from src.review.storage.library import load_library
from src.review.storage.assignments import load_session, save_full_session
from src.analyzer.lyric_attribution import propagate_singers_to_phonemes


def _load_song(song_id: str):
    lib = load_library()
    return next((s for s in lib["songs"] if s["song_id"] == song_id), None)


def _distinct_singers(words: list[dict]) -> list[str]:
    """Singer names in first-appearance order (backing excluded)."""
    seen: list[str] = []
    for w in words:
        for name in (w.get("singers") or []):
            if name not in seen:
                seen.append(name)
    return seen


@api_v1.route("/songs/<song_id>/words", methods=["GET"])
def get_words(song_id: str):
    if _load_song(song_id) is None:
        return jsonify({"error": {"code": "song_not_found", "message": "Song not found"}}), 404
    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409
    words = session.get("words", []) or []
    return jsonify({
        "words": words,
        "phonemes": session.get("phonemes", []) or [],
        "singers": _distinct_singers(words),
    }), 200


@api_v1.route("/songs/<song_id>/words", methods=["PUT"])
def put_words(song_id: str):
    if _load_song(song_id) is None:
        return jsonify({"error": {"code": "song_not_found", "message": "Song not found"}}), 404
    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    body = request.get_json(silent=True) or {}
    incoming = body.get("words")
    if not isinstance(incoming, list):
        return jsonify({"error": {"code": "missing_field",
                                   "message": "'words' must be an array"}}), 400

    words: list[dict] = []
    for w in incoming:
        try:
            words.append({
                "label": str(w["label"]),
                "start_ms": int(w["start_ms"]),
                "end_ms": int(w["end_ms"]),
                "singers": [str(s) for s in (w.get("singers") or [])],
                "backing": bool(w.get("backing", False)),
                **({"speaker": w["speaker"]} if w.get("speaker") is not None else {}),
            })
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": {"code": "invalid_word",
                                       "message": "each word needs label/start_ms/end_ms"}}), 422

    phonemes = session.get("phonemes", []) or []
    propagate_singers_to_phonemes(words, phonemes)

    session["words"] = words
    session["phonemes"] = phonemes
    save_full_session(song_id, session)

    return jsonify({
        "words": words,
        "phonemes": phonemes,
        "singers": _distinct_singers(words),
        "count": len(words),
    }), 200
