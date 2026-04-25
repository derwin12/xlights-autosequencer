"""Integration tests for the L2/L3 confidence pipeline.

Exercises the selector → validator handoff that the orchestrator wires up:

  1. ``annotate_agreement_confidence`` writes per-mark agreement values.
  2. ``validate_hierarchy`` preserves those per-mark values and only fills
     ``mark.confidence`` from the track-level scalar when it's still ``None``.

The full ``run_orchestrator`` pipeline depends on vamp / madmom / demucs and
is exercised by ``xlight-evaluate gate`` (analyzer suite). Here we drive the
two stages directly so the test runs in milliseconds without those heavy
deps and stays deterministic.
"""
from __future__ import annotations

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.analyzer.selector import (
    annotate_agreement_confidence,
    select_best_beat_track_with_candidates,
)
from src.analyzer.validator import validate_hierarchy


def _track(name: str, times_ms: list[int]) -> TimingTrack:
    return TimingTrack(
        name=name,
        algorithm_name=name,
        element_type="beat",
        marks=[TimingMark(time_ms=t, confidence=None) for t in times_ms],
        quality_score=0.0,
    )


def _hierarchy_with_beats(beats: TimingTrack) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="stub.mp3",
        source_hash="0" * 32,
        duration_ms=10_000,
        estimated_bpm=120.0,
        beats=beats,
    )


def test_multi_tracker_yields_per_mark_confidence_distinct_from_score():
    """T6.2: With ≥2 trackers, at least one beat mark has confidence ≠ track-level score.

    The selector annotates per-mark agreement; the validator computes a
    track-level scalar for ``report['beats']['score']`` but does NOT
    overwrite the per-mark values. So unless every mark happens to coincide
    with ``score``, at least one mark's confidence differs.
    """
    # Three loser tracks: one perfectly agrees, two miss every beat.
    winner = _track("winner", [1000, 2000, 3000, 4000, 5000])
    losers = [
        _track("a", [1010, 2010, 3010, 4010, 5010]),  # all within 35 ms → agreement = 1
        _track("b", [9000, 9100, 9200, 9300, 9400]),  # never within 35 ms
        _track("c", [9050, 9150, 9250, 9350, 9450]),  # never within 35 ms
    ]
    annotate_agreement_confidence(winner, losers, window_ms=35)
    # Each winner mark should now have confidence = 1/3.
    assert all(m.confidence == round(1 / 3, 3) for m in winner.marks)

    result = _hierarchy_with_beats(winner)
    report = validate_hierarchy(result)

    # The track-level score is regularity + onset_alignment scaled — its
    # value is deterministic but not necessarily equal to 1/3.
    track_score = report["beats"]["score"]
    # At least one mark has confidence ≠ track-level score (the validator
    # preserved the agreement value rather than overwriting with track score).
    assert any(m.confidence != track_score for m in winner.marks), (
        f"validator clobbered per-mark confidence; expected at least one "
        f"mark with confidence≠{track_score}"
    )
    # And specifically, every mark retains the agreement value.
    assert all(m.confidence == round(1 / 3, 3) for m in winner.marks)


def test_single_tracker_fallback_uses_track_level_score():
    """T6.3: Single-tracker (no losers) → validator fills every mark with track score.

    Mirrors ``profile="quick"`` where only one beat tracker runs, so
    ``annotate_agreement_confidence`` is a no-op and validator's
    track-level fallback fills the field.
    """
    winner = _track("only", [1000, 2000, 3000, 4000, 5000])
    # Selector with no losers is a no-op.
    annotate_agreement_confidence(winner, [], window_ms=35)
    assert all(m.confidence is None for m in winner.marks)

    result = _hierarchy_with_beats(winner)
    report = validate_hierarchy(result)
    track_score = report["beats"]["score"]

    # Every mark receives the track-level scalar — pre-change behavior.
    assert all(m.confidence == track_score for m in winner.marks), (
        f"single-tracker fallback failed; got "
        f"{[m.confidence for m in winner.marks]}, expected all == {track_score}"
    )


def test_beats_score_unchanged_by_validator_guard():
    """T6.4: ``report['beats']['score']`` is the same regardless of pre-set confidence.

    Regression guard: the validator change only affects how per-mark
    confidence is populated; the track-level ``score`` field must still
    reflect regularity + onset_alignment as before.
    """
    winner_a = _track("w", [1000, 2000, 3000, 4000, 5000])
    winner_b = _track("w", [1000, 2000, 3000, 4000, 5000])
    # Pre-populate winner_a with an arbitrary per-mark confidence; leave
    # winner_b as None.
    for m in winner_a.marks:
        m.confidence = 0.42

    score_a = validate_hierarchy(_hierarchy_with_beats(winner_a))["beats"]["score"]
    score_b = validate_hierarchy(_hierarchy_with_beats(winner_b))["beats"]["score"]
    assert score_a == score_b, (
        f"validator track-level score must not depend on pre-set per-mark "
        f"confidence; got {score_a} vs {score_b}"
    )


def test_orchestrator_handoff_with_candidates_variant():
    """T6.x: ``select_best_beat_track_with_candidates`` + annotate + validate end-to-end.

    Confirms the wiring used in the orchestrator at L3: the variant returns
    (winner, losers); the annotate call writes per-mark values; validation
    preserves them.
    """
    a = _track("a", [1000, 1500, 2000, 2500, 3000])  # most regular → wins
    b = _track("b", [1010, 1490, 2005, 2490, 3015])  # within 35 ms of every winner mark
    c = _track("c", [9000, 9100, 9200, 9300, 9400])  # never agrees

    winner, losers = select_best_beat_track_with_candidates([a, b, c])
    assert winner is a
    assert len(losers) == 2

    annotate_agreement_confidence(winner, losers, window_ms=35)
    # b agrees on every mark, c never does → 1/2 == 0.5 per mark.
    assert all(m.confidence == 0.5 for m in winner.marks)

    result = _hierarchy_with_beats(winner)
    validate_hierarchy(result)
    # Per-mark values survive validator unchanged.
    assert all(m.confidence == 0.5 for m in winner.marks)
