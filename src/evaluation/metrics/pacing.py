"""Pacing metrics: placements_per_minute, density_energy_correlation."""
from __future__ import annotations

import numpy as np

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.metrics import (
    DEFAULT_TOLERANCE,
    MetricDefinition,
    MetricKind,
    MetricTolerance,
    register,
)


def placements_per_minute(summary: SequenceSummary) -> MetricValue:
    """Return the number of effect placements per minute of song duration."""
    if summary.duration_ms == 0 or len(summary.placements) == 0:
        return MetricValue(
            name="placements_per_minute",
            kind=MetricKind.SCALAR,
            value=0.0,
            payload=None,
            reliability="ok",
        )
    value = len(summary.placements) / (summary.duration_ms / 60_000.0)
    return MetricValue(
        name="placements_per_minute",
        kind=MetricKind.SCALAR,
        value=value,
        payload=None,
        reliability="ok",
    )


def density_energy_correlation(
    summary: SequenceSummary, audio_context: dict | None = None
) -> MetricValue:
    """Pearson correlation between rolling placement density and the L5 energy curve.

    audio_context keys:
        energy_curve: list of (time_ms, energy_float) tuples
        window_ms:    int, bucketing window size (default 500)
    """
    _zero = MetricValue(
        name="density_energy_correlation",
        kind=MetricKind.SCALAR,
        value=0.0,
        payload=None,
        reliability="reduced",
    )

    if audio_context is None:
        return _zero

    energy_curve: list[tuple[int, float]] = audio_context.get("energy_curve", [])
    if not energy_curve:
        return _zero

    window_ms: int = audio_context.get("window_ms", 500)

    # Determine song span from the energy curve boundaries.
    times = [t for t, _ in energy_curve]
    energies_raw = [e for _, e in energy_curve]
    t_min = min(times)
    t_max = max(times)

    if t_max <= t_min:
        return _zero

    # Build window grid aligned to t_min.
    window_starts = list(range(t_min, t_max, window_ms))
    if len(window_starts) < 3:
        return _zero

    # Count placements starting in each window.
    counts = []
    for ws in window_starts:
        we = ws + window_ms
        c = sum(1 for p in summary.placements if ws <= p.start_ms < we)
        counts.append(float(c))

    # Interpolate energy at each window midpoint.
    midpoints = [ws + window_ms / 2.0 for ws in window_starts]
    energies = list(
        np.interp(midpoints, times, energies_raw)
    )

    counts_arr = np.array(counts, dtype=float)
    energies_arr = np.array(energies, dtype=float)

    if len(counts_arr) < 3:
        return _zero

    corr_matrix = np.corrcoef(counts_arr, energies_arr)
    corr = float(corr_matrix[0, 1])

    if np.isnan(corr):
        return _zero

    return MetricValue(
        name="density_energy_correlation",
        kind=MetricKind.SCALAR,
        value=corr,
        payload=None,
        reliability="ok",
    )


register(
    MetricDefinition(
        name="placements_per_minute",
        kind=MetricKind.SCALAR,
        gated=True,
        tolerance=MetricTolerance(kind="relative", value=0.15),
        compute=placements_per_minute,
        pro_comparable=True,
    )
)

register(
    MetricDefinition(
        name="density_energy_correlation",
        kind=MetricKind.SCALAR,
        gated=True,
        tolerance=None,  # caller uses DEFAULT_TOLERANCE (10% relative)
        compute=density_energy_correlation,
        pro_comparable=True,
    )
)
