"""Tests for within-tier base-effect diversity (spec 041).

T003: 5 mock arch groups in tier 6 with identical scoring → ≥3 distinct base effects
T004: Single group in tier 6 → top-scored variant unchanged (no regression)
T005: 10 arch groups, only 4 distinct suitable effects → all 4 used before reuse
T006: 0.3 score floor — unclaimed effect scoring 0.2 → fall back to top-scored (allow dup)
T012: Tree group scored against full library → top-ranked variant is tree-ideal
T013: Tree group and arch group in same tier → receive different base effects
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.generator.rotation import RotationEngine, build_scoring_context
from src.generator.models import SectionEnergy
from src.grouper.grouper import PowerGroup
from src.themes.models import Theme, EffectLayer
from src.effects.library import load_effect_library
from src.variants.library import load_variant_library
from src.variants.models import EffectVariant, VariantTags


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EFFECT_LIB_PATH = FIXTURES / "effects" / "minimal_library_with_meteors.json"
VARIANT_LIB_PATH = FIXTURES / "variants" / "builtin_variants_minimal.json"


def _make_group(name: str, tier: int, members: list[str], prop_type: str) -> PowerGroup:
    g = PowerGroup(name=name, tier=tier, members=members)
    g.prop_type = prop_type
    return g


def _v(name: str, base_effect: str, score: float = 0.8) -> tuple[EffectVariant, float, dict]:
    """Build a (EffectVariant, score, breakdown) tuple for mocking _rank_for_group."""
    v = EffectVariant(
        name=name,
        base_effect=base_effect,
        description="test variant",
        parameter_overrides={},
        tags=VariantTags(),
    )
    return (v, score, {})


def _section(energy_score: int = 60, label: str = "chorus") -> SectionEnergy:
    return SectionEnergy(
        label=label, start_ms=0, end_ms=10000,
        energy_score=energy_score, mood_tier="structural", impact_count=1,
    )


def _theme() -> Theme:
    return Theme(
        name="TestTheme", mood="energetic", occasion="general",
        genre="rock", intent="test",
        layers=[EffectLayer(variant="Bars Sweep Left")],
        palette=["#FF0000"],
    )


@pytest.fixture()
def effect_library():
    return load_effect_library(builtin_path=EFFECT_LIB_PATH, custom_dir=None)


@pytest.fixture()
def variant_library(effect_library):
    return load_variant_library(
        builtin_path=VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
    )


@pytest.fixture()
def engine(variant_library, effect_library):
    return RotationEngine(variant_library=variant_library, effect_library=effect_library)


class TestWithinTierBaseEffectDiversity:
    """T003-T006: Within-tier base-effect diversity for tier 5-8 groups (US1)."""

    def test_t003_five_groups_identical_scoring_get_three_plus_distinct_base_effects(
        self, engine, monkeypatch
    ):
        """T003: 5 tier-6 arch groups with identical ranked results → ≥3 distinct base effects.

        With embrace_repetition=True (default), current code returns results[0] for all
        groups → all 5 get Bars (1 distinct). After within-tier dedup is added, each
        group advances to the next unclaimed base effect, yielding ≥3 distinct.
        """
        ranked = [
            _v("Bars Sweep Left", "Bars", 0.90),
            _v("Wave Slow", "Wave", 0.85),
            _v("Chase Fast", "Chase", 0.80),
            _v("Spirals Dense", "Spirals", 0.75),
            _v("Fire Tall", "Fire", 0.70),
        ]
        monkeypatch.setattr(engine, "_rank_for_group", lambda *a, **kw: ranked)

        groups = [
            _make_group(f"06_PROP_Arch{i}", tier=6, members=[f"Arch{i}"], prop_type="arch")
            for i in range(5)
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        base_effects = {e.base_effect for e in plan.entries}
        assert len(base_effects) >= 3, (
            f"Expected ≥3 distinct base effects across 5 arch groups, got {base_effects}"
        )

    def test_t004_single_group_receives_top_scored_variant_unchanged(
        self, engine, monkeypatch
    ):
        """T004: A single group in a tier gets its top-scored variant unchanged (no regression).

        With only one group in a tier, there is nothing to deduplicate against.
        The group must still receive results[0] exactly as before.
        """
        ranked = [
            _v("Bars Sweep Left", "Bars", 0.90),
            _v("Wave Slow", "Wave", 0.80),
        ]
        monkeypatch.setattr(engine, "_rank_for_group", lambda *a, **kw: ranked)

        groups = [_make_group("06_PROP_Solo", tier=6, members=["Solo"], prop_type="arch")]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        assert len(plan.entries) == 1
        assert plan.entries[0].variant_name == "Bars Sweep Left"
        assert plan.entries[0].base_effect == "Bars"

    def test_t005_ten_groups_four_distinct_effects_all_used_before_reuse(
        self, engine, monkeypatch
    ):
        """T005: 10 groups but only 4 distinct suitable effects → all 4 used before any reuse.

        The ranked list has 4 distinct base effects. After the first 4 groups exhaust
        the pool, groups 5-10 must reuse from the top, but the first 4 must all be
        distinct before any duplication occurs.
        """
        ranked = [
            _v("Bars Sweep", "Bars", 0.90),
            _v("Wave Fast", "Wave", 0.85),
            _v("Chase Right", "Chase", 0.80),
            _v("Spirals Dense", "Spirals", 0.75),
        ]
        monkeypatch.setattr(engine, "_rank_for_group", lambda *a, **kw: ranked)

        groups = [
            _make_group(f"06_PROP_{i}", tier=6, members=[f"P{i}"], prop_type="arch")
            for i in range(10)
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        base_effects_list = [e.base_effect for e in plan.entries]

        # All 4 distinct effects must appear somewhere
        assert set(base_effects_list) == {"Bars", "Wave", "Chase", "Spirals"}, (
            f"Expected all 4 distinct effects to be used, got {set(base_effects_list)}"
        )

        # The first 4 assignments must all be distinct (no early reuse)
        first_four = base_effects_list[:4]
        assert len(set(first_four)) == 4, (
            f"Expected all 4 distinct effects in first 4 assignments, got {first_four}"
        )

    def test_t006_score_floor_falls_back_to_top_when_unclaimed_scores_below_03(
        self, engine, monkeypatch
    ):
        """T006: When the only unclaimed effect scores < 0.3, fall back to top-scored (allow dup).

        Group 1 claims Bars (score 0.9).
        Group 2's only unclaimed option Wave scores 0.2 < 0.3 floor.
        Group 2 must fall back to Bars (top-scored), even though it duplicates Group 1.
        """
        group1_ranked = [
            _v("Bars Sweep", "Bars", 0.90),
            _v("Wave Slow", "Wave", 0.20),
        ]
        group2_ranked = [
            _v("Bars Sweep", "Bars", 0.90),
            _v("Wave Slow", "Wave", 0.20),
        ]

        call_count = [0]

        def controlled_rank(*args, **kwargs):
            call_count[0] += 1
            return group1_ranked if call_count[0] == 1 else group2_ranked

        monkeypatch.setattr(engine, "_rank_for_group", controlled_rank)

        groups = [
            _make_group("06_PROP_A", tier=6, members=["A"], prop_type="arch"),
            _make_group("06_PROP_B", tier=6, members=["B"], prop_type="arch"),
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        base_effects = [e.base_effect for e in plan.entries]
        assert len(base_effects) == 2
        assert base_effects[0] == "Bars", f"Group 1 should get Bars, got {base_effects[0]}"
        assert base_effects[1] == "Bars", (
            f"Group 2 should fall back to Bars (score floor: Wave=0.2 < 0.3), "
            f"got {base_effects[1]}"
        )

    def test_t003_dedup_applies_with_embrace_repetition_false_too(
        self, engine, monkeypatch
    ):
        """Within-tier base-effect dedup is independent of embrace_repetition flag."""
        ranked = [
            _v("Bars Sweep Left", "Bars", 0.90),
            _v("Wave Slow", "Wave", 0.85),
            _v("Chase Fast", "Chase", 0.80),
        ]
        monkeypatch.setattr(engine, "_rank_for_group", lambda *a, **kw: ranked)

        groups = [
            _make_group(f"06_PROP_{i}", tier=6, members=[f"P{i}"], prop_type="arch")
            for i in range(3)
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=False,
        )

        base_effects = {e.base_effect for e in plan.entries}
        assert len(base_effects) == 3, (
            f"Expected 3 distinct base effects (embrace_repetition=False), got {base_effects}"
        )

    def test_t003_dedup_only_applies_within_tier_not_across_tiers(
        self, engine, monkeypatch
    ):
        """Tier 6 and tier 8 groups may share the same base effect (cross-tier is allowed)."""
        ranked = [_v("Bars Sweep Left", "Bars", 0.90)]
        monkeypatch.setattr(engine, "_rank_for_group", lambda *a, **kw: ranked)

        groups = [
            _make_group("06_PROP_Arch", tier=6, members=["Arch"], prop_type="arch"),
            _make_group("08_HERO_Tree", tier=8, members=["Tree"], prop_type="tree"),
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        assert len(plan.entries) == 2
        # Both can have Bars — different tiers, no conflict
        assert plan.entries[0].base_effect == "Bars"
        assert plan.entries[1].base_effect == "Bars"

    def test_t003_low_tier_groups_excluded_from_dedup(self, engine, monkeypatch):
        """Tiers 1-4 are excluded — tier 4 groups should not be in rotation plan at all."""
        ranked = [_v("Bars Sweep Left", "Bars", 0.90)]
        monkeypatch.setattr(engine, "_rank_for_group", lambda *a, **kw: ranked)

        groups = [
            _make_group("04_BEAT_Chase", tier=4, members=["Chase"], prop_type="arch"),
            _make_group("06_PROP_Arch", tier=6, members=["Arch"], prop_type="arch"),
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        # Tier 4 excluded from rotation plan (handled by chase pattern separately)
        group_names = {e.group_name for e in plan.entries}
        assert "04_BEAT_Chase" not in group_names
        assert "06_PROP_Arch" in group_names


class TestTreeRadialPropRouting:
    """T012-T013: Tree/radial groups get tree-ideal effects (US2)."""

    def test_t012_tree_group_top_ranked_variant_is_tree_ideal(
        self, engine, monkeypatch
    ):
        """T012: Tree group scored against full library → top variant is tree-ideal.

        With within-tier dedup, a tree group should pick an effect rated 'ideal'
        for tree in prop_suitability. This test mocks _rank_for_group to return
        tree-ideal effects first (as the RotationEngine scoring already does via
        prop_type weight 0.30).
        """
        # Simulate RotationEngine scoring: tree-ideal effects rank first for tree groups
        tree_ideal_ranked = [
            _v("Spirals Dense Slow", "Spirals", 0.92),
            _v("Pinwheel Fast", "Pinwheel", 0.88),
            _v("Fan Sweep", "Fan", 0.85),
            _v("Bars Sweep Left", "Bars", 0.40),  # not ideal for tree
        ]
        monkeypatch.setattr(engine, "_rank_for_group", lambda *a, **kw: tree_ideal_ranked)

        groups = [
            _make_group("06_PROP_Tree", tier=6, members=["Tree1"], prop_type="tree"),
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        assert len(plan.entries) == 1
        # Top-ranked effect for a tree group should be a tree-ideal effect
        assert plan.entries[0].base_effect in {"Spirals", "Pinwheel", "Fan", "Ripple", "Shockwave"}, (
            f"Expected tree-ideal base effect, got {plan.entries[0].base_effect}"
        )

    def test_t013_tree_and_arch_in_same_tier_get_different_base_effects(
        self, engine, monkeypatch
    ):
        """T013: Tree group and arch group in same tier → different base effects.

        Tree group ranks Spirals first; arch group ranks Bars first. After within-tier
        dedup, they should receive different base effects simultaneously.
        """
        def rank_by_prop_type(section, group, theme):
            if getattr(group, "prop_type", None) == "tree":
                return [
                    _v("Spirals Dense", "Spirals", 0.92),
                    _v("Bars Sweep Left", "Bars", 0.40),
                ]
            else:  # arch
                return [
                    _v("Bars Sweep Left", "Bars", 0.90),
                    _v("Spirals Dense", "Spirals", 0.45),
                ]

        monkeypatch.setattr(engine, "_rank_for_group", rank_by_prop_type)

        groups = [
            _make_group("06_PROP_Tree", tier=6, members=["Tree1"], prop_type="tree"),
            _make_group("06_PROP_Arch", tier=6, members=["Arch1"], prop_type="arch"),
        ]

        plan = engine.build_rotation_plan(
            [_section()], groups, theme=_theme(), embrace_repetition=True,
        )

        assert len(plan.entries) == 2
        tree_effect = next(e.base_effect for e in plan.entries if e.group_name == "06_PROP_Tree")
        arch_effect = next(e.base_effect for e in plan.entries if e.group_name == "06_PROP_Arch")

        assert tree_effect != arch_effect, (
            f"Tree and arch groups in same tier should get different base effects, "
            f"both got {tree_effect}"
        )
        assert tree_effect == "Spirals", f"Tree group should get Spirals, got {tree_effect}"
        assert arch_effect == "Bars", f"Arch group should get Bars, got {arch_effect}"
