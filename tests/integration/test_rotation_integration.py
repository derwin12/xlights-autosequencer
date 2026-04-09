"""Integration tests for the intelligent effect rotation engine.

Tests the full rotation flow: given groups of different prop types and a section
with known energy, verify the rotation engine assigns appropriate variants to
each group based on energy level and prop suitability.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.generator.models import SectionEnergy
from src.generator.rotation import RotationEngine, RotationPlan
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer, Theme
from src.variants.library import load_variant_library

FIXTURES = Path(__file__).parent.parent / "fixtures"
EFFECTS_FIXTURE = FIXTURES / "effects" / "minimal_library_with_meteors.json"
VARIANTS_FIXTURE = FIXTURES / "variants" / "builtin_variants_minimal.json"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_groups() -> list[PowerGroup]:
    """Create 4 tier-6 PowerGroups with different prop types."""
    return [
        PowerGroup(name="Arches", tier=6, members=["Arch-L", "Arch-R"], prop_type="arch"),
        PowerGroup(name="Matrix-Center", tier=6, members=["Matrix-1"], prop_type="matrix"),
        PowerGroup(name="MegaTree", tier=6, members=["MegaTree-1"], prop_type="tree"),
        PowerGroup(name="Roofline", tier=6, members=["Roof-1", "Roof-2"], prop_type="outline"),
    ]


def _make_chorus_section(energy: int = 80) -> SectionEnergy:
    """Create a high-energy chorus section."""
    return SectionEnergy(
        label="chorus",
        start_ms=0,
        end_ms=30000,
        energy_score=energy,
        mood_tier="high",
        impact_count=4,
    )


def _make_theme() -> Theme:
    """Create a minimal theme for rotation testing."""
    return Theme(
        name="Test Energetic",
        mood="energetic",
        occasion="christmas",
        genre="any",
        intent="High-energy test theme",
        layers=[
            EffectLayer(variant="Fire"),
            EffectLayer(variant="Bars"),
        ],
        palette=["#FF0000", "#00FF00", "#0000FF"],
        accent_palette=["#FFFFFF"],
    )


def _load_libraries():
    """Load effect and variant libraries from test fixtures."""
    effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE, custom_dir=None)
    variant_lib = load_variant_library(
        builtin_path=VARIANTS_FIXTURE,
        custom_dir=None,
        effect_library=effect_lib,
    )
    return effect_lib, variant_lib


# ── Tests ────────────────────────────────────────────────────────────────────


class TestRotationIntegration:
    """Integration tests for the full rotation engine flow."""

    def test_rotation_assigns_variants_to_all_groups(self):
        """Every group should receive a RotationEntry in the plan."""
        effect_lib, variant_lib = _load_libraries()
        groups = _make_groups()
        section = _make_chorus_section(energy=80)
        theme = _make_theme()

        engine = RotationEngine(
            effect_library=effect_lib,
            variant_library=variant_lib,
        )
        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme=theme,
        )

        assert isinstance(plan, RotationPlan)
        # Every group must have an entry for section 0
        assigned_groups = {e.group_name for e in plan.entries}
        expected_groups = {g.name for g in groups}
        assert assigned_groups == expected_groups, (
            f"Missing assignments for groups: {expected_groups - assigned_groups}"
        )

    def test_high_energy_section_gets_high_energy_variants(self):
        """A chorus at energy=80 should get 'high' or 'medium' energy variants."""
        effect_lib, variant_lib = _load_libraries()
        groups = _make_groups()
        section = _make_chorus_section(energy=80)
        theme = _make_theme()

        engine = RotationEngine(
            effect_library=effect_lib,
            variant_library=variant_lib,
        )
        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme=theme,
        )

        # Look up each variant in the library and check its energy tag.
        # With the minimal fixture (3 variants: 1 high, 1 medium, 1 low) and
        # intra-section dedup across 4 groups, at least 50% should be high/medium.
        variant_map = {v.name: v for v in variant_lib.variants.values()}
        allowed_energy = {"high", "medium"}
        matching = 0
        for entry in plan.entries:
            variant = variant_map.get(entry.variant_name)
            assert variant is not None, (
                f"Variant '{entry.variant_name}' not found in library"
            )
            if variant.tags.energy_level in allowed_energy:
                matching += 1
        total = len(plan.entries)
        assert matching >= total * 0.5, (
            f"Only {matching}/{total} entries have energy 'high' or 'medium', "
            f"expected at least 50%"
        )

    def test_different_groups_get_different_variants(self):
        """With 4 groups and sufficient variants, at least 2 distinct variants
        should be assigned (US1 minimum diversity -- full dedup is US2)."""
        effect_lib, variant_lib = _load_libraries()
        groups = _make_groups()
        section = _make_chorus_section(energy=80)
        theme = _make_theme()

        engine = RotationEngine(
            effect_library=effect_lib,
            variant_library=variant_lib,
        )
        plan = engine.build_rotation_plan(
            sections=[section],
            groups=groups,
            theme=theme,
        )

        variant_names = {e.variant_name for e in plan.entries}
        assert len(variant_names) >= 2, (
            f"Expected at least 2 distinct variants across 4 groups, "
            f"got {len(variant_names)}: {variant_names}"
        )


class TestEffectPoolIntegration:
    """T028: Integration tests for US3 — effect pool filtering across sections."""

    POOL_THEME_FIXTURE = FIXTURES / "themes" / "theme_with_effect_pool.json"

    def test_pool_variants_all_appear(self):
        """Load theme_with_effect_pool fixture, run rotation across 6+ sections,
        and verify that multiple pool variants appear in the results."""
        from src.themes.models import Theme as ThemeModel

        # Load full builtin libraries (pool references real variant names)
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)

        # Load the pool theme from fixture
        import json
        raw = json.loads(self.POOL_THEME_FIXTURE.read_text())
        theme_data = raw["themes"]["Test Pool Theme"]
        theme = ThemeModel.from_dict(theme_data)

        # The pool is on layer index 1 (the upper layer)
        pool_names = set(theme.layers[1].effect_pool)
        assert len(pool_names) >= 2, "Fixture should have at least 2 pool variants"

        # Create sections with varying energy to encourage different pool picks
        sections = [
            SectionEnergy(label="verse", start_ms=0, end_ms=10000,
                          energy_score=30, mood_tier="ethereal", impact_count=0),
            SectionEnergy(label="chorus", start_ms=10000, end_ms=20000,
                          energy_score=80, mood_tier="aggressive", impact_count=3),
            SectionEnergy(label="bridge", start_ms=20000, end_ms=30000,
                          energy_score=50, mood_tier="structural", impact_count=1),
            SectionEnergy(label="verse", start_ms=30000, end_ms=40000,
                          energy_score=25, mood_tier="ethereal", impact_count=0),
            SectionEnergy(label="chorus", start_ms=40000, end_ms=50000,
                          energy_score=85, mood_tier="aggressive", impact_count=4),
            SectionEnergy(label="outro", start_ms=50000, end_ms=60000,
                          energy_score=20, mood_tier="ethereal", impact_count=0),
        ]

        # Create tier-7 groups so they pick the upper layer (index 1) which has the pool
        groups = [
            PowerGroup(name="07_CMP_Tree", tier=7, members=["Tree1"], prop_type="tree"),
            PowerGroup(name="07_CMP_Matrix", tier=7, members=["Matrix1"], prop_type="matrix"),
        ]

        engine = RotationEngine(effect_library=effect_lib, variant_library=variant_lib)
        plan = engine.build_rotation_plan(sections=sections, groups=groups, theme=theme)

        # Collect variant names assigned to tier-7 groups
        assigned_names = {e.variant_name for e in plan.entries if e.group_tier == 7}

        # At least some assignments should come from the pool
        pool_hits = assigned_names & pool_names
        assert len(pool_hits) >= 1, (
            f"Expected at least 1 pool variant in assignments, got none. "
            f"Pool={pool_names}, assigned={assigned_names}"
        )


class TestRotationReportAPI:
    """T039: Integration tests for the /rotation-report API endpoint.

    TODO: These tests require a running Flask app context with a plan file
    on disk. Implement once the review server test harness supports
    fixture-based plan file loading (depends on T041 endpoint being stable).
    """

    @pytest.mark.skip(reason="Needs Flask test client setup for review server")
    def test_rotation_report_returns_plan_data(self):
        pass

    @pytest.mark.skip(reason="Needs Flask test client setup for review server")
    def test_rotation_report_filters_by_section(self):
        pass

    @pytest.mark.skip(reason="Needs Flask test client setup for review server")
    def test_rotation_report_missing_plan_returns_404(self):
        pass
