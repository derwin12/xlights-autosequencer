"""POST /api/v1/import/by-path -- import a local audio/video file by absolute
path.

Desktop-app-only counterpart to /api/v1/import and /api/v1/import-video:
Tauri's native open-file dialog and drag-drop listener (src/lib/nativeDialog.ts)
give real filesystem paths, not uploadable File blobs, so there's no bytes to
multipart-upload -- the backend reads the file directly off disk instead.
Dedup/validation/song-schema logic is identical to the upload routes (shared
via import_.finalize_audio_import / import_video.finalize_video_import).
"""
from __future__ import annotations

from pathlib import Path

from flask import jsonify, request

from . import api_v1
from src.review.api.v1.import_ import _ALLOWED_EXTENSIONS, _MAX_BYTES as _AUDIO_MAX_BYTES, finalize_audio_import
from src.review.api.v1.import_video import (
    _ALLOWED_VIDEO_EXTENSIONS, _MAX_BYTES as _VIDEO_MAX_BYTES, finalize_video_import,
)


@api_v1.route("/import/by-path", methods=["POST"])
def import_by_path():
    body = request.get_json(silent=True) or {}
    path = body.get("path")
    if not path:
        return jsonify({"error": {"code": "missing_path", "message": "No path provided"}}), 400

    source = Path(path)
    if not source.is_file():
        return jsonify({"error": {"code": "file_not_found",
                                   "message": f"File not found: {path}"}}), 404

    ext = source.suffix.lower()
    folder_id = body.get("folder_id") or "unfiled"
    size = source.stat().st_size

    if ext in _ALLOWED_EXTENSIONS:
        if size > _AUDIO_MAX_BYTES:
            return jsonify({"error": {"code": "audio_too_large",
                                       "message": "File exceeds 200 MB limit"}}), 413
        audio_bytes = source.read_bytes()
        response_body, status = finalize_audio_import(
            audio_bytes, source.name, ext, folder_id, extra_source_path=str(source),
        )
        return jsonify(response_body), status

    if ext in _ALLOWED_VIDEO_EXTENSIONS:
        if size > _VIDEO_MAX_BYTES:
            return jsonify({"error": {"code": "video_too_large",
                                       "message": "File exceeds 1 GB limit"}}), 413
        response_body, status = finalize_video_import(source, source.name, folder_id)
        return jsonify(response_body), status

    return jsonify({"error": {"code": "unsupported_format",
                               "message": f"Unsupported file type: {ext}"}}), 400
