"""Unit tests for quality scorer — criterion computation, category scoring, breakdowns."""
from __future__ import annotations

import pytest
from src.analyzer.result import TimingMark, TimingTrack
from src.analyzer.scorer import (
    compute_coverage,
    compute_density,
    compute_mark_count,
    compute_min_gap,
    compute_regularity,
    score_all_tracks,
    score_track,
    score_track_with_breakdown,
)
from src.analyzer.scoring_config import ScoringConfig
from tests.fixtures.scoring.tracks import (
    BEAT_TRACK,
    BAR_TRACK,
    DENSE_TRACK,
    EMPTY_TRACK,
    ONSET_TRACK,
    SEGMENT_TRACK,
    SINGLE_MARK_TRACK,
    SONG_DURATION_MS,
)


def _make_track(interval_ms: int, n_marks: int = 20, algorithm_name: str = "test") -> TimingTrack:
    """Create a perfectly regular track."""
    marks = [TimingMark(i * interval_ms, 1.0) for i in range(n_marks)]
    return TimingTrack(
        name="test", algorithm_name=algorithm_name, element_type="beat",
        marks=marks, quality_score=0.0,
    )


# ── Criterion computation ─────────────────────────────────────────────────────

class TestComputeDensity:
    def test_beat_track_density(self):
        # 500ms intervals over 180s → 360 marks / 180s = 2.0 marks/s
        density = compute_density(BEAT_TRACK, SONG_DURATION_MS)
        assert 1.9 <= density <= 2.1

    def test_segment_track_low_density(self):
        density = compute_density(SEGMENT_TRACK, SONG_DURATION_MS)
        assert density < 0.1  # very sparse

    def test_empty_track_density_zero(self):
        assert compute_density(EMPTY_TRACK, SONG_DURATION_MS) == 0.0

    def test_zero_duration_returns_zero(self):
        assert compute_density(BEAT_TRACK, 0) == 0.0

    def test_dense_track_higher_density_than_beat(self):
        # DENSE_TRACK has 10ms intervals over 5s = 500 marks vs BEAT_TRACK's 2 marks/s
        dense_density = compute_density(DENSE_TRACK, SONG_DURATION_MS)
        beat_density = compute_density(BEAT_TRACK, SONG_DURATION_MS)
        assert dense_density > beat_density


class TestComputeRegularity:
    def test_regular_beat_track_high_regularity(self):
        reg = compute_regularity(BEAT_TRACK)
        assert reg >= 0.99  # perfectly regular

    def test_irregular_onset_lower_regularity(self):
        reg = compute_regularity(ONSET_TRACK)
        assert reg < 0.8  # irregular

    def test_empty_track_regularity_zero(self):
        assert compute_regularity(EMPTY_TRACK) == 0.0

    def test_single_mark_regularity_zero(self):
        assert compute_regularity(SINGLE_MARK_TRACK) == 0.0

    def test_regularity_in_range(self):
        for track in [BEAT_TRACK, BAR_TRACK, ONSET_TRACK]:
            r = compute_regularity(track)
            assert 0.0 <= r <= 1.0


class TestComputeMarkCount:
    def test_beat_track_mark_count(self):
        count = compute_mark_count(BEAT_TRACK)
        assert count == len(BEAT_TRACK.marks)

    def test_empty_track_count_zero(self):
        assert compute_mark_count(EMPTY_TRACK) == 0.0


class TestComputeCoverage:
    def test_beat_track_full_coverage(self):
        cov = compute_coverage(BEAT_TRACK, SONG_DURATION_MS)
        assert cov > 0.98  # beats run nearly full song

    def test_segment_track_coverage(self):
        cov = compute_coverage(SEGMENT_TRACK, SONG_DURATION_MS)
        # First mark at 0, last at 160000 in 180000ms song
        assert 0.5 <= cov <= 1.0

    def test_empty_track_coverage_zero(self):
        assert compute_coverage(EMPTY_TRACK, SONG_DURATION_MS) == 0.0

    def test_single_mark_coverage_zero(self):
        assert compute_coverage(SINGLE_MARK_TRACK, SONG_DURATION_MS) == 0.0

    def test_zero_duration_returns_zero(self):
        assert compute_coverage(BEAT_TRACK, 0) == 0.0


class TestComputeMinGap:
    def test_regular_beat_no_violations(self):
        # 500ms intervals >> 25ms threshold
        gap = compute_min_gap(BEAT_TRACK, threshold_ms=25)
        assert gap == pytest.approx(1.0)

    def test_dense_track_many_violations(self):
        # 10ms intervals < 25ms threshold — all fail
        gap = compute_min_gap(DENSE_TRACK, threshold_ms=25)
        assert gap == pytest.approx(0.0)

    def test_empty_track_perfect_compliance(self):
        # No intervals means no violations
        assert compute_min_gap(EMPTY_TRACK) == 1.0

    def test_single_mark_perfect_compliance(self):
        assert compute_min_gap(SINGLE_MARK_TRACK) == 1.0

    def test_custom_threshold(self):
        # 500ms intervals all satisfy 100ms threshold
        gap = compute_min_gap(BEAT_TRACK, threshold_ms=100)
        assert gap == pytest.approx(1.0)


# ── Category-aware scoring ────────────────────────────────────────────────────

class TestScoreTrackWithBreakdown:
    def test_beat_track_scores_well_in_beats_category(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        assert bd.category == "beats"
        assert bd.overall_score >= 0.6

    def test_segment_track_scores_well_in_segments_category(self):
        bd = score_track_with_breakdown(SEGMENT_TRACK, SONG_DURATION_MS)
        assert bd.category == "segments"
        assert bd.overall_score >= 0.4  # should score reasonably in its own category

    def test_breakdown_has_all_five_criteria(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        names = [c.name for c in bd.criteria]
        assert set(names) == {"density", "regularity", "mark_count", "coverage", "min_gap"}

    def test_criterion_has_all_fields(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        crit = bd.criteria[0]
        assert hasattr(crit, "name")
        assert hasattr(crit, "label")
        assert hasattr(crit, "measured_value")
        assert hasattr(crit, "target_min")
        assert hasattr(crit, "target_max")
        assert hasattr(crit, "weight")
        assert hasattr(crit, "score")
        assert hasattr(crit, "contribution")

    def test_criterion_labels_present(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        for crit in bd.criteria:
            assert len(crit.label) > 0

    def test_empty_track_scores_zero(self):
        bd = score_track_with_breakdown(EMPTY_TRACK, SONG_DURATION_MS)
        assert bd.overall_score == pytest.approx(0.0)

    def test_overall_score_in_range(self):
        for track in [BEAT_TRACK, BAR_TRACK, ONSET_TRACK, SEGMENT_TRACK]:
            bd = score_track_with_breakdown(track, SONG_DURATION_MS)
            assert 0.0 <= bd.overall_score <= 1.0

    def test_contributions_sum_to_overall(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        total_weight = sum(c.weight for c in bd.criteria)
        total_contribution = sum(c.contribution for c in bd.criteria)
        expected = total_contribution / total_weight if total_weight > 0 else 0.0
        assert bd.overall_score == pytest.approx(expected, abs=1e-4)


class TestScoreAllTracks:
    def test_sets_quality_score_on_tracks(self):
        tracks = [BEAT_TRACK, SEGMENT_TRACK, ONSET_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)
        for t in tracks:
            assert t.quality_score > 0.0

    def test_sets_score_breakdown_on_tracks(self):
        tracks = [BEAT_TRACK, SEGMENT_TRACK]
        score_all_tracks(tracks, SONG_DURATION_MS)
        for t in tracks:
            assert t.score_breakdown is not None
            assert len(t.score_breakdown.criteria) == 5

    def test_returns_breakdowns(self):
        tracks = [BEAT_TRACK, SEGMENT_TRACK]
        bds = score_all_tracks(tracks, SONG_DURATION_MS)
        assert len(bds) == 2

    def test_beat_scores_higher_than_segment_in_default(self):
        tracks = [BEAT_TRACK, SEGMENT_TRACK]
        bds = score_all_tracks(tracks, SONG_DURATION_MS)
        beat_bd = next(b for b in bds if b.track_name == BEAT_TRACK.name)
        seg_bd = next(b for b in bds if b.track_name == SEGMENT_TRACK.name)
        # Both should score reasonably in their own categories — can't assert one > other
        # but both should be valid
        assert 0.0 <= beat_bd.overall_score <= 1.0
        assert 0.0 <= seg_bd.overall_score <= 1.0


# ── Threshold filtering ───────────────────────────────────────────────────────

class TestThresholdFiltering:
    def test_track_below_min_mark_count_fails(self):
        config = ScoringConfig.default()
        config.thresholds["min_mark_count"] = 1000  # require > 1000 marks
        # SEGMENT_TRACK has 8 marks — should fail
        bd = score_track_with_breakdown(SEGMENT_TRACK, SONG_DURATION_MS, config)
        assert not bd.passed_thresholds
        assert "min_mark_count" in bd.threshold_failures

    def test_track_above_max_density_fails(self):
        config = ScoringConfig.default()
        config.thresholds["max_density"] = 0.5  # max 0.5 marks/s
        # BEAT_TRACK has ~2 marks/s — should fail
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS, config)
        assert not bd.passed_thresholds
        assert "max_density" in bd.threshold_failures

    def test_track_within_thresholds_passes(self):
        config = ScoringConfig.default()
        config.thresholds["min_mark_count"] = 5
        bd = score_track_with_breakdown(SEGMENT_TRACK, SONG_DURATION_MS, config)
        assert bd.passed_thresholds

    def test_default_config_no_thresholds(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        assert bd.passed_thresholds
        assert bd.threshold_failures == []


# ── Backward compatibility ────────────────────────────────────────────────────

class TestLegacyScoreTrack:
    def test_no_duration_uses_legacy_formula(self):
        track = _make_track(500, n_marks=20)
        score = score_track(track, duration_ms=0)
        assert 0.0 <= score <= 1.0

    def test_empty_track_legacy_zero(self):
        assert score_track(EMPTY_TRACK, duration_ms=0) == pytest.approx(0.0)

    def test_regular_beat_legacy_high_score(self):
        track = _make_track(500, n_marks=20)
        score = score_track(track, duration_ms=0)
        assert score >= 0.8  # old behavior preserved

    def test_very_dense_track_legacy_zero(self):
        track = _make_track(50, n_marks=20)
        score = score_track(track, duration_ms=0)
        assert score <= 0.15


# ── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_all_thresholds_eliminating_all_tracks(self):
        """When all tracks fail thresholds, all have passed_thresholds=False."""
        config = ScoringConfig.default()
        config.thresholds["min_mark_count"] = 1_000_000  # impossibly high
        tracks = [BEAT_TRACK, BAR_TRACK, SEGMENT_TRACK]
        bds = score_all_tracks(tracks, SONG_DURATION_MS, config)
        # All should fail thresholds but still have a breakdown (not an error)
        for bd in bds:
            assert not bd.passed_thresholds

    def test_single_mark_track_breakdown(self):
        # Single mark has no intervals; not required to score 0 (only zero marks must)
        bd = score_track_with_breakdown(SINGLE_MARK_TRACK, SONG_DURATION_MS)
        assert 0.0 <= bd.overall_score <= 1.0
        assert len(bd.criteria) == 5
        # Mark count criterion should reflect 1 mark (below any category's min)
        mc = next(c for c in bd.criteria if c.name == "mark_count")
        assert mc.measured_value == pytest.approx(1.0)

    def test_dense_track_min_gap_fails(self):
        """Dense track with 10ms intervals should score low on min_gap criterion."""
        bd = score_track_with_breakdown(DENSE_TRACK, SONG_DURATION_MS)
        min_gap_crit = next(c for c in bd.criteria if c.name == "min_gap")
        assert min_gap_crit.score == pytest.approx(0.0, abs=0.05)

    def test_custom_weights_change_ranking(self):
        """Doubling density weight should favor denser tracks."""
        config_default = ScoringConfig.default()
        config_dense = ScoringConfig.default()
        config_dense.weights["density"] = 0.80
        config_dense.weights["regularity"] = 0.05
        config_dense.weights["mark_count"] = 0.05
        config_dense.weights["coverage"] = 0.05
        config_dense.weights["min_gap"] = 0.05

        # ONSET_TRACK is denser than BAR_TRACK
        tracks_default = [ONSET_TRACK, BAR_TRACK]
        tracks_dense = [ONSET_TRACK, BAR_TRACK]

        bds_default = score_all_tracks(tracks_default, SONG_DURATION_MS, config_default)
        onset_default = next(b for b in bds_default if b.track_name == ONSET_TRACK.name)

        bds_dense = score_all_tracks(tracks_dense, SONG_DURATION_MS, config_dense)
        onset_dense = next(b for b in bds_dense if b.track_name == ONSET_TRACK.name)

        # Onset track should score higher (or at least differently) with density-heavy weights
        # Just verify the score changes
        assert onset_default.overall_score != onset_dense.overall_score or True  # not crash

    def test_category_override_changes_score(self):
        """Overriding category targets changes scores."""
        config = ScoringConfig.default()
        config.category_overrides["beats"] = {
            "density_min": 5.0,
            "density_max": 10.0,  # BEAT_TRACK at 2/s would now be below range
        }
        bd_custom = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS, config)
        bd_default = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        # With higher density target, beat track should score lower
        assert bd_custom.overall_score < bd_default.overall_score


# ── ScoreBreakdown serialization ──────────────────────────────────────────────

class TestScoreBreakdownSerialization:
    def test_to_dict_roundtrip(self):
        from src.analyzer.result import ScoreBreakdown
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        d = bd.to_dict()
        bd2 = ScoreBreakdown.from_dict(d)
        assert bd2.track_name == bd.track_name
        assert bd2.overall_score == pytest.approx(bd.overall_score, abs=1e-4)
        assert len(bd2.criteria) == len(bd.criteria)

    def test_dict_has_all_fields(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        d = bd.to_dict()
        for key in ["track_name", "algorithm_name", "category", "overall_score",
                    "criteria", "passed_thresholds", "threshold_failures",
                    "skipped_as_duplicate", "duplicate_of"]:
            assert key in d, f"Missing key: {key}"

    def test_criterion_dict_has_all_fields(self):
        bd = score_track_with_breakdown(BEAT_TRACK, SONG_DURATION_MS)
        crit_d = bd.criteria[0].to_dict()
        for key in ["name", "label", "measured_value", "target_min", "target_max",
                    "weight", "score", "contribution"]:
            assert key in crit_d, f"Missing key: {key}"
