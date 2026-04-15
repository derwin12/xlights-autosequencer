"""Unit tests for src/review/generate_routes.py."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(layout_path: str | None = "/fake/layout.xml"):
    """Create a minimal Flask test app with the generate blueprint registered."""
    from flask import Flask
    from src.review.generate_routes import generate_bp, _jobs
    _jobs.clear()

    app = Flask(__name__)
    app.register_blueprint(generate_bp, url_prefix="/generate")
    app.config["TESTING"] = True
    return app


def _make_entry(source_hash="abc123", analysis_exists=True):
    """Return a mock LibraryEntry."""
    entry = MagicMock()
    entry.source_hash = source_hash
    entry.source_file = "/fake/song.mp3"
    entry.analysis_path = "/fake/song_hierarchy.json"
    entry.title = "Test Song"
    entry.artist = "Test Artist"
    # analysis_exists is checked via Path(entry.analysis_path).exists()
    return entry


# ---------------------------------------------------------------------------
# T005: GenerationJob dataclass + _sanitize_error()
# ---------------------------------------------------------------------------

class TestGenerationJob:
    def test_all_status_values(self):
        from src.review.generate_routes import GenerationJob
        import uuid
        job = GenerationJob(
            job_id=str(uuid.uuid4()),
            source_hash="abc",
            status="pending",
            output_path=None,
            error_message=None,
            genre="pop",
            occasion="general",
            transition_mode="subtle",
            created_at=time.time(),
        )
        assert job.status == "pending"
        job.status = "running"
        assert job.status == "running"
        job.status = "complete"
        assert job.status == "complete"
        job.status = "failed"
        assert job.status == "failed"

    def test_sanitize_error_file_not_found(self):
        from src.review.generate_routes import _sanitize_error
        err = FileNotFoundError("layout.xml not found")
        result = _sanitize_error(err)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "traceback" not in result.lower()
        assert "Traceback" not in result

    def test_sanitize_error_value_error(self):
        from src.review.generate_routes import _sanitize_error
        err = ValueError("bad config value")
        result = _sanitize_error(err)
        assert isinstance(result, str)
        assert "bad config value" in result

    def test_sanitize_error_generic(self):
        from src.review.generate_routes import _sanitize_error
        err = RuntimeError("something exploded")
        result = _sanitize_error(err)
        assert isinstance(result, str)
        assert "traceback" not in result.lower()
        # Should be a user-friendly fallback, not a raw traceback
        assert "Traceback" not in result


# ---------------------------------------------------------------------------
# T006: POST /generate/<source_hash>
# ---------------------------------------------------------------------------

class TestStartGeneration:
    def test_404_when_song_not_in_library(self):
        app = _make_app()
        with app.test_client() as client:
            with patch("src.review.generate_routes.Library") as MockLib:
                MockLib.return_value.find_by_hash.return_value = None
                resp = client.post("/generate/unknownhash",
                                   json={"genre": "pop", "occasion": "general", "transition_mode": "subtle"})
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_400_when_analysis_missing(self, tmp_path):
        app = _make_app()
        entry = _make_entry()
        entry.analysis_path = str(tmp_path / "missing_hierarchy.json")
        with app.test_client() as client:
            with patch("src.review.generate_routes.Library") as MockLib, \
                 patch("src.review.generate_routes.get_layout_path", return_value=Path("/fake/layout.xml")):
                MockLib.return_value.find_by_hash.return_value = entry
                resp = client.post("/generate/abc123", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "analyz" in data["error"].lower()

    def test_409_when_no_layout_configured(self, tmp_path):
        app = _make_app()
        entry = _make_entry()
        analysis_file = tmp_path / "song_hierarchy.json"
        analysis_file.write_text("{}")
        entry.analysis_path = str(analysis_file)
        with app.test_client() as client:
            with patch("src.review.generate_routes.Library") as MockLib, \
                 patch("src.review.generate_routes.get_layout_path", return_value=None):
                MockLib.return_value.find_by_hash.return_value = entry
                resp = client.post("/generate/abc123", json={})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data.get("setup_required") is True

    def test_202_with_job_id_when_all_ok(self, tmp_path):
        app = _make_app()
        entry = _make_entry()
        analysis_file = tmp_path / "song_hierarchy.json"
        analysis_file.write_text("{}")
        entry.analysis_path = str(analysis_file)
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlightsproject/>")
        with app.test_client() as client:
            with patch("src.review.generate_routes.Library") as MockLib, \
                 patch("src.review.generate_routes.get_layout_path", return_value=layout_file), \
                 patch("src.review.generate_routes._run_generation"):
                MockLib.return_value.find_by_hash.return_value = entry
                resp = client.post("/generate/abc123",
                                   json={"genre": "rock", "occasion": "christmas", "transition_mode": "none"})
        assert resp.status_code == 202
        data = resp.get_json()
        assert "job_id" in data
        assert data["status"] == "pending"


# ---------------------------------------------------------------------------
# T007: GET /generate/<source_hash>/status
# ---------------------------------------------------------------------------

class TestJobStatus:
    def _insert_job(self, status="pending", source_hash="abc123", error=None, output_path=None):
        from src.review.generate_routes import GenerationJob, _jobs
        import uuid
        job_id = str(uuid.uuid4())
        job = GenerationJob(
            job_id=job_id,
            source_hash=source_hash,
            status=status,
            output_path=output_path,
            error_message=error,
            genre="pop",
            occasion="general",
            transition_mode="subtle",
            created_at=time.time(),
        )
        _jobs[job_id] = job
        return job_id

    def test_404_for_unknown_job_id(self):
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/generate/abc123/status?job_id=nonexistent")
        assert resp.status_code == 404

    def test_returns_pending_status(self):
        app = _make_app()
        job_id = self._insert_job(status="pending")
        with app.test_client() as client:
            resp = client.get(f"/generate/abc123/status?job_id={job_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "pending"

    def test_returns_running_status(self):
        app = _make_app()
        job_id = self._insert_job(status="running")
        with app.test_client() as client:
            resp = client.get(f"/generate/abc123/status?job_id={job_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "running"

    def test_returns_complete_status(self):
        app = _make_app()
        job_id = self._insert_job(status="complete")
        with app.test_client() as client:
            resp = client.get(f"/generate/abc123/status?job_id={job_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "complete"

    def test_error_field_present_on_failed_jobs(self):
        app = _make_app()
        job_id = self._insert_job(status="failed", error="Layout not found")
        with app.test_client() as client:
            resp = client.get(f"/generate/abc123/status?job_id={job_id}")
        data = resp.get_json()
        assert data["status"] == "failed"
        assert data["error"] == "Layout not found"


# ---------------------------------------------------------------------------
# T008: GET /generate/<source_hash>/download/<job_id>
# ---------------------------------------------------------------------------

class TestDownloadSequence:
    def _insert_complete_job(self, output_path: Path | None = None):
        from src.review.generate_routes import GenerationJob, _jobs
        import uuid
        job_id = str(uuid.uuid4())
        job = GenerationJob(
            job_id=job_id,
            source_hash="abc123",
            status="complete",
            output_path=output_path,
            error_message=None,
            genre="pop",
            occasion="general",
            transition_mode="subtle",
            created_at=time.time(),
        )
        _jobs[job_id] = job
        return job_id

    def test_404_when_job_not_found(self):
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/generate/abc123/download/nonexistent-job")
        assert resp.status_code == 404

    def test_404_when_job_not_complete(self):
        from src.review.generate_routes import GenerationJob, _jobs
        import uuid
        app = _make_app()
        job_id = str(uuid.uuid4())
        job = GenerationJob(
            job_id=job_id, source_hash="abc123", status="running",
            output_path=None, error_message=None,
            genre="pop", occasion="general", transition_mode="subtle",
            created_at=time.time(),
        )
        _jobs[job_id] = job
        with app.test_client() as client:
            resp = client.get(f"/generate/abc123/download/{job_id}")
        assert resp.status_code == 404

    def test_200_with_file_when_complete(self, tmp_path):
        app = _make_app()
        xsq_file = tmp_path / "output.xsq"
        xsq_file.write_text("<xlightsproject/>")
        job_id = self._insert_complete_job(output_path=xsq_file)
        with app.test_client() as client:
            resp = client.get(f"/generate/abc123/download/{job_id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# T021: US2 — genre/occasion validation tests
# ---------------------------------------------------------------------------

class TestGenerationInputValidation:
    def _setup(self, tmp_path, genre="pop", occasion="general", transition_mode="subtle"):
        app = _make_app()
        entry = _make_entry()
        analysis_file = tmp_path / "hierarchy.json"
        analysis_file.write_text("{}")
        entry.analysis_path = str(analysis_file)
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlightsproject/>")
        return app, entry, layout_file

    def test_genre_passed_through_to_config(self, tmp_path):
        app, entry, layout_file = self._setup(tmp_path)
        captured = {}
        def fake_run(job, config):
            captured["genre"] = config.genre
        with app.test_client() as client:
            with patch("src.review.generate_routes.Library") as MockLib, \
                 patch("src.review.generate_routes.get_layout_path", return_value=layout_file), \
                 patch("src.review.generate_routes._run_generation", side_effect=fake_run):
                MockLib.return_value.find_by_hash.return_value = entry
                client.post("/generate/abc123", json={"genre": "rock", "occasion": "general", "transition_mode": "subtle"})
        assert captured.get("genre") == "rock"

    def test_genre_any_is_accepted(self, tmp_path):
        app, entry, layout_file = self._setup(tmp_path)
        with app.test_client() as client:
            with patch("src.review.generate_routes.Library") as MockLib, \
                 patch("src.review.generate_routes.get_layout_path", return_value=layout_file), \
                 patch("src.review.generate_routes._run_generation"):
                MockLib.return_value.find_by_hash.return_value = entry
                resp = client.post("/generate/abc123", json={"genre": "any", "occasion": "general", "transition_mode": "subtle"})
        assert resp.status_code == 202

    def test_invalid_occasion_returns_400(self, tmp_path):
        app, entry, layout_file = self._setup(tmp_path)
        with app.test_client() as client:
            with patch("src.review.generate_routes.Library") as MockLib, \
                 patch("src.review.generate_routes.get_layout_path", return_value=layout_file):
                MockLib.return_value.find_by_hash.return_value = entry
                resp = client.post("/generate/abc123",
                                   json={"genre": "pop", "occasion": "valentines", "transition_mode": "subtle"})
        assert resp.status_code == 400
        assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# T024: US3 — GET /generate/<source_hash>/history tests
# ---------------------------------------------------------------------------

class TestGenerationHistory:
    def _add_job(self, source_hash, status, genre="pop", created_at=None):
        from src.review.generate_routes import GenerationJob, _jobs
        import uuid
        job_id = str(uuid.uuid4())
        job = GenerationJob(
            job_id=job_id,
            source_hash=source_hash,
            status=status,
            output_path=Path("/fake/out.xsq") if status == "complete" else None,
            error_message="err" if status == "failed" else None,
            genre=genre,
            occasion="general",
            transition_mode="subtle",
            created_at=created_at or time.time(),
        )
        _jobs[job_id] = job
        return job_id

    def test_empty_list_when_no_jobs_for_hash(self):
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/generate/nosuchhash/history")
        assert resp.status_code == 200
        assert resp.get_json()["jobs"] == []

    # Spec 046 T036: history now returns ALL jobs (including in-flight).
    def test_all_jobs_returned_sorted_newest_first(self):
        app = _make_app()
        now = time.time()
        self._add_job("hash1", status="complete", created_at=now - 30)
        self._add_job("hash1", status="failed", created_at=now - 20)
        self._add_job("hash1", status="running", created_at=now - 10)
        with app.test_client() as client:
            resp = client.get("/generate/hash1/history")
        data = resp.get_json()
        assert len(data["jobs"]) == 3
        # Running is newest, then failed, then complete.
        statuses = [j["status"] for j in data["jobs"]]
        assert statuses == ["running", "failed", "complete"]

    # Spec 046 T037: conditional fields by status.
    def test_download_url_only_on_complete_error_only_on_failed(self):
        app = _make_app()
        self._add_job("hash9", status="complete")
        self._add_job("hash9", status="running")
        self._add_job("hash9", status="failed")
        with app.test_client() as client:
            resp = client.get("/generate/hash9/history")
        by_status = {j["status"]: j for j in resp.get_json()["jobs"]}

        assert "download_url" in by_status["complete"]
        assert by_status["complete"]["download_url"].startswith(
            "/generate/hash9/download/"
        )
        assert "download_url" not in by_status["running"]
        assert "download_url" not in by_status["failed"]

        assert "error" in by_status["failed"]
        assert "error" not in by_status["complete"]
        assert "error" not in by_status["running"]

    def test_sorted_newest_first(self):
        app = _make_app()
        now = time.time()
        self._add_job("hash2", status="complete", genre="pop", created_at=now - 100)
        self._add_job("hash2", status="complete", genre="rock", created_at=now)
        with app.test_client() as client:
            resp = client.get("/generate/hash2/history")
        data = resp.get_json()
        assert len(data["jobs"]) == 2
        # Newest first: rock was created more recently
        assert data["jobs"][0]["genre"] == "rock"
        assert data["jobs"][1]["genre"] == "pop"

    def test_job_entry_has_required_fields(self):
        app = _make_app()
        self._add_job("hash3", status="complete")
        with app.test_client() as client:
            resp = client.get("/generate/hash3/history")
        job = resp.get_json()["jobs"][0]
        for field in ["job_id", "genre", "occasion", "transition_mode", "created_at"]:
            assert field in job, f"Missing field: {field}"
