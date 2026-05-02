"""Diagnostic metrics for tier and group activation.

Two structured metrics that surface what most of the existing scalar
metrics can't: which tiers and groups the placer actually reaches.
The matrix-panel dogfood (PR #151) and the weighted-suitability null
result both showed that narrow generator changes can be invisible to
the panel because most placements concentrate on a few tiers and a
few groups. These metrics make that concentration measurable.

- ``tier_placement_breakdown``: payload maps tier prefix
  (``"01_BASE"``, ``"02_GEO"``, ``"04_BEAT"``, ``"06_PROP"``,
  ``"07_COMP"``, ``"08_HERO"``) to placement count. Scalar value is
  the count of distinct tier prefixes that received ≥1 placement —
  a higher value means the song is exercising more of the tier
  hierarchy.
- ``group_utilization``: payload maps placement-target group name
  to placement count. Scalar value is the number of distinct groups
  that received ≥1 placement.

Tier prefix is read from the placement target name (e.g.,
``"08_HERO_MegaTree"`` → tier ``"08_HERO"``); names without an
underscore-separated tier prefix bucket into ``"unknown"``.
"""
from __future__ import annotations

import re

from src.evaluation.metrics import (
    DEFAULT_TOLERANCE,
    MetricDefinition,
    MetricKind,
    register,
)
from src.evaluation.models import MetricValue, SequenceSummary


# Match the conventional tier-prefixed group names emitted by the
# grouper (see src/grouper/grouper.py): two digits, underscore, role
# token, optional further name. Anything that doesn't match falls into
# the "unknown" bucket — useful as a sentinel for direct-model
# placements or non-conventional names.
_TIER_PREFIX_RE = re.compile(r"^(\d{2}_[A-Z]+)(?:_|$)")


def _tier_prefix(target_name: str) -> str:
    m = _TIER_PREFIX_RE.match(target_name)
    return m.group(1) if m else "unknown"


def tier_placement_breakdown(summary: SequenceSummary) -> MetricValue:
    counts: dict[str, int] = {}
    for p in summary.placements:
        prefix = _tier_prefix(p.model_name)
        counts[prefix] = counts.get(prefix, 0) + 1
    active = [k for k, v in counts.items() if v > 0 and k != "unknown"]
    return MetricValue(
        name="tier_placement_breakdown",
        kind=MetricKind.STRUCTURED.value,
        value=float(len(active)),
        payload={"counts": dict(sorted(counts.items())), "active_tiers": sorted(active)},
        reliability="ok" if summary.placements else "no_placements",
    )


def group_utilization(summary: SequenceSummary) -> MetricValue:
    counts: dict[str, int] = {}
    for p in summary.placements:
        counts[p.model_name] = counts.get(p.model_name, 0) + 1
    return MetricValue(
        name="group_utilization",
        kind=MetricKind.STRUCTURED.value,
        value=float(len(counts)),
        payload={"counts": dict(sorted(counts.items()))},
        reliability="ok" if summary.placements else "no_placements",
    )


register(
    MetricDefinition(
        name="tier_placement_breakdown",
        kind=MetricKind.STRUCTURED,
        gated=False,
        tolerance=DEFAULT_TOLERANCE,
        compute=tier_placement_breakdown,
        pro_comparable=False,
        higher_is_better=True,
    )
)

register(
    MetricDefinition(
        name="group_utilization",
        kind=MetricKind.STRUCTURED,
        gated=False,
        tolerance=DEFAULT_TOLERANCE,
        compute=group_utilization,
        pro_comparable=False,
        higher_is_better=True,
    )
)
