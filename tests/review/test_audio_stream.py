"""Tests for GET /audio/<song_id> — T056."""
from __future__ import annotations

import io
import struct
import wave
import pytest


def _make_wav_bytes(duration_secs: float = 0.5) -> bytes:
    sample_rate = 22050
    n_samples = int(duration_secs * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
    return buf.getvalue()


class TestAudioStream:
    def test_unknown_song_returns_404(self, client):
        resp = client.get("/audio/deadbeef00000000")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body is not None
        assert body["error"]["code"] == "source_file_missing"

    def test_streams_bytes_with_accept_ranges(self, client, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)

        song_id = client.post(
            "/api/v1/import",
            data={
                "audio": (io.BytesIO(wav_bytes), "test.wav"),
                "source_path": str(wav_path),
            },
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]

        resp = client.get(f"/audio/{song_id}")
        assert resp.status_code == 200
        assert "bytes" in resp.headers.get("Accept-Ranges", "")

    def test_partial_content_206(self, client, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)

        song_id = client.post(
            "/api/v1/import",
            data={
                "audio": (io.BytesIO(wav_bytes), "test.wav"),
                "source_path": str(wav_path),
            },
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]

        resp = client.get(
            f"/audio/{song_id}",
            headers={"Range": "bytes=0-99"},
        )
        assert resp.status_code == 206

    # Note: previously this file had `test_no_source_path_returns_404` and
    # `test_missing_file_returns_404`, both asserting 404 from /audio/<id>
    # for songs that had no usable source. Those scenarios are no longer
    # reachable: /api/v1/import always persists the uploaded bytes to the
    # state directory (see src/review/api/v1/import_.py), so every imported
    # song has a guaranteed-readable source. The tests' setup paths produce
    # streamable audio (200) rather than 404. Removed as obsolete.
