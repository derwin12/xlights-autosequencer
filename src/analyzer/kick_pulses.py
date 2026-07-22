"""Rare kick-drum-flourish detection, for occasional individual accents on
props with no useful buffer resolution (e.g. single-pixel floodlights —
see effect_placer.py::_place_floodlight_pulses).

Unlike riff_bursts.py (which runs its own onset detection on a freshly
separated snare stem), this reuses HierarchyResult.kick_hits — already
computed earlier in the pipeline by drum_classifier.py's preferred
stems-based classifier, itself reading the same drumsep kick isolation
(src/analyzer/drum_stems.py::separate_kick) that classify_drum_events_
from_stems already pays for. No extra separation or onset detection is
needed here, just grouping the already-classified kick onset times.

Ordinary kick_hits fire on every kick drum hit (multiple times per second
on a typical song) -- far too frequent for an "occasional" accent. The
same run-grouping formula validated for riff_bursts.py (rare drum-fill
detection: >=3 onsets with consecutive gaps <=0.2s) applied to kicks
instead of snare isolates double-kick/kick-roll flourishes, which are
genuinely rare, rather than firing on the ordinary backbeat.
"""
from __future__ import annotations

from src.analyzer.result import TimingMark

_BURST_MIN_ONSETS = 3
_BURST_MAX_GAP_S = 0.2
_MIN_GAP_MS = 1_000


def detect_kick_pulses(kick_hits: list[TimingMark]) -> list[TimingMark]:
    """Return kick-flourish moments: runs of >=3 kick hits with consecutive
    gaps <=0.2s. *kick_hits* is HierarchyResult.kick_hits (already
    classified elsewhere in the pipeline). No hits -> no marks.
    """
    if not kick_hits:
        return []

    times_s = sorted(m.time_ms / 1000 for m in kick_hits)

    marks_ms: list[int] = []
    n = len(times_s)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and times_s[j + 1] - times_s[j] <= _BURST_MAX_GAP_S:
            j += 1
        if j - i + 1 >= _BURST_MIN_ONSETS:
            mid_s = (times_s[i] + times_s[j]) / 2
            time_ms = int(round(mid_s * 1000))
            if not marks_ms or time_ms - marks_ms[-1] >= _MIN_GAP_MS:
                marks_ms.append(time_ms)
            i = j + 1
        else:
            i += 1

    return [TimingMark(time_ms=t, confidence=None, label="kick_pulse")
            for t in marks_ms]
