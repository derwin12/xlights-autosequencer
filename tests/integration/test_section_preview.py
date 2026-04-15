"""Integration tests for the section preview render pipeline (spec 049).

T013-T015: end-to-end POST → poll → download, brief modes, failed job handling.
T047-T049: explicit section_index, out-of-range, no sections.
T056: supersede semantics — concurrent requests for same song.
"""
from __future__ import annotations

import json
import time
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Flask test client fixture ─────────────────────────────────────────────


@pytest.fixture
def app(tmp_path):
    """Create a minimal Flask app with preview_bp registered for testing."""
    from flask import Flask

    flask_app = Flask(__name__, static_folder=None)
    flask_app.config["TESTING"] = True

    # We patch the preview module state so each test gets a fresh job store
    import src.review.preview_routes as pr
    pr._preview_jobs.clear()
    pr._active_by_song.clear()
    import tempfile
    pr._preview_dir = Path(tempfile.mkdtemp(prefix="xlight_preview_test_"))
    pr._preview_cache = pr._PreviewCache(max_entries=16)

    from src.review.preview_routes import preview_bp
    flask_app.register_blueprint(preview_bp, url_prefix="/api/song")

    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ── Library and layout mocks ───────────────────────────────────────────────


def _make_library_entry(tmp_path: Path):
    """Create a minimal library entry pointing to a temp audio file."""
    entry = MagicMock()
    audio = tmp_path / "test_song.mp3"
    audio.write_bytes(b"")  # empty file
    analysis = tmp_path / "test_song_analysis.json"
    analysis.write_text('{"schema_version": "2.0.0"}')
    entry.source_file = str(audio)
    entry.analysis_path = str(analysis)
    entry.source_hash = "abc123"
    return entry


def _make_hierarchy(tmp_path: Path):
    """Create a minimal HierarchyResult mock with 3 sections."""
    from src.generator.models import SectionEnergy
    from src.analyzer.result import TimingMark

    sections = [
        TimingMark(time_ms=0, label="intro"),
        TimingMark(time_ms=15000, label="chorus"),
        TimingMark(time_ms=45000, label="outro"),
    ]

    h = MagicMock()
    h.duration_ms = 60000
    h.estimated_bpm = 120.0
    h.sections = sections
    h.energy_curves = {}
    h.energy_impacts = []
    h.events = {}
    h.bars = None
    h.beats = None
    h.chords = None
    h.key_changes = None
    h.essentia_features = {}
    return h


def _make_groups():
    """Return empty list of groups for minimal test."""
    return []


def _make_plan(tmp_path: Path):
    """Create a minimal SequencePlan for testing."""
    from src.generator.models import (
        EffectPlacement, SectionAssignment, SectionEnergy,
        SequencePlan, SongProfile,
    )
    from src.themes.models import EffectLayer, Theme

    theme = Theme(
        name="TestTheme",
        mood="structural",
        occasion="general",
        genre="any",
        intent="test",
        layers=[EffectLayer(variant="Fire")],
        palette=["#FF0000"],
    )
    placement = EffectPlacement(
        effect_name="Fire",
        xlights_id="Fire",
        model_or_group="Group1",
        start_ms=15000,
        end_ms=30000,
        color_palette=["#FF0000"],
    )
    section = SectionAssignment(
        section=SectionEnergy(
            label="chorus",
            start_ms=15000,
            end_ms=45000,
            energy_score=80,
            mood_tier="aggressive",
            impact_count=0,
        ),
        theme=theme,
        group_effects={"Group1": [placement]},
    )
    profile = SongProfile(
        title="Test", artist="", genre="pop", occasion="general",
        duration_ms=60000, estimated_bpm=120.0,
    )
    return SequencePlan(
        song_profile=profile,
        sections=[section],
        layout_groups=[],
        models=["Group1"],
    )


# ── T013: POST → poll → download ─────────────────────────────────────────


def test_post_poll_download_returns_valid_xsq(client, tmp_path):
    """T013: POST preview → poll until done → download .xsq → validate structure."""
    from src.generator.preview import PreviewResult
    import src.review.preview_routes as pr

    entry = _make_library_entry(tmp_path)
    plan = _make_plan(tmp_path)

    # Create a real .xsq artifact that can be downloaded
    from src.generator.xsq_writer import write_xsq

    fake_result = PreviewResult(
        section={"label": "chorus", "start_ms": 15000, "end_ms": 45000,
                 "energy_score": 80, "role": "chorus"},
        window_ms=15000,
        theme_name="TestTheme",
        placement_count=1,
        artifact_url="",  # will be filled by route
    )

    def _fake_run(config, section_index, output_path, cancel_token):
        """Write a real .xsq so the download test works."""
        write_xsq(plan, output_path, scoped_duration_ms=15000, audio_offset_ms=15000)
        return fake_result

    # Patch the underlying libraries so POST succeeds without real analysis
    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes.run_section_preview", side_effect=_fake_run), \
         patch("src.review.preview_routes._load_saved_brief", return_value={}):

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        resp = client.post(
            "/api/song/abc123/preview",
            json={"section_index": 1, "brief": {}},
        )
        assert resp.status_code == 202
        data = resp.get_json()
        job_id = data["job_id"]
        assert job_id

    # Wait for job to complete (background thread)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        resp = client.get(f"/api/song/abc123/preview/{job_id}")
        data = resp.get_json()
        if data["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)

    assert data["status"] == "done", f"Job did not complete: {data}"
    assert "result" in data
    result = data["result"]
    assert result["window_ms"] == 15000
    assert result["theme_name"] == "TestTheme"
    assert "artifact_url" in result

    # Download the .xsq
    import src.review.preview_routes as pr
    job = pr._preview_jobs[job_id]
    assert job.artifact_path is not None and job.artifact_path.exists()

    download_resp = client.get(f"/api/song/abc123/preview/{job_id}/download")
    assert download_resp.status_code == 200

    # Validate it's a valid .xsq XML
    tree = ET.fromstring(download_resp.data)
    assert tree.tag == "xsequence"
    head = tree.find("head")
    assert head is not None
    dur_el = head.find("sequenceDuration")
    assert dur_el is not None
    # sequenceDuration should be the scoped window (15s)
    dur_val = float(dur_el.text)
    assert 0 < dur_val <= 20.0, f"Expected sequenceDuration in 0-20s range, got {dur_val}"

    # mediaOffset should be present
    media_offset = head.find("mediaOffset")
    assert media_offset is not None
    assert media_offset.text == "15000"


# ── T014: brief modes (saved vs inline) ─────────────────────────────────


def test_post_with_saved_brief_uses_persisted_brief(client, tmp_path):
    """T014: brief='saved' loads the persisted brief from disk."""
    entry = _make_library_entry(tmp_path)
    plan = _make_plan(tmp_path)

    import src.review.preview_routes as pr

    fake_result = pr.PreviewResult(
        section={"label": "chorus", "start_ms": 15000, "end_ms": 45000,
                 "energy_score": 80, "role": "chorus"},
        window_ms=15000,
        theme_name="TestTheme",
        placement_count=1,
        artifact_url="",
    ) if False else None

    from src.generator.preview import PreviewResult as _PR
    fake_result = _PR(
        section={"label": "chorus", "start_ms": 15000, "end_ms": 45000,
                 "energy_score": 80, "role": "chorus"},
        window_ms=15000,
        theme_name="TestTheme",
        placement_count=1,
        artifact_url="",
    )

    saved_brief = {"genre": "rock", "focused_vocabulary": True}

    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes.run_section_preview", return_value=fake_result), \
         patch("src.review.preview_routes._load_saved_brief", return_value=saved_brief) as mock_brief:

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        resp = client.post(
            "/api/song/abc123/preview",
            json={"section_index": 1, "brief": "saved"},
        )
        assert resp.status_code == 202
        # Verify _load_saved_brief was called with the song hash
        mock_brief.assert_called_once_with("abc123")


def test_post_with_inline_brief_uses_it_verbatim(client, tmp_path):
    """T014: inline brief dict is used verbatim without loading saved brief."""
    entry = _make_library_entry(tmp_path)

    from src.generator.preview import PreviewResult as _PR
    fake_result = _PR(
        section={"label": "chorus", "start_ms": 15000, "end_ms": 30000,
                 "energy_score": 80, "role": "chorus"},
        window_ms=15000,
        theme_name="TestTheme",
        placement_count=1,
        artifact_url="",
    )
    inline_brief = {"genre": "pop", "focused_vocabulary": False, "palette_restraint": True}

    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes.run_section_preview", return_value=fake_result), \
         patch("src.review.preview_routes._load_saved_brief") as mock_brief:

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        resp = client.post(
            "/api/song/abc123/preview",
            json={"section_index": 1, "brief": inline_brief},
        )
        assert resp.status_code == 202
        # _load_saved_brief should NOT be called when inline brief is given
        mock_brief.assert_not_called()


# ── T015: failed job handling ────────────────────────────────────────────


def test_failed_job_returns_error_no_artifact(client, tmp_path):
    """T015: failed job returns status='failed' with error_message; no artifact_path."""
    entry = _make_library_entry(tmp_path)

    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes.run_section_preview",
               side_effect=FileNotFoundError("Analysis not found")), \
         patch("src.review.preview_routes._load_saved_brief", return_value={}):

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        resp = client.post(
            "/api/song/abc123/preview",
            json={"section_index": 0, "brief": {}},
        )
        assert resp.status_code == 202
        job_id = resp.get_json()["job_id"]

    # Wait for job to fail
    deadline = time.time() + 5.0
    while time.time() < deadline:
        resp = client.get(f"/api/song/abc123/preview/{job_id}")
        data = resp.get_json()
        if data["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)

    assert data["status"] == "failed"
    assert "error" in data
    assert data["error"]  # non-empty error message
    # FR-013: no artifact_url in failed response
    assert "artifact_url" not in (data.get("result") or {})


def test_song_not_found_returns_404(client, tmp_path):
    """POST for unknown song returns 404."""
    with patch("src.review.preview_routes.Library") as mock_lib:
        mock_lib.return_value.find_by_hash.return_value = None
        resp = client.post("/api/song/unknown/preview", json={"brief": {}})
        assert resp.status_code == 404


def test_no_analysis_returns_400(client, tmp_path):
    """POST when analysis file missing returns 400."""
    entry = _make_library_entry(tmp_path)
    # Delete the analysis file
    Path(entry.analysis_path).unlink()

    with patch("src.review.preview_routes.Library") as mock_lib:
        mock_lib.return_value.find_by_hash.return_value = entry
        resp = client.post("/api/song/abc123/preview", json={"brief": {}})
        assert resp.status_code == 400


def test_no_layout_returns_409(client, tmp_path):
    """POST when layout not configured returns 409."""
    entry = _make_library_entry(tmp_path)

    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path", return_value=None):
        mock_lib.return_value.find_by_hash.return_value = entry
        resp = client.post("/api/song/abc123/preview", json={"brief": {}})
        assert resp.status_code == 409


# ── T047: explicit section_index ──────────────────────────────────────────


def test_explicit_section_index_used(client, tmp_path):
    """T047: POST with explicit section_index=2 uses section 2."""
    entry = _make_library_entry(tmp_path)

    from src.generator.preview import PreviewResult as _PR
    fake_result = _PR(
        section={"label": "outro", "start_ms": 45000, "end_ms": 60000,
                 "energy_score": 30, "role": "outro"},
        window_ms=15000,
        theme_name="TestTheme",
        placement_count=0,
        artifact_url="",
    )

    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes.run_section_preview", return_value=fake_result) as mock_run, \
         patch("src.review.preview_routes._load_saved_brief", return_value={}):

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        resp = client.post(
            "/api/song/abc123/preview",
            json={"section_index": 2, "brief": {}},
        )
        assert resp.status_code == 202
        job_id = resp.get_json()["job_id"]

    # Wait for completion
    deadline = time.time() + 5.0
    while time.time() < deadline:
        resp = client.get(f"/api/song/abc123/preview/{job_id}")
        data = resp.get_json()
        if data["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)

    # Verify run_section_preview was called with section_index=2
    import src.review.preview_routes as pr
    job = pr._preview_jobs[job_id]
    assert job.section_index == 2


# ── T048: section_index out of range ─────────────────────────────────────


def test_out_of_range_section_index_causes_failed_job(client, tmp_path):
    """T048: section_index out of range results in a failed job with clear error."""
    entry = _make_library_entry(tmp_path)

    # Mock run_section_preview to raise ValueError for out-of-range index
    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes.run_section_preview",
               side_effect=ValueError("section_index 999 out of range")), \
         patch("src.review.preview_routes._load_saved_brief", return_value={}):

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        resp = client.post(
            "/api/song/abc123/preview",
            json={"section_index": 999, "brief": {}},
        )
        assert resp.status_code == 202
        job_id = resp.get_json()["job_id"]

    deadline = time.time() + 5.0
    while time.time() < deadline:
        resp = client.get(f"/api/song/abc123/preview/{job_id}")
        data = resp.get_json()
        if data["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)

    assert data["status"] == "failed"
    assert data.get("error")


# ── T056: supersede semantics ─────────────────────────────────────────────


def test_supersede_cancels_inflight_job(client, tmp_path):
    """T056: second POST for same song cancels the first job."""
    entry = _make_library_entry(tmp_path)

    import src.review.preview_routes as pr

    # Use a slow mock for the first job
    first_job_started = threading.Event()
    cancel_token_holder = []

    def slow_run_section_preview(config, section_index, output_path, cancel_token):
        from src.generator.preview import PreviewResult, PreviewCancelled
        cancel_token_holder.append(cancel_token)
        first_job_started.set()
        # Simulate slow work — check for cancellation
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if cancel_token.is_cancelled():
                raise PreviewCancelled()
            time.sleep(0.05)
        # Should not reach here in the test
        return PreviewResult(
            section={"label": "chorus", "start_ms": 0, "end_ms": 15000,
                     "energy_score": 80, "role": "chorus"},
            window_ms=15000, theme_name="TestTheme",
            placement_count=0, artifact_url="",
        )

    from src.generator.preview import PreviewResult as _PR
    second_result = _PR(
        section={"label": "verse", "start_ms": 15000, "end_ms": 30000,
                 "energy_score": 60, "role": "verse"},
        window_ms=15000, theme_name="TestTheme2",
        placement_count=2, artifact_url="",
    )

    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes._load_saved_brief", return_value={}):

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        # First POST
        with patch("src.review.preview_routes.run_section_preview", slow_run_section_preview):
            resp1 = client.post(
                "/api/song/abc123/preview",
                json={"section_index": 0, "brief": {}},
            )
            assert resp1.status_code == 202
            first_job_id = resp1.get_json()["job_id"]

        # Wait for first job to start
        first_job_started.wait(timeout=3.0)
        assert first_job_started.is_set(), "First job did not start in time"

        # Second POST — should supersede the first
        with patch("src.review.preview_routes.run_section_preview", return_value=second_result):
            resp2 = client.post(
                "/api/song/abc123/preview",
                json={"section_index": 1, "brief": {}},
            )
            assert resp2.status_code == 202
            second_job_id = resp2.get_json()["job_id"]

    assert first_job_id != second_job_id

    # First job should eventually be cancelled
    deadline = time.time() + 5.0
    while time.time() < deadline:
        resp = client.get(f"/api/song/abc123/preview/{first_job_id}")
        data = resp.get_json()
        if data["status"] == "cancelled":
            break
        time.sleep(0.1)
    assert data["status"] == "cancelled", f"First job not cancelled: {data}"

    # Download of cancelled job should return 410 Gone
    dl_resp = client.get(f"/api/song/abc123/preview/{first_job_id}/download")
    assert dl_resp.status_code == 410

    # Second job should complete normally
    deadline = time.time() + 5.0
    while time.time() < deadline:
        resp = client.get(f"/api/song/abc123/preview/{second_job_id}")
        data = resp.get_json()
        if data["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert data["status"] == "done"


# ── Status endpoint edge cases ────────────────────────────────────────────


def test_status_unknown_job_returns_404(client):
    """GET /preview/<unknown_job_id> returns 404."""
    resp = client.get("/api/song/abc123/preview/nonexistent-job-id")
    assert resp.status_code == 404


def test_status_hash_mismatch_returns_400(client, tmp_path):
    """GET /preview/<job_id> with wrong hash returns 400."""
    entry = _make_library_entry(tmp_path)

    from src.generator.preview import PreviewResult as _PR
    fake_result = _PR(
        section={"label": "chorus", "start_ms": 0, "end_ms": 15000,
                 "energy_score": 80, "role": "chorus"},
        window_ms=15000, theme_name="TestTheme",
        placement_count=0, artifact_url="",
    )

    with patch("src.review.preview_routes.Library") as mock_lib, \
         patch("src.review.preview_routes.get_layout_path") as mock_layout, \
         patch("src.review.preview_routes.run_section_preview", return_value=fake_result), \
         patch("src.review.preview_routes._load_saved_brief", return_value={}):

        mock_lib.return_value.find_by_hash.return_value = entry
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xlights_networks/>")
        mock_layout.return_value = layout_file

        resp = client.post("/api/song/abc123/preview", json={"brief": {}})
        job_id = resp.get_json()["job_id"]

    # Poll with wrong hash
    resp = client.get(f"/api/song/wronghash/preview/{job_id}")
    assert resp.status_code == 400


def test_download_not_done_returns_409(client, tmp_path):
    """GET /preview/<job_id>/download when status != done returns 409."""
    import src.review.preview_routes as pr

    # Insert a job in pending state manually
    from src.generator.preview import PreviewJob, CancelToken
    job = PreviewJob(
        job_id="test-pending",
        song_hash="abc123",
        section_index=0,
        brief_snapshot={},
        brief_hash="0" * 16,
        status="pending",
        started_at=time.time(),
    )
    pr._preview_jobs["test-pending"] = job

    resp = client.get("/api/song/abc123/preview/test-pending/download")
    assert resp.status_code == 409
