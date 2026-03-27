"""Tests for src/themes/library.py — load, get, query by tags."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.themes.library import ThemeLibrary, load_theme_library
from src.themes.models import Theme

THEMES_FIXTURE = Path(__file__).parent.parent / "fixtures" / "themes" / "minimal_themes.json"
EFFECTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library.json"


@pytest.fixture
def effect_lib():
    return load_effect_library(builtin_path=EFFECTS_FIXTURE)


class TestLoadThemeLibrary:
    def test_loads_minimal_fixture(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        assert isinstance(lib, ThemeLibrary)

    def test_fixture_has_expected_themes(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        assert len(lib.themes) == 3

    def test_themes_are_theme_objects(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        for t in lib.themes.values():
            assert isinstance(t, Theme)

    def test_layers_deserialized(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        t = lib.themes["Test Aggressive"]
        assert len(t.layers) >= 1
        assert t.layers[0].effect == "Fire"

    def test_missing_file_raises(self, effect_lib):
        with pytest.raises(FileNotFoundError):
            load_theme_library(builtin_path=Path("/nonexistent.json"), effect_library=effect_lib)

    def test_schema_version_stored(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        assert lib.schema_version == "1.0.0"


class TestGet:
    def test_get_existing(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        t = lib.get("Test Aggressive")
        assert t is not None
        assert t.name == "Test Aggressive"

    def test_get_case_insensitive(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        assert lib.get("test aggressive") is not None
        assert lib.get("TEST AGGRESSIVE") is not None

    def test_get_nonexistent(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        assert lib.get("NoSuchTheme") is None


class TestByMood:
    def test_by_mood(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        ethereal = lib.by_mood("ethereal")
        assert len(ethereal) == 2  # Test Ethereal + Test Christmas
        for t in ethereal:
            assert t.mood == "ethereal"

    def test_by_mood_aggressive(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        agg = lib.by_mood("aggressive")
        assert len(agg) == 1
        assert agg[0].name == "Test Aggressive"

    def test_by_mood_empty(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        assert lib.by_mood("dark") == []


class TestByOccasion:
    def test_by_occasion_christmas(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        xmas = lib.by_occasion("christmas")
        assert len(xmas) == 1
        assert xmas[0].name == "Test Christmas"

    def test_by_occasion_general(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        gen = lib.by_occasion("general")
        assert len(gen) == 2


class TestByGenre:
    def test_by_genre_rock(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        rock = lib.by_genre("rock")
        # Test Aggressive (rock) + Test Ethereal (any) + Test Christmas is pop, not rock
        names = {t.name for t in rock}
        assert "Test Aggressive" in names
        assert "Test Ethereal" in names  # tagged "any"

    def test_by_genre_includes_any(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        classical = lib.by_genre("classical")
        # Only Test Ethereal (any)
        assert any(t.genre == "any" for t in classical)


class TestQuery:
    def test_combined_mood_and_occasion(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        result = lib.query(mood="ethereal", occasion="christmas")
        assert len(result) == 1
        assert result[0].name == "Test Christmas"

    def test_combined_mood_and_genre(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        result = lib.query(mood="aggressive", genre="rock")
        assert len(result) == 1
        assert result[0].name == "Test Aggressive"

    def test_no_filters_returns_all(self, effect_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)
        result = lib.query()
        assert len(result) == 3


class TestCustomOverrides:
    def test_custom_overrides_builtin(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom_data = {
                "name": "Test Aggressive",
                "mood": "aggressive",
                "occasion": "general",
                "genre": "rock",
                "intent": "CUSTOM override",
                "layers": [{"effect": "Fire", "blend_mode": "Normal", "parameter_overrides": {}}],
                "palette": ["#0000FF", "#4400FF"],
            }
            (custom_dir / "Test Aggressive.json").write_text(json.dumps(custom_data))
            lib = load_theme_library(
                builtin_path=THEMES_FIXTURE, effect_library=effect_lib, custom_dir=custom_dir,
            )
            t = lib.get("Test Aggressive")
            assert t.intent == "CUSTOM override"

    def test_invalid_custom_skipped(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "Bad.json").write_text('{"name": "Bad"}')
            lib = load_theme_library(
                builtin_path=THEMES_FIXTURE, effect_library=effect_lib, custom_dir=custom_dir,
            )
            assert len(lib.themes) >= 3

    def test_missing_custom_dir_no_error(self, effect_lib):
        lib = load_theme_library(
            builtin_path=THEMES_FIXTURE, effect_library=effect_lib,
            custom_dir=Path("/nonexistent/custom"),
        )
        assert len(lib.themes) == 3

    def test_new_custom_theme_added(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom_data = {
                "name": "Brand New",
                "mood": "dark",
                "occasion": "halloween",
                "genre": "any",
                "intent": "New custom theme",
                "layers": [{"effect": "Fire", "blend_mode": "Normal", "parameter_overrides": {}}],
                "palette": ["#800080", "#000000"],
            }
            (custom_dir / "Brand New.json").write_text(json.dumps(custom_data))
            lib = load_theme_library(
                builtin_path=THEMES_FIXTURE, effect_library=effect_lib, custom_dir=custom_dir,
            )
            assert lib.get("Brand New") is not None
            assert len(lib.themes) == 4
