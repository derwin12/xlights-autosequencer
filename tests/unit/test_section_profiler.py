"""Failing TDD tests for src/story/section_profiler.py.

These tests define the contract for profile_section() and MUST fail before
the implementation exists. Do not create the implementation to make them pass
until the full module is ready.
"""
from __future__ import annotations

import pytest

from tests.fixtures.story_fixture import make_hierarchy_dict

# This import MUST fail until the module is implemented.
from src.story.section_profiler import profile_section  # noqa: E402


# ── Fixture helpers ────────────────────────────────────────────────────────────

INTRO_START = 0
INTRO_END = 12_000

CHORUS_START = 36_000
CHORUS_END = 54_000


@pytest.fixture()
def hierarchy():
    return make_hierarchy_dict()


@pytest.fixture()
def intro_profile(hierarchy):
    return profile_section(INTRO_START, INTRO_END, hierarchy)


@pytest.fixture()
def chorus_profile(hierarchy):
    return profile_section(CHORUS_START, CHORUS_END, hierarchy)


# ── Return structure ───────────────────────────────────────────────────────────

class TestReturnStructure:
    def test_returns_dict(self, intro_profile):
        assert isinstance(intro_profile, dict)

    def test_has_character_key(self, intro_profile):
        assert "character" in intro_profile

    def test_has_stems_key(self, intro_profile):
        assert "stems" in intro_profile

    def test_character_is_dict(self, intro_profile):
        assert isinstance(intro_profile["character"], dict)

    def test_stems_is_dict(self, intro_profile):
        assert isinstance(intro_profile["stems"], dict)


# ── Energy level thresholds ────────────────────────────────────────────────────

class TestEnergyLevel:
    """energy_score 0-33 → "low", 34-66 → "medium", 67-100 → "high"."""

    def test_intro_energy_level_is_low(self, intro_profile):
        # Fixture intro energy = 0.2 → score ≈ 20 → "low"
        assert intro_profile["character"]["energy_level"] == "low"

    def test_chorus_energy_level_is_high(self, chorus_profile):
        # Fixture chorus energy = 0.8 → score ≈ 80 → "high"
        assert chorus_profile["character"]["energy_level"] == "high"

    def test_energy_level_medium_at_score_50(self, hierarchy):
        # Verse (12s-36s) has energy 0.5 → score ≈ 50 → "medium"
        profile = profile_section(12_000, 36_000, hierarchy)
        assert profile["character"]["energy_level"] == "medium"

    def test_energy_level_low_boundary_score_33(self, hierarchy):
        # Build a minimal hierarchy where average energy maps to exactly score 33
        import copy
        h = copy.deepcopy(hierarchy)
        rate = h["energy_curves"]["full_mix"]["sample_rate"]
        n = int((INTRO_END - INTRO_START) / 1000 * rate)
        # 33/100 = 0.33 → values all 0.33 → score 33 → "low"
        h["energy_curves"]["full_mix"]["values"] = [0.33] * len(
            h["energy_curves"]["full_mix"]["values"]
        )
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["energy_level"] == "low"

    def test_energy_level_medium_boundary_score_34(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        h["energy_curves"]["full_mix"]["values"] = [0.34] * len(
            h["energy_curves"]["full_mix"]["values"]
        )
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["energy_level"] == "medium"

    def test_energy_level_high_boundary_score_67(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        h["energy_curves"]["full_mix"]["values"] = [0.67] * len(
            h["energy_curves"]["full_mix"]["values"]
        )
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["energy_level"] == "high"


# ── energy_score ───────────────────────────────────────────────────────────────

class TestEnergyScore:
    def test_energy_score_is_int(self, intro_profile):
        assert isinstance(intro_profile["character"]["energy_score"], int)

    def test_energy_score_in_range(self, intro_profile):
        score = intro_profile["character"]["energy_score"]
        assert 0 <= score <= 100

    def test_chorus_energy_score_gt_intro(self, intro_profile, chorus_profile):
        assert chorus_profile["character"]["energy_score"] > intro_profile["character"]["energy_score"]

    def test_intro_energy_score_approx_20(self, intro_profile):
        # Fixture intro energy is a flat 0.2 → score should be 20
        assert intro_profile["character"]["energy_score"] == pytest.approx(20, abs=5)

    def test_chorus_energy_score_approx_80(self, chorus_profile):
        # Fixture chorus energy is a flat 0.8 → score should be 80
        assert chorus_profile["character"]["energy_score"] == pytest.approx(80, abs=5)


# ── energy_peak ───────────────────────────────────────────────────────────────

class TestEnergyPeak:
    def test_energy_peak_is_int(self, intro_profile):
        assert isinstance(intro_profile["character"]["energy_peak"], int)

    def test_energy_peak_in_range(self, intro_profile):
        peak = intro_profile["character"]["energy_peak"]
        assert 0 <= peak <= 100

    def test_energy_peak_gte_energy_score(self, intro_profile):
        char = intro_profile["character"]
        assert char["energy_peak"] >= char["energy_score"]

    def test_energy_peak_gte_energy_score_chorus(self, chorus_profile):
        char = chorus_profile["character"]
        assert char["energy_peak"] >= char["energy_score"]

    def test_flat_signal_peak_equals_score(self, hierarchy):
        """When energy is perfectly flat, peak == score."""
        import copy
        h = copy.deepcopy(hierarchy)
        h["energy_curves"]["full_mix"]["values"] = [0.5] * len(
            h["energy_curves"]["full_mix"]["values"]
        )
        profile = profile_section(INTRO_START, INTRO_END, h)
        char = profile["character"]
        assert char["energy_peak"] == char["energy_score"]


# ── energy_trajectory ─────────────────────────────────────────────────────────

class TestEnergyTrajectory:
    VALID_TRAJECTORIES = {"rising", "falling", "stable", "oscillating"}

    def test_trajectory_is_valid_string(self, intro_profile):
        traj = intro_profile["character"]["energy_trajectory"]
        assert traj in self.VALID_TRAJECTORIES

    def test_chorus_trajectory_is_valid(self, chorus_profile):
        traj = chorus_profile["character"]["energy_trajectory"]
        assert traj in self.VALID_TRAJECTORIES

    def test_stable_when_flat_energy(self, hierarchy):
        """A perfectly flat curve should yield 'stable'."""
        import copy
        h = copy.deepcopy(hierarchy)
        h["energy_curves"]["full_mix"]["values"] = [0.5] * len(
            h["energy_curves"]["full_mix"]["values"]
        )
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["energy_trajectory"] == "stable"

    def test_rising_when_monotonically_increasing(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        n = len(h["energy_curves"]["full_mix"]["values"])
        h["energy_curves"]["full_mix"]["values"] = [i / n for i in range(n)]
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["energy_trajectory"] == "rising"

    def test_falling_when_monotonically_decreasing(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        n = len(h["energy_curves"]["full_mix"]["values"])
        h["energy_curves"]["full_mix"]["values"] = [1.0 - i / n for i in range(n)]
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["energy_trajectory"] == "falling"


# ── texture ───────────────────────────────────────────────────────────────────

class TestTexture:
    """hp_ratio > 2.0 → "harmonic"; < 0.5 → "percussive"; else "balanced"."""

    VALID_TEXTURES = {"harmonic", "percussive", "balanced"}

    def test_texture_is_valid_string(self, intro_profile):
        assert intro_profile["character"]["texture"] in self.VALID_TEXTURES

    def test_texture_harmonic_when_hp_ratio_gt_2(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        # Force high harmonic energy, low percussive
        sr = h["energy_curves"]["full_mix"]["sample_rate"]
        n = len(h["energy_curves"]["full_mix"]["values"])
        h["energy_curves"]["full_mix"]["values"] = [0.5] * n
        # Manipulate drums (percussive) to near-zero and guitar/piano (harmonic) to high
        for stem in ("drums",):
            h["energy_curves"][stem] = {"sample_rate": sr, "values": [0.05] * n}
        for stem in ("guitar", "piano"):
            h["energy_curves"][stem] = {"sample_rate": sr, "values": [0.9] * n}
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["texture"] == "harmonic"

    def test_texture_percussive_when_hp_ratio_lt_0_5(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        sr = h["energy_curves"]["full_mix"]["sample_rate"]
        n = len(h["energy_curves"]["full_mix"]["values"])
        for stem in ("guitar", "piano", "bass", "vocals"):
            h["energy_curves"][stem] = {"sample_rate": sr, "values": [0.02] * n}
        h["energy_curves"]["drums"] = {"sample_rate": sr, "values": [0.95] * n}
        profile = profile_section(INTRO_START, INTRO_END, h)
        assert profile["character"]["texture"] == "percussive"

    def test_hp_ratio_is_float(self, intro_profile):
        assert isinstance(intro_profile["character"]["hp_ratio"], float)

    def test_hp_ratio_positive(self, intro_profile):
        assert intro_profile["character"]["hp_ratio"] > 0.0


# ── spectral_brightness ───────────────────────────────────────────────────────

class TestSpectralBrightness:
    VALID_BRIGHTNESS = {"dark", "neutral", "bright"}

    def test_spectral_brightness_is_valid(self, intro_profile):
        assert intro_profile["character"]["spectral_brightness"] in self.VALID_BRIGHTNESS

    def test_spectral_brightness_chorus_is_valid(self, chorus_profile):
        assert chorus_profile["character"]["spectral_brightness"] in self.VALID_BRIGHTNESS


# ── spectral_flatness ─────────────────────────────────────────────────────────

class TestSpectralFlatness:
    def test_spectral_flatness_is_float(self, intro_profile):
        assert isinstance(intro_profile["character"]["spectral_flatness"], float)

    def test_spectral_flatness_in_range(self, intro_profile):
        sf = intro_profile["character"]["spectral_flatness"]
        assert 0.0 <= sf <= 1.0

    def test_spectral_flatness_chorus_in_range(self, chorus_profile):
        sf = chorus_profile["character"]["spectral_flatness"]
        assert 0.0 <= sf <= 1.0


# ── local_tempo_bpm ───────────────────────────────────────────────────────────

class TestLocalTempoBpm:
    def test_local_tempo_bpm_positive_when_beats_present(self, chorus_profile):
        # Fixture has beats at 120 BPM throughout including the chorus window
        assert chorus_profile["character"]["local_tempo_bpm"] > 0

    def test_local_tempo_bpm_approx_120(self, chorus_profile):
        # Fixture BPM = 120 → beats every 500ms
        assert chorus_profile["character"]["local_tempo_bpm"] == pytest.approx(120.0, abs=5)

    def test_local_tempo_bpm_is_float(self, chorus_profile):
        assert isinstance(chorus_profile["character"]["local_tempo_bpm"], float)


# ── dominant_stem ─────────────────────────────────────────────────────────────

class TestDominantStem:
    def test_dominant_stem_is_string(self, chorus_profile):
        assert isinstance(chorus_profile["stems"]["dominant_stem"], str)

    def test_dominant_stem_is_known_stem(self, chorus_profile):
        known = {"drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"}
        assert chorus_profile["stems"]["dominant_stem"] in known

    def test_chorus_dominant_stem_is_drums(self, chorus_profile):
        # In fixture, drums energy = 0.7 in chorus, highest of any stem
        assert chorus_profile["stems"]["dominant_stem"] == "drums"

    def test_intro_dominant_stem_is_guitar(self, intro_profile):
        # In fixture intro, drums = 0.1, bass = 0.05, guitar = 0.3 → guitar wins
        assert intro_profile["stems"]["dominant_stem"] == "guitar"


# ── vocals_active ─────────────────────────────────────────────────────────────

class TestVocalsActive:
    def test_vocals_active_is_bool(self, intro_profile):
        assert isinstance(intro_profile["stems"]["vocals_active"], bool)

    def test_vocals_inactive_in_intro(self, intro_profile):
        # Fixture: vocals energy = 0.0 in intro (0-12s)
        assert intro_profile["stems"]["vocals_active"] is False

    def test_vocals_active_in_chorus(self, chorus_profile):
        # Fixture: vocals energy = 0.6 in chorus (36-54s)
        assert chorus_profile["stems"]["vocals_active"] is True


# ── onset_counts ──────────────────────────────────────────────────────────────

class TestOnsetCounts:
    def test_onset_counts_is_dict(self, chorus_profile):
        assert isinstance(chorus_profile["stems"]["onset_counts"], dict)

    def test_onset_counts_values_non_negative(self, chorus_profile):
        for stem, count in chorus_profile["stems"]["onset_counts"].items():
            assert count >= 0, f"Negative count for stem '{stem}'"

    def test_onset_counts_values_are_ints(self, chorus_profile):
        for stem, count in chorus_profile["stems"]["onset_counts"].items():
            assert isinstance(count, int), f"Non-int count for stem '{stem}'"

    def test_chorus_drums_onset_count_positive(self, chorus_profile):
        # Fixture has drum events from 12s onward through chorus
        onset_counts = chorus_profile["stems"]["onset_counts"]
        assert onset_counts.get("drums", 0) > 0

    def test_intro_drums_onset_count_zero(self, intro_profile):
        # Fixture drum events start at 12s; intro ends at 12s (exclusive)
        onset_counts = intro_profile["stems"]["onset_counts"]
        assert onset_counts.get("drums", 0) == 0


# ── drum_pattern ──────────────────────────────────────────────────────────────

class TestDrumPattern:
    def test_drum_pattern_none_when_no_drums(self, intro_profile):
        # Fixture has no drum events in 0-12s
        assert intro_profile["stems"]["drum_pattern"] is None

    def test_drum_pattern_present_in_chorus(self, chorus_profile):
        assert chorus_profile["stems"]["drum_pattern"] is not None

    def test_drum_pattern_has_style(self, chorus_profile):
        dp = chorus_profile["stems"]["drum_pattern"]
        assert "style" in dp

    def test_drum_pattern_style_sparse_when_low_density(self, hierarchy):
        """A section with fewer than 1 drum event/sec → style == 'sparse'."""
        import copy
        h = copy.deepcopy(hierarchy)
        # Replace drum marks with only 5 events spread over intro duration of 12s
        sparse_marks = [
            {"time_ms": ms, "label": "kick", "confidence": 0.9}
            for ms in [0, 2500, 5000, 7500, 10000]
        ]
        h["events"]["drums"]["marks"] = sparse_marks
        profile = profile_section(INTRO_START, INTRO_END, h)
        dp = profile["stems"]["drum_pattern"]
        if dp is not None:
            # 5 events / 12 seconds = 0.42 /sec → sparse
            assert dp["style"] == "sparse"

    def test_drum_pattern_style_driving_when_kick_dominant(self, chorus_profile):
        """Fixture chorus: kick count > 50% of total → 'driving'."""
        dp = chorus_profile["stems"]["drum_pattern"]
        if dp is not None:
            total = dp["kick_count"] + dp["snare_count"] + dp["hihat_count"]
            if total > 0 and dp["kick_count"] / total > 0.5:
                assert dp["style"] == "driving"

    def test_drum_pattern_kick_count_non_negative(self, chorus_profile):
        dp = chorus_profile["stems"]["drum_pattern"]
        assert dp["kick_count"] >= 0

    def test_drum_pattern_snare_count_non_negative(self, chorus_profile):
        dp = chorus_profile["stems"]["drum_pattern"]
        assert dp["snare_count"] >= 0


# ── frequency_bands ───────────────────────────────────────────────────────────

class TestFrequencyBands:
    EXPECTED_KEYS = {"sub_bass", "bass", "low_mid", "mid", "upper_mid", "presence", "brilliance"}

    def test_frequency_bands_present(self, intro_profile):
        assert "frequency_bands" in intro_profile["character"]

    def test_frequency_bands_has_all_expected_keys(self, intro_profile):
        bands = intro_profile["character"]["frequency_bands"]
        assert self.EXPECTED_KEYS == set(bands.keys())

    def test_frequency_bands_chorus_has_all_expected_keys(self, chorus_profile):
        bands = chorus_profile["character"]["frequency_bands"]
        assert self.EXPECTED_KEYS == set(bands.keys())

    def test_each_band_has_mean_and_relative(self, intro_profile):
        bands = intro_profile["character"]["frequency_bands"]
        for key, band in bands.items():
            assert "mean" in band, f"Band '{key}' missing 'mean'"
            assert "relative" in band, f"Band '{key}' missing 'relative'"


# ── stem_levels ───────────────────────────────────────────────────────────────

class TestStemLevels:
    def test_stem_levels_is_dict(self, chorus_profile):
        assert isinstance(chorus_profile["stems"]["stem_levels"], dict)

    def test_stem_levels_values_in_0_1(self, chorus_profile):
        for stem, level in chorus_profile["stems"]["stem_levels"].items():
            assert 0.0 <= level <= 1.0, f"stem_levels['{stem}'] = {level} out of range"

    def test_stem_levels_values_are_floats(self, chorus_profile):
        for stem, level in chorus_profile["stems"]["stem_levels"].items():
            assert isinstance(level, float), f"stem_levels['{stem}'] is not float"
