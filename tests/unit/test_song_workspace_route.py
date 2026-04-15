"""Tests for the /song/<source_hash> workspace route (spec 046)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def _tmp_xlight(tmp_path):
    """Set up a temporary ~/.xlight directory with a seeded library entry."""
    xlight_dir = tmp_path / ".xlight"
    xlight_dir.mkdir()
    (xlight_dir / "custom_themes").mkdir()

    analysis_dir = xlight_dir / "songs"
    analysis_dir.mkdir()
    analysis_file = analysis_dir / "abc_hierarchy.json"
    analysis_file.write_text(json.dumps({
        "schema_version": "2.0.0",
        "validation": {"overall_score": 0.8},
        "song": {"title": "Spec 046 Song", "artist": "Test"},
    }))

    library_path = xlight_dir / "library.json"
    library_path.write_text(json.dumps({
        "version": "1.0",
        "entries": [{
            "source_hash": "abc123",
            "source_file": str(analysis_dir / "abc.mp3"),
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


class TestSongWorkspaceRoute:
    # T008 — known hash returns 200 with the workspace HTML body
    def test_known_hash_returns_workspace_html(self, client):
        resp = client.get("/song/abc123")
        assert resp.status_code == 200
        # song-workspace.html body signature — we assert a known fragment once
        # implementation lands; for now just assert the response is HTML.
        assert resp.mimetype == "text/html"
        assert b"panel-analysis" in resp.data

    # T009 — unknown hash returns 404 with a library-pointer message
    def test_unknown_hash_returns_404(self, client):
        resp = client.get("/song/bogus-hash-1234")
        assert resp.status_code == 404
        # message should reference the library (directing the user back)
        body = resp.data.decode("utf-8", errors="replace").lower()
        assert "library" in body or "not found" in body

    # T010 — /timeline still serves index.html (no regression)
    def test_timeline_still_serves_index(self, client):
        resp = client.get("/timeline")
        assert resp.status_code == 200
        # timeline's index.html exposes the timeline-root mount point
        assert b"timeline-root" in resp.data

    # T011 — /phonemes-view and /story-review still return their static files
    def test_phonemes_view_still_serves_static(self, client):
        resp = client.get("/phonemes-view")
        assert resp.status_code == 200

    def test_story_review_still_serves_static(self, client):
        resp = client.get("/story-review")
        assert resp.status_code == 200
