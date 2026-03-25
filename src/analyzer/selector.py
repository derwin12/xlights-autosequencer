"""Best-of selection for hierarchy levels.

Selects the single best TimingTrack per hierarchy level using
coefficient of variation (CV) of inter-mark intervals as primary metric,
with onset correlation as tiebreaker.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.analyzer.result import TimingTrack


def _coefficient_of_variation(track: "TimingTrack") -> float:
    """Compute CV of inter-mark intervals. Lower = more regular = better."""
    marks = track.marks
    if len(marks) < 3:
        return float("inf")
    intervals = [
        marks[i + 1].time_ms - marks[i].time_ms
        for i in range(len(marks) - 1)
    ]
    arr = np.array(intervals, dtype=np.float64)
    mean = arr.mean()
    if mean < 1:
        return float("inf")
    return float(arr.std() / mean)


def _onset_correlation(track: "TimingTrack", onset_times_ms: list[int]) -> float:
    """Cross-correlate track beats with onset density. Higher = better alignment."""
    if not track.marks or not onset_times_ms:
        return 0.0
    if not onset_times_ms:
        return 0.0

    beat_times = np.array([m.time_ms for m in track.marks], dtype=np.float64)
    onset_times = np.array(onset_times_ms, dtype=np.float64)

    # For each beat, count how many onsets fall within ±50ms
    count = 0
    for bt in beat_times:
        count += int(np.sum(np.abs(onset_times - bt) < 50))
    return count / max(len(beat_times), 1)


def select_best_track(
    candidates: list["TimingTrack"],
    onset_times_ms: list[int] | None = None,
) -> "TimingTrack | None":
    """Select the best track from candidates using CV, with onset correlation tiebreak.

    Args:
        candidates: List of tracks to select from (same hierarchy level).
        onset_times_ms: Optional onset timestamps for tiebreak correlation.

    Returns:
        The best track, or None if candidates is empty.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    scored = [(track, _coefficient_of_variation(track)) for track in candidates]
    scored.sort(key=lambda x: x[1])

    # If top two are close in CV (within 5%), use onset correlation as tiebreak
    best_track, best_cv = scored[0]
    if len(scored) > 1 and onset_times_ms:
        second_track, second_cv = scored[1]
        if best_cv > 0 and abs(best_cv - second_cv) / best_cv < 0.05:
            corr_best = _onset_correlation(best_track, onset_times_ms)
            corr_second = _onset_correlation(second_track, onset_times_ms)
            if corr_second > corr_best:
                return second_track

    return best_track


def select_best_bar_track(
    candidates: list["TimingTrack"],
    onset_times_ms: list[int] | None = None,
) -> "TimingTrack | None":
    """Select best bar-level track (L2)."""
    return select_best_track(candidates, onset_times_ms)


def select_best_beat_track(
    candidates: list["TimingTrack"],
    onset_times_ms: list[int] | None = None,
) -> "TimingTrack | None":
    """Select best beat-level track (L3)."""
    return select_best_track(candidates, onset_times_ms)
