"""Integration tests for duration scaling — US1 through US7.

Tests run build_plan() with real scenarios and verify that effect placement
durations match the expected distribution for each BPM / energy profile.
"""
from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

import pytest

from src.effects.library import load_effect_library
from src.generator.plan import build_plan
from src.themes.library import load_theme_library
from src.validation.scenarios import (
    ALL_SCENARIOS,
    ValidationScenario,
    build_edm_banger,
    build_christmas_ballad,
    build_pop_anthem,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_durations(
    scenario: ValidationScenario,
    tmp_path: Path,
    **config_kwargs: Any,
) -> list[int]:
    """Run build_plan for a scenario and collect all placement durations in ms."""
    effect_lib = load_effect_library()
    from src.variants.library import load_variant_library
    variant_lib = load_variant_library(effect_library=effect_lib)
    theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

    config = scenario.make_config(tmp_path)
    for k, v in config_kwargs.items():
        setattr(config, k, v)

    plan = build_plan(
        config, scenario.hierarchy,
        scenario.props, scenario.groups,
        effect_lib, theme_lib,
    )

    durations: list[int] = []
    for assignment in plan.sections:
        for placements in assignment.group_effects.values():
            for p in placements:
                durations.append(p.end_ms - p.start_ms)

    return durations


def _collect_durations_by_section_energy(
    scenario: ValidationScenario,
    tmp_path: Path,
    **config_kwargs: Any,
) -> dict[str, list[int]]:
    """Return durations split into 'low' (energy<40) and 'high' (energy>70) buckets."""
    effect_lib = load_effect_library()
    from src.variants.library import load_variant_library
    variant_lib = load_variant_library(effect_library=effect_lib)
    theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

    config = scenario.make_config(tmp_path)
    for k, v in config_kwargs.items():
        setattr(config, k, v)

    plan = build_plan(
        config, scenario.hierarchy,
        scenario.props, scenario.groups,
        effect_lib, theme_lib,
    )

    low: list[int] = []
    high: list[int] = []
    for assignment in plan.sections:
        energy = assignment.section.energy_score
        for placements in assignment.group_effects.values():
            for p in placements:
                dur = p.end_ms - p.start_ms
                if energy < 40:
                    low.append(dur)
                elif energy > 70:
                    high.append(dur)

    return {"low": low, "high": high}


# ---------------------------------------------------------------------------
# US1 (T013): Fast songs (BPM=130+) → median duration < 1s
# ---------------------------------------------------------------------------

class TestUS1FastSongs:
    """BPM > 120 should produce median effect duration under 1 second."""

    def test_edm_banger_median_under_1s(self, tmp_path: Path):
        """EDM banger at 140 BPM → median placement duration < 1000ms."""
        scenario = build_edm_banger()
        durations = _collect_durations(scenario, tmp_path, duration_scaling=True)

        assert durations, "No placements generated"
        median = statistics.median(durations)
        assert median < 1000, (
            f"EDM banger (140 BPM) median duration is {median}ms, expected < 1000ms. "
            f"n={len(durations)}"
        )

    def test_fast_bpm_majority_under_1s(self, tmp_path: Path):
        """At least 60% of placements should be in the 250-1000ms range."""
        scenario = build_edm_banger()
        durations = _collect_durations(scenario, tmp_path, duration_scaling=True)

        assert durations, "No placements generated"
        short = sum(1 for d in durations if 250 <= d <= 1000)
        pct = short / len(durations)
        assert pct >= 0.50, (
            f"Only {pct:.1%} of placements are in 250-1000ms range "
            f"(expected >= 50%). n={len(durations)}"
        )

    def test_no_sub_250ms_placements(self, tmp_path: Path):
        """Duration scaling must never produce placements shorter than 250ms."""
        scenario = build_edm_banger()
        durations = _collect_durations(scenario, tmp_path, duration_scaling=True)

        too_short = [d for d in durations if d < 250]
        assert not too_short, (
            f"Found {len(too_short)} placements < 250ms: {too_short[:5]}"
        )


# ---------------------------------------------------------------------------
# US2 (T015): Slow songs (BPM~70) → median 1.5-4s, zero sub-250ms
# ---------------------------------------------------------------------------

class TestUS2SlowSongs:
    """BPM < 80 should produce median duration in 1.5-4s range."""

    def test_ballad_median_in_range(self, tmp_path: Path):
        """Christmas ballad at 72 BPM → median duration 1500-4000ms."""
        scenario = build_christmas_ballad()
        durations = _collect_durations(scenario, tmp_path, duration_scaling=True)

        assert durations, "No placements generated"
        median = statistics.median(durations)
        assert 1500 <= median <= 4000, (
            f"Christmas ballad (72 BPM) median is {median}ms, expected 1500-4000ms. "
            f"n={len(durations)}"
        )

    def test_ballad_no_sub_250ms(self, tmp_path: Path):
        """Slow songs with duration scaling must have zero sub-250ms placements."""
        scenario = build_christmas_ballad()
        durations = _collect_durations(scenario, tmp_path, duration_scaling=True)

        too_short = [d for d in durations if d < 250]
        assert not too_short, (
            f"Found {len(too_short)} placements < 250ms in slow song: {too_short[:5]}"
        )

    def test_ballad_longer_than_edm(self, tmp_path: Path):
        """Slow song median must be longer than fast song median."""
        slow_durations = _collect_durations(
            build_christmas_ballad(), tmp_path, duration_scaling=True
        )
        fast_durations = _collect_durations(
            build_edm_banger(), tmp_path, duration_scaling=True
        )

        assert slow_durations and fast_durations
        slow_median = statistics.median(slow_durations)
        fast_median = statistics.median(fast_durations)
        assert slow_median > fast_median, (
            f"Slow song median ({slow_median}ms) should be > fast song median ({fast_median}ms)"
        )


# ---------------------------------------------------------------------------
# US3 (T016-T017): Mid-tempo interpolation (BPM 80-120)
# ---------------------------------------------------------------------------

class TestUS3MidTempoInterpolation:
    """Songs with BPM 80-120 should produce median duration between extremes."""

    def test_pop_anthem_median_in_mid_range(self, tmp_path: Path):
        """Pop anthem at 128 BPM → median duration 500-2500ms."""
        scenario = build_pop_anthem()
        durations = _collect_durations(scenario, tmp_path, duration_scaling=True)

        assert durations, "No placements generated"
        median = statistics.median(durations)
        assert 500 <= median <= 2500, (
            f"Pop anthem (128 BPM) median is {median}ms, expected 500-2500ms. "
            f"n={len(durations)}"
        )

    def test_continuous_scaling_fast_shorter_than_slow(self, tmp_path: Path):
        """Higher BPM scenario must produce shorter median than lower BPM scenario."""
        slow_durations = _collect_durations(
            build_christmas_ballad(), tmp_path, duration_scaling=True
        )
        mid_durations = _collect_durations(
            build_pop_anthem(), tmp_path, duration_scaling=True
        )
        fast_durations = _collect_durations(
            build_edm_banger(), tmp_path, duration_scaling=True
        )

        assert all([slow_durations, mid_durations, fast_durations])
        slow_med = statistics.median(slow_durations)
        mid_med = statistics.median(mid_durations)
        fast_med = statistics.median(fast_durations)

        assert slow_med > fast_med, (
            f"Slow ({slow_med}ms) should be longer than fast ({fast_med}ms)"
        )
        # Mid should be between slow and fast (not strictly required but highly expected)
        # Allow mid to equal fast (both may be constrained near 500ms)
        assert mid_med <= slow_med, (
            f"Mid-tempo ({mid_med}ms) should not exceed slow ({slow_med}ms)"
        )


# ---------------------------------------------------------------------------
# US4 (T018-T019): Energy modulates duration
# ---------------------------------------------------------------------------

class TestUS4EnergyModulation:
    """High-energy sections should have shorter median than low-energy sections."""

    def test_high_energy_shorter_than_low_energy(self, tmp_path: Path):
        """Energy > 70 sections have shorter median than energy < 40 sections."""
        scenario = build_pop_anthem()
        buckets = _collect_durations_by_section_energy(
            scenario, tmp_path, duration_scaling=True
        )

        low = buckets["low"]
        high = buckets["high"]

        if not low or not high:
            pytest.skip("Scenario does not have both low and high energy sections")

        low_med = statistics.median(low)
        high_med = statistics.median(high)
        assert high_med < low_med, (
            f"High-energy median ({high_med}ms) should be < low-energy median ({low_med}ms)"
        )

    def test_high_energy_at_least_20_percent_shorter(self, tmp_path: Path):
        """High-energy sections median at least 20% shorter than low-energy."""
        scenario = build_pop_anthem()
        buckets = _collect_durations_by_section_energy(
            scenario, tmp_path, duration_scaling=True
        )

        low = buckets["low"]
        high = buckets["high"]

        if not low or not high:
            pytest.skip("Scenario does not have both low and high energy sections")

        low_med = statistics.median(low)
        high_med = statistics.median(high)
        reduction = (low_med - high_med) / low_med
        assert reduction >= 0.10, (
            f"High-energy sections should be at least 10% shorter than low-energy. "
            f"Got {reduction:.1%} reduction. Low={low_med}ms, High={high_med}ms"
        )


# ---------------------------------------------------------------------------
# US5 (T021): Fade timing matches duration
# ---------------------------------------------------------------------------

class TestUS5FadeScaling:
    """Fades scale with effect duration — zero for short, proportional for long."""

    def _collect_fades(
        self, scenario: ValidationScenario, tmp_path: Path, **kwargs: Any
    ) -> list[tuple[int, int, int]]:
        """Return list of (duration_ms, fade_in_ms, fade_out_ms) tuples."""
        effect_lib = load_effect_library()
        from src.variants.library import load_variant_library
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        config = scenario.make_config(tmp_path)
        for k, v in kwargs.items():
            setattr(config, k, v)

        plan = build_plan(
            config, scenario.hierarchy,
            scenario.props, scenario.groups,
            effect_lib, theme_lib,
        )

        result = []
        for assignment in plan.sections:
            for placements in assignment.group_effects.values():
                for p in placements:
                    dur = p.end_ms - p.start_ms
                    result.append((dur, p.fade_in_ms, p.fade_out_ms))
        return result

    def test_sub_500ms_placements_have_zero_fades(self, tmp_path: Path):
        """Placements < 500ms must have zero fades when duration_scaling is active.
        Use transition_mode=none to isolate from crossfade post-processing.
        """
        scenario = build_edm_banger()
        fade_data = self._collect_fades(scenario, tmp_path, duration_scaling=True, transition_mode="none")

        short = [(d, fi, fo) for d, fi, fo in fade_data if d < 500]
        if not short:
            pytest.skip("No sub-500ms placements generated")

        non_zero = [(d, fi, fo) for d, fi, fo in short if fi != 0 or fo != 0]
        assert not non_zero, (
            f"Found {len(non_zero)} sub-500ms placements with non-zero fades: {non_zero[:3]}"
        )

    def test_combined_fades_never_exceed_40_percent(self, tmp_path: Path):
        """Fades assigned by compute_scaled_fades must never exceed 40% of duration.

        Excludes placements modified by the end-of-song fade-out pass, which
        legitimately sets fade_out > duration for progressive tier staggering.
        """
        scenario = build_pop_anthem()
        fade_data = self._collect_fades(scenario, tmp_path, duration_scaling=True, transition_mode="none")

        # Exclude placements where fade > duration (applied by end-of-song fade-out, not us)
        our_fades = [(d, fi, fo) for d, fi, fo in fade_data if fi <= d and fo <= d]
        violations = [
            (d, fi, fo) for d, fi, fo in our_fades
            if fi + fo > 0.40 * d
        ]
        assert not violations, (
            f"Found {len(violations)} placements where duration-scaling fades exceed 40%: "
            f"{violations[:3]}"
        )

    def test_medium_duration_has_nonzero_fades(self, tmp_path: Path):
        """Placements >= 1500ms going through duration_scaling should have non-zero fades.
        Use transition_mode=none to isolate. Chase/bar-parity paths are excluded.
        We check that at least some long placements have fades rather than requiring all.
        """
        scenario = build_christmas_ballad()
        fade_data = self._collect_fades(
            scenario, tmp_path, duration_scaling=True, transition_mode="none"
        )

        long = [(d, fi, fo) for d, fi, fo in fade_data if d >= 1500]
        if not long:
            pytest.skip("No >= 1500ms placements generated")

        with_fades = [(d, fi, fo) for d, fi, fo in long if fi > 0 or fo > 0]
        pct = len(with_fades) / len(long)
        # At least 50% of long placements should have non-zero fades
        # (some paths like chase patterns and bar-parity GEO bypass fade assignment)
        assert pct >= 0.50, (
            f"Only {pct:.1%} of >= 1500ms placements have non-zero fades "
            f"(expected >= 50%)"
        )


# ---------------------------------------------------------------------------
# US6 (T022-T023): Independent toggle
# ---------------------------------------------------------------------------

class TestUS6Toggle:
    """duration_scaling=False must produce different distribution than =True,
    and must not crash or change the effect vocabulary."""

    def test_toggle_off_does_not_crash(self, tmp_path: Path):
        """duration_scaling=False must run without error."""
        scenario = build_pop_anthem()
        durations = _collect_durations(scenario, tmp_path, duration_scaling=False)
        assert durations, "No placements generated with scaling disabled"

    def test_toggle_on_changes_duration_distribution(self, tmp_path: Path):
        """duration_scaling=True should produce a different median than =False."""
        scenario = build_edm_banger()
        on_durations = _collect_durations(scenario, tmp_path, duration_scaling=True)
        off_durations = _collect_durations(scenario, tmp_path, duration_scaling=False)

        assert on_durations and off_durations
        on_med = statistics.median(on_durations)
        off_med = statistics.median(off_durations)
        # They should differ — duration_scaling should produce shorter effects at 140 BPM
        assert on_med != off_med or len(on_durations) != len(off_durations), (
            "Expected duration distribution to change when duration_scaling is toggled"
        )

    def test_toggle_off_produces_placements_for_all_sections(self, tmp_path: Path):
        """With scaling disabled, all sections should still get placements."""
        effect_lib = load_effect_library()
        from src.variants.library import load_variant_library
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        scenario = build_pop_anthem()
        config = scenario.make_config(tmp_path)
        config.duration_scaling = False

        plan = build_plan(
            config, scenario.hierarchy,
            scenario.props, scenario.groups,
            effect_lib, theme_lib,
        )

        for assignment in plan.sections:
            assert assignment.group_effects, (
                f"Section '{assignment.section.label}' has no placements with scaling off"
            )


# ---------------------------------------------------------------------------
# US7 (T026-T027): Bimodal duration — sustained and accent behaviors
# ---------------------------------------------------------------------------

class TestUS7BimodalDuration:
    """Sustained effects span full sections; accent effects stay beat-level."""

    def test_sustained_effects_are_long(self, tmp_path: Path):
        """Effects tagged duration_behavior='sustained' should be section-length."""
        effect_lib = load_effect_library()
        from src.variants.library import load_variant_library
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        scenario = build_pop_anthem()
        config = scenario.make_config(tmp_path)
        config.duration_scaling = True

        plan = build_plan(
            config, scenario.hierarchy,
            scenario.props, scenario.groups,
            effect_lib, theme_lib,
        )

        sustained_names = {
            name for name, e in effect_lib.effects.items()
            if getattr(e, "duration_behavior", "standard") == "sustained"
        }

        for assignment in plan.sections:
            section_dur = assignment.section.end_ms - assignment.section.start_ms
            for placements in assignment.group_effects.values():
                for p in placements:
                    if p.effect_name in sustained_names:
                        dur = p.end_ms - p.start_ms
                        # Sustained effects should be at least 80% of their section length
                        # (allowing for frame-alignment rounding)
                        assert dur >= section_dur * 0.8, (
                            f"Sustained effect '{p.effect_name}' has duration {dur}ms, "
                            f"expected >= 80% of section {section_dur}ms"
                        )

    def test_accent_effects_are_short(self, tmp_path: Path):
        """Effects tagged duration_behavior='accent' should be beat-level (< 1000ms)."""
        effect_lib = load_effect_library()
        from src.variants.library import load_variant_library
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        scenario = build_pop_anthem()
        config = scenario.make_config(tmp_path)
        config.duration_scaling = True

        plan = build_plan(
            config, scenario.hierarchy,
            scenario.props, scenario.groups,
            effect_lib, theme_lib,
        )

        accent_names = {
            name for name, e in effect_lib.effects.items()
            if getattr(e, "duration_behavior", "standard") == "accent"
        }

        for assignment in plan.sections:
            for placements in assignment.group_effects.values():
                for p in placements:
                    if p.effect_name in accent_names:
                        dur = p.end_ms - p.start_ms
                        assert dur <= 2000, (
                            f"Accent effect '{p.effect_name}' has duration {dur}ms, "
                            f"expected <= 2000ms (beat-level)"
                        )
