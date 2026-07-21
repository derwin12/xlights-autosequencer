"""Whole-house restraint metric: whole_house_cluster_count.

Advisory, ours-only metric (no professional-sequence equivalent to compare
against, since it's specific to our own tier-1 01_BASE_All naming
convention). Idea borrowed from a third-party xLights sequencer project
(helix-sequencer, "density and restraint scoring" doc, 2026-07-21) after
reviewing its approach for anything transferable -- not mined from our own
vendor corpus like the effect-placement idioms elsewhere in this project.
Scoped narrowly to whole-house/tier-1 placements specifically, since that's
the exact domain where this project has already had real user-reported
"too much going on at once" incidents (the tier-layering-policy visual-
overwhelm fix, bug-206 Shockwave-on-Shockwave, and the Pictures "shake"
motion tuned down 2026-07-21) -- all caught by manual eyeballing, never by
an automated check.

New and unproven -- set XLIGHT_DISABLE_RESTRAINT_METRIC=1 to skip
registering it entirely (no code change needed) if it turns out to be
noisy or not worth keeping.
"""
from __future__ import annotations

import os

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    MetricTolerance,
    register,
)

# Two whole-house placements landing within this gap read as one cluttered
# burst rather than two separately-earned emphasis moments. Not vendor-
# mined -- a first-draft threshold, same as every other new first-cut
# value in this project; worth eyeballing against a real render before
# treating it as tuned.
_CLUSTER_GAP_MS = 2000

# Matches the established whole-house/tier-1 naming convention used
# throughout the generator (01_BASE_All, 01_BASE_All_FADES) -- see
# xsq_writer._tier_sort_key and CLAUDE.md's tier-1 discussion.
_WHOLE_HOUSE_PREFIX = "01_base_all"


def whole_house_cluster_count(summary: SequenceSummary) -> MetricValue:
    """Count of whole-house (tier-1) placements starting within
    ``_CLUSTER_GAP_MS`` of the previous whole-house placement's end --
    a proxy for "too many whole-layout hits landing in a tight cluster"
    rather than being spaced out to read as distinct, earned moments.
    Lower is more restrained. Returns 0 when there are fewer than two
    whole-house placements to compare.
    """
    whole_house = sorted(
        (p for p in summary.placements if p.model_name.lower().startswith(_WHOLE_HOUSE_PREFIX)),
        key=lambda p: p.start_ms,
    )
    if len(whole_house) < 2:
        return MetricValue(
            name="whole_house_cluster_count",
            kind=MetricKind.SCALAR,
            value=0.0,
            payload=[],
            reliability="ok",
        )

    clusters: list[dict] = []
    for prev, nxt in zip(whole_house, whole_house[1:]):
        gap_ms = nxt.start_ms - prev.end_ms
        if gap_ms < _CLUSTER_GAP_MS:
            clusters.append({
                "prev_end_ms": prev.end_ms,
                "next_start_ms": nxt.start_ms,
                "gap_ms": gap_ms,
            })

    return MetricValue(
        name="whole_house_cluster_count",
        kind=MetricKind.SCALAR,
        value=float(len(clusters)),
        payload=clusters,
        reliability="ok",
    )


if not os.environ.get("XLIGHT_DISABLE_RESTRAINT_METRIC"):
    register(
        MetricDefinition(
            name="whole_house_cluster_count",
            kind=MetricKind.SCALAR,
            gated=True,
            tolerance=MetricTolerance(kind="absolute", value=1),
            compute=whole_house_cluster_count,
            pro_comparable=False,
        )
    )
