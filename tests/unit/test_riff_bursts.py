"""Unit tests for src/analyzer/riff_bursts.py — bass-burst + chord-acceleration
riff/fill detection.

Synthetic fixtures: the bass stem carries clusters of short broadband
pulses (energy in every band including 20-250Hz, same trick the crash-accent
tests use); the analysis itself does the band restriction, so the pulses
don't need to be spectrally shaped. The chord track is a plain TimingTrack
of marks at chosen times.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.result import TimingMark, TimingTrack
from src.analyzer.riff_bursts import detect_riff_bursts

_SR = 22050


def _bass_stem(duration_s: float, pulse_groups: list[list[float]] = (), seed: int = 7) -> np.ndarray:
    n = int(_SR * duration_s)
    rng = np.random.default_rng(seed)
    stem = (0.0005 * rng.standard_normal(n)).astype(np.float32)
    for group in pulse_groups:
        for at in group:
            start = int(at * _SR)
            length = int(0.05 * _SR)
            if start + length > n:
                continue
            burst = 0.6 * rng.standard_normal(length)
            burst *= np.exp(-np.linspace(0, 6, length))
            stem[start:start + length] += burst.astype(np.float32)
    return stem


def _chords(times_s: list[float]) -> TimingTrack:
    marks = [TimingMark(time_ms=int(round(t * 1000)), confidence=None, label="X")
             for t in times_s]
    return TimingTrack(name="chords", algorithm_name="chordino",
                        element_type="chord", marks=marks, quality_score=0.0)


class TestDetectRiffBursts:
    def test_empty_bass_produces_no_marks(self):
        assert detect_riff_bursts(np.array([]), _SR, _chords([10.0, 10.3])) == []

    def test_no_chord_track_produces_no_marks(self):
        stem = _bass_stem(20.0, [[10.0, 10.3, 10.6]])
        assert detect_riff_bursts(stem, _SR, None) == []

    def test_bass_burst_without_accelerated_chords_produces_no_marks(self):
        # 3 pulses within 1s (a burst), but chords are evenly spaced (no
        # gap <=0.6s) -- must not fire alone.
        stem = _bass_stem(20.0, [[10.0, 10.3, 10.6]])
        chords = _chords([8.5, 10.0, 11.5, 13.0])
        assert detect_riff_bursts(stem, _SR, chords) == []

    def test_accelerated_chords_without_bass_burst_produces_no_marks(self):
        # Fast chord change, but genuinely no bass activity nearby (true
        # silence, not random-noise "quiet" -- white noise has spectral
        # novelty everywhere and would itself look like scattered onsets)
        # -- must not fire alone.
        stem = np.zeros(int(_SR * 20.0), dtype=np.float32)
        chords = _chords([8.0, 10.0, 10.4, 13.0])
        assert detect_riff_bursts(stem, _SR, chords) == []

    def test_burst_with_accelerated_chord_change_detected(self):
        stem = _bass_stem(20.0, [[10.0, 10.3, 10.6]])
        chords = _chords([7.0, 10.2, 10.6, 14.0])
        marks = detect_riff_bursts(stem, _SR, chords)
        assert len(marks) == 1
        assert marks[0].label == "riff_burst"
        assert 9.5 <= marks[0].time_ms / 1000 <= 11.5

    def test_two_well_separated_bursts_both_detected(self):
        stem = _bass_stem(20.0, [[5.0, 5.3, 5.6], [15.0, 15.3, 15.6]])
        chords = _chords([4.7, 5.2, 5.6, 14.7, 15.2, 15.6])
        marks = detect_riff_bursts(stem, _SR, chords)
        assert len(marks) == 2
