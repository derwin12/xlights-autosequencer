"""Tests for src/themes/models.py — dataclasses."""
from __future__ import annotations

import pytest

from src.themes.models import (
    EffectLayer,
    Theme,
    VALID_BLEND_MODES,
    VALID_GENRES,
    VALID_MOODS,
    VALID_OCCASIONS,
)


class TestEffectLayer:
    def test_construction(self):
        layer = EffectLayer(
            effect="Fire",
            blend_mode="Normal",
            parameter_overrides={"E_SLIDER_Fire_Height": 80},
        )
        assert layer.effect == "Fire"
        assert layer.blend_mode == "Normal"

    def test_default_blend_mode(self):
        layer = EffectLayer(effect="Fire")
        assert layer.blend_mode == "Normal"

    def test_default_overrides_empty(self):
        layer = EffectLayer(effect="Fire")
        assert layer.parameter_overrides == {}

    def test_from_dict(self):
        data = {
            "effect": "Fire",
            "blend_mode": "Additive",
            "parameter_overrides": {"E_SLIDER_Fire_Height": 80},
        }
        layer = EffectLayer.from_dict(data)
        assert layer.effect == "Fire"
        assert layer.blend_mode == "Additive"

    def test_from_dict_minimal(self):
        data = {"effect": "Fire"}
        layer = EffectLayer.from_dict(data)
        assert layer.blend_mode == "Normal"
        assert layer.parameter_overrides == {}


class TestTheme:
    def _make_theme(self) -> Theme:
        return Theme(
            name="Inferno",
            mood="aggressive",
            occasion="general",
            genre="rock",
            intent="Raw power",
            layers=[
                EffectLayer(effect="Fire", blend_mode="Normal"),
                EffectLayer(effect="Bars", blend_mode="Additive"),
            ],
            palette=["#FF4400", "#FF8800"],
        )

    def test_construction(self):
        t = self._make_theme()
        assert t.name == "Inferno"
        assert t.mood == "aggressive"
        assert len(t.layers) == 2
        assert len(t.palette) == 2

    def test_from_dict(self):
        data = {
            "name": "Inferno",
            "mood": "aggressive",
            "occasion": "general",
            "genre": "rock",
            "intent": "Raw power",
            "layers": [
                {"effect": "Fire", "blend_mode": "Normal", "parameter_overrides": {}},
            ],
            "palette": ["#FF4400", "#FF8800"],
        }
        t = Theme.from_dict(data)
        assert t.name == "Inferno"
        assert isinstance(t.layers[0], EffectLayer)

    def test_from_dict_defaults(self):
        data = {
            "name": "Simple",
            "mood": "ethereal",
            "intent": "Test",
            "layers": [{"effect": "On"}],
            "palette": ["#FFFFFF", "#000000"],
        }
        t = Theme.from_dict(data)
        assert t.occasion == "general"
        assert t.genre == "any"


class TestConstants:
    def test_moods(self):
        assert set(VALID_MOODS) == {"ethereal", "aggressive", "dark", "structural"}

    def test_occasions(self):
        assert set(VALID_OCCASIONS) == {"christmas", "halloween", "general"}

    def test_genres(self):
        assert set(VALID_GENRES) == {"rock", "pop", "classical", "any"}

    def test_blend_modes_count(self):
        assert len(VALID_BLEND_MODES) == 24

    def test_blend_modes_includes_key_modes(self):
        assert "Normal" in VALID_BLEND_MODES
        assert "Additive" in VALID_BLEND_MODES
        assert "Subtractive" in VALID_BLEND_MODES
        assert "1 is Mask" in VALID_BLEND_MODES
