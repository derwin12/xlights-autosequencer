"""Unit tests for the DiversityFilter."""
from __future__ import annotations

import pytest

from src.analyzer.diversity import DiversityFilter
from src.analyzer.result import TimingMark, TimingTrack
from src.analyzer.scorer import score_all_tracks
from src.analyzer.scoring_config import ScoringConfig
from tests.fixtures.scoring.tracks import (
    BEAT_TRACK,
    BEAT_TRACK_CLONE,
    BAR_TRACK,
    SEGMENT_TRACK,
    SONG_DURATION_MS,
)


def _make_track(name: str, marks_ms: list[int], alg: str = "test") -> TimingTrack:
    return TimingTrack(
        name=name, algorithm_name=alg, element_type="beat",
        marks=[TimingMark(t, 1.0) for t in marks_ms],
        quality_score=0.0,
    )


class TestDiversityFilter:
    def test_near_identical_tracks_deduplicated(self):
        # BEAT_TRACK and BEAT_TRACK_CLONE are 5ms apart — should be near-identical at 50ms tol
        tracks = [BEAT_TRACK, BEAT_TRACK_CLONE, BAR_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)

        flt = DiversityFilter(tolerance_ms=50, threshold=0.90)
        selected, skipped = flt.filter(tracks, n=3)

        assert len(selected) <= 3
        # The clone should have been detected as near-identical
        all_names = [t.name for t in selected] + [t.name for t in skipped]
        assert BEAT_TRACK.name in all_names or BEAT_TRACK_CLONE.name in all_names

    def test_duplicate_of_field_set_on_skipped(self):
        tracks = [BEAT_TRACK, BEAT_TRACK_CLONE, BAR_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)

        flt = DiversityFilter(tolerance_ms=50, threshold=0.90)
        selected, skipped = flt.filter(tracks, n=3)

        for t in skipped:
            assert t.score_breakdown is not None
            assert t.score_breakdown.skipped_as_duplicate is True
            assert t.score_breakdown.duplicate_of is not None

    def test_distinct_tracks_all_selected(self):
        tracks = [BEAT_TRACK, BAR_TRACK, SEGMENT_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)

        flt = DiversityFilter(tolerance_ms=50, threshold=0.90)
        selected, skipped = flt.filter(tracks, n=3)

        # All three are distinct categories — should all be selected
        assert len(skipped) == 0
        assert len(selected) == 3

    def test_high_threshold_disables_dedup(self):
        """Very high threshold (0.999) means only essentially-perfect duplicates are skipped.
        Tracks with only ~50% overlap are not considered near-identical."""
        # Create two tracks with ~50% mark overlap
        marks_a = list(range(0, 10000, 200))  # every 200ms
        marks_b = list(range(100, 10100, 400))  # every 400ms, offset 100ms from a
        t_a = _make_track("ta", marks_a, alg="librosa_beats")
        t_b = _make_track("tb", marks_b, alg="madmom_beats")
        score_all_tracks([t_a, t_b], 10000)

        flt = DiversityFilter(tolerance_ms=50, threshold=0.999)
        selected, skipped = flt.filter([t_a, t_b], n=2)
        # At very high threshold, ~50% similar tracks are not near-identical
        assert len(selected) == 2
        assert len(skipped) == 0

    def test_low_threshold_more_aggressive_dedup(self):
        """Low threshold (0.40) flags tracks with ≥40% similarity as near-identical."""
        # ~50% similar tracks: at threshold=0.40 they WILL be considered near-identical
        marks_a = list(range(0, 10000, 200))  # 50 marks
        marks_b = list(range(0, 10000, 400))  # 25 marks, subset of a
        t_a = _make_track("ta2", marks_a, alg="librosa_beats")
        t_b = _make_track("tb2", marks_b, alg="madmom_beats")
        score_all_tracks([t_a, t_b], 10000)

        flt = DiversityFilter(tolerance_ms=50, threshold=0.40)
        selected, skipped = flt.filter([t_a, t_b], n=2)
        # t_b's marks are all in t_a (fwd=1.0), t_a has 50% in t_b (rev=0.5) → min=0.5 ≥ 0.40
        assert len(skipped) == 1

    def test_configurable_tolerance_ms(self):
        """Tighter tolerance means fewer marks match."""
        tracks = [BEAT_TRACK, BEAT_TRACK_CLONE, BAR_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)

        # 1ms tolerance — 5ms offset clone should NOT match
        flt_tight = DiversityFilter(tolerance_ms=1, threshold=0.90)
        selected_tight, skipped_tight = flt_tight.filter(tracks, n=3)
        assert len(selected_tight) == 3  # clone not detected as near-identical

        # 50ms tolerance — 5ms offset clone SHOULD match
        flt_loose = DiversityFilter(tolerance_ms=50, threshold=0.90)
        selected_loose, skipped_loose = flt_loose.filter(tracks, n=3)
        assert len(skipped_loose) >= 1  # clone detected

    def test_respects_n_limit(self):
        tracks = [BEAT_TRACK, BAR_TRACK, SEGMENT_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)

        flt = DiversityFilter(tolerance_ms=50, threshold=0.90)
        selected, _ = flt.filter(tracks, n=2)
        assert len(selected) == 2

    def test_empty_track_list(self):
        flt = DiversityFilter(tolerance_ms=50, threshold=0.90)
        selected, skipped = flt.filter([], n=3)
        assert selected == []
        assert skipped == []

    def test_exact_duplicate_detected(self):
        """Track with same marks as another should be detected as near-identical."""
        marks_ms = [0, 500, 1000, 1500, 2000]
        t1 = _make_track("t1", marks_ms, alg="librosa_beats")
        t2 = _make_track("t2", marks_ms, alg="madmom_beats")
        score_all_tracks([t1, t2], 10000)

        flt = DiversityFilter(tolerance_ms=50, threshold=0.90)
        selected, skipped = flt.filter([t1, t2], n=2)
        assert len(skipped) == 1
        assert skipped[0].score_breakdown.skipped_as_duplicate is True
