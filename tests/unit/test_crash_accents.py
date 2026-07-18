"""Unit tests for src/analyzer/crash_accents.py — cymbal-stem crash detection.

The detector consumes a cymbal-isolated stem plus the full mix (cold-open
guard only). Synthetic fixtures model what a real drumsep platillos stem
looks like: continuous low-level cymbal bleed, sparse small ticks (ordinary
hits), and rare high-amplitude bursts with a multi-second decaying wash
(hero crashes). The wash is what separates a crash from a tick — the score
multiplies isolation by wash area.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.crash_accents import (
    _MAX_MARKS,
    _MIN_GAP_MS,
    detect_crash_accents,
    detect_ending_punches,
)

_SR = 22050


def _full_mix(duration_s: float, silent_until_s: float = 0.0) -> np.ndarray:
    """Steady mid-level mix so the pre-transient RMS guard passes."""
    t = np.linspace(0, duration_s, int(_SR * duration_s), endpoint=False)
    mix = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    mix[: int(silent_until_s * _SR)] = 0.0
    return mix


def _cymbal_stem(
    duration_s: float,
    crashes: list[float] = (),
    ticks: bool = True,
    seed: int = 42,
) -> np.ndarray:
    """Cymbal stem: low bleed + small periodic ticks + crash washes."""
    n = int(_SR * duration_s)
    rng = np.random.default_rng(seed)
    stem = (0.01 * rng.standard_normal(n)).astype(np.float32)

    if ticks:  # ordinary hits every 0.7s: short, small, fast decay
        for at in np.arange(0.5, duration_s - 0.1, 0.7):
            start = int(at * _SR)
            length = int(0.03 * _SR)
            burst = 0.05 * rng.standard_normal(length)
            burst *= np.exp(-np.linspace(0, 6, length))
            stem[start:start + length] += burst.astype(np.float32)

    for at in crashes:  # hero crash: loud attack, ~1.5s bright wash
        start = int(at * _SR)
        length = min(int(1.5 * _SR), n - start)
        burst = 0.9 * rng.standard_normal(length)
        burst *= np.exp(-np.linspace(0, 5, length))
        stem[start:start + length] += burst.astype(np.float32)

    return stem


class TestDetectCrashAccents:
    def test_empty_inputs_produce_no_marks(self):
        assert detect_crash_accents(np.array([]), _SR, _full_mix(5.0), _SR) == []
        assert detect_crash_accents(_cymbal_stem(5.0), _SR, np.array([]), _SR) == []

    def test_silent_stem_produces_no_marks(self):
        assert detect_crash_accents(
            np.zeros(_SR * 5, dtype=np.float32), _SR, _full_mix(5.0), _SR) == []

    def test_ordinary_hits_only_produce_no_marks(self):
        """Rare by design: a stem with only ordinary hits (no isolated
        high-energy wash) must emit zero marks — most songs get none."""
        stem = _cymbal_stem(30.0, crashes=[])
        assert detect_crash_accents(stem, _SR, _full_mix(30.0), _SR) == []

    def test_single_crash_detected_near_its_time(self):
        stem = _cymbal_stem(30.0, crashes=[12.0])
        marks = detect_crash_accents(stem, _SR, _full_mix(30.0), _SR)
        assert len(marks) == 1
        assert marks[0].label == "crash"
        assert abs(marks[0].time_ms - 12000) < 150

    def test_two_separated_crashes_both_detected_sorted(self):
        stem = _cymbal_stem(45.0, crashes=[30.0, 8.0])
        marks = detect_crash_accents(stem, _SR, _full_mix(45.0), _SR)
        times = [m.time_ms for m in marks]
        assert times == sorted(times)
        assert len(times) == 2
        assert abs(times[0] - 8000) < 150
        assert abs(times[1] - 30000) < 150

    def test_crashes_closer_than_min_gap_collapse_to_one(self):
        gap_s = (_MIN_GAP_MS / 1000) / 2
        stem = _cymbal_stem(30.0, crashes=[12.0, 12.0 + gap_s])
        marks = detect_crash_accents(stem, _SR, _full_mix(30.0), _SR)
        assert len(marks) == 1

    def test_hard_cap_keeps_at_most_max_marks(self):
        crash_times = [5.0 + 11.0 * i for i in range(_MAX_MARKS + 2)]
        duration = crash_times[-1] + 10.0
        stem = _cymbal_stem(duration, crashes=crash_times)
        marks = detect_crash_accents(stem, _SR, _full_mix(duration), _SR)
        assert len(marks) <= _MAX_MARKS

    def test_crash_out_of_full_mix_silence_is_excluded(self):
        """The cold-open guard (kept verbatim from v2, bug-201): a transient
        whose preceding 500ms of FULL MIX is near-silent must not fire, no
        matter how dramatic it looks on the cymbal stem."""
        stem = _cymbal_stem(30.0, crashes=[12.0])
        mix = _full_mix(30.0, silent_until_s=12.0)
        assert detect_crash_accents(stem, _SR, mix, _SR) == []

    def test_mismatched_sample_rates_map_times_correctly(self):
        """The full mix may be at a different sample rate than the stem."""
        stem = _cymbal_stem(30.0, crashes=[12.0])
        mix_sr = 44100
        t = np.linspace(0, 30.0, int(mix_sr * 30.0), endpoint=False)
        mix = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        marks = detect_crash_accents(stem, _SR, mix, mix_sr)
        assert len(marks) == 1
        assert abs(marks[0].time_ms - 12000) < 150


def _punchy_stem(duration_s: float, punches: list[float] = (), seed: int = 7) -> np.ndarray:
    """Cymbal stem with short hard hits (no multi-second wash): the ending
    'button' shape — loud, brief, fast decay."""
    n = int(_SR * duration_s)
    rng = np.random.default_rng(seed)
    stem = (0.01 * rng.standard_normal(n)).astype(np.float32)
    for at in np.arange(0.5, duration_s - 0.1, 0.7):  # ordinary ticks
        start = int(at * _SR)
        length = int(0.03 * _SR)
        burst = 0.05 * rng.standard_normal(length)
        burst *= np.exp(-np.linspace(0, 6, length))
        stem[start:start + length] += burst.astype(np.float32)
    for at in punches:
        start = int(at * _SR)
        length = min(int(0.08 * _SR), n - start)
        burst = 0.6 * rng.standard_normal(length)
        burst *= np.exp(-np.linspace(0, 4, length))
        stem[start:start + length] += burst.astype(np.float32)
    return stem


class TestDetectEndingPunches:
    """Ending 'button' punches: cymbal hits in the final seconds before the
    audible end. Fixture mixes go silent at 60s (the audible end) with 2s of
    trailing silence, like a hard-cut ending followed by encoder padding."""

    def _mix(self, duration_s: float = 62.0, audible_until_s: float = 60.0) -> np.ndarray:
        t = np.linspace(0, duration_s, int(_SR * duration_s), endpoint=False)
        mix = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        mix[int(audible_until_s * _SR):] = 0.0
        return mix

    def test_empty_inputs_produce_no_marks(self):
        assert detect_ending_punches(np.array([]), _SR, self._mix(), _SR) == []
        assert detect_ending_punches(_punchy_stem(62.0), _SR, np.array([]), _SR) == []

    def test_punches_in_final_window_detected(self):
        stem = _punchy_stem(62.0, punches=[55.0, 57.0])
        marks = detect_ending_punches(stem, _SR, self._mix(), _SR)
        assert len(marks) == 2
        assert all(m.label == "ending_punch" for m in marks)
        assert abs(marks[0].time_ms - 55_000) < 150
        assert abs(marks[1].time_ms - 57_000) < 150

    def test_identical_punches_mid_song_are_ignored(self):
        """Position is the discriminator: the same hit strength mid-song
        must not fire (a bare loudness rule fires ~17x/song)."""
        stem = _punchy_stem(62.0, punches=[20.0, 35.0])
        assert detect_ending_punches(stem, _SR, self._mix(), _SR) == []

    def test_no_punches_near_end_produces_no_marks(self):
        stem = _punchy_stem(62.0, punches=[])
        assert detect_ending_punches(stem, _SR, self._mix(), _SR) == []

    def test_machine_gun_cluster_fires_per_hit(self):
        """Hits ~300ms apart (validated cluster: 192.0/192.2/192.3s in the
        target song) must each get their own mark."""
        stem = _punchy_stem(62.0, punches=[56.0, 56.35, 56.7])
        marks = detect_ending_punches(stem, _SR, self._mix(), _SR)
        assert len(marks) == 3

    def test_trailing_silence_does_not_shift_the_window(self):
        """The window anchors to the audible end (60s), not the file end
        (62s): a punch 5s before the audible end is inside the window even
        though it is 7s before end-of-file."""
        stem = _punchy_stem(62.0, punches=[55.0])
        marks = detect_ending_punches(stem, _SR, self._mix(), _SR)
        assert len(marks) == 1
