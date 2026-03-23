"""Unit tests for Library and LibraryEntry — written before implementation (RED phase)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _entry(source_hash: str = "abc123", analyzed_at: int = 1000, **kwargs):
    from src.library import LibraryEntry
    defaults = dict(
        source_hash=source_hash,
        source_file=f"/music/{source_hash}.mp3",
        filename=f"{source_hash}.mp3",
        analysis_path=f"/music/{source_hash}_analysis.json",
        duration_ms=180000,
        estimated_tempo_bpm=128.0,
        track_count=18,
        stem_separation=False,
        analyzed_at=analyzed_at,
    )
    defaults.update(kwargs)
    return LibraryEntry(**defaults)


class TestLibraryUpsert:
    def test_upsert_adds_entry(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        lib.upsert(_entry("hash1"))
        entries = lib.all_entries()
        assert len(entries) == 1
        assert entries[0].source_hash == "hash1"

    def test_upsert_replaces_existing_by_hash(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        lib.upsert(_entry("hash1", analyzed_at=1000))
        lib.upsert(_entry("hash1", analyzed_at=2000))
        entries = lib.all_entries()
        assert len(entries) == 1
        assert entries[0].analyzed_at == 2000

    def test_upsert_preserves_other_entries(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        lib.upsert(_entry("hash1", analyzed_at=1000))
        lib.upsert(_entry("hash2", analyzed_at=2000))
        lib.upsert(_entry("hash1", analyzed_at=3000))  # update hash1
        entries = lib.all_entries()
        assert len(entries) == 2
        hashes = {e.source_hash for e in entries}
        assert hashes == {"hash1", "hash2"}

    def test_upsert_multiple_distinct_entries(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        lib.upsert(_entry("hash1", analyzed_at=1000))
        lib.upsert(_entry("hash2", analyzed_at=2000))
        lib.upsert(_entry("hash3", analyzed_at=3000))
        entries = lib.all_entries()
        assert len(entries) == 3


class TestLibraryAllEntries:
    def test_sorted_newest_first(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        lib.upsert(_entry("hash1", analyzed_at=1000))
        lib.upsert(_entry("hash2", analyzed_at=3000))
        lib.upsert(_entry("hash3", analyzed_at=2000))
        entries = lib.all_entries()
        assert [e.source_hash for e in entries] == ["hash2", "hash3", "hash1"]

    def test_returns_empty_list_when_no_library_file(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        assert lib.all_entries() == []

    def test_returns_library_entry_instances(self, tmp_path):
        from src.library import Library, LibraryEntry
        lib = Library(tmp_path / "library.json")
        lib.upsert(_entry("hash1"))
        entries = lib.all_entries()
        assert all(isinstance(e, LibraryEntry) for e in entries)


class TestLibraryFindByHash:
    def test_returns_entry_when_found(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        lib.upsert(_entry("hash1"))
        found = lib.find_by_hash("hash1")
        assert found is not None
        assert found.source_hash == "hash1"
        assert found.filename == "hash1.mp3"

    def test_returns_none_when_not_found(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        assert lib.find_by_hash("nonexistent") is None

    def test_returns_none_on_empty_library(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "library.json")
        assert lib.find_by_hash("anything") is None


class TestLibraryIndexCreation:
    def test_index_file_auto_created_on_upsert(self, tmp_path):
        from src.library import Library
        lib = Library(tmp_path / "xlight" / "library.json")
        lib.upsert(_entry("hash1"))
        assert (tmp_path / "xlight" / "library.json").exists()

    def test_index_contains_version(self, tmp_path):
        from src.library import Library
        index_path = tmp_path / "library.json"
        lib = Library(index_path)
        lib.upsert(_entry("hash1"))
        data = json.loads(index_path.read_text())
        assert data["version"] == "1.0"

    def test_backward_compat_missing_version_field(self, tmp_path):
        from src.library import Library
        index_path = tmp_path / "library.json"
        index_path.write_text(json.dumps({"entries": []}), encoding="utf-8")
        lib = Library(index_path)
        lib.upsert(_entry("hash1"))
        entries = lib.all_entries()
        assert len(entries) == 1

    def test_backward_compat_corrupt_json_treated_as_empty(self, tmp_path):
        from src.library import Library
        index_path = tmp_path / "library.json"
        index_path.write_text("not valid json", encoding="utf-8")
        lib = Library(index_path)
        assert lib.all_entries() == []
        lib.upsert(_entry("hash1"))
        assert len(lib.all_entries()) == 1
