"""Integration tests for the /library response extension (spec 045).

Verifies that `_enrich()` adds four fields per entry used by the dashboard's
stateful workflow strip and Zone A banner: `layout_configured`,
`last_generated_at`, `has_story`, and `is_stale`.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_entry_dict(source_file: Path, analysis_path: Path, source_hash: str,
                     analyzed_at: int = 1_700_000_000_000) -> dict:
    """Build a minimal library entry dict (matches library.json on-disk schema)."""
    return {
        "source_hash": source_hash,
        "source_file": str(source_file),
        "filename": source_file.name,
        "analysis_path": str(analysis_path),
        "duration_ms": 180_000,
        "estimated_tempo_bpm": 120.0,
        "track_count": 6,
        "stem_separation": True,
        "analyzed_at": analyzed_at,
        "title": "Test Song",
        "artist": "Test Artist",
    }


def _write_library_index(tmp_path: Path, entries: list[dict]) -> Path:
    """Write a library.json file to tmp_path and return its path."""
    index_path = tmp_path / "library.json"
    index_path.write_text(
        json.dumps({"version": "1.0", "entries": entries}, indent=2),
        encoding="utf-8",
    )
    return index_path


def _build_client(library_index: Path, layout_path):
    """Create a Flask test client with the library index + layout patched.

    Returns a context-manager-style tuple: call `.get("/library")` after
    entering the returned contexts.
    """
    from src.review.server import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


@pytest.fixture
def single_song_library(tmp_path):
    """Create a library with one analyzed song whose MD5 matches its stored hash."""
    source_file = tmp_path / "song.mp3"
    source_file.write_bytes(b"FAKE-MP3-CONTENT-STABLE-FOR-MD5")
    source_hash = _md5(source_file)

    analysis_path = tmp_path / "song_analysis.json"
    analysis_path.write_text(
        json.dumps({"source_hash": source_hash, "validation": {}}),
        encoding="utf-8",
    )

    entries = [_make_entry_dict(source_file, analysis_path, source_hash)]
    library_index = _write_library_index(tmp_path, entries)
    return {
        "source_file": source_file,
        "source_hash": source_hash,
        "analysis_path": analysis_path,
        "library_index": library_index,
        "tmp_path": tmp_path,
    }


def _get_library(app, library_index_path: Path, layout_path):
    """Make a GET /library request with library_index and layout patched."""
    with patch("src.library.DEFAULT_LIBRARY_PATH", library_index_path), \
         patch("src.review.server.get_layout_path", return_value=layout_path):
        with app.test_client() as client:
            return client.get("/library")


# ---------------------------------------------------------------------------
# T004: /library returns entries with the four new fields present
# ---------------------------------------------------------------------------

class TestLibraryPayloadFields:
    def test_all_four_new_fields_present(self, single_song_library):
        app = _build_client(single_song_library["library_index"], None)
        resp = _get_library(app, single_song_library["library_index"], None)
        assert resp.status_code == 200, resp.data
        data = resp.get_json()
        assert "entries" in data
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert "layout_configured" in entry
        assert "last_generated_at" in entry
        assert "has_story" in entry
        assert "is_stale" in entry
        assert isinstance(entry["layout_configured"], bool)
        assert entry["last_generated_at"] is None or isinstance(entry["last_generated_at"], str)
        assert isinstance(entry["has_story"], bool)
        assert isinstance(entry["is_stale"], bool)


# ---------------------------------------------------------------------------
# T005: layout_configured reflects get_layout_path()
# ---------------------------------------------------------------------------

class TestLayoutConfigured:
    def test_layout_not_configured_when_path_is_none(self, single_song_library):
        app = _build_client(single_song_library["library_index"], None)
        resp = _get_library(app, single_song_library["library_index"], None)
        entries = resp.get_json()["entries"]
        assert all(e["layout_configured"] is False for e in entries)

    def test_layout_configured_when_path_exists(self, single_song_library, tmp_path):
        layout_file = tmp_path / "layout.xml"
        layout_file.write_text("<xmodels/>")
        app = _build_client(single_song_library["library_index"], layout_file)
        resp = _get_library(app, single_song_library["library_index"], layout_file)
        entries = resp.get_json()["entries"]
        assert all(e["layout_configured"] is True for e in entries)

    def test_layout_not_configured_when_file_missing(self, single_song_library, tmp_path):
        """Edge case: settings references a path that no longer exists on disk."""
        phantom = tmp_path / "missing_layout.xml"  # never created
        app = _build_client(single_song_library["library_index"], phantom)
        resp = _get_library(app, single_song_library["library_index"], phantom)
        entries = resp.get_json()["entries"]
        assert all(e["layout_configured"] is False for e in entries)


# ---------------------------------------------------------------------------
# T006: is_stale compares recomputed MD5 to stored source_hash
# ---------------------------------------------------------------------------

class TestIsStale:
    def test_not_stale_when_md5_matches(self, single_song_library):
        app = _build_client(single_song_library["library_index"], None)
        resp = _get_library(app, single_song_library["library_index"], None)
        entry = resp.get_json()["entries"][0]
        assert entry["is_stale"] is False

    def test_stale_when_source_modified(self, single_song_library):
        # Overwrite the source with new content → new MD5
        source_file = single_song_library["source_file"]
        original_hash = single_song_library["source_hash"]
        source_file.write_bytes(b"DIFFERENT-CONTENT-AFTER-EDIT")
        assert _md5(source_file) != original_hash

        app = _build_client(single_song_library["library_index"], None)
        resp = _get_library(app, single_song_library["library_index"], None)
        entry = resp.get_json()["entries"][0]
        assert entry["is_stale"] is True

    def test_not_stale_when_source_missing(self, single_song_library):
        # Delete the source file — should skip staleness check (is_stale = False)
        single_song_library["source_file"].unlink()
        app = _build_client(single_song_library["library_index"], None)
        resp = _get_library(app, single_song_library["library_index"], None)
        entry = resp.get_json()["entries"][0]
        assert entry["is_stale"] is False


# ---------------------------------------------------------------------------
# T025: US2 — layout_configured is false on every entry when layout_path is cleared
# ---------------------------------------------------------------------------

class TestLayoutClearedUS2:
    def test_cleared_layout_path_propagates_to_every_entry(self, tmp_path):
        # Build a library with two analyzed songs
        entries = []
        for i in range(2):
            src = tmp_path / f"song{i}.mp3"
            src.write_bytes(f"SONG-{i}-BYTES".encode())
            src_hash = _md5(src)
            ana = tmp_path / f"song{i}_analysis.json"
            ana.write_text(json.dumps({"source_hash": src_hash}), encoding="utf-8")
            entries.append(_make_entry_dict(src, ana, src_hash))
        library_index = _write_library_index(tmp_path, entries)

        app = _build_client(library_index, None)
        resp = _get_library(app, library_index, None)
        data = resp.get_json()
        assert len(data["entries"]) == 2
        for entry in data["entries"]:
            assert entry["layout_configured"] is False


# ---------------------------------------------------------------------------
# last_generated_at from _jobs dict
# ---------------------------------------------------------------------------

class TestLastGeneratedAt:
    def test_null_when_no_jobs(self, single_song_library):
        from src.review.generate_routes import _jobs
        _jobs.clear()
        app = _build_client(single_song_library["library_index"], None)
        resp = _get_library(app, single_song_library["library_index"], None)
        entry = resp.get_json()["entries"][0]
        assert entry["last_generated_at"] is None

    def test_iso_string_when_completed_job_exists(self, single_song_library):
        from src.review.generate_routes import _jobs, GenerationJob
        _jobs.clear()
        source_hash = single_song_library["source_hash"]
        job = GenerationJob(
            job_id="j1",
            source_hash=source_hash,
            status="complete",
            output_path=None,
            error_message=None,
            genre="pop",
            occasion="general",
            transition_mode="subtle",
            created_at=time.time(),
        )
        _jobs["j1"] = job

        try:
            app = _build_client(single_song_library["library_index"], None)
            resp = _get_library(app, single_song_library["library_index"], None)
            entry = resp.get_json()["entries"][0]
            assert entry["last_generated_at"] is not None
            # ISO-8601 like 2024-01-01T12:34:56…
            assert "T" in entry["last_generated_at"]
        finally:
            _jobs.clear()
