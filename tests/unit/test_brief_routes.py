"""Unit tests for brief_routes GET/PUT endpoints (spec 047, US3)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.review.server import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_song(tmp_path):
    """Create a fake song directory with a minimal MP3 and library entry."""
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"ID3")
    return audio


@pytest.fixture
def mock_library_entry(tmp_song):
    """A mock LibraryEntry pointing to tmp_song."""
    entry = MagicMock()
    entry.source_file = str(tmp_song)
    entry.analysis_path = str(tmp_song.parent / "song_analysis.json")
    return entry


@pytest.fixture
def app(mock_library_entry):
    """Flask test app with library patched."""
    with patch("src.review.brief_routes.Library") as MockLib:
        instance = MockLib.return_value
        instance.find_by_hash.return_value = mock_library_entry
        application = create_app()
        application.config["TESTING"] = True
        yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _brief_path_for(audio_path: str) -> Path:
    p = Path(audio_path)
    return p.parent / f"{p.stem}_brief.json"


# ---------------------------------------------------------------------------
# T041: GET returns 404 when no brief file exists
# ---------------------------------------------------------------------------

class TestGetBriefNotFound:
    def test_returns_404_when_no_brief(self, client):
        resp = client.get("/brief/abc123")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data


# ---------------------------------------------------------------------------
# T041b: GET returns 404 when song not in library
# ---------------------------------------------------------------------------

class TestGetBriefSongNotInLibrary:
    def test_returns_404_when_song_unknown(self):
        with patch("src.review.brief_routes.Library") as MockLib:
            MockLib.return_value.find_by_hash.return_value = None
            app = create_app()
            app.config["TESTING"] = True
            with app.test_client() as c:
                resp = c.get("/brief/notexist")
                assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T042: PUT writes brief, GET returns same doc
# ---------------------------------------------------------------------------

VALID_BRIEF = {
    "brief_schema_version": 1,
    "source_hash": "abc123",
    "genre": "pop",
    "occasion": "general",
    "mood_intent": "dramatic",
    "variation": "focused",
    "palette": "restrained",
    "duration": "flowing",
    "accents": "strong",
    "transitions": "dramatic",
    "curves": "on",
    "advanced": {},
    "per_section_overrides": [],
}


class TestPutAndGet:
    def test_put_writes_and_get_returns_same(self, client, mock_library_entry):
        resp = client.put(
            "/brief/abc123",
            data=json.dumps(VALID_BRIEF),
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        stored = resp.get_json()
        assert stored["genre"] == "pop"
        assert stored["mood_intent"] == "dramatic"
        assert "updated_at" in stored

        # Now GET should return the same (minus updated_at drift)
        get_resp = client.get("/brief/abc123")
        assert get_resp.status_code == 200
        got = get_resp.get_json()
        for key in VALID_BRIEF:
            if key not in ("updated_at",):
                assert got.get(key) == stored.get(key), f"mismatch on key {key}"

    def test_brief_file_written_to_disk(self, client, mock_library_entry):
        client.put(
            "/brief/abc123",
            data=json.dumps(VALID_BRIEF),
            content_type="application/json",
        )
        brief_file = _brief_path_for(mock_library_entry.source_file)
        assert brief_file.exists()
        with open(brief_file) as f:
            saved = json.load(f)
        assert saved["genre"] == "pop"


# ---------------------------------------------------------------------------
# T043: PUT with invalid field returns 400 with {field, error}
# ---------------------------------------------------------------------------

class TestPutValidation:
    def test_invalid_genre_returns_400(self, client):
        bad = dict(VALID_BRIEF, genre="jazz")
        resp = client.put(
            "/brief/abc123",
            data=json.dumps(bad),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data.get("field") == "genre"
        assert "error" in data

    def test_invalid_occasion_returns_400(self, client):
        bad = dict(VALID_BRIEF, occasion="easter")
        resp = client.put(
            "/brief/abc123",
            data=json.dumps(bad),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data.get("field") == "occasion"

    def test_invalid_curves_returns_400(self, client):
        bad = dict(VALID_BRIEF, curves="turbo")
        resp = client.put(
            "/brief/abc123",
            data=json.dumps(bad),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data.get("field") == "curves"

    def test_invalid_advanced_curves_mode_returns_400(self, client):
        bad = dict(VALID_BRIEF, advanced={"curves_mode": "rainbow"})
        resp = client.put(
            "/brief/abc123",
            data=json.dumps(bad),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "curves_mode" in data.get("field", "")


# ---------------------------------------------------------------------------
# T044: PUT with wrong schema_version returns 409
# ---------------------------------------------------------------------------

class TestPutSchemaVersionMismatch:
    def test_wrong_version_returns_409(self, client):
        bad = dict(VALID_BRIEF, brief_schema_version=99)
        resp = client.put(
            "/brief/abc123",
            data=json.dumps(bad),
            content_type="application/json",
        )
        assert resp.status_code == 409
        data = resp.get_json()
        assert "brief_schema_version" in data.get("field", "")


# ---------------------------------------------------------------------------
# T046: Round-trip a fully populated brief through PUT → GET
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_full_round_trip(self, client, mock_library_entry):
        full_brief = dict(VALID_BRIEF)
        full_brief["per_section_overrides"] = []  # keep empty to avoid theme catalog validation
        full_brief["advanced"] = {"curves_mode": "brightness"}

        put_resp = client.put(
            "/brief/abc123",
            data=json.dumps(full_brief),
            content_type="application/json",
        )
        assert put_resp.status_code == 200
        stored = put_resp.get_json()

        get_resp = client.get("/brief/abc123")
        assert get_resp.status_code == 200
        got = get_resp.get_json()

        # Every axis should match
        for axis in ("genre", "occasion", "mood_intent", "variation", "palette",
                     "duration", "accents", "transitions", "curves"):
            assert got[axis] == full_brief[axis], f"axis {axis} mismatch"
        assert got["advanced"]["curves_mode"] == "brightness"
