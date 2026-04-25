"""Tests for src/variants/library.py — VariantLibrary, load/query/save/delete."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.variants.library import VariantLibrary, load_variant_library
from src.variants.models import EffectVariant, VariantTags

FIXTURES = Path(__file__).parent.parent / "fixtures"
EFFECTS_FIXTURES = FIXTURES / "effects"
VARIANT_FIXTURES = FIXTURES / "variants"


@pytest.fixture
def effect_lib():
    return load_effect_library(builtin_path=EFFECTS_FIXTURES / "minimal_library_with_meteors.json")


@pytest.fixture
def isolated_custom_dir(tmp_path):
    """Empty custom-variants dir, so tests don't pick up the user's
    ~/.xlight/custom_variants/ contents (which would inflate counts and
    add unexpected variant names)."""
    d = tmp_path / "no_custom_variants"
    # Don't create it — load_variant_library treats a missing dir as "no
    # custom overrides" per its docstring.
    return d


@pytest.fixture
def variant_lib(effect_lib, isolated_custom_dir):
    return load_variant_library(
        builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
        custom_dir=isolated_custom_dir,
        effect_library=effect_lib,
    )


class TestLoadVariantLibrary:
    def test_loads_from_fixture(self, effect_lib, isolated_custom_dir):
        lib = load_variant_library(
            builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
            custom_dir=isolated_custom_dir,
            effect_library=effect_lib,
        )
        assert isinstance(lib, VariantLibrary)

    def test_has_expected_variants(self, variant_lib):
        assert len(variant_lib.variants) == 3
        assert "Fire Blaze High" in variant_lib.variants
        assert "Bars Sweep Left" in variant_lib.variants
        assert "Meteors Gentle Rain" in variant_lib.variants

    def test_variants_are_effect_variant_instances(self, variant_lib):
        for v in variant_lib.variants.values():
            assert isinstance(v, EffectVariant)

    def test_schema_version_stored(self, variant_lib):
        assert variant_lib.schema_version == "1.0.0"

    def test_missing_file_raises(self, effect_lib):
        with pytest.raises(FileNotFoundError):
            load_variant_library(
                builtin_path=Path("/nonexistent/variants.json"),
                effect_library=effect_lib,
            )

    def test_custom_dir_no_error_if_missing(self, effect_lib):
        lib = load_variant_library(
            builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
            custom_dir=Path("/nonexistent/custom_dir"),
            effect_library=effect_lib,
        )
        assert len(lib.variants) == 3

    def test_custom_overrides_builtin(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom = {
                "name": "Fire Blaze High",
                "base_effect": "Fire",
                "description": "Custom override of fire variant",
                "parameter_overrides": {"E_SLIDER_Fire_Height": 99},
                "tags": {},
            }
            (custom_dir / "fire-blaze-high.json").write_text(json.dumps(custom))

            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            v = lib.get("Fire Blaze High")
            assert v is not None
            assert v.description == "Custom override of fire variant"
            assert v.parameter_overrides["E_SLIDER_Fire_Height"] == 99

    def test_custom_adds_new_variant(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom = {
                "name": "Bars Fast Right",
                "base_effect": "Bars",
                "description": "Fast bars sweeping right",
                "parameter_overrides": {"E_CHOICE_Bars_Direction": "Right"},
                "tags": {},
            }
            (custom_dir / "bars-fast-right.json").write_text(json.dumps(custom))

            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            assert len(lib.variants) == 4
            assert lib.get("Bars Fast Right") is not None

    def test_invalid_custom_skipped(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "bad.json").write_text('{"name": "Bad"}')

            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            assert len(lib.variants) == 3  # built-in still loads


class TestGet:
    def test_get_existing(self, variant_lib):
        v = variant_lib.get("Fire Blaze High")
        assert v is not None
        assert v.name == "Fire Blaze High"

    def test_get_case_insensitive(self, variant_lib):
        assert variant_lib.get("fire blaze high") is not None
        assert variant_lib.get("FIRE BLAZE HIGH") is not None

    def test_get_nonexistent_returns_none(self, variant_lib):
        assert variant_lib.get("No Such Variant") is None


class TestQuery:
    def test_query_all_returns_all(self, variant_lib):
        results = variant_lib.query()
        assert len(results) == 3

    def test_query_by_base_effect(self, variant_lib):
        results = variant_lib.query(base_effect="Meteors")
        assert len(results) == 1
        assert results[0].base_effect == "Meteors"

    def test_query_base_effect_case_insensitive(self, variant_lib):
        results_lower = variant_lib.query(base_effect="meteors")
        results_upper = variant_lib.query(base_effect="METEORS")
        assert len(results_lower) == 1
        assert len(results_upper) == 1

    def test_query_by_energy_level(self, variant_lib):
        results = variant_lib.query(energy_level="high")
        assert len(results) == 1
        assert results[0].tags.energy_level == "high"

    def test_query_by_tier_affinity(self, variant_lib):
        results = variant_lib.query(tier_affinity="background")
        assert len(results) == 1
        assert results[0].tags.tier_affinity == "background"

    def test_query_by_scope(self, variant_lib):
        results = variant_lib.query(scope="single-prop")
        assert len(results) == 1
        assert results[0].tags.scope == "single-prop"

    def test_query_by_section_role(self, variant_lib):
        results = variant_lib.query(section_role="chorus")
        # Fire Blaze High and Bars Sweep Left both have chorus
        assert len(results) == 2

    def test_query_combined_filters(self, variant_lib):
        results = variant_lib.query(base_effect="Bars", energy_level="medium")
        assert len(results) == 1
        assert results[0].name == "Bars Sweep Left"

    def test_query_no_match_returns_empty(self, variant_lib):
        results = variant_lib.query(energy_level="low", tier_affinity="hero")
        assert results == []


class TestSaveCustomVariant:
    def test_save_creates_file(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            variant = EffectVariant(
                name="My Custom Variant",
                base_effect="Fire",
                description="Custom test",
                parameter_overrides={"E_SLIDER_Fire_Height": 60},
                tags=VariantTags(),
            )
            saved_path = lib.save_custom_variant(variant, custom_dir)
            assert saved_path.exists()
            data = json.loads(saved_path.read_text())
            assert data["name"] == "My Custom Variant"

    def test_save_uses_slugified_name(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            variant = EffectVariant(
                name="Fire High & Mighty",
                base_effect="Fire",
                description="d",
                parameter_overrides={},
                tags=VariantTags(),
            )
            saved_path = lib.save_custom_variant(variant, custom_dir)
            assert saved_path.suffix == ".json"
            assert " " not in saved_path.name


class TestDeleteCustomVariant:
    def test_delete_removes_file(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            variant = EffectVariant(
                name="Temp Variant",
                base_effect="Fire",
                description="temp",
                parameter_overrides={},
                tags=VariantTags(),
            )
            saved_path = lib.save_custom_variant(variant, custom_dir)
            assert saved_path.exists()

            lib.delete_custom_variant("Temp Variant", custom_dir)
            assert not saved_path.exists()

    def test_delete_nonexistent_raises(self, effect_lib):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            with pytest.raises((FileNotFoundError, KeyError, ValueError)):
                lib.delete_custom_variant("No Such Variant", custom_dir)

    def test_delete_finds_non_slug_filename(self, effect_lib):
        """delete_custom_variant must find files not named by slug convention."""
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            lib = load_variant_library(
                builtin_path=VARIANT_FIXTURES / "builtin_variants_minimal.json",
                custom_dir=custom_dir,
                effect_library=effect_lib,
            )
            variant = EffectVariant(
                name="Special Fire",
                base_effect="Fire",
                description="non-slug test",
                parameter_overrides={},
                tags=VariantTags(),
            )
            # Write with a non-slug filename
            non_slug_file = custom_dir / "my-custom-thing.json"
            non_slug_file.write_text(json.dumps(variant.to_dict()), encoding="utf-8")
            lib.variants[variant.name] = variant

            lib.delete_custom_variant("Special Fire", custom_dir)
            assert not non_slug_file.exists()
            assert lib.get("Special Fire") is None
