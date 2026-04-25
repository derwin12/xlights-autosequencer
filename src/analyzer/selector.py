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
    """Select the best track from candidates using a combined regularity + onset score.

    Scoring (per candidate):
      regularity  = 1 - CV, clamped [0, 1]          weight 0.5
      onset_corr  = normalised onset correlation      weight 0.5

    Onset correlation is normalised across candidates so a single strong
    algorithm doesn't dominate purely because it has more marks.

    Args:
        candidates: List of tracks to select from (same hierarchy level).
        onset_times_ms: Optional onset timestamps for onset correlation signal.

    Returns:
        The best track, or None if candidates is empty.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    cvs = {id(t): _coefficient_of_variation(t) for t in candidates}

    if onset_times_ms:
        raw_corrs = {id(t): _onset_correlation(t, onset_times_ms) for t in candidates}
        max_corr = max(raw_corrs.values()) or 1.0
        norm_corrs = {k: v / max_corr for k, v in raw_corrs.items()}
    else:
        norm_corrs = {id(t): 0.0 for t in candidates}

    def _combined(track: "TimingTrack") -> float:
        cv = cvs[id(track)]
        regularity = max(0.0, min(1.0, 1.0 - cv))
        onset = norm_corrs[id(track)]
        return 0.5 * regularity + 0.5 * onset

    return max(candidates, key=_combined)


def rank_tracks(
    candidates: list["TimingTrack"],
    onset_times_ms: list[int] | None = None,
) -> list["TimingTrack"]:
    """Return candidates sorted best-first by combined regularity + onset score."""
    if not candidates:
        return []
    if len(candidates) == 1:
        return list(candidates)

    cvs = {id(t): _coefficient_of_variation(t) for t in candidates}

    if onset_times_ms:
        raw_corrs = {id(t): _onset_correlation(t, onset_times_ms) for t in candidates}
        max_corr = max(raw_corrs.values()) or 1.0
        norm_corrs = {k: v / max_corr for k, v in raw_corrs.items()}
    else:
        norm_corrs = {id(t): 0.0 for t in candidates}

    def _combined(track: "TimingTrack") -> float:
        cv = cvs[id(track)]
        regularity = max(0.0, min(1.0, 1.0 - cv))
        onset = norm_corrs[id(track)]
        return 0.5 * regularity + 0.5 * onset

    return sorted(candidates, key=_combined, reverse=True)


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


def annotate_agreement_confidence(
    winner: "TimingTrack",
    losers: list["TimingTrack"],
    window_ms: int = 35,
) -> None:
    """Annotate each winner mark with cross-tracker agreement confidence.

    For each ``winner.marks[i]``, count how many ``losers`` have at least one
    mark within ``±window_ms`` of the winner mark, then write
    ``count / len(losers)`` (rounded to 3 decimals) into
    ``winner.marks[i].confidence``.

    Mutates ``winner.marks`` in place. No-op when ``losers`` is empty (the
    single-tracker fallback case): ``confidence`` is left untouched (typically
    ``None``) so the validator's track-level fallback can populate it.

    Multiple loser marks within the window count once per loser (not double
    counted) — agreement is measured at the per-tracker level. Boundary is
    inclusive: a loser mark exactly at ``window_ms`` distance counts.

    Implementation: pre-sort each loser's mark times once, then use
    ``numpy.searchsorted`` to find the nearest mark per winner — O(N log M)
    per loser instead of O(N · M).
    """
    if not winner or not winner.marks or not losers:
        return

    n_losers = len(losers)
    # Pre-sort loser mark times as numpy arrays for binary search.
    loser_times = [
        np.array(sorted(m.time_ms for m in loser.marks), dtype=np.int64)
        for loser in losers
    ]

    for mark in winner.marks:
        t = mark.time_ms
        agreeing = 0
        for times in loser_times:
            if times.size == 0:
                continue
            idx = int(np.searchsorted(times, t))
            # Closest mark is either at idx or idx-1.
            best = None
            if idx < times.size:
                best = abs(int(times[idx]) - t)
            if idx > 0:
                d = abs(int(times[idx - 1]) - t)
                best = d if best is None else min(best, d)
            if best is not None and best <= window_ms:
                agreeing += 1
        mark.confidence = round(agreeing / n_losers, 3)


def select_best_bar_track_with_candidates(
    candidates: list["TimingTrack"],
    onset_times_ms: list[int] | None = None,
) -> "tuple[TimingTrack | None, list[TimingTrack]]":
    """Select best L2 bar track and return the winner plus the remaining losers.

    Returns ``(winner, losers)`` where ``losers`` preserves input order minus
    the winner. When ``candidates`` is empty, returns ``(None, [])``. When a
    single candidate is supplied, returns ``(candidate, [])``.
    """
    winner = select_best_track(candidates, onset_times_ms)
    if winner is None:
        return None, []
    losers = [c for c in candidates if c is not winner]
    return winner, losers


def select_best_beat_track_with_candidates(
    candidates: list["TimingTrack"],
    onset_times_ms: list[int] | None = None,
) -> "tuple[TimingTrack | None, list[TimingTrack]]":
    """Select best L3 beat track and return the winner plus the remaining losers.

    Returns ``(winner, losers)`` where ``losers`` preserves input order minus
    the winner. When ``candidates`` is empty, returns ``(None, [])``. When a
    single candidate is supplied, returns ``(candidate, [])``.
    """
    winner = select_best_track(candidates, onset_times_ms)
    if winner is None:
        return None, []
    losers = [c for c in candidates if c is not winner]
    return winner, losers
