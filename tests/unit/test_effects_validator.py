"""Tests for src/effects/validator.py — schema validation."""
from __future__ import annotations

import pytest

from src.effects.validator import validate_effect_definition


def _valid_effect() -> dict:
    return {
        "name": "TestEffect",
        "xlights_id": "eff_TEST",
        "category": "nature",
        "description": "Test effect",
        "intent": "Testing",
        "parameters": [
            {
                "name": "Param1", "storage_name": "E_SLIDER_Test_Param1",
                "widget_type": "slider", "value_type": "int",
                "default": 50, "min": 0, "max": 100, "description": "A param",
            },
        ],
        "prop_suitability": {
            "matrix": "ideal", "outline": "good", "arch": "possible",
            "vertical": "good", "tree": "not_recommended", "radial": "good",
        },
        "analysis_mappings": [],
    }


class TestValidateEffectDefinition:
    def test_valid_definition_passes(self):
        errors = validate_effect_definition(_valid_effect())
        assert errors == []

    def test_missing_name_fails(self):
        data = _valid_effect()
        del data["name"]
        errors = validate_effect_definition(data)
        assert any("name" in e.lower() for e in errors)

    def test_missing_category_fails(self):
        data = _valid_effect()
        del data["category"]
        errors = validate_effect_definition(data)
        assert any("category" in e.lower() for e in errors)

    def test_invalid_category_fails(self):
        data = _valid_effect()
        data["category"] = "nonexistent_category"
        errors = validate_effect_definition(data)
        assert any("category" in e.lower() for e in errors)

    def test_missing_parameters_fails(self):
        data = _valid_effect()
        del data["parameters"]
        errors = validate_effect_definition(data)
        assert any("parameters" in e.lower() for e in errors)

    def test_missing_prop_suitability_fails(self):
        data = _valid_effect()
        del data["prop_suitability"]
        errors = validate_effect_definition(data)
        assert any("suitability" in e.lower() for e in errors)

    def test_incomplete_prop_suitability_fails(self):
        data = _valid_effect()
        del data["prop_suitability"]["tree"]
        errors = validate_effect_definition(data)
        assert any("tree" in e.lower() for e in errors)

    def test_invalid_suitability_rating_fails(self):
        data = _valid_effect()
        data["prop_suitability"]["matrix"] = "amazing"
        errors = validate_effect_definition(data)
        assert any("rating" in e.lower() or "amazing" in e.lower() for e in errors)

    def test_param_min_greater_than_max_fails(self):
        data = _valid_effect()
        data["parameters"][0]["min"] = 100
        data["parameters"][0]["max"] = 0
        errors = validate_effect_definition(data)
        assert any("min" in e.lower() and "max" in e.lower() for e in errors)

    def test_invalid_widget_type_fails(self):
        data = _valid_effect()
        data["parameters"][0]["widget_type"] = "unknown_widget"
        errors = validate_effect_definition(data)
        assert any("widget" in e.lower() for e in errors)

    def test_invalid_value_type_fails(self):
        data = _valid_effect()
        data["parameters"][0]["value_type"] = "complex"
        errors = validate_effect_definition(data)
        assert any("value_type" in e.lower() or "complex" in e.lower() for e in errors)

    def test_invalid_mapping_type_fails(self):
        data = _valid_effect()
        data["analysis_mappings"] = [{
            "parameter": "Param1",
            "analysis_level": "L5",
            "analysis_field": "energy_curves.bass",
            "mapping_type": "magical",
            "description": "Bad mapping",
        }]
        errors = validate_effect_definition(data)
        assert any("mapping_type" in e.lower() or "magical" in e.lower() for e in errors)

    def test_invalid_analysis_level_fails(self):
        data = _valid_effect()
        data["analysis_mappings"] = [{
            "parameter": "Param1",
            "analysis_level": "L99",
            "analysis_field": "whatever",
            "mapping_type": "direct",
            "description": "Bad level",
        }]
        errors = validate_effect_definition(data)
        assert any("analysis_level" in e.lower() or "L99" in e for e in errors)

    def test_mapping_referencing_nonexistent_parameter_fails(self):
        data = _valid_effect()
        data["analysis_mappings"] = [{
            "parameter": "NonExistentParam",
            "analysis_level": "L5",
            "analysis_field": "energy_curves.bass",
            "mapping_type": "direct",
            "description": "References missing param",
        }]
        errors = validate_effect_definition(data)
        assert any("NonExistentParam" in e for e in errors)

    def test_valid_with_mappings_passes(self):
        data = _valid_effect()
        data["analysis_mappings"] = [{
            "parameter": "Param1",
            "analysis_level": "L5",
            "analysis_field": "energy_curves.bass",
            "mapping_type": "direct",
            "description": "Good mapping",
        }]
        errors = validate_effect_definition(data)
        assert errors == []
