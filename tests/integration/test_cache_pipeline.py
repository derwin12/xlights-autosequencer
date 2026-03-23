"""Integration tests for the analysis cache pipeline (T016).

These tests exercise the full cache lifecycle using synthetic fixture WAVs:
- source_hash is written on the first analysis run
- second run is a cache hit (no algorithm output)
- --no-cache forces a fresh run
- library entry is present and correct after each run

NOTE: These tests run real algorithms against fixture audio. They are slower
than unit tests and require librosa (and optionally vamp/madmom) to be installed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.cache import AnalysisCache
from src.library import Library


# ── Helpers ───────────────────────────────────────────────────────────────────

def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_analyze(audio_path: Path, output_path: Path, no_cache: bool = False) -> None:
    """Run the analyze command via Click's test runner."""
    from click.testing import CliRunner
    from src.cli import cli

    args = ["analyze", str(audio_path), "--output", str(output_path),
            "--no-vamp", "--no-madmom"]
    if no_cache:
        args.append("--no-cache")

    runner = CliRunner()
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"analyze failed:\n{result.output}\n{result.exception}"


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCachePipeline:
    def test_source_hash_written_on_first_run(self, beat_fixture_path, tmp_path):
        out = tmp_path / "song_analysis.json"
        _run_analyze(beat_fixture_path, out)
        data = json.loads(out.read_text())
        assert data.get("source_hash") == _md5(beat_fixture_path)

    def test_second_run_is_cache_hit(self, beat_fixture_path, tmp_path):
        out = tmp_path / "song_analysis.json"
        # First run — full analysis
        _run_analyze(beat_fixture_path, out)
        # Second run — should be a cache hit
        from click.testing import CliRunner
        from src.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, [
            "analyze", str(beat_fixture_path), "--output", str(out),
            "--no-vamp", "--no-madmom",
        ])
        assert result.exit_code == 0
        assert "cache: hit" in result.output.lower()

    def test_no_cache_forces_rerun(self, beat_fixture_path, tmp_path):
        out = tmp_path / "song_analysis.json"
        # First run
        _run_analyze(beat_fixture_path, out)
        # Force re-run
        from click.testing import CliRunner
        from src.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, [
            "analyze", str(beat_fixture_path), "--output", str(out),
            "--no-vamp", "--no-madmom", "--no-cache",
        ])
        assert result.exit_code == 0
        assert "cache: hit" not in result.output.lower()
        assert "cache: miss" in result.output.lower() or "running algorithms" in result.output.lower()

    def test_cache_invalid_after_audio_change(self, tmp_path):
        # Write initial audio
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"ORIGINAL_CONTENT" * 1000)
        out = tmp_path / "song_analysis.json"
        cache = AnalysisCache(audio, out)

        from src.analyzer.result import AnalysisResult, TimingTrack, TimingMark
        from src import export as export_mod

        result = AnalysisResult(
            schema_version="1.0",
            source_file=str(audio),
            filename="song.wav",
            duration_ms=10000,
            sample_rate=22050,
            estimated_tempo_bpm=120.0,
            run_timestamp="2026-03-22T10:00:00Z",
            algorithms=[],
            timing_tracks=[TimingTrack("b", "librosa_beats", "beat", [TimingMark(500, None)], 0.9)],
        )
        cache.save(result)
        assert cache.is_valid() is True

        # Change the audio file
        audio.write_bytes(b"CHANGED_CONTENT" * 1000)
        # New cache instance (clears cached MD5)
        cache2 = AnalysisCache(audio, out)
        assert cache2.is_valid() is False

    def test_library_entry_created_after_run(self, beat_fixture_path, tmp_path):
        library_path = tmp_path / "library.json"
        out = tmp_path / "song_analysis.json"

        # Monkeypatch DEFAULT_LIBRARY_PATH for this test
        import src.library as lib_module
        original_default = lib_module.DEFAULT_LIBRARY_PATH
        lib_module.DEFAULT_LIBRARY_PATH = library_path
        try:
            _run_analyze(beat_fixture_path, out)
        finally:
            lib_module.DEFAULT_LIBRARY_PATH = original_default

        lib = Library(library_path)
        entries = lib.all_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.source_hash == _md5(beat_fixture_path)
        assert entry.filename == beat_fixture_path.name
        assert entry.track_count > 0
        assert entry.duration_ms > 0

    def test_library_entry_updated_on_rerun(self, beat_fixture_path, tmp_path):
        library_path = tmp_path / "library.json"
        out = tmp_path / "song_analysis.json"

        import src.library as lib_module
        original_default = lib_module.DEFAULT_LIBRARY_PATH
        lib_module.DEFAULT_LIBRARY_PATH = library_path
        try:
            _run_analyze(beat_fixture_path, out)
            _run_analyze(beat_fixture_path, out, no_cache=True)
        finally:
            lib_module.DEFAULT_LIBRARY_PATH = original_default

        lib = Library(library_path)
        entries = lib.all_entries()
        # Only one entry per source_hash
        assert len(entries) == 1
