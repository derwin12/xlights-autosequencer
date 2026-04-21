"""Ours-only internal metrics: tier_utilization, theme_assignment_consistency.

These metrics access information only available in our generated sequences
(not in pro sequences) and are gated for regression detection against our
own baseline.
"""
from __future__ import annotations

from collections import Counter

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    MetricTolerance,
    register,
)


def tier_utilization(
    summary: SequenceSummary,
    sections: list[dict] | None = None,
) -> MetricValue:
    """Fraction of total models that have at least one placement in each section.

    Uses a simple heuristic: total_models = all unique model_names in the summary;
    active_models per section = unique model_names that appear in any placement
    within that section's time window.  The returned value is the mean utilization
    across all sections.
    """
    total_models = len(summary.model_names)

    if total_models == 0:
        return MetricValue(
            name="tier_utilization",
            kind=MetricKind.PER_SECTION,
            value=0.0,
            payload=[],
            reliability="ok",
        )

    # Normalise sections: None → one section spanning the whole song.
    if sections is None:
        effective_sections = [
            {"label": "song", "start_ms": 0, "end_ms": summary.duration_ms}
        ]
    else:
        effective_sections = sections

    payload: list[dict] = []
    utilizations: list[float] = []

    for sec in effective_sections:
        label = sec.get("label", "")
        start_ms: int = sec["start_ms"]
        end_ms: int = sec["end_ms"]

        active = {
            p.model_name
            for p in summary.placements
            if p.start_ms < end_ms and p.end_ms > start_ms
        }
        active_count = len(active)
        util = active_count / total_models

        utilizations.append(util)
        payload.append(
            {
                "section_label": label,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "utilization": util,
                "active_models": active_count,
                "total_models": total_models,
            }
        )

    mean_util = sum(utilizations) / len(utilizations) if utilizations else 0.0

    return MetricValue(
        name="tier_utilization",
        kind=MetricKind.PER_SECTION,
        value=mean_util,
        payload=payload,
        reliability="ok",
    )


def theme_assignment_consistency(
    summary: SequenceSummary,
    sections: list[dict] | None = None,
) -> MetricValue:
    """Fraction of repeated-label sections that share the same dominant effect type
    as the first occurrence of that label.

    If sections is None or no label repeats exist, returns 1.0.
    """
    _full = MetricValue(
        name="theme_assignment_consistency",
        kind=MetricKind.SCALAR,
        value=1.0,
        payload={},
        reliability="ok",
    )

    if not sections:
        return _full

    # Count how many times each label appears.
    label_counts: Counter[str] = Counter(sec.get("label", "") for sec in sections)
    repeated_labels = {lbl for lbl, cnt in label_counts.items() if cnt > 1}

    if not repeated_labels:
        return _full

    def dominant_effect(start_ms: int, end_ms: int) -> str | None:
        """Most common effect_type among placements in [start_ms, end_ms)."""
        effects = [
            p.effect_type
            for p in summary.placements
            if p.start_ms < end_ms and p.end_ms > start_ms
            and p.effect_type != "Unknown"
        ]
        if not effects:
            return None
        return Counter(effects).most_common(1)[0][0]

    # For each repeated label, record the dominant effect per section occurrence.
    label_occurrences: dict[str, list[str | None]] = {lbl: [] for lbl in repeated_labels}
    for sec in sections:
        lbl = sec.get("label", "")
        if lbl not in repeated_labels:
            continue
        dom = dominant_effect(sec["start_ms"], sec["end_ms"])
        if dom is not None:
            label_occurrences[lbl].append(dom)

    payload: dict[str, dict] = {}
    consistent_count = 0
    total_count = 0

    for lbl, occurrences in label_occurrences.items():
        if len(occurrences) < 2:
            # Not enough data to evaluate — treat as consistent.
            payload[lbl] = {"occurrences": occurrences, "consistent": True}
            continue

        reference = occurrences[0]
        matching = sum(1 for eff in occurrences[1:] if eff == reference)
        label_consistent = matching == len(occurrences) - 1

        payload[lbl] = {
            "reference_effect": reference,
            "occurrences": occurrences,
            "consistent": label_consistent,
        }
        consistent_count += matching
        total_count += len(occurrences) - 1

    if total_count == 0:
        value = 1.0
    else:
        value = consistent_count / total_count

    return MetricValue(
        name="theme_assignment_consistency",
        kind=MetricKind.SCALAR,
        value=value,
        payload=payload,
        reliability="ok",
    )


register(
    MetricDefinition(
        name="tier_utilization",
        kind=MetricKind.PER_SECTION,
        gated=True,
        tolerance=MetricTolerance(kind="absolute", value=0.05),
        compute=tier_utilization,
        pro_comparable=False,
    )
)

register(
    MetricDefinition(
        name="theme_assignment_consistency",
        kind=MetricKind.SCALAR,
        gated=True,
        tolerance=None,
        compute=theme_assignment_consistency,
        pro_comparable=False,
    )
)
