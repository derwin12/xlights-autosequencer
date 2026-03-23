"""Unit tests for AnalysisCache — written before implementation (RED phase)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.analyzer.result import AnalysisAlgorithm, AnalysisResult, TimingMark, TimingTrack
from src import export as export_mod


def _minimal_result(**kwargs) -> AnalysisResult:
    defaults = dict(
        schema_version="1.0",
        source_file="/tmp/song.wav",
        filename="song.wav",
        duration_ms=10000,
        sample_rate=22050,
        estimated_tempo_bpm=120.0,
        run_timestamp="2026-03-22T10:00:00Z",
        algorithms=[],
        timing_tracks=[TimingTrack("beats", "librosa_beats", "beat", [TimingMark(500, None)], 0.9)],
    )
    defaults.update(kwargs)
    return AnalysisResult(**defaults)


class TestAnalysisCacheIsValid:
    def test_returns_false_when_output_missing(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        cache = AnalysisCache(audio, tmp_path / "song_analysis.json")
        assert cache.is_valid() is False

    def test_returns_false_when_source_hash_none(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(source_file=str(audio))
        result.source_hash = None
        export_mod.write(result, str(output))
        cache = AnalysisCache(audio, output)
        assert cache.is_valid() is False

    def test_returns_false_when_md5_mismatch(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(source_file=str(audio))
        result.source_hash = "deadbeef" * 4  # wrong MD5
        export_mod.write(result, str(output))
        cache = AnalysisCache(audio, output)
        assert cache.is_valid() is False

    def test_returns_true_when_md5_matches(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        correct_md5 = hashlib.md5(b"FAKEWAV").hexdigest()
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(source_file=str(audio))
        result.source_hash = correct_md5
        export_mod.write(result, str(output))
        cache = AnalysisCache(audio, output)
        assert cache.is_valid() is True

    def test_returns_false_when_output_json_corrupt(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        output = tmp_path / "song_analysis.json"
        output.write_text("not valid json", encoding="utf-8")
        cache = AnalysisCache(audio, output)
        assert cache.is_valid() is False


class TestAnalysisCacheLoad:
    def test_load_returns_analysis_result(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        correct_md5 = hashlib.md5(b"FAKEWAV").hexdigest()
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(source_file=str(audio))
        result.source_hash = correct_md5
        export_mod.write(result, str(output))
        cache = AnalysisCache(audio, output)
        loaded = cache.load()
        assert isinstance(loaded, AnalysisResult)
        assert loaded.source_hash == correct_md5
        assert loaded.filename == "song.wav"


class TestAnalysisCacheSave:
    def test_save_stamps_source_hash(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"FAKEWAV")
        expected_md5 = hashlib.md5(b"FAKEWAV").hexdigest()
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(source_file=str(audio))
        cache = AnalysisCache(audio, output)
        cache.save(result)
        assert result.source_hash == expected_md5
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["source_hash"] == expected_md5

    def test_save_then_is_valid(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"REALCONTENT")
        output = tmp_path / "song_analysis.json"
        result = _minimal_result(source_file=str(audio))
        cache = AnalysisCache(audio, output)
        cache.save(result)
        assert cache.is_valid() is True

    def test_save_overwrites_existing(self, tmp_path):
        from src.cache import AnalysisCache
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"CONTENT")
        output = tmp_path / "song_analysis.json"
        result1 = _minimal_result(source_file=str(audio))
        cache = AnalysisCache(audio, output)
        cache.save(result1)
        # Change audio content — now a different hash
        audio.write_bytes(b"NEWCONTENT")
        result2 = _minimal_result(source_file=str(audio))
        cache2 = AnalysisCache(audio, output)
        cache2.save(result2)
        data = json.loads(output.read_text())
        assert data["source_hash"] == hashlib.md5(b"NEWCONTENT").hexdigest()
