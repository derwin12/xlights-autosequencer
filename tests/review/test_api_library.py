"""Tests for GET /api/v1/library — T044."""
from __future__ import annotations

import io
import struct
import wave
import pytest


def _make_wav_bytes(duration_secs: float = 1.0, sample_rate: int = 44100) -> bytes:
    n_samples = int(duration_secs * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
    return buf.getvalue()


def _import_song(client, wav: bytes, filename: str = "test.wav", source_path: str | None = None):
    data = {"audio": (io.BytesIO(wav), filename)}
    if source_path:
        data["source_path"] = source_path
    return client.post("/api/v1/import", data=data, content_type="multipart/form-data").get_json()


class TestLibraryEmpty:
    def test_returns_200_empty(self, client):
        resp = client.get("/api/v1/library")
        assert resp.status_code == 200

    def test_empty_songs_list(self, client):
        data = client.get("/api/v1/library").get_json()
        assert data["songs"] == []

    def test_unfiled_folder_always_present(self, client):
        data = client.get("/api/v1/library").get_json()
        assert any(f["folder_id"] == "unfiled" for f in data["folders"])

    def test_folders_present(self, client):
        data = client.get("/api/v1/library").get_json()
        assert isinstance(data["folders"], list)
        assert len(data["folders"]) >= 1


class TestLibraryWithSong:
    def test_song_appears_in_library(self, client):
        wav = _make_wav_bytes()
        _import_song(client, wav)
        data = client.get("/api/v1/library").get_json()
        assert len(data["songs"]) == 1

    def test_source_exists_true_when_path_set(self, client, tmp_path):
        # Create a real file on disk
        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)
        _import_song(client, wav_bytes, source_path=str(wav_path))
        data = client.get("/api/v1/library").get_json()
        song = data["songs"][0]
        assert song["source_exists"] is True

    # Note: previously this file had `test_source_exists_false_when_path_missing`
    # and `test_source_exists_false_when_no_paths`. Both scenarios are
    # unreachable now — /api/v1/import always persists the uploaded bytes to
    # the state directory (see src/review/api/v1/import_.py), so every
    # imported song always has source_exists=True against the persisted copy
    # regardless of the original source_path argument. Removed as obsolete.

    def test_song_fields_present(self, client):
        wav = _make_wav_bytes()
        _import_song(client, wav)
        data = client.get("/api/v1/library").get_json()
        song = data["songs"][0]
        for field in ("song_id", "title", "status", "folder_id", "imported_at"):
            assert field in song, f"Missing field: {field}"
