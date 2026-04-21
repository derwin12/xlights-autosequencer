"""Effect histogram metrics for the quality calibration harness."""
from __future__ import annotations

import math

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.metrics import (
    DEFAULT_TOLERANCE,
    MetricDefinition,
    MetricKind,
    register,
)


def effect_type_histogram(summary: SequenceSummary) -> MetricValue:
    """Compute a normalized histogram of effect types.

    Returns a MetricValue where:
    - value = unknown_effect_fraction (0.0 if all effects are known)
    - payload = {"histogram": {effect_type: fraction, ...}, "unknown_fraction": float}

    The histogram covers only non-"Unknown" effect types, normalized to sum to 1.0
    over the known vocabulary.  Empty placements yields value=0.0 and empty histogram.
    """
    placements = summary.placements

    if not placements:
        return MetricValue(
            name="effect_type_histogram",
            kind=MetricKind.DISTRIBUTION.value,
            value=0.0,
            payload={"histogram": {}, "unknown_fraction": 0.0},
            reliability="ok",
        )

    total = len(placements)
    counts: dict[str, int] = {}
    unknown_count = 0

    for p in placements:
        if p.effect_type == "Unknown":
            unknown_count += 1
        else:
            counts[p.effect_type] = counts.get(p.effect_type, 0) + 1

    unknown_fraction = unknown_count / total
    known_total = total - unknown_count

    if known_total == 0:
        histogram: dict[str, float] = {}
    else:
        histogram = {et: count / known_total for et, count in counts.items()}

    return MetricValue(
        name="effect_type_histogram",
        kind=MetricKind.DISTRIBUTION.value,
        value=unknown_fraction,
        payload={"histogram": histogram, "unknown_fraction": unknown_fraction},
        reliability="ok",
    )


def js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Compute Jensen-Shannon divergence between two normalized histograms.

    Both p and q should be normalized dicts (values sum to 1.0) over their
    own vocabulary.  The divergence is computed over the UNION of keys.
    Result is bounded in [0, 1] using base-2 logarithms.

    Returns 0.0 if both dicts are empty.
    """
    vocab = set(p) | set(q)
    if not vocab:
        return 0.0

    kl_pm = 0.0
    kl_qm = 0.0

    for key in vocab:
        p_val = p.get(key, 0.0)
        q_val = q.get(key, 0.0)
        m = 0.5 * (p_val + q_val)
        if m == 0.0:
            continue
        if p_val > 0.0:
            kl_pm += p_val * math.log2(p_val / m)
        if q_val > 0.0:
            kl_qm += q_val * math.log2(q_val / m)

    jsd = 0.5 * kl_pm + 0.5 * kl_qm
    return max(0.0, min(1.0, jsd))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register(
    MetricDefinition(
        name="effect_type_histogram",
        kind=MetricKind.DISTRIBUTION,
        gated=True,
        tolerance=None,  # DEFAULT_TOLERANCE (10% relative) applied at comparison time
        compute=effect_type_histogram,
        pro_comparable=True,
    )
)
