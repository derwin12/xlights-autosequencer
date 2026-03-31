"""Detect the shape of an energy arc from a list of float values."""

from __future__ import annotations

import statistics


def detect_energy_arc(energy_curve: list[float]) -> str:
    """Classify the shape of an energy curve.

    Returns one of: "ramp", "arch", "flat", "valley", "sawtooth", "bookend".

    The curve is sampled at 10 equally-spaced points before classification.
    """
    # Edge cases
    if len(energy_curve) <= 1:
        return "flat"
    if len(energy_curve) == 2:
        diff = energy_curve[1] - energy_curve[0]
        if abs(diff) < 0.05:
            return "flat"
        return "ramp"

    # Sample 10 equally-spaced points from the curve
    n = 10
    samples = _sample(energy_curve, n)

    # 1. Flat: std dev < 0.05
    try:
        std = statistics.stdev(samples)
    except statistics.StatisticsError:
        return "flat"
    if std < 0.05:
        return "flat"

    # 2. Valley: trough in middle 40-60%; both halves average > trough
    if _check_valley(samples):
        return "valley"

    # 3. Arch: peak in middle 40-60%; both halves average < peak
    if _check_arch(samples):
        return "arch"

    # 4. Bookend: first 20% avg > middle 60% avg AND last 20% avg > middle 60% avg
    first_end = samples[:2]   # first 20% of 10 samples = 2 samples
    last_end = samples[-2:]   # last 20% = 2 samples
    middle = samples[2:-2]    # middle 60% = 6 samples
    first_avg = sum(first_end) / len(first_end)
    last_avg = sum(last_end) / len(last_end)
    mid_avg = sum(middle) / len(middle)
    if first_avg > mid_avg and last_avg > mid_avg:
        return "bookend"

    # 5. Sawtooth: >= 2 direction changes (oscillating pattern)
    direction_changes = _direction_changes(samples)
    if direction_changes >= 2:
        return "sawtooth"

    # 6. Ramp: linear regression slope > 0.02
    slope = _linear_slope(samples)
    if slope > 0.02:
        return "ramp"

    return "flat"


def _sample(curve: list[float], n: int) -> list[float]:
    """Sample n equally-spaced points from curve via linear interpolation."""
    if len(curve) == n:
        return list(curve)
    result = []
    length = len(curve) - 1
    for i in range(n):
        pos = i * length / (n - 1)
        lo = int(pos)
        hi = min(lo + 1, length)
        frac = pos - lo
        value = curve[lo] * (1.0 - frac) + curve[hi] * frac
        result.append(value)
    return result


def _linear_slope(samples: list[float]) -> float:
    """Compute the slope of the best-fit line through the samples (x = 0..n-1 normalized to 0..1)."""
    n = len(samples)
    xs = [i / (n - 1) for i in range(n)]
    x_mean = sum(xs) / n
    y_mean = sum(samples) / n
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, samples))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _direction_changes(samples: list[float]) -> int:
    """Count the number of direction changes (sign changes in successive differences)."""
    if len(samples) < 3:
        return 0
    diffs = [samples[i + 1] - samples[i] for i in range(len(samples) - 1)]
    # Filter out near-zero diffs to avoid noise counting as changes
    threshold = 0.05
    filtered = [d for d in diffs if abs(d) > threshold]
    if len(filtered) < 2:
        return 0
    changes = 0
    for i in range(1, len(filtered)):
        if filtered[i] * filtered[i - 1] < 0:
            changes += 1
    return changes


def _check_arch(samples: list[float]) -> bool:
    """Return True if the curve has an arch shape."""
    n = len(samples)
    peak_val = max(samples)
    peak_idx = samples.index(peak_val)
    # Peak must be in middle 40-60%
    lo = int(0.4 * n)
    hi = int(0.6 * n)
    # For n=10: lo=4, hi=6 → indices 4 or 5 (0-based)
    if not (lo <= peak_idx < hi + 1):
        return False
    first_half = samples[:peak_idx]
    second_half = samples[peak_idx + 1:]
    if not first_half or not second_half:
        return False
    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    return first_avg < peak_val and second_avg < peak_val


def _check_valley(samples: list[float]) -> bool:
    """Return True if the curve has a valley shape."""
    n = len(samples)
    trough_val = min(samples)
    trough_idx = samples.index(trough_val)
    # Trough must be in middle 40-60%
    lo = int(0.4 * n)
    hi = int(0.6 * n)
    if not (lo <= trough_idx < hi + 1):
        return False
    first_half = samples[:trough_idx]
    second_half = samples[trough_idx + 1:]
    if not first_half or not second_half:
        return False
    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    return first_avg > trough_val and second_avg > trough_val
