"""Tests for value curve generation."""
from __future__ import annotations

import pytest

from src.effects.models import AnalysisMapping, EffectDefinition, EffectParameter
from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.generator.models import EffectPlacement
from src.generator.value_curves import (
    apply_chord_accents,
    classify_param_category,
    generate_value_curves,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_parameter(
    name: str = "brightness",
    supports_value_curve: bool = True,
    min_val: int = 0,
    max_val: int = 100,
) -> EffectParameter:
    return EffectParameter(
        name=name,
        storage_name=f"E_{name}",
        widget_type="slider",
        value_type="int",
        default=50,
        description=f"{name} parameter",
        min=min_val,
        max=max_val,
        supports_value_curve=supports_value_curve,
    )


def _make_mapping(
    parameter: str = "brightness",
    mapping_type: str = "direct",
    curve_shape: str = "linear",
    input_min: float = 0.0,
    input_max: float = 100.0,
    output_min: float | None = None,
    output_max: float | None = None,
    threshold: float | None = None,
) -> AnalysisMapping:
    return AnalysisMapping(
        parameter=parameter,
        analysis_level="L5",
        analysis_field="full_mix",
        mapping_type=mapping_type,
        description="test mapping",
        input_min=input_min,
        input_max=input_max,
        output_min=output_min,
        output_max=output_max,
        curve_shape=curve_shape,
        threshold=threshold,
    )


def _make_effect_def(
    parameters: list[EffectParameter] | None = None,
    mappings: list[AnalysisMapping] | None = None,
) -> EffectDefinition:
    return EffectDefinition(
        name="Color Wash",
        xlights_id="E_VALUECURVE_ColorWash",
        category="color_wash",
        description="A color wash effect",
        intent="Fill with color",
        parameters=parameters or [],
        prop_suitability={"matrix": "ideal"},
        analysis_mappings=mappings or [],
    )


def _make_placement(start_ms: int = 0, end_ms: int = 5000) -> EffectPlacement:
    return EffectPlacement(
        effect_name="Color Wash",
        xlights_id="E_VALUECURVE_ColorWash",
        model_or_group="AllModels",
        start_ms=start_ms,
        end_ms=end_ms,
    )


def _make_hierarchy(num_frames: int = 200, fps: int = 40) -> HierarchyResult:
    """Build a minimal HierarchyResult with a full_mix energy curve.

    Default: 200 frames at 40 fps = 5 seconds of audio.
    Values ramp linearly from 0 to 100.
    """
    values = [int(i * 100 / max(num_frames - 1, 1)) for i in range(num_frames)]
    curve = ValueCurve(
        name="full_mix",
        stem_source="full_mix",
        fps=fps,
        values=values,
    )
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=int(num_frames * 1000 / fps),
        estimated_bpm=120.0,
        energy_curves={"full_mix": curve},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateValueCurves:
    """Tests for generate_value_curves()."""

    def test_no_mappings_returns_empty(self) -> None:
        """Effect with no analysis_mappings returns an empty dict."""
        effect_def = _make_effect_def(parameters=[], mappings=[])
        placement = _make_placement()
        hierarchy = _make_hierarchy()

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert result == {}

    def test_parameter_without_value_curve_support_skipped(self) -> None:
        """Mapping exists but parameter has supports_value_curve=False."""
        param = _make_parameter(name="brightness", supports_value_curve=False)
        mapping = _make_mapping(parameter="brightness")
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement()
        hierarchy = _make_hierarchy()

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" not in result

    def test_linear_curve_shape(self) -> None:
        """Linear mapping from input range to output range produces correct points."""
        param = _make_parameter(name="brightness", supports_value_curve=True)
        mapping = _make_mapping(
            parameter="brightness",
            curve_shape="linear",
            input_min=0.0,
            input_max=100.0,
            output_min=0.0,
            output_max=100.0,
        )
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" in result
        points = result["brightness"]
        assert len(points) > 0
        # Linear mapping: output should track input proportionally.
        # First point should map near 0, last point should map near 100.
        _x_first, y_first = points[0]
        _x_last, y_last = points[-1]
        assert y_first == pytest.approx(0.0, abs=2.0)
        assert y_last == pytest.approx(100.0, abs=2.0)

    def test_logarithmic_curve_shape(self) -> None:
        """Logarithmic mapping produces logarithmically scaled output."""
        param = _make_parameter(name="brightness", supports_value_curve=True)
        mapping = _make_mapping(
            parameter="brightness",
            curve_shape="logarithmic",
            input_min=0.0,
            input_max=100.0,
            output_min=0.0,
            output_max=100.0,
        )
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" in result
        points = result["brightness"]
        # Log curve: midpoint input (50) should map above linear midpoint (50).
        mid_idx = len(points) // 2
        _x_mid, y_mid = points[mid_idx]
        assert y_mid > 50.0, (
            f"Logarithmic midpoint {y_mid} should be above linear midpoint 50"
        )

    def test_exponential_curve_shape(self) -> None:
        """Exponential mapping produces exponentially scaled output."""
        param = _make_parameter(name="brightness", supports_value_curve=True)
        mapping = _make_mapping(
            parameter="brightness",
            curve_shape="exponential",
            input_min=0.0,
            input_max=100.0,
            output_min=0.0,
            output_max=100.0,
        )
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" in result
        points = result["brightness"]
        # Exp curve: midpoint input (50) should map below linear midpoint (50).
        mid_idx = len(points) // 2
        _x_mid, y_mid = points[mid_idx]
        assert y_mid < 50.0, (
            f"Exponential midpoint {y_mid} should be below linear midpoint 50"
        )

    def test_step_curve_shape(self) -> None:
        """Step mapping with threshold produces binary output."""
        param = _make_parameter(name="brightness", supports_value_curve=True)
        mapping = _make_mapping(
            parameter="brightness",
            curve_shape="step",
            mapping_type="threshold_trigger",
            input_min=0.0,
            input_max=100.0,
            output_min=0.0,
            output_max=100.0,
            threshold=50.0,
        )
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" in result
        points = result["brightness"]
        # Step/threshold: every y value should be either output_min or output_max.
        y_values = {y for _x, y in points}
        assert y_values <= {0.0, 100.0}, (
            f"Step curve should produce only 0.0 or 100.0, got {y_values}"
        )

    def test_range_mapping(self) -> None:
        """Input range [0, 100] maps to output range [10, 90] correctly."""
        param = _make_parameter(name="brightness", supports_value_curve=True, min_val=0, max_val=100)
        mapping = _make_mapping(
            parameter="brightness",
            curve_shape="linear",
            input_min=0.0,
            input_max=100.0,
            output_min=10.0,
            output_max=90.0,
        )
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" in result
        points = result["brightness"]
        y_values = [y for _x, y in points]
        assert min(y_values) >= 10.0 - 1.0, (
            f"Output minimum {min(y_values)} should be >= ~10.0"
        )
        assert max(y_values) <= 90.0 + 1.0, (
            f"Output maximum {max(y_values)} should be <= ~90.0"
        )

    def test_downsampling_to_100_points(self) -> None:
        """Input with 500 frames downsamples to at most 100 control points."""
        param = _make_parameter(name="brightness", supports_value_curve=True)
        mapping = _make_mapping(parameter="brightness")
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=12500)
        hierarchy = _make_hierarchy(num_frames=500, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" in result
        points = result["brightness"]
        assert len(points) <= 100, (
            f"Expected at most 100 control points, got {len(points)}"
        )

    def test_normalized_x_positions(self) -> None:
        """X values range from 0.0 to 1.0 within the effect span."""
        param = _make_parameter(name="brightness", supports_value_curve=True)
        mapping = _make_mapping(parameter="brightness")
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=1000, end_ms=4000)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)

        assert "brightness" in result
        points = result["brightness"]
        x_values = [x for x, _y in points]
        assert min(x_values) == pytest.approx(0.0, abs=0.01)
        assert max(x_values) == pytest.approx(1.0, abs=0.01)
        # X values should be monotonically non-decreasing.
        for i in range(1, len(x_values)):
            assert x_values[i] >= x_values[i - 1], (
                f"X values not monotonic at index {i}: {x_values[i]} < {x_values[i-1]}"
            )


# ---------------------------------------------------------------------------
# T005: classify_param_category tests
# ---------------------------------------------------------------------------

class TestClassifyParamCategory:
    """Tests for classify_param_category()."""

    def test_brightness_keywords(self) -> None:
        assert classify_param_category("On_Transparency") == "brightness"
        assert classify_param_category("Eff_Brightness") == "brightness"
        assert classify_param_category("Color_Intensity") == "brightness"
        assert classify_param_category("Layer_Opacity") == "brightness"

    def test_speed_keywords(self) -> None:
        assert classify_param_category("Bars_Speed") == "speed"
        assert classify_param_category("Meteors_Velocity") == "speed"
        assert classify_param_category("Spirals_Rate") == "speed"
        assert classify_param_category("Pinwheel_Cycles") == "speed"
        assert classify_param_category("Spirals_Rotation") == "speed"

    def test_color_keywords(self) -> None:
        assert classify_param_category("Fire_HueShift") == "color"
        assert classify_param_category("ColorWash_Saturation") == "color"
        assert classify_param_category("Twinkle_Color") == "color"
        assert classify_param_category("Effect_Palette") == "color"

    def test_other_fallback(self) -> None:
        assert classify_param_category("Fire_Height") == "other"
        assert classify_param_category("Meteors_Count") == "other"
        assert classify_param_category("Wave_Length") == "other"
        assert classify_param_category("Bars_Gap") == "other"

    def test_case_insensitive(self) -> None:
        assert classify_param_category("TRANSPARENCY") == "brightness"
        assert classify_param_category("SPEED") == "speed"
        assert classify_param_category("HUE") == "color"


# ---------------------------------------------------------------------------
# T005: minimum duration guard tests
# ---------------------------------------------------------------------------

class TestMinimumDurationGuard:
    """Tests for the 1000ms minimum duration guard in generate_value_curves()."""

    def _make_effect_with_brightness(self) -> tuple:
        param = _make_parameter(name="On_Transparency", supports_value_curve=True)
        mapping = _make_mapping(parameter="On_Transparency")
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        hierarchy = _make_hierarchy(num_frames=200, fps=40)
        return effect_def, hierarchy

    def test_placement_under_1s_returns_empty(self) -> None:
        # Use 975ms which frame-aligns to 975 (38 * 25ms), still < 1000
        effect_def, hierarchy = self._make_effect_with_brightness()
        placement = _make_placement(start_ms=0, end_ms=975)
        result = generate_value_curves(placement, effect_def, hierarchy)
        assert result == {}

    def test_placement_exactly_1s_proceeds(self) -> None:
        # Boundary: exactly 1000ms (not < 1000) should proceed normally
        effect_def, hierarchy = self._make_effect_with_brightness()
        placement = _make_placement(start_ms=0, end_ms=1000)
        result = generate_value_curves(placement, effect_def, hierarchy)
        assert result != {}

    def test_placement_above_1s_proceeds(self) -> None:
        effect_def, hierarchy = self._make_effect_with_brightness()
        placement = _make_placement(start_ms=0, end_ms=2000)
        result = generate_value_curves(placement, effect_def, hierarchy)
        assert "On_Transparency" in result
        assert len(result["On_Transparency"]) > 0


# ---------------------------------------------------------------------------
# T006: brightness curve generation tests (US1)
# ---------------------------------------------------------------------------

class TestBrightnessCurveGeneration:
    """Test that generate_value_curves produces brightness curves for transparency params."""

    def test_generates_transparency_curve(self) -> None:
        param = _make_parameter(name="On_Transparency", supports_value_curve=True)
        mapping = _make_mapping(
            parameter="On_Transparency",
            curve_shape="linear",
            input_min=0.0,
            input_max=100.0,
            output_min=0.0,
            output_max=100.0,
        )
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="all")

        assert "On_Transparency" in result
        points = result["On_Transparency"]
        assert len(points) > 0
        # All y values should be in [0, 100]
        for _x, y in points:
            assert 0.0 <= y <= 100.0

    def test_brightness_with_energy_data_varies(self) -> None:
        """Brightness curve should reflect energy variation (not flat)."""
        param = _make_parameter(name="On_Transparency", supports_value_curve=True)
        mapping = _make_mapping(parameter="On_Transparency", input_min=0.0, input_max=100.0,
                                output_min=0.0, output_max=100.0)
        effect_def = _make_effect_def(parameters=[param], mappings=[mapping])
        placement = _make_placement(start_ms=0, end_ms=5000)
        # Linearly ramping energy: first = 0, last = 100
        hierarchy = _make_hierarchy(num_frames=200, fps=40)

        result = generate_value_curves(placement, effect_def, hierarchy)
        points = result["On_Transparency"]
        y_values = [y for _x, y in points]
        assert max(y_values) - min(y_values) > 10.0, "Curve should vary with energy data"


# ---------------------------------------------------------------------------
# T007: curves_mode filtering tests (US1)
# ---------------------------------------------------------------------------

class TestCurvesModeFiltering:
    """Test that curves_mode controls which parameter categories are generated."""

    def _make_multi_param_effect(self):
        """Effect with brightness, speed, and color params."""
        params = [
            _make_parameter(name="On_Transparency", supports_value_curve=True),
            _make_parameter(name="Bars_Speed", supports_value_curve=True),
            _make_parameter(name="Fire_HueShift", supports_value_curve=True),
            _make_parameter(name="Fire_Height", supports_value_curve=True),
        ]
        mappings = [
            _make_mapping(parameter="On_Transparency"),
            _make_mapping(parameter="Bars_Speed"),
            _make_mapping(parameter="Fire_HueShift"),
            _make_mapping(parameter="Fire_Height"),
        ]
        return _make_effect_def(parameters=params, mappings=mappings)

    def test_curves_mode_none_returns_empty(self) -> None:
        effect_def = self._make_multi_param_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy()

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="none")
        assert result == {}

    def test_curves_mode_all_returns_all_categories(self) -> None:
        effect_def = self._make_multi_param_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy()

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="all")
        assert "On_Transparency" in result
        assert "Bars_Speed" in result
        assert "Fire_HueShift" in result
        assert "Fire_Height" in result  # "other" category included in "all"

    def test_curves_mode_brightness_returns_only_brightness(self) -> None:
        effect_def = self._make_multi_param_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy()

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="brightness")
        assert "On_Transparency" in result
        assert "Bars_Speed" not in result
        assert "Fire_HueShift" not in result
        assert "Fire_Height" not in result  # "other" excluded in specific mode

    def test_curves_mode_speed_returns_only_speed(self) -> None:
        effect_def = self._make_multi_param_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy()

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="speed")
        assert "On_Transparency" not in result
        assert "Bars_Speed" in result
        assert "Fire_HueShift" not in result

    def test_curves_mode_color_returns_only_color(self) -> None:
        effect_def = self._make_multi_param_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)
        hierarchy = _make_hierarchy()

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="color")
        assert "On_Transparency" not in result
        assert "Bars_Speed" not in result
        assert "Fire_HueShift" in result


# ---------------------------------------------------------------------------
# T013: speed curve generation tests (US2)
# ---------------------------------------------------------------------------

class TestSpeedCurveGeneration:
    """Test that generate_value_curves produces speed curves for speed-category params."""

    def _make_speed_effect(self) -> tuple:
        """Effect with speed params (Bars_Speed, Meteors_Speed) and brightness."""
        params = [
            _make_parameter(name="Meteors_Speed", supports_value_curve=True),
            _make_parameter(name="Bars_Speed", supports_value_curve=True),
            _make_parameter(name="On_Transparency", supports_value_curve=True),
        ]
        mappings = [
            _make_mapping(parameter="Meteors_Speed"),
            _make_mapping(parameter="Bars_Speed"),
            _make_mapping(parameter="On_Transparency"),
        ]
        effect_def = _make_effect_def(parameters=params, mappings=mappings)
        hierarchy = _make_hierarchy(num_frames=200, fps=40)
        return effect_def, hierarchy

    def test_speed_curves_generated_in_all_mode(self) -> None:
        effect_def, hierarchy = self._make_speed_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="all")
        assert "Meteors_Speed" in result
        assert "Bars_Speed" in result

    def test_speed_curves_generated_in_speed_mode(self) -> None:
        effect_def, hierarchy = self._make_speed_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="speed")
        assert "Meteors_Speed" in result
        assert "Bars_Speed" in result
        assert "On_Transparency" not in result

    def test_speed_curves_omitted_in_brightness_mode(self) -> None:
        effect_def, hierarchy = self._make_speed_effect()
        placement = _make_placement(start_ms=0, end_ms=5000)

        result = generate_value_curves(placement, effect_def, hierarchy, curves_mode="brightness")
        assert "Meteors_Speed" not in result
        assert "Bars_Speed" not in result
        assert "On_Transparency" in result


# ---------------------------------------------------------------------------
# T016 + T017: apply_chord_accents tests (US3)
# ---------------------------------------------------------------------------

def _make_chord_track(
    marks_ms: list[int],
    quality: float = 0.8,
) -> TimingTrack:
    """Build a TimingTrack with chord events at given timestamps."""
    return TimingTrack(
        name="chords",
        algorithm_name="chordino",
        element_type="chord",
        marks=[TimingMark(time_ms=t, confidence=1.0) for t in marks_ms],
        quality_score=quality,
    )


def _make_flat_curve(n: int = 20, y_val: float = 50.0) -> list[tuple[float, float]]:
    """Flat curve at y_val with n control points."""
    return [(round(i / max(n - 1, 1), 4), y_val) for i in range(n)]


def _make_hierarchy_with_chords(
    duration_ms: int = 10000,
    chord_marks_ms: list[int] | None = None,
    chord_quality: float = 0.8,
) -> HierarchyResult:
    fps = 40
    num_frames = duration_ms * fps // 1000
    values = [int(i * 100 / max(num_frames - 1, 1)) for i in range(num_frames)]
    energy_curves = {
        "full_mix": ValueCurve(
            name="full_mix", stem_source="full_mix", fps=fps, values=values,
        )
    }
    chords = None
    if chord_marks_ms is not None:
        chords = _make_chord_track(chord_marks_ms, quality=chord_quality)

    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        energy_curves=energy_curves,
        chords=chords,
    )


class TestApplyChordAccents:
    """Tests for apply_chord_accents() (T016)."""

    def test_overlays_accents_at_chord_positions(self) -> None:
        """Chord events at good density/quality should increase y at those positions."""
        base_curve = _make_flat_curve(n=50, y_val=50.0)
        # 30 events/min over 10s = 5 events
        chord_marks = [1000, 3000, 5000, 7000, 9000]
        hierarchy = _make_hierarchy_with_chords(
            duration_ms=10000,
            chord_marks_ms=chord_marks,
            chord_quality=0.8,
        )

        result = apply_chord_accents(base_curve, hierarchy, 0, 10000, 0.0, 100.0)

        # Should have the same number or more points than base
        assert len(result) >= 1

        # Max y in result should be above the base flat value of 50
        max_y = max(y for _, y in result)
        assert max_y > 50.0, (
            f"Expected accent to push max y above 50, got {max_y}"
        )

    def test_below_density_threshold_returns_base(self) -> None:
        """Chord density < 20/min should return base curve unchanged."""
        base_curve = _make_flat_curve(n=20, y_val=60.0)
        # 10 events over 60s = ~10/min (below 20/min threshold)
        chord_marks = [i * 6000 for i in range(10)]
        hierarchy = _make_hierarchy_with_chords(
            duration_ms=60000,
            chord_marks_ms=chord_marks,
            chord_quality=0.8,
        )

        result = apply_chord_accents(base_curve, hierarchy, 0, 60000, 0.0, 100.0)

        # Should be unchanged (same as base)
        assert result == base_curve

    def test_below_quality_threshold_returns_base(self) -> None:
        """Chord quality < 0.4 should return base curve unchanged."""
        base_curve = _make_flat_curve(n=20, y_val=40.0)
        # High density but low quality
        chord_marks = [i * 2000 for i in range(10)]  # 30/min density
        hierarchy = _make_hierarchy_with_chords(
            duration_ms=20000,
            chord_marks_ms=chord_marks,
            chord_quality=0.3,  # below 0.4 threshold
        )

        result = apply_chord_accents(base_curve, hierarchy, 0, 20000, 0.0, 100.0)

        assert result == base_curve


class TestApplyChordAccentsEdgeCases:
    """Tests for chord accent edge cases (T017)."""

    def test_missing_chord_data_returns_base(self) -> None:
        """No chord track in hierarchy returns base curve unchanged."""
        base_curve = _make_flat_curve(n=20, y_val=50.0)
        hierarchy = _make_hierarchy_with_chords(
            duration_ms=10000,
            chord_marks_ms=None,  # no chords
        )

        result = apply_chord_accents(base_curve, hierarchy, 0, 10000, 0.0, 100.0)

        assert result == base_curve

    def test_accent_stays_within_bounds(self) -> None:
        """Y values should never exceed output_max even at accent peaks."""
        # Start near max so accent can't push past it
        base_curve = _make_flat_curve(n=30, y_val=95.0)
        chord_marks = [i * 1500 for i in range(20)]  # ~40/min density over 30s
        hierarchy = _make_hierarchy_with_chords(
            duration_ms=30000,
            chord_marks_ms=chord_marks,
            chord_quality=0.9,
        )

        result = apply_chord_accents(base_curve, hierarchy, 0, 30000, 0.0, 100.0)

        for x, y in result:
            assert y <= 100.0, f"Accent pushed y={y} above output_max=100.0 at x={x}"
            assert y >= 0.0, f"Accent produced negative y={y} at x={x}"

    def test_empty_base_curve_returns_empty(self) -> None:
        """Empty base curve returns empty."""
        chord_marks = [1000, 2000, 3000]
        hierarchy = _make_hierarchy_with_chords(
            duration_ms=10000,
            chord_marks_ms=chord_marks,
            chord_quality=0.9,
        )

        result = apply_chord_accents([], hierarchy, 0, 10000, 0.0, 100.0)

        assert result == []
