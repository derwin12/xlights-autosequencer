"""Tests for layout endpoints - T052.

GET returns the active layout: an uploaded override if one has been
posted via POST /api/v1/layout, else the repo-committed
layout/xlights_rgbeffects.xml. DELETE removes the uploaded override.
"""
from __future__ import annotations

import io


_MINIMAL_LAYOUT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<xrgb>
  <models type="rgb_effects">
    <model name="Test Prop 1" DisplayAs="Single Line" parm1="50" parm2="1" />
    <model name="Test Prop 2" DisplayAs="Single Line" parm1="30" parm2="1" />
  </models>
</xrgb>
"""


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
        assert "is_uploaded" in data

    def test_props_extracted_from_committed_file(self, client):
        data = client.get("/api/v1/layout").get_json()
        assert len(data["props"]) > 0


class TestUploadLayout:
    def test_upload_replaces_active_layout(self, client):
        committed = client.get("/api/v1/layout").get_json()

        resp = client.post(
            "/api/v1/layout",
            data={"rgbeffects": (io.BytesIO(_MINIMAL_LAYOUT_XML), "xlights_rgbeffects.xml")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        uploaded = resp.get_json()
        assert uploaded["is_uploaded"] is True
        assert len(uploaded["props"]) == 2
        assert {p["name"] for p in uploaded["props"]} == {"Test Prop 1", "Test Prop 2"}

        # GET now reflects the uploaded layout, not the committed one.
        data = client.get("/api/v1/layout").get_json()
        assert data["layout_id"] == uploaded["layout_id"]
        assert data["layout_id"] != committed["layout_id"]

        # Clean up so this test doesn't leak state into other tests.
        client.delete("/api/v1/layout")

    def test_upload_missing_file_returns_400(self, client):
        resp = client.post("/api/v1/layout", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_file"

    def test_upload_invalid_xml_returns_400(self, client):
        resp = client.post(
            "/api/v1/layout",
            data={"rgbeffects": (io.BytesIO(b"not xml"), "xlights_rgbeffects.xml")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_xml"
        client.delete("/api/v1/layout")

    def test_upload_no_models_returns_400(self, client):
        resp = client.post(
            "/api/v1/layout",
            data={"rgbeffects": (io.BytesIO(b"<xrgb></xrgb>"), "xlights_rgbeffects.xml")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "no_models"
        client.delete("/api/v1/layout")


class TestDeleteLayout:
    def test_delete_reverts_to_committed_layout(self, client):
        committed = client.get("/api/v1/layout").get_json()

        client.post(
            "/api/v1/layout",
            data={"rgbeffects": (io.BytesIO(_MINIMAL_LAYOUT_XML), "xlights_rgbeffects.xml")},
            content_type="multipart/form-data",
        )

        resp = client.delete("/api/v1/layout")
        assert resp.status_code == 200
        reverted = resp.get_json()
        assert reverted["is_uploaded"] is False
        assert reverted["layout_id"] == committed["layout_id"]

    def test_delete_without_upload_is_a_noop(self, client):
        resp = client.delete("/api/v1/layout")
        assert resp.status_code == 200
        assert resp.get_json()["is_uploaded"] is False
