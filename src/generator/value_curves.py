"""Value curve generation — modulates effect parameters from analysis data."""
from __future__ import annotations

import math

from src.analyzer.result import HierarchyResult, ValueCurve
from src.effects.models import AnalysisMapping, EffectDefinition, EffectParameter
from src.generator.energy import slice_curve
from src.generator.models import EffectPlacement


MAX_CONTROL_POINTS = 100

_BRIGHTNESS_KEYWORDS = ("transparency", "brightness", "intensity", "opacity")
_SPEED_KEYWORDS = ("speed", "velocity", "rate", "cycles", "rotation")
_COLOR_KEYWORDS = ("color", "hue", "saturation", "palette")


def classify_param_category(parameter_name: str) -> str:
    """Classify a parameter name into a curve category.

    Returns "brightness", "speed", "color", or "other".
    """
    lower = parameter_name.lower()
    if any(kw in lower for kw in _BRIGHTNESS_KEYWORDS):
        return "brightness"
    if any(kw in lower for kw in _SPEED_KEYWORDS):
        return "speed"
    if any(kw in lower for kw in _COLOR_KEYWORDS):
        return "color"
    return "other"


def generate_value_curves(
    placement: EffectPlacement,
    effect_def: EffectDefinition,
    hierarchy: HierarchyResult,
    curves_mode: str = "all",
) -> dict[str, list[tuple[float, float]]]:
    """Generate parameter modulation curves from analysis mappings.

    For each AnalysisMapping where the target parameter supports value curves:
    1. Extract analysis data for the effect's time range
    2. Apply curve_shape transform (linear, log, exp, step)
    3. Map input_min/max -> output_min/max
    4. Downsample to ≤100 control points
    5. Return as (x, y) tuples where x is normalized position [0.0-1.0]

    curves_mode filters which parameter categories are generated:
    - "all": all categories including "other"
    - "brightness"/"speed"/"color": only that category (plus "other" is excluded)
    - "none": always returns empty dict
    """
    if curves_mode == "none":
        return {}

    if placement.end_ms - placement.start_ms < 1000:
        return {}

    if not effect_def.analysis_mappings:
        return {}

    # Build parameter lookup
    param_map: dict[str, EffectParameter] = {
        p.name: p for p in effect_def.parameters
    }

    result: dict[str, list[tuple[float, float]]] = {}

    for mapping in effect_def.analysis_mappings:
        param = param_map.get(mapping.parameter)
        if param is None or not param.supports_value_curve:
            continue

        # Filter by curves_mode
        if curves_mode != "all":
            category = classify_param_category(mapping.parameter)
            if category != curves_mode:
                continue

        curve_data = _extract_analysis_data(
            mapping, hierarchy, placement.start_ms, placement.end_ms
        )
        if not curve_data:
            continue

        points = _map_to_output(curve_data, mapping)
        points = _downsample(points, MAX_CONTROL_POINTS)

        # Apply chord accents for color-category parameters when mode allows
        if curves_mode in ("all", "color"):
            category = classify_param_category(mapping.parameter)
            if category == "color":
                out_min = mapping.output_min if mapping.output_min is not None else mapping.input_min
                out_max = mapping.output_max if mapping.output_max is not None else mapping.input_max
                points = apply_chord_accents(
                    points, hierarchy,
                    placement.start_ms, placement.end_ms,
                    out_min, out_max,
                )

        result[mapping.parameter] = points

    return result


def _extract_analysis_data(
    mapping: AnalysisMapping,
    hierarchy: HierarchyResult,
    start_ms: int,
    end_ms: int,
) -> list[float]:
    """Extract raw analysis values for the effect's time range."""
    if mapping.analysis_level == "L5":
        curve = hierarchy.energy_curves.get(mapping.analysis_field)
        if curve is None:
            curve = hierarchy.energy_curves.get("full_mix")
        return [float(v) for v in slice_curve(curve, start_ms, end_ms)]

    return []


def _map_to_output(
    raw_values: list[float],
    mapping: AnalysisMapping,
) -> list[tuple[float, float]]:
    """Apply curve shape and range mapping to produce (x, y) control points."""
    n = len(raw_values)
    if n == 0:
        return []

    in_min = mapping.input_min
    in_max = mapping.input_max
    out_min = mapping.output_min if mapping.output_min is not None else in_min
    out_max = mapping.output_max if mapping.output_max is not None else in_max
    in_range = in_max - in_min if in_max != in_min else 1.0

    points: list[tuple[float, float]] = []
    for i, raw in enumerate(raw_values):
        x = i / max(n - 1, 1)

        # Normalize to 0-1
        normalized = max(0.0, min(1.0, (raw - in_min) / in_range))

        # Apply curve shape
        shaped = _apply_curve_shape(normalized, mapping.curve_shape, mapping.threshold)

        # Invert if mapping type is inverted
        if mapping.mapping_type == "inverted":
            shaped = 1.0 - shaped

        # Map to output range
        y = out_min + shaped * (out_max - out_min)
        points.append((round(x, 4), round(y, 2)))

    return points


def _apply_curve_shape(
    normalized: float, shape: str, threshold: float | None
) -> float:
    """Apply a curve shape transform to a normalized 0-1 value."""
    if shape == "linear":
        return normalized

    elif shape == "logarithmic":
        # Log curve: fast rise, slow finish
        return math.log1p(normalized * 9) / math.log(10)

    elif shape == "exponential":
        # Exponential curve: slow start, fast finish
        return (math.pow(10, normalized) - 1) / 9

    elif shape == "step":
        # Binary output based on threshold
        thresh = threshold if threshold is not None else 0.5
        return 1.0 if normalized >= thresh else 0.0

    return normalized


def _downsample(
    points: list[tuple[float, float]], max_points: int
) -> list[tuple[float, float]]:
    """Downsample control points to at most max_points."""
    if len(points) <= max_points:
        return points

    step = len(points) / max_points
    result = [points[int(i * step)] for i in range(max_points - 1)]
    result.append(points[-1])  # Always include last point
    return result


# ---------------------------------------------------------------------------
# Chord accent helpers (US3)
# ---------------------------------------------------------------------------

_CHORD_DENSITY_THRESHOLD = 20.0   # events/min
_CHORD_QUALITY_THRESHOLD = 0.4    # quality score
_CHORD_ACCENT_DECAY_MS = 500      # ms over which accent decays back to base
_CHORD_ACCENT_SHIFT = 0.15        # fraction of output range added at chord boundary


def _get_chord_density_and_quality(
    hierarchy: HierarchyResult,
    start_ms: int,
    end_ms: int,
) -> tuple[float, float]:
    """Return (events_per_min, quality_score) for the chord track in the time range.

    Returns (0.0, 0.0) if no chord data is available.
    """
    if hierarchy.chords is None:
        return 0.0, 0.0

    track = hierarchy.chords
    duration_ms = end_ms - start_ms
    if duration_ms <= 0:
        return 0.0, 0.0

    events_in_range = [m for m in track.marks if start_ms <= m.time_ms < end_ms]
    density = len(events_in_range) / (duration_ms / 60000.0)
    return density, track.quality_score


def apply_chord_accents(
    base_curve: list[tuple[float, float]],
    hierarchy: HierarchyResult,
    start_ms: int,
    end_ms: int,
    output_min: float,
    output_max: float,
) -> list[tuple[float, float]]:
    """Overlay chord-change accent pulses onto a base energy curve.

    If chord density > 20/min AND quality > 0.4:
    - At each chord event, inject a +15% accent that decays over 500ms
    - Merge with base curve and downsample to ≤100 points
    Otherwise returns base_curve unchanged.
    """
    density, quality = _get_chord_density_and_quality(hierarchy, start_ms, end_ms)

    if density <= _CHORD_DENSITY_THRESHOLD or quality <= _CHORD_QUALITY_THRESHOLD:
        return base_curve

    if not base_curve or hierarchy.chords is None:
        return base_curve

    duration_ms = end_ms - start_ms
    out_range = output_max - output_min

    # Build a dict of x_position → accent_boost for fast lookup
    # Accents decay linearly from +15% to 0 over CHORD_ACCENT_DECAY_MS
    accent_at: dict[float, float] = {}
    events_in_range = [m for m in hierarchy.chords.marks if start_ms <= m.time_ms < end_ms]

    for event in events_in_range:
        peak_x = (event.time_ms - start_ms) / duration_ms
        decay_x = min(1.0, peak_x + _CHORD_ACCENT_DECAY_MS / duration_ms)
        peak_boost = _CHORD_ACCENT_SHIFT * out_range

        # Sample decay curve at several points
        for step in range(10):
            frac = step / 10.0
            x = peak_x + frac * (decay_x - peak_x)
            if x > 1.0:
                break
            boost = peak_boost * (1.0 - frac)
            accent_at[round(x, 4)] = max(accent_at.get(round(x, 4), 0.0), boost)

    if not accent_at:
        return base_curve

    # Merge accent boosts into base curve
    merged: list[tuple[float, float]] = []
    for x, y in base_curve:
        # Find nearest accent (within 0.02 in x)
        boost = 0.0
        for ax, ab in accent_at.items():
            if abs(ax - x) < 0.02:
                boost = max(boost, ab)
        y_new = min(output_max, y + boost)
        merged.append((x, round(y_new, 2)))

    # Add accent peak points not already in base curve
    base_xs = {x for x, _ in merged}
    for ax, ab in sorted(accent_at.items()):
        if ax not in base_xs:
            # Interpolate base y at this x position
            base_y = _interpolate_y(base_curve, ax)
            y_new = min(output_max, base_y + ab)
            merged.append((ax, round(y_new, 2)))

    merged.sort(key=lambda p: p[0])
    return _downsample(merged, MAX_CONTROL_POINTS)


def _interpolate_y(curve: list[tuple[float, float]], x: float) -> float:
    """Linear interpolation of y at position x within a curve."""
    if not curve:
        return 0.0
    if x <= curve[0][0]:
        return curve[0][1]
    if x >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        x0, y0 = curve[i]
        x1, y1 = curve[i + 1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return y0 + t * (y1 - y0)
    return curve[-1][1]
