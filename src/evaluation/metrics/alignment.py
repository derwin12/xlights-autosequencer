"""Beat alignment metric: beat_alignment_pct."""
from __future__ import annotations

import bisect

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    MetricTolerance,
    register,
)

_BEAT_WINDOW_MS = 80


def beat_alignment_pct(
    summary: SequenceSummary, beats: list[int] | None = None
) -> MetricValue:
    """Return fraction of placements whose start_ms falls within ±80ms of any beat.

    Args:
        summary: The sequence to evaluate.
        beats:   Beat timestamps in milliseconds (from madmom analysis).
                 None or empty list → returns 0.0.
    """
    _zero = MetricValue(
        name="beat_alignment_pct",
        kind=MetricKind.SCALAR,
        value=0.0,
        payload=None,
        reliability="ok",
    )

    if not summary.placements:
        return _zero

    if not beats:
        return _zero

    sorted_beats = sorted(beats)
    aligned = 0

    for placement in summary.placements:
        t = placement.start_ms
        # Binary search: find insertion point for t in sorted_beats
        idx = bisect.bisect_left(sorted_beats, t)

        # Check the nearest candidates: the beat just before and at/after idx
        closest_dist = float("inf")
        for i in (idx - 1, idx):
            if 0 <= i < len(sorted_beats):
                dist = abs(t - sorted_beats[i])
                if dist < closest_dist:
                    closest_dist = dist

        if closest_dist <= _BEAT_WINDOW_MS:
            aligned += 1

    return MetricValue(
        name="beat_alignment_pct",
        kind=MetricKind.SCALAR,
        value=aligned / len(summary.placements),
        payload=None,
        reliability="ok",
    )


register(
    MetricDefinition(
        name="beat_alignment_pct",
        kind=MetricKind.SCALAR,
        gated=True,
        tolerance=MetricTolerance(kind="absolute", value=0.03),
        compute=beat_alignment_pct,
        pro_comparable=True,
    )
)
