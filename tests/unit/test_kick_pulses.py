"""Unit tests for src/analyzer/kick_pulses.py — kick-roll flourish detection,
grouped from already-classified kick_hits marks (no fresh onset detection)."""
from __future__ import annotations

from src.analyzer.kick_pulses import _MIN_GAP_MS, detect_kick_pulses
from src.analyzer.result import TimingMark


def _kick_hits(times_s: list[float]) -> list[TimingMark]:
    return [TimingMark(time_ms=int(t * 1000), confidence=None, label="kick") for t in times_s]


class TestDetectKickPulses:
    def test_no_hits_returns_no_marks(self):
        assert detect_kick_pulses([]) == []

    def test_isolated_hits_produce_no_marks(self):
        # Ordinary four-on-the-floor: hits spaced well over the burst window apart.
        assert detect_kick_pulses(_kick_hits([1.0, 2.0, 3.0, 4.0, 5.0])) == []

    def test_two_close_hits_below_threshold_produce_no_marks(self):
        # Only 2 hits in the burst window -- needs >=3.
        assert detect_kick_pulses(_kick_hits([5.0, 5.15])) == []

    def test_three_hit_roll_detected(self):
        marks = detect_kick_pulses(_kick_hits([5.0, 5.15, 5.3]))
        assert len(marks) == 1
        assert marks[0].label == "kick_pulse"
        assert 4.9 <= marks[0].time_ms / 1000 <= 5.4

    def test_two_well_separated_rolls_both_detected(self):
        marks = detect_kick_pulses(_kick_hits([3.0, 3.15, 3.3, 10.0, 10.15, 10.3, 10.45]))
        assert len(marks) == 2

    def test_min_gap_dedupes_adjacent_bursts(self):
        marks = detect_kick_pulses(_kick_hits([5.0, 5.15, 5.3, 5.6, 5.75, 5.9]))
        assert len(marks) == 1

    def test_unsorted_input_hits_are_handled(self):
        marks = detect_kick_pulses(_kick_hits([5.3, 5.0, 5.15]))
        assert len(marks) == 1

    def test_min_gap_constant_is_one_second(self):
        assert _MIN_GAP_MS == 1_000
