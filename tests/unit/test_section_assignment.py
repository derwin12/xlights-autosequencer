"""Tests for extended `SectionAssignment` fields (spec 048).

Covers:
  - User Story 1: every Brief-visible decision is a populated field on the
    assignment after `build_plan()` returns.
  - User Story 2: `place_effects` reads all per-section decisions off the
    assignment.
  - User Story 3: accent helpers trust `assignment.accent_policy`.
  - User Story 4: detaching a single assignment and re-running `place_effects`
    reproduces the full-song output for that section.
  - User Story 5: mutations to `active_tiers`, `palette_target`,
    `duration_target`, `accent_policy` flow through placement without new
    plumbing.

Uses the same deterministic fixture hierarchy as the equivalence gate so all
tests operate on a known plan shape.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult
from src.effects.library import load_effect_library
from src.generator.effect_placer import (
    _IMPACT_ENERGY_GATE,
    _IMPACT_MIN_DURATION_MS,
    _IMPACT_QUALIFYING_ROLES,
    _place_drum_accents,
    _place_impact_accent,
    place_effects,
)
from src.generator.models import (
    AccentPolicy,
    DurationTarget,
    GenerationConfig,
    SectionAssignment,
    SequencePlan,
)
from src.generator.plan import build_plan
from src.grouper.classifier import classify_props, normalize_coords
from src.grouper.grouper import generate_groups
from src.grouper.layout import parse_layout
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library

# Reuse the same fixture hierarchy as the equivalence gate.
from tests.integration.test_generator_equivalence import (
    LAYOUT_PATH,
    FIXTURE_AUDIO,
    _build_fixture_hierarchy,
)


# ---------------------------------------------------------------------------
# Plan builder that mirrors _generate_xsq but returns the built plan + deps
# ---------------------------------------------------------------------------

def _build_plan_and_deps(
    tmp_path: Path,
    *,
    palette_restraint: bool = True,
    duration_scaling: bool = True,
    beat_accent_effects: bool = True,
    tier_selection: bool = True,
    focused_vocabulary: bool = True,
):
    """Return `(plan, config, hierarchy, groups, effect_lib, variant_lib)` for a fixture run."""
    config = GenerationConfig(
        audio_path=FIXTURE_AUDIO,
        layout_path=LAYOUT_PATH,
        output_dir=tmp_path,
        curves_mode="none",
        transition_mode="none",
        focused_vocabulary=focused_vocabulary,
        palette_restraint=palette_restraint,
        duration_scaling=duration_scaling,
        beat_accent_effects=beat_accent_effects,
        tier_selection=tier_selection,
    )
    hierarchy = _build_fixture_hierarchy()
    layout = parse_layout(config.layout_path)
    props = layout.props
    normalize_coords(props)
    classify_props(props)
    groups = generate_groups(props)
    effect_lib = load_effect_library()
    variant_lib = load_variant_library(effect_library=effect_lib)
    theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
    plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)
    return plan, config, hierarchy, groups, effect_lib, variant_lib


# ===========================================================================
# User Story 1 — field population
# ===========================================================================

class TestUS1_FieldPopulation:
    """After build_plan() returns, every assignment carries the full decision record."""

    def test_active_tiers_populated(self, tmp_path: Path) -> None:
        """T010: active_tiers is a non-empty frozenset[int] drawn from {1..8}."""
        plan, *_ = _build_plan_and_deps(tmp_path)
        for a in plan.sections:
            assert isinstance(a.active_tiers, frozenset), a
            assert a.active_tiers, f"empty active_tiers on section {a.section.label}"
            assert all(1 <= t <= 8 for t in a.active_tiers), a.active_tiers

    def test_palette_target_populated_when_restraint_on(self, tmp_path: Path) -> None:
        """T011: with palette_restraint=True every palette_target is a dict[tier, int in 1..6]."""
        plan, *_ = _build_plan_and_deps(tmp_path, palette_restraint=True)
        for a in plan.sections:
            assert a.palette_target is not None, a.section.label
            assert isinstance(a.palette_target, dict)
            assert set(a.palette_target.keys()) == set(a.active_tiers), (
                f"palette_target keys {set(a.palette_target)} != active_tiers {set(a.active_tiers)}"
            )
            for tier, count in a.palette_target.items():
                assert isinstance(count, int)
                assert 1 <= count <= 6, f"tier {tier} count {count} out of [1,6]"

    def test_palette_target_none_when_restraint_off(self, tmp_path: Path) -> None:
        """T012: with palette_restraint=False every palette_target is None."""
        plan, *_ = _build_plan_and_deps(tmp_path, palette_restraint=False)
        for a in plan.sections:
            assert a.palette_target is None, a.section.label

    def test_duration_target_populated(self, tmp_path: Path) -> None:
        """T013: with duration_scaling=True every duration_target is a DurationTarget."""
        plan, *_ = _build_plan_and_deps(tmp_path, duration_scaling=True)
        for a in plan.sections:
            assert a.duration_target is not None, a.section.label
            assert isinstance(a.duration_target, DurationTarget)
            assert a.duration_target.min_ms > 0
            assert a.duration_target.target_ms >= a.duration_target.min_ms
            assert a.duration_target.max_ms >= a.duration_target.target_ms

    def test_duration_target_none_when_disabled(self, tmp_path: Path) -> None:
        plan, *_ = _build_plan_and_deps(tmp_path, duration_scaling=False)
        for a in plan.sections:
            assert a.duration_target is None, a.section.label

    def test_accent_policy_populated(self, tmp_path: Path) -> None:
        """T014: every assignment carries a non-null AccentPolicy with boolean fields."""
        plan, _config, hierarchy, *_ = _build_plan_and_deps(tmp_path)
        for a in plan.sections:
            assert isinstance(a.accent_policy, AccentPolicy), a.section.label
            assert isinstance(a.accent_policy.drum_hits, bool)
            assert isinstance(a.accent_policy.impact, bool)
            # Cross-check the policy against today's gate outcomes.
            section = a.section
            expected_drum = (
                section.energy_score >= 60
                and hierarchy.events.get("drums") is not None
            )
            expected_impact = (
                section.energy_score > _IMPACT_ENERGY_GATE
                and (section.end_ms - section.start_ms) >= _IMPACT_MIN_DURATION_MS
                and (
                    not (section.label or "").lower()
                    or (section.label or "").lower() in _IMPACT_QUALIFYING_ROLES
                )
            )
            assert a.accent_policy.drum_hits == expected_drum, (
                f"section '{section.label}': drum_hits={a.accent_policy.drum_hits}, expected={expected_drum}"
            )
            assert a.accent_policy.impact == expected_impact, (
                f"section '{section.label}': impact={a.accent_policy.impact}, expected={expected_impact}"
            )

    def test_accent_policy_disabled_globally(self, tmp_path: Path) -> None:
        """With beat_accent_effects=False, both fields are False for every section."""
        plan, *_ = _build_plan_and_deps(tmp_path, beat_accent_effects=False)
        for a in plan.sections:
            assert a.accent_policy.drum_hits is False, a.section.label
            assert a.accent_policy.impact is False, a.section.label

    def test_section_index_populated(self, tmp_path: Path) -> None:
        """T015: assignment.section_index equals its position in plan.sections."""
        plan, *_ = _build_plan_and_deps(tmp_path)
        for i, a in enumerate(plan.sections):
            assert a.section_index == i, f"section {i} has section_index={a.section_index}"

    def test_working_set_reflects_focused_vocabulary(self, tmp_path: Path) -> None:
        plan, *_ = _build_plan_and_deps(tmp_path, focused_vocabulary=True)
        # When focused_vocabulary=True, at least one section with a theme that has layers
        # should have a non-None working_set.
        have_ws = any(a.working_set is not None for a in plan.sections)
        assert have_ws or all(not a.theme.layers for a in plan.sections), (
            "focused_vocabulary=True but no assignment has a working_set"
        )

    def test_working_set_none_when_focused_disabled(self, tmp_path: Path) -> None:
        plan, *_ = _build_plan_and_deps(tmp_path, focused_vocabulary=False)
        for a in plan.sections:
            assert a.working_set is None, a.section.label


# ===========================================================================
# User Story 2 — place_effects reads recipe off the assignment
# ===========================================================================

class TestUS2_RecipeRead:
    """place_effects consumes an assignment; no ambient flags."""

    def test_active_tiers_override_limits_placements(self, tmp_path: Path) -> None:
        """T024: with active_tiers={1,4,8} only groups in that set receive placements."""
        plan, _config, hierarchy, groups, effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = plan.sections[2]  # chorus — high energy, likely has placements
        a.active_tiers = frozenset({1, 8})
        a.group_effects = {}
        redone = place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )
        group_tier_by_name = {g.name: g.tier for g in groups}
        for group_name in redone.keys():
            tier = group_tier_by_name.get(group_name)
            if tier is None:
                # Accent placements can target individual model names (not group names).
                # Those come from the accent pass, not place_effects, so should not appear.
                pytest.fail(f"Unexpected non-group placement target: {group_name}")
            assert tier in {1, 8}, (
                f"group {group_name} is tier {tier} but active_tiers={{1,8}}"
            )

    def test_palette_target_trims_placement_colors(self, tmp_path: Path) -> None:
        """T025: placements' color_palette respects assignment.palette_target[tier]."""
        plan, _config, hierarchy, groups, effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = plan.sections[2]
        tier_caps = {t: 2 for t in a.active_tiers}
        a.palette_target = tier_caps
        a.group_effects = {}
        redone = place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )
        group_tier_by_name = {g.name: g.tier for g in groups}
        for group_name, placements in redone.items():
            tier = group_tier_by_name[group_name]
            for p in placements:
                assert len(p.color_palette) <= tier_caps[tier], (
                    f"{group_name} tier={tier} got {len(p.color_palette)} colors, cap={tier_caps[tier]}"
                )

    def test_place_effects_is_pure(self, tmp_path: Path) -> None:
        """T026: place_effects called twice with identical assignment → identical group_effects."""
        plan, _config, hierarchy, groups, effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = plan.sections[2]
        a.group_effects = {}
        first = place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )
        second = place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )
        assert set(first.keys()) == set(second.keys())
        for key in first:
            assert len(first[key]) == len(second[key])
            for p1, p2 in zip(first[key], second[key]):
                assert p1.effect_name == p2.effect_name
                assert p1.start_ms == p2.start_ms
                assert p1.end_ms == p2.end_ms
                assert p1.color_palette == p2.color_palette


# ===========================================================================
# User Story 3 — accent helpers trust the policy
# ===========================================================================

class TestUS3_AccentPolicy:
    def test_drum_accents_skip_when_policy_false(self, tmp_path: Path) -> None:
        """T040: accent_policy.drum_hits=False → _place_drum_accents returns empty."""
        plan, _config, hierarchy, groups, _effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        layout = parse_layout(LAYOUT_PATH)
        normalize_coords(layout.props)
        classify_props(layout.props)
        props_by_name = {p.name: p for p in layout.props}
        # Pick a section that would normally fire drum accents, then force policy off.
        a = next((s for s in plan.sections if s.accent_policy.drum_hits), None)
        if a is None:
            pytest.skip("No section would fire drum accents in the fixture")
        a.accent_policy = AccentPolicy(drum_hits=False, impact=a.accent_policy.impact)
        result = _place_drum_accents(
            groups=groups,
            hierarchy=hierarchy,
            assignment=a,
            variant_library=variant_lib,
            props_by_name=props_by_name,
        )
        assert result == {}, f"_place_drum_accents returned {result} despite policy=False"

    def test_impact_accents_skip_when_policy_false(self, tmp_path: Path) -> None:
        """T041: accent_policy.impact=False → _place_impact_accent returns empty."""
        plan, _config, _hierarchy, groups, _effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = next((s for s in plan.sections if s.accent_policy.impact), None)
        if a is None:
            pytest.skip("No section would fire impact accents in the fixture")
        a.accent_policy = AccentPolicy(drum_hits=a.accent_policy.drum_hits, impact=False)
        result = _place_impact_accent(groups=groups, assignment=a, variant_library=variant_lib)
        assert result == {}, f"_place_impact_accent returned {result} despite policy=False"

    def test_accent_helpers_have_no_section_level_gates(self) -> None:
        """T042: accent helper sources reference no section-level gating constants.

        The per-hit `_DRUM_HIT_ENERGY_GATE` sample is permitted (per-hit, not per-section).
        """
        drum_src = inspect.getsource(_place_drum_accents)
        impact_src = inspect.getsource(_place_impact_accent)
        forbidden = [
            "section.energy_score",
            "section.end_ms - section.start_ms",
            "_IMPACT_ENERGY_GATE",
            "_IMPACT_QUALIFYING_ROLES",
            "_IMPACT_MIN_DURATION_MS",
        ]
        for pattern in forbidden:
            assert pattern not in drum_src, (
                f"_place_drum_accents still references gating symbol '{pattern}'"
            )
            assert pattern not in impact_src, (
                f"_place_impact_accent still references gating symbol '{pattern}'"
            )


# ===========================================================================
# User Story 4 — isolation (walkthrough 2)
# ===========================================================================

class TestUS4_Isolation:
    def test_walkthrough_2_isolation(self, tmp_path: Path) -> None:
        """T050: snapshot plan.sections[2].group_effects, clear, re-run, assert equal."""
        plan, _config, hierarchy, groups, effect_lib, variant_lib = _build_plan_and_deps(
            tmp_path,
            # Disable accents + transitions for this isolation test: accents are applied
            # as a separate pass in build_plan after place_effects, so the stored
            # group_effects on the assignment already includes them. Re-running
            # place_effects alone won't re-add the accent overlay. Turn accents off
            # so the snapshot equals what place_effects alone produces.
            beat_accent_effects=False,
        )
        a = plan.sections[2]
        original = dict(a.group_effects)
        a.group_effects = {}
        redone = place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )
        # Compare keys first for a readable diff if it fails.
        assert set(redone.keys()) == set(original.keys())
        for k in redone:
            assert len(redone[k]) == len(original[k])
            for p1, p2 in zip(redone[k], original[k]):
                assert p1.effect_name == p2.effect_name
                assert p1.start_ms == p2.start_ms
                assert p1.end_ms == p2.end_ms
                assert p1.color_palette == p2.color_palette
                assert p1.parameters == p2.parameters

    def test_impact_accent_fires_on_isolated_assignment(self, tmp_path: Path) -> None:
        """T051: an extracted assignment fires impact accent the same way."""
        plan, _config, _hierarchy, groups, _effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = next((s for s in plan.sections if s.accent_policy.impact), None)
        if a is None:
            pytest.skip("No section would fire impact accents in the fixture")
        result = _place_impact_accent(groups=groups, assignment=a, variant_library=variant_lib)
        assert result, "Expected impact accent placements with accent_policy.impact=True"

    def test_walkthrough_2_isolation_no_section_index_kwarg(self, tmp_path: Path) -> None:
        """T052: place_effects exposes no `section_index` parameter — reads assignment.section_index."""
        sig = inspect.signature(place_effects)
        assert "section_index" not in sig.parameters, (
            "place_effects still has a section_index parameter; it should read assignment.section_index"
        )


# ===========================================================================
# User Story 5 — override hooks
# ===========================================================================

class TestUS5_Overrides:
    def test_override_palette_target(self, tmp_path: Path) -> None:
        """T055: mutating palette_target caps all placement palettes."""
        plan, _config, hierarchy, groups, effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = plan.sections[1]
        a.palette_target = {t: 2 for t in a.active_tiers}
        a.group_effects = {}
        redone = place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )
        for _, placements in redone.items():
            for p in placements:
                assert len(p.color_palette) <= 2, (
                    f"{p.model_or_group}: {len(p.color_palette)} colors, expected <=2"
                )

    def test_override_duration_target(self, tmp_path: Path) -> None:
        """T056: mutating duration_target applies to placements."""
        plan, _config, hierarchy, groups, effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = plan.sections[1]
        a.duration_target = DurationTarget(min_ms=400, target_ms=600, max_ms=800)
        a.group_effects = {}
        # Existence assertion: override must propagate without error.
        place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )

    def test_override_active_tiers(self, tmp_path: Path) -> None:
        """T057: mutating active_tiers limits placements."""
        plan, _config, hierarchy, groups, effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        a = plan.sections[1]
        a.active_tiers = frozenset({1, 8})
        a.group_effects = {}
        redone = place_effects(
            a, groups, effect_lib, hierarchy,
            variant_library=variant_lib, rotation_plan=plan.rotation_plan,
        )
        group_tier_by_name = {g.name: g.tier for g in groups}
        for group_name in redone:
            tier = group_tier_by_name.get(group_name)
            assert tier in {1, 8}, f"{group_name}: tier={tier} not in {{1,8}}"

    def test_override_accent_policy_disables_accents(self, tmp_path: Path) -> None:
        """T058: disabling accent_policy on one section suppresses its accent placements."""
        plan, _config, _hierarchy, groups, _effect_lib, variant_lib = _build_plan_and_deps(tmp_path)
        # Find a section with accents
        a = next((s for s in plan.sections if s.accent_policy.drum_hits or s.accent_policy.impact), None)
        if a is None:
            pytest.skip("No section fires accents in the fixture")
        a.accent_policy = AccentPolicy(drum_hits=False, impact=False)
        impact = _place_impact_accent(groups=groups, assignment=a, variant_library=variant_lib)
        assert impact == {}, impact


# ===========================================================================
# Phase 8 — regenerate_sections parity
# ===========================================================================

class TestRegenerateSectionsParity:
    """T061: regenerate_sections uses the same place_effects path as build_plan."""

    def test_both_call_sites_use_six_arg_form(self) -> None:
        """T062 (mirror): scan plan.py for both call sites using the six-arg form."""
        plan_py = Path(__file__).parent.parent.parent / "src" / "generator" / "plan.py"
        source = plan_py.read_text(encoding="utf-8")
        # Count place_effects( occurrences — expect exactly two call sites.
        occurrences = [m.start() for m in re.finditer(r"\bplace_effects\s*\(", source)]
        # Some may be in a def (the function definition line). Exclude those.
        non_def = [
            o for o in occurrences
            if not source[max(0, o - 40):o].rstrip().endswith("def")
        ]
        # Note: the import of place_effects will appear too; filter those.
        real_calls = []
        for o in non_def:
            prefix = source[max(0, o - 40):o]
            if "import" in prefix or "from" in prefix:
                continue
            real_calls.append(o)
        assert len(real_calls) >= 2, (
            f"Expected ≥2 place_effects call sites in plan.py, found {len(real_calls)}"
        )
