"""Rare drum-fill / riff detection (snare-roll burst on the isolated snare
stem).

Second design (2026-07-18). The first version (bass-band onset burst AND
accelerated chord change) was validated against a rough, separately-
computed onset approximation rather than the actual shipped code path,
and failed on real data: it missed both of the user's originally-confirmed
moments and produced 9 candidates the user rejected on spot-check (0/9
confirmed). See CLAUDE.md -> "Riff/Fill Detector for Moving Head Accent"
for that history — this module replaces it entirely.

This version detects the much more literal, physically-grounded signal a
"riff" moment turned out to actually be: a rapid snare-drum roll/fill,
found directly by listening to a real isolated snare stem (drumsep
`redoblante`, see src/analyzer/drum_stems.py::separate_snare). A burst is
>=3 onsets on the snare stem with consecutive gaps <=0.2s — validated on
"bar-guitar-and-a-honky-tonk-crowd": this exact formula found all 15
candidates in the song, and BOTH of the user's originally-confirmed
moments (~33s, ~43s) landed cleanly as bursts with no extra machinery
needed. 5 additional candidates were spot-checked by ear and all 5
confirmed (33s, 43s, 45.7s, 132.4s, 190.9s) — a materially better hit rate
than the first design's 0/9.

Rare-by-design note: unlike crash_accents (deliberately sparse, most songs
get zero marks), this signal fires roughly once every 13s on a song with
frequent fills — it is NOT tuned to be rare. The generator side is
responsible for keeping the resulting accent visually rare/distinct
(placement cadence, not detection sparsity).
"""
from __future__ import annotations

import numpy as np

from src.analyzer.result import TimingMark

_BURST_MIN_ONSETS = 3
_BURST_MAX_GAP_S = 0.2
_MIN_GAP_MS = 1_000


def detect_riff_bursts(
    snare_audio: np.ndarray,
    snare_sample_rate: int,
) -> list[TimingMark]:
    """Return snare-roll/fill moments: runs of >=3 onsets on the isolated
    snare stem with consecutive gaps <=0.2s. *snare_audio* is the
    demucs+drumsep snare-isolated mono array
    (drum_stems.separate_snare). No stem -> no marks.
    """
    if snare_audio.size == 0:
        return []

    import librosa

    onset_env = librosa.onset.onset_strength(y=snare_audio, sr=snare_sample_rate)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=snare_sample_rate, backtrack=True,
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=snare_sample_rate)
    if onset_times.size == 0:
        return []

    marks_ms: list[int] = []
    n = len(onset_times)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and onset_times[j + 1] - onset_times[j] <= _BURST_MAX_GAP_S:
            j += 1
        if j - i + 1 >= _BURST_MIN_ONSETS:
            mid_s = (onset_times[i] + onset_times[j]) / 2
            time_ms = int(round(mid_s * 1000))
            if not marks_ms or time_ms - marks_ms[-1] >= _MIN_GAP_MS:
                marks_ms.append(time_ms)
            i = j + 1
        else:
            i += 1

    return [TimingMark(time_ms=t, confidence=None, label="riff_burst")
            for t in marks_ms]
