"""Tests for POST /api/v1/import-video.

Uses a real tiny synthetic MP4 (ffmpeg lavfi test source + sine audio)
rather than mocking ffmpeg, so the actual audio-extraction subprocess
call is exercised end-to-end.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _make_mp4_bytes(duration_secs: float = 6.0) -> bytes:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "fixture.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"testsrc=duration={duration_secs}:size=64x64:rate=10",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_secs}",
                "-c:v", "libx264", "-c:a", "aac", "-shortest",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )
        return out_path.read_bytes()


@pytest.fixture(scope="module")
def mp4_bytes():
    return _make_mp4_bytes()


class TestImportVideoNewSong:
    def test_returns_201_on_new_song(self, client, mp4_bytes):
        resp = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "clip.mp4")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201

    def test_song_has_video_path_ending_in_mp4(self, client, mp4_bytes):
        data = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "clip.mp4")},
            content_type="multipart/form-data",
        ).get_json()
        assert data["song"]["video_path"].endswith(".mp4")

    def test_title_falls_back_to_filename_stem(self, client, mp4_bytes):
        data = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "my_clip.mp4")},
            content_type="multipart/form-data",
        ).get_json()
        assert data["song"]["title"] == "my_clip"

    def test_duration_positive(self, client, mp4_bytes):
        data = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "clip.mp4")},
            content_type="multipart/form-data",
        ).get_json()
        assert data["song"]["duration_ms"] > 0


class TestImportVideoDedup:
    def test_repeat_import_returns_created_false(self, client, mp4_bytes):
        client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "clip.mp4")},
            content_type="multipart/form-data",
        )
        data = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "clip_again.mp4")},
            content_type="multipart/form-data",
        ).get_json()
        assert data["created"] is False

    def test_repeat_import_updates_video_path_to_latest_drop(self, client, mp4_bytes):
        # Same audio (dedups to the same song) but a different filename on
        # the second drop -- video_path must reflect the most recent upload,
        # not the first, so the export pipeline references the right file.
        client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "clip.mp4")},
            content_type="multipart/form-data",
        )
        data = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(mp4_bytes), "clip_again.mp4")},
            content_type="multipart/form-data",
        ).get_json()
        assert data["song"]["video_path"].endswith("clip_again.mp4")


class TestImportVideoErrors:
    def test_missing_file_returns_400(self, client):
        resp = client.post(
            "/api/v1/import-video",
            data={},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_file"

    def test_unsupported_format_returns_400(self, client):
        resp = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(b"fake"), "clip.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "unsupported_format"

    def test_junk_mp4_returns_400(self, client):
        resp = client.post(
            "/api/v1/import-video",
            data={"video": (io.BytesIO(b"not a real video" * 10), "junk.mp4")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "video_audio_extraction_failed"
