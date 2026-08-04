"""Regression test for coverage-aware track selection.

``select_best_track``/`rank_tracks` originally scored candidates purely on
regularity (CV of inter-mark intervals) + onset correlation, with no
penalty for a candidate that's simply missing a large span of the song.
On Aerosmith "Dream On", `librosa_bars` won L2 bar selection despite having
zero marks for the first 69 seconds (the drums stem it's derived from is
silent during the song's quiet piano intro) -- it scored well purely
because the marks it does have (all from 69s onward) are locally regular.
"""
from __future__ import annotations

from src.analyzer.result import TimingMark, TimingTrack
from src.analyzer.selector import rank_tracks, select_best_track


def _track(name: str, times_ms: list[int]) -> TimingTrack:
    return TimingTrack(
        name=name,
        algorithm_name=name,
        element_type="bar",
        marks=[TimingMark(time_ms=t, confidence=None) for t in times_ms],
        quality_score=0.0,
    )


def test_full_coverage_candidate_wins_over_locally_regular_partial_candidate():
    duration_ms = 100_000  # 100s song

    # Perfectly regular, but only covers the last 31s (69s-100s) -- the
    # real Dream On librosa_bars scenario, scaled down.
    partial_but_regular = _track(
        "partial_but_regular", list(range(69_000, 100_000, 1500)),
    )
    # Covers the whole song, with slightly less perfect regularity
    # (alternating 1450/1550ms intervals instead of a flat 1500ms).
    full_coverage_times = []
    t = 0
    toggle = True
    while t < duration_ms:
        full_coverage_times.append(t)
        t += 1450 if toggle else 1550
        toggle = not toggle
    full_coverage = _track("full_coverage", full_coverage_times)

    winner = select_best_track(
        [partial_but_regular, full_coverage], onset_times_ms=None, duration_ms=duration_ms,
    )

    assert winner is full_coverage


def test_coverage_is_a_noop_without_duration_ms():
    """Backward compatibility: omitting duration_ms preserves the old
    regularity-only behavior (the more locally-regular candidate wins even
    with a huge coverage gap), for any caller that doesn't pass it."""
    partial_but_regular = _track(
        "partial_but_regular", list(range(69_000, 100_000, 1500)),
    )
    full_coverage_times = []
    t = 0
    toggle = True
    while t < 100_000:
        full_coverage_times.append(t)
        t += 1450 if toggle else 1550
        toggle = not toggle
    full_coverage = _track("full_coverage", full_coverage_times)

    winner = select_best_track([partial_but_regular, full_coverage], onset_times_ms=None)

    assert winner is partial_but_regular


def test_rank_tracks_orders_by_coverage_too():
    duration_ms = 100_000
    partial = _track("partial", list(range(69_000, 100_000, 1500)))
    full = _track("full", list(range(0, 100_000, 1500)))

    ranked = rank_tracks([partial, full], onset_times_ms=None, duration_ms=duration_ms)

    assert ranked[0] is full
