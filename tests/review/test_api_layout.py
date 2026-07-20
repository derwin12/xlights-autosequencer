"""Tests for layout endpoints — T052.

The layout is a fixed file committed to the repo at
layout/xlights_rgbeffects.xml — there is no per-session upload/replace.
"""
from __future__ import annotations


class TestGetLayout:
    def test_returns_200(self, client):
        resp = client.get("/api/v1/layout")
        assert resp.status_code == 200

    def test_layout_fields_present(self, client):
        data = client.get("/api/v1/layout").get_json()
        assert "layout_id" in data
        assert "display_name" in data
        assert "props" in data
        assert "total_pixels" in data
        assert "xml_path" in data

    def test_props_extracted_from_committed_file(self, client):
        data = client.get("/api/v1/layout").get_json()
        assert len(data["props"]) > 0

    def test_no_upload_endpoint(self, client):
        resp = client.post("/api/v1/layout")
        assert resp.status_code == 405
