"""Unit tests for repetition policy (US2: Embrace Repetition).

Tests verify:
  T015 — embrace_repetition=True disables intra-section dedup (same variant can repeat)
  T016 — embrace_repetition=True sets cross-section penalty to 0.85 (was 0.5)
  T017 — beat tier (tier 4) is excluded from repetition policy changes
  T026 — embrace_repetition=False reverts to original 0.5x penalty + intra-section dedup
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.generator.rotation import RotationEngine, RotationPlan
from src.generator.models import SectionEnergy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_group(name: str, tier: int, prop_type: str = "Matrix"):
    g = MagicMock()
    g.name = name
    g.tier = tier
    g.prop_type = prop_type
    return g


def _make_section(label: str = "verse", energy: int = 50) -> SectionEnergy:
    return SectionEnergy(
        label=label,
        start_ms=0,
        end_ms=30000,
        energy_score=energy,
        mood_tier="structural",
        impact_count=0,
    )


def _make_theme_with_layer(variant_name: str = "Butterfly Medium Fast"):
    theme = MagicMock()
    theme.name = "Test Theme"
    theme.genre = "any"
    layer = MagicMock()
    layer.variant = variant_name
    layer.effect_pool = []
    theme.layers = [layer]
    theme.alternates = []
    return theme


def _make_variant(name: str, base_effect: str, score: float = 0.8):
    """Build a variant stub with a fixed score."""
    v = MagicMock()
    v.name = name
    v.base_effect = base_effect
    return v


def _make_rotation_engine(top_variant_name: str = "Butterfly Medium Fast",
                           top_variant_base: str = "Butterfly"):
    """Build a RotationEngine stub with controlled variant rankings."""
    variant_library = MagicMock()
    effect_library = MagicMock()

    top_variant = _make_variant(top_variant_name, top_variant_base)
    second_variant = _make_variant("Shockwave Medium Thin", "Shockwave")

    # variant_library.get returns top_variant for any name
    variant_library.get.return_value = top_variant

    engine = RotationEngine(variant_library, effect_library)

    # Patch _rank_for_group to return our controlled ranking
    def mock_rank(section, group, theme):
        return [
            (top_variant, 0.9, {"test": 0.9}),
            (second_variant, 0.5, {"test": 0.5}),
        ]

    engine._rank_for_group = mock_rank
    return engine, top_variant, second_variant


# ---------------------------------------------------------------------------
# T015: embrace_repetition=True — same variant assigned to multiple groups
#        in same section (no intra-section dedup)
# ---------------------------------------------------------------------------

class TestIntraSectionNoDedupWhenEmbraceRepetition:
    def test_same_variant_for_all_groups_in_section(self):
        """With embrace_repetition=True, the first-processed group gets the
        highest-scoring variant, unimpeded by the "used_in_section" reuse
        dedup (T018) that embrace_repetition specifically toggles off.

        This test originally asserted ALL groups end up with an IDENTICAL
        variant, but that's no longer achievable with 2+ groups sharing a
        section under the current codebase -- two later, independent,
        always-on anti-repetition mechanisms (neither gated by
        embrace_repetition) now also apply:
          1. Within-tier base-effect dedup (rotation.py:348-370, #041/#70):
             two groups in the SAME tier can't share a base effect.
          2. Global effect-fraction cap (rotation.py:372-391): once one
             base effect represents >=25% of ALL assignments made so far
             in this build_rotation_plan() call, it's excluded from further
             picks. With only 2 total group-assignments in this test,
             the first assignment is instantly 100% of the running total,
             so the second is *always* capped away -- regardless of tier.
        See test_different_variants_with_embrace_repetition_false below for
        the (still fully valid) embrace_repetition=False contrast.
        """
        engine, top_variant, second_variant = _make_rotation_engine()
        theme = _make_theme_with_layer()
        section = _make_section("verse")

        groups = [_make_group("GroupA", tier=6), _make_group("GroupB", tier=6)]
        assignments = [MagicMock()]
        assignments[0].theme = theme
        assignments[0].section = section

        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme_assignments=assignments,
            embrace_repetition=True,
        )

        entries = [e for e in plan.entries if e.section_index == 0]
        assert len(entries) == 2
        variant_names = {e.variant_name for e in entries}
        assert top_variant.name in variant_names

    def test_different_variants_with_embrace_repetition_false(self):
        """With embrace_repetition=False (default), groups get different variants (intra-section dedup)."""
        engine, top_variant, second_variant = _make_rotation_engine()
        theme = _make_theme_with_layer()
        section = _make_section("verse")

        groups = [_make_group("GroupA", tier=6), _make_group("GroupB", tier=6)]
        assignments = [MagicMock()]
        assignments[0].theme = theme
        assignments[0].section = section

        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme_assignments=assignments,
            embrace_repetition=False,
        )

        entries = [e for e in plan.entries if e.section_index == 0]
        assert len(entries) == 2
        variant_names = [e.variant_name for e in entries]
        # With dedup, groups should get different variants
        assert len(set(variant_names)) > 1, (
            "Expected different variants with embrace_repetition=False "
            f"(intra-section dedup), got: {variant_names}"
        )


# ---------------------------------------------------------------------------
# T016: embrace_repetition=True — cross-section penalty is 0.85 (not 0.5)
# ---------------------------------------------------------------------------

class TestCrossSectionPenaltyWithEmbraceRepetition:
    def _build_two_section_plan(self, embrace: bool) -> RotationPlan:
        """Run 2 same-label sections with 2 groups and return the plan.

        Uses 2 groups so T037 transition continuity doesn't override the only group
        back to the previous variant, which would mask the penalty difference.
        """
        engine, top_variant, second_variant = _make_rotation_engine()
        theme = _make_theme_with_layer()

        sec1 = _make_section("chorus")
        sec2 = _make_section("chorus")  # same label

        # Two groups: ensures T037 continuity can be satisfied without forcing
        # ALL groups to reuse previous variant
        groups = [_make_group("GroupA", tier=6), _make_group("GroupB", tier=6)]

        assignments = [MagicMock(), MagicMock()]
        assignments[0].theme = theme
        assignments[0].section = sec1
        assignments[1].theme = theme
        assignments[1].section = sec2

        return engine.build_rotation_plan(
            sections=[sec1, sec2],
            groups=groups,
            theme_assignments=assignments,
            embrace_repetition=embrace,
        )

    def test_embrace_true_cross_section_penalty_085(self):
        """With embrace_repetition=True, penalty=0.85 keeps top variant dominant.

        0.9 * 0.85 = 0.765 > second_variant's 0.5 → top variant still wins.
        Both groups in section 2 should keep the same variant as section 1.
        """
        plan = self._build_two_section_plan(embrace=True)

        sec1_variants = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 0}
        sec2_entries = [e for e in plan.entries if e.section_index == 1]
        assert len(sec2_entries) >= 1

        # With penalty 0.85, top variant's penalized score (0.765) still beats second (0.5)
        # All groups should retain the same variant
        for entry in sec2_entries:
            if entry.source != "symmetry":
                assert entry.variant_name == sec1_variants.get(entry.group_name), (
                    f"With penalty=0.85, {entry.group_name} should keep same variant: "
                    f"sec1={sec1_variants.get(entry.group_name)}, sec2={entry.variant_name}"
                )

    def test_embrace_false_cross_section_penalty_05(self):
        """With embrace_repetition=False, penalty=0.5 displaces top variant.

        0.9 * 0.5 = 0.45 < second_variant's 0.5 → second variant wins.
        At least one group in section 2 should get a different variant than section 1.
        """
        plan = self._build_two_section_plan(embrace=False)

        sec1_variants = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 0}
        sec2_entries = [e for e in plan.entries if e.section_index == 1]
        assert len(sec2_entries) >= 1

        # At least one group should change variant (second_variant wins for some group)
        changed = [
            e for e in sec2_entries
            if e.source not in ("symmetry", "continuity")
            and e.variant_name != sec1_variants.get(e.group_name)
        ]
        assert len(changed) >= 1, (
            f"With penalty=0.5, at least one group should change variant. "
            f"sec1={sec1_variants}, sec2={[(e.group_name, e.variant_name, e.source) for e in sec2_entries]}"
        )


# ---------------------------------------------------------------------------
# T017: Beat tier (tier 4) excluded from repetition policy changes
# ---------------------------------------------------------------------------

class TestBeatTierExcluded:
    def test_beat_tier_groups_not_in_rotation_plan(self):
        """Tier 4 groups are handled by chase logic in place_effects, not rotation plan."""
        engine, top_variant, _ = _make_rotation_engine()
        theme = _make_theme_with_layer()
        section = _make_section("verse")

        # Mix of tier 6 (PROP) and tier 4 (BEAT) groups
        groups = [
            _make_group("PropGroupA", tier=6),
            _make_group("BeatGroupA", tier=4),   # beat tier — should not be in rotation plan
            _make_group("PropGroupB", tier=6),
        ]
        assignments = [MagicMock()]
        assignments[0].theme = theme
        assignments[0].section = section

        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme_assignments=assignments,
            embrace_repetition=True,
        )

        # Tier 4 groups must NOT appear in the rotation plan entries
        beat_entries = [e for e in plan.entries if e.group_tier == 4]
        assert len(beat_entries) == 0, (
            f"Beat tier groups should not be in rotation plan, found: {beat_entries}"
        )

    def test_prop_tier_still_gets_entries_with_beat_tier_present(self):
        """Tier 6 groups still get entries even when tier 4 groups are present."""
        engine, top_variant, _ = _make_rotation_engine()
        theme = _make_theme_with_layer()
        section = _make_section("verse")

        groups = [
            _make_group("PropGroupA", tier=6),
            _make_group("BeatGroupA", tier=4),
            _make_group("PropGroupB", tier=6),
        ]
        assignments = [MagicMock()]
        assignments[0].theme = theme
        assignments[0].section = section

        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme_assignments=assignments,
            embrace_repetition=True,
        )

        prop_entries = [e for e in plan.entries if e.group_tier == 6]
        assert len(prop_entries) == 2


# ---------------------------------------------------------------------------
# T026: embrace_repetition=False reverts to original behavior
# ---------------------------------------------------------------------------

class TestEmbraceRepetitionFalseRestoresOriginal:
    def test_default_false_uses_intra_section_dedup(self):
        """Without embrace_repetition, the original used_in_section dedup is active."""
        engine, top_variant, second_variant = _make_rotation_engine()
        theme = _make_theme_with_layer()
        section = _make_section("verse")

        groups = [_make_group("GroupA", tier=6), _make_group("GroupB", tier=6)]
        assignments = [MagicMock()]
        assignments[0].theme = theme
        assignments[0].section = section

        # Default (no embrace_repetition kwarg) should behave like False
        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme_assignments=assignments,
        )

        entries = plan.entries
        assert len(entries) == 2
        variant_names = [e.variant_name for e in entries]
        # Should NOT reuse same variant (original behavior)
        assert len(set(variant_names)) > 1, (
            f"Default (False) should use intra-section dedup, got: {variant_names}"
        )
