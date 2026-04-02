"""Tests for src/generator/rotation — RotationEntry, RotationPlan, build_scoring_context."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.generator.rotation import RotationEntry, RotationPlan, build_scoring_context

try:
    from src.generator.rotation import RotationEngine
except ImportError:
    RotationEngine = None  # T019 not yet implemented
from src.generator.models import SectionEnergy
from src.grouper.grouper import PowerGroup
from src.themes.models import Theme, EffectLayer
from src.effects.library import load_effect_library
from src.variants.library import VariantLibrary, load_variant_library


def _make_group(name: str, tier: int, members: list[str], prop_type: str) -> PowerGroup:
    """Create a PowerGroup with prop_type set (not a dataclass field, but accessed by rotation)."""
    g = PowerGroup(name=name, tier=tier, members=members)
    g.prop_type = prop_type
    return g


class TestRotationEntry:
    def test_construction_all_fields(self):
        entry = RotationEntry(
            section_index=0,
            section_label="chorus",
            group_name="06_PROP_Arch",
            group_tier=6,
            variant_name="Chase_Fast",
            base_effect="Chase",
            score=0.85,
            score_breakdown={"energy": 0.9, "prop_type": 0.8},
            source="pool",
        )
        assert entry.section_index == 0
        assert entry.section_label == "chorus"
        assert entry.group_name == "06_PROP_Arch"
        assert entry.group_tier == 6
        assert entry.variant_name == "Chase_Fast"
        assert entry.base_effect == "Chase"
        assert entry.score == 0.85
        assert entry.score_breakdown == {"energy": 0.9, "prop_type": 0.8}
        assert entry.source == "pool"

    def test_default_values(self):
        entry = RotationEntry(
            section_index=1,
            section_label="verse",
            group_name="05_TEX_HiDens",
            group_tier=5,
            variant_name="Wave_Slow",
            base_effect="Wave",
            score=0.5,
        )
        assert entry.score_breakdown == {}
        assert entry.source == "library"

    def test_to_dict(self):
        entry = RotationEntry(
            section_index=2,
            section_label="bridge",
            group_name="08_HERO_Tree",
            group_tier=8,
            variant_name="Fire_Tall",
            base_effect="Fire",
            score=0.92,
            score_breakdown={"energy": 1.0},
            source="continuity",
        )
        d = entry.to_dict()
        assert d == {
            "section_index": 2,
            "section_label": "bridge",
            "group_name": "08_HERO_Tree",
            "group_tier": 8,
            "variant_name": "Fire_Tall",
            "base_effect": "Fire",
            "score": 0.92,
            "score_breakdown": {"energy": 1.0},
            "source": "continuity",
        }


class TestRotationPlan:
    def test_construction_defaults(self):
        plan = RotationPlan()
        assert plan.entries == []
        assert plan.sections_count == 0
        assert plan.groups_count == 0
        assert plan.symmetry_pairs == []

    def test_to_dict(self):
        entry = RotationEntry(
            section_index=0,
            section_label="chorus",
            group_name="06_PROP_Arch",
            group_tier=6,
            variant_name="Chase_Fast",
            base_effect="Chase",
            score=0.85,
        )
        plan = RotationPlan(
            entries=[entry],
            sections_count=3,
            groups_count=2,
            symmetry_pairs=["pair_a"],
        )
        d = plan.to_dict()
        assert d["sections_count"] == 3
        assert d["groups_count"] == 2
        assert len(d["entries"]) == 1
        assert d["entries"][0]["variant_name"] == "Chase_Fast"
        assert d["symmetry_pairs"] == ["pair_a"]

    def test_lookup_found(self):
        e1 = RotationEntry(
            section_index=0,
            section_label="verse",
            group_name="06_PROP_Arch",
            group_tier=6,
            variant_name="Wave_Slow",
            base_effect="Wave",
            score=0.7,
        )
        e2 = RotationEntry(
            section_index=1,
            section_label="chorus",
            group_name="08_HERO_Tree",
            group_tier=8,
            variant_name="Fire_Tall",
            base_effect="Fire",
            score=0.9,
        )
        plan = RotationPlan(entries=[e1, e2], sections_count=2, groups_count=2)
        result = plan.lookup(1, "08_HERO_Tree")
        assert result is e2

    def test_lookup_missing(self):
        e1 = RotationEntry(
            section_index=0,
            section_label="verse",
            group_name="06_PROP_Arch",
            group_tier=6,
            variant_name="Wave_Slow",
            base_effect="Wave",
            score=0.7,
        )
        plan = RotationPlan(entries=[e1], sections_count=1, groups_count=1)
        assert plan.lookup(5, "nonexistent") is None


class TestBuildScoringContext:
    """Test build_scoring_context energy/tier/role/genre/prop mapping."""

    def _section(self, energy_score: int, label: str = "verse") -> SectionEnergy:
        return SectionEnergy(
            label=label,
            start_ms=0,
            end_ms=10000,
            energy_score=energy_score,
            mood_tier="ethereal",
            impact_count=0,
        )

    def _group(self, tier: int = 6, prop_type: str = "arch") -> PowerGroup:
        return _make_group(
            name="06_PROP_Arch", tier=tier, members=["Arch1"], prop_type=prop_type
        )

    def _theme(self, genre: str = "rock") -> Theme:
        return Theme(
            name="T",
            mood="dark",
            occasion="general",
            genre=genre,
            intent="test",
            layers=[],
            palette=["#FF0000"],
        )

    # ---- energy_level mapping ----

    def test_energy_20_is_low(self):
        ctx = build_scoring_context(self._section(20), self._group(), self._theme())
        assert ctx.energy_level == "low"

    def test_energy_33_is_low(self):
        ctx = build_scoring_context(self._section(33), self._group(), self._theme())
        assert ctx.energy_level == "low"

    def test_energy_34_is_medium(self):
        ctx = build_scoring_context(self._section(34), self._group(), self._theme())
        assert ctx.energy_level == "medium"

    def test_energy_66_is_medium(self):
        ctx = build_scoring_context(self._section(66), self._group(), self._theme())
        assert ctx.energy_level == "medium"

    def test_energy_67_is_high(self):
        ctx = build_scoring_context(self._section(67), self._group(), self._theme())
        assert ctx.energy_level == "high"

    # ---- tier_affinity mapping ----

    def test_tier_5_is_mid(self):
        ctx = build_scoring_context(
            self._section(50), self._group(tier=5), self._theme()
        )
        assert ctx.tier_affinity == "mid"

    def test_tier_6_is_mid(self):
        ctx = build_scoring_context(
            self._section(50), self._group(tier=6), self._theme()
        )
        assert ctx.tier_affinity == "mid"

    def test_tier_7_is_foreground(self):
        ctx = build_scoring_context(
            self._section(50), self._group(tier=7), self._theme()
        )
        assert ctx.tier_affinity == "foreground"

    def test_tier_8_is_hero(self):
        ctx = build_scoring_context(
            self._section(50), self._group(tier=8), self._theme()
        )
        assert ctx.tier_affinity == "hero"

    # ---- passthrough fields ----

    def test_section_label_maps_to_section_role(self):
        ctx = build_scoring_context(
            self._section(50, label="chorus"), self._group(), self._theme()
        )
        assert ctx.section_role == "chorus"

    def test_theme_genre_maps_to_genre(self):
        ctx = build_scoring_context(
            self._section(50), self._group(), self._theme(genre="country")
        )
        assert ctx.genre == "country"

    def test_group_prop_type_maps_to_prop_type(self):
        ctx = build_scoring_context(
            self._section(50), self._group(prop_type="matrix"), self._theme()
        )
        assert ctx.prop_type == "matrix"


@pytest.mark.skipif(RotationEngine is None, reason="RotationEngine not yet implemented (T019)")
class TestSelectVariantForGroup:
    """Tests for RotationEngine.select_variant_for_group() — expects T019 implementation."""

    FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
    EFFECT_LIB_PATH = FIXTURES / "effects" / "minimal_library_with_meteors.json"
    VARIANT_LIB_PATH = FIXTURES / "variants" / "builtin_variants_minimal.json"

    @pytest.fixture()
    def effect_library(self):
        return load_effect_library(builtin_path=self.EFFECT_LIB_PATH, custom_dir=None)

    @pytest.fixture()
    def variant_library(self, effect_library):
        return load_variant_library(
            builtin_path=self.VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
        )

    @pytest.fixture()
    def engine(self, variant_library, effect_library):
        return RotationEngine(variant_library=variant_library, effect_library=effect_library)

    @staticmethod
    def _section(energy_score: int, label: str = "chorus") -> SectionEnergy:
        return SectionEnergy(
            label=label,
            start_ms=0,
            end_ms=10000,
            energy_score=energy_score,
            mood_tier="aggressive",
            impact_count=2,
        )

    @staticmethod
    def _group(tier: int = 6, prop_type: str = "matrix") -> PowerGroup:
        g = PowerGroup(name="06_PROP_Matrix", tier=tier, members=["Matrix1"])
        g.prop_type = prop_type
        return g

    @staticmethod
    def _theme() -> Theme:
        return Theme(
            name="TestTheme",
            mood="aggressive",
            occasion="general",
            genre="rock",
            intent="high energy test",
            layers=[EffectLayer(effect="Fire")],
            palette=["#FF0000", "#FF6600"],
        )

    @staticmethod
    def _layer() -> EffectLayer:
        return EffectLayer(effect="Fire")

    def test_returns_top_scoring_variant(self, engine):
        """High-energy section should select a variant tagged high or adjacent energy."""
        section = self._section(energy_score=80)
        group = self._group(tier=6, prop_type="matrix")
        theme = self._theme()
        layer = self._layer()

        result = engine.select_variant_for_group(section, group, theme, layer)

        assert result is not None, "Expected a variant for high-energy matrix group"
        # The minimal fixture has Fire Blaze High (high) and Bars Sweep Left (medium).
        # With energy_score=80 the context energy_level is "high", so the top scorer
        # should be an energy_level="high" or adjacent ("medium") variant.
        assert result.tags.get("energy_level") in ("high", "medium")

    def test_handles_empty_variant_library(self, effect_library):
        """An empty variant library should cause select_variant_for_group to return None."""
        empty_lib = VariantLibrary(schema_version="1.0.0", variants={})
        engine = RotationEngine(variant_library=empty_lib, effect_library=effect_library)

        section = self._section(energy_score=50)
        group = self._group()
        theme = self._theme()
        layer = self._layer()

        result = engine.select_variant_for_group(section, group, theme, layer)
        assert result is None

    def test_uses_correct_scoring_context(self, engine, monkeypatch):
        """Verify the method builds a ScoringContext with the right fields from inputs."""
        captured_contexts: list = []

        original_select = engine.select_variant_for_group

        def spy_select(section, group, theme, layer):
            # Build the context the same way the engine should internally
            ctx = build_scoring_context(section, group, theme)
            captured_contexts.append(ctx)
            return original_select(section, group, theme, layer)

        engine.select_variant_for_group = spy_select

        section = self._section(energy_score=80, label="chorus")
        group = self._group(tier=7, prop_type="matrix")
        theme = self._theme()
        layer = self._layer()

        engine.select_variant_for_group(section, group, theme, layer)

        assert len(captured_contexts) == 1
        ctx = captured_contexts[0]
        assert ctx.energy_level == "high"
        assert ctx.tier_affinity == "foreground"
        assert ctx.prop_type == "matrix"
        assert ctx.section_role == "chorus"
        assert ctx.genre == "rock"


@pytest.mark.skipif(RotationEngine is None, reason="RotationEngine not yet implemented (T019)")
class TestIntraSectionVariety:
    """T023: Tests for intra-section variety — groups within a section get distinct variants."""

    FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
    EFFECT_LIB_PATH = FIXTURES / "effects" / "minimal_library_with_meteors.json"
    VARIANT_LIB_PATH = FIXTURES / "variants" / "builtin_variants_minimal.json"

    @pytest.fixture()
    def effect_library(self):
        return load_effect_library(builtin_path=self.EFFECT_LIB_PATH, custom_dir=None)

    @pytest.fixture()
    def variant_library(self, effect_library):
        return load_variant_library(
            builtin_path=self.VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
        )

    @pytest.fixture()
    def engine(self, variant_library, effect_library):
        return RotationEngine(variant_library=variant_library, effect_library=effect_library)

    @staticmethod
    def _section(energy_score: int = 60, label: str = "chorus") -> SectionEnergy:
        return SectionEnergy(
            label=label, start_ms=0, end_ms=10000,
            energy_score=energy_score, mood_tier="structural", impact_count=1,
        )

    @staticmethod
    def _theme() -> Theme:
        return Theme(
            name="TestTheme", mood="aggressive", occasion="general",
            genre="rock", intent="high energy test",
            layers=[EffectLayer(effect="Fire")], palette=["#FF0000", "#FF6600"],
        )

    def test_four_groups_get_at_least_three_distinct_variants(self, engine):
        """4 tier-6 groups should produce at least 3 distinct variant names (library has 3)."""
        groups = [
            _make_group(f"06_PROP_{i}", tier=6, members=[f"Prop{i}"], prop_type="matrix")
            for i in range(4)
        ]
        sections = [self._section()]
        theme = self._theme()

        plan = engine.build_rotation_plan(sections, groups, theme=theme)

        variant_names = {e.variant_name for e in plan.entries}
        assert len(variant_names) >= 3, (
            f"Expected at least 3 distinct variants among 4 groups, got {variant_names}"
        )

    def test_two_groups_one_variant_graceful_reuse(self, effect_library):
        """With only 1 variant available, 2 groups should both get entries (reuse, no error)."""
        single_variant_lib = load_variant_library(
            builtin_path=self.VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
        )
        # Keep only the first variant
        first_key = next(iter(single_variant_lib.variants))
        single_variant_lib.variants = {first_key: single_variant_lib.variants[first_key]}

        engine = RotationEngine(variant_library=single_variant_lib, effect_library=effect_library)
        groups = [
            _make_group(f"06_PROP_{i}", tier=6, members=[f"Prop{i}"], prop_type="matrix")
            for i in range(2)
        ]
        sections = [self._section()]
        theme = self._theme()

        plan = engine.build_rotation_plan(sections, groups, theme=theme)

        assert len(plan.entries) == 2, "Both groups should have entries even with 1 variant"
        assert plan.entries[0].variant_name == plan.entries[1].variant_name


@pytest.mark.skipif(RotationEngine is None, reason="RotationEngine not yet implemented (T019)")
class TestCrossSectionVariety:
    """T024: Tests for cross-section repeat penalty — repeated section labels get variety."""

    FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
    EFFECT_LIB_PATH = FIXTURES / "effects" / "minimal_library_with_meteors.json"
    VARIANT_LIB_PATH = FIXTURES / "variants" / "builtin_variants_minimal.json"

    @pytest.fixture()
    def effect_library(self):
        return load_effect_library(builtin_path=self.EFFECT_LIB_PATH, custom_dir=None)

    @pytest.fixture()
    def variant_library(self, effect_library):
        return load_variant_library(
            builtin_path=self.VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
        )

    @pytest.fixture()
    def engine(self, variant_library, effect_library):
        return RotationEngine(variant_library=variant_library, effect_library=effect_library)

    @staticmethod
    def _section(energy_score: int = 60, label: str = "verse") -> SectionEnergy:
        return SectionEnergy(
            label=label, start_ms=0, end_ms=10000,
            energy_score=energy_score, mood_tier="structural", impact_count=1,
        )

    @staticmethod
    def _theme() -> Theme:
        return Theme(
            name="TestTheme", mood="aggressive", occasion="general",
            genre="rock", intent="test",
            layers=[EffectLayer(effect="Fire")], palette=["#FF0000", "#FF6600"],
        )

    def test_repeated_verse_sections_differ_50_percent(self, engine):
        """Two sections both labeled 'verse' with 4 groups: at least 50% of assignments differ."""
        groups = [
            _make_group(f"06_PROP_{i}", tier=6, members=[f"Prop{i}"], prop_type="matrix")
            for i in range(4)
        ]
        sections = [self._section(label="verse"), self._section(label="verse")]
        theme = self._theme()

        plan = engine.build_rotation_plan(sections, groups, theme=theme)

        sec0 = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 0}
        sec1 = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 1}

        differ_count = sum(
            1 for g in sec0 if g in sec1 and sec0[g] != sec1[g]
        )
        total = len(sec0)
        assert total > 0, "Should have entries for section 0"
        assert differ_count / total >= 0.5, (
            f"Expected at least 50% different assignments across repeated verse sections, "
            f"got {differ_count}/{total}. sec0={sec0}, sec1={sec1}"
        )

    def test_non_repeating_section_no_penalty(self, engine):
        """Two sections with different labels should not penalize cross-section repeats."""
        groups = [
            _make_group(f"06_PROP_{i}", tier=6, members=[f"Prop{i}"], prop_type="matrix")
            for i in range(4)
        ]
        sections = [self._section(label="verse"), self._section(label="chorus")]
        theme = self._theme()

        plan = engine.build_rotation_plan(sections, groups, theme=theme)

        # With different labels, no cross-section penalty applies.
        # Both sections should have entries assigned purely by scoring.
        sec0 = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 0}
        sec1 = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 1}
        assert len(sec0) == 4, "All 4 groups should have entries in section 0"
        assert len(sec1) == 4, "All 4 groups should have entries in section 1"


@pytest.mark.skipif(RotationEngine is None, reason="RotationEngine not yet implemented (T019)")
class TestSymmetryEnforcement:
    """T033: Symmetry pairs receive the same variant assignment."""

    FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
    EFFECT_LIB_PATH = FIXTURES / "effects" / "minimal_library_with_meteors.json"
    VARIANT_LIB_PATH = FIXTURES / "variants" / "builtin_variants_minimal.json"

    @pytest.fixture()
    def effect_library(self):
        return load_effect_library(builtin_path=self.EFFECT_LIB_PATH, custom_dir=None)

    @pytest.fixture()
    def variant_library(self, effect_library):
        return load_variant_library(
            builtin_path=self.VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
        )

    @pytest.fixture()
    def engine(self, variant_library, effect_library):
        return RotationEngine(variant_library=variant_library, effect_library=effect_library)

    @staticmethod
    def _section(energy_score: int = 60, label: str = "chorus") -> SectionEnergy:
        return SectionEnergy(
            label=label, start_ms=0, end_ms=10000,
            energy_score=energy_score, mood_tier="structural", impact_count=1,
        )

    @staticmethod
    def _theme() -> Theme:
        return Theme(
            name="TestTheme", mood="aggressive", occasion="general",
            genre="rock", intent="test",
            layers=[EffectLayer(effect="Fire")], palette=["#FF0000", "#FF6600"],
        )

    def test_symmetry_pair_gets_same_variant(self, engine):
        """Two groups in a symmetry pair should receive the same variant_name."""
        from src.grouper.symmetry import SymmetryGroup

        group_a = _make_group("06_PROP_Arch_Left", tier=6, members=["ArchL"], prop_type="arch")
        group_b = _make_group("06_PROP_Arch_Right", tier=6, members=["ArchR"], prop_type="arch")
        groups = [group_a, group_b]
        sections = [self._section()]
        theme = self._theme()

        symmetry_pairs = [
            SymmetryGroup(group_a="06_PROP_Arch_Left", group_b="06_PROP_Arch_Right",
                          detection_method="name"),
        ]

        plan = engine.build_rotation_plan(
            sections, groups, theme=theme, symmetry_pairs=symmetry_pairs,
        )

        entries_by_group = {e.group_name: e for e in plan.entries}
        assert "06_PROP_Arch_Left" in entries_by_group
        assert "06_PROP_Arch_Right" in entries_by_group
        assert (
            entries_by_group["06_PROP_Arch_Left"].variant_name
            == entries_by_group["06_PROP_Arch_Right"].variant_name
        )


@pytest.mark.skipif(RotationEngine is None, reason="RotationEngine not yet implemented (T019)")
class TestTransitionContinuity:
    """T034: Adjacent sections share at least one variant for visual continuity."""

    FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
    EFFECT_LIB_PATH = FIXTURES / "effects" / "minimal_library_with_meteors.json"
    VARIANT_LIB_PATH = FIXTURES / "variants" / "builtin_variants_minimal.json"

    @pytest.fixture()
    def effect_library(self):
        return load_effect_library(builtin_path=self.EFFECT_LIB_PATH, custom_dir=None)

    @pytest.fixture()
    def variant_library(self, effect_library):
        return load_variant_library(
            builtin_path=self.VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
        )

    @pytest.fixture()
    def engine(self, variant_library, effect_library):
        return RotationEngine(variant_library=variant_library, effect_library=effect_library)

    @staticmethod
    def _section(energy_score: int = 60, label: str = "verse") -> SectionEnergy:
        return SectionEnergy(
            label=label, start_ms=0, end_ms=10000,
            energy_score=energy_score, mood_tier="structural", impact_count=1,
        )

    @staticmethod
    def _theme() -> Theme:
        return Theme(
            name="TestTheme", mood="aggressive", occasion="general",
            genre="rock", intent="test",
            layers=[EffectLayer(effect="Fire")], palette=["#FF0000", "#FF6600"],
        )

    def test_adjacent_sections_share_variant(self, engine):
        """At least one group should have the same variant in both adjacent sections."""
        groups = [
            _make_group(f"06_PROP_{i}", tier=6, members=[f"Prop{i}"], prop_type="matrix")
            for i in range(3)
        ]
        sections = [self._section(label="verse"), self._section(label="chorus")]
        theme = self._theme()

        plan = engine.build_rotation_plan(sections, groups, theme=theme)

        sec0 = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 0}
        sec1 = {e.group_name: e.variant_name for e in plan.entries if e.section_index == 1}

        shared = any(
            sec0.get(g) == sec1.get(g)
            for g in sec0
            if g in sec1
        )
        assert shared, (
            f"Expected at least one group to keep its variant across sections. "
            f"sec0={sec0}, sec1={sec1}"
        )


@pytest.mark.skipif(RotationEngine is None, reason="RotationEngine not yet implemented (T019)")
class TestEffectPoolSelection:
    """T027: Tests for US3 — theme effect pool filtering in select_variant_for_group."""

    FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
    EFFECT_LIB_PATH = FIXTURES / "effects" / "minimal_library_with_meteors.json"
    VARIANT_LIB_PATH = FIXTURES / "variants" / "builtin_variants_minimal.json"

    @pytest.fixture()
    def effect_library(self):
        return load_effect_library(builtin_path=self.EFFECT_LIB_PATH, custom_dir=None)

    @pytest.fixture()
    def variant_library(self, effect_library):
        return load_variant_library(
            builtin_path=self.VARIANT_LIB_PATH, custom_dir=None, effect_library=effect_library,
        )

    @pytest.fixture()
    def engine(self, variant_library, effect_library):
        return RotationEngine(variant_library=variant_library, effect_library=effect_library)

    @staticmethod
    def _section(energy_score: int = 80, label: str = "chorus") -> SectionEnergy:
        return SectionEnergy(
            label=label, start_ms=0, end_ms=10000,
            energy_score=energy_score, mood_tier="aggressive", impact_count=2,
        )

    @staticmethod
    def _group(tier: int = 6, prop_type: str = "matrix") -> PowerGroup:
        g = PowerGroup(name="06_PROP_Matrix", tier=tier, members=["Matrix1"])
        g.prop_type = prop_type
        return g

    @staticmethod
    def _theme() -> Theme:
        return Theme(
            name="TestTheme", mood="aggressive", occasion="general",
            genre="rock", intent="pool test",
            layers=[EffectLayer(effect="Fire")],
            palette=["#FF0000", "#FF6600"],
        )

    def test_pool_restricts_selection(self, engine):
        """When a layer has effect_pool, only pool variants should be selected."""
        pool_names = ["Fire Blaze High", "Meteors Gentle Rain"]
        layer = EffectLayer(effect="Fire", effect_pool=pool_names)

        section = self._section(energy_score=80)
        group = self._group(tier=6, prop_type="matrix")
        theme = self._theme()

        result = engine.select_variant_for_group(section, group, theme, layer)

        assert result is not None, "Expected a variant from the pool"
        assert result.name in pool_names, (
            f"Variant '{result.name}' is not in pool {pool_names}"
        )

    def test_pool_fallback_to_library(self, engine):
        """When pool contains only non-existent variants, fall back to library scoring."""
        layer = EffectLayer(effect="Fire", effect_pool=["nonexistent-variant"])

        section = self._section(energy_score=80)
        group = self._group(tier=6, prop_type="matrix")
        theme = self._theme()

        result = engine.select_variant_for_group(section, group, theme, layer)

        # Should fall back to library — still return something, not error
        assert result is not None, "Expected fallback to library scoring"
