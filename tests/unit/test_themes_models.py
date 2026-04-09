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
        layer = EffectLayer(variant="Fire Blaze", blend_mode="Normal")
        assert layer.variant == "Fire Blaze"
        assert layer.blend_mode == "Normal"

    def test_default_blend_mode(self):
        layer = EffectLayer(variant="Fire Blaze")
        assert layer.blend_mode == "Normal"

    def test_effect_pool_defaults_empty(self):
        layer = EffectLayer(variant="Fire Blaze")
        assert layer.effect_pool == []

    def test_from_dict(self):
        data = {"variant": "Fire Blaze", "blend_mode": "Additive"}
        layer = EffectLayer.from_dict(data)
        assert layer.variant == "Fire Blaze"
        assert layer.blend_mode == "Additive"

    def test_from_dict_minimal(self):
        data = {"variant": "Fire Blaze"}
        layer = EffectLayer.from_dict(data)
        assert layer.blend_mode == "Normal"
        assert layer.effect_pool == []


class TestTheme:
    def _make_theme(self) -> Theme:
        return Theme(
            name="Inferno",
            mood="aggressive",
            occasion="general",
            genre="rock",
            intent="Raw power",
            layers=[
                EffectLayer(variant="Fire Blaze", blend_mode="Normal"),
                EffectLayer(variant="Bars Triple", blend_mode="Additive"),
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
            "layers": [{"variant": "Fire Blaze", "blend_mode": "Normal"}],
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
            "layers": [{"variant": "Wave Sine"}],
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


# ---------------------------------------------------------------------------
# T003 — EffectLayer new model tests (FAILING — implementation does not exist yet)
# These tests specify the NEW EffectLayer shape after theme-variant-separation:
#   - `variant` field replaces `effect` + `parameter_overrides` + `variant_ref`
#   - `effect`, `parameter_overrides`, and `variant_ref` fields are removed
# ---------------------------------------------------------------------------

class TestEffectLayerNewModel:
    def test_effect_layer_requires_variant_field(self):
        """EffectLayer must accept a `variant` field (a string variant name)."""
        layer = EffectLayer(variant="Wave Sine", blend_mode="Normal")
        assert layer.variant == "Wave Sine"

    def test_effect_layer_has_no_effect_field(self):
        """EffectLayer must NOT have an `effect` field after the refactor."""
        layer = EffectLayer(variant="Wave Sine")
        with pytest.raises(AttributeError):
            _ = layer.effect  # noqa: F841

    def test_effect_layer_has_no_parameter_overrides(self):
        """EffectLayer must NOT have a `parameter_overrides` field after the refactor."""
        layer = EffectLayer(variant="Wave Sine")
        with pytest.raises(AttributeError):
            _ = layer.parameter_overrides  # noqa: F841

    def test_effect_layer_has_no_variant_ref(self):
        """EffectLayer must NOT have a `variant_ref` field after the refactor."""
        layer = EffectLayer(variant="Wave Sine")
        with pytest.raises(AttributeError):
            _ = layer.variant_ref  # noqa: F841

    def test_effect_layer_from_dict_with_variant(self):
        """`EffectLayer.from_dict` reads the `variant` key, not `effect`."""
        data = {"variant": "Wave Sine", "blend_mode": "Normal"}
        layer = EffectLayer.from_dict(data)
        assert layer.variant == "Wave Sine"
        assert layer.blend_mode == "Normal"

    def test_effect_layer_to_dict_contains_variant(self):
        """`layer.to_dict()` returns `variant` key; must NOT contain `effect` or `parameter_overrides`."""
        layer = EffectLayer(variant="Wave Sine", blend_mode="Normal")
        d = layer.to_dict()
        assert "variant" in d
        assert d["variant"] == "Wave Sine"
        assert "effect" not in d
        assert "parameter_overrides" not in d

    def test_effect_layer_effect_pool_defaults_empty(self):
        """effect_pool field must still exist and default to []."""
        layer = EffectLayer(variant="Wave Sine")
        assert layer.effect_pool == []


# ---------------------------------------------------------------------------
# T004 — ThemeAlternate rename tests (FAILING — implementation does not exist yet)
# These tests specify:
#   - `ThemeVariant` is renamed to `ThemeAlternate`
#   - `Theme.variants` field is renamed to `Theme.alternates`
#   - `Theme.from_dict` reads from the "alternates" JSON key
# ---------------------------------------------------------------------------

class TestThemeAlternateRename:
    def test_theme_alternate_class_exists(self):
        """`ThemeAlternate` must be importable from src.themes.models."""
        from src.themes.models import ThemeAlternate  # noqa: F401

    def test_theme_variant_class_removed(self):
        """`ThemeVariant` must no longer exist in src.themes.models."""
        import importlib
        import src.themes.models as m
        assert not hasattr(m, "ThemeVariant"), (
            "ThemeVariant still exists — it should have been renamed to ThemeAlternate"
        )

    def test_theme_alternate_from_dict(self):
        """`ThemeAlternate.from_dict` builds an instance from layers using the `variant` key."""
        from src.themes.models import ThemeAlternate
        data = {"layers": [{"variant": "Wave Sine", "blend_mode": "Normal"}]}
        alt = ThemeAlternate.from_dict(data)
        assert len(alt.layers) == 1
        assert alt.layers[0].variant == "Wave Sine"

    def test_theme_alternates_field_on_theme(self):
        """`Theme` dataclass must expose `.alternates`, not `.variants`."""
        t = Theme(
            name="X",
            mood="ethereal",
            occasion="general",
            genre="any",
            intent="Test",
            layers=[EffectLayer(variant="Wave Sine", blend_mode="Normal")],
            palette=["#FFFFFF", "#000000"],
        )
        assert hasattr(t, "alternates"), "Theme must have an `alternates` field"
        assert not hasattr(t, "variants"), "Theme must NOT have a `variants` field after rename"

    def test_theme_from_dict_uses_alternates_key(self):
        """`Theme.from_dict` must read the `alternates` JSON key, not `variants`."""
        from src.themes.models import ThemeAlternate
        data = {
            "name": "Surf",
            "mood": "ethereal",
            "occasion": "general",
            "genre": "any",
            "intent": "Ocean vibes",
            "layers": [{"variant": "Wave Sine", "blend_mode": "Normal"}],
            "palette": ["#0077FF", "#00AAFF"],
            "alternates": [
                {"layers": [{"variant": "Ripple Center", "blend_mode": "Normal"}]}
            ],
        }
        t = Theme.from_dict(data)
        assert hasattr(t, "alternates")
        assert len(t.alternates) == 1
        assert isinstance(t.alternates[0], ThemeAlternate)
