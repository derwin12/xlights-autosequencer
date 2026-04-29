"""Unit tests for the ID3 confirmation prompt + atomic write-back (§6a).

Covers ``src.review.server.read_id3_metadata`` and
``src.review.server.write_id3_metadata_atomic`` per OpenSpec change
``lyric-anchored-boundary-refinement`` §6a.

The atomic-write-with-backup pattern: write the original bytes to a
sibling ``.bak`` first, then write the new content to a temp path in
the same directory, then ``os.replace`` it into place. On any failure
between backup and rename, the ``.bak`` MUST remain so the user can
recover by hand.
"""
from __future__ import annotations

import os
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from src.review.server import read_id3_metadata, write_id3_metadata_atomic


# A real fixture MP3 with valid ID3 metadata. Artist="Kevin MacLeod",
# no title. Used for read/write round-trip tests.
_FIXTURE_MP3 = Path(__file__).resolve().parents[1] / "fixtures" / "cc0_music" / "maple_leaf_rag.mp3"


@pytest.fixture
def fixture_mp3(tmp_path):
    """A tmp-path copy of the real fixture MP3 so tests can mutate freely."""
    if not _FIXTURE_MP3.exists():
        pytest.skip(f"fixture not present: {_FIXTURE_MP3}")
    dst = tmp_path / "song.mp3"
    shutil.copy2(_FIXTURE_MP3, dst)
    return dst


# ── read_id3_metadata ────────────────────────────────────────────────────────

class TestReadId3Metadata:
    def test_reads_existing_tags(self, fixture_mp3):
        title, artist = read_id3_metadata(str(fixture_mp3))
        # The fixture's artist tag is set; title may be empty. Either way
        # we get a string (never None).
        assert isinstance(title, str)
        assert isinstance(artist, str)
        assert artist == "Kevin MacLeod"

    def test_returns_empty_strings_when_no_tags(self, tmp_path, monkeypatch):
        """Mutagen-mocked path: file with no readable ID3 header → ('', '')."""
        # Patch EasyID3 to raise the "no header" exception that real
        # mutagen raises on a tagless file.
        from mutagen.id3 import ID3NoHeaderError

        class _Raises:
            def __init__(self, *a, **kw):
                raise ID3NoHeaderError("no header")

        with patch("mutagen.easyid3.EasyID3", _Raises):
            title, artist = read_id3_metadata(str(tmp_path / "missing.mp3"))
        assert title == ""
        assert artist == ""

    def test_returns_empty_on_unrelated_exception(self, tmp_path):
        """A non-existent file path is read as ('', '') rather than raising."""
        # Read should NOT raise — caller wants graceful empty defaults so
        # the prompt UI prefills empty fields.
        title, artist = read_id3_metadata(str(tmp_path / "does-not-exist.mp3"))
        assert title == ""
        assert artist == ""


# ── write_id3_metadata_atomic ────────────────────────────────────────────────

class TestWriteId3MetadataAtomic:
    def test_writes_new_tags_and_creates_backup(self, fixture_mp3):
        """Happy path: corrected tags land on disk; .bak preserves original bytes."""
        original_bytes = fixture_mp3.read_bytes()
        write_id3_metadata_atomic(
            str(fixture_mp3),
            title="Maple Leaf Rag",
            artist="Scott Joplin",
        )
        # The .bak holds the original file verbatim.
        bak = fixture_mp3.with_name(fixture_mp3.name + ".bak")
        assert bak.exists(), "atomic write must leave a .bak with original bytes"
        assert bak.read_bytes() == original_bytes
        # The corrected file has the new tags.
        new_title, new_artist = read_id3_metadata(str(fixture_mp3))
        assert new_title == "Maple Leaf Rag"
        assert new_artist == "Scott Joplin"

    def test_no_temp_files_left_behind(self, fixture_mp3):
        """After a successful write, the working directory has no .tmp leftovers."""
        write_id3_metadata_atomic(
            str(fixture_mp3), title="X", artist="Y",
        )
        leftovers = [
            p for p in fixture_mp3.parent.iterdir()
            if p.suffix == ".tmp" or ".tmp" in p.name
        ]
        assert leftovers == [], f"expected no .tmp leftovers but found: {leftovers}"

    def test_missing_source_raises_filenotfound(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            write_id3_metadata_atomic(
                str(tmp_path / "does-not-exist.mp3"),
                title="X", artist="Y",
            )

    def test_write_failure_preserves_backup(self, fixture_mp3, monkeypatch):
        """If the os.replace step fails, the .bak survives for recovery.

        Per the spec: "On any failure between write and rename, the
        ``.bak`` stays — don't delete it."
        """
        # Patch os.replace to raise so we simulate an OS-level rename
        # failure (e.g. EACCES, ENOSPC). The .bak should persist; the
        # in-flight .tmp should be cleaned up.
        import src.review.server as server_mod

        def _boom(*a, **kw):
            raise OSError("simulated rename failure")

        monkeypatch.setattr(server_mod.os, "replace", _boom)

        with pytest.raises(OSError, match="simulated rename failure"):
            write_id3_metadata_atomic(
                str(fixture_mp3), title="X", artist="Y",
            )
        # .bak preserved
        bak = fixture_mp3.with_name(fixture_mp3.name + ".bak")
        assert bak.exists()
        # No .tmp leftovers
        leftovers = [p for p in fixture_mp3.parent.iterdir() if p.suffix == ".tmp"]
        assert leftovers == [], f"unexpected .tmp leftovers: {leftovers}"


# ── Job state machine: response branches ─────────────────────────────────────

class TestJobId3Response:
    """The AnalysisJob ID3 response state machine — the API the SSE/HTTP
    routes use to relay user input back to the analyzer thread."""

    def _make_job(self):
        from src.review.server import AnalysisJob
        # Build via __new__ so we don't trigger I/O on construction.
        job = AnalysisJob.__new__(AnalysisJob)
        # Manually init the fields we need; mirror __init__.
        import threading
        job.events = []
        job.lock = threading.Lock()
        job._id3_event = threading.Event()
        job.id3_response = None
        job.id3_corrected_title = None
        job.id3_corrected_artist = None
        job.id3_write_back = False
        return job

    def test_confirm_response(self):
        job = self._make_job()
        job.prompt_id3_confirm("Tee", "Eye")
        # Simulate /id3-confirm POST with response=confirm.
        job.submit_id3_response("confirm")
        assert job.wait_for_id3_response(timeout=0.1) == "confirm"
        assert job.id3_corrected_title is None
        assert job.id3_corrected_artist is None
        assert job.id3_write_back is False

    def test_correct_response_with_write_back(self):
        job = self._make_job()
        job.prompt_id3_confirm("Old Title", "Old Artist")
        job.submit_id3_response(
            "correct", title="New Title", artist="New Artist", write_back=True,
        )
        assert job.wait_for_id3_response(timeout=0.1) == "correct"
        assert job.id3_corrected_title == "New Title"
        assert job.id3_corrected_artist == "New Artist"
        assert job.id3_write_back is True

    def test_skip_response(self):
        job = self._make_job()
        job.prompt_id3_confirm("X", "Y")
        job.submit_id3_response("skip")
        assert job.wait_for_id3_response(timeout=0.1) == "skip"

    def test_prompt_emits_event(self):
        job = self._make_job()
        job.prompt_id3_confirm("Foo", "Bar")
        assert any(
            ev.get("id3_confirm_prompt") and ev.get("id3_title") == "Foo"
            for ev in job.events
        )
