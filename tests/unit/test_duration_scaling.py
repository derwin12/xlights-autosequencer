"""Unit tests for duration scaling — compute_duration_target and compute_scaled_fades."""
from __future__ import annotations

import pytest

from src.generator.effect_placer import compute_duration_target, compute_scaled_fades
from src.generator.models import DurationTarget


# ---------------------------------------------------------------------------
# T005 / T007: Tests written first (TDD) — these FAIL before implementation
# ---------------------------------------------------------------------------


class TestComputeDurationTarget:
    """compute_duration_target(bpm, energy_score) -> DurationTarget"""

    # BPM anchor points
    def test_slow_bpm_gives_long_target(self):
        result = compute_duration_target(bpm=70.0, energy_score=50)
        assert result.target_ms >= 2500, f"Expected >=2500ms at 70bpm, got {result.target_ms}"

    def test_fast_bpm_gives_short_target(self):
        result = compute_duration_target(bpm=140.0, energy_score=50)
        assert result.target_ms <= 600, f"Expected <=600ms at 140bpm, got {result.target_ms}"

    def test_mid_bpm_interpolates(self):
        slow = compute_duration_target(bpm=80.0, energy_score=50)
        mid = compute_duration_target(bpm=110.0, energy_score=50)
        fast = compute_duration_target(bpm=140.0, energy_score=50)
        assert slow.target_ms > mid.target_ms > fast.target_ms

    def test_bpm_80_anchor(self):
        result = compute_duration_target(bpm=80.0, energy_score=50)
        assert 2500 <= result.target_ms <= 3500

    def test_bpm_140_anchor(self):
        result = compute_duration_target(bpm=140.0, energy_score=50)
        assert 400 <= result.target_ms <= 700

    def test_bpm_below_80_clamps_to_slow_anchor(self):
        at_80 = compute_duration_target(bpm=80.0, energy_score=50)
        at_60 = compute_duration_target(bpm=60.0, energy_score=50)
        # Both should give slow target — clamped at 80 boundary
        assert abs(at_80.target_ms - at_60.target_ms) < 200

    def test_bpm_above_140_clamps_to_fast_anchor(self):
        at_140 = compute_duration_target(bpm=140.0, energy_score=50)
        at_180 = compute_duration_target(bpm=180.0, energy_score=50)
        assert abs(at_140.target_ms - at_180.target_ms) < 200

    # Energy modulation
    def test_high_energy_shortens_duration(self):
        low = compute_duration_target(bpm=100.0, energy_score=20)
        high = compute_duration_target(bpm=100.0, energy_score=80)
        assert high.target_ms < low.target_ms

    def test_energy_0_gives_longer_than_energy_100(self):
        e0 = compute_duration_target(bpm=100.0, energy_score=0)
        e100 = compute_duration_target(bpm=100.0, energy_score=100)
        assert e0.target_ms > e100.target_ms

    def test_energy_50_neutral_between_extremes(self):
        e0 = compute_duration_target(bpm=100.0, energy_score=0)
        e50 = compute_duration_target(bpm=100.0, energy_score=50)
        e100 = compute_duration_target(bpm=100.0, energy_score=100)
        assert e0.target_ms > e50.target_ms > e100.target_ms

    # Clamp bounds
    def test_target_never_below_250ms(self):
        result = compute_duration_target(bpm=200.0, energy_score=100)
        assert result.target_ms >= 250
        assert result.min_ms >= 250

    def test_target_never_above_8000ms(self):
        result = compute_duration_target(bpm=40.0, energy_score=0)
        assert result.target_ms <= 8000
        assert result.max_ms <= 8000

    # min/max relationship
    def test_min_less_than_target(self):
        result = compute_duration_target(bpm=100.0, energy_score=50)
        assert result.min_ms <= result.target_ms

    def test_target_less_than_max(self):
        result = compute_duration_target(bpm=100.0, energy_score=50)
        assert result.target_ms <= result.max_ms

    def test_returns_duration_target_dataclass(self):
        result = compute_duration_target(bpm=120.0, energy_score=50)
        assert isinstance(result, DurationTarget)
        assert hasattr(result, "min_ms")
        assert hasattr(result, "target_ms")
        assert hasattr(result, "max_ms")

    # Monotonicity
    def test_higher_bpm_always_shorter(self):
        for energy in [0, 50, 100]:
            for bpm_low, bpm_high in [(80, 100), (100, 120), (120, 140)]:
                low = compute_duration_target(bpm=float(bpm_low), energy_score=energy)
                high = compute_duration_target(bpm=float(bpm_high), energy_score=energy)
                assert high.target_ms <= low.target_ms, (
                    f"BPM {bpm_high} should give shorter target than {bpm_low} at energy {energy}"
                )


class TestComputeScaledFades:
    """compute_scaled_fades(duration_ms) -> tuple[int, int]"""

    def test_sub_500ms_gives_zero_fades(self):
        fade_in, fade_out = compute_scaled_fades(300)
        assert fade_in == 0
        assert fade_out == 0

    def test_exactly_500ms_boundary(self):
        fade_in, fade_out = compute_scaled_fades(500)
        # At boundary: zero or very small
        assert fade_in == 0 or fade_in <= 50
        assert fade_out == 0 or fade_out <= 50

    def test_medium_duration_gives_proportional_fades(self):
        fade_in, fade_out = compute_scaled_fades(2000)
        assert 50 <= fade_in <= 500
        assert 50 <= fade_out <= 500

    def test_long_duration_gives_larger_fades(self):
        fade_in, fade_out = compute_scaled_fades(6000)
        assert 200 <= fade_in <= 2000
        assert 200 <= fade_out <= 2000

    def test_combined_fades_never_exceed_40_percent(self):
        for duration in [300, 500, 1000, 2000, 4000, 8000]:
            fade_in, fade_out = compute_scaled_fades(duration)
            assert fade_in + fade_out <= 0.40 * duration, (
                f"duration={duration}: fades {fade_in}+{fade_out}={fade_in+fade_out} exceeds 40%"
            )

    def test_fades_are_non_negative(self):
        for duration in [100, 500, 2000, 8000]:
            fade_in, fade_out = compute_scaled_fades(duration)
            assert fade_in >= 0
            assert fade_out >= 0

    def test_longer_duration_gives_equal_or_larger_fades(self):
        fi_short, fo_short = compute_scaled_fades(1000)
        fi_long, fo_long = compute_scaled_fades(5000)
        assert fi_long >= fi_short
        assert fo_long >= fo_short

    def test_returns_tuple_of_two_ints(self):
        result = compute_scaled_fades(2000)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_fades_are_symmetric(self):
        fade_in, fade_out = compute_scaled_fades(2000)
        assert fade_in == fade_out
