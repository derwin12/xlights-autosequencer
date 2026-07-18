"""Unit tests for src/analyzer/riff_bursts.py — snare-roll burst detection.

Synthetic fixtures: short broadband pulses on the (isolated) snare stem,
clustered to model a real drum roll/fill vs. isolated ordinary hits.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.riff_bursts import _MIN_GAP_MS, detect_riff_bursts

_SR = 22050


def _snare_stem(duration_s: float, pulse_times: list[float] = (), seed: int = 3) -> np.ndarray:
    n = int(_SR * duration_s)
    rng = np.random.default_rng(seed)
    stem = np.zeros(n, dtype=np.float32)
    for at in pulse_times:
        start = int(at * _SR)
        length = int(0.03 * _SR)
        if start + length > n:
            continue
        burst = 0.7 * rng.standard_normal(length)
        burst *= np.exp(-np.linspace(0, 6, length))
        stem[start:start + length] += burst.astype(np.float32)
    return stem


class TestDetectRiffBursts:
    def test_empty_audio_returns_no_marks(self):
        assert detect_riff_bursts(np.array([]), _SR) == []

    def test_silent_audio_returns_no_marks(self):
        assert detect_riff_bursts(np.zeros(_SR * 5, dtype=np.float32), _SR) == []

    def test_isolated_hits_produce_no_marks(self):
        # Ordinary backbeat: hits spaced well over the burst window apart.
        stem = _snare_stem(10.0, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert detect_riff_bursts(stem, _SR) == []

    def test_two_close_hits_below_threshold_produce_no_marks(self):
        # Only 2 hits in the burst window -- needs >=3.
        stem = _snare_stem(10.0, [5.0, 5.15])
        assert detect_riff_bursts(stem, _SR) == []

    def test_three_hit_roll_detected(self):
        stem = _snare_stem(10.0, [5.0, 5.15, 5.3])
        marks = detect_riff_bursts(stem, _SR)
        assert len(marks) == 1
        assert marks[0].label == "riff_burst"
        assert 4.9 <= marks[0].time_ms / 1000 <= 5.4

    def test_two_well_separated_rolls_both_detected(self):
        stem = _snare_stem(15.0, [3.0, 3.15, 3.3, 10.0, 10.15, 10.3, 10.45])
        marks = detect_riff_bursts(stem, _SR)
        assert len(marks) == 2

    def test_min_gap_dedupes_adjacent_bursts(self):
        # Two DISTINCT bursts (gap between them > _BURST_MAX_GAP_S, so they
        # group separately) whose midpoints land closer than _MIN_GAP_MS
        # apart collapse to one mark.
        stem = _snare_stem(10.0, [5.0, 5.15, 5.3, 5.6, 5.75, 5.9])
        marks = detect_riff_bursts(stem, _SR)
        assert len(marks) == 1
