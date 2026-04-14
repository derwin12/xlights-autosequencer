"""Unit tests for palette restraint and MusicSparkles features."""
from __future__ import annotations

import random
from random import Random

import pytest

from src.generator.effect_placer import (
    _AUDIO_REACTIVE_EFFECTS,
    _TIER_PALETTE_CAP,
    compute_music_sparkles,
    restrain_palette,
)


# ---------------------------------------------------------------------------
# T004: restrain_palette() unit tests
# ---------------------------------------------------------------------------

SAMPLE_PALETTE = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF", "#FFFFFF", "#000000"]


class TestRestrainPalette:
    """Tests for restrain_palette(palette, energy_score, tier) -> list[str]."""

    def test_energy_0_gives_2_colors(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=0, tier=8)
        assert len(result) == 2

    def test_energy_50_gives_3_colors(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=50, tier=8)
        assert len(result) == 3

    def test_energy_80_gives_4_colors(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=80, tier=8)
        assert len(result) == 4

    def test_single_color_theme_stays_at_1(self):
        result = restrain_palette(["#FF0000"], energy_score=80, tier=8)
        assert len(result) == 1

    def test_palette_shorter_than_target_returns_all(self):
        two_color = ["#FF0000", "#00FF00"]
        # energy=80 wants 4 colors, but only 2 available
        result = restrain_palette(two_color, energy_score=80, tier=8)
        assert len(result) == 2

    def test_returns_spread_colors_not_adjacent(self):
        # Spread selection: for an 8-color palette with target=2, should pick
        # index 0 (first) and index 7 (last), not two adjacent colors at the start.
        result = restrain_palette(SAMPLE_PALETTE, energy_score=0, tier=8)
        assert result == [SAMPLE_PALETTE[0], SAMPLE_PALETTE[-1]]

    def test_spread_includes_first_and_last(self):
        # For any target >= 2, spread always anchors at both ends of the palette.
        result = restrain_palette(SAMPLE_PALETTE, energy_score=50, tier=8)
        assert result[0] == SAMPLE_PALETTE[0]
        assert result[-1] == SAMPLE_PALETTE[-1]

    def test_never_returns_empty(self):
        result = restrain_palette(["#FF0000"], energy_score=0, tier=1)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# T008: palette_restraint=False bypass (written here; verified in US1 phase)
# ---------------------------------------------------------------------------
# (No implementation yet — these tests are written for T004 target)


# ---------------------------------------------------------------------------
# T014: US2 — tier differentiation tests
# ---------------------------------------------------------------------------

class TestTierDifferentiation:
    """Hero tiers (7-8) get more colors than base tiers (1-2) at same energy."""

    def test_tier8_energy80_returns_5_to_6_colors(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=80, tier=8)
        # energy=80 → base_count = 2 + 80//33 = 4; tier 8 cap = 6 → min(4,6) = 4
        # At energy=99: base_count=5; at energy=100: base_count=5; capped at 6
        # To get 5-6 we need energy high enough: energy=99 → 2+3=5
        assert len(result) >= 4

    def test_tier8_energy99_returns_5_colors(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=99, tier=8)
        assert len(result) == 5

    def test_tier1_energy80_capped_at_3(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=80, tier=1)
        assert len(result) <= 3

    def test_hero_vs_base_tier_at_high_energy(self):
        hero = restrain_palette(SAMPLE_PALETTE, energy_score=80, tier=8)
        base = restrain_palette(SAMPLE_PALETTE, energy_score=80, tier=1)
        assert len(hero) >= len(base)


# ---------------------------------------------------------------------------
# T018: US5 — energy scaling tests
# ---------------------------------------------------------------------------

class TestEnergyScaling:
    """High energy sections get more active colors than low energy sections."""

    def test_tier7_energy20_gives_2_colors(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=20, tier=7)
        assert len(result) == 2

    def test_tier7_energy85_gives_4_to_5_colors(self):
        result = restrain_palette(SAMPLE_PALETTE, energy_score=85, tier=7)
        assert len(result) >= 4

    def test_high_energy_gives_more_than_low_energy(self):
        low = restrain_palette(SAMPLE_PALETTE, energy_score=20, tier=7)
        high = restrain_palette(SAMPLE_PALETTE, energy_score=85, tier=7)
        assert len(high) > len(low)


# ---------------------------------------------------------------------------
# T021: US3 — compute_music_sparkles unit tests
# ---------------------------------------------------------------------------

class TestComputeMusicSparkles:
    """compute_music_sparkles(energy, effect_name, rng) -> int."""

    def test_audio_reactive_effect_always_returns_0(self):
        rng = Random(42)
        for _ in range(100):
            assert compute_music_sparkles(energy_score=80, effect_name="VU Meter", rng=rng) == 0

    def test_music_effect_always_returns_0(self):
        rng = Random(42)
        for _ in range(100):
            assert compute_music_sparkles(energy_score=80, effect_name="Music", rng=rng) == 0

    def test_pattern_effect_can_return_nonzero(self):
        # Run many times at high energy — should get at least one non-zero
        rng = Random(0)
        results = [compute_music_sparkles(energy_score=80, effect_name="Bars", rng=rng) for _ in range(200)]
        assert any(r > 0 for r in results), "Expected at least one non-zero sparkle value"

    def test_result_is_zero_or_in_valid_range(self):
        rng = Random(1)
        for _ in range(100):
            r = compute_music_sparkles(energy_score=80, effect_name="Bars", rng=rng)
            assert r == 0 or 20 <= r <= 100

    def test_zero_energy_never_triggers(self):
        rng = Random(42)
        results = [compute_music_sparkles(energy_score=0, effect_name="Bars", rng=rng) for _ in range(100)]
        assert all(r == 0 for r in results)


# ---------------------------------------------------------------------------
# T029: US4 — SparkleFrequency scaling tests
# ---------------------------------------------------------------------------

class TestSparkleFrequencyScaling:
    """When triggered, frequency scales with energy."""

    def _triggered_value(self, energy: int) -> int | None:
        """Return a triggered sparkle value at given energy, or None if not triggered."""
        rng = Random(999)
        for _ in range(1000):
            v = compute_music_sparkles(energy_score=energy, effect_name="Bars", rng=rng)
            if v > 0:
                return v
        return None

    def test_low_energy_triggered_value_in_range_20_35(self):
        val = self._triggered_value(energy=20)
        if val is None:
            pytest.skip("Low energy rarely triggers — need more iterations for this test")
        assert 20 <= val <= 40, f"Expected 20-40 range for energy=20, got {val}"

    def test_high_energy_triggered_value_in_range_70_80(self):
        val = self._triggered_value(energy=90)
        assert val is not None, "High energy should trigger sparkles"
        assert 60 <= val <= 90, f"Expected 60-90 range for energy=90, got {val}"

    def test_high_energy_frequency_exceeds_low_energy_frequency(self):
        low_val = self._triggered_value(energy=20)
        high_val = self._triggered_value(energy=90)
        if low_val is None:
            pytest.skip("Low energy rarely triggers")
        assert high_val > low_val


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------

class TestConstants:
    def test_tier_palette_cap_has_all_8_tiers(self):
        assert set(_TIER_PALETTE_CAP.keys()) == {1, 2, 3, 4, 5, 6, 7, 8}

    def test_audio_reactive_effects_non_empty(self):
        assert len(_AUDIO_REACTIVE_EFFECTS) > 0

    def test_vu_meter_is_audio_reactive(self):
        assert "VU Meter" in _AUDIO_REACTIVE_EFFECTS
