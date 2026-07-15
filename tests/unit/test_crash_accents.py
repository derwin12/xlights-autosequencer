"""Unit tests for src/analyzer/crash_accents.py — rare whole-house crash detection."""
from __future__ import annotations

import numpy as np
import pytest

from src.analyzer.crash_accents import _MAX_MARKS, _MIN_GAP_MS, detect_crash_accents

_SR = 22050


def _ambient(duration_s: float, seed: int = 42) -> np.ndarray:
    t = np.linspace(0, duration_s, int(_SR * duration_s), endpoint=False)
    rng = np.random.default_rng(seed)
    return (0.02 * np.sin(2 * np.pi * 220 * t) + 0.005 * rng.standard_normal(len(t))).astype(np.float64)


def _add_burst(audio: np.ndarray, at_s: float, dur_s: float = 0.05, amp: float = 0.95) -> np.ndarray:
    start = int(at_s * _SR)
    end = int((at_s + dur_s) * _SR)
    rng = np.random.default_rng(int(at_s * 1000))
    audio[start:end] += amp * rng.standard_normal(end - start)
    return audio


class TestDetectCrashAccents:
    def test_silence_produces_no_marks(self):
        assert detect_crash_accents(np.zeros(_SR * 5), _SR) == []

    def test_empty_audio_produces_no_marks(self):
        assert detect_crash_accents(np.array([]), _SR) == []

    def test_ambient_only_produces_no_marks(self):
        """A steady ambient signal with no outlier transient should be
        quiet by design -- most songs should get zero marks."""
        assert detect_crash_accents(_ambient(20.0), _SR) == []

    def test_single_burst_detected_near_its_time(self):
        audio = _add_burst(_ambient(15.0), at_s=7.0)
        marks = detect_crash_accents(audio, _SR)
        assert len(marks) == 1
        assert marks[0].label == "crash"
        assert abs(marks[0].time_ms - 7000) < 100

    def test_two_well_separated_bursts_both_detected(self):
        audio = _ambient(30.0)
        audio = _add_burst(audio, at_s=3.0)
        audio = _add_burst(audio, at_s=20.0)
        marks = detect_crash_accents(audio, _SR)
        times = sorted(m.time_ms for m in marks)
        assert len(times) == 2
        assert abs(times[0] - 3000) < 100
        assert abs(times[1] - 20000) < 100

    def test_bursts_closer_than_min_gap_collapse_to_one(self):
        audio = _ambient(15.0)
        audio = _add_burst(audio, at_s=5.0)
        audio = _add_burst(audio, at_s=5.0 + (_MIN_GAP_MS / 1000) / 2)
        marks = detect_crash_accents(audio, _SR)
        assert len(marks) == 1

    def test_hard_cap_keeps_only_max_marks(self):
        audio = _ambient(90.0)
        for at_s in (3, 15, 27, 39, 51, 63, 75):
            audio = _add_burst(audio, at_s=at_s)
        marks = detect_crash_accents(audio, _SR)
        assert len(marks) <= _MAX_MARKS

    def test_marks_sorted_ascending_by_time(self):
        audio = _ambient(30.0)
        audio = _add_burst(audio, at_s=20.0)
        audio = _add_burst(audio, at_s=3.0)
        marks = detect_crash_accents(audio, _SR)
        times = [m.time_ms for m in marks]
        assert times == sorted(times)

    def test_burst_out_of_silence_is_excluded(self):
        """A transient out of near-silence (e.g. the track's own cold open)
        must NOT fire, even if it is the largest onset-strength value in
        the whole track -- confirmed on a real song (2026-07-14): the
        first-ever version of this detector flagged the very first audio
        frame as a "crash" because transitioning out of near-silence
        produces a huge relative spectral-flux spike despite being the
        quietest moment in the song. The pre-transient RMS floor exists
        specifically to reject this."""
        audio = _ambient(15.0)
        audio[: int(0.3 * _SR)] = 0.0
        end = int(0.05 * _SR)
        audio[:end] += 0.95 * np.random.default_rng(7).standard_normal(end)
        assert detect_crash_accents(audio, _SR) == []

