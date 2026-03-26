"""Tests for src/effects/models.py — dataclasses."""
from __future__ import annotations

import pytest

from src.effects.models import (
    ALL_XLIGHTS_EFFECTS,
    AnalysisMapping,
    EffectDefinition,
    EffectParameter,
    PROP_TYPES,
    SUITABILITY_RATINGS,
)


class TestEffectParameter:
    def test_construction_slider(self):
        p = EffectParameter(
            name="Fire_Height",
            storage_name="E_SLIDER_Fire_Height",
            widget_type="slider",
            value_type="int",
            default=50,
            min=1,
            max=100,
            description="Flame height",
        )
        assert p.name == "Fire_Height"
        assert p.widget_type == "slider"
        assert p.default == 50

    def test_construction_checkbox(self):
        p = EffectParameter(
            name="Fire_GrowWithMusic",
            storage_name="E_CHECKBOX_Fire_GrowWithMusic",
            widget_type="checkbox",
            value_type="bool",
            default=False,
            description="Music reactive",
        )
        assert p.value_type == "bool"
        assert p.min is None
        assert p.max is None

    def test_construction_choice(self):
        p = EffectParameter(
            name="Fire_Location",
            storage_name="E_CHOICE_Fire_Location",
            widget_type="choice",
            value_type="choice",
            default="Bottom",
            choices=["Bottom", "Top", "Left", "Right"],
            description="Origin direction",
        )
        assert p.choices == ["Bottom", "Top", "Left", "Right"]

    def test_supports_value_curve_default_false(self):
        p = EffectParameter(
            name="X", storage_name="E_SLIDER_X", widget_type="slider",
            value_type="int", default=0, description="test",
        )
        assert p.supports_value_curve is False

    def test_from_dict(self):
        data = {
            "name": "Fire_Height",
            "storage_name": "E_SLIDER_Fire_Height",
            "widget_type": "slider",
            "value_type": "int",
            "default": 50,
            "min": 1,
            "max": 100,
            "description": "Height",
            "supports_value_curve": True,
        }
        p = EffectParameter.from_dict(data)
        assert p.name == "Fire_Height"
        assert p.supports_value_curve is True


class TestAnalysisMapping:
    def test_construction(self):
        m = AnalysisMapping(
            parameter="Fire_Height",
            analysis_level="L5",
            analysis_field="energy_curves.bass",
            mapping_type="direct",
            description="Bass drives height",
        )
        assert m.analysis_level == "L5"
        assert m.mapping_type == "direct"

    def test_from_dict(self):
        data = {
            "parameter": "Fire_Height",
            "analysis_level": "L5",
            "analysis_field": "energy_curves.bass",
            "mapping_type": "direct",
            "description": "Bass drives height",
        }
        m = AnalysisMapping.from_dict(data)
        assert m.parameter == "Fire_Height"


class TestEffectDefinition:
    def _make_definition(self) -> EffectDefinition:
        return EffectDefinition(
            name="Fire",
            xlights_id="eff_FIRE",
            category="nature",
            description="Fire effect",
            intent="Aggressive sections",
            parameters=[
                EffectParameter(
                    name="Fire_Height", storage_name="E_SLIDER_Fire_Height",
                    widget_type="slider", value_type="int", default=50,
                    min=1, max=100, description="Height",
                ),
            ],
            prop_suitability={"matrix": "ideal", "outline": "good", "arch": "possible", "vertical": "good", "tree": "good", "radial": "good"},
            analysis_mappings=[],
        )

    def test_construction(self):
        d = self._make_definition()
        assert d.name == "Fire"
        assert len(d.parameters) == 1

    def test_from_dict(self):
        data = {
            "name": "Fire",
            "xlights_id": "eff_FIRE",
            "category": "nature",
            "description": "Fire effect",
            "intent": "Aggressive",
            "parameters": [{
                "name": "Fire_Height", "storage_name": "E_SLIDER_Fire_Height",
                "widget_type": "slider", "value_type": "int",
                "default": 50, "min": 1, "max": 100, "description": "Height",
            }],
            "prop_suitability": {"matrix": "ideal", "outline": "good", "arch": "possible", "vertical": "good", "tree": "good", "radial": "good"},
            "analysis_mappings": [],
        }
        d = EffectDefinition.from_dict(data)
        assert d.name == "Fire"
        assert isinstance(d.parameters[0], EffectParameter)


class TestConstants:
    def test_all_xlights_effects_count(self):
        assert len(ALL_XLIGHTS_EFFECTS) == 56

    def test_prop_types(self):
        assert set(PROP_TYPES) == {"matrix", "outline", "arch", "vertical", "tree", "radial"}

    def test_suitability_ratings(self):
        assert set(SUITABILITY_RATINGS) == {"ideal", "good", "possible", "not_recommended"}
