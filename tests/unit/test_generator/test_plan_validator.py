"""Tests for src.generator.plan_validator (pre-write plan diagnostics).

See openspec/changes/plan-variety-validator for the design rationale.
"""
from __future__ import annotations

from src.generator.models import EffectPlacement, SectionAssignment, SectionEnergy, Theme
from src.generator.plan_validator import validate_plan
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer


def _section(index: int) -> SectionEnergy:
    return SectionEnergy(
        label="chorus", start_ms=index * 1000, end_ms=index * 1000 + 900,
        energy_score=80, mood_tier="aggressive", impact_count=0,
    )


def _placement(effect_name: str, group_name: str, start_ms: int) -> EffectPlacement:
    return EffectPlacement(
        effect_name=effect_name, xlights_id=f"E_{effect_name.upper()}",
        model_or_group=group_name, start_ms=start_ms, end_ms=start_ms + 500,
    )


def _assignment(section_index: int, group_name: str, effect_name: str) -> SectionAssignment:
    theme = Theme(
        name="Test Theme", mood="structural", occasion="general", genre="any",
        intent="test", layers=[EffectLayer(variant="Color Wash")], palette=["#ff0000"],
    )
    return SectionAssignment(
        section=_section(section_index), theme=theme, section_index=section_index,
        group_effects={group_name: [_placement(effect_name, group_name, section_index * 1000)]},
    )


_MINITREE_GROUP = PowerGroup(
    name="06_PROP_Tree", tier=6, members=["Tree 1", "Tree 2"],
)
_MATRIX_GROUP = PowerGroup(
    name="06_PROP_Matrix", tier=6, members=["Matrix 1"],
)


class TestCorpusRecipeMonotony:
    def test_flags_group_that_never_uses_the_alt_effect(self) -> None:
        # minitree's recipe pairs Single Strand (primary) / Shockwave (alt).
        # Every occurrence here uses only the primary -- the exact "one
        # effect the whole song" shape this check exists to catch.
        assignments = [
            _assignment(0, "06_PROP_Tree", "Single Strand"),
            _assignment(1, "06_PROP_Tree", "Single Strand"),
            _assignment(2, "06_PROP_Tree", "Single Strand"),
        ]
        warnings = validate_plan(assignments, [_MINITREE_GROUP])
        assert len(warnings) == 1
        assert warnings[0].code == "corpus_recipe_monotony"
        assert warnings[0].group_name == "06_PROP_Tree"
        assert warnings[0].severity == "warning"

    def test_does_not_flag_when_both_effects_appear(self) -> None:
        assignments = [
            _assignment(0, "06_PROP_Tree", "Single Strand"),
            _assignment(1, "06_PROP_Tree", "Shockwave"),
            _assignment(2, "06_PROP_Tree", "Single Strand"),
        ]
        assert validate_plan(assignments, [_MINITREE_GROUP]) == []

    def test_does_not_flag_a_single_occurrence(self) -> None:
        # One qualifying occurrence can't demonstrate variety by
        # construction -- not a bug.
        assignments = [_assignment(0, "06_PROP_Tree", "Single Strand")]
        assert validate_plan(assignments, [_MINITREE_GROUP]) == []

    def test_does_not_flag_a_group_with_no_recipe(self) -> None:
        group = PowerGroup(name="06_PROP_Unknown", tier=6, members=["Thing 1"])
        assignments = [
            _assignment(0, "06_PROP_Unknown", "On"),
            _assignment(1, "06_PROP_Unknown", "On"),
        ]
        assert validate_plan(assignments, [group]) == []

    def test_does_not_flag_motion_rotation_families(self) -> None:
        # matrix uses motion_rotation, not the plain primary/alt path --
        # out of scope for V1 (see module docstring), needs its own
        # reachability-shaped check instead.
        assignments = [
            _assignment(0, "06_PROP_Matrix", "Shockwave"),
            _assignment(1, "06_PROP_Matrix", "Shockwave"),
            _assignment(2, "06_PROP_Matrix", "Shockwave"),
        ]
        assert validate_plan(assignments, [_MATRIX_GROUP]) == []

    def test_ignores_placements_outside_the_recipe_pair(self) -> None:
        # An On mask-layer placement (or anything else not in
        # {effect_name, alt_effect_name}) must not count toward variety --
        # only the primary/alt choice itself is being checked. Two real
        # Single Strand occurrences plus an unrelated On placement should
        # still flag as monotone (On doesn't "count" as the missing alt).
        assignments = [
            _assignment(0, "06_PROP_Tree", "Single Strand"),
            _assignment(1, "06_PROP_Tree", "On"),
            _assignment(2, "06_PROP_Tree", "Single Strand"),
        ]
        warnings = validate_plan(assignments, [_MINITREE_GROUP])
        assert len(warnings) == 1
        assert "Single Strand" in warnings[0].message
