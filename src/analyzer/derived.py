"""Derived feature computation for L0 Special Moments.

Computes energy impacts, drops, and gaps from a ValueCurve.
Thresholds validated on 22-song batch (see research.md R2).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.analyzer.result import TimingMark, ValueCurve

# Validated thresholds (research.md R2)
_IMPACT_RATIO = 1.8   # energy increase > 1.8x = impact
_DROP_RATIO = 0.55    # energy decrease < 0.55x = drop
_GAP_THRESHOLD = 5    # energy < 5/100 = silence
_GAP_MIN_MS = 300     # minimum gap duration (ms)
_WINDOW_MS = 1000     # 1-second analysis window


def derive_energy_impacts(curve: "ValueCurve") -> list["TimingMark"]:
    """Find sudden energy increases (>1.8x ratio in 1-second windows).

    Args:
        curve: ValueCurve with 0-100 normalized energy values.

    Returns:
        List of TimingMark with label="impact" at each impact timestamp.
    """
    from src.analyzer.result import TimingMark

    if not curve.values or curve.fps <= 0:
        return []

    frames_per_window = max(1, curve.fps * _WINDOW_MS // 1000)
    values = curve.values
    marks: list[TimingMark] = []

    for i in range(frames_per_window, len(values)):
        prev_start = max(0, i - 2 * frames_per_window)
        prev_end = i - frames_per_window
        curr_start = i - frames_per_window
        curr_end = i

        prev_vals = values[prev_start:prev_end]
        curr_vals = values[curr_start:curr_end]

        if not prev_vals or not curr_vals:
            continue

        prev_avg = sum(prev_vals) / len(prev_vals)
        curr_avg = sum(curr_vals) / len(curr_vals)

        if prev_avg < 1:
            continue

        if curr_avg / prev_avg > _IMPACT_RATIO:
            time_ms = int(curr_start * 1000 / curve.fps)
            marks.append(TimingMark(time_ms=time_ms, confidence=None, label="impact"))

    return _deduplicate_marks(marks, min_gap_ms=500)


def derive_energy_drops(curve: "ValueCurve") -> list["TimingMark"]:
    """Find sudden energy decreases (<0.55x ratio in 1-second windows).

    Args:
        curve: ValueCurve with 0-100 normalized energy values.

    Returns:
        List of TimingMark with label="drop" at each drop timestamp.
    """
    from src.analyzer.result import TimingMark

    if not curve.values or curve.fps <= 0:
        return []

    frames_per_window = max(1, curve.fps * _WINDOW_MS // 1000)
    values = curve.values
    marks: list[TimingMark] = []

    for i in range(frames_per_window, len(values)):
        prev_start = max(0, i - 2 * frames_per_window)
        prev_end = i - frames_per_window
        curr_start = i - frames_per_window
        curr_end = i

        prev_vals = values[prev_start:prev_end]
        curr_vals = values[curr_start:curr_end]

        if not prev_vals or not curr_vals:
            continue

        prev_avg = sum(prev_vals) / len(prev_vals)
        curr_avg = sum(curr_vals) / len(curr_vals)

        if prev_avg < 1:
            continue

        if curr_avg / prev_avg < _DROP_RATIO:
            time_ms = int(curr_start * 1000 / curve.fps)
            marks.append(TimingMark(time_ms=time_ms, confidence=None, label="drop"))

    return _deduplicate_marks(marks, min_gap_ms=500)


def derive_gaps(curve: "ValueCurve") -> list["TimingMark"]:
    """Find silence periods (energy < 5/100 for >300ms).

    Args:
        curve: ValueCurve with 0-100 normalized energy values.

    Returns:
        List of TimingMark with label="gap" and duration_ms set.
    """
    from src.analyzer.result import TimingMark

    if not curve.values or curve.fps <= 0:
        return []

    values = curve.values
    ms_per_frame = 1000 / curve.fps
    marks: list[TimingMark] = []

    gap_start: int | None = None

    for i, v in enumerate(values):
        if v < _GAP_THRESHOLD:
            if gap_start is None:
                gap_start = i
        else:
            if gap_start is not None:
                gap_duration_ms = int((i - gap_start) * ms_per_frame)
                if gap_duration_ms >= _GAP_MIN_MS:
                    time_ms = int(gap_start * ms_per_frame)
                    marks.append(TimingMark(
                        time_ms=time_ms,
                        confidence=None,
                        label="gap",
                        duration_ms=gap_duration_ms,
                    ))
                gap_start = None

    # Handle gap that extends to end of song
    if gap_start is not None:
        gap_duration_ms = int((len(values) - gap_start) * ms_per_frame)
        if gap_duration_ms >= _GAP_MIN_MS:
            time_ms = int(gap_start * ms_per_frame)
            marks.append(TimingMark(
                time_ms=time_ms,
                confidence=None,
                label="gap",
                duration_ms=gap_duration_ms,
            ))

    return marks


def _deduplicate_marks(marks: list["TimingMark"], min_gap_ms: int = 500) -> list["TimingMark"]:
    """Remove marks that are too close together, keeping the first."""
    if not marks:
        return []
    result = [marks[0]]
    for m in marks[1:]:
        if m.time_ms - result[-1].time_ms >= min_gap_ms:
            result.append(m)
    return result
