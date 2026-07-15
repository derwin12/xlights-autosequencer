"""Rare whole-house crash/transient detection.

Distinct from ``derive_energy_impacts`` (src/analyzer/derived.py): that
detector averages energy over a 1-second window and is tuned for
section-level energy jumps. It was verified (2026-07-14, against a real
cached hierarchy for Dream On/Aerosmith, 201.9s) to dilute genuine
sub-second percussive transients well below its 1.8x threshold -- two
known audible crashes (50.85s, ~190s) both measured only ~1.3x with that
windowing.

This module was itself recalibrated once against that same song after an
initial full-spectrum onset-strength design failed two ways: it missed
both known crashes (their full-spectrum ratio was only ~1.2-2.5x the
song's own level) while flagging the song's very first audio frame as the
single largest spectral-flux value in the track -- an edge artifact, not a
crash: that moment is the *quietest* half-second in the whole song (RMS
~0.05 vs a track RMS of ~0.22), but transitioning out of near-silence
produces a huge relative onset-strength spike regardless of loudness.

Two changes fixed that:
  1. A **treble-band-only** (>=4000Hz) onset envelope instead of
     full-spectrum -- a cymbal-style crash is specifically bright/
     high-frequency, unlike an ordinary loud low/mid-weighted hit
     (kick, snare, guitar chord), so this feature discriminates a genuine
     crash from merely-loud passages far better. On the validated song it
     isolated the ~190s crash as the single strongest, clearly-separated
     treble transient in the entire track.
  2. A **pre-transient RMS floor**: require the 500ms immediately before
     a candidate to already carry real energy (>=40% of the song's
     median RMS). This is what actually distinguishes "a crash within
     ongoing music" from "the song's cold open out of silence" -- the
     false-positive frame's pre-transient RMS was 1% of median; both real
     crashes were 77-95%.

Even after both fixes, the weaker of the two known crashes (50.85s) did
not clear a ratio floor high enough to avoid also admitting several
merely-loud (not user-flagged) moments elsewhere in the same song --
there is no clean statistical gap between "the one crash a listener
noticed" and "an ordinary loud drum/guitar hit" at that signal strength.
Per explicit user decision (2026-07-14): tune for the clear, cleanly
isolated case only (a single treble transient dramatically above
everything else in the song) and accept missing quieter crashes like
50.85s, rather than loosening the floor and admitting false positives.
`_RATIO_FLOOR` reflects that -- it is deliberately high enough that most
songs, and even the weaker of this module's own two ground-truth crashes,
produce zero marks. See CLAUDE.md -> "Crash/Transient Detector for
Whole-House Accent" for the full background.

Vocal-proximity exclusion is intentionally NOT applied here -- it depends
on WhisperX word timing, which is a generator-side input
(``GenerationConfig.vocal_words``) not available during hierarchy
analysis. See ``src/generator/effect_placer.py::_place_crash_accents``.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.result import TimingMark

_HOP_LENGTH = 512
_N_FFT = 2048
_TREBLE_FMIN_HZ = 4000.0
# A candidate's own onset-strength value must clear this multiple of the
# song's median treble-onset level. Calibrated so only a single, cleanly
# isolated extreme transient qualifies (validated song: the true crash hit
# 6.17x; the next-loudest ordinary moment in the same song was 5.66x and
# is meant to stay excluded).
_RATIO_FLOOR = 6.0
# The 500ms immediately before a candidate must average at least this
# fraction of the song's median full-mix RMS -- excludes a transient that
# is really just the transition out of near-silence (e.g. the track's own
# cold open), which produces a large *relative* spectral-flux spike despite
# being the quietest moment in the song.
_PRE_TRANSIENT_RMS_FLOOR_RATIO = 0.4
_PRE_TRANSIENT_WINDOW_MS = 500
# Crashes are rare by design -- never allow two marks closer than this.
_MIN_GAP_MS = 10_000
# Hard cap regardless of how many candidates pass the thresholds above.
_MAX_MARKS = 5


def detect_crash_accents(audio: np.ndarray, sample_rate: int) -> list[TimingMark]:
    """Return up to `_MAX_MARKS` rare, cleanly-isolated percussive transients.

    Each candidate is a genuine local maximum (at least `_MIN_GAP_MS` from
    any other) of the treble-band (>=4000Hz) onset-strength envelope that
    clears both `_RATIO_FLOOR` over the song's own median and the
    pre-transient RMS floor.
    """
    if audio.size == 0:
        return []

    import librosa
    from scipy.signal import find_peaks

    stft = np.abs(librosa.stft(audio, n_fft=_N_FFT, hop_length=_HOP_LENGTH))
    freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=_N_FFT)
    treble_stft = stft[freqs >= _TREBLE_FMIN_HZ, :]
    onset_env = librosa.onset.onset_strength(
        S=librosa.amplitude_to_db(treble_stft, ref=np.max),
        sr=sample_rate,
        hop_length=_HOP_LENGTH,
    )
    rms = librosa.feature.rms(y=audio, hop_length=_HOP_LENGTH)[0]
    n = min(len(onset_env), len(rms))
    if n == 0:
        return []
    onset_env = onset_env[:n]
    rms = rms[:n]

    median_onset = float(np.median(onset_env))
    median_rms = float(np.median(rms))
    if median_onset <= 0 or median_rms <= 0:
        return []

    min_gap_frames = max(1, int(round(_MIN_GAP_MS / 1000 * sample_rate / _HOP_LENGTH)))
    lead_frames = max(1, int(round(_PRE_TRANSIENT_WINDOW_MS / 1000 * sample_rate / _HOP_LENGTH)))

    peak_indices, _ = find_peaks(onset_env, distance=min_gap_frames)

    candidates: list[tuple[int, float]] = []
    for i in peak_indices:
        val = float(onset_env[i])
        if val / median_onset < _RATIO_FLOOR:
            continue
        pre_window = rms[max(0, i - lead_frames):i]
        pre_mean = float(pre_window.mean()) if pre_window.size else 0.0
        if pre_mean / median_rms < _PRE_TRANSIENT_RMS_FLOOR_RATIO:
            continue
        time_ms = int(round(i * _HOP_LENGTH * 1000 / sample_rate))
        candidates.append((time_ms, val))

    candidates.sort(key=lambda c: c[1], reverse=True)
    top = candidates[:_MAX_MARKS]
    top.sort(key=lambda c: c[0])

    return [TimingMark(time_ms=t, confidence=None, label="crash") for t, _ in top]
