"""Integration tests for the full effect library pipeline."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from src.effects.library import EffectLibrary, load_effect_library
from src.effects.models import ALL_XLIGHTS_EFFECTS, EffectDefinition

BUILTIN_PATH = Path(__file__).parent.parent.parent / "src" / "effects" / "builtin_effects.json"


@pytest.fixture
def library() -> EffectLibrary:
    return load_effect_library(builtin_path=BUILTIN_PATH)


class TestBuiltinCatalog:
    def test_loads_without_errors(self, library):
        assert isinstance(library, EffectLibrary)

    def test_sc001_at_least_35_effects(self, library):
        """SC-001: At least 35 effect definitions."""
        assert len(library.effects) >= 35, (
            f"Expected >=35 effects, got {len(library.effects)}"
        )

    def test_sc002_at_least_3_params_each(self, library):
        """SC-002: Every effect has at least 3 parameters."""
        for name, defn in library.effects.items():
            assert len(defn.parameters) >= 3, (
                f"Effect '{name}' has only {len(defn.parameters)} parameters (need >=3)"
            )

    def test_sc003_at_least_20_with_mappings(self, library):
        """SC-003: At least 20 effects have analysis mappings."""
        with_mappings = sum(
            1 for defn in library.effects.values()
            if len(defn.analysis_mappings) > 0
        )
        assert with_mappings >= 20, (
            f"Only {with_mappings} effects have analysis mappings (need >=20)"
        )

    def test_sc004_all_6_suitability_ratings(self, library):
        """SC-004: Every effect has suitability ratings for all 6 prop types."""
        expected_keys = {"matrix", "outline", "arch", "vertical", "tree", "radial"}
        for name, defn in library.effects.items():
            actual_keys = set(defn.prop_suitability.keys())
            assert actual_keys == expected_keys, (
                f"Effect '{name}' missing suitability keys: {expected_keys - actual_keys}"
            )

    def test_sc005_loads_under_1_second(self):
        """SC-005: Library loads and validates in under 1 second."""
        start = time.monotonic()
        load_effect_library(builtin_path=BUILTIN_PATH)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Library load took {elapsed:.2f}s (limit: 1s)"

    def test_sc006_lookup_by_name(self, library):
        """SC-006: Can look up effect and read parameters in one call."""
        fire = library.get("Fire")
        assert fire is not None
        assert len(fire.parameters) >= 3

    def test_all_definitions_are_valid(self, library):
        for name, defn in library.effects.items():
            assert isinstance(defn, EffectDefinition)
            assert defn.name == name
            assert defn.category in (
                "color_wash", "pattern", "nature", "movement",
                "audio_reactive", "media", "utility",
            )

    def test_analysis_mappings_reference_valid_parameters(self, library):
        for name, defn in library.effects.items():
            param_names = {p.name for p in defn.parameters}
            for mapping in defn.analysis_mappings:
                assert mapping.parameter in param_names, (
                    f"Effect '{name}': mapping references unknown param '{mapping.parameter}'"
                )


class TestCustomOverrideIntegration:
    def test_custom_override_round_trip(self, library):
        """Place a custom effect, load library, verify override."""
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            # Export Fire's data and modify it
            fire = library.get("Fire")
            assert fire is not None
            custom_data = {
                "name": "Fire",
                "xlights_id": fire.xlights_id,
                "category": fire.category,
                "description": "CUSTOM: Modified fire",
                "intent": fire.intent,
                "parameters": [
                    {
                        "name": p.name,
                        "storage_name": p.storage_name,
                        "widget_type": p.widget_type,
                        "value_type": p.value_type,
                        "default": p.default,
                        "min": p.min,
                        "max": p.max,
                        "choices": p.choices,
                        "description": p.description,
                        "supports_value_curve": p.supports_value_curve,
                    }
                    for p in fire.parameters
                ],
                "prop_suitability": fire.prop_suitability,
                "analysis_mappings": [
                    {
                        "parameter": m.parameter,
                        "analysis_level": m.analysis_level,
                        "analysis_field": m.analysis_field,
                        "mapping_type": m.mapping_type,
                        "description": m.description,
                    }
                    for m in fire.analysis_mappings
                ],
            }
            (custom_dir / "Fire.json").write_text(json.dumps(custom_data))

            custom_lib = load_effect_library(
                builtin_path=BUILTIN_PATH,
                custom_dir=custom_dir,
            )
            custom_fire = custom_lib.get("Fire")
            assert custom_fire.description == "CUSTOM: Modified fire"

    def test_invalid_custom_does_not_break_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "Broken.json").write_text("not valid json at all {{{")

            lib = load_effect_library(
                builtin_path=BUILTIN_PATH,
                custom_dir=custom_dir,
            )
            assert len(lib.effects) >= 35  # built-in still loads


class TestCoverageIntegration:
    def test_coverage_reports_correct_totals(self, library):
        cov = library.coverage()
        assert cov.total_xlights == 56
        assert len(cov.cataloged) >= 35
        assert len(cov.cataloged) + len(cov.uncatalogued) == 56

    def test_sc007_at_least_30_xlights_effects_covered(self, library):
        """SC-007: At least 30 of 56 xLights effects used."""
        cov = library.coverage()
        assert len(cov.cataloged) >= 30
