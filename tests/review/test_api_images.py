"""Tests for GET/POST /api/v1/images (global image library for Pictures effects)."""
from __future__ import annotations

import io


class TestUploadImage:
    def test_returns_201_on_new_image(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"gif-bytes"), "snowman.gif"), "tag": "snowman"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201

    def test_entry_has_tag_and_filename(self, client):
        data = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"gif-bytes"), "snowman.gif"), "tag": "snowman"},
            content_type="multipart/form-data",
        ).get_json()
        assert data["image"]["tag"] == "snowman"
        assert data["image"]["filename"] == "snowman.gif"

    def test_missing_file_returns_400(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"tag": "snowman"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_file"

    def test_missing_tag_returns_400(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"gif-bytes"), "snowman.gif")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_tag"

    def test_unsupported_extension_returns_400(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"not an image"), "notes.txt"), "tag": "notes"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "unsupported_format"


class TestListImages:
    def test_empty_library_returns_empty_list(self, client):
        resp = client.get("/api/v1/images")
        assert resp.status_code == 200
        assert resp.get_json()["images"] == []

    def test_uploaded_images_appear_in_list(self, client):
        client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"a"), "a.gif"), "tag": "snowman"},
            content_type="multipart/form-data",
        )
        client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"b"), "b.png"), "tag": "rocker"},
            content_type="multipart/form-data",
        )
        data = client.get("/api/v1/images").get_json()
        tags = {img["tag"] for img in data["images"]}
        assert tags == {"snowman", "rocker"}


class TestIgnoredImages:
    SONG = "cafe0123deadbeef"

    def test_empty_by_default(self, client):
        resp = client.get(f"/api/v1/songs/{self.SONG}/ignored-images")
        assert resp.status_code == 200
        assert resp.get_json()["words"] == []

    def test_ignore_adds_word_lowercased(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "Snowman"}
        )
        assert resp.status_code == 200
        assert resp.get_json()["words"] == ["snowman"]
        listed = client.get(f"/api/v1/songs/{self.SONG}/ignored-images").get_json()
        assert listed["words"] == ["snowman"]

    def test_ignore_is_idempotent(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman"})
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman"})
        listed = client.get(f"/api/v1/songs/{self.SONG}/ignored-images").get_json()
        assert listed["words"] == ["snowman"]

    def test_missing_word_returns_400(self, client):
        resp = client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_word"

    def test_restore_removes_word(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman"})
        resp = client.delete(f"/api/v1/songs/{self.SONG}/ignored-images/snowman")
        assert resp.status_code == 200
        listed = client.get(f"/api/v1/songs/{self.SONG}/ignored-images").get_json()
        assert listed["words"] == []

    def test_restore_unknown_word_returns_404(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/ignored-images/nothere")
        assert resp.status_code == 404

    def test_ignore_preserves_existing_session_fields(self, client):
        from src.review.storage.assignments import load_session, save_full_session

        save_full_session(self.SONG, {"sections": [{"label": "verse"}], "words": []})
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman"})
        session = load_session(self.SONG)
        assert session["sections"] == [{"label": "verse"}]
        assert session["ignored_image_words"] == ["snowman"]
