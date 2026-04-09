"""Integration tests for value curve generation in build_plan().

T008: Verify at least one EffectPlacement has non-empty value_curves with valid (x, y) points.
T012: Verify xSQ XML encodes curves as Active=TRUE|Id=... inline format.
T022: Verify curves_mode="none" produces all-empty value_curves; "brightness" produces only brightness.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.library import load_effect_library
from src.generator.models import GenerationConfig, SequencePlan
from src.generator.plan import build_plan
from src.generator.value_curves import classify_param_category
from src.generator.xsq_writer import write_xsq
from src.grouper.grouper import PowerGroup
from src.grouper.layout import Prop
from src.themes.library import load_theme_library


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_hierarchy(duration_ms: int = 20000) -> HierarchyResult:
    """Build a mock HierarchyResult with energy curves for value curve generation."""
    fps = 40
    num_frames = duration_ms * fps // 1000
    # Ramping energy so curves are non-flat
    values = [int(i * 100 / max(num_frames - 1, 1)) for i in range(num_frames)]
    energy_curves = {
        "full_mix": ValueCurve(
            name="full_mix", stem_source="full_mix", fps=fps, values=values,
        )
    }

    beats = TimingTrack(
        name="beats", algorithm_name="librosa_beats", element_type="beat",
        marks=[TimingMark(time_ms=i * 500, confidence=1.0) for i in range(duration_ms // 500)],
        quality_score=0.85,
    )
    bars = TimingTrack(
        name="bars", algorithm_name="librosa_beats", element_type="bar",
        marks=[TimingMark(time_ms=i * 2000, confidence=1.0) for i in range(duration_ms // 2000)],
        quality_score=0.8,
    )
    section_dur = duration_ms // 4
    sections = [
        TimingMark(time_ms=i * section_dur, confidence=1.0,
                   label=label, duration_ms=section_dur)
        for i, label in enumerate(["intro", "verse", "chorus", "outro"])
    ]

    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        sections=sections,
        beats=beats,
        bars=bars,
        energy_curves=energy_curves,
        energy_impacts=[TimingMark(time_ms=duration_ms // 2, confidence=1.0)],
    )


def _make_props() -> list[Prop]:
    return [
        Prop(name="ArchLeft", display_as="Arch",
             world_x=50, world_y=40, world_z=0,
             scale_x=2, scale_y=1, parm1=1, parm2=50,
             sub_models=[], pixel_count=50,
             norm_x=0.1, norm_y=0.1, aspect_ratio=2.0),
        Prop(name="MatrixCenter", display_as="Matrix",
             world_x=300, world_y=350, world_z=0,
             scale_x=3, scale_y=2, parm1=20, parm2=30,
             sub_models=[], pixel_count=600,
             norm_x=0.5, norm_y=0.9, aspect_ratio=1.5),
    ]


def _make_groups() -> list[PowerGroup]:
    return [
        PowerGroup(name="01_BASE_All", tier=1, members=["ArchLeft", "MatrixCenter"]),
        PowerGroup(name="02_GEO_Left", tier=2, members=["ArchLeft"]),
    ]


def _build(tmp_path: Path, curves_mode: str = "all") -> SequencePlan:
    props = _make_props()
    groups = _make_groups()
    hierarchy = _make_hierarchy()
    effect_lib = load_effect_library()
    from src.variants.library import load_variant_library
    variant_lib = load_variant_library(effect_library=effect_lib)
    theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
    config = GenerationConfig(
        audio_path=tmp_path / "test.mp3",
        layout_path=tmp_path / "layout.xml",
        genre="pop",
        occasion="general",
        curves_mode=curves_mode,
    )
    return build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)


def _all_placements(plan: SequencePlan):
    """Yield every EffectPlacement in the plan."""
    for section in plan.sections:
        for placements in section.group_effects.values():
            yield from placements


# ---------------------------------------------------------------------------
# T008: value curves activated in build_plan
# ---------------------------------------------------------------------------

class TestValueCurvesActivation:
    """Verify build_plan generates value_curves for at least one placement (T008)."""

    def test_at_least_one_placement_has_curves(self, tmp_path: Path) -> None:
        plan = _build(tmp_path, curves_mode="all")
        placements = list(_all_placements(plan))
        assert placements, "Expected at least one EffectPlacement in plan"

        non_empty = [p for p in placements if p.value_curves]
        assert non_empty, (
            "Expected at least one EffectPlacement with non-empty value_curves. "
            f"Total placements: {len(placements)}, all had empty curves."
        )

    def test_curve_points_in_valid_range(self, tmp_path: Path) -> None:
        """All (x, y) curve points must be in [0.0-1.0] x [0.0-100.0]."""
        plan = _build(tmp_path, curves_mode="all")

        for placement in _all_placements(plan):
            for param_name, points in placement.value_curves.items():
                for x, y in points:
                    assert 0.0 <= x <= 1.0, (
                        f"{placement.effect_name}.{param_name}: x={x} out of [0.0, 1.0]"
                    )
                    assert 0.0 <= y <= 100.0, (
                        f"{placement.effect_name}.{param_name}: y={y} out of [0.0, 100.0]"
                    )

    def test_curve_x_values_monotonic(self, tmp_path: Path) -> None:
        """X values within each curve must be monotonically non-decreasing."""
        plan = _build(tmp_path, curves_mode="all")

        for placement in _all_placements(plan):
            for param_name, points in placement.value_curves.items():
                x_vals = [x for x, _y in points]
                for i in range(1, len(x_vals)):
                    assert x_vals[i] >= x_vals[i - 1], (
                        f"{placement.effect_name}.{param_name}: x not monotonic at index {i}"
                    )


# ---------------------------------------------------------------------------
# T022: curves_mode filtering in build_plan (US4)
# ---------------------------------------------------------------------------

class TestCurvesModeInBuildPlan:
    """Verify curves_mode config field controls what curves are generated (T022)."""

    def test_curves_mode_none_produces_all_empty(self, tmp_path: Path) -> None:
        plan = _build(tmp_path, curves_mode="none")
        for placement in _all_placements(plan):
            assert placement.value_curves == {}, (
                f"Expected empty value_curves for {placement.effect_name} "
                f"with curves_mode='none', got {list(placement.value_curves)}"
            )

    def test_curves_mode_brightness_only_brightness_params(self, tmp_path: Path) -> None:
        plan = _build(tmp_path, curves_mode="brightness")
        for placement in _all_placements(plan):
            for param_name in placement.value_curves:
                category = classify_param_category(param_name)
                assert category == "brightness", (
                    f"curves_mode='brightness' but got param '{param_name}' "
                    f"with category '{category}' in {placement.effect_name}"
                )

    def test_curves_mode_speed_only_speed_params(self, tmp_path: Path) -> None:
        plan = _build(tmp_path, curves_mode="speed")
        for placement in _all_placements(plan):
            for param_name in placement.value_curves:
                category = classify_param_category(param_name)
                assert category == "speed", (
                    f"curves_mode='speed' but got param '{param_name}' "
                    f"with category '{category}' in {placement.effect_name}"
                )

    def test_curves_mode_all_default(self, tmp_path: Path) -> None:
        """Default curves_mode='all' should produce the most curves."""
        plan_all = _build(tmp_path, curves_mode="all")
        plan_brightness = _build(tmp_path, curves_mode="brightness")

        total_all = sum(len(p.value_curves) for p in _all_placements(plan_all))
        total_brightness = sum(len(p.value_curves) for p in _all_placements(plan_brightness))

        # "all" mode should produce >= curves than a specific category mode
        assert total_all >= total_brightness, (
            f"'all' mode ({total_all} curves) should have >= 'brightness' mode ({total_brightness})"
        )

    def test_brightness_mode_filters_with_known_l5_effect(self) -> None:
        """'On' effect has an L5 brightness mapping — verify brightness mode generates it."""
        from src.generator.value_curves import generate_value_curves
        from src.generator.models import EffectPlacement

        effect_lib = load_effect_library()
        effect_def = effect_lib.effects["On"]
        hierarchy = _make_hierarchy()
        placement = EffectPlacement(
            effect_name="On", xlights_id="x1", model_or_group="Test",
            start_ms=0, end_ms=5000,
        )

        curves_all = generate_value_curves(placement, effect_def, hierarchy, "all")
        curves_brightness = generate_value_curves(placement, effect_def, hierarchy, "brightness")
        curves_speed = generate_value_curves(placement, effect_def, hierarchy, "speed")

        assert curves_brightness, "Expected On_Transparency curve in brightness mode"
        assert curves_all, "Expected On_Transparency curve in all mode"
        assert not curves_speed, "Expected no curves for 'On' effect in speed mode"
        assert set(curves_brightness.keys()) <= set(curves_all.keys())



# ---------------------------------------------------------------------------
# T012: xSQ writer encodes curves inline
# ---------------------------------------------------------------------------

class TestXsqCurveEncoding:
    """Verify that build_plan curves are encoded in xSQ XML (T012)."""

    def test_xsq_contains_active_true_encoding(self, tmp_path: Path) -> None:
        """At least one effect in the xSQ should have Active=TRUE|Id= curve encoding."""
        props = _make_props()
        groups = _make_groups()
        hierarchy = _make_hierarchy()
        from src.variants.library import load_variant_library
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
            curves_mode="all",
        )
        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        # Verify the plan has curves
        placements_with_curves = [
            p for p in _all_placements(plan) if p.value_curves
        ]
        assert placements_with_curves, "Expected at least one placement with curves"

        # Write xSQ and check the XML
        xsq_path = tmp_path / "test.xsq"
        write_xsq(plan, xsq_path)
        xsq_content = xsq_path.read_text()

        assert "Active=TRUE" in xsq_content, (
            "Expected 'Active=TRUE' in xSQ output to indicate value curve encoding"
        )
        assert "Id=ID_" in xsq_content, (
            "Expected 'Id=ID_' parameter identifier in xSQ value curve encoding"
        )
