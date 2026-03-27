"""Integration tests for the full themes pipeline."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.themes.library import ThemeLibrary, load_theme_library
from src.themes.models import Theme

BUILTIN_THEMES = Path(__file__).parent.parent.parent / "src" / "themes" / "builtin_themes.json"
BUILTIN_EFFECTS = Path(__file__).parent.parent.parent / "src" / "effects" / "builtin_effects.json"


@pytest.fixture
def effect_lib():
    return load_effect_library(builtin_path=BUILTIN_EFFECTS)


@pytest.fixture
def library(effect_lib):
    return load_theme_library(builtin_path=BUILTIN_THEMES, effect_library=effect_lib)


class TestBuiltinCatalog:
    def test_loads_without_errors(self, library):
        assert isinstance(library, ThemeLibrary)

    def test_sc001_at_least_20_themes(self, library):
        assert len(library.themes) >= 20, f"Got {len(library.themes)} themes"

    def test_sc001_4_mood_collections_with_3_each(self, library):
        for mood in ("ethereal", "aggressive", "dark", "structural"):
            themes = library.by_mood(mood)
            assert len(themes) >= 3, f"Mood '{mood}' has only {len(themes)} themes (need 3+)"

    def test_sc001_christmas_themes(self, library):
        xmas = library.by_occasion("christmas")
        assert len(xmas) >= 4, f"Got {len(xmas)} Christmas themes (need 4+)"

    def test_sc001_halloween_themes(self, library):
        halloween = library.by_occasion("halloween")
        assert len(halloween) >= 2, f"Got {len(halloween)} Halloween themes (need 2+)"

    def test_sc002_all_effect_refs_valid(self, library, effect_lib):
        for name, theme in library.themes.items():
            for i, layer in enumerate(theme.layers):
                assert effect_lib.get(layer.effect) is not None, (
                    f"Theme '{name}' layer {i}: effect '{layer.effect}' not in effect library"
                )

    def test_sc003_loads_under_1_second(self, effect_lib):
        start = time.monotonic()
        load_theme_library(builtin_path=BUILTIN_THEMES, effect_library=effect_lib)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Load took {elapsed:.2f}s"

    def test_all_themes_are_valid(self, library):
        for name, theme in library.themes.items():
            assert isinstance(theme, Theme)
            assert theme.name == name
            assert theme.mood in ("ethereal", "aggressive", "dark", "structural")
            assert theme.occasion in ("christmas", "halloween", "general")
            assert theme.genre in ("rock", "pop", "classical", "any")
            assert len(theme.layers) >= 1
            assert len(theme.palette) >= 2

    def test_bottom_layers_all_normal(self, library):
        for name, theme in library.themes.items():
            assert theme.layers[0].blend_mode == "Normal", (
                f"Theme '{name}' bottom layer blend_mode is '{theme.layers[0].blend_mode}'"
            )

    def test_sc006_christmas_palettes_appropriate(self, library):
        xmas = library.by_occasion("christmas")
        for theme in xmas:
            assert len(theme.palette) >= 2, f"Christmas theme '{theme.name}' needs 2+ colors"

    def test_sc006_halloween_palettes_appropriate(self, library):
        halloween = library.by_occasion("halloween")
        for theme in halloween:
            assert len(theme.palette) >= 2, f"Halloween theme '{theme.name}' needs 2+ colors"


class TestQueryIntegration:
    def test_sc004_mood_query(self, library):
        for mood in ("ethereal", "aggressive", "dark", "structural"):
            results = library.by_mood(mood)
            for t in results:
                assert t.mood == mood

    def test_sc004_occasion_query(self, library):
        for occasion in ("christmas", "halloween", "general"):
            results = library.by_occasion(occasion)
            for t in results:
                assert t.occasion == occasion

    def test_sc004_combined_query(self, library):
        results = library.query(mood="aggressive", occasion="general")
        for t in results:
            assert t.mood == "aggressive"
            assert t.occasion == "general"


class TestCustomOverrideIntegration:
    def test_sc005_custom_override(self, library, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            # Get first theme and modify it
            first_name = next(iter(library.themes))
            first = library.themes[first_name]
            custom_data = {
                "name": first_name,
                "mood": first.mood,
                "occasion": first.occasion,
                "genre": first.genre,
                "intent": "CUSTOM OVERRIDE",
                "layers": [
                    {"effect": l.effect, "blend_mode": l.blend_mode,
                     "parameter_overrides": l.parameter_overrides}
                    for l in first.layers
                ],
                "palette": first.palette,
            }
            (custom_dir / f"{first_name}.json").write_text(json.dumps(custom_data))
            custom_lib = load_theme_library(
                builtin_path=BUILTIN_THEMES, effect_library=effect_lib, custom_dir=custom_dir,
            )
            assert custom_lib.get(first_name).intent == "CUSTOM OVERRIDE"

    def test_invalid_custom_does_not_break(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "Broken.json").write_text("{{{not json")
            lib = load_theme_library(
                builtin_path=BUILTIN_THEMES, effect_library=effect_lib, custom_dir=custom_dir,
            )
            assert len(lib.themes) >= 20
