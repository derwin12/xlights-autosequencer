"""Quality scorer for timing tracks — category-aware with explainable breakdowns."""
from __future__ import annotations

from typing import Optional

import numpy as np

from src.analyzer.result import CriterionResult, ScoreBreakdown, TimingTrack
from src.analyzer.scoring_config import (
    CRITERIA_LABELS,
    CRITERIA_NAMES,
    DEFAULT_WEIGHTS,
    ScoringCategory,
    ScoringConfig,
    get_category_for_algorithm,
)


# ── Criterion computation ─────────────────────────────────────────────────────

def compute_density(track: TimingTrack, duration_ms: int) -> float:
    """Compute marks per second."""
    if duration_ms <= 0 or len(track.marks) == 0:
        return 0.0
    return len(track.marks) / (duration_ms / 1000.0)


def compute_regularity(track: TimingTrack) -> float:
    """Compute regularity as 1 - coefficient of variation of inter-mark intervals."""
    if len(track.marks) < 2:
        return 0.0
    times = np.array([m.time_ms for m in track.marks], dtype=float)
    intervals = np.diff(times)
    mean_interval = float(np.mean(intervals))
    if mean_interval <= 0:
        return 0.0
    cv = float(np.std(intervals)) / mean_interval
    return max(0.0, min(1.0, 1.0 - cv))


def compute_mark_count(track: TimingTrack) -> float:
    """Return the total number of marks as a float."""
    return float(len(track.marks))


def compute_coverage(track: TimingTrack, duration_ms: int) -> float:
    """Compute fraction of song duration spanned by marks (first to last / total)."""
    if len(track.marks) < 2 or duration_ms <= 0:
        return 0.0
    first = track.marks[0].time_ms
    last = track.marks[-1].time_ms
    span = last - first
    return min(1.0, span / duration_ms)


def compute_min_gap(track: TimingTrack, threshold_ms: int = 25) -> float:
    """Compute proportion of inter-mark intervals at or above the minimum gap threshold."""
    if len(track.marks) < 2:
        return 1.0  # no intervals = no violations
    times = np.array([m.time_ms for m in track.marks], dtype=float)
    intervals = np.diff(times)
    if len(intervals) == 0:
        return 1.0
    compliant = np.sum(intervals >= threshold_ms)
    return float(compliant / len(intervals))


# ── Range scoring ─────────────────────────────────────────────────────────────

def _score_in_range(value: float, target_min: float, target_max: float) -> float:
    """
    Score a value against a target range.

    Within range → 1.0
    Below min → linear falloff to 0.0 at 0
    Above max → linear falloff to 0.0 at 2× max
    """
    if target_min <= value <= target_max:
        return 1.0

    if value < target_min:
        if target_min <= 0:
            return 0.0
        return max(0.0, value / target_min)

    # value > target_max
    if target_max <= 0:
        return 0.0
    upper_bound = 2.0 * target_max
    if value >= upper_bound:
        return 0.0
    return max(0.0, 1.0 - (value - target_max) / target_max)


# ── Category-aware scoring ────────────────────────────────────────────────────

def score_track_with_breakdown(
    track: TimingTrack,
    duration_ms: int,
    config: Optional[ScoringConfig] = None,
) -> ScoreBreakdown:
    """
    Score a single track against its category targets, returning a full breakdown.
    """
    if config is None:
        config = ScoringConfig.default()

    # Tracks with zero marks always score 0 (nothing to evaluate)
    if len(track.marks) == 0:
        category = config.get_category(track.algorithm_name)
        zero_criteria = [
            CriterionResult(
                name=crit,
                label=CRITERIA_LABELS[crit],
                measured_value=0.0,
                target_min=0.0,
                target_max=0.0,
                weight=config.weights.get(crit, 0.0),
                score=0.0,
                contribution=0.0,
            )
            for crit in CRITERIA_NAMES
        ]
        return ScoreBreakdown(
            track_name=track.name,
            algorithm_name=track.algorithm_name,
            category=category.name,
            overall_score=0.0,
            criteria=zero_criteria,
            passed_thresholds=False,
            threshold_failures=["mark_count"],
        )

    category = config.get_category(track.algorithm_name)
    weights = config.weights

    # Compute raw measured values
    measured = {
        "density": compute_density(track, duration_ms),
        "regularity": compute_regularity(track),
        "mark_count": compute_mark_count(track),
        "coverage": compute_coverage(track, duration_ms),
        "min_gap": compute_min_gap(track, config.min_gap_threshold_ms),
    }

    # Target ranges per criterion from category
    target_ranges = {
        "density": category.density_range,
        "regularity": category.regularity_range,
        "mark_count": (float(category.mark_count_range[0]), float(category.mark_count_range[1])),
        "coverage": category.coverage_range,
        "min_gap": (0.9, 1.0),  # min_gap: ideal is 90-100% compliance
    }

    criteria: list[CriterionResult] = []
    total_weight = sum(weights.get(c, 0.0) for c in CRITERIA_NAMES)

    for crit_name in CRITERIA_NAMES:
        value = measured[crit_name]
        t_min, t_max = target_ranges[crit_name]
        weight = weights.get(crit_name, 0.0)
        crit_score = _score_in_range(value, t_min, t_max)
        contribution = weight * crit_score

        criteria.append(CriterionResult(
            name=crit_name,
            label=CRITERIA_LABELS[crit_name],
            measured_value=value,
            target_min=t_min,
            target_max=t_max,
            weight=weight,
            score=crit_score,
            contribution=contribution,
        ))

    overall = sum(c.contribution for c in criteria) / total_weight if total_weight > 0 else 0.0
    overall = max(0.0, min(1.0, overall))

    # Threshold filtering
    passed = True
    failures: list[str] = []
    for key, threshold_value in config.thresholds.items():
        if key.startswith("min_"):
            crit_name = key[4:]  # e.g. "min_mark_count" → "mark_count"
            if crit_name in measured and measured[crit_name] < threshold_value:
                passed = False
                failures.append(key)
        elif key.startswith("max_"):
            crit_name = key[4:]  # e.g. "max_density" → "density"
            if crit_name in measured and measured[crit_name] > threshold_value:
                passed = False
                failures.append(key)

    return ScoreBreakdown(
        track_name=track.name,
        algorithm_name=track.algorithm_name,
        category=category.name,
        overall_score=overall,
        criteria=criteria,
        passed_thresholds=passed,
        threshold_failures=failures,
    )


def score_track(track: TimingTrack, duration_ms: int = 0, config: Optional[ScoringConfig] = None) -> float:
    """
    Backward-compatible scoring function.

    When duration_ms is 0, falls back to legacy density+regularity formula
    for backward compatibility with callers that don't provide duration.
    """
    if duration_ms <= 0:
        return _legacy_score(track)

    breakdown = score_track_with_breakdown(track, duration_ms, config)
    return breakdown.overall_score


def score_all_tracks(
    tracks: list[TimingTrack],
    duration_ms: int,
    config: Optional[ScoringConfig] = None,
) -> list[ScoreBreakdown]:
    """
    Score all tracks using category-aware scoring. Sets quality_score and
    score_breakdown on each track. Returns list of ScoreBreakdowns.
    """
    if config is None:
        config = ScoringConfig.default()

    breakdowns: list[ScoreBreakdown] = []
    for track in tracks:
        bd = score_track_with_breakdown(track, duration_ms, config)
        track.quality_score = bd.overall_score
        track.score_breakdown = bd
        breakdowns.append(bd)

    return breakdowns


# ── Legacy scorer (backward compatibility) ────────────────────────────────────

def _legacy_score(track: TimingTrack) -> float:
    """
    Original scoring formula: 0.6 * density + 0.4 * regularity.
    Used when duration_ms is not provided (backward compat for runner.py).
    """
    if len(track.marks) < 2:
        return 0.0

    times = np.array([m.time_ms for m in track.marks], dtype=float)
    intervals = np.diff(times)
    mean_interval = float(np.mean(intervals))

    if mean_interval <= 0:
        return 0.0

    # density score
    if mean_interval < 100:
        return 0.0
    elif mean_interval < 250:
        density = (mean_interval - 100) / (250 - 100)
    elif mean_interval <= 1000:
        density = 1.0
    elif mean_interval <= 3000:
        density = 1.0 - 0.5 * (mean_interval - 1000) / (3000 - 1000)
    else:
        density = 0.5

    # regularity score
    std_interval = float(np.std(intervals))
    cv = std_interval / mean_interval
    regularity = max(0.0, 1.0 - cv)

    score = 0.6 * density + 0.4 * regularity
    return float(np.clip(score, 0.0, 1.0))
