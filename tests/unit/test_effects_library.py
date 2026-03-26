"""Tests for src/effects/library.py — load, get, for_prop_type, coverage."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.effects.library import EffectLibrary, load_effect_library
from src.effects.models import CoverageResult, EffectDefinition

FIXTURES = Path(__file__).parent.parent / "fixtures" / "effects"


class TestLoadBuiltinLibrary:
    def test_loads_minimal_fixture(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        assert isinstance(lib, EffectLibrary)

    def test_fixture_has_expected_effects(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        assert len(lib.effects) == 3
        assert "Fire" in lib.effects
        assert "On" in lib.effects
        assert "Bars" in lib.effects

    def test_effects_are_effect_definitions(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        for defn in lib.effects.values():
            assert isinstance(defn, EffectDefinition)

    def test_parameters_deserialized(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        fire = lib.effects["Fire"]
        assert len(fire.parameters) >= 3
        assert fire.parameters[0].name == "Fire_Height"

    def test_analysis_mappings_deserialized(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        fire = lib.effects["Fire"]
        assert len(fire.analysis_mappings) >= 1
        assert fire.analysis_mappings[0].mapping_type == "direct"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_effect_library(builtin_path=Path("/nonexistent/library.json"))

    def test_schema_version_stored(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        assert lib.schema_version == "1.0.0"


class TestGet:
    def test_get_existing_effect(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        fire = lib.get("Fire")
        assert fire is not None
        assert fire.name == "Fire"

    def test_get_case_insensitive(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        assert lib.get("fire") is not None
        assert lib.get("FIRE") is not None
        assert lib.get("Fire") is not None

    def test_get_nonexistent_returns_none(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        assert lib.get("NonExistentEffect") is None


class TestForPropType:
    def test_returns_effects_rated_ideal_or_good(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        matrix_effects = lib.for_prop_type("matrix")
        for e in matrix_effects:
            assert e.prop_suitability["matrix"] in ("ideal", "good")

    def test_excludes_not_recommended(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        # All fixture effects are ideal/good for matrix
        matrix_effects = lib.for_prop_type("matrix")
        assert len(matrix_effects) == 3

    def test_invalid_prop_type_returns_empty(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        assert lib.for_prop_type("nonexistent") == []


class TestCoverage:
    def test_coverage_counts(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        cov = lib.coverage()
        assert isinstance(cov, CoverageResult)
        assert cov.total_xlights == 56
        assert len(cov.cataloged) == 3
        assert len(cov.uncatalogued) == 53

    def test_cataloged_names(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        cov = lib.coverage()
        assert "Fire" in cov.cataloged
        assert "On" in cov.cataloged

    def test_uncatalogued_names(self):
        lib = load_effect_library(builtin_path=FIXTURES / "minimal_library.json")
        cov = lib.coverage()
        assert "Meteors" in cov.uncatalogued
        assert "Spirals" in cov.uncatalogued


class TestCustomOverrides:
    def test_custom_overrides_builtin(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom_data = {
                "name": "Fire",
                "xlights_id": "eff_FIRE",
                "category": "nature",
                "description": "Custom fire",
                "intent": "Custom",
                "parameters": [
                    {"name": "Fire_Height", "storage_name": "E_SLIDER_Fire_Height",
                     "widget_type": "slider", "value_type": "int",
                     "default": 99, "min": 1, "max": 100, "description": "Custom height"},
                    {"name": "Fire_HueShift", "storage_name": "E_SLIDER_Fire_HueShift",
                     "widget_type": "slider", "value_type": "int",
                     "default": 0, "min": 0, "max": 100, "description": "Hue"},
                    {"name": "Fire_Location", "storage_name": "E_CHOICE_Fire_Location",
                     "widget_type": "choice", "value_type": "choice",
                     "default": "Bottom", "choices": ["Bottom", "Top"], "description": "Dir"},
                ],
                "prop_suitability": {"matrix": "ideal", "outline": "good", "arch": "good",
                                     "vertical": "good", "tree": "ideal", "radial": "good"},
                "analysis_mappings": [],
            }
            (custom_dir / "Fire.json").write_text(json.dumps(custom_data))

            lib = load_effect_library(
                builtin_path=FIXTURES / "minimal_library.json",
                custom_dir=custom_dir,
            )
            fire = lib.get("Fire")
            assert fire.description == "Custom fire"
            assert fire.parameters[0].default == 99

    def test_invalid_custom_skipped_with_warning(self, caplog):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            (custom_dir / "Bad.json").write_text('{"name": "Bad"}')

            lib = load_effect_library(
                builtin_path=FIXTURES / "minimal_library.json",
                custom_dir=custom_dir,
            )
            # Built-in library still loads fine
            assert len(lib.effects) >= 3
            # Bad custom was skipped

    def test_missing_custom_dir_no_error(self):
        lib = load_effect_library(
            builtin_path=FIXTURES / "minimal_library.json",
            custom_dir=Path("/nonexistent/custom_dir"),
        )
        assert len(lib.effects) == 3

    def test_custom_only_effect_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            custom_data = {
                "name": "MyCustomEffect",
                "xlights_id": "eff_CUSTOM",
                "category": "utility",
                "description": "Brand new effect",
                "intent": "Custom",
                "parameters": [
                    {"name": "P1", "storage_name": "E_SLIDER_Custom_P1",
                     "widget_type": "slider", "value_type": "int",
                     "default": 50, "min": 0, "max": 100, "description": "Param 1"},
                    {"name": "P2", "storage_name": "E_SLIDER_Custom_P2",
                     "widget_type": "slider", "value_type": "int",
                     "default": 25, "min": 0, "max": 100, "description": "Param 2"},
                    {"name": "P3", "storage_name": "E_CHECKBOX_Custom_P3",
                     "widget_type": "checkbox", "value_type": "bool",
                     "default": False, "description": "Param 3"},
                ],
                "prop_suitability": {"matrix": "ideal", "outline": "good", "arch": "good",
                                     "vertical": "good", "tree": "good", "radial": "good"},
                "analysis_mappings": [],
            }
            (custom_dir / "MyCustomEffect.json").write_text(json.dumps(custom_data))

            lib = load_effect_library(
                builtin_path=FIXTURES / "minimal_library.json",
                custom_dir=custom_dir,
            )
            assert lib.get("MyCustomEffect") is not None
            assert len(lib.effects) == 4
