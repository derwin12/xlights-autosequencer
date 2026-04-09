"""Tests for dashboard and theme API routes."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def _tmp_xlight(tmp_path):
    """Set up a temporary ~/.xlight directory for tests."""
    xlight_dir = tmp_path / ".xlight"
    xlight_dir.mkdir()
    (xlight_dir / "custom_themes").mkdir()
    library_path = xlight_dir / "library.json"
    library_path.write_text(json.dumps({"version": "1.0", "entries": []}))
    return xlight_dir, library_path


@pytest.fixture
def app(_tmp_xlight):
    """Create a test Flask app in upload/dashboard mode."""
    xlight_dir, library_path = _tmp_xlight

    with patch("src.library.DEFAULT_LIBRARY_PATH", library_path):
        from src.review.server import create_app
        app = create_app(analysis_path=None, audio_path=None)
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


class TestDashboardRoutes:
    """Test that the dashboard homepage and library routes work."""

    def test_homepage_serves_dashboard(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"dashboard" in resp.data.lower() or b"xLight" in resp.data

    def test_library_view_redirects(self, client):
        resp = client.get("/library-view")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")

    def test_library_returns_empty(self, client):
        resp = client.get("/library")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "entries" in data
        assert len(data["entries"]) == 0

    def test_library_enriched_fields(self, client, _tmp_xlight):
        """Test that the library endpoint returns enriched fields."""
        xlight_dir, library_path = _tmp_xlight

        # Create a fake analysis file and library entry
        analysis_dir = xlight_dir / "songs"
        analysis_dir.mkdir()
        analysis_file = analysis_dir / "test_hierarchy.json"
        analysis_file.write_text(json.dumps({
            "schema_version": "2.0.0",
            "validation": {"overall_score": 0.85},
            "song": {"title": "Test Song", "artist": "Test Artist"},
        }))

        library_path.write_text(json.dumps({
            "version": "1.0",
            "entries": [{
                "source_hash": "abc123",
                "source_file": str(analysis_dir / "test.mp3"),
                "filename": "test.mp3",
                "analysis_path": str(analysis_file),
                "duration_ms": 180000,
                "estimated_tempo_bpm": 120.0,
                "track_count": 22,
                "stem_separation": True,
                "analyzed_at": 1711843200000,
            }],
        }))

        resp = client.get("/library")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["title"] == "Test Song"
        assert entry["artist"] == "Test Artist"
        assert entry["quality_score"] == 0.85
        assert "has_phonemes" in entry
        assert "has_story" in entry
        assert "file_exists" in entry
        assert "analysis_exists" in entry

    def test_timeline_serves_index(self, client):
        resp = client.get("/timeline")
        assert resp.status_code == 200

    def test_phonemes_view_serves_page(self, client):
        resp = client.get("/phonemes-view")
        assert resp.status_code == 200


class TestThemeRoutes:
    """Test theme endpoints (using main's API structure)."""

    @pytest.mark.xfail(reason="US2: builtin_themes.json still uses old EffectLayer format; 0 themes load until US2 migration", strict=False)
    def test_theme_list(self, client):
        resp = client.get("/themes/api/list")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "themes" in data
        assert len(data["themes"]) > 0

    def test_theme_editor_page(self, client):
        resp = client.get("/themes/")
        assert resp.status_code == 200

    def test_effects_list(self, client):
        resp = client.get("/themes/api/effects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "effects" in data
        assert "blend_modes" in data
