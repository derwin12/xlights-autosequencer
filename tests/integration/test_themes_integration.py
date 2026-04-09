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
from src.variants.library import load_variant_library

BUILTIN_THEMES = Path(__file__).parent.parent.parent / "src" / "themes" / "builtin_themes.json"
BUILTIN_EFFECTS = Path(__file__).parent.parent.parent / "src" / "effects" / "builtin_effects.json"
BUILTIN_VARIANTS = Path(__file__).parent.parent.parent / "src" / "variants" / "builtins"
MINIMAL_THEMES = Path(__file__).parent.parent / "fixtures" / "themes" / "minimal_themes.json"
MINIMAL_EFFECTS = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library_with_meteors.json"
MINIMAL_VARIANTS = Path(__file__).parent.parent / "fixtures" / "variants" / "builtin_variants_minimal.json"


@pytest.fixture
def effect_lib():
    return load_effect_library(builtin_path=BUILTIN_EFFECTS)


@pytest.fixture
def variant_lib(effect_lib):
    return load_variant_library(builtin_dir=BUILTIN_VARIANTS, effect_library=effect_lib)


@pytest.fixture
def library(effect_lib, variant_lib):
    return load_theme_library(
        builtin_path=BUILTIN_THEMES, effect_library=effect_lib, variant_library=variant_lib
    )


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

    def test_sc002_all_variant_refs_valid(self, library, variant_lib):
        for name, theme in library.themes.items():
            for i, layer in enumerate(theme.layers):
                assert layer.variant in variant_lib.variants, (
                    f"Theme '{name}' layer {i}: variant '{layer.variant}' not in variant library"
                )

    def test_sc003_loads_under_1_second(self, effect_lib, variant_lib):
        start = time.monotonic()
        load_theme_library(builtin_path=BUILTIN_THEMES, effect_library=effect_lib, variant_library=variant_lib)
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
    def test_sc005_custom_override(self):
        """Custom theme overrides a builtin — verified using minimal fixtures (new format)."""
        min_effect_lib = load_effect_library(builtin_path=MINIMAL_EFFECTS)
        min_variant_lib = load_variant_library(
            builtin_path=MINIMAL_VARIANTS, effect_library=min_effect_lib
        )
        min_lib = load_theme_library(
            builtin_path=MINIMAL_THEMES, effect_library=min_effect_lib,
            variant_library=min_variant_lib,
        )
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            first_name = next(iter(min_lib.themes))
            first = min_lib.themes[first_name]
            custom_data = {
                "name": first_name,
                "mood": first.mood,
                "occasion": first.occasion,
                "genre": first.genre,
                "intent": "CUSTOM OVERRIDE",
                "layers": [
                    {"variant": l.variant, "blend_mode": l.blend_mode}
                    for l in first.layers
                ],
                "palette": first.palette,
            }
            (custom_dir / f"{first_name}.json").write_text(json.dumps(custom_data))
            custom_lib = load_theme_library(
                builtin_path=MINIMAL_THEMES, effect_library=min_effect_lib,
                variant_library=min_variant_lib, custom_dir=custom_dir,
            )
            assert custom_lib.get(first_name).intent == "CUSTOM OVERRIDE"

    def test_invalid_custom_does_not_break(self, effect_lib, variant_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "Broken.json").write_text("{{{not json")
            lib = load_theme_library(
                builtin_path=BUILTIN_THEMES, effect_library=effect_lib,
                variant_library=variant_lib, custom_dir=custom_dir,
            )
            assert isinstance(lib, ThemeLibrary)


# ---------------------------------------------------------------------------
# T021: Post-migration regression — resolved params must match pre-migration snapshot
# ---------------------------------------------------------------------------

PRE_MIGRATION_PARAMS = Path(__file__).parent.parent / "fixtures" / "themes" / "pre_migration_params.json"


class TestMigrationRegression:
    """Verify that after US2 migration, resolved variant parameters match
    the pre-migration parameter snapshot captured before the migration."""

    def test_resolved_params_match_pre_migration_snapshot(self, effect_lib, variant_lib):
        """Every theme layer's resolved params must exactly match the pre-migration snapshot."""
        snapshot = json.loads(PRE_MIGRATION_PARAMS.read_text())
        theme_lib = load_theme_library(
            builtin_path=BUILTIN_THEMES, effect_library=effect_lib, variant_library=variant_lib
        )

        mismatches = []
        for theme_name, layer_snapshots in snapshot["themes"].items():
            theme = theme_lib.themes.get(theme_name)
            if theme is None:
                mismatches.append(f"{theme_name}: theme not found in library")
                continue

            for key, expected in layer_snapshots.items():
                # Determine the layer source: primary.N or variant.V.N
                parts = key.split(".")
                if parts[0] == "primary":
                    idx = int(parts[1])
                    layers = theme.layers
                    source = "primary"
                else:
                    # variant.V.N -> alternates[V].layers[N]
                    v_idx = int(parts[1])
                    l_idx = int(parts[2])
                    if v_idx >= len(theme.alternates):
                        mismatches.append(
                            f"{theme_name}/{key}: alternate index {v_idx} out of range "
                            f"(only {len(theme.alternates)} alternates)"
                        )
                        continue
                    layers = theme.alternates[v_idx].layers
                    idx = l_idx
                    source = f"alternate[{v_idx}]"

                if idx >= len(layers):
                    mismatches.append(
                        f"{theme_name}/{key}: layer index {idx} out of range "
                        f"(only {len(layers)} layers in {source})"
                    )
                    continue

                layer = layers[idx]
                variant = variant_lib.variants.get(layer.variant)
                if variant is None:
                    mismatches.append(
                        f"{theme_name}/{key}: variant '{layer.variant}' not found in library"
                    )
                    continue

                actual_effect = variant.base_effect
                actual_params = variant.parameter_overrides or {}

                if actual_effect != expected["effect"]:
                    mismatches.append(
                        f"{theme_name}/{key}: effect mismatch — "
                        f"expected '{expected['effect']}', got '{actual_effect}'"
                    )

                expected_params = expected.get("params", {})
                if actual_params != expected_params:
                    mismatches.append(
                        f"{theme_name}/{key}: param mismatch — "
                        f"expected {expected_params}, got {actual_params}"
                    )

        assert not mismatches, (
            f"Post-migration parameter regression ({len(mismatches)} mismatches):\n"
            + "\n".join(f"  - {m}" for m in mismatches)
        )
