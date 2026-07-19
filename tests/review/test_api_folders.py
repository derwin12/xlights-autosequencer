"""T091: Failing tests for folder CRUD endpoints."""
from __future__ import annotations

import io
import struct
import wave


def _make_unique_wav(seed: int = 0) -> bytes:
    # 6 seconds so the import-time validator (5 s minimum) accepts it.
    n_samples = 6 * 44100
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        samples = [(seed * 100 + i) % 32767 for i in range(n_samples)]
        w.writeframes(struct.pack(f"<{n_samples}h", *samples))
    return buf.getvalue()


def _import_song(client, wav: bytes, filename: str = "test.wav", folder_id: str | None = None):
    data: dict = {"audio": (io.BytesIO(wav), filename)}
    if folder_id:
        data["folder_id"] = folder_id
    return client.post(
        "/api/v1/import", data=data, content_type="multipart/form-data"
    ).get_json()


class TestCreateFolder:
    def test_create_folder_returns_201(self, client):
        resp = client.post("/api/v1/folders", json={"name": "Halloween 2026"})
        assert resp.status_code == 201

    def test_create_folder_returns_folder_id(self, client):
        data = client.post("/api/v1/folders", json={"name": "Halloween 2026"}).get_json()
        assert "folder_id" in data
        assert data["folder_id"]

    def test_create_folder_returns_name(self, client):
        data = client.post("/api/v1/folders", json={"name": "Halloween 2026"}).get_json()
        assert data["name"] == "Halloween 2026"

    def test_create_folder_appears_in_library(self, client):
        resp = client.post("/api/v1/folders", json={"name": "Show 1"})
        folder_id = resp.get_json()["folder_id"]
        lib = client.get("/api/v1/library").get_json()
        assert any(f["folder_id"] == folder_id for f in lib["folders"])

    def test_create_folder_empty_name_returns_400(self, client):
        resp = client.post("/api/v1/folders", json={"name": ""})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_name"

    def test_create_folder_whitespace_name_returns_400(self, client):
        resp = client.post("/api/v1/folders", json={"name": "   "})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_name"

    def test_create_folder_name_too_long_returns_400(self, client):
        resp = client.post("/api/v1/folders", json={"name": "x" * 65})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_name"

    def test_create_folder_duplicate_name_returns_409(self, client):
        client.post("/api/v1/folders", json={"name": "Show A"})
        resp = client.post("/api/v1/folders", json={"name": "Show A"})
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "folder_name_taken"

    def test_create_folder_duplicate_name_case_insensitive(self, client):
        client.post("/api/v1/folders", json={"name": "Show A"})
        resp = client.post("/api/v1/folders", json={"name": "show a"})
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "folder_name_taken"


class TestPatchFolder:
    def test_rename_folder_returns_200(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "Old Name"}).get_json()["folder_id"]
        resp = client.patch(f"/api/v1/folders/{folder_id}", json={"name": "New Name"})
        assert resp.status_code == 200

    def test_rename_folder_updates_name(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "Old Name"}).get_json()["folder_id"]
        data = client.patch(f"/api/v1/folders/{folder_id}", json={"name": "New Name"}).get_json()
        assert data["name"] == "New Name"

    def test_patch_nonexistent_folder_returns_404(self, client):
        resp = client.patch("/api/v1/folders/nonexistent_id", json={"name": "X"})
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "folder_not_found"

    def test_patch_unfiled_returns_400(self, client):
        resp = client.patch("/api/v1/folders/unfiled", json={"name": "Renamed"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "reserved_folder"

    def test_patch_folder_collapsed_field(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "A"}).get_json()["folder_id"]
        data = client.patch(f"/api/v1/folders/{folder_id}", json={"collapsed": True}).get_json()
        assert data["collapsed"] is True

    def test_patch_folder_partial_update(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "A"}).get_json()["folder_id"]
        data = client.patch(f"/api/v1/folders/{folder_id}", json={"collapsed": True}).get_json()
        assert data["name"] == "A"
        assert data["collapsed"] is True


class TestDeleteFolder:
    def test_delete_folder_returns_204(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "To Delete"}).get_json()["folder_id"]
        resp = client.delete(f"/api/v1/folders/{folder_id}")
        assert resp.status_code == 204

    def test_delete_folder_removed_from_library(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "To Delete"}).get_json()["folder_id"]
        client.delete(f"/api/v1/folders/{folder_id}")
        lib = client.get("/api/v1/library").get_json()
        assert not any(f["folder_id"] == folder_id for f in lib["folders"])

    def test_delete_folder_moves_songs_to_unfiled(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "Custom"}).get_json()["folder_id"]
        song_data = _import_song(client, _make_unique_wav(1), "s1.wav", folder_id=folder_id)
        song_id = song_data["song"]["song_id"]

        client.delete(f"/api/v1/folders/{folder_id}")

        lib = client.get("/api/v1/library").get_json()
        song = next(s for s in lib["songs"] if s["song_id"] == song_id)
        assert song["folder_id"] == "unfiled"

    def test_delete_nonexistent_folder_returns_404(self, client):
        resp = client.delete("/api/v1/folders/nonexistent")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "folder_not_found"

    def test_delete_unfiled_returns_400(self, client):
        resp = client.delete("/api/v1/folders/unfiled")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "reserved_folder"


class TestPatchSongFolder:
    def test_move_song_to_folder_returns_200(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "Show"}).get_json()["folder_id"]
        song_data = _import_song(client, _make_unique_wav(2))
        song_id = song_data["song"]["song_id"]
        resp = client.patch(f"/api/v1/songs/{song_id}/folder", json={"folder_id": folder_id})
        assert resp.status_code == 200

    def test_move_song_updates_folder_id(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "Show"}).get_json()["folder_id"]
        song_data = _import_song(client, _make_unique_wav(3))
        song_id = song_data["song"]["song_id"]
        data = client.patch(f"/api/v1/songs/{song_id}/folder", json={"folder_id": folder_id}).get_json()
        assert data["folder_id"] == folder_id

    def test_move_song_reflected_in_library(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "Show"}).get_json()["folder_id"]
        song_data = _import_song(client, _make_unique_wav(4))
        song_id = song_data["song"]["song_id"]
        client.patch(f"/api/v1/songs/{song_id}/folder", json={"folder_id": folder_id})
        lib = client.get("/api/v1/library").get_json()
        song = next(s for s in lib["songs"] if s["song_id"] == song_id)
        assert song["folder_id"] == folder_id

    def test_move_nonexistent_song_returns_404(self, client):
        folder_id = client.post("/api/v1/folders", json={"name": "Show"}).get_json()["folder_id"]
        resp = client.patch("/api/v1/songs/deadbeef/folder", json={"folder_id": folder_id})
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "song_not_found"

    def test_move_song_to_nonexistent_folder_returns_404(self, client):
        song_data = _import_song(client, _make_unique_wav(5))
        song_id = song_data["song"]["song_id"]
        resp = client.patch(f"/api/v1/songs/{song_id}/folder", json={"folder_id": "nonexistent"})
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "folder_not_found"


class TestPatchSongMetadata:
    def test_update_title_returns_200(self, client):
        song_data = _import_song(client, _make_unique_wav(6))
        song_id = song_data["song"]["song_id"]
        resp = client.patch(f"/api/v1/songs/{song_id}/metadata", json={"title": "With a Little Help From My Friends"})
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "With a Little Help From My Friends"

    def test_update_artist_reflected_in_library(self, client):
        song_data = _import_song(client, _make_unique_wav(7))
        song_id = song_data["song"]["song_id"]
        client.patch(f"/api/v1/songs/{song_id}/metadata", json={"artist": "Wet Wet Wet"})
        lib = client.get("/api/v1/library").get_json()
        song = next(s for s in lib["songs"] if s["song_id"] == song_id)
        assert song["artist"] == "Wet Wet Wet"

    def test_update_title_and_artist_together(self, client):
        song_data = _import_song(client, _make_unique_wav(8))
        song_id = song_data["song"]["song_id"]
        resp = client.patch(
            f"/api/v1/songs/{song_id}/metadata",
            json={"title": "Corrected Title", "artist": "Corrected Artist"},
        )
        data = resp.get_json()
        assert data["title"] == "Corrected Title"
        assert data["artist"] == "Corrected Artist"

    def test_empty_title_returns_400(self, client):
        song_data = _import_song(client, _make_unique_wav(9))
        song_id = song_data["song"]["song_id"]
        resp = client.patch(f"/api/v1/songs/{song_id}/metadata", json={"title": "   "})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_title"

    def test_empty_artist_returns_400(self, client):
        song_data = _import_song(client, _make_unique_wav(10))
        song_id = song_data["song"]["song_id"]
        resp = client.patch(f"/api/v1/songs/{song_id}/metadata", json={"artist": ""})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_artist"

    def test_unknown_song_returns_404(self, client):
        resp = client.patch("/api/v1/songs/deadbeef/metadata", json={"title": "X"})
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "song_not_found"
