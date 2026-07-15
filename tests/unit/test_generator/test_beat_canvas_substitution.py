"""Tests for _substitute_beat_canvas_effect (tier-4 BEAT blocky-effect swap)."""
from __future__ import annotations

from src.effects.library import EffectLibrary
from src.effects.models import EffectDefinition
from src.generator.effect_placer import _substitute_beat_canvas_effect


def _effect(name: str) -> EffectDefinition:
    return EffectDefinition(
        name=name, xlights_id=f"E_{name.upper().replace(' ', '')}", category="test",
        description="test effect", intent="fill", parameters=[],
        prop_suitability={}, analysis_mappings=[], layer_role="standalone",
        duration_type="section",
    )


def _library(*names: str) -> EffectLibrary:
    effects = {n: _effect(n) for n in names}
    return EffectLibrary(schema_version="1.0.0", target_xlights_version="2024.15", effects=effects)


class TestSubstituteBeatCanvasEffect:
    def test_single_strand_substituted_with_color_wash(self) -> None:
        library = _library("Single Strand", "Color Wash")
        result = _substitute_beat_canvas_effect(_effect("Single Strand"), library)
        assert result.name == "Color Wash"

    def test_bars_substituted_with_color_wash(self) -> None:
        library = _library("Bars", "Color Wash")
        result = _substitute_beat_canvas_effect(_effect("Bars"), library)
        assert result.name == "Color Wash"

    def test_curtain_substituted_with_color_wash(self) -> None:
        library = _library("Curtain", "Color Wash")
        result = _substitute_beat_canvas_effect(_effect("Curtain"), library)
        assert result.name == "Color Wash"

    def test_non_blocky_effect_passes_through_unchanged(self) -> None:
        library = _library("Butterfly", "Color Wash")
        result = _substitute_beat_canvas_effect(_effect("Butterfly"), library)
        assert result.name == "Butterfly"

    def test_falls_back_to_original_when_color_wash_missing(self) -> None:
        library = _library("Single Strand")
        result = _substitute_beat_canvas_effect(_effect("Single Strand"), library)
        assert result.name == "Single Strand"
