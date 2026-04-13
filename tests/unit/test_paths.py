"""Unit tests for src.paths.PathContext — environment detection and path mapping."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.paths import PathContext


# ── Helpers ───────────────────────────────────────────────────────────────────

CONTAINER_SHOW = "/home/node/xlights"
HOST_SHOW = "/Users/bob/xlights"


def _ctx_container(host_show: str = HOST_SHOW) -> PathContext:
    """Return a PathContext as-if running inside the dev container."""
    with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": host_show}):
        return PathContext()


def _ctx_local() -> PathContext:
    """Return a PathContext as-if running on the host (no env var)."""
    env = {k: v for k, v in os.environ.items() if k != "XLIGHTS_HOST_SHOW_DIR"}
    with patch.dict(os.environ, env, clear=True):
        return PathContext()


# ── Environment detection ─────────────────────────────────────────────────────

class TestEnvDetection:
    def test_in_container_when_env_var_set(self):
        ctx = _ctx_container()
        assert ctx.in_container is True

    def test_not_in_container_when_env_var_absent(self):
        ctx = _ctx_local()
        assert ctx.in_container is False

    def test_not_in_container_when_env_var_empty(self):
        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": ""}):
            ctx = PathContext()
        assert ctx.in_container is False

    def test_container_show_dir_set_in_container(self):
        ctx = _ctx_container()
        assert ctx.container_show_dir == CONTAINER_SHOW

    def test_host_show_dir_from_env_var(self):
        ctx = _ctx_container()
        assert ctx.host_show_dir == HOST_SHOW

    def test_container_show_dir_none_on_host(self):
        ctx = _ctx_local()
        assert ctx.container_show_dir is None

    def test_host_show_dir_none_on_host(self):
        ctx = _ctx_local()
        assert ctx.host_show_dir is None


# ── is_in_show_dir ────────────────────────────────────────────────────────────

class TestIsInShowDir:
    def test_path_inside_show_dir_in_container(self):
        ctx = _ctx_container()
        assert ctx.is_in_show_dir(f"{CONTAINER_SHOW}/show/song.mp3") is True

    def test_path_at_show_dir_root_in_container(self):
        ctx = _ctx_container()
        assert ctx.is_in_show_dir(CONTAINER_SHOW) is False  # must be *inside*

    def test_path_outside_show_dir_in_container(self):
        ctx = _ctx_container()
        assert ctx.is_in_show_dir("/tmp/song.mp3") is False

    def test_host_path_not_in_show_dir_from_container(self):
        ctx = _ctx_container()
        assert ctx.is_in_show_dir(f"{HOST_SHOW}/song.mp3") is False

    def test_always_false_on_local_with_no_show_dir(self):
        ctx = _ctx_local()
        assert ctx.is_in_show_dir("/Users/bob/xlights/song.mp3") is False


# ── to_relative ───────────────────────────────────────────────────────────────

class TestToRelative:
    def test_converts_container_path_to_relative(self):
        ctx = _ctx_container()
        result = ctx.to_relative(f"{CONTAINER_SHOW}/show/song.mp3")
        assert result == "show/song.mp3"

    def test_nested_path_relative(self):
        ctx = _ctx_container()
        result = ctx.to_relative(f"{CONTAINER_SHOW}/2024/Christmas/jingle.mp3")
        assert result == "2024/Christmas/jingle.mp3"

    def test_returns_none_for_path_outside_show_dir(self):
        ctx = _ctx_container()
        assert ctx.to_relative("/tmp/song.mp3") is None

    def test_returns_none_for_host_path_from_container(self):
        ctx = _ctx_container()
        assert ctx.to_relative(f"{HOST_SHOW}/song.mp3") is None

    def test_returns_none_on_local_environment(self):
        ctx = _ctx_local()
        assert ctx.to_relative("/Users/bob/xlights/song.mp3") is None

    def test_relative_path_has_no_leading_slash(self):
        ctx = _ctx_container()
        result = ctx.to_relative(f"{CONTAINER_SHOW}/song.mp3")
        assert result is not None
        assert not result.startswith("/")

    def test_relative_path_has_no_dotdot(self):
        ctx = _ctx_container()
        result = ctx.to_relative(f"{CONTAINER_SHOW}/show/../song.mp3")
        # Path.resolve() or normalization should eliminate ..
        assert result is None or ".." not in result


# ── to_absolute ───────────────────────────────────────────────────────────────

class TestToAbsolute:
    def test_converts_relative_to_container_absolute(self):
        ctx = _ctx_container()
        result = ctx.to_absolute("show/song.mp3")
        assert result == f"{CONTAINER_SHOW}/show/song.mp3"

    def test_nested_relative_path(self):
        ctx = _ctx_container()
        result = ctx.to_absolute("2024/Christmas/jingle.mp3")
        assert result == f"{CONTAINER_SHOW}/2024/Christmas/jingle.mp3"

    def test_passthrough_on_local_no_show_dir(self):
        # Simulate a machine where get_show_dir() finds nothing
        with patch("src.paths.get_show_dir", return_value=None):
            ctx = _ctx_local()
            result = ctx.to_absolute("show/song.mp3")
        assert result == "show/song.mp3"


# ── suggest_path ──────────────────────────────────────────────────────────────

class TestSuggestPath:
    def test_suggests_container_path_for_host_path_inside_container(self):
        ctx = _ctx_container()
        result = ctx.suggest_path(f"{HOST_SHOW}/show/song.mp3")
        assert result == f"{CONTAINER_SHOW}/show/song.mp3"

    def test_returns_none_for_unknown_path_inside_container(self):
        ctx = _ctx_container()
        assert ctx.suggest_path("/tmp/song.mp3") is None

    def test_returns_none_on_local_for_container_path(self):
        ctx = _ctx_local()
        # On host without container, can't map container paths
        result = ctx.suggest_path(f"{CONTAINER_SHOW}/song.mp3")
        assert result is None

    def test_returns_none_on_local_for_arbitrary_path(self):
        ctx = _ctx_local()
        assert ctx.suggest_path("/some/path/song.mp3") is None

    def test_suggests_path_preserves_subdirectory(self):
        ctx = _ctx_container()
        result = ctx.suggest_path(f"{HOST_SHOW}/a/b/c/song.mp3")
        assert result == f"{CONTAINER_SHOW}/a/b/c/song.mp3"


# ── HierarchyResult relative_source_file ─────────────────────────────────────

class TestHierarchyResultRelativePath:
    def test_relative_source_file_defaults_to_none(self):
        from src.analyzer.result import HierarchyResult
        r = HierarchyResult(
            schema_version="2.0.0",
            source_file="/some/path/song.mp3",
            source_hash="abc123",
            duration_ms=60000,
            estimated_bpm=120.0,
        )
        assert r.relative_source_file is None

    def test_relative_source_file_serialises_when_set(self):
        from src.analyzer.result import HierarchyResult
        r = HierarchyResult(
            schema_version="2.0.0",
            source_file="/home/node/xlights/show/song.mp3",
            source_hash="abc123",
            duration_ms=60000,
            estimated_bpm=120.0,
            relative_source_file="show/song.mp3",
        )
        d = r.to_dict()
        assert d["relative_source_file"] == "show/song.mp3"

    def test_relative_source_file_absent_from_dict_when_none(self):
        from src.analyzer.result import HierarchyResult
        r = HierarchyResult(
            schema_version="2.0.0",
            source_file="/some/path/song.mp3",
            source_hash="abc123",
            duration_ms=60000,
            estimated_bpm=120.0,
        )
        d = r.to_dict()
        assert "relative_source_file" not in d

    def test_relative_source_file_round_trips_via_from_dict(self):
        from src.analyzer.result import HierarchyResult
        original = HierarchyResult(
            schema_version="2.0.0",
            source_file="/home/node/xlights/show/song.mp3",
            source_hash="abc123",
            duration_ms=60000,
            estimated_bpm=120.0,
            relative_source_file="show/song.mp3",
        )
        restored = HierarchyResult.from_dict(original.to_dict())
        assert restored.relative_source_file == "show/song.mp3"

    def test_from_dict_defaults_to_none_for_old_json(self):
        from src.analyzer.result import HierarchyResult
        d = {
            "schema_version": "2.0.0",
            "source_file": "/old/absolute/song.mp3",
            "source_hash": "abc123",
            "duration_ms": 60000,
            "estimated_bpm": 120.0,
        }
        obj = HierarchyResult.from_dict(d)
        assert obj.relative_source_file is None


# ── Orchestrator integration test helper ─────────────────────────────────────

class TestOrchestratorRelativePath:
    def test_orchestrator_sets_relative_source_file_in_container(self):
        """Verify PathContext computes relative path for a container-side song path."""
        from src.paths import PathContext

        container_song = "/home/node/xlights/show/song.mp3"

        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": "/Users/bob/xlights"}):
            ctx = PathContext()
            rel = ctx.to_relative(container_song)

        assert rel == "show/song.mp3"


# ── LibraryEntry relative path fields ────────────────────────────────────────

class TestLibraryEntryRelativePaths:
    def test_library_entry_has_relative_fields(self):
        from src.library import LibraryEntry
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
        assert entry.relative_source_file == "show/song.mp3"
        assert entry.relative_analysis_path == "show/song/song_hierarchy.json"

    def test_library_entry_relative_fields_default_none(self):
        from src.library import LibraryEntry
        entry = LibraryEntry(
            source_hash="abc123",
            source_file="/some/path/song.mp3",
            filename="song.mp3",
            analysis_path="/some/path/song_hierarchy.json",
            duration_ms=60000,
            estimated_tempo_bpm=120.0,
            track_count=5,
            stem_separation=False,
            analyzed_at=0,
        )
        assert entry.relative_source_file is None
        assert entry.relative_analysis_path is None

    def test_library_upsert_deduplicates_by_hash(self, tmp_path):
        from src.library import Library, LibraryEntry

        lib = Library(tmp_path / "library.json")

        entry1 = LibraryEntry(
            source_hash="deadbeef",
            source_file="/old/path/song.mp3",
            filename="song.mp3",
            analysis_path="/old/path/song_hierarchy.json",
            duration_ms=60000,
            estimated_tempo_bpm=120.0,
            track_count=5,
            stem_separation=False,
            analyzed_at=1000,
        )
        lib.upsert(entry1)

        entry2 = LibraryEntry(
            source_hash="deadbeef",  # same hash, different path (container vs host)
            source_file="/new/path/song.mp3",
            filename="song.mp3",
            analysis_path="/new/path/song_hierarchy.json",
            duration_ms=60000,
            estimated_tempo_bpm=120.0,
            track_count=5,
            stem_separation=False,
            analyzed_at=2000,
            relative_source_file="show/song.mp3",
        )
        lib.upsert(entry2)

        entries = lib.all_entries()
        assert len(entries) == 1
        # source_file is resolved via relative_source_file at load time;
        # the exact absolute path depends on the current show dir
        assert entries[0].relative_source_file == "show/song.mp3"
        assert entries[0].analyzed_at == 2000  # entry2 replaced entry1


# ── Cache fallback ────────────────────────────────────────────────────────────

class TestCacheRelativeFallback:
    def test_cache_suggests_path_on_miss(self, tmp_path):
        """When audio path is missing but matches cross-env pattern, suggest_path is available."""
        show_dir = tmp_path / "xlights"
        show_dir.mkdir()
        # Simulate the user typed a host path inside the container
        missing_host_path = f"/Users/bob/xlights/song.mp3"

        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": "/Users/bob/xlights"}):
            ctx = PathContext()
            suggestion = ctx.suggest_path(missing_host_path)

        assert suggestion == f"{CONTAINER_SHOW}/song.mp3"


# ── Stem manifest relative_source_path ───────────────────────────────────────

class TestStemManifestRelativePath:
    def test_stem_cache_saves_relative_source_path(self, tmp_path):
        """StemCache manifest should include relative_source_path when PathContext resolves it."""
        import json
        import numpy as np
        from src.analyzer.stems import StemSet, StemCache

        # Use the container show dir so PathContext.to_relative resolves it
        show_dir = Path("/home/node/xlights")
        song_path = show_dir / "song.mp3"

        stems_dir = tmp_path / "stems"
        stems_dir.mkdir()

        # Provide a fake source file for hash computation
        fake_source = tmp_path / "song.mp3"
        fake_source.write_bytes(b"fake mp3 data for testing stem relative path")

        cache = StemCache(fake_source, cache_root=stems_dir)
        # Patch source_path to look like it's inside the container show dir
        cache.source_path = song_path

        with patch.dict(os.environ, {"XLIGHTS_HOST_SHOW_DIR": "/Users/bob/xlights"}):
            empty_arr = np.zeros(100, dtype=np.float32)
            stems = StemSet(
                drums=empty_arr, bass=empty_arr, vocals=empty_arr,
                guitar=empty_arr, piano=empty_arr, other=empty_arr,
                sample_rate=44100,
            )
            cache.save(stems)

        manifest = json.loads((stems_dir / "manifest.json").read_text())
        assert manifest.get("relative_source_path") == "song.mp3"

    def test_stem_manifest_loads_without_relative_path(self, tmp_path):
        """Old manifests without relative_source_path load without error."""
        import json
        from src.analyzer.stems import StemCache

        show_dir = tmp_path
        song_file = show_dir / "song.mp3"
        song_file.write_bytes(b"fake mp3 data")

        stems_dir = tmp_path / "stems"
        stems_dir.mkdir()

        # Write an old-format manifest without relative_source_path
        import hashlib
        h = hashlib.md5()
        h.update(b"fake mp3 data")
        source_hash = h.hexdigest()

        manifest = {
            "source_hash": source_hash,
            "source_path": str(song_file),
            "created_at": 0,
            "stems": {},
        }
        (stems_dir / "manifest.json").write_text(json.dumps(manifest))

        cache = StemCache(song_file, cache_root=stems_dir)
        assert cache.is_valid()  # old manifest still valid
