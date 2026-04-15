"""Integration tests for the Song Workspace Shell (spec 046)."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _tmp_xlight(tmp_path):
    xlight_dir = tmp_path / ".xlight"
    xlight_dir.mkdir()
    (xlight_dir / "custom_themes").mkdir()

    analysis_dir = xlight_dir / "songs"
    analysis_dir.mkdir()
    analysis_file = analysis_dir / "abc_hierarchy.json"
    analysis_file.write_text(json.dumps({
        "schema_version": "2.0.0",
        "validation": {"overall_score": 0.8},
        "song": {"title": "Flow Song", "artist": "Flow"},
    }))
    source_file = analysis_dir / "abc.mp3"
    source_file.write_bytes(b"\xff\xfb\x90\x00")  # minimal MP3 header stub

    library_path = xlight_dir / "library.json"
    library_path.write_text(json.dumps({
        "version": "1.0",
        "entries": [{
            "source_hash": "abc123",
            "source_file": str(source_file),
            "filename": "abc.mp3",
            "analysis_path": str(analysis_file),
            "duration_ms": 180000,
            "estimated_tempo_bpm": 120.0,
            "track_count": 10,
            "stem_separation": True,
            "analyzed_at": 1711843200000,
        }],
    }))
    return xlight_dir, library_path


@pytest.fixture
def app(_tmp_xlight):
    xlight_dir, library_path = _tmp_xlight
    with patch("src.library.DEFAULT_LIBRARY_PATH", library_path):
        from src.review.server import create_app
        app = create_app(analysis_path=None, audio_path=None)
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


# T022 — workspace HTML references the Analysis panel
class TestWorkspaceMarkupSmoke:
    def test_workspace_markup_has_analysis_panel(self, client):
        resp = client.get("/song/abc123")
        assert resp.status_code == 200
        assert b"panel-analysis" in resp.data
        # Workspace HTML loads the factory script lazily via JS, but app.js
        # must be reachable by the browser.
        app_js = client.get("/app.js")
        assert app_js.status_code == 200

    def test_workspace_has_four_tab_buttons_in_order(self, client):
        resp = client.get("/song/abc123")
        body = resp.data.decode("utf-8")
        # Find each tab in declared order.
        i_a = body.find('data-tab="analysis"')
        i_b = body.find('data-tab="brief"')
        i_p = body.find('data-tab="preview"')
        i_g = body.find('data-tab="generate"')
        assert 0 < i_a < i_b < i_p < i_g


# T039 — seeded running job shows up in history payload for workspace mount
class TestInFlightHistoryReattach:
    def test_running_job_visible_in_history(self, client):
        from src.review.generate_routes import GenerationJob, _jobs
        _jobs.clear()
        _jobs["running-1"] = GenerationJob(
            job_id="running-1",
            source_hash="abc123",
            status="running",
            output_path=None,
            error_message=None,
            genre="pop",
            occasion="general",
            transition_mode="subtle",
            created_at=time.time(),
        )
        resp = client.get("/generate/abc123/history")
        assert resp.status_code == 200
        data = resp.get_json()
        running = [j for j in data["jobs"] if j["status"] == "running"]
        assert len(running) == 1
        assert running[0]["job_id"] == "running-1"


# T038 — Full generate flow end-to-end (POST -> status -> download).
#
# The full pipeline runs in a background thread that calls generate_sequence()
# (which requires a real layout and audio). We exercise the orchestration path
# by stubbing generate_sequence so the job transitions running -> complete.
class TestFullGenerationFlow:
    def test_generate_status_download_cycle(self, client, tmp_path, _tmp_xlight):
        from src.review.generate_routes import _jobs
        _jobs.clear()

        # Fake an .xsq output file that generate_sequence would produce.
        fake_xsq = tmp_path / "out.xsq"
        fake_xsq.write_bytes(b"<xsq/>")

        # Stub the layout path so start_generation() accepts the POST.
        layout_xml = tmp_path / "layout.xml"
        layout_xml.write_bytes(b"<xml/>")

        with patch("src.review.generate_routes.get_layout_path", return_value=layout_xml), \
             patch("src.review.generate_routes.generate_sequence", return_value=fake_xsq) \
                 if False else patch("src.generator.plan.generate_sequence", return_value=fake_xsq):

            # 1. Load the workspace shell.
            resp = client.get("/song/abc123")
            assert resp.status_code == 200

            # 2. POST /generate/<hash> — returns job_id + 202.
            resp = client.post("/generate/abc123", json={})
            assert resp.status_code == 202
            job_id = resp.get_json()["job_id"]

            # 3. Poll status until complete (thread is fast w/ stub).
            deadline = time.time() + 5.0
            status = "pending"
            while time.time() < deadline:
                s = client.get(f"/generate/abc123/status?job_id={job_id}")
                status = s.get_json()["status"]
                if status in ("complete", "failed"):
                    break
                time.sleep(0.05)
            assert status == "complete"

            # 4. Download the artifact.
            d = client.get(f"/generate/abc123/download/{job_id}")
            assert d.status_code == 200
            assert d.data == b"<xsq/>"
