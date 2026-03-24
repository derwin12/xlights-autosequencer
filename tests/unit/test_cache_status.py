"""Tests for CacheStatus.from_audio_path() — T016 (RED phase before CacheStatus impl)."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from src.analyzer.result import AnalysisResult, TimingMark, TimingTrack
from src import export as export_mod


def _minimal_result(audio_path: Path, source_hash: str | None = None, tracks: int = 2) -> AnalysisResult:
    timing_tracks = [
        TimingTrack(f"track_{i}", f"algo_{i}", "beat", [TimingMark(500 * i, None)], 0.8)
        for i in range(tracks)
    ]
    result = AnalysisResult(
        schema_version="1.0",
        source_file=str(audio_path),
        filename=audio_path.name,
        duration_ms=10000,
        sample_rate=22050,
        estimated_tempo_bpm=120.0,
        run_timestamp="2026-03-24T10:00:00Z",
        algorithms=[],
        timing_tracks=timing_tracks,
    )
    result.source_hash = source_hash
    return result


class TestCacheStatusFromAudioPath:
    """CacheStatus.from_audio_path() factory method."""

    def test_no_cache_file(self, tmp_path):
        from src.cache import CacheStatus
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        status = CacheStatus.from_audio_path(audio)
        assert status.exists is False
        assert status.is_valid is False

    def test_valid_cache(self, tmp_path):
        from src.cache import CacheStatus
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        correct_md5 = hashlib.md5(b"FAKEWAV").hexdigest()
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(audio, source_hash=correct_md5, tracks=3)
        export_mod.write(result, str(output))

        status = CacheStatus.from_audio_path(audio)
        assert status.exists is True
        assert status.is_valid is True
        assert status.track_count == 3

    def test_stale_cache_md5_mismatch(self, tmp_path):
        from src.cache import CacheStatus
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"ORIGINAL")
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(audio, source_hash=hashlib.md5(b"ORIGINAL").hexdigest())
        export_mod.write(result, str(output))

        # Change audio content — now MD5 doesn't match cached hash
        audio.write_bytes(b"CHANGED_CONTENT")
        status = CacheStatus.from_audio_path(audio)
        assert status.exists is True
        assert status.is_valid is False

    def test_cache_age_seconds(self, tmp_path):
        from src.cache import CacheStatus
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        correct_md5 = hashlib.md5(b"FAKEWAV").hexdigest()
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(audio, source_hash=correct_md5)
        export_mod.write(result, str(output))

        before = time.time()
        status = CacheStatus.from_audio_path(audio)
        assert status.age_seconds is not None
        assert 0 <= status.age_seconds <= (time.time() - before + 2)

    def test_no_cache_has_none_age(self, tmp_path):
        from src.cache import CacheStatus
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        status = CacheStatus.from_audio_path(audio)
        assert status.age_seconds is None

    def test_explicit_output_path(self, tmp_path):
        from src.cache import CacheStatus
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        correct_md5 = hashlib.md5(b"FAKEWAV").hexdigest()
        custom_output = tmp_path / "custom_dir" / "my_analysis.json"
        custom_output.parent.mkdir()
        result = _minimal_result(audio, source_hash=correct_md5)
        export_mod.write(result, str(custom_output))

        status = CacheStatus.from_audio_path(audio, output_path=custom_output)
        assert status.exists is True
        assert status.is_valid is True
