"""Tests for POST /api/v1/import/by-path — desktop-app native drag-drop/dialog import."""
from __future__ import annotations

from pathlib import Path

from tests.review.test_api_import import _make_wav_bytes


class TestImportByPathNewSong:
    def test_returns_201_on_new_song(self, client, tmp_path: Path):
        wav_path = tmp_path / "song.wav"
        wav_path.write_bytes(_make_wav_bytes())

        resp = client.post("/api/v1/import/by-path", json={"path": str(wav_path)})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["created"] is True
        song = data["song"]
        assert "song_id" in song
        assert song["status"] == "draft"
        assert str(wav_path) in song["source_paths"]

    def test_folder_id_applied(self, client, tmp_path: Path):
        wav_path = tmp_path / "song.wav"
        wav_path.write_bytes(_make_wav_bytes())

        resp = client.post(
            "/api/v1/import/by-path",
            json={"path": str(wav_path), "folder_id": "christmas"},
        )
        assert resp.get_json()["song"]["folder_id"] == "christmas"

    def test_missing_path_returns_400(self, client):
        resp = client.post("/api/v1/import/by-path", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_path"

    def test_nonexistent_file_returns_404(self, client, tmp_path: Path):
        resp = client.post(
            "/api/v1/import/by-path",
            json={"path": str(tmp_path / "does-not-exist.wav")},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "file_not_found"

    def test_unsupported_extension_returns_400(self, client, tmp_path: Path):
        bogus = tmp_path / "notes.txt"
        bogus.write_text("hello")
        resp = client.post("/api/v1/import/by-path", json={"path": str(bogus)})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "unsupported_format"


class TestImportByPathDedup:
    def test_same_audio_content_dedups(self, client, tmp_path: Path):
        wav_bytes = _make_wav_bytes()
        first_path = tmp_path / "first.wav"
        first_path.write_bytes(wav_bytes)
        second_path = tmp_path / "second.wav"
        second_path.write_bytes(wav_bytes)

        first = client.post("/api/v1/import/by-path", json={"path": str(first_path)}).get_json()
        second = client.post("/api/v1/import/by-path", json={"path": str(second_path)}).get_json()

        assert first["created"] is True
        assert second["created"] is False
        assert second["song"]["song_id"] == first["song"]["song_id"]
        assert str(second_path) in second["song"]["source_paths"]

    def test_dedups_with_multipart_upload(self, client, tmp_path: Path):
        """A path-import and a multipart-upload of the same audio must dedup
        to the same song_id -- both routes share finalize_audio_import."""
        import io
        wav_bytes = _make_wav_bytes()

        uploaded = client.post(
            "/api/v1/import",
            data={"audio": (io.BytesIO(wav_bytes), "test.wav")},
            content_type="multipart/form-data",
        ).get_json()

        path = tmp_path / "test.wav"
        path.write_bytes(wav_bytes)
        by_path = client.post("/api/v1/import/by-path", json={"path": str(path)}).get_json()

        assert by_path["created"] is False
        assert by_path["song"]["song_id"] == uploaded["song"]["song_id"]
