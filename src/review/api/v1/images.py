"""GET/POST /api/v1/images — global image library for Pictures effects.

Unlike video import (song-scoped), images are a shared library: an image
uploaded once for a "topic" (e.g. a lyric word like "snowman") is available
to every song's Pictures placement and every future song's suggested-topics
matching, not just the song it was uploaded against.
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
