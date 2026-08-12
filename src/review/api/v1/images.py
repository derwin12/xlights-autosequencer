"""GET/POST /api/v1/images — global image library for Pictures effects.

Unlike video import (song-scoped), images are a shared library: an image
uploaded once for a "topic" (e.g. a lyric word like "snowman") is available
to every song's Pictures placement and every future song's suggested-topics
matching, not just the song it was uploaded against.

Also hosts the per-song ignore list (``/songs/<song_id>/ignored-images``):
unmapping a word→image match on the Pictures screen suppresses that ONE
lyric occurrence's Pictures burst for this song only — other occurrences of
the same word, and the library entry itself, stay available. Stored as
``ignored_image_occurrences`` (each ``{"word", "start_ms"}``) in the song's
session JSON and consumed at export time
(``GenerationConfig.ignored_image_occurrences``).

And the per-song image overrides (``/songs/<song_id>/image-overrides``):
pins one specific lyric occurrence to a chosen library image, distinct from
whatever that word's normal fuzzy-tag match resolves to for its OTHER
occurrences. Stored as ``image_occurrence_overrides`` (each ``{"word",
"start_ms", "image_id"}``) in the song's session JSON and consumed at
export time (``GenerationConfig.image_occurrence_overrides``) — same
per-occurrence, per-song-override pattern as ``ignored_image_occurrences``
above, just carrying a chosen value instead of a boolean.

And per-song manual occurrences (``/songs/<song_id>/image-manual-occurrences``,
2026-08-09): pins a Pictures burst to an explicit ``mm:ss`` timestamp
independent of any transcribed lyric word (Extras screen). Unlike an
override, there's no existing lyric-matched occurrence to pin -- this
creates a wholly new one, keyed purely on ``start_ms``. Stored as
``image_manual_occurrences`` (each ``{"start_ms", "image_id"}``) and merged
into ``word_image_matches`` at export time (see ``plan.py``'s
``_manual_picture_matches``, ``GenerationConfig.image_manual_occurrences``).

And ``GET /songs/<song_id>/image-matches`` (2026-08-09): recomputes
per-occurrence matches/unmatched-topics live against the CURRENT image
library, rather than the ``image_suggestions``/``image_topics`` snapshot
``analysis.py`` writes once at analyze time and never refreshes — a word
uploaded an image for after analyzing would otherwise never show its
other occurrences on the Pictures screen even though export-time
generation (which also reruns this matching fresh) already handles it
correctly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request

from . import api_v1
from src.generator.image_catalog import (
    find_unmatched_topics,
    load_image_library,
    replace_image_in_library,
    save_image_to_library,
    suggest_images_for_words,
)

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


@api_v1.route("/images/<image_id>", methods=["PUT"])
def replace_image(image_id: str):
    """Overwrite an existing library entry's file in place (see
    image_catalog.replace_image_in_library) -- every occurrence already
    matched to this entry (by image_id, via fuzzy-tag matching or a
    per-occurrence override) picks up the new image immediately, unlike a
    fresh POST /images upload (which always creates a separate new entry).
    """
    if "image" not in request.files:
        return jsonify({"error": {"code": "missing_file", "message": "No image file provided"}}), 400

    f = request.files["image"]
    filename = f.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"error": {"code": "unsupported_format",
                                   "message": f"Unsupported image type: {ext}"}}), 400

    image_bytes = f.read()
    if len(image_bytes) > _MAX_BYTES:
        return jsonify({"error": {"code": "image_too_large",
                                   "message": "File exceeds 50 MB limit"}}), 413

    entry = replace_image_in_library(
        image_id=image_id,
        filename=filename,
        data=image_bytes,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
    )
    if entry is None:
        return jsonify({"error": {"code": "image_not_found",
                                   "message": f"No library image with id '{image_id}'"}}), 404
    return jsonify({"replaced": True, "image": entry}), 200


def _load_ignored_occurrences(song_id: str) -> list[dict]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    return [
        {"word": str(o.get("word", "")), "start_ms": o.get("start_ms")}
        for o in session.get("ignored_image_occurrences", [])
    ]


def _save_ignored_occurrences(song_id: str, occurrences: list[dict]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["ignored_image_occurrences"] = occurrences
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/ignored-images", methods=["GET"])
def list_ignored_images(song_id: str):
    return jsonify({"occurrences": _load_ignored_occurrences(song_id)}), 200


@api_v1.route("/songs/<song_id>/ignored-images", methods=["POST"])
def ignore_image_word(song_id: str):
    body = request.get_json(silent=True) or {}
    word = str(body.get("word") or "").strip().lower()
    start_ms = body.get("start_ms")
    if not word:
        return jsonify({"error": {"code": "missing_word", "message": "A word is required"}}), 400
    if start_ms is None:
        return jsonify({"error": {"code": "missing_start_ms", "message": "start_ms is required"}}), 400

    occurrences = _load_ignored_occurrences(song_id)
    if not any(o["word"] == word and o["start_ms"] == start_ms for o in occurrences):
        occurrences.append({"word": word, "start_ms": start_ms})
        _save_ignored_occurrences(song_id, occurrences)

    # A per-occurrence override always wins over an ignore at export time
    # (image_catalog.suggest_images_for_words), so an override left over
    # from a previous "Choose image"/upload must be cleared here too --
    # otherwise "unmap" looks like it worked (the UI shows "unmapped") but
    # the overridden image still renders at export (2026-08-09 user report:
    # a stray override survived an unmap and kept firing at that occurrence).
    overrides = _load_image_overrides(song_id)
    filtered_overrides = [
        o for o in overrides if not (o["word"] == word and o["start_ms"] == start_ms)
    ]
    if len(filtered_overrides) != len(overrides):
        _save_image_overrides(song_id, filtered_overrides)

    return jsonify({"ignored": True, "occurrences": occurrences, "overrides": filtered_overrides}), 200


@api_v1.route("/songs/<song_id>/ignored-images/<word>/<int:start_ms>", methods=["DELETE"])
def restore_image_word(song_id: str, word: str, start_ms: int):
    token = word.strip().lower()
    occurrences = _load_ignored_occurrences(song_id)
    if not any(o["word"] == token and o["start_ms"] == start_ms for o in occurrences):
        return jsonify({"error": {"code": "not_ignored",
                                   "message": f"'{token}' at {start_ms}ms is not in this song's ignore list"}}), 404
    occurrences = [o for o in occurrences if not (o["word"] == token and o["start_ms"] == start_ms)]
    _save_ignored_occurrences(song_id, occurrences)
    return jsonify({"restored": True, "occurrences": occurrences}), 200


def _load_image_overrides(song_id: str) -> list[dict]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    return [
        {"word": str(o.get("word", "")), "start_ms": o.get("start_ms"), "image_id": o.get("image_id")}
        for o in session.get("image_occurrence_overrides", [])
    ]


def _save_image_overrides(song_id: str, overrides: list[dict]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["image_occurrence_overrides"] = overrides
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/image-overrides", methods=["GET"])
def list_image_overrides(song_id: str):
    return jsonify({"overrides": _load_image_overrides(song_id)}), 200


@api_v1.route("/songs/<song_id>/image-overrides", methods=["PUT"])
def set_image_override(song_id: str):
    body = request.get_json(silent=True) or {}
    word = str(body.get("word") or "").strip().lower()
    start_ms = body.get("start_ms")
    image_id = str(body.get("image_id") or "").strip()
    if not word:
        return jsonify({"error": {"code": "missing_word", "message": "A word is required"}}), 400
    if start_ms is None:
        return jsonify({"error": {"code": "missing_start_ms", "message": "start_ms is required"}}), 400
    if not image_id:
        return jsonify({"error": {"code": "missing_image_id", "message": "image_id is required"}}), 400

    library_ids = {e.get("id") for e in load_image_library()}
    if image_id not in library_ids:
        return jsonify({"error": {"code": "image_not_found",
                                   "message": f"No library image with id '{image_id}'"}}), 404

    overrides = [o for o in _load_image_overrides(song_id)
                 if not (o["word"] == word and o["start_ms"] == start_ms)]
    overrides.append({"word": word, "start_ms": start_ms, "image_id": image_id})
    _save_image_overrides(song_id, overrides)
    return jsonify({"set": True, "overrides": overrides}), 200


@api_v1.route("/songs/<song_id>/image-overrides/<word>/<int:start_ms>", methods=["DELETE"])
def clear_image_override(song_id: str, word: str, start_ms: int):
    token = word.strip().lower()
    overrides = _load_image_overrides(song_id)
    if not any(o["word"] == token and o["start_ms"] == start_ms for o in overrides):
        return jsonify({"error": {"code": "not_overridden",
                                   "message": f"'{token}' at {start_ms}ms has no override"}}), 404
    overrides = [o for o in overrides if not (o["word"] == token and o["start_ms"] == start_ms)]
    _save_image_overrides(song_id, overrides)
    return jsonify({"cleared": True, "overrides": overrides}), 200


def _load_manual_occurrences(song_id: str) -> list[dict]:
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    return [
        {"start_ms": o.get("start_ms"), "image_id": o.get("image_id")}
        for o in session.get("image_manual_occurrences", [])
    ]


def _save_manual_occurrences(song_id: str, occurrences: list[dict]) -> None:
    from src.review.storage.assignments import load_session, save_full_session

    session = load_session(song_id) or {}
    session["image_manual_occurrences"] = occurrences
    save_full_session(song_id, session)


@api_v1.route("/songs/<song_id>/image-manual-occurrences", methods=["GET"])
def list_manual_occurrences(song_id: str):
    return jsonify({"occurrences": _load_manual_occurrences(song_id)}), 200


@api_v1.route("/songs/<song_id>/image-manual-occurrences", methods=["PUT"])
def set_manual_occurrence(song_id: str):
    """Pin a Pictures burst to an explicit timestamp (Extras screen's mm:ss
    entry), independent of any transcribed lyric word -- for a moment the
    word transcript doesn't capture. Unlike ``image-overrides`` (which pins
    an EXISTING lyric-matched occurrence to a different image), this creates
    a wholly new occurrence keyed purely on ``start_ms`` since there's no
    word to key on. Idempotent: PUT-ing the same ``start_ms`` again replaces
    the prior entry rather than duplicating it.
    """
    body = request.get_json(silent=True) or {}
    start_ms = body.get("start_ms")
    image_id = str(body.get("image_id") or "").strip()
    if start_ms is None:
        return jsonify({"error": {"code": "missing_start_ms", "message": "start_ms is required"}}), 400
    if not image_id:
        return jsonify({"error": {"code": "missing_image_id", "message": "image_id is required"}}), 400

    library_ids = {e.get("id") for e in load_image_library()}
    if image_id not in library_ids:
        return jsonify({"error": {"code": "image_not_found",
                                   "message": f"No library image with id '{image_id}'"}}), 404

    occurrences = [o for o in _load_manual_occurrences(song_id) if o["start_ms"] != start_ms]
    occurrences.append({"start_ms": start_ms, "image_id": image_id})
    occurrences.sort(key=lambda o: o["start_ms"])
    _save_manual_occurrences(song_id, occurrences)
    return jsonify({"set": True, "occurrences": occurrences}), 200


@api_v1.route("/songs/<song_id>/image-manual-occurrences/<int:start_ms>", methods=["DELETE"])
def clear_manual_occurrence(song_id: str, start_ms: int):
    occurrences = _load_manual_occurrences(song_id)
    if not any(o["start_ms"] == start_ms for o in occurrences):
        return jsonify({"error": {"code": "not_found",
                                   "message": f"No manual occurrence at {start_ms}ms"}}), 404
    occurrences = [o for o in occurrences if o["start_ms"] != start_ms]
    _save_manual_occurrences(song_id, occurrences)
    return jsonify({"cleared": True, "occurrences": occurrences}), 200


@api_v1.route("/songs/<song_id>/image-matches", methods=["GET"])
def get_image_matches(song_id: str):
    """Recompute per-occurrence image matches and unmatched topics live.

    ``session["image_suggestions"]``/``["image_topics"]`` are a one-time
    snapshot written at analyze time — they never reflect images uploaded
    to the (shared, cross-song) library afterward, so the Pictures screen
    would keep showing a word as "needs an image" (or miss its later
    occurrences entirely) forever after the user uploads one. This
    endpoint reruns the same matching functions generation itself already
    reruns fresh at export time (``plan.py``), against the *current*
    library, so the review screen and the generated .xsq never disagree.
    """
    from src.review.storage.assignments import load_session

    session = load_session(song_id) or {}
    words = session.get("words") or []
    library = load_image_library()
    ignored = _load_ignored_occurrences(song_id)
    overrides = _load_image_overrides(song_id)

    suggestions = suggest_images_for_words(words, library, ignored, overrides)
    topics = find_unmatched_topics(words, library)
    return jsonify({"suggestions": suggestions, "topics": topics}), 200
