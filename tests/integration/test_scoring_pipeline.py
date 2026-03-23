"""Integration tests for the scoring pipeline — breakdowns in JSON output."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.analyzer.result import AnalysisResult, TimingMark, TimingTrack, ScoreBreakdown
from src.analyzer.scorer import score_all_tracks
from src.analyzer.scoring_config import ScoringConfig
from src import export as export_mod
from tests.fixtures.scoring.tracks import (
    BEAT_TRACK,
    BAR_TRACK,
    SEGMENT_TRACK,
    SONG_DURATION_MS,
)


def _make_minimal_result(tracks: list[TimingTrack]) -> AnalysisResult:
    return AnalysisResult(
        schema_version="1.0",
        source_file="/tmp/test.mp3",
        filename="test.mp3",
        duration_ms=SONG_DURATION_MS,
        sample_rate=44100,
        estimated_tempo_bpm=120.0,
        run_timestamp="2026-03-23T00:00:00Z",
        algorithms=[],
        timing_tracks=tracks,
    )


class TestScoreBreakdownInJSON:
    def test_breakdowns_present_after_scoring(self):
        tracks = [BEAT_TRACK, BAR_TRACK, SEGMENT_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)
        for t in tracks:
            assert t.score_breakdown is not None

    def test_breakdowns_in_serialized_json(self):
        tracks = [BEAT_TRACK, BAR_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)
        result = _make_minimal_result(tracks)
        d = result.to_dict()
        for track_d in d["timing_tracks"]:
            assert "score_breakdown" in track_d, f"Missing score_breakdown on {track_d['name']}"

    def test_breakdown_has_all_five_criteria_in_json(self):
        tracks = [BEAT_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)
        result = _make_minimal_result(tracks)
        d = result.to_dict()
        breakdown = d["timing_tracks"][0]["score_breakdown"]
        criterion_names = {c["name"] for c in breakdown["criteria"]}
        assert criterion_names == {"density", "regularity", "mark_count", "coverage", "min_gap"}

    def test_roundtrip_json_preserves_breakdowns(self):
        tracks = [BEAT_TRACK, SEGMENT_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)
        result = _make_minimal_result(tracks)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            export_mod.write(result, tmp_path)
            loaded = export_mod.read(tmp_path)
            for t in loaded.timing_tracks:
                assert t.score_breakdown is not None
                assert len(t.score_breakdown.criteria) == 5
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_criterion_labels_in_json(self):
        tracks = [BEAT_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)
        result = _make_minimal_result(tracks)
        d = result.to_dict()
        breakdown = d["timing_tracks"][0]["score_breakdown"]
        for crit in breakdown["criteria"]:
            assert len(crit["label"]) > 10  # has meaningful content

    def test_backward_compat_no_breakdown_loads_fine(self):
        """Analysis JSON without score_breakdown field loads without error."""
        result = _make_minimal_result([BEAT_TRACK])
        d = result.to_dict()
        # Remove score_breakdown as if it was an old analysis file
        for track_d in d["timing_tracks"]:
            track_d.pop("score_breakdown", None)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(d, f)
            tmp_path = f.name

        try:
            loaded = export_mod.read(tmp_path)
            for t in loaded.timing_tracks:
                assert t.score_breakdown is None  # gracefully missing
        finally:
            Path(tmp_path).unlink(missing_ok=True)
