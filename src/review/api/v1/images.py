"""GET/POST /api/v1/images — global image library for Pictures effects.

Unlike video import (song-scoped), images are a shared library: an image
uploaded once for a "topic" (e.g. a lyric word like "snowman") is available
to every song's Pictures placement and every future song's suggested-topics
matching, not just the song it was uploaded against.

Also hosts the per-song ignore list (``/songs/<song_id>/ignored-images``):
unmapping a word→image match on the Pictures screen suppresses that word's
lyric-matched Pictures bursts for this song only — the library entry itself
stays available to every other song. Stored as ``ignored_image_words`` in
the song's session JSON and consumed at export time
(``GenerationConfig.ignored_image_words``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request

from . import api_v1
from src.generator.image_catalog import load_image_library, save_image_to_library

_ALLOWED_IMAGE_EXTENSIONS = {".gif", ".png", ".bmp", ".jpg", ".jpeg"}
_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


@api_v1.route("/images", methods=["GET"])
def list_images():
    return jsonify({"images": load_image_library()}), 200


@api_v1.route("/images", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": {"code": "missing_file", "message": "No image file provided"}}), 400

    f = request.files["image"]
    filename = f.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"error": {"code": "unsupported_format",
                                   "message": f"Unsupported image type: {ext}"}}), 400

    tag = (request.form.get("tag") or "").strip()
    if not tag:
        return jsonify({"error": {"code": "missing_tag", "message": "A tag is required"}}), 400

    image_bytes = f.read()
    if len(image_bytes) > _MAX_BYTES:
        return jsonify({"error": {"code": "image_too_large",
                                   "message": "File exceeds 50 MB limit"}}), 413

    entry = save_image_to_library(
        tag=tag,
        filename=filename,
        data=image_bytes,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
    )
    return jsonify({"created": True, "image": entry}), 201


def _load_ignored_words(song_id: str) -> list[str]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    return [str(w) for w in session.get("ignored_image_words", [])]


def _save_ignored_words(song_id: str, words: list[str]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["ignored_image_words"] = words
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/ignored-images", methods=["GET"])
def list_ignored_images(song_id: str):
    return jsonify({"words": _load_ignored_words(song_id)}), 200


@api_v1.route("/songs/<song_id>/ignored-images", methods=["POST"])
def ignore_image_word(song_id: str):
    body = request.get_json(silent=True) or {}
    word = str(body.get("word") or "").strip().lower()
    if not word:
        return jsonify({"error": {"code": "missing_word", "message": "A word is required"}}), 400

    words = _load_ignored_words(song_id)
    if word not in words:
        words.append(word)
        _save_ignored_words(song_id, words)
    return jsonify({"ignored": True, "words": words}), 200


@api_v1.route("/songs/<song_id>/ignored-images/<word>", methods=["DELETE"])
def restore_image_word(song_id: str, word: str):
    token = word.strip().lower()
    words = _load_ignored_words(song_id)
    if token not in words:
        return jsonify({"error": {"code": "not_ignored",
                                   "message": f"'{token}' is not in this song's ignore list"}}), 404
    words = [w for w in words if w != token]
    _save_ignored_words(song_id, words)
    return jsonify({"restored": True, "words": words}), 200
