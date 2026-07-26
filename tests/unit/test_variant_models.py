"""Tests for src/variants/models.py — EffectVariant and VariantTags dataclasses."""
from __future__ import annotations

import pytest

from src.variants.models import (
    VALID_ENERGY_LEVELS,
    VALID_SECTION_ROLES,
    VALID_SPEED_FEELS,
    VALID_TIER_AFFINITIES,
    VALID_SCOPES,
    EffectVariant,
    VariantTags,
)


class TestVariantTags:
    def test_defaults(self):
        tags = VariantTags()
        assert tags.tier_affinity is None
        assert tags.energy_level is None
        assert tags.speed_feel is None
        assert tags.direction is None
        assert tags.section_roles == []
        assert tags.scope is None
        assert tags.genre_affinity == "any"

    def test_fully_populated(self):
        tags = VariantTags(
            tier_affinity="background",
            energy_level="low",
            speed_feel="slow",
            direction="rain-down",
            section_roles=["verse", "intro"],
            scope="single-prop",
            genre_affinity="rock",
        )
        assert tags.tier_affinity == "background"
        assert tags.energy_level == "low"
        assert tags.section_roles == ["verse", "intro"]

    def test_from_dict_full(self):
        data = {
            "tier_affinity": "foreground",
            "energy_level": "high",
            "speed_feel": "fast",
            "direction": "sweep-left",
            "section_roles": ["chorus", "build"],
            "scope": "group",
            "genre_affinity": "any",
        }
        tags = VariantTags.from_dict(data)
        assert tags.tier_affinity == "foreground"
        assert tags.energy_level == "high"
        assert tags.section_roles == ["chorus", "build"]

    def test_from_dict_empty(self):
        tags = VariantTags.from_dict({})
        assert tags.tier_affinity is None
        assert tags.energy_level is None
        assert tags.section_roles == []
        assert tags.genre_affinity == "any"

    def test_from_dict_null_values(self):
        data = {"tier_affinity": None, "energy_level": None, "direction": None}
        tags = VariantTags.from_dict(data)
        assert tags.tier_affinity is None
        assert tags.energy_level is None
        assert tags.direction is None

    def test_to_dict_roundtrip(self):
        tags = VariantTags(
            tier_affinity="mid",
            energy_level="medium",
            speed_feel="moderate",
            direction="expand-out",
            section_roles=["verse"],
            scope="single-prop",
            genre_affinity="pop",
        )
        d = tags.to_dict()
        restored = VariantTags.from_dict(d)
        assert restored.tier_affinity == tags.tier_affinity
        assert restored.energy_level == tags.energy_level
        assert restored.section_roles == tags.section_roles

    def test_to_dict_contains_all_keys(self):
        tags = VariantTags()
        d = tags.to_dict()
        expected_keys = {
            "tier_affinity", "energy_level", "speed_feel",
            "direction", "section_roles", "scope", "genre_affinity",
            "requires_color_mask", "companion_base_effect",
        }
        assert set(d.keys()) == expected_keys


class TestEffectVariant:
    def _make_variant(self) -> EffectVariant:
        return EffectVariant(
            name="Fire Blaze High",
            base_effect="Fire",
            description="Tall intense fire for chorus",
            parameter_overrides={"E_SLIDER_Fire_Height": 85, "E_CHECKBOX_Fire_GrowWithMusic": True},
            tags=VariantTags(tier_affinity="foreground", energy_level="high"),
        )

    def test_construction(self):
        v = self._make_variant()
        assert v.name == "Fire Blaze High"
        assert v.base_effect == "Fire"
        assert v.parameter_overrides["E_SLIDER_Fire_Height"] == 85

    def test_from_dict(self):
        data = {
            "name": "Meteors Gentle Rain",
            "base_effect": "Meteors",
            "description": "Soft falling meteors",
            "parameter_overrides": {
                "E_SLIDER_Meteors_Count": 5,
                "E_SLIDER_Meteors_Speed": 8,
            },
            "tags": {
                "tier_affinity": "background",
                "energy_level": "low",
                "section_roles": ["verse"],
            },
        }
        v = EffectVariant.from_dict(data)
        assert v.name == "Meteors Gentle Rain"
        assert v.base_effect == "Meteors"
        assert v.parameter_overrides["E_SLIDER_Meteors_Count"] == 5
        assert v.tags.tier_affinity == "background"
        assert isinstance(v.tags, VariantTags)

    def test_from_dict_empty_overrides(self):
        data = {
            "name": "Bare Effect",
            "base_effect": "On",
            "description": "No overrides",
            "parameter_overrides": {},
            "tags": {},
        }
        v = EffectVariant.from_dict(data)
        assert v.parameter_overrides == {}

    def test_to_dict_roundtrip(self):
        v = self._make_variant()
        d = v.to_dict()
        restored = EffectVariant.from_dict(d)
        assert restored.name == v.name
        assert restored.base_effect == v.base_effect
        assert restored.parameter_overrides == v.parameter_overrides
        assert restored.tags.tier_affinity == v.tags.tier_affinity

    def test_to_dict_structure(self):
        v = self._make_variant()
        d = v.to_dict()
        assert "name" in d
        assert "base_effect" in d
        assert "description" in d
        assert "parameter_overrides" in d
        assert "tags" in d
        assert isinstance(d["tags"], dict)

    def test_identity_key(self):
        """Two variants with same base_effect + parameters have the same identity key."""
        v1 = EffectVariant(
            name="Variant A",
            base_effect="Fire",
            description="desc",
            parameter_overrides={"E_SLIDER_Fire_Height": 80},
            tags=VariantTags(),
        )
        v2 = EffectVariant(
            name="Variant B",
            base_effect="Fire",
            description="different",
            parameter_overrides={"E_SLIDER_Fire_Height": 80},
            tags=VariantTags(energy_level="high"),
        )
        assert v1.identity_key() == v2.identity_key()

    def test_identity_key_differs_by_params(self):
        v1 = EffectVariant(
            name="A",
            base_effect="Fire",
            description="d",
            parameter_overrides={"E_SLIDER_Fire_Height": 80},
            tags=VariantTags(),
        )
        v2 = EffectVariant(
            name="A",
            base_effect="Fire",
            description="d",
            parameter_overrides={"E_SLIDER_Fire_Height": 50},
            tags=VariantTags(),
        )
        assert v1.identity_key() != v2.identity_key()

    def test_identity_key_differs_by_effect(self):
        v1 = EffectVariant(
            name="A", base_effect="Fire", description="d",
            parameter_overrides={}, tags=VariantTags(),
        )
        v2 = EffectVariant(
            name="A", base_effect="Bars", description="d",
            parameter_overrides={}, tags=VariantTags(),
        )
        assert v1.identity_key() != v2.identity_key()

    def test_identity_key_bool_int_equivalence(self):
        """True (bool) and 1 (int) must produce the same identity key."""
        v_bool = EffectVariant(
            name="A", base_effect="Fire", description="d",
            parameter_overrides={"E_CHECKBOX_Fire_GrowWithMusic": True},
            tags=VariantTags(),
        )
        v_int = EffectVariant(
            name="A", base_effect="Fire", description="d",
            parameter_overrides={"E_CHECKBOX_Fire_GrowWithMusic": 1},
            tags=VariantTags(),
        )
        assert v_bool.identity_key() == v_int.identity_key()

    def test_identity_key_float_int_equivalence(self):
        """1.0 (float) and 1 (int) must produce the same identity key."""
        v_float = EffectVariant(
            name="A", base_effect="Bars", description="d",
            parameter_overrides={"E_TEXTCTRL_Bars_Cycles": 1.0},
            tags=VariantTags(),
        )
        v_int = EffectVariant(
            name="A", base_effect="Bars", description="d",
            parameter_overrides={"E_TEXTCTRL_Bars_Cycles": 1},
            tags=VariantTags(),
        )
        assert v_float.identity_key() == v_int.identity_key()

    def test_identity_key_false_zero_equivalence(self):
        """False (bool) and 0 (int) must produce the same identity key."""
        v_bool = EffectVariant(
            name="A", base_effect="Fire", description="d",
            parameter_overrides={"E_CHECKBOX_Fire_GrowWithMusic": False},
            tags=VariantTags(),
        )
        v_int = EffectVariant(
            name="A", base_effect="Fire", description="d",
            parameter_overrides={"E_CHECKBOX_Fire_GrowWithMusic": 0},
            tags=VariantTags(),
        )
        assert v_bool.identity_key() == v_int.identity_key()


class TestConstants:
    def test_tier_affinities(self):
        assert set(VALID_TIER_AFFINITIES) == {"background", "mid", "foreground", "hero"}

    def test_energy_levels(self):
        assert set(VALID_ENERGY_LEVELS) == {"low", "medium", "high"}

    def test_speed_feels(self):
        assert set(VALID_SPEED_FEELS) == {"slow", "moderate", "fast"}

    def test_section_roles(self):
        assert set(VALID_SECTION_ROLES) == {
            "verse", "chorus", "bridge", "intro", "outro", "build", "drop"
        }

    def test_scopes(self):
        assert set(VALID_SCOPES) == {"single-prop", "group"}


class TestDirectionCycle:
    def test_direction_cycle_from_dict(self):
        data = {
            "name": "Wave Sine Horizontal",
            "base_effect": "Wave",
            "description": "Horizontal wave",
            "parameter_overrides": {"E_CHECKBOX_Mirror_Wave": 0},
            "tags": {"direction": "horizontal"},
            "direction_cycle": {
                "param": "E_CHOICE_Wave_Direction",
                "values": ["Left to Right", "Right to Left"],
                "mode": "alternate",
            },
        }
        v = EffectVariant.from_dict(data)
        assert v.direction_cycle is not None
        assert v.direction_cycle["param"] == "E_CHOICE_Wave_Direction"
        assert v.direction_cycle["values"] == ["Left to Right", "Right to Left"]
        assert v.direction_cycle["mode"] == "alternate"

    def test_direction_cycle_to_dict(self):
        v = EffectVariant(
            name="Bars 4-Bar 3D Vertical",
            base_effect="Bars",
            description="Vertical bars",
            parameter_overrides={"E_CHECKBOX_Bars_3D": 1},
            tags=VariantTags(direction="vertical"),
            direction_cycle={
                "param": "E_CHOICE_Bars_Direction",
                "values": ["up", "down"],
                "mode": "alternate",
            },
        )
        d = v.to_dict()
        assert "direction_cycle" in d
        assert d["direction_cycle"]["param"] == "E_CHOICE_Bars_Direction"
        assert d["direction_cycle"]["values"] == ["up", "down"]
        assert d["direction_cycle"]["mode"] == "alternate"

    def test_direction_cycle_none_by_default(self):
        data = {
            "name": "Fire Blaze",
            "base_effect": "Fire",
            "description": "A fire effect",
            "parameter_overrides": {"E_SLIDER_Fire_Height": 80},
            "tags": {},
        }
        v = EffectVariant.from_dict(data)
        assert v.direction_cycle is None
        d = v.to_dict()
        assert "direction_cycle" not in d

    def test_identity_key_ignores_direction_cycle(self):
        v1 = EffectVariant(
            name="Wave Sine Horizontal",
            base_effect="Wave",
            description="desc",
            parameter_overrides={"E_CHECKBOX_Mirror_Wave": 0},
            tags=VariantTags(),
            direction_cycle={
                "param": "E_CHOICE_Wave_Direction",
                "values": ["Left to Right", "Right to Left"],
                "mode": "alternate",
            },
        )
        v2 = EffectVariant(
            name="Wave Sine Horizontal",
            base_effect="Wave",
            description="desc",
            parameter_overrides={"E_CHECKBOX_Mirror_Wave": 0},
            tags=VariantTags(),
            direction_cycle=None,
        )
        assert v1.identity_key() == v2.identity_key()
