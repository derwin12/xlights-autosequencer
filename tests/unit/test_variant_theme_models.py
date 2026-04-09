"""Unit tests for new EffectLayer model (variant field) and theme validation."""
from __future__ import annotations

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
def variant_lib(effect_lib):
    return load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_lib)


def _valid_theme() -> dict:
    """A minimal valid theme dict using new variant-only layer format."""
    return {
        "name": "Test",
        "mood": "aggressive",
        "occasion": "general",
        "genre": "any",
        "intent": "Testing",
        "layers": [
            {"variant": "Fire Blaze High", "blend_mode": "Normal"},
        ],
        "palette": ["#FF0000", "#00FF00"],
    }


class TestEffectLayerVariantField:
    """Tests for new EffectLayer.variant field (replaces effect + parameter_overrides + variant_ref)."""

    def test_from_dict_with_variant(self):
        data = {"variant": "meteors-fast-down", "blend_mode": "Normal"}
        layer = EffectLayer.from_dict(data)
        assert layer.variant == "meteors-fast-down"

    def test_from_dict_defaults_blend_mode(self):
        data = {"variant": "Fire Blaze High"}
        layer = EffectLayer.from_dict(data)
        assert layer.blend_mode == "Normal"

    def test_to_dict_includes_variant(self):
        layer = EffectLayer(variant="meteors-fast-down", blend_mode="Additive")
        d = layer.to_dict()
        assert d["variant"] == "meteors-fast-down"
        assert d["blend_mode"] == "Additive"

    def test_to_dict_has_no_effect_or_parameter_overrides(self):
        layer = EffectLayer(variant="Fire Blaze High")
        d = layer.to_dict()
        assert "effect" not in d
        assert "parameter_overrides" not in d
        assert "variant_ref" not in d

    def test_roundtrip_preserves_variant(self):
        original = EffectLayer(variant="bars-triple", blend_mode="Additive",
                               effect_pool=["bars-triple", "fire-low-flicker"])
        restored = EffectLayer.from_dict(original.to_dict())
        assert restored.variant == "bars-triple"
        assert restored.blend_mode == "Additive"
        assert restored.effect_pool == ["bars-triple", "fire-low-flicker"]

    def test_no_parameter_overrides_field(self):
        layer = EffectLayer(variant="Fire Blaze High")
        assert not hasattr(layer, "parameter_overrides")

    def test_no_effect_field(self):
        layer = EffectLayer(variant="Fire Blaze High")
        assert not hasattr(layer, "effect")

    def test_no_variant_ref_field(self):
        layer = EffectLayer(variant="Fire Blaze High")
        assert not hasattr(layer, "variant_ref")


class TestValidateThemeWithVariants:
    """Tests for validate_theme with new variant-only layer format."""

    def test_valid_variant_passes(self, effect_lib, variant_lib):
        data = _valid_theme()
        errors = validate_theme(data, effect_lib, variant_lib)
        assert errors == []

    def test_missing_variant_is_error(self, effect_lib, variant_lib):
        """variant pointing to nonexistent variant is a hard error."""
        data = _valid_theme()
        data["layers"][0]["variant"] = "nonexistent-variant"
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("nonexistent-variant" in e for e in errors)

    def test_valid_bars_variant_passes(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"][0] = {"variant": "bars-triple", "blend_mode": "Normal"}
        errors = validate_theme(data, effect_lib, variant_lib)
        assert errors == []

    def test_valid_meteors_variant_passes(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"][0] = {"variant": "meteors-fast-down", "blend_mode": "Normal"}
        errors = validate_theme(data, effect_lib, variant_lib)
        assert errors == []


class TestEffectLayerEffectPool:
    """Tests for EffectLayer.effect_pool field."""

    def test_from_dict_with_effect_pool(self):
        data = {"variant": "Fire Blaze High", "effect_pool": ["variant-a", "variant-b"]}
        layer = EffectLayer.from_dict(data)
        assert layer.effect_pool == ["variant-a", "variant-b"]

    def test_from_dict_without_effect_pool_defaults_to_empty_list(self):
        data = {"variant": "Fire Blaze High", "blend_mode": "Normal"}
        layer = EffectLayer.from_dict(data)
        assert layer.effect_pool == []

    def test_to_dict_includes_effect_pool_when_populated(self):
        layer = EffectLayer(variant="Fire Blaze High",
                            effect_pool=["meteors-fast-down", "fire-low-flicker"])
        d = layer.to_dict()
        assert "effect_pool" in d
        assert d["effect_pool"] == ["meteors-fast-down", "fire-low-flicker"]

    def test_to_dict_includes_effect_pool_as_empty_list_when_not_set(self):
        layer = EffectLayer(variant="Fire Blaze High")
        d = layer.to_dict()
        assert "effect_pool" in d
        assert d["effect_pool"] == []

    def test_roundtrip_preserves_effect_pool(self):
        original = EffectLayer(variant="meteors-fast-down",
                               effect_pool=["meteors-fast-down", "fire-low-flicker"])
        restored = EffectLayer.from_dict(original.to_dict())
        assert restored.effect_pool == ["meteors-fast-down", "fire-low-flicker"]
        assert restored.variant == "meteors-fast-down"
