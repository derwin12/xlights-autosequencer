"""Unit tests for GenerationConfig nominal fields added by spec 047."""
from __future__ import annotations

import pytest


@pytest.fixture
def cfg_kwargs(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"ID3")
    layout = tmp_path / "layout.xml"
    layout.write_text("<xlightsproject/>")
    return {
        "audio_path": audio,
        "layout_path": layout,
        "output_dir": tmp_path,
    }


class TestMoodIntentField:
    def test_default_is_auto(self, cfg_kwargs):
        from src.generator.models import GenerationConfig
        cfg = GenerationConfig(**cfg_kwargs)
        assert cfg.mood_intent == "auto"

    @pytest.mark.parametrize("value", ["auto", "party", "emotional", "dramatic", "playful"])
    def test_accepts_valid_values(self, cfg_kwargs, value):
        from src.generator.models import GenerationConfig
        cfg = GenerationConfig(mood_intent=value, **cfg_kwargs)
        assert cfg.mood_intent == value

    def test_rejects_unknown_value(self, cfg_kwargs):
        from src.generator.models import GenerationConfig
        with pytest.raises(ValueError, match="mood_intent"):
            GenerationConfig(mood_intent="bouncy", **cfg_kwargs)


class TestDurationFeelField:
    def test_default_is_auto(self, cfg_kwargs):
        from src.generator.models import GenerationConfig
        cfg = GenerationConfig(**cfg_kwargs)
        assert cfg.duration_feel == "auto"

    @pytest.mark.parametrize("value", ["auto", "snappy", "balanced", "flowing"])
    def test_accepts_valid_values(self, cfg_kwargs, value):
        from src.generator.models import GenerationConfig
        cfg = GenerationConfig(duration_feel=value, **cfg_kwargs)
        assert cfg.duration_feel == value

    def test_rejects_unknown_value(self, cfg_kwargs):
        from src.generator.models import GenerationConfig
        with pytest.raises(ValueError, match="duration_feel"):
            GenerationConfig(duration_feel="instant", **cfg_kwargs)


class TestAccentStrengthField:
    def test_default_is_auto(self, cfg_kwargs):
        from src.generator.models import GenerationConfig
        cfg = GenerationConfig(**cfg_kwargs)
        assert cfg.accent_strength == "auto"

    @pytest.mark.parametrize("value", ["auto", "subtle", "strong"])
    def test_accepts_valid_values(self, cfg_kwargs, value):
        from src.generator.models import GenerationConfig
        cfg = GenerationConfig(accent_strength=value, **cfg_kwargs)
        assert cfg.accent_strength == value

    def test_rejects_unknown_value(self, cfg_kwargs):
        from src.generator.models import GenerationConfig
        with pytest.raises(ValueError, match="accent_strength"):
            GenerationConfig(accent_strength="wild", **cfg_kwargs)


class TestExistingValidationUnchanged:
    def test_invalid_curves_mode_still_raises(self, cfg_kwargs):
        from src.generator.models import GenerationConfig
        with pytest.raises(ValueError, match="curves_mode"):
            GenerationConfig(curves_mode="rainbow", **cfg_kwargs)
