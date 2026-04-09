"""Integration tests for variant resolution in the sequence generator."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.effects.library import load_effect_library
from src.generator.effect_placer import place_effects
from src.generator.models import SectionAssignment, SectionEnergy
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer, Theme
from src.variants.library import VariantLibrary, load_variant_library
from src.variants.models import EffectVariant, VariantTags

EFFECTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library_with_meteors.json"
VARIANTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "variants" / "builtin_variants_minimal.json"


# ── Test helpers ──────────────────────────────────────────────────────────────


def _make_hierarchy(duration_ms: int = 10000) -> HierarchyResult:
    beats = TimingTrack(
        name="beats", algorithm_name="librosa_beats", element_type="beat",
        marks=[TimingMark(time_ms=i * 500, confidence=1.0) for i in range(duration_ms // 500)],
        quality_score=0.9,
    )
    bars = TimingTrack(
        name="bars", algorithm_name="librosa_beats", element_type="bar",
        marks=[TimingMark(time_ms=i * 2000, confidence=1.0) for i in range(duration_ms // 2000)],
        quality_score=0.9,
    )
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        sections=[TimingMark(time_ms=0, confidence=1.0, label="verse", duration_ms=duration_ms)],
        beats=beats,
        bars=bars,
        energy_curves={},
        energy_impacts=[],
    )


def _make_section_energy(start_ms: int = 0, end_ms: int = 10000) -> SectionEnergy:
    return SectionEnergy(
        label="verse",
        start_ms=start_ms,
        end_ms=end_ms,
        energy_score=60,
        mood_tier="mid",
        impact_count=0,
    )


def _make_groups() -> list[PowerGroup]:
    return [
        PowerGroup(name="01_BASE_All", tier=1, members=["Arch1"]),
        PowerGroup(name="08_HERO_Main", tier=8, members=["Matrix1"]),
    ]


def _make_theme(variant_name: str) -> Theme:
    """Create a minimal theme with a single layer using the given variant name."""
    return Theme(
        name="Test Theme",
        mood="ethereal",
        occasion="general",
        genre="any",
        intent="Testing",
        layers=[EffectLayer(variant=variant_name, blend_mode="Normal")],
        palette=["#FF0000", "#00FF00", "#0000FF"],
    )


def _make_assignment(theme: Theme, section: SectionEnergy) -> SectionAssignment:
    return SectionAssignment(
        section=section,
        theme=theme,
        variation_seed=0,
        group_effects={},
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestVariantResolutionInPlacer:
    """Verify that variant parameter_overrides flow through to EffectPlacement."""

    def test_variant_params_appear_in_placement(self):
        """Variant overrides appear in the generated placement parameters."""
        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_lib = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_lib)

        # "Bars Sweep Left" sets E_SLIDER_Bars_BarCount=3, E_CHOICE_Bars_Direction="Left"
        theme = _make_theme("Bars Sweep Left")
        section = _make_section_energy()
        assignment = _make_assignment(theme, section)
        groups = _make_groups()
        hierarchy = _make_hierarchy()

        result = place_effects(
            assignment, groups, effect_lib, hierarchy,
            variant_library=variant_lib,
        )

        all_placements = [p for placements in result.values() for p in placements]
        assert len(all_placements) > 0

        found = any(
            p.parameters.get("E_SLIDER_Bars_BarCount") == 3
            for p in all_placements
        )
        assert found, (
            f"Expected E_SLIDER_Bars_BarCount=3 from 'Bars Sweep Left' variant, "
            f"got params: {[p.parameters for p in all_placements]}"
        )

    def test_nonexistent_variant_skips_layer(self, caplog):
        """A layer whose variant name is not in the library is skipped with a warning."""
        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_lib = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_lib)

        theme = _make_theme("NoSuchVariant")
        section = _make_section_energy()
        assignment = _make_assignment(theme, section)
        groups = _make_groups()
        hierarchy = _make_hierarchy()

        with caplog.at_level(logging.WARNING):
            result = place_effects(
                assignment, groups, effect_lib, hierarchy,
                variant_library=variant_lib,
            )

        assert any("NoSuchVariant" in r.message for r in caplog.records), (
            "Expected a warning mentioning the missing variant name"
        )

    def test_fire_variant_params_appear_in_placement(self):
        """Fire Blaze High variant sets Height=85 and GrowWithMusic=True."""
        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_lib = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_lib)

        theme = _make_theme("Fire Blaze High")
        section = _make_section_energy()
        assignment = _make_assignment(theme, section)
        groups = _make_groups()
        hierarchy = _make_hierarchy()

        result = place_effects(
            assignment, groups, effect_lib, hierarchy,
            variant_library=variant_lib,
        )

        all_placements = [p for placements in result.values() for p in placements]
        assert len(all_placements) > 0

        found = any(
            p.parameters.get("E_SLIDER_Fire_Height") == 85
            for p in all_placements
        )
        assert found, (
            f"Expected E_SLIDER_Fire_Height=85 from 'Fire Blaze High' variant, "
            f"got params: {[p.parameters for p in all_placements]}"
        )

    def test_direction_cycle_applied_to_placement(self):
        """Variant with direction_cycle sets the direction param on placement."""
        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)

        # Create a variant with direction_cycle
        variant = EffectVariant(
            name="bars-cycle-test",
            base_effect="Bars",
            description="test",
            parameter_overrides={"E_SLIDER_Bars_BarCount": 2},
            tags=VariantTags(),
            direction_cycle={
                "param": "E_CHOICE_Bars_Direction",
                "values": ["left", "right"],
                "mode": "alternate",
            },
        )
        variant_lib = VariantLibrary(
            schema_version="1.0.0",
            variants={"bars-cycle-test": variant},
            builtin_names=set(),
        )

        theme = _make_theme("bars-cycle-test")
        section = _make_section_energy()
        assignment = _make_assignment(theme, section)
        groups = _make_groups()
        hierarchy = _make_hierarchy()

        result = place_effects(
            assignment, groups, effect_lib, hierarchy,
            variant_library=variant_lib,
        )

        all_placements = [p for placements in result.values() for p in placements]
        assert len(all_placements) >= 1

        directions = [
            p.parameters.get("E_CHOICE_Bars_Direction")
            for p in all_placements
            if "E_CHOICE_Bars_Direction" in p.parameters
        ]
        assert len(directions) >= 1, (
            f"Expected direction_cycle to inject E_CHOICE_Bars_Direction, "
            f"got params: {[p.parameters for p in all_placements]}"
        )
        assert directions[0] == "left", (
            f"Expected 'left' for instance_index=0, got: {directions[0]}"
        )

    def test_direction_cycle_alternates_with_multiple_instances(self):
        """direction_cycle alternates values across multiple placements (unit test of _make_placement)."""
        from src.generator.effect_placer import _make_placement

        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        bars_def = effect_lib.get("Bars")

        dc = {"param": "E_CHOICE_Bars_Direction", "values": ["up", "down"], "mode": "alternate"}
        params = {"E_SLIDER_Bars_BarCount": 3}

        p0 = _make_placement(bars_def, "G1", 0, 2000, params, ["#FF0000"], "Normal", "bar",
                             instance_index=0, direction_cycle=dc)
        p1 = _make_placement(bars_def, "G1", 2000, 4000, params, ["#FF0000"], "Normal", "bar",
                             instance_index=1, direction_cycle=dc)
        p2 = _make_placement(bars_def, "G1", 4000, 6000, params, ["#FF0000"], "Normal", "bar",
                             instance_index=2, direction_cycle=dc)

        assert p0.parameters["E_CHOICE_Bars_Direction"] == "up"
        assert p1.parameters["E_CHOICE_Bars_Direction"] == "down"
        assert p2.parameters["E_CHOICE_Bars_Direction"] == "up"

    def test_no_direction_cycle_uses_hardcoded_fallback(self):
        """Without direction_cycle, hardcoded _ALTERNATING_DIRECTIONS still works."""
        from src.generator.effect_placer import _make_placement

        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        bars_def = effect_lib.get("Bars")

        params = {"E_SLIDER_Bars_BarCount": 2, "E_CHOICE_Bars_Direction": "Left"}

        p0 = _make_placement(bars_def, "G1", 0, 2000, params, ["#FF0000"], "Normal", "bar",
                             instance_index=0)
        p1 = _make_placement(bars_def, "G1", 2000, 4000, params, ["#FF0000"], "Normal", "bar",
                             instance_index=1)

        # Hardcoded _ALTERNATING_DIRECTIONS for Bars_Direction is ["Left", "Right", "expand", "compress"]
        assert p0.parameters["E_CHOICE_Bars_Direction"] == "Left"
        assert p1.parameters["E_CHOICE_Bars_Direction"] == "Right"


# ── T008: variant-only theme integration ─────────────────────────────────────


class TestVariantOnlyThemeIntegration:
    """T008: Variant-only theme layers produce correct placements via variant_library."""

    def test_variant_only_theme_produces_correct_placements(self):
        """A theme with variant-only layers uses variant params for placements."""
        from src.themes.library import load_theme_library

        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)

        wave_sine_variant = EffectVariant(
            name="Wave Sine",
            base_effect="Fire",
            description="Sine-wave shaped fire for gentle ethereal sections",
            parameter_overrides={
                "E_SLIDER_Fire_Height": 42,
                "E_SLIDER_Fire_HueShift": 15,
            },
            tags=VariantTags(
                tier_affinity="background",
                energy_level="low",
                speed_feel="slow",
                section_roles=["verse", "bridge"],
                scope="group",
                genre_affinity="any",
            ),
        )
        variant_lib = VariantLibrary(
            schema_version="1.0.0",
            variants={"Wave Sine": wave_sine_variant},
            builtin_names={"Wave Sine"},
        )

        theme_data = {
            "name": "Test Theme",
            "mood": "ethereal",
            "occasion": "general",
            "genre": "any",
            "intent": "test",
            "layers": [
                {"variant": "Wave Sine", "blend_mode": "Normal"}
            ],
            "palette": ["#FF0000", "#00FF00"],
            "alternates": [],
        }

        import json
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump({"schema_version": "1.0.0", "themes": {"Test Theme": theme_data}}, tmp)
            tmp_path = tmp.name

        theme_lib = load_theme_library(
            builtin_path=Path(tmp_path),
            effect_library=effect_lib,
            variant_library=variant_lib,
        )

        theme = theme_lib.get("Test Theme")
        assert theme is not None, "Theme 'Test Theme' should be loaded from the catalog"
        assert len(theme.layers) == 1
        layer = theme.layers[0]

        # New model: layer.variant holds the variant name
        assert layer.variant == "Wave Sine", (
            f"Expected layer.variant='Wave Sine', got {layer.variant!r}"
        )

        # New model: no parameter_overrides field on the layer
        assert not hasattr(layer, "parameter_overrides"), (
            "Post-refactor EffectLayer must not have parameter_overrides"
        )

        section = _make_section_energy(start_ms=0, end_ms=10000)
        assignment = SectionAssignment(
            section=section,
            theme=theme,
            variation_seed=0,
            group_effects={},
        )
        groups = _make_groups()
        hierarchy = _make_hierarchy(duration_ms=10000)

        result = place_effects(
            assignment, groups, effect_lib, hierarchy,
            variant_library=variant_lib,
        )

        all_placements = [p for placements in result.values() for p in placements]
        assert len(all_placements) > 0, "Expected at least one placement"

        height_ok = any(
            p.parameters.get("E_SLIDER_Fire_Height") == 42 for p in all_placements
        )
        hue_ok = any(
            p.parameters.get("E_SLIDER_Fire_HueShift") == 15 for p in all_placements
        )
        assert height_ok, (
            "Expected E_SLIDER_Fire_Height=42 from Wave Sine variant, "
            f"got: {[p.parameters for p in all_placements]}"
        )
        assert hue_ok, (
            "Expected E_SLIDER_Fire_HueShift=15 from Wave Sine variant, "
            f"got: {[p.parameters for p in all_placements]}"
        )
