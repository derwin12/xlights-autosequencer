"""Vitality metrics: palette luminance proxies.

Palette-derived proxy; not a measurement of rendered light. These
metrics summarise the Rec.601 luma of the colours that appear in each
placement's palette, weighted by placement duration. They do **not**
observe any pixel that xLights actually renders, so the magnitude
should not be interpreted as scene brightness.

Both metrics register with ``higher_is_better=None``: the
direction-of-good has not been validated against rendered output and
the names deliberately avoid words like "brightness", "breathing", or
"dynamics".
"""
from __future__ import annotations

from src.evaluation.models import MetricValue, Placement, SequenceSummary
from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    register,
)


def _hex_to_luma(hex_color: str) -> float:
    """Return the Rec.601 luma (0-255) of a ``#RRGGBB`` string.

    Raises ``ValueError`` on a malformed input.
    """
    s = hex_color.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        raise ValueError(f"expected #RRGGBB, got {hex_color!r}")
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _placement_mean_luma(placement: Placement) -> float | None:
    """Mean Rec.601 luma across a placement's palette colours.

    Returns ``None`` when the placement has no palette colours so the
    caller can skip it without penalising the song.
    """
    colors = placement.palette_colors
    if not colors:
        return None
    total = 0.0
    for color in colors:
        total += _hex_to_luma(color)
    return total / len(colors)


def _collect_weighted_luma(
    summary: SequenceSummary,
) -> list[tuple[float, float]]:
    """Return ``(luma, weight)`` pairs for placements with a palette.

    Weight is ``end_ms - start_ms``; placements with non-positive
    duration or empty palette are skipped.
    """
    pairs: list[tuple[float, float]] = []
    for placement in summary.placements:
        weight = placement.end_ms - placement.start_ms
        if weight <= 0:
            continue
        luma = _placement_mean_luma(placement)
        if luma is None:
            continue
        pairs.append((luma, float(weight)))
    return pairs


def palette_luminance_mean(summary: SequenceSummary) -> MetricValue:
    """Duration-weighted mean of per-placement palette luma (Rec.601).

    Palette-derived proxy; not a measurement of rendered light. Each
    placement contributes the mean Rec.601 luma (0-255) of its
    ``palette_colors``, weighted by ``end_ms - start_ms``. Placements
    without a palette are skipped (not penalised). Direction-of-good
    is not validated against rendered output, so the metric registers
    with ``higher_is_better=None``.
    """
    pairs = _collect_weighted_luma(summary)
    if not pairs:
        return MetricValue(
            name="palette_luminance_mean",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_placements",
        )

    total_weight = sum(w for _, w in pairs)
    if total_weight <= 0:
        return MetricValue(
            name="palette_luminance_mean",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_placements",
        )

    weighted_sum = sum(luma * w for luma, w in pairs)
    mean = weighted_sum / total_weight

    return MetricValue(
        name="palette_luminance_mean",
        kind=MetricKind.SCALAR.value,
        value=mean,
        payload=None,
        reliability="ok",
    )


def palette_luminance_cv(summary: SequenceSummary) -> MetricValue:
    """Duration-weighted coefficient of variation of palette luma.

    Palette-derived proxy; not a measurement of rendered light. Uses
    the same per-placement luma and the same duration weighting as
    ``palette_luminance_mean`` so both metrics describe the same
    population. Returns ``weighted_std / weighted_mean`` where the
    weighted variance is the population form
    ``sum(w_i * (x_i - mu)^2) / sum(w_i)``. Returns 0.0 when there is
    a single placement, when all placement luminances are identical,
    or when the weighted mean is 0. Direction-of-good is not validated
    against rendered output, so the metric registers with
    ``higher_is_better=None``.
    """
    pairs = _collect_weighted_luma(summary)
    if not pairs:
        return MetricValue(
            name="palette_luminance_cv",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_placements",
        )

    total_weight = sum(w for _, w in pairs)
    if total_weight <= 0:
        return MetricValue(
            name="palette_luminance_cv",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_placements",
        )

    weighted_mean = sum(luma * w for luma, w in pairs) / total_weight
    if weighted_mean == 0.0:
        return MetricValue(
            name="palette_luminance_cv",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="ok",
        )

    weighted_var = (
        sum(w * (luma - weighted_mean) ** 2 for luma, w in pairs) / total_weight
    )
    if weighted_var <= 0.0:
        return MetricValue(
            name="palette_luminance_cv",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="ok",
        )

    weighted_std = weighted_var ** 0.5
    cv = weighted_std / weighted_mean

    return MetricValue(
        name="palette_luminance_cv",
        kind=MetricKind.SCALAR.value,
        value=cv,
        payload=None,
        reliability="ok",
    )


register(MetricDefinition(
    name="palette_luminance_mean",
    kind=MetricKind.SCALAR,
    gated=True,
    tolerance=None,
    compute=palette_luminance_mean,
    pro_comparable=False,
    higher_is_better=None,
))

register(MetricDefinition(
    name="palette_luminance_cv",
    kind=MetricKind.SCALAR,
    gated=True,
    tolerance=None,
    compute=palette_luminance_cv,
    pro_comparable=False,
    higher_is_better=None,
))
