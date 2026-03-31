"""Failing TDD tests for src/story/stem_curves.py.

These tests define the contract for extract_stem_curves() and MUST fail before
the implementation exists. Do not create the implementation to make them pass
until the full module is ready.
"""
from __future__ import annotations

import math

import pytest

from tests.fixtures.story_fixture import (
    make_hierarchy_dict,
    make_hierarchy_dict_no_stems,
    FIXTURE_DURATION_MS,
)

# This import MUST fail until the module is implemented.
from src.story.stem_curves import extract_stem_curves  # noqa: E402


# ── Fixture helpers ────────────────────────────────────────────────────────────

FIXTURE_DURATION_SEC = FIXTURE_DURATION_MS / 1000  # 60.0
EXPECTED_FRAMES = math.ceil(FIXTURE_DURATION_SEC * 2)  # 120


@pytest.fixture()
def hierarchy():
    return make_hierarchy_dict()


@pytest.fixture()
def curves(hierarchy):
    return extract_stem_curves(hierarchy, FIXTURE_DURATION_MS)


@pytest.fixture()
def curves_no_stems():
    return extract_stem_curves(make_hierarchy_dict_no_stems(), FIXTURE_DURATION_MS)


# ── Return structure ───────────────────────────────────────────────────────────

class TestReturnStructure:
    def test_returns_dict(self, curves):
        assert isinstance(curves, dict)

    def test_has_sample_rate_hz(self, curves):
        assert "sample_rate_hz" in curves

    def test_has_stem_keys(self, curves):
        for stem in ("drums", "bass", "vocals", "guitar", "piano", "other"):
            assert stem in curves, f"Missing key: {stem!r}"

    def test_has_full_mix_key(self, curves):
        assert "full_mix" in curves


# ── sample_rate_hz ─────────────────────────────────────────────────────────────

class TestSampleRateHz:
    def test_sample_rate_hz_is_2(self, curves):
        assert curves["sample_rate_hz"] == 2

    def test_sample_rate_hz_is_int(self, curves):
        assert isinstance(curves["sample_rate_hz"], int)


# ── Array lengths ─────────────────────────────────────────────────────────────

class TestArrayLengths:
    def test_array_length_equals_ceil_duration_times_2(self, curves):
        """ceil(60s * 2fps) = 120 frames."""
        assert len(curves["drums"]["rms"]) == EXPECTED_FRAMES

    def test_all_stem_rms_arrays_same_length(self, curves):
        lengths = {stem: len(curves[stem]["rms"]) for stem in
                   ("drums", "bass", "vocals", "guitar", "piano", "other")}
        values = set(lengths.values())
        assert len(values) == 1, f"Stem rms arrays have different lengths: {lengths}"

    def test_full_mix_rms_length_matches_stems(self, curves):
        stem_len = len(curves["drums"]["rms"])
        assert len(curves["full_mix"]["rms"]) == stem_len

    def test_60s_song_produces_120_frames(self, curves):
        assert len(curves["drums"]["rms"]) == 120

    def test_arbitrary_duration_length(self, hierarchy):
        """45s * 2fps = 90 frames."""
        result = extract_stem_curves(hierarchy, 45_000)
        assert len(result["drums"]["rms"]) == 90

    def test_non_even_duration_is_ceil(self, hierarchy):
        """61s * 2fps = 122 frames (ceil(61*2)=122)."""
        result = extract_stem_curves(hierarchy, 61_000)
        assert len(result["drums"]["rms"]) == 122


# ── Per-stem rms values ────────────────────────────────────────────────────────

class TestStemRmsValues:
    def test_drums_rms_is_list_of_floats(self, curves):
        rms = curves["drums"]["rms"]
        assert isinstance(rms, list)
        for i, v in enumerate(rms):
            assert isinstance(v, float), f"drums rms[{i}] is {type(v).__name__}, not float"

    def test_drums_rms_values_in_0_1(self, curves):
        for i, v in enumerate(curves["drums"]["rms"]):
            assert 0.0 <= v <= 1.0, f"drums rms[{i}] = {v} out of [0,1]"

    def test_vocals_rms_is_list_of_floats(self, curves):
        rms = curves["vocals"]["rms"]
        assert isinstance(rms, list)
        for i, v in enumerate(rms):
            assert isinstance(v, float), f"vocals rms[{i}] is {type(v).__name__}, not float"

    def test_vocals_rms_values_in_0_1(self, curves):
        for i, v in enumerate(curves["vocals"]["rms"]):
            assert 0.0 <= v <= 1.0, f"vocals rms[{i}] = {v} out of [0,1]"

    def test_no_numpy_floats_in_drums(self, curves):
        """Values must be plain Python floats, not numpy.float32/float64."""
        for v in curves["drums"]["rms"]:
            assert type(v) is float, f"Expected Python float, got {type(v)}"

    def test_no_numpy_floats_in_vocals(self, curves):
        for v in curves["vocals"]["rms"]:
            assert type(v) is float, f"Expected Python float, got {type(v)}"


# ── full_mix structure ─────────────────────────────────────────────────────────

class TestFullMix:
    REQUIRED_KEYS = {"rms", "spectral_centroid_hz", "harmonic_rms", "percussive_rms"}

    def test_full_mix_has_required_keys(self, curves):
        assert self.REQUIRED_KEYS == set(curves["full_mix"].keys()), (
            f"full_mix keys mismatch: {set(curves['full_mix'].keys())}"
        )

    def test_full_mix_rms_in_0_1(self, curves):
        for i, v in enumerate(curves["full_mix"]["rms"]):
            assert 0.0 <= v <= 1.0, f"full_mix rms[{i}] = {v} out of [0,1]"

    def test_full_mix_all_arrays_same_length(self, curves):
        stem_len = len(curves["drums"]["rms"])
        for key in ("rms", "spectral_centroid_hz", "harmonic_rms", "percussive_rms"):
            arr = curves["full_mix"][key]
            assert len(arr) == stem_len, (
                f"full_mix[{key!r}] length {len(arr)} != stem length {stem_len}"
            )

    def test_full_mix_arrays_are_lists_of_floats(self, curves):
        for key in ("rms", "harmonic_rms", "percussive_rms"):
            arr = curves["full_mix"][key]
            assert isinstance(arr, list)
            for i, v in enumerate(arr):
                assert isinstance(v, float), (
                    f"full_mix[{key!r}][{i}] is {type(v).__name__}, not float"
                )

    def test_full_mix_spectral_centroid_hz_non_negative(self, curves):
        for i, v in enumerate(curves["full_mix"]["spectral_centroid_hz"]):
            assert v >= 0.0, f"full_mix spectral_centroid_hz[{i}] = {v} is negative"

    def test_no_numpy_floats_in_full_mix_rms(self, curves):
        for v in curves["full_mix"]["rms"]:
            assert type(v) is float, f"Expected Python float, got {type(v)}"


# ── No-stems fallback ─────────────────────────────────────────────────────────

class TestNoStemsFallback:
    def test_returns_dict_when_no_stems(self, curves_no_stems):
        assert isinstance(curves_no_stems, dict)

    def test_stem_arrays_all_zeros_when_no_stems(self, curves_no_stems):
        """When stems_available is empty, per-stem arrays must be all-zeros."""
        for stem in ("drums", "bass", "vocals", "guitar", "piano", "other"):
            rms = curves_no_stems[stem]["rms"]
            assert all(v == 0.0 for v in rms), (
                f"{stem} rms not all-zero without stems: {rms[:5]}..."
            )

    def test_zeros_have_correct_length_when_no_stems(self, curves_no_stems):
        for stem in ("drums", "bass", "vocals", "guitar", "piano", "other"):
            rms = curves_no_stems[stem]["rms"]
            assert len(rms) == EXPECTED_FRAMES

    def test_full_mix_still_populated_when_no_stems(self, curves_no_stems):
        """full_mix rms comes from energy_curves full_mix, not stems."""
        rms = curves_no_stems["full_mix"]["rms"]
        assert len(rms) == EXPECTED_FRAMES
        # Should not be all-zeros even without stems
        assert any(v > 0.0 for v in rms)


# ── Missing stem graceful handling ────────────────────────────────────────────

class TestMissingStemGraceful:
    def test_missing_stem_in_energy_curves_yields_zeros(self, hierarchy):
        """If a stem key is absent from energy_curves, output zeros of correct length."""
        import copy
        h = copy.deepcopy(hierarchy)
        del h["energy_curves"]["guitar"]
        result = extract_stem_curves(h, FIXTURE_DURATION_MS)
        rms = result["guitar"]["rms"]
        assert len(rms) == EXPECTED_FRAMES
        assert all(v == 0.0 for v in rms)


# ── Downsampling ──────────────────────────────────────────────────────────────

class TestDownsampling:
    """Source energy_curves are at 10fps; output must be at 2fps.

    5 input frames are averaged to produce 1 output frame.
    Frame 0 of output = mean(input[0:5])
    Frame 1 of output = mean(input[5:10])
    ...etc.
    """

    def test_downsampling_first_frame_is_average_of_first_5_input_frames(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        # Set drums to known sequence: 0.1, 0.2, 0.3, 0.4, 0.5, then 0.9 repeatedly
        known = [0.1, 0.2, 0.3, 0.4, 0.5] + [0.9] * (600 - 5)
        h["energy_curves"]["drums"] = {"sample_rate": 10.0, "values": known}
        result = extract_stem_curves(h, FIXTURE_DURATION_MS)
        expected_first = (0.1 + 0.2 + 0.3 + 0.4 + 0.5) / 5  # = 0.3
        assert result["drums"]["rms"][0] == pytest.approx(expected_first, abs=0.01)

    def test_downsampling_second_frame_is_average_of_next_5_input_frames(self, hierarchy):
        import copy
        h = copy.deepcopy(hierarchy)
        known = [0.0] * 5 + [0.6, 0.7, 0.8, 0.9, 1.0] + [0.0] * (600 - 10)
        h["energy_curves"]["drums"] = {"sample_rate": 10.0, "values": known}
        result = extract_stem_curves(h, FIXTURE_DURATION_MS)
        expected_second = (0.6 + 0.7 + 0.8 + 0.9 + 1.0) / 5  # = 0.8
        assert result["drums"]["rms"][1] == pytest.approx(expected_second, abs=0.01)

    def test_downsampling_preserves_relative_magnitudes(self, hierarchy):
        """Intro (low) → Chorus (high) ordering preserved after downsampling."""
        result = extract_stem_curves(make_hierarchy_dict(), FIXTURE_DURATION_MS)
        # Frame index 0 = t=0s (intro, energy=0.2)
        # Frame index 72 = t=36s (chorus start, energy=0.8)
        intro_val = result["full_mix"]["rms"][0]
        chorus_val = result["full_mix"]["rms"][72]
        assert chorus_val > intro_val

    def test_output_length_is_correct_after_downsampling(self, hierarchy):
        """600 input frames at 10fps → 120 output frames at 2fps."""
        result = extract_stem_curves(hierarchy, FIXTURE_DURATION_MS)
        assert len(result["drums"]["rms"]) == 120


# ── Fixture-driven value spot checks ──────────────────────────────────────────

class TestFixtureSpotChecks:
    def test_intro_vocals_rms_near_zero(self, curves):
        """Fixture vocals = 0.0 in intro (0-12s) → output frames 0-23 near 0."""
        vocal_rms = curves["vocals"]["rms"]
        # Frames 0-23 correspond to 0-12s at 2fps
        for i in range(24):
            assert vocal_rms[i] == pytest.approx(0.0, abs=0.01), (
                f"vocals rms[{i}] = {vocal_rms[i]} expected ~0 in intro"
            )

    def test_chorus_vocals_rms_above_threshold(self, curves):
        """Fixture vocals = 0.6 in chorus (36-54s) → output frames 72-107 > 0."""
        vocal_rms = curves["vocals"]["rms"]
        # Frames 72-107 correspond to 36-54s at 2fps
        for i in range(72, 108):
            assert vocal_rms[i] > 0.1, (
                f"vocals rms[{i}] = {vocal_rms[i]} expected >0.1 in chorus"
            )

    def test_chorus_drums_rms_higher_than_intro(self, curves):
        """Drums energy 0.7 in chorus vs 0.1 in intro."""
        drum_rms = curves["drums"]["rms"]
        intro_avg = sum(drum_rms[:12]) / 12    # frames 0-11 = 0-6s
        chorus_avg = sum(drum_rms[72:96]) / 24  # frames 72-95 = 36-48s
        assert chorus_avg > intro_avg
