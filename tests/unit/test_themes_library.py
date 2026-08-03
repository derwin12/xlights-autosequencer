"""Tests for src/themes/library.py — load, get, query by tags."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.themes.library import ThemeLibrary, heal_custom_theme_data, load_theme_library
from src.themes.models import Theme
from src.variants.library import load_variant_library

THEMES_FIXTURE = Path(__file__).parent.parent / "fixtures" / "themes" / "minimal_themes.json"
EFFECTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library_with_meteors.json"
VARIANTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "variants" / "builtin_variants_minimal.json"


@pytest.fixture
def effect_lib():
    return load_effect_library(builtin_path=EFFECTS_FIXTURE)


@pytest.fixture
def variant_lib(effect_lib):
    return load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_lib)


class TestLoadThemeLibrary:
    def test_loads_minimal_fixture(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        assert isinstance(lib, ThemeLibrary)

    def test_fixture_has_expected_themes(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        assert len(lib.themes) == 3

    def test_themes_are_theme_objects(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        for t in lib.themes.values():
            assert isinstance(t, Theme)

    def test_layers_deserialized(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        t = lib.themes["Test Aggressive"]
        assert len(t.layers) >= 1
        assert t.layers[0].variant == "Fire Blaze High"

    def test_missing_file_raises(self, effect_lib, variant_lib):
        with pytest.raises(FileNotFoundError):
            load_theme_library(builtin_path=Path("/nonexistent.json"), effect_library=effect_lib, variant_library=variant_lib)

    def test_schema_version_stored(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        assert lib.schema_version == "1.0.0"


class TestGet:
    def test_get_existing(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        t = lib.get("Test Aggressive")
        assert t is not None
        assert t.name == "Test Aggressive"

    def test_get_case_insensitive(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        assert lib.get("test aggressive") is not None
        assert lib.get("TEST AGGRESSIVE") is not None

    def test_get_nonexistent(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        assert lib.get("NoSuchTheme") is None


class TestByMood:
    def test_by_mood(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        ethereal = lib.by_mood("ethereal")
        assert len(ethereal) == 2  # Test Ethereal + Test Christmas
        for t in ethereal:
            assert t.mood == "ethereal"

    def test_by_mood_aggressive(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        agg = lib.by_mood("aggressive")
        assert len(agg) == 1
        assert agg[0].name == "Test Aggressive"

    def test_by_mood_empty(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        assert lib.by_mood("dark") == []


class TestByOccasion:
    def test_by_occasion_christmas(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        xmas = lib.by_occasion("christmas")
        assert len(xmas) == 1
        assert xmas[0].name == "Test Christmas"

    def test_by_occasion_general(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        gen = lib.by_occasion("general")
        assert len(gen) == 2


class TestByGenre:
    def test_by_genre_rock(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        rock = lib.by_genre("rock")
        # Test Aggressive (rock) + Test Ethereal (any) + Test Christmas is pop, not rock
        names = {t.name for t in rock}
        assert "Test Aggressive" in names
        assert "Test Ethereal" in names  # tagged "any"

    def test_by_genre_includes_any(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        classical = lib.by_genre("classical")
        # Only Test Ethereal (any)
        assert any(t.genre == "any" for t in classical)


class TestQuery:
    def test_combined_mood_and_occasion(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        result = lib.query(mood="ethereal", occasion="christmas")
        assert len(result) == 1
        assert result[0].name == "Test Christmas"

    def test_combined_mood_and_genre(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        result = lib.query(mood="aggressive", genre="rock")
        assert len(result) == 1
        assert result[0].name == "Test Aggressive"

    def test_no_filters_returns_all(self, effect_lib, variant_lib):
        lib = load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib)
        result = lib.query()
        assert len(result) == 3


class TestCustomOverrides:
    def test_custom_overrides_builtin(self, effect_lib, variant_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom_data = {
                "name": "Test Aggressive",
                "mood": "aggressive",
                "occasion": "general",
                "genre": "rock",
                "intent": "CUSTOM override",
                "layers": [{"variant": "Fire Blaze High", "blend_mode": "Normal"}],
                "palette": ["#0000FF", "#4400FF"],
            }
            (custom_dir / "Test Aggressive.json").write_text(json.dumps(custom_data))
            lib = load_theme_library(
                builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib, custom_dir=custom_dir,
            )
            t = lib.get("Test Aggressive")
            assert t.intent == "CUSTOM override"

    def test_invalid_custom_skipped(self, effect_lib, variant_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "Bad.json").write_text('{"name": "Bad"}')
            lib = load_theme_library(
                builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib, custom_dir=custom_dir,
            )
            assert len(lib.themes) >= 3

    def test_missing_custom_dir_no_error(self, effect_lib, variant_lib):
        lib = load_theme_library(
            builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib,
            custom_dir=Path("/nonexistent/custom"),
        )
        assert len(lib.themes) == 3

    def test_new_custom_theme_added(self, effect_lib, variant_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom_data = {
                "name": "Brand New",
                "mood": "dark",
                "occasion": "halloween",
                "genre": "any",
                "intent": "New custom theme",
                "layers": [{"variant": "Fire Blaze High", "blend_mode": "Normal"}],
                "palette": ["#800080", "#000000"],
            }
            (custom_dir / "Brand New.json").write_text(json.dumps(custom_data))
            lib = load_theme_library(
                builtin_path=THEMES_FIXTURE, effect_library=effect_lib, variant_library=variant_lib, custom_dir=custom_dir,
            )
            assert lib.get("Brand New") is not None
            assert len(lib.themes) == 4


# ── T006: variant_library required ───────────────────────────────────────────
# These tests FAIL against the current implementation because load_theme_library
# currently accepts variant_library=None without complaint.  After the
# theme-variant-separation refactor, passing None (or omitting the argument)
# must raise TypeError or ValueError so callers are forced to provide a real
# VariantLibrary.


class TestVariantLibraryRequired:
    def test_load_theme_library_requires_variant_library(self, effect_lib):
        """load_theme_library() without variant_library must raise TypeError or ValueError.

        FAILS NOW: current signature has variant_library=None (optional).
        PASSES AFTER: refactor makes variant_library a required positional arg
        or adds an explicit None-check that raises.
        """
        with pytest.raises((TypeError, ValueError)):
            load_theme_library(builtin_path=THEMES_FIXTURE, effect_library=effect_lib)

    def test_load_theme_library_fails_if_variant_library_none(self, effect_lib):
        """load_theme_library(variant_library=None) must raise TypeError or ValueError.

        FAILS NOW: current code treats None as 'skip variant validation' and
        succeeds silently.
        PASSES AFTER: refactor rejects None explicitly.
        """
        with pytest.raises((TypeError, ValueError)):
            load_theme_library(
                builtin_path=THEMES_FIXTURE,
                effect_library=effect_lib,
                variant_library=None,
            )


class TestLayersLessCustomThemeBackfill:
    """A custom theme saved with no `layers` (the review UI's palette-only
    New Theme/Edit dialog has no layer/effect picker) used to fail
    validate_theme() ("Theme must have at least one layer") and get silently
    dropped from the catalog entirely (user report 2026-08-03: assigned a
    theme to a section, the exported .xsq showed the auto-selected theme
    instead of the one actually chosen). DEFAULT_THEME_LAYERS's "Color Wash
    Smooth" is a real built-in variant, so these use the real production
    effect/variant libraries (not the minimal test fixtures) to confirm it
    actually resolves against the real catalog, not just a mocked one."""

    @pytest.fixture(scope="class")
    @classmethod
    def real_effect_lib(cls):
        return load_effect_library()

    @pytest.fixture(scope="class")
    @classmethod
    def real_variant_lib(cls, real_effect_lib):
        return load_variant_library(effect_library=real_effect_lib)

    def test_empty_layers_list_is_backfilled_and_included(self, real_effect_lib, real_variant_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "test2.json").write_text(json.dumps({
                "name": "test2", "mood": "structural", "occasion": "general",
                "genre": "any", "intent": "", "palette": ["#1E1B4B", "#7DD3FC"],
                "accent_palette": [], "layers": [],
            }))
            lib = load_theme_library(
                effect_library=real_effect_lib, variant_library=real_variant_lib, custom_dir=custom_dir,
            )
            t = lib.get("test2")
            assert t is not None
            assert len(t.layers) == 1
            assert t.layers[0].variant == "Color Wash Smooth"

    def test_missing_layers_key_is_backfilled_and_included(self, real_effect_lib, real_variant_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "no-layers-key.json").write_text(json.dumps({
                "name": "No Layers Key", "mood": "structural", "occasion": "general",
                "genre": "any", "intent": "", "palette": ["#FFFFFF", "#000000"],
            }))
            lib = load_theme_library(
                effect_library=real_effect_lib, variant_library=real_variant_lib, custom_dir=custom_dir,
            )
            assert lib.get("No Layers Key") is not None

    def test_real_layers_are_left_untouched(self, real_effect_lib, real_variant_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "has-layers.json").write_text(json.dumps({
                "name": "Has Layers", "mood": "structural", "occasion": "general",
                "genre": "any", "intent": "", "palette": ["#FFFFFF", "#000000"],
                "layers": [{"variant": "Fire Tall", "blend_mode": "Normal"}],
            }))
            lib = load_theme_library(
                effect_library=real_effect_lib, variant_library=real_variant_lib, custom_dir=custom_dir,
            )
            t = lib.get("Has Layers")
            assert t is not None
            assert t.layers[0].variant == "Fire Tall"


class TestHealCustomThemeData:
    """Fixups load_theme_library() applies to every custom theme before
    validation -- see the function's own docstring for the three real
    failure modes this was built from (found 2026-08-03 investigating a
    single real user theme that hit all three simultaneously)."""

    def test_no_layers_key_gets_default(self):
        healed = heal_custom_theme_data({"name": "X"})
        assert healed["layers"] == [
            {"variant": "Color Wash Smooth", "blend_mode": "Normal", "effect_pool": [], "stem": None},
        ]

    def test_empty_layers_list_gets_default(self):
        healed = heal_custom_theme_data({"name": "X", "layers": []})
        assert len(healed["layers"]) == 1

    def test_real_layers_are_untouched(self):
        original = [{"variant": "Fire Tall", "blend_mode": "Normal"}]
        healed = heal_custom_theme_data({"name": "X", "layers": original})
        assert healed["layers"] is original

    def test_wrong_case_genre_is_lowercased(self):
        healed = heal_custom_theme_data({"name": "X", "genre": "Rock"})
        assert healed["genre"] == "rock"

    def test_unrecognized_genre_falls_back_to_any(self):
        healed = heal_custom_theme_data({"name": "X", "genre": "Country"})
        assert healed["genre"] == "any"

    def test_missing_genre_is_left_absent(self):
        # Missing entirely is a validate_theme concern (defaults to "any"
        # per _theme_to_api elsewhere) -- this only fixes up a genre that
        # IS present but in the wrong form.
        healed = heal_custom_theme_data({"name": "X"})
        assert "genre" not in healed

    def test_valid_lowercase_genre_is_untouched(self):
        healed = heal_custom_theme_data({"name": "X", "genre": "pop"})
        assert healed["genre"] == "pop"

    def test_single_accent_color_is_dropped(self):
        healed = heal_custom_theme_data({"name": "X", "accent_palette": ["#FF4500"]})
        assert healed["accent_palette"] == []

    def test_two_or_more_accent_colors_are_untouched(self):
        original = ["#FF4500", "#00FF00"]
        healed = heal_custom_theme_data({"name": "X", "accent_palette": original})
        assert healed["accent_palette"] is original

    def test_empty_accent_palette_is_untouched(self):
        healed = heal_custom_theme_data({"name": "X", "accent_palette": []})
        assert healed["accent_palette"] == []

    def test_missing_accent_palette_is_left_absent(self):
        healed = heal_custom_theme_data({"name": "X"})
        assert "accent_palette" not in healed

    def test_original_dict_is_not_mutated(self):
        original = {"name": "X", "genre": "Rock", "accent_palette": ["#FF4500"]}
        heal_custom_theme_data(original)
        assert original == {"name": "X", "genre": "Rock", "accent_palette": ["#FF4500"]}

    def test_the_real_user_theme_that_prompted_this_heals_cleanly(self):
        # Dream On/Aerosmith investigation, 2026-08-03: a real custom theme
        # hit all three healable problems simultaneously.
        healed = heal_custom_theme_data({
            "name": "Aerosmith DreamOn", "mood": "structural", "occasion": "general",
            "genre": "Rock", "intent": "From the AI pull",
            "palette": ["#0D1B2A", "#1B263B", "#22333B", "#415A77"],
            "accent_palette": ["#FF4500"],
            "layers": [],
        })
        assert healed["genre"] == "rock"
        assert healed["accent_palette"] == []
        assert len(healed["layers"]) == 1


class TestThemeIdSurvivesRename:
    """A custom theme's theme_id must stay pinned to its file's stable
    identity (filename stem, fixed at creation) even after the theme's
    display .name is edited -- otherwise plan.py's override resolution
    (keyed by theme_id) silently orphans every existing section assignment
    that references the theme by its original id (bug found 2026-08-03:
    renamed a theme created as "test2" to "Aerosmith DreamOn"; assignments
    still stored theme_id="test2", but the theme's own identity used to be
    re-derived from its current .name, which no longer matched)."""

    @pytest.fixture(scope="class")
    @classmethod
    def real_effect_lib(cls):
        return load_effect_library()

    @pytest.fixture(scope="class")
    @classmethod
    def real_variant_lib(cls, real_effect_lib):
        return load_variant_library(effect_library=real_effect_lib)

    def test_custom_theme_id_is_the_filename_stem_not_a_slug_of_current_name(
        self, real_effect_lib, real_variant_lib,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            # Filename stem ("test2") deliberately does not match what
            # slugifying the current .name would produce.
            (custom_dir / "test2.json").write_text(json.dumps({
                "name": "Aerosmith DreamOn", "mood": "structural", "occasion": "general",
                "genre": "rock", "intent": "", "palette": ["#0D1B2A", "#1B263B"],
                "layers": [{"variant": "Fire Tall", "blend_mode": "Normal"}],
            }))
            lib = load_theme_library(
                effect_library=real_effect_lib, variant_library=real_variant_lib, custom_dir=custom_dir,
            )
            t = lib.get("Aerosmith DreamOn")
            assert t is not None
            assert t.theme_id == "test2"

    def test_builtin_theme_id_is_slug_of_its_catalog_name(self, real_effect_lib, real_variant_lib):
        lib = load_theme_library(effect_library=real_effect_lib, variant_library=real_variant_lib)
        # Any real built-in theme works here -- confirms theme_id is set
        # for the built-in path too, not just custom.
        t = next(iter(lib.themes.values()))
        assert t.theme_id
        assert t.theme_id == t.theme_id.lower()
