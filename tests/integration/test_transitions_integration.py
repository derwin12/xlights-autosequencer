"""Integration tests for section transitions — crossfades at boundaries, end-of-song fade-out."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.effects.library import load_effect_library
from src.generator.effect_placer import place_effects
from src.variants.library import load_variant_library
from src.generator.models import SectionAssignment, SectionEnergy
from src.generator.transitions import TransitionConfig, apply_crossfades, apply_fadeout, build_fadeout_plan
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer, Theme

EFFECTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library_with_meteors.json"
VARIANTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "variants" / "builtin_variants_minimal.json"

FIRE_VARIANT = "Fire Blaze High"
METEORS_VARIANT = "Meteors Gentle Rain"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hierarchy(duration_ms: int = 60000, bpm: float = 120.0) -> HierarchyResult:
    beats = TimingTrack(
        name="beats", algorithm_name="librosa_beats", element_type="beat",
        marks=[TimingMark(time_ms=i * int(60000 / bpm), confidence=1.0)
               for i in range(int(duration_ms / (60000 / bpm)) + 1)],
        quality_score=0.9,
    )
    bars = TimingTrack(
        name="bars", algorithm_name="librosa_beats", element_type="bar",
        marks=[TimingMark(time_ms=i * int(240000 / bpm), confidence=1.0)
               for i in range(int(duration_ms / (240000 / bpm)) + 1)],
        quality_score=0.9,
    )
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=bpm,
        beats=beats,
        bars=bars,
    )


def _make_section(label: str, start_ms: int, end_ms: int, energy: int = 60) -> SectionEnergy:
    return SectionEnergy(
        label=label,
        start_ms=start_ms,
        end_ms=end_ms,
        energy_score=energy,
        mood_tier="structural",
        impact_count=0,
    )


def _make_theme(effect_name: str = "Fire") -> Theme:
    return Theme(
        name="Test",
        mood="structural",
        occasion="general",
        genre="any",
        intent="test",
        layers=[EffectLayer(variant=effect_name)],
        palette=["#FF0000", "#00FF00"],
    )


def _make_group(name: str, tier: int) -> PowerGroup:
    return PowerGroup(
        name=name,
        tier=tier,
        members=[name],
    )


def _build_section_assignment(
    label: str, start_ms: int, end_ms: int,
    variant_name: str,
    groups: list[PowerGroup],
    effect_library,
    hierarchy: HierarchyResult,
    variant_library=None,
) -> SectionAssignment:
    theme = _make_theme(variant_name)
    section = _make_section(label, start_ms, end_ms)
    assignment = SectionAssignment(
        section=section, theme=theme,
        active_tiers=frozenset({g.tier for g in groups}),
    )
    assignment.group_effects = place_effects(
        assignment, groups, effect_library, hierarchy, variant_library=variant_library,
    )
    return assignment


# ---------------------------------------------------------------------------
# T009: Integration test — crossfades on real placements
# ---------------------------------------------------------------------------

class TestCrossfadesIntegration:
    def test_three_sections_all_boundaries_have_fades(self):
        """intro→verse→chorus: every boundary should have non-zero fades on at least one group."""
        effect_library = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_library = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_library)
        hierarchy = _make_hierarchy(duration_ms=60000)

        # Two groups that will get placements
        groups = [
            _make_group("01_BASE_ALL", tier=1),
            _make_group("08_HERO_TREE", tier=8),
        ]

        assignments = [
            _build_section_assignment("intro",  0,     20000, FIRE_VARIANT,    groups, effect_library, hierarchy, variant_library),
            _build_section_assignment("verse",  20000, 40000, METEORS_VARIANT, groups, effect_library, hierarchy, variant_library),
            _build_section_assignment("chorus", 40000, 60000, FIRE_VARIANT,    groups, effect_library, hierarchy, variant_library),
        ]

        config = TransitionConfig(mode="subtle")
        apply_crossfades(assignments, config, bpm=120.0)

        # Check boundary 0→1 (intro→verse)
        boundary_01_has_fade = False
        for group_name in assignments[0].group_effects:
            placements_a = assignments[0].group_effects[group_name]
            if placements_a and placements_a[-1].fade_out_ms > 0:
                boundary_01_has_fade = True
                break
        assert boundary_01_has_fade, "intro→verse boundary should have at least one group with fade_out_ms > 0"

        # Check boundary 1→2 (verse→chorus)
        boundary_12_has_fade = False
        for group_name in assignments[1].group_effects:
            placements_b = assignments[1].group_effects.get(group_name, [])
            if placements_b and placements_b[-1].fade_out_ms > 0:
                boundary_12_has_fade = True
                break
        assert boundary_12_has_fade, "verse→chorus boundary should have at least one group with fade_out_ms > 0"

    def test_none_mode_all_fades_zero(self):
        """mode='none' should produce zero fades — backward compatible."""
        effect_library = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_library = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_library)
        hierarchy = _make_hierarchy(duration_ms=40000)

        groups = [_make_group("01_BASE_ALL", tier=1)]

        assignments = [
            _build_section_assignment("verse",  0,     20000, FIRE_VARIANT,    groups, effect_library, hierarchy, variant_library),
            _build_section_assignment("chorus", 20000, 40000, METEORS_VARIANT, groups, effect_library, hierarchy, variant_library),
        ]

        config = TransitionConfig(mode="none")
        apply_crossfades(assignments, config, bpm=120.0)

        for assignment in assignments:
            for placements in assignment.group_effects.values():
                for p in placements:
                    assert p.fade_in_ms == 0, f"Expected fade_in_ms=0 in 'none' mode, got {p.fade_in_ms}"
                    assert p.fade_out_ms == 0, f"Expected fade_out_ms=0 in 'none' mode, got {p.fade_out_ms}"

    def test_dramatic_produces_longer_fades_than_subtle(self):
        """Dramatic mode should produce longer fades than subtle on same song."""
        effect_library = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_library = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_library)
        hierarchy = _make_hierarchy(duration_ms=40000)
        groups = [_make_group("01_BASE_ALL", tier=1)]

        def total_fade_ms(mode: str) -> int:
            assigns = [
                _build_section_assignment("verse",  0,     20000, FIRE_VARIANT,    groups, effect_library, hierarchy, variant_library),
                _build_section_assignment("chorus", 20000, 40000, METEORS_VARIANT, groups, effect_library, hierarchy, variant_library),
            ]
            apply_crossfades(assigns, TransitionConfig(mode=mode), bpm=120.0)
            total = 0
            for assignment in assigns:
                for placements in assignment.group_effects.values():
                    for p in placements:
                        total += p.fade_in_ms + p.fade_out_ms
            return total

        assert total_fade_ms("dramatic") > total_fade_ms("subtle")

    def test_same_effect_across_boundary_no_fade(self):
        """Same effect on both sides of boundary → no crossfade for that group."""
        effect_library = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_library = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_library)
        hierarchy = _make_hierarchy(duration_ms=40000)
        groups = [_make_group("01_BASE_ALL", tier=1)]

        # Both sections use same Fire variant
        assignments = [
            _build_section_assignment("verse",  0,     20000, FIRE_VARIANT, groups, effect_library, hierarchy, variant_library),
            _build_section_assignment("chorus", 20000, 40000, FIRE_VARIANT, groups, effect_library, hierarchy, variant_library),
        ]

        config = TransitionConfig(mode="subtle")
        apply_crossfades(assignments, config, bpm=120.0)

        # Fire→Fire is same effect with same params → no fade on 01_BASE_ALL
        p_last = assignments[0].group_effects.get("01_BASE_ALL", [])[-1]
        p_first = assignments[1].group_effects.get("01_BASE_ALL", [])[0]
        assert p_last.fade_out_ms == 0
        assert p_first.fade_in_ms == 0


# ---------------------------------------------------------------------------
# T022: Backward compatibility — mode=none should produce zero fades everywhere
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_mode_none_matches_pre_feature_output(self):
        """Generating with mode='none' should produce all-zero fade values."""
        effect_library = load_effect_library(builtin_path=EFFECTS_FIXTURE)
        variant_library = load_variant_library(builtin_path=VARIANTS_FIXTURE, effect_library=effect_library)
        hierarchy = _make_hierarchy(duration_ms=60000)
        groups = [
            _make_group("01_BASE_ALL", tier=1),
            _make_group("06_PROP_ARCH", tier=6),
            _make_group("08_HERO_TREE", tier=8),
        ]

        assignments = [
            _build_section_assignment("intro",  0,     20000, FIRE_VARIANT,    groups, effect_library, hierarchy, variant_library),
            _build_section_assignment("verse",  20000, 40000, METEORS_VARIANT, groups, effect_library, hierarchy, variant_library),
            _build_section_assignment("chorus", 40000, 60000, FIRE_VARIANT,    groups, effect_library, hierarchy, variant_library),
        ]

        config = TransitionConfig(mode="none", fadeout_strategy="none")
        apply_crossfades(assignments, config, bpm=120.0)

        for assignment in assignments:
            for group_name, placements in assignment.group_effects.items():
                for p in placements:
                    assert p.fade_in_ms == 0, (
                        f"Expected fade_in_ms=0 for {group_name} in none mode"
                    )
                    assert p.fade_out_ms == 0, (
                        f"Expected fade_out_ms=0 for {group_name} in none mode"
                    )
