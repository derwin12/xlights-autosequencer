"""Tests for upload mode: POST /upload, GET /progress, GET /job-status."""
from __future__ import annotations

import io
import json
import threading
import time

import pytest

import src.review.server as server_mod
from src.review.server import AnalysisJob, create_app


@pytest.fixture(autouse=True)
def reset_job():
    """Ensure _current_job is cleared between tests."""
    server_mod._current_job = None
    yield
    server_mod._current_job = None


@pytest.fixture()
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


# ── Helpers ────────────────────────────────────────────────────────────────

def _mp3_bytes():
    """Minimal valid-ish bytes for upload (just needs to be non-empty with .mp3 name)."""
    return b"\xff\xfb\x90\x00" + b"\x00" * 100


def _upload(client, filename="song.mp3", extra_data=None):
    data = {"mp3": (io.BytesIO(_mp3_bytes()), filename)}
    if extra_data:
        data.update(extra_data)
    return client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
    )


# ── POST /upload ───────────────────────────────────────────────────────────

class TestUpload:
    def test_valid_mp3_returns_202(self, client, monkeypatch):
        # Prevent background thread from actually running analysis
        monkeypatch.setattr(
            "src.review.server._run_analysis",
            lambda app, job: None,
        )
        resp = _upload(client, filename="song.mp3")
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["status"] == "started"
        assert body["filename"] == "song.mp3"
        assert "total" in body

    def test_non_mp3_returns_400(self, client):
        resp = _upload(client, filename="song.wav")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_no_file_returns_400(self, client):
        resp = client.post("/upload", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_busy_returns_409(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr("src.review.server._run_analysis", lambda app, job: None)
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        # First upload
        _upload(client, filename="first.mp3")
        # Force job to appear running
        assert server_mod._current_job is not None
        server_mod._current_job.status = "running"

        # Second upload should 409
        resp = _upload(client, filename="second.mp3")
        assert resp.status_code == 409

    def test_job_is_set_after_upload(self, client, monkeypatch):
        monkeypatch.setattr("src.review.server._run_analysis", lambda app, job: None)
        _upload(client, filename="song.mp3")
        assert server_mod._current_job is not None

    def test_upload_creates_job_with_mp3_path(self, client, monkeypatch):
        captured = {}

        def fake_run(app, job):
            captured["mp3_path"] = job.mp3_path

        monkeypatch.setattr("src.review.server._run_analysis", fake_run)
        client.post(
            "/upload",
            data={"mp3": (io.BytesIO(_mp3_bytes()), "song.mp3")},
            content_type="multipart/form-data",
        )
        assert "song.mp3" in captured.get("mp3_path", "")


# ── GET /job-status ────────────────────────────────────────────────────────

class TestJobStatus:
    def test_idle_when_no_job(self, client):
        resp = client.get("/job-status")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "idle"

    def test_running_fields_when_job_active(self, client):
        job = AnalysisJob("fake.mp3")
        job.total = 5
        job.record_progress(0, 5, "librosa_beats", 120)
        server_mod._current_job = job

        resp = client.get("/job-status")
        body = resp.get_json()
        assert body["status"] == "running"
        assert body["total"] == 5
        assert body["events_count"] == 1
        assert body["result_path"] is None
        assert body["error"] is None

    def test_done_fields_when_job_complete(self, client):
        job = AnalysisJob("fake.mp3")
        job.status = "done"
        job.result_path = "/some/path.json"
        job.total = 3
        server_mod._current_job = job

        resp = client.get("/job-status")
        body = resp.get_json()
        assert body["status"] == "done"
        assert body["result_path"] == "/some/path.json"


# ── GET /progress ──────────────────────────────────────────────────────────

class TestProgress:
    def _read_sse(self, data: bytes) -> list[dict]:
        """Parse SSE stream bytes into list of event dicts."""
        events = []
        for line in data.decode().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_no_job_returns_error_event(self, client):
        resp = client.get("/progress")
        events = self._read_sse(resp.data)
        assert any("error" in e for e in events)

    def test_completed_job_replays_all_events_then_done(self, client):
        job = AnalysisJob("fake.mp3")
        job.total = 2
        job.record_progress(0, 2, "librosa_beats", 110)
        job.record_progress(1, 2, "librosa_hpss", 85)
        job.status = "done"
        job.result_path = "/some/out.json"
        server_mod._current_job = job

        resp = client.get("/progress")
        events = self._read_sse(resp.data)

        # Should have 2 progress events + 1 terminal done
        progress_events = [e for e in events if "name" in e]
        done_events = [e for e in events if e.get("done")]
        assert len(progress_events) == 2
        assert len(done_events) == 1
        assert done_events[0]["result_path"] == "/some/out.json"

    def test_error_job_sends_terminal_error(self, client):
        job = AnalysisJob("fake.mp3")
        job.status = "error"
        job.error_message = "All algorithms failed — no tracks produced"
        server_mod._current_job = job

        resp = client.get("/progress")
        events = self._read_sse(resp.data)
        error_events = [e for e in events if "error" in e]
        assert error_events
        assert "All algorithms failed" in error_events[-1]["error"]
