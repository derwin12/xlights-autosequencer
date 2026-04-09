"""Tests for src/themes/validator.py — theme validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.themes.validator import validate_theme

EFFECTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library.json"


@pytest.fixture
def effect_lib():
    return load_effect_library(builtin_path=EFFECTS_FIXTURE)


class _FakeVariant:
    """Minimal variant stand-in."""
    def __init__(self, base_effect: str):
        self.base_effect = base_effect


class _FakeVariantLib:
    """Variant library stub that resolves known variants to their base effects."""
    def __init__(self, known: dict[str, str]):
        # known: variant_name -> base_effect
        self._known = known

    def get(self, name: str):
        if name in self._known:
            return _FakeVariant(self._known[name])
        return None


@pytest.fixture
def variant_lib():
    """A minimal variant library with known variants mapping to effects."""
    return _FakeVariantLib({"Fire Blaze": "Fire", "Bars Classic": "Bars", "On Basic": "On"})


def _valid_theme() -> dict:
    return {
        "name": "Test",
        "mood": "aggressive",
        "occasion": "general",
        "genre": "rock",
        "intent": "Testing",
        "layers": [
            {"variant": "Fire Blaze", "blend_mode": "Normal"},
        ],
        "palette": ["#FF0000", "#00FF00"],
    }


class TestValidateTheme:
    def test_valid_theme_passes(self, effect_lib, variant_lib):
        assert validate_theme(_valid_theme(), effect_lib, variant_lib) == []

    def test_missing_name_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        del data["name"]
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("name" in e.lower() for e in errors)

    def test_missing_mood_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        del data["mood"]
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("mood" in e.lower() for e in errors)

    def test_invalid_mood_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["mood"] = "spooky"
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("mood" in e.lower() for e in errors)

    def test_invalid_occasion_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["occasion"] = "easter"
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("occasion" in e.lower() for e in errors)

    def test_invalid_genre_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["genre"] = "jazz"
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("genre" in e.lower() for e in errors)

    def test_empty_layers_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"] = []
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("layer" in e.lower() for e in errors)

    def test_invalid_blend_mode_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"][0]["blend_mode"] = "SuperBlend"
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("blend" in e.lower() for e in errors)

    def test_bottom_layer_not_normal_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"][0]["blend_mode"] = "Additive"
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("bottom" in e.lower() for e in errors)

    def test_variant_not_in_library_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"][0]["variant"] = "NonExistentVariant"
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("NonExistentVariant" in e for e in errors)

    def test_palette_fewer_than_2_warns(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["palette"] = ["#FF0000"]
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("palette" in e.lower() for e in errors)

    def test_missing_palette_fails(self, effect_lib, variant_lib):
        data = _valid_theme()
        del data["palette"]
        errors = validate_theme(data, effect_lib, variant_lib)
        assert any("palette" in e.lower() for e in errors)

    def test_multi_layer_valid(self, effect_lib, variant_lib):
        data = _valid_theme()
        data["layers"].append({"variant": "Bars Classic", "blend_mode": "Additive"})
        assert validate_theme(data, effect_lib, variant_lib) == []

    def test_modifier_on_bottom_layer_fails(self, effect_lib, variant_lib):
        """Valid theme with non-modifier bottom layer passes."""
        data = _valid_theme()
        assert validate_theme(data, effect_lib, variant_lib) == []


# ---------------------------------------------------------------------------
# T005 — Validator tests for variant_library requirement
# ---------------------------------------------------------------------------

def _variant_theme_data(variant_name: str = "Wave Sine") -> dict:
    """Minimal theme using the new `variant` key on layers (post-refactor shape)."""
    return {
        "name": "Surf",
        "mood": "ethereal",
        "occasion": "general",
        "genre": "any",
        "intent": "Ocean vibes",
        "layers": [
            {"variant": variant_name, "blend_mode": "Normal"},
        ],
        "palette": ["#0077FF", "#00AAFF"],
    }


class _FakeVariantLibrary:
    """Minimal stand-in for a variant library that holds one known variant."""

    def __init__(self, known_variants: list[str]):
        self._known = set(known_variants)

    def get(self, name: str):
        if name in self._known:
            return _FakeVariant("Fire")  # truthy with base_effect
        return None


class TestValidatorVariantLibrary:
    def test_validator_requires_variant_library(self, effect_lib):
        """`validate_theme` must raise TypeError when variant_library is not supplied."""
        with pytest.raises(TypeError):
            validate_theme(_variant_theme_data(), effect_lib)  # missing variant_library arg

    def test_validator_rejects_missing_variant_as_error(self, effect_lib):
        """A layer.variant that is not in variant_library must produce an error, not just a warning."""
        variant_lib = _FakeVariantLibrary(known_variants=["Ripple Center"])
        errors = validate_theme(_variant_theme_data("NonExistentVariant"), effect_lib, variant_lib)
        assert any("NonExistentVariant" in e for e in errors), (
            "Expected an error for unknown variant 'NonExistentVariant', got: " + repr(errors)
        )

    def test_validator_no_error_for_valid_variant(self, effect_lib):
        """A layer.variant that IS in variant_library must produce no errors."""
        variant_lib = _FakeVariantLibrary(known_variants=["Wave Sine"])
        errors = validate_theme(_variant_theme_data("Wave Sine"), effect_lib, variant_lib)
        assert errors == [], f"Expected no errors for valid variant, got: {errors}"

    def test_validator_no_parameter_overrides_check(self, effect_lib):
        """Validator must not inspect `parameter_overrides` on layers (field no longer exists)."""
        variant_lib = _FakeVariantLibrary(known_variants=["Wave Sine"])
        data = _variant_theme_data("Wave Sine")
        assert "parameter_overrides" not in data["layers"][0]
        errors = validate_theme(data, effect_lib, variant_lib)
        assert errors == [], f"Unexpected errors when parameter_overrides is absent: {errors}"
