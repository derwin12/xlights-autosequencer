"""Unit tests for src/generator/transitions.py — dataclasses, duration math, crossfades, fadeout."""
from __future__ import annotations

import pytest

from src.generator.models import EffectPlacement, SectionAssignment, SectionEnergy
from src.generator.transitions import (
    VALID_FADEOUT_STRATEGIES,
    VALID_MODES,
    CrossfadeRegion,
    FadeOutPlan,
    TransitionConfig,
    apply_crossfades,
    apply_fadeout,
    apply_transitions,
    build_fadeout_plan,
    compute_crossfade_duration,
    detect_same_effect_continuation,
)
from src.themes.models import Theme, EffectLayer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_theme(name: str = "Test", transition_mode: str | None = None) -> Theme:
    return Theme(
        name=name,
        mood="structural",
        occasion="general",
        genre="any",
        intent="test",
        layers=[EffectLayer(variant="Fire")],
        palette=["#FF0000"],
        transition_mode=transition_mode,
    )


def _make_section(label: str, start_ms: int, end_ms: int, energy: int = 50) -> SectionEnergy:
    return SectionEnergy(
        label=label,
        start_ms=start_ms,
        end_ms=end_ms,
        energy_score=energy,
        mood_tier="structural",
        impact_count=0,
    )


def _make_placement(
    effect_name: str = "Fire",
    xlights_id: str = "E_FIRE",
    start_ms: int = 0,
    end_ms: int = 10000,
    params: dict | None = None,
) -> EffectPlacement:
    return EffectPlacement(
        effect_name=effect_name,
        xlights_id=xlights_id,
        model_or_group="01_BASE_ALL",
        start_ms=start_ms,
        end_ms=end_ms,
        parameters=params or {},
    )


def _make_assignment(
    label: str, start_ms: int, end_ms: int,
    group_effects: dict | None = None,
    theme: Theme | None = None,
) -> SectionAssignment:
    return SectionAssignment(
        section=_make_section(label, start_ms, end_ms),
        theme=theme or _make_theme(),
        group_effects=group_effects or {},
    )


# ---------------------------------------------------------------------------
# T003: TransitionConfig dataclass
# ---------------------------------------------------------------------------

class TestTransitionConfig:
    def test_default_values(self):
        cfg = TransitionConfig()
        assert cfg.mode == "subtle"
        assert cfg.snap_window_ms is None
        assert cfg.fadeout_strategy == "progressive"
        assert cfg.abrupt_end_fade_ms == 3000

    def test_explicit_values(self):
        cfg = TransitionConfig(mode="dramatic", fadeout_strategy="uniform", abrupt_end_fade_ms=5000)
        assert cfg.mode == "dramatic"
        assert cfg.fadeout_strategy == "uniform"
        assert cfg.abrupt_end_fade_ms == 5000

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode must be one of"):
            TransitionConfig(mode="fast")

    def test_invalid_fadeout_strategy_raises(self):
        with pytest.raises(ValueError, match="fadeout_strategy must be one of"):
            TransitionConfig(fadeout_strategy="instant")

    def test_none_mode_valid(self):
        cfg = TransitionConfig(mode="none")
        assert cfg.mode == "none"

    def test_all_valid_modes(self):
        for mode in VALID_MODES:
            cfg = TransitionConfig(mode=mode)
            assert cfg.mode == mode

    def test_all_valid_fadeout_strategies(self):
        for strategy in VALID_FADEOUT_STRATEGIES:
            cfg = TransitionConfig(fadeout_strategy=strategy)
            assert cfg.fadeout_strategy == strategy


class TestCrossfadeRegion:
    def test_construction(self):
        region = CrossfadeRegion(
            boundary_ms=10000,
            section_a_index=0,
            section_b_index=1,
            fade_duration_ms=500,
        )
        assert region.boundary_ms == 10000
        assert region.fade_duration_ms == 500
        assert region.skip_groups == set()

    def test_with_skip_groups(self):
        region = CrossfadeRegion(
            boundary_ms=10000,
            section_a_index=0,
            section_b_index=1,
            fade_duration_ms=500,
            skip_groups={"01_BASE_ALL", "08_HERO_TREE"},
        )
        assert "01_BASE_ALL" in region.skip_groups


class TestFadeOutPlan:
    def test_construction(self):
        plan = FadeOutPlan(
            start_ms=50000,
            end_ms=60000,
            is_outro=True,
            tier_offsets={8: 0.0, 1: 0.8},
        )
        assert plan.start_ms == 50000
        assert plan.is_outro is True
        assert plan.tier_offsets[8] == 0.0


# ---------------------------------------------------------------------------
# T004: compute_crossfade_duration
# ---------------------------------------------------------------------------

class TestComputeCrossfadeDuration:
    def test_none_mode_returns_zero(self):
        assert compute_crossfade_duration(120, "none", 10000) == 0

    def test_subtle_mode_returns_one_beat(self):
        # 120 BPM → beat = 500ms
        result = compute_crossfade_duration(120, "subtle", 10000)
        assert result == 500

    def test_dramatic_mode_returns_one_bar(self):
        # 120 BPM → bar = 2000ms
        result = compute_crossfade_duration(120, "dramatic", 20000)
        assert result == 2000

    def test_subtle_at_80_bpm(self):
        # 80 BPM → beat = 750ms
        result = compute_crossfade_duration(80, "subtle", 10000)
        assert result == 750

    def test_subtle_at_150_bpm(self):
        # 150 BPM → beat = 400ms
        result = compute_crossfade_duration(150, "subtle", 10000)
        assert result == 400

    def test_dramatic_at_80_bpm(self):
        # 80 BPM → bar = 3000ms
        result = compute_crossfade_duration(80, "dramatic", 20000)
        assert result == 3000

    def test_dramatic_at_150_bpm(self):
        # 150 BPM → bar = 1600ms
        result = compute_crossfade_duration(150, "dramatic", 20000)
        assert result == 1600

    def test_clamped_to_half_section_subtle(self):
        # Short section: 500ms total → max = 250ms
        # 120 BPM → beat = 500ms, but clamped to 250
        result = compute_crossfade_duration(120, "subtle", 500)
        assert result == 250

    def test_clamped_to_half_section_dramatic(self):
        # Section = 2000ms → max = 1000ms
        # 80 BPM → bar = 3000ms, clamped to 1000
        result = compute_crossfade_duration(80, "dramatic", 2000)
        assert result == 1000

    def test_unknown_mode_returns_zero(self):
        result = compute_crossfade_duration(120, "unknown", 10000)
        assert result == 0


# ---------------------------------------------------------------------------
# T005: Theme.transition_mode field
# ---------------------------------------------------------------------------

class TestThemeTransitionMode:
    def test_default_transition_mode_is_none(self):
        theme = _make_theme()
        assert theme.transition_mode is None

    def test_from_dict_without_transition_mode(self):
        data = {
            "name": "Test",
            "mood": "structural",
            "occasion": "general",
            "genre": "any",
            "intent": "test",
            "layers": [{"variant": "Fire", "blend_mode": "Normal"}],
            "palette": ["#FF0000"],
        }
        theme = Theme.from_dict(data)
        assert theme.transition_mode is None

    def test_from_dict_with_transition_mode(self):
        data = {
            "name": "Test",
            "mood": "structural",
            "occasion": "general",
            "genre": "any",
            "intent": "test",
            "layers": [{"variant": "Fire", "blend_mode": "Normal"}],
            "palette": ["#FF0000"],
            "transition_mode": "dramatic",
        }
        theme = Theme.from_dict(data)
        assert theme.transition_mode == "dramatic"

    def test_to_dict_omits_none_transition_mode(self):
        theme = _make_theme()
        d = theme.to_dict()
        assert "transition_mode" not in d

    def test_to_dict_includes_transition_mode_when_set(self):
        theme = _make_theme(transition_mode="subtle")
        d = theme.to_dict()
        assert d["transition_mode"] == "subtle"

    def test_roundtrip_with_transition_mode(self):
        theme = _make_theme(transition_mode="none")
        d = theme.to_dict()
        theme2 = Theme.from_dict(d)
        assert theme2.transition_mode == "none"

    def test_roundtrip_without_transition_mode(self):
        theme = _make_theme()
        d = theme.to_dict()
        theme2 = Theme.from_dict(d)
        assert theme2.transition_mode is None


# ---------------------------------------------------------------------------
# detect_same_effect_continuation
# ---------------------------------------------------------------------------

class TestDetectSameEffectContinuation:
    def test_identical_placements_are_continuation(self):
        p1 = _make_placement(params={"speed": 10})
        p2 = _make_placement(params={"speed": 10})
        assert detect_same_effect_continuation(p1, p2) is True

    def test_different_effect_name(self):
        p1 = _make_placement(effect_name="Fire")
        p2 = _make_placement(effect_name="Meteors")
        assert detect_same_effect_continuation(p1, p2) is False

    def test_different_xlights_id(self):
        p1 = _make_placement(xlights_id="E_FIRE")
        p2 = _make_placement(xlights_id="E_METEORS")
        assert detect_same_effect_continuation(p1, p2) is False

    def test_params_within_10_percent_tolerance(self):
        # 10 vs 10.05 — within 10% tolerance
        p1 = _make_placement(params={"speed": 10.0})
        p2 = _make_placement(params={"speed": 10.5})
        assert detect_same_effect_continuation(p1, p2) is True

    def test_params_outside_10_percent_tolerance(self):
        # 10 vs 12 — 20% difference
        p1 = _make_placement(params={"speed": 10.0})
        p2 = _make_placement(params={"speed": 12.0})
        assert detect_same_effect_continuation(p1, p2) is False

    def test_different_param_keys(self):
        p1 = _make_placement(params={"speed": 10})
        p2 = _make_placement(params={"color": "red"})
        assert detect_same_effect_continuation(p1, p2) is False

    def test_both_zero_params(self):
        p1 = _make_placement(params={"speed": 0})
        p2 = _make_placement(params={"speed": 0})
        assert detect_same_effect_continuation(p1, p2) is True

    def test_string_params_must_match_exactly(self):
        p1 = _make_placement(params={"dir": "left"})
        p2 = _make_placement(params={"dir": "right"})
        assert detect_same_effect_continuation(p1, p2) is False


# ---------------------------------------------------------------------------
# T008: apply_crossfades — US1
# ---------------------------------------------------------------------------

class TestApplyCrossfades:
    def test_different_effects_get_fades(self):
        """Adjacent sections with different effects should get non-zero fades."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE", start_ms=0, end_ms=10000)
        p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS", start_ms=10000, end_ms=20000)

        a = _make_assignment("verse", 0, 10000, group_effects={"01_BASE_ALL": [p_a]})
        b = _make_assignment("chorus", 10000, 20000, group_effects={"01_BASE_ALL": [p_b]})

        config = TransitionConfig(mode="subtle")
        apply_crossfades([a, b], config, bpm=120)

        assert p_a.fade_out_ms > 0
        assert p_b.fade_in_ms > 0

    def test_same_effect_continuation_skips_fade(self):
        """Same effect continuing across boundary should have no crossfade."""
        p_a = _make_placement(params={"speed": 10})
        p_b = _make_placement(params={"speed": 10})

        a = _make_assignment("verse", 0, 10000, group_effects={"01_BASE_ALL": [p_a]})
        b = _make_assignment("chorus", 10000, 20000, group_effects={"01_BASE_ALL": [p_b]})

        config = TransitionConfig(mode="subtle")
        apply_crossfades([a, b], config, bpm=120)

        assert p_a.fade_out_ms == 0
        assert p_b.fade_in_ms == 0

    def test_mode_none_skips_all_fades(self):
        """'none' mode should produce zero fades on all groups."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
        p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS")

        a = _make_assignment("verse", 0, 10000, group_effects={"01_BASE_ALL": [p_a]})
        b = _make_assignment("chorus", 10000, 20000, group_effects={"01_BASE_ALL": [p_b]})

        config = TransitionConfig(mode="none")
        apply_crossfades([a, b], config, bpm=120)

        assert p_a.fade_out_ms == 0
        assert p_b.fade_in_ms == 0

    def test_dramatic_produces_longer_fades_than_subtle(self):
        """Dramatic mode should produce longer fades than subtle mode."""
        def get_fades(mode: str) -> tuple[int, int]:
            p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
            p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS")
            a = _make_assignment("verse", 0, 20000, group_effects={"g": [p_a]})
            b = _make_assignment("chorus", 20000, 40000, group_effects={"g": [p_b]})
            apply_crossfades([a, b], TransitionConfig(mode=mode), bpm=120)
            return p_a.fade_out_ms, p_b.fade_in_ms

        out_subtle, in_subtle = get_fades("subtle")
        out_dramatic, in_dramatic = get_fades("dramatic")

        assert out_dramatic > out_subtle
        assert in_dramatic > in_subtle

    def test_single_assignment_is_noop(self):
        """Only one section — nothing to crossfade."""
        p = _make_placement()
        a = _make_assignment("verse", 0, 10000, group_effects={"g": [p]})
        apply_crossfades([a], TransitionConfig(), bpm=120)
        assert p.fade_out_ms == 0
        assert p.fade_in_ms == 0

    def test_group_only_in_one_section_gets_no_fade(self):
        """Group absent in one section — no fade on its placements."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
        a = _make_assignment("verse", 0, 10000, group_effects={"08_HERO": [p_a]})
        b = _make_assignment("chorus", 10000, 20000, group_effects={})

        apply_crossfades([a, b], TransitionConfig(mode="subtle"), bpm=120)
        assert p_a.fade_out_ms == 0

    def test_fade_applied_to_last_and_first_placements(self):
        """Fade should be on the last of section A and first of section B."""
        p_a1 = _make_placement(effect_name="Fire", xlights_id="E_FIRE", start_ms=0, end_ms=5000)
        p_a2 = _make_placement(effect_name="Fire", xlights_id="E_FIRE", start_ms=5000, end_ms=10000)
        p_b1 = _make_placement(effect_name="Meteors", xlights_id="E_METEORS", start_ms=10000, end_ms=15000)
        p_b2 = _make_placement(effect_name="Meteors", xlights_id="E_METEORS", start_ms=15000, end_ms=20000)

        a = _make_assignment("verse", 0, 10000, group_effects={"g": [p_a1, p_a2]})
        b = _make_assignment("chorus", 10000, 20000, group_effects={"g": [p_b1, p_b2]})

        apply_crossfades([a, b], TransitionConfig(mode="subtle"), bpm=120)

        assert p_a1.fade_out_ms == 0  # not last
        assert p_a2.fade_out_ms > 0   # last in A
        assert p_b1.fade_in_ms > 0    # first in B
        assert p_b2.fade_in_ms == 0   # not first


# ---------------------------------------------------------------------------
# T013/T014: build_fadeout_plan + apply_fadeout — US2
# ---------------------------------------------------------------------------

class TestBuildFadeoutPlan:
    def test_outro_section_uses_full_section(self):
        """Outro label → start_ms/end_ms match section bounds."""
        section = _make_section("outro", 50000, 70000)
        a = _make_assignment("outro", 50000, 70000)
        plan = build_fadeout_plan([a], fadeout_strategy="progressive")
        assert plan is not None
        assert plan.start_ms == 50000
        assert plan.end_ms == 70000
        assert plan.is_outro is True

    def test_non_outro_uses_abrupt_end_fade(self):
        """Non-outro section uses last abrupt_end_fade_ms of section."""
        a = _make_assignment("chorus", 0, 30000)
        plan = build_fadeout_plan([a], fadeout_strategy="progressive", abrupt_end_fade_ms=3000)
        assert plan is not None
        assert plan.end_ms == 30000
        assert plan.start_ms == 27000  # 30000 - 3000
        assert plan.is_outro is False

    def test_progressive_long_outro_staggered(self):
        """Outro > 8s with progressive strategy → different tier offsets."""
        a = _make_assignment("outro", 0, 20000)
        plan = build_fadeout_plan([a], fadeout_strategy="progressive")
        assert plan is not None
        # Hero tier should start earlier (lower offset) than base tier
        assert plan.tier_offsets[8] < plan.tier_offsets[1]
        assert plan.tier_offsets[8] == 0.0

    def test_progressive_short_outro_uniform(self):
        """Short outro (< 8s) with progressive strategy → uniform (all 0.0)."""
        a = _make_assignment("outro", 0, 5000)
        plan = build_fadeout_plan([a], fadeout_strategy="progressive")
        assert plan is not None
        # All offsets should be 0.0 (uniform) since outro < 8s
        for offset in plan.tier_offsets.values():
            assert offset == 0.0

    def test_uniform_strategy_all_zero_offsets(self):
        """Uniform strategy → all tiers start fading at same time."""
        a = _make_assignment("outro", 0, 20000)
        plan = build_fadeout_plan([a], fadeout_strategy="uniform")
        assert plan is not None
        for offset in plan.tier_offsets.values():
            assert offset == 0.0

    def test_empty_assignments_returns_none(self):
        plan = build_fadeout_plan([], fadeout_strategy="progressive")
        assert plan is None

    def test_fadeout_end_ms_matches_song_end(self):
        """end_ms should match the final section's end."""
        a = _make_assignment("outro", 50000, 90000)
        plan = build_fadeout_plan([a], fadeout_strategy="progressive")
        assert plan.end_ms == 90000


class TestApplyFadeout:
    def test_hero_tier_gets_largest_fade(self):
        """Hero tier (08_) should have the longest fade_out_ms."""
        p_hero = _make_placement()
        p_base = _make_placement()

        a = _make_assignment("outro", 0, 20000, group_effects={
            "08_HERO_TREE": [p_hero],
            "01_BASE_ALL": [p_base],
        })

        plan = FadeOutPlan(
            start_ms=0,
            end_ms=20000,
            is_outro=True,
            tier_offsets={8: 0.0, 1: 0.8},
        )
        apply_fadeout([a], plan)

        # Hero: (1.0 - 0.0) * 20000 = 20000
        assert p_hero.fade_out_ms == 20000
        # Base: (1.0 - 0.8) * 20000 = 4000
        assert p_base.fade_out_ms == 4000
        assert p_hero.fade_out_ms > p_base.fade_out_ms

    def test_abrupt_ending_all_tiers_equal(self):
        """Uniform offsets → all tiers get same fade_out_ms."""
        p1 = _make_placement()
        p2 = _make_placement()
        p3 = _make_placement()

        a = _make_assignment("chorus", 0, 10000, group_effects={
            "08_HERO": [p1],
            "06_PROP_ARCH": [p2],
            "01_BASE_ALL": [p3],
        })

        plan = FadeOutPlan(
            start_ms=7000,
            end_ms=10000,
            is_outro=False,
            tier_offsets={8: 0.0, 6: 0.0, 1: 0.0},
        )
        apply_fadeout([a], plan)

        assert p1.fade_out_ms == 3000
        assert p2.fade_out_ms == 3000
        assert p3.fade_out_ms == 3000

    def test_only_last_placement_in_group_gets_fade(self):
        """Fade should only apply to the last placement in each group."""
        p1 = _make_placement(start_ms=0, end_ms=5000)
        p2 = _make_placement(start_ms=5000, end_ms=10000)

        a = _make_assignment("outro", 0, 10000, group_effects={"08_HERO": [p1, p2]})
        plan = FadeOutPlan(start_ms=0, end_ms=10000, is_outro=True, tier_offsets={8: 0.0})
        apply_fadeout([a], plan)

        assert p1.fade_out_ms == 0   # not last
        assert p2.fade_out_ms == 10000  # last

    def test_empty_group_is_skipped(self):
        """Groups with no placements should not crash."""
        a = _make_assignment("outro", 0, 10000, group_effects={"08_HERO": []})
        plan = FadeOutPlan(start_ms=0, end_ms=10000, is_outro=True, tier_offsets={8: 0.0})
        apply_fadeout([a], plan)  # should not raise


# ---------------------------------------------------------------------------
# T021: Mode override logic — US4
# ---------------------------------------------------------------------------

class TestModeOverrideLogic:
    def test_theme_transition_mode_overrides_global(self):
        """theme.transition_mode='none' should override global 'subtle'."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
        p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS")

        # Outgoing section theme has transition_mode="none"
        theme_no_transition = _make_theme(transition_mode="none")
        a = _make_assignment("verse", 0, 10000,
                             group_effects={"g": [p_a]},
                             theme=theme_no_transition)
        b = _make_assignment("chorus", 10000, 20000, group_effects={"g": [p_b]})

        config = TransitionConfig(mode="subtle")
        apply_crossfades([a, b], config, bpm=120)

        # Theme override "none" → no fades
        assert p_a.fade_out_ms == 0
        assert p_b.fade_in_ms == 0

    def test_none_theme_mode_falls_back_to_global(self):
        """theme.transition_mode=None should use global config mode."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
        p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS")

        a = _make_assignment("verse", 0, 10000, group_effects={"g": [p_a]})
        b = _make_assignment("chorus", 10000, 20000, group_effects={"g": [p_b]})

        config = TransitionConfig(mode="subtle")
        apply_crossfades([a, b], config, bpm=120)

        # Falls back to "subtle" → non-zero fades
        assert p_a.fade_out_ms > 0
        assert p_b.fade_in_ms > 0

    def test_subtle_and_dramatic_produce_different_durations(self):
        """Different modes should produce different fade durations."""
        def get_fade(mode: str) -> int:
            p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
            p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS")
            a = _make_assignment("verse", 0, 20000, group_effects={"g": [p_a]})
            b = _make_assignment("chorus", 20000, 40000, group_effects={"g": [p_b]})
            apply_crossfades([a, b], TransitionConfig(mode=mode), bpm=120)
            return p_a.fade_out_ms

        assert get_fade("subtle") != get_fade("dramatic")
        assert get_fade("none") == 0

    def test_theme_invalid_transition_mode_raises(self):
        """Invalid transition_mode on a theme should raise ValueError."""
        with pytest.raises(ValueError, match="transition_mode must be"):
            _make_theme(transition_mode="blazing_fast")

    def test_theme_dramatic_overrides_global_none(self):
        """theme.transition_mode='dramatic' should apply even if global is 'none'."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
        p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS")

        theme_dramatic = _make_theme(transition_mode="dramatic")
        a = _make_assignment("verse", 0, 20000,
                             group_effects={"g": [p_a]},
                             theme=theme_dramatic)
        b = _make_assignment("chorus", 20000, 40000, group_effects={"g": [p_b]})

        config = TransitionConfig(mode="none")
        apply_crossfades([a, b], config, bpm=120)

        # Theme override "dramatic" → fades present
        assert p_a.fade_out_ms > 0


# ---------------------------------------------------------------------------
# apply_transitions — combined entry point
# ---------------------------------------------------------------------------

class TestApplyTransitions:
    def test_crossfade_and_fadeout_combined(self):
        """apply_transitions should apply both crossfades and fadeout in one call."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
        p_b_first = _make_placement(effect_name="Meteors", xlights_id="E_METEORS", start_ms=10000, end_ms=15000)
        p_b_last = _make_placement(effect_name="Meteors", xlights_id="E_METEORS", start_ms=15000, end_ms=20000)

        a = _make_assignment("verse", 0, 10000, group_effects={"08_HERO": [p_a]})
        b = _make_assignment("outro", 10000, 20000, group_effects={"08_HERO": [p_b_first, p_b_last]})

        config = TransitionConfig(mode="subtle", fadeout_strategy="progressive")
        apply_transitions([a, b], config, bpm=120)

        # Crossfade: verse→outro boundary
        assert p_a.fade_out_ms > 0, "Crossfade should set fade_out on outgoing"
        assert p_b_first.fade_in_ms > 0, "Crossfade should set fade_in on incoming"
        # Fadeout: last placement in outro should have fade_out
        assert p_b_last.fade_out_ms > 0, "Fadeout should set fade_out on last outro placement"

    def test_fadeout_preserves_larger_crossfade(self):
        """If crossfade set a larger fade_out_ms than fadeout would, keep the larger value."""
        p_last = _make_placement(effect_name="Fire", xlights_id="E_FIRE", start_ms=0, end_ms=5000)

        # Single short section — abrupt fade will be 3000ms
        a = _make_assignment("chorus", 0, 5000, group_effects={"08_HERO": [p_last]})
        # Manually set a larger fade from a hypothetical crossfade pass
        p_last.fade_out_ms = 9999

        from src.generator.transitions import apply_fadeout, FadeOutPlan
        plan = FadeOutPlan(start_ms=2000, end_ms=5000, is_outro=False, tier_offsets={8: 0.0})
        apply_fadeout([a], plan)

        # Fadeout would set 3000ms, but existing 9999 is larger — should keep 9999
        assert p_last.fade_out_ms == 9999

    def test_mode_none_fadeout_none_produces_all_zeros(self):
        """mode=none + fadeout_strategy=none → zero fades everywhere."""
        p_a = _make_placement(effect_name="Fire", xlights_id="E_FIRE")
        p_b = _make_placement(effect_name="Meteors", xlights_id="E_METEORS")

        a = _make_assignment("verse", 0, 10000, group_effects={"g": [p_a]})
        b = _make_assignment("outro", 10000, 20000, group_effects={"g": [p_b]})

        config = TransitionConfig(mode="none", fadeout_strategy="none")
        apply_transitions([a, b], config, bpm=120)

        assert p_a.fade_in_ms == 0
        assert p_a.fade_out_ms == 0
        assert p_b.fade_in_ms == 0
        assert p_b.fade_out_ms == 0
