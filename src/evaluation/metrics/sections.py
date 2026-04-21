"""Section transition delta metric for the quality calibration harness."""
from __future__ import annotations

from src.evaluation.models import MetricValue, Placement, SequenceSummary
from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    register,
)
from src.evaluation.metrics.effects import js_divergence


def _color_distribution(placements: list[Placement]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for p in placements:
        for c in p.palette_colors:
            counts[c] = counts.get(c, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {c: v / total for c, v in counts.items()}


def _effect_distribution(placements: list[Placement]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for p in placements:
        if p.effect_type != "Unknown":
            counts[p.effect_type] = counts.get(p.effect_type, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {e: v / total for e, v in counts.items()}


def _placements_in_window(
    placements: tuple[Placement, ...], start_ms: int, end_ms: int
) -> list[Placement]:
    """Return placements whose start_ms falls within [start_ms, end_ms)."""
    return [p for p in placements if start_ms <= p.start_ms < end_ms]


def section_transition_delta(
    summary: SequenceSummary,
    sections: list[dict] | None = None,
) -> MetricValue:
    """Measure how much the sequence changes at each section boundary.

    For each consecutive section pair (A → B):
    - Collect placements in the last 20% of A and first 20% of B.
    - Compute JS divergence between color distributions (palette_delta).
    - Compute JS divergence between effect histograms (effect_delta).
    - transition_score = 0.5 * palette_delta + 0.5 * effect_delta

    Returns MetricValue with:
    - value = mean transition_score across all boundaries (0.0 if < 2 sections)
    - payload = list of per-boundary dicts
    """
    _zero = MetricValue(
        name="section_transition_delta",
        kind=MetricKind.PER_SECTION.value,
        value=0.0,
        payload=[],
        reliability="ok",
    )

    if not sections or len(sections) < 2:
        return _zero

    payload = []
    for i in range(len(sections) - 1):
        sec_a = sections[i]
        sec_b = sections[i + 1]

        # Last 20% of section A
        a_start = sec_a["start_ms"]
        a_end = sec_a["end_ms"]
        a_duration = a_end - a_start
        a_window_start = a_start + int(a_duration * 0.8)
        a_placements = _placements_in_window(summary.placements, a_window_start, a_end)

        # First 20% of section B
        b_start = sec_b["start_ms"]
        b_end = sec_b["end_ms"]
        b_duration = b_end - b_start
        b_window_end = b_start + int(b_duration * 0.2)
        b_placements = _placements_in_window(summary.placements, b_start, b_window_end)

        palette_a = _color_distribution(a_placements)
        palette_b = _color_distribution(b_placements)
        palette_delta = js_divergence(palette_a, palette_b) if (palette_a or palette_b) else 0.0

        effects_a = _effect_distribution(a_placements)
        effects_b = _effect_distribution(b_placements)
        effect_delta = js_divergence(effects_a, effects_b) if (effects_a or effects_b) else 0.0

        transition_score = 0.5 * palette_delta + 0.5 * effect_delta

        payload.append({
            "boundary_label": f"{sec_a['label']} \u2192 {sec_b['label']}",
            "palette_delta": palette_delta,
            "effect_delta": effect_delta,
            "transition_score": transition_score,
        })

    mean_score = sum(e["transition_score"] for e in payload) / len(payload)

    return MetricValue(
        name="section_transition_delta",
        kind=MetricKind.PER_SECTION.value,
        value=mean_score,
        payload=payload,
        reliability="ok",
    )


register(MetricDefinition(
    name="section_transition_delta",
    kind=MetricKind.PER_SECTION,
    gated=True,
    tolerance=None,
    compute=section_transition_delta,
    pro_comparable=True,
))
