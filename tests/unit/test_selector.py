"""Tests for src/analyzer/selector — cross-tracker agreement annotation.

Covers ``annotate_agreement_confidence`` and the ``_with_candidates``
selector variants introduced for the beat-confidence-annotation change.
"""
from __future__ import annotations

from src.analyzer.result import TimingMark, TimingTrack
from src.analyzer.selector import (
    annotate_agreement_confidence,
    select_best_beat_track_with_candidates,
    select_best_bar_track_with_candidates,
)


def _track(name: str, times_ms: list[int]) -> TimingTrack:
    """Build a minimal TimingTrack with marks at the given times (confidence=None)."""
    return TimingTrack(
        name=name,
        algorithm_name=name,
        element_type="beat",
        marks=[TimingMark(time_ms=t, confidence=None) for t in times_ms],
        quality_score=0.0,
    )


# ── annotate_agreement_confidence ─────────────────────────────────────────────

def test_three_losers_all_agree_yields_one():
    """T2.2: Three losers all within ±35 ms of every winner mark → 1.0."""
    winner = _track("winner", [1000, 2000, 3000])
    losers = [
        _track("a", [1005, 2010, 3000]),    # all within 10 ms
        _track("b", [995, 2000, 3020]),     # all within 20 ms
        _track("c", [1030, 1980, 2980]),    # all within 30 ms
    ]
    annotate_agreement_confidence(winner, losers, window_ms=35)
    assert all(m.confidence == 1.0 for m in winner.marks)


def test_zero_losers_agree_yields_zero():
    """T2.3: No loser within ±35 ms → 0.0."""
    winner = _track("winner", [1000, 2000, 3000])
    losers = [
        _track("a", [500, 1500, 2500]),     # all 500 ms off
        _track("b", [600, 1600, 2600]),
        _track("c", [800, 1800, 2800]),
    ]
    annotate_agreement_confidence(winner, losers, window_ms=35)
    assert all(m.confidence == 0.0 for m in winner.marks)


def test_one_of_three_losers_agrees():
    """T2.4: One of three losers agrees → 1/3 ≈ 0.333."""
    winner = _track("winner", [1000])
    losers = [
        _track("a", [1010]),    # within window
        _track("b", [1500]),    # outside
        _track("c", [2000]),    # outside
    ]
    annotate_agreement_confidence(winner, losers, window_ms=35)
    assert winner.marks[0].confidence == round(1 / 3, 3)


def test_empty_losers_leaves_confidence_none():
    """T2.5: Empty losers list → confidence remains None (single-tracker fallback)."""
    winner = _track("winner", [1000, 2000])
    annotate_agreement_confidence(winner, [], window_ms=35)
    assert all(m.confidence is None for m in winner.marks)


def test_window_boundary_inclusive():
    """T2.6: Loser at exactly ±35 ms counts; loser at 36 ms does not."""
    winner = _track("winner", [1000])
    # Loser at exactly 35 ms — should count.
    on_boundary_loser = _track("a", [1035])
    annotate_agreement_confidence(winner, [on_boundary_loser], window_ms=35)
    assert winner.marks[0].confidence == 1.0

    # Loser at 36 ms — should not count.
    winner2 = _track("winner", [1000])
    just_outside_loser = _track("a", [1036])
    annotate_agreement_confidence(winner2, [just_outside_loser], window_ms=35)
    assert winner2.marks[0].confidence == 0.0


def test_loser_with_multiple_marks_counts_once():
    """T2.7: A loser with several marks inside the window counts as one tracker."""
    winner = _track("winner", [1000])
    crowded_loser = _track("a", [995, 1005, 1015, 1025])
    other_loser = _track("b", [1500])
    annotate_agreement_confidence(winner, [crowded_loser, other_loser], window_ms=35)
    # Only one of two losers agrees; crowded marks must not double-count.
    assert winner.marks[0].confidence == 0.5


# ── select_best_beat_track_with_candidates ───────────────────────────────────

def test_with_candidates_returns_winner_and_losers():
    """T2.8: Returns (winner, losers) with len(losers) == len(candidates) - 1."""
    # Build four candidates; the most regular (cv=0) should win.
    a = _track("a", [1000, 1500, 2000, 2500, 3000])      # perfectly regular
    b = _track("b", [1000, 1400, 2050, 2480, 3010])      # less regular
    c = _track("c", [1000, 1600, 1900, 2700, 3100])
    d = _track("d", [1000, 1300, 2200, 2400, 3200])
    candidates = [a, b, c, d]

    winner, losers = select_best_beat_track_with_candidates(candidates)
    assert winner is a
    assert len(losers) == 3
    assert set(id(t) for t in losers) == {id(b), id(c), id(d)}


def test_with_candidates_single_candidate_yields_empty_losers():
    """T2.9: Single candidate returns (candidate, [])."""
    only = _track("only", [1000, 2000, 3000])
    winner, losers = select_best_beat_track_with_candidates([only])
    assert winner is only
    assert losers == []


def test_with_candidates_empty_returns_none_and_empty():
    """Empty candidate list returns (None, [])."""
    winner, losers = select_best_bar_track_with_candidates([])
    assert winner is None
    assert losers == []
