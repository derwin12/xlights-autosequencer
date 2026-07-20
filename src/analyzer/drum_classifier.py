"""Drum hit classifier: label each drum onset as kick, snare, or hihat.

Two classification strategies, in preference order:

1. ``classify_drum_events_from_stems`` (preferred, 2026-07-20): compares
   short-window RMS energy across the drumsep-separated kick/snare/cymbals
   stems (src/analyzer/drum_stems.py) at each onset and labels with
   whichever stem is loudest there — real per-instrument evidence instead
   of a guess. Same isolation-over-combined-kit reasoning that drove
   crash_accents.py to a cymbal-isolated stem (see drum_stems.py's module
   docstring): a spectral-band guess on the combined kit conflates kick,
   snare, and cymbal energy in the same window. Note drumsep's "cymbals"
   bucket (platillos) is hihat+crash+ride combined, not hihat alone — this
   is a real accuracy improvement over the fallback below, not a perfect
   hihat isolation.
2. ``classify_drum_events`` (fallback): frequency-band energy ratios on a
   short window of the *combined* drum stem — used when drumsep separation
   is unavailable (no demucs/torch, offline, separation error). Three
   spectral bands are enough to separate the three primary drum types
   reasonably:

     kick   — dominated by sub/low energy  (20-200 Hz)
     hihat  — dominated by high energy     (8 000+ Hz)
     snare  — everything in between (midrange body + transient crack)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.analyzer.result import TimingTrack

# Frequency boundaries (Hz)
_KICK_MAX = 200
_HIHAT_MIN = 8_000

# Window around onset to analyse (ms)
_WINDOW_MS = 60


def classify_drum_events(
    track: "TimingTrack",
    drum_audio: np.ndarray,
    sample_rate: int,
) -> None:
    """Mutate each mark's label in-place with 'kick', 'snare', or 'hihat'.

    Fallback classifier — see module docstring. Prefer
    ``classify_drum_events_from_stems`` when drumsep-separated stems are
    available.

    Args:
        track:       Drum TimingTrack whose marks will be labelled.
        drum_audio:  Mono float32 array of the separated drum stem.
        sample_rate: Sample rate of drum_audio.
    """
    if not track or not track.marks or drum_audio is None:
        return

    # Ensure mono
    if drum_audio.ndim == 2:
        drum_audio = drum_audio.mean(axis=1)

    n_fft = 1024
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    kick_mask  = freqs < _KICK_MAX
    hihat_mask = freqs >= _HIHAT_MIN

    window_samples = max(n_fft, int(_WINDOW_MS * sample_rate / 1000))
    n = len(drum_audio)

    mid_mask = ~kick_mask & ~hihat_mask

    for mark in track.marks:
        center = int(mark.time_ms * sample_rate / 1000)
        segment = drum_audio[center: min(n, center + window_samples)]

        if len(segment) < n_fft:
            segment = np.pad(segment, (0, n_fft - len(segment)))

        spectrum = np.abs(np.fft.rfft(segment[:n_fft]))

        low_e  = float(spectrum[kick_mask].mean())
        mid_e  = float(spectrum[mid_mask].mean())
        high_e = float(spectrum[hihat_mask].mean())
        total  = low_e + mid_e + high_e + 1e-10

        low_ratio  = low_e  / total
        high_ratio = high_e / total

        if low_ratio > 0.60:
            mark.label = "kick"
        elif high_ratio > 0.20:
            mark.label = "hihat"
        else:
            mark.label = "snare"


def classify_drum_events_from_stems(
    track: "TimingTrack",
    kick_audio: np.ndarray | None,
    kick_sample_rate: int,
    snare_audio: np.ndarray | None,
    snare_sample_rate: int,
    cymbals_audio: np.ndarray | None,
    cymbals_sample_rate: int,
) -> None:
    """Mutate each mark's label in-place with 'kick', 'snare', or 'hihat',
    using RMS energy in a short window of each drumsep-separated stem at
    the onset's timestamp — whichever stem is loudest there wins. See
    module docstring for the isolation-over-combined-kit rationale.

    Any of the three stems may be ``None`` (that source failed to
    separate) — its window energy is then treated as 0, so the remaining
    stems still compete normally. No-ops (leaves existing labels
    untouched) if all three are ``None``.
    """
    stems = [
        (kick_audio, kick_sample_rate, "kick"),
        (snare_audio, snare_sample_rate, "snare"),
        (cymbals_audio, cymbals_sample_rate, "hihat"),
    ]
    if not track or not track.marks or all(audio is None for audio, _, _ in stems):
        return

    window_ms = _WINDOW_MS
    for mark in track.marks:
        best_label: str | None = None
        best_energy = -1.0
        for audio, sr, label in stems:
            if audio is None:
                continue
            arr = audio.mean(axis=1) if audio.ndim == 2 else audio
            center = int(mark.time_ms * sr / 1000)
            window_samples = max(1, int(window_ms * sr / 1000))
            segment = arr[center: min(len(arr), center + window_samples)]
            if segment.size == 0:
                continue
            energy = float(np.sqrt(np.mean(np.square(segment))))
            if energy > best_energy:
                best_energy = energy
                best_label = label
        if best_label is not None:
            mark.label = best_label
