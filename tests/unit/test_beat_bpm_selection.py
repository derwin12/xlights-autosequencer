"""Regression test for L3 beat-track selection's BPM-multiplier check.

``_select_beat_with_bpm_check`` (src/analyzer/orchestrator.py) picks the
winning beat track among candidates by checking whether each track's rate
matches the expected BPM at 1x, 2x (double-time), or 0.5x (half-time). The
multiplier loop was nested inside the per-candidate loop, so a higher-ranked
candidate could win via an octave-tolerant 2x/0.5x match before a
lower-ranked candidate's true 1x match was ever checked -- meaning even a
correct ``estimated_bpm`` (e.g. a manual override) didn't guarantee the
correct-tempo track was selected if a double-time track happened to rank
higher on regularity/onset-correlation alone.
"""
from __future__ import annotations

from src.analyzer.orchestrator import _select_beat_with_bpm_check
from src.analyzer.result import TimingMark, TimingTrack


def _evenly_spaced_track(name: str, count: int, duration_ms: int) -> TimingTrack:
    interval = duration_ms // count
    return TimingTrack(
        name=name,
        algorithm_name=name,
        element_type="beat",
        marks=[TimingMark(time_ms=i * interval, confidence=None) for i in range(count)],
        quality_score=0.0,
    )


def test_exact_tempo_match_wins_over_higher_ranked_double_time_track():
    duration_ms = 10_000
    estimated_bpm = 78.0  # 1.3 Hz

    # 26 marks over 10s = 2.6 Hz = exactly 2x the expected rate.
    double_time = _evenly_spaced_track("double_time", 26, duration_ms)
    # 13 marks over 10s = 1.3 Hz = exactly the expected rate.
    true_tempo = _evenly_spaced_track("true_tempo", 13, duration_ms)

    # Both tracks are perfectly regular (cv=0) and no onset correlation is
    # supplied, so they tie on combined score and the stable sort preserves
    # input order -- double_time ranks first, reproducing the bug scenario
    # where a same-or-higher ranked octave-multiple candidate could win.
    winner, _losers = _select_beat_with_bpm_check(
        [double_time, true_tempo], onset_times=[], estimated_bpm=estimated_bpm,
        duration_ms=duration_ms,
    )

    assert winner is true_tempo


def test_falls_back_to_double_time_when_no_exact_match_exists():
    duration_ms = 10_000
    estimated_bpm = 78.0  # 1.3 Hz

    double_time = _evenly_spaced_track("double_time", 26, duration_ms)
    unrelated = _evenly_spaced_track("unrelated", 40, duration_ms)  # 4.0 Hz, no multiplier matches

    winner, _losers = _select_beat_with_bpm_check(
        [unrelated, double_time], onset_times=[], estimated_bpm=estimated_bpm,
        duration_ms=duration_ms,
    )

    assert winner is double_time
