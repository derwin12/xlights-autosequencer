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


def test_folds_double_time_winner_down_when_no_exact_match_exists():
    """No candidate matches 1x (only unrelated + double_time exist) -> the
    2x match is folded down to the correct rate instead of returned as-is.

    This is the real-world case behind Aerosmith "Dream On": every beat
    tracker detects the syncopated 8th-note pattern as "the beat", so no
    candidate is ever produced anywhere near the true tempo -- a correct
    ``estimated_bpm`` alone can't fix beat selection when there's nothing
    at 1x to select.
    """
    duration_ms = 10_000
    estimated_bpm = 78.0  # 1.3 Hz

    double_time = _evenly_spaced_track("double_time", 26, duration_ms)
    unrelated = _evenly_spaced_track("unrelated", 40, duration_ms)  # 4.0 Hz, no multiplier matches

    winner, losers = _select_beat_with_bpm_check(
        [unrelated, double_time], onset_times=[], estimated_bpm=estimated_bpm,
        duration_ms=duration_ms,
    )

    assert winner is not double_time  # folded into a new track, not returned as-is
    assert winner.algorithm_name == "double_time"
    assert winner.mark_count == 13
    implied_hz = winner.mark_count / (duration_ms / 1000)
    assert abs(implied_hz - 1.3) < 0.01
    # The raw (un-folded) double_time candidate is excluded from both the
    # returned winner (a new folded track) and the losers list (it's the
    # candidate the winner was derived from, not a losing alternative).
    assert double_time not in losers
    assert unrelated in losers


def test_fold_picks_phase_aligned_with_bar_track():
    """When a bar track is available, folding picks whichever phase (even-
    or odd-indexed marks) lands closer to real bar/downbeat times, rather
    than blindly keeping the first mark of every pair.
    """
    duration_ms = 10_000
    estimated_bpm = 78.0  # 1.3 Hz -> true beats should land near 769ms apart

    # 26 evenly-spaced marks at 385ms intervals (2x the true ~769ms rate).
    double_time = _evenly_spaced_track("double_time", 26, duration_ms)
    # Bar track marks align with the ODD-indexed marks of double_time
    # (index 1, 3, 5, ... at ~385, 1155, 1925ms), not the even-indexed ones.
    odd_indexed_times = [m.time_ms for m in double_time.marks[1::2]]
    bars = TimingTrack(
        name="bars", algorithm_name="qm_bars", element_type="bar",
        marks=[TimingMark(time_ms=t, confidence=None) for t in odd_indexed_times[::4]],
        quality_score=0.0,
    )

    winner, _losers = _select_beat_with_bpm_check(
        [double_time], onset_times=[], estimated_bpm=estimated_bpm,
        duration_ms=duration_ms, bars=bars,
    )

    winner_times = [m.time_ms for m in winner.marks]
    assert winner_times == odd_indexed_times
