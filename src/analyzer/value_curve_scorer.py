"""Quality scoring for continuous value curves (energy, spectral flux, etc.).

A good value curve for xLights has:
- High dynamic range (uses the full 0–100 range)
- Temporal structure that correlates with musical events (not flat, not noise)
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "score_value_curve",
]


def score_value_curve(curve: list[int] | list[float]) -> float:
    """Score a value curve on a 0.0–1.0 scale.

    Combines two metrics equally:
    - **Dynamic range**: (max - min) / 100 — how much of the 0–100 range is used.
    - **Temporal structure**: autocorrelation at lag 1 — high means structured
      variation (musical), low means random noise.

    Returns 0.0 for empty or constant curves.
    """
    if not curve or len(curve) < 2:
        return 0.0

    arr = np.array(curve, dtype=np.float64)

    # Dynamic range score: 0 if flat, 1 if full 0-100 range
    val_range = float(arr.max() - arr.min())
    range_score = min(1.0, val_range / 100.0)

    if range_score < 0.01:
        return 0.0  # flat curve

    # Temporal structure: normalized autocorrelation at lag 1
    # High autocorrelation = structured (musical), low = noise
    centered = arr - arr.mean()
    variance = float(np.sum(centered ** 2))
    if variance < 1e-9:
        return 0.0
    autocorr = float(np.sum(centered[:-1] * centered[1:])) / variance
    structure_score = max(0.0, min(1.0, (autocorr + 1.0) / 2.0))  # map [-1,1] → [0,1]

    return round(0.5 * range_score + 0.5 * structure_score, 4)
