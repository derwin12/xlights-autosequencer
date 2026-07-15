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
