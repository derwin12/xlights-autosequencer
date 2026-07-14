"""POST /api/v1/import-video — import a video file as a song's source.

The video's audio track drives the sequence (same analysis/generation
pipeline as an MP3 import); the video itself is stored so it can be placed
on a matrix via the xLights Video effect. Dedup and song schema mirror
``import_.py`` — song identity is the SHA-256 of the *extracted audio*,
so a video and an MP3 of the same song would (correctly) dedup together.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import jsonify, request

from . import api_v1
from src.review.api.v1._audio_validation import AudioValidationError, validate_audio
from src.review.api.v1.import_ import _duration_ms, _now_iso, _read_id3
from src.review.storage.library import load_library, save_library
from src.review.storage.paths import library_root

_ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_MAX_BYTES = 1024 * 1024 * 1024  # 1 GB


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("ffmpeg not found. Install via: brew install ffmpeg")


class VideoImportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _extract_audio(video_path: Path) -> bytes:
    """Extract the audio track from ``video_path`` as MP3 bytes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_out = Path(tmp_dir) / "audio.mp3"
        try:
            subprocess.run(
                [_find_ffmpeg(), "-y", "-i", str(video_path), "-vn", "-q:a", "2", str(audio_out)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise VideoImportError(
                "video_audio_extraction_failed",
                f"Could not extract audio from video: {exc.stderr.decode(errors='replace')[-300:]}",
            ) from exc
        except FileNotFoundError as exc:
            raise VideoImportError("ffmpeg_not_found", str(exc)) from exc
        return audio_out.read_bytes()


@api_v1.route("/import-video", methods=["POST"])
def import_video():
    if "video" not in request.files:
        return jsonify({"error": {"code": "missing_file", "message": "No video file provided"}}), 400

    f = request.files["video"]
    filename = f.filename or ""
    ext = Path(filename).suffix.lower()

    if ext not in _ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({"error": {"code": "unsupported_format",
                                   "message": f"Unsupported video type: {ext}"}}), 400

    video_bytes = f.read()
    if len(video_bytes) > _MAX_BYTES:
        return jsonify({"error": {"code": "video_too_large",
                                   "message": "File exceeds 1 GB limit"}}), 413

    folder_id = request.form.get("folder_id") or "unfiled"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_video_path = Path(tmp_dir) / filename
        tmp_video_path.write_bytes(video_bytes)

        try:
            audio_bytes = _extract_audio(tmp_video_path)
        except VideoImportError as exc:
            return jsonify({"error": {"code": exc.code, "message": exc.message}}), 400

        song_id = hashlib.sha256(audio_bytes).hexdigest()[:16]

        audio_dir = library_root() / "songs" / song_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        stored_audio_path = audio_dir / (Path(filename).stem + ".mp3")
        if not stored_audio_path.exists():
            tmp_audio_out = stored_audio_path.with_suffix(".tmp")
            tmp_audio_out.write_bytes(audio_bytes)
            os.replace(str(tmp_audio_out), str(stored_audio_path))

        video_dir = library_root() / "songs" / song_id / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        stored_video_path = video_dir / filename
        if not stored_video_path.exists():
            tmp_video_out = stored_video_path.with_suffix(stored_video_path.suffix + ".tmp")
            shutil.copy2(tmp_video_path, tmp_video_out)
            os.replace(str(tmp_video_out), str(stored_video_path))

        canonical_audio_path = str(stored_audio_path)
        video_path = str(stored_video_path)

        lib = load_library()
        existing = next((s for s in lib["songs"] if s["song_id"] == song_id), None)

        if existing is None:
            try:
                validate_audio(canonical_audio_path)
            except AudioValidationError as exc:
                try:
                    stored_audio_path.unlink()
                    stored_audio_path.parent.rmdir()
                    stored_video_path.unlink()
                    stored_video_path.parent.rmdir()
                    stored_audio_path.parent.parent.rmdir()
                except OSError:
                    pass
                return jsonify({"error": {"code": exc.code, "message": exc.message}}), 400

        if existing is not None:
            if canonical_audio_path not in existing["source_paths"]:
                existing["source_paths"].insert(0, canonical_audio_path)
            # This route requires a video file (see the missing_file check
            # above), so the just-stored video is always the freshest one --
            # always adopt it, even on dedup, so the export pipeline never
            # references a stale video from an earlier drop.
            existing["video_path"] = video_path
            save_library(lib)
            return jsonify({"created": False, "source_path_added": True, "song": existing}), 200

        duration_ms = _duration_ms(audio_bytes, ".mp3")
        id3_title, id3_artist = _read_id3(audio_bytes)
        title = id3_title or Path(filename).stem

        song = {
            "song_id": song_id,
            "title": title,
            "artist": id3_artist,
            "duration_ms": duration_ms,
            "bpm": None,
            "key": None,
            "time_signature": None,
            "status": "draft",
            "source_paths": [canonical_audio_path],
            "video_path": video_path,
            "folder_id": folder_id,
            "imported_at": _now_iso(),
            "last_opened_at": None,
        }

        lib["songs"].append(song)
        save_library(lib)

        return jsonify({"created": True, "song": song}), 201
