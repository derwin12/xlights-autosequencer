"""Rare guitar/bass riff or fill detection (bass-burst + chord-acceleration).

Validated 2026-07-18 against "bar-guitar-and-a-honky-tonk-crowd" (user
listened and confirmed 5 moments by ear via the mp3 review UI, at ~33s,
~43s, ~60.6s, ~96.5s, ~149.3s). Companion to crash_accents.py — same "rare,
isolated moment" design goal, but a structurally different event: a crash
is one isolated treble transient, a riff/fill is a *cluster* of low/low-mid
onsets, so the detection shape (burst counting, not single-peak isolation
scoring) is deliberately different.

Two signals, neither selective alone:

- **Bass burst**: >=3 bass-band (20-250Hz, same cut as
  ``LibrosaBassAlgorithm``) onset-envelope peaks within a 1.0s window.
  Computed on the demucs bass STEM, not the full mix (same isolation
  lesson crash_accents learned the hard way — full-mix analysis gets
  fooled by unrelated loud moments). Alone: 12 hits in a 197s song, too
  frequent to be a rare accent (this song's bassline is just consistently
  busy).
- **Accelerated chord change**: two adjacent marks in the song's Chordino
  chord track landing <=0.6s apart, inside the burst's window (+/-1.5s of
  the burst span). Alone: 21 hits in the same song, including ordinary
  passing-tone chord changes with no burst underneath.

The AND of both, computed against the validated song, reproduced exactly
the 5 user-confirmed moments and nothing else (0 false positives out of the
12 raw bass bursts and 21 raw fast-chord-changes considered independently).

**Single-song validation only so far.** crash_accents.py shipped only
after a 6-song panel; this formula has one song's worth of ground truth.
Treat results with the same caution until validated against 2-3 more
songs — see CLAUDE.md -> "Future Work" for the follow-up note.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.result import TimingMark, TimingTrack

_HOP_LENGTH = 512
_N_FFT = 2048
_BASS_FMIN_HZ = 20.0
_BASS_FMAX_HZ = 250.0

# A "burst" is >=3 onset-envelope peaks within this rolling window.
_BURST_WINDOW_S = 1.0
_BURST_MIN_PEAKS = 3

# Two adjacent chord marks landing this close together counts as an
# "accelerated" change (validated song's typical chord duration is
# ~1.3-1.5s; the 5 confirmed moments measured 0.33-0.56s gaps).
_CHORD_ACCEL_GAP_S = 0.6
# How far around a burst's span to look for an accelerated chord change.
_CHORD_SEARCH_MARGIN_S = 1.5

_MIN_GAP_MS = 3_000


def detect_riff_bursts(
    bass_audio: np.ndarray,
    bass_sample_rate: int,
    chords: TimingTrack | None,
) -> list[TimingMark]:
    """Return rare guitar/bass riff or fill moments.

    *bass_audio* is the demucs bass-stem mono array. *chords* is the
    song's Chordino chord-change track (``HierarchyResult.chords``). No
    chord track -> no marks (the accelerated-chord-change signal is
    required, not optional — a bare bass burst alone is not selective
    enough, see module docstring).
    """
    if bass_audio.size == 0 or chords is None or not chords.marks:
        return []

    import librosa

    stft = np.abs(librosa.stft(bass_audio, n_fft=_N_FFT, hop_length=_HOP_LENGTH))
    freqs = librosa.fft_frequencies(sr=bass_sample_rate, n_fft=_N_FFT)
    band_stft = stft[(freqs >= _BASS_FMIN_HZ) & (freqs <= _BASS_FMAX_HZ), :]
    if band_stft.size == 0 or float(band_stft.max()) <= 0.0:
        return []

    # Same onset-strength + onset-detect approach as
    # LibrosaBassAlgorithm._band_onsets — a genuine spectral-novelty onset
    # detector (with backtracking), not a raw envelope peak-pick, so it
    # doesn't fire on ordinary frame-to-frame noise jitter.
    onset_env = librosa.onset.onset_strength(
        S=librosa.amplitude_to_db(band_stft, ref=np.max),
        sr=bass_sample_rate, hop_length=_HOP_LENGTH,
    )
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=bass_sample_rate,
        hop_length=_HOP_LENGTH, backtrack=True,
    )
    peak_times = librosa.frames_to_time(
        onset_frames, sr=bass_sample_rate, hop_length=_HOP_LENGTH,
    )
    if peak_times.size == 0:
        return []

    bursts: list[tuple[float, float]] = []  # (start_s, end_s)
    n = len(peak_times)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and peak_times[j + 1] - peak_times[i] <= _BURST_WINDOW_S:
            j += 1
        if j - i + 1 >= _BURST_MIN_PEAKS:
            bursts.append((float(peak_times[i]), float(peak_times[j])))
            i = j + 1
        else:
            i += 1
    if not bursts:
        return []

    chord_times = sorted(m.time_ms / 1000.0 for m in chords.marks)

    def _has_accelerated_chord_change(start_s: float, end_s: float) -> bool:
        lo, hi = start_s - _CHORD_SEARCH_MARGIN_S, end_s + _CHORD_SEARCH_MARGIN_S
        nearby = [t for t in chord_times if lo <= t <= hi]
        return any(
            nearby[k + 1] - nearby[k] <= _CHORD_ACCEL_GAP_S
            for k in range(len(nearby) - 1)
        )

    marks_ms: list[int] = []
    for start_s, end_s in bursts:
        if not _has_accelerated_chord_change(start_s, end_s):
            continue
        time_ms = int(round((start_s + end_s) / 2 * 1000))
        if marks_ms and time_ms - marks_ms[-1] < _MIN_GAP_MS:
            continue
        marks_ms.append(time_ms)

    return [TimingMark(time_ms=t, confidence=None, label="riff_burst")
            for t in marks_ms]
