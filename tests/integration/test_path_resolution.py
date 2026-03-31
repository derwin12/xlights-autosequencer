"""Integration tests for devcontainer path resolution (feature 023).

T024: Verify local (non-container) environment leaves PathContext inert.
T025: Verify library, cache, and stems produce identical output to pre-023 behaviour
      when no container env vars are set.
T026: Cross-environment integration — simulate container env and verify end-to-end
      path mapping works.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _make_audio_file(path: Path, content: bytes = b"fake mp3 audio") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ── T024: PathContext is inert on local environment ──────────────────────────

class TestLocalEnvironmentUnaffected:
    """US5: local-only workflow must behave identically to pre-023."""

    def test_pathcontext_inert_without_env_var(self):
        from src.paths import PathContext

        env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
        with patch.dict(os.environ, env, clear=True):
            ctx = PathContext()

        assert ctx.in_container is False
        assert ctx.container_show_dir is None
        assert ctx.host_show_dir is None

    def test_to_relative_returns_none_locally(self):
        from src.paths import PathContext

        env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
        with patch.dict(os.environ, env, clear=True):
            ctx = PathContext()

        assert ctx.to_relative("/any/path/song.mp3") is None

    def test_to_absolute_passthrough_locally(self):
        from src.paths import PathContext

        env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
        with patch.dict(os.environ, env, clear=True):
            ctx = PathContext()

        assert ctx.to_absolute("show/song.mp3") == "show/song.mp3"

    def test_suggest_path_returns_none_locally(self):
        from src.paths import PathContext

        env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
        with patch.dict(os.environ, env, clear=True):
            ctx = PathContext()

        assert ctx.suggest_path("/home/node/xlights/song.mp3") is None
        assert ctx.suggest_path("/any/path/song.mp3") is None

    def test_is_in_show_dir_always_false_locally(self):
        from src.paths import PathContext

        env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
        with patch.dict(os.environ, env, clear=True):
            ctx = PathContext()

        assert ctx.is_in_show_dir("/Users/bob/xlights/song.mp3") is False
        assert ctx.is_in_show_dir("/home/node/xlights/song.mp3") is False


# ── T025: Library and HierarchyResult unchanged in local env ────────────────

class TestLocalLibraryBehaviour:
    """US5: library and result fields retain pre-023 behaviour in local env."""

    def test_library_entry_loads_without_relative_fields(self, tmp_path):
        from src.library import Library, LibraryEntry

        env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
        with patch.dict(os.environ, env, clear=True):
            lib = Library(tmp_path / "library.json")

            entry = LibraryEntry(
                source_hash="abc123",
                source_file="/local/song.mp3",
                filename="song.mp3",
                analysis_path="/local/song_hierarchy.json",
                duration_ms=60000,
                estimated_tempo_bpm=120.0,
                track_count=5,
                stem_separation=False,
                analyzed_at=int(time.time() * 1000),
            )
            lib.upsert(entry)
            loaded = lib.find_by_hash("abc123")

        assert loaded is not None
        assert loaded.source_file == "/local/song.mp3"
        assert loaded.relative_source_file is None
        assert loaded.relative_analysis_path is None

    def test_hierarchy_result_relative_field_none_locally(self):
        from src.analyzer.result import HierarchyResult

        env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
        with patch.dict(os.environ, env, clear=True):
            r = HierarchyResult(
                schema_version="2.0.0",
                source_file="/local/song.mp3",
                source_hash="abc123",
                duration_ms=60000,
                estimated_bpm=120.0,
            )
            # Relative field defaults None; serialising excludes it (backward compat)
            d = r.to_dict()

        assert r.relative_source_file is None
        assert "relative_source_file" not in d

    def test_old_hierarchy_json_loads_cleanly(self):
        """Pre-023 JSON without relative_source_file must deserialise without error."""
        from src.analyzer.result import HierarchyResult

        old_json = {
            "schema_version": "2.0.0",
            "source_file": "/old/path/song.mp3",
            "source_hash": "deadbeef" * 4,
            "duration_ms": 120000,
            "estimated_bpm": 128.0,
        }
        hr = HierarchyResult.from_dict(old_json)
        assert hr.source_file == "/old/path/song.mp3"
        assert hr.relative_source_file is None


# ── T026: Cross-environment path resolution (container simulation) ───────────

class TestCrossEnvironmentResolution:
    """Simulate container env and verify end-to-end: path mapping → library → result."""

    def test_container_path_maps_to_relative(self):
        from src.paths import PathContext

        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": "/Users/bob/xlights"}):
            ctx = PathContext()
            rel = ctx.to_relative("/home/node/xlights/2024/song.mp3")

        assert rel == "2024/song.mp3"

    def test_relative_path_resolves_back_to_absolute_in_container(self):
        from src.paths import PathContext

        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": "/Users/bob/xlights"}):
            ctx = PathContext()
            abs_path = ctx.to_absolute("2024/song.mp3")

        assert abs_path == "/home/node/xlights/2024/song.mp3"

    def test_library_stores_relative_path_in_container(self, tmp_path):
        from src.library import Library, LibraryEntry

        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": "/Users/bob/xlights"}):
            lib = Library(tmp_path / "library.json")
            entry = LibraryEntry(
                source_hash="abc123",
                source_file="/home/node/xlights/show/song.mp3",
                filename="song.mp3",
                analysis_path="/home/node/xlights/show/song/song_hierarchy.json",
                duration_ms=60000,
                estimated_tempo_bpm=120.0,
                track_count=5,
                stem_separation=False,
                analyzed_at=0,
                relative_source_file="show/song.mp3",
                relative_analysis_path="show/song/song_hierarchy.json",
            )
            lib.upsert(entry)
            loaded = lib.find_by_hash("abc123")

        assert loaded is not None
        assert loaded.relative_source_file == "show/song.mp3"
        assert loaded.relative_analysis_path == "show/song/song_hierarchy.json"

    def test_library_deduplicates_on_environment_switch(self, tmp_path):
        """Same song accessed from host then container must produce one library entry."""
        from src.library import Library, LibraryEntry

        lib = Library(tmp_path / "library.json")
        hash_val = "cafebabe"

        # First access: from host (absolute path is host path)
        host_entry = LibraryEntry(
            source_hash=hash_val,
            source_file="/Users/bob/xlights/show/song.mp3",
            filename="song.mp3",
            analysis_path="/Users/bob/xlights/show/song/song_hierarchy.json",
            duration_ms=60000,
            estimated_tempo_bpm=120.0,
            track_count=5,
            stem_separation=False,
            analyzed_at=1000,
            relative_source_file="show/song.mp3",
        )
        lib.upsert(host_entry)

        # Second access: from container (absolute path is container path, same hash)
        container_entry = LibraryEntry(
            source_hash=hash_val,
            source_file="/home/node/xlights/show/song.mp3",
            filename="song.mp3",
            analysis_path="/home/node/xlights/show/song/song_hierarchy.json",
            duration_ms=60000,
            estimated_tempo_bpm=120.0,
            track_count=5,
            stem_separation=False,
            analyzed_at=2000,
            relative_source_file="show/song.mp3",
        )
        lib.upsert(container_entry)

        all_entries = lib.all_entries()
        assert len(all_entries) == 1, "Duplicate entries created for same-hash song"
        assert all_entries[0].source_file == "/home/node/xlights/show/song.mp3"

    def test_host_path_suggestion_in_container(self):
        """User typed a host path inside container → suggest correct container path."""
        from src.paths import PathContext

        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": "/Users/bob/xlights"}):
            ctx = PathContext()
            suggestion = ctx.suggest_path("/Users/bob/xlights/show/song.mp3")

        assert suggestion == "/home/node/xlights/show/song.mp3"

    def test_hierarchy_result_relative_path_in_container(self):
        from src.analyzer.result import HierarchyResult

        r = HierarchyResult(
            schema_version="2.0.0",
            source_file="/home/node/xlights/show/song.mp3",
            source_hash="abc",
            duration_ms=60000,
            estimated_bpm=120.0,
            relative_source_file="show/song.mp3",
        )
        d = r.to_dict()
        restored = HierarchyResult.from_dict(d)

        assert restored.relative_source_file == "show/song.mp3"
        assert restored.source_file == "/home/node/xlights/show/song.mp3"
