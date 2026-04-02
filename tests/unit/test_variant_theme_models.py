"""Unit tests for EffectLayer.variant_ref field and theme validation with variants."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.themes.models import EffectLayer
from src.themes.validator import validate_theme
from src.variants.library import load_variant_library

EFFECTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library_with_meteors.json"
VARIANTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "variants" / "variants_with_variant_refs.json"


@pytest.fixture
def effect_lib():
    return load_effect_library(builtin_path=EFFECTS_FIXTURE)


@pytest.fixture
def variant_lib():
    return load_variant_library(builtin_path=VARIANTS_FIXTURE)


def _valid_theme() -> dict:
    return {
        "name": "Test",
        "mood": "aggressive",
        "occasion": "general",
        "genre": "any",
        "intent": "Testing",
        "layers": [
            {"effect": "Fire", "blend_mode": "Normal", "parameter_overrides": {}},
        ],
        "palette": ["#FF0000", "#00FF00"],
    }


class TestEffectLayerVariantRef:
    def test_from_dict_with_variant_ref(self):
        data = {
            "effect": "Meteors",
            "blend_mode": "Normal",
            "parameter_overrides": {},
            "variant_ref": "meteors-fast-down",
        }
        layer = EffectLayer.from_dict(data)
        assert layer.variant_ref == "meteors-fast-down"

    def test_from_dict_without_variant_ref_defaults_to_none(self):
        data = {
            "effect": "Fire",
            "blend_mode": "Normal",
            "parameter_overrides": {},
        }
        layer = EffectLayer.from_dict(data)
        assert layer.variant_ref is None

    def test_from_dict_explicit_none_variant_ref(self):
        data = {
            "effect": "Bars",
            "blend_mode": "Normal",
            "parameter_overrides": {},
            "variant_ref": None,
        }
        layer = EffectLayer.from_dict(data)
        assert layer.variant_ref is None

    def test_to_dict_includes_variant_ref_when_set(self):
        layer = EffectLayer(
            effect="Meteors",
            blend_mode="Normal",
            parameter_overrides={},
            variant_ref="meteors-fast-down",
        )
        d = layer.to_dict()
        assert "variant_ref" in d
        assert d["variant_ref"] == "meteors-fast-down"

    def test_to_dict_includes_variant_ref_when_none(self):
        layer = EffectLayer(
            effect="Fire",
            blend_mode="Normal",
            parameter_overrides={},
            variant_ref=None,
        )
        d = layer.to_dict()
        assert "variant_ref" in d
        assert d["variant_ref"] is None

    def test_roundtrip_preserves_variant_ref(self):
        original = EffectLayer(
            effect="Bars",
            blend_mode="Additive",
            parameter_overrides={"E_SLIDER_Bars_BarCount": 5},
            variant_ref="bars-triple",
        )
        d = original.to_dict()
        restored = EffectLayer.from_dict(d)
        assert restored.variant_ref == "bars-triple"
        assert restored.effect == "Bars"
        assert restored.parameter_overrides == {"E_SLIDER_Bars_BarCount": 5}


class TestValidateThemeWithVariants:
    def test_valid_variant_ref_passes(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"][0] = {
            "effect": "Bars",
            "blend_mode": "Normal",
            "parameter_overrides": {},
            "variant_ref": "bars-triple",
        }
        errors = validate_theme(data, effect_lib, variant_library=variant_lib)
        assert errors == []

    def test_missing_variant_ref_is_warning_not_error(self, effect_lib, variant_lib, caplog):
        """variant_ref pointing to nonexistent variant emits a WARNING, not an error."""
        data = _valid_theme()
        data["layers"][0]["variant_ref"] = "nonexistent-variant"
        with caplog.at_level(logging.WARNING, logger="src.themes.validator"):
            errors = validate_theme(data, effect_lib, variant_library=variant_lib)
        # Must not be in errors list (not a hard failure)
        error_texts = " ".join(errors)
        assert "nonexistent-variant" not in error_texts
        # Must have logged a warning
        assert any("nonexistent-variant" in r.message for r in caplog.records)

    def test_variant_base_effect_mismatch_is_error(self, effect_lib, variant_lib):
        """variant_ref whose base_effect doesn't match the layer effect is an error."""
        data = _valid_theme()
        # Layer uses Fire, but meteors-fast-down is for Meteors
        data["layers"][0]["variant_ref"] = "meteors-fast-down"
        errors = validate_theme(data, effect_lib, variant_library=variant_lib)
        assert any(
            "meteors-fast-down" in e or "base_effect" in e.lower() or "mismatch" in e.lower()
            for e in errors
        )

    def test_no_variant_library_ignores_variant_ref(self, effect_lib):
        """Without variant_library, variant_ref is silently ignored."""
        data = _valid_theme()
        data["layers"][0]["variant_ref"] = "whatever"
        errors = validate_theme(data, effect_lib)
        assert errors == []

    def test_variant_ref_none_with_variant_library_passes(self, effect_lib, variant_lib):
        """variant_ref=None with variant_library provided causes no issue."""
        data = _valid_theme()
        data["layers"][0]["variant_ref"] = None
        errors = validate_theme(data, effect_lib, variant_library=variant_lib)
        assert errors == []

    def test_matching_effect_and_variant_passes(self, effect_lib, variant_lib):
        """Fire layer with fire-low-flicker variant passes."""
        data = _valid_theme()
        data["layers"][0]["variant_ref"] = "fire-low-flicker"
        errors = validate_theme(data, effect_lib, variant_library=variant_lib)
        assert errors == []


class TestEffectLayerEffectPool:
    """Tests for EffectLayer.effect_pool field."""

    def test_from_dict_with_effect_pool(self):
        data = {
            "effect": "Fire",
            "effect_pool": ["variant-a", "variant-b"],
        }
        layer = EffectLayer.from_dict(data)
        assert layer.effect_pool == ["variant-a", "variant-b"]

    def test_from_dict_without_effect_pool_defaults_to_empty_list(self):
        data = {"effect": "Fire", "blend_mode": "Normal", "parameter_overrides": {}}
        layer = EffectLayer.from_dict(data)
        assert layer.effect_pool == []

    def test_to_dict_includes_effect_pool_when_populated(self):
        layer = EffectLayer(
            effect="Fire",
            effect_pool=["meteors-fast-down", "fire-low-flicker"],
        )
        d = layer.to_dict()
        assert "effect_pool" in d
        assert d["effect_pool"] == ["meteors-fast-down", "fire-low-flicker"]

    def test_to_dict_includes_effect_pool_as_empty_list_when_not_set(self):
        layer = EffectLayer(effect="Fire")
        d = layer.to_dict()
        assert "effect_pool" in d
        assert d["effect_pool"] == []

    def test_backward_compat_existing_dict_without_effect_pool(self):
        """Dicts saved before effect_pool was added still parse correctly."""
        data = {
            "effect": "Bars",
            "blend_mode": "Additive",
            "parameter_overrides": {"E_SLIDER_Bars_BarCount": 5},
            "variant_ref": "bars-triple",
        }
        layer = EffectLayer.from_dict(data)
        assert layer.effect == "Bars"
        assert layer.blend_mode == "Additive"
        assert layer.variant_ref == "bars-triple"
        assert layer.effect_pool == []

    def test_roundtrip_preserves_effect_pool(self):
        original = EffectLayer(
            effect="Meteors",
            blend_mode="Normal",
            parameter_overrides={},
            variant_ref="meteors-fast-down",
            effect_pool=["meteors-fast-down", "meteors-slow-up"],
        )
        d = original.to_dict()
        restored = EffectLayer.from_dict(d)
        assert restored.effect_pool == ["meteors-fast-down", "meteors-slow-up"]
        assert restored.variant_ref == "meteors-fast-down"
