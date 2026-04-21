"""Palette metrics for the quality calibration harness."""
from __future__ import annotations

from collections import defaultdict

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.metrics import (
    DEFAULT_TOLERANCE,
    MetricDefinition,
    MetricKind,
    register,
)


def palette_top5_colors(summary: SequenceSummary) -> MetricValue:
    """Compute the 5 most-used colors by total lit-time across all placements."""
    color_time: dict[str, float] = defaultdict(float)

    for placement in summary.placements:
        if not placement.palette_colors:
            continue
        duration = placement.end_ms - placement.start_ms
        if duration <= 0:
            continue
        share_per_color = duration / len(placement.palette_colors)
        for color in placement.palette_colors:
            color_time[color] += share_per_color

    if not color_time:
        return MetricValue(
            name="palette_top5_colors",
            kind=MetricKind.STRUCTURED.value,
            value=0.0,
            payload=[],
            reliability="ok",
        )

    total = sum(color_time.values())
    top5 = sorted(color_time.items(), key=lambda kv: kv[1], reverse=True)[:5]
    payload = [[color, time_ms / total] for color, time_ms in top5]

    return MetricValue(
        name="palette_top5_colors",
        kind=MetricKind.STRUCTURED.value,
        value=payload[0][1],
        payload=payload,
        reliability="ok",
    )


def per_section_palette_diversity(
    summary: SequenceSummary,
    sections: list[dict] | None = None,
) -> MetricValue:
    """Compute unique color count per audio-derived section."""
    if not sections:
        sections = [{"start_ms": 0, "end_ms": summary.duration_ms, "label": "whole"}]

    if not summary.placements:
        payload = [
            {
                "section_label": s["label"],
                "start_ms": s["start_ms"],
                "end_ms": s["end_ms"],
                "unique_colors": 0,
            }
            for s in sections
        ]
        return MetricValue(
            name="per_section_palette_diversity",
            kind=MetricKind.PER_SECTION.value,
            value=0.0,
            payload=payload,
            reliability="ok",
        )

    payload = []
    for section in sections:
        sec_start = section["start_ms"]
        sec_end = section["end_ms"]
        unique_colors: set[str] = set()
        for placement in summary.placements:
            if placement.start_ms < sec_end and placement.end_ms > sec_start:
                unique_colors.update(placement.palette_colors)
        payload.append({
            "section_label": section["label"],
            "start_ms": sec_start,
            "end_ms": sec_end,
            "unique_colors": len(unique_colors),
        })

    mean_unique = sum(e["unique_colors"] for e in payload) / len(payload)

    return MetricValue(
        name="per_section_palette_diversity",
        kind=MetricKind.PER_SECTION.value,
        value=mean_unique,
        payload=payload,
        reliability="ok",
    )


register(MetricDefinition(
    name="palette_top5_colors",
    kind=MetricKind.STRUCTURED,
    gated=True,
    tolerance=None,
    compute=palette_top5_colors,
    pro_comparable=True,
))

register(MetricDefinition(
    name="per_section_palette_diversity",
    kind=MetricKind.PER_SECTION,
    gated=True,
    tolerance=None,
    compute=per_section_palette_diversity,
    pro_comparable=True,
))
