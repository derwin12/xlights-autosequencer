"""TDD tests for src/story/lighting_mapper.py — must FAIL before implementation."""
import pytest

from src.story.lighting_mapper import map_lighting

# ---------------------------------------------------------------------------
# Known valid roles and energy levels
# ---------------------------------------------------------------------------

ALL_ROLES = [
    "intro", "verse", "pre_chorus", "chorus", "post_chorus",
    "bridge", "instrumental_break", "climax", "ambient_bridge",
    "outro", "interlude",
]

ENERGY_LEVELS = ["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_dict(self):
        result = map_lighting("chorus", "high")
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        """The returned dict must contain the expected top-level keys."""
        result = map_lighting("chorus", "high")
        for key in ("active_tiers", "brightness_ceiling", "beat_effect_density",
                    "transition_in", "theme_layer_mode"):
            assert key in result, f"Missing key '{key}' in result: {result}"

    def test_active_tiers_is_list(self):
        result = map_lighting("verse", "medium")
        assert isinstance(result["active_tiers"], list)

    def test_brightness_ceiling_is_float(self):
        result = map_lighting("verse", "medium")
        assert isinstance(result["brightness_ceiling"], float)

    def test_beat_effect_density_is_float(self):
        result = map_lighting("verse", "medium")
        assert isinstance(result["beat_effect_density"], float)

    def test_transition_in_is_string(self):
        result = map_lighting("chorus", "high")
        assert isinstance(result["transition_in"], str)

    def test_theme_layer_mode_is_string(self):
        result = map_lighting("chorus", "high")
        assert isinstance(result["theme_layer_mode"], str)


# ---------------------------------------------------------------------------
# Brightness ceiling bounds
# ---------------------------------------------------------------------------

class TestBrightnessCeiling:
    def test_brightness_always_in_unit_interval(self):
        """brightness_ceiling must always be in [0.0, 1.0]."""
        for role in ALL_ROLES:
            for energy in ENERGY_LEVELS:
                result = map_lighting(role, energy)
                val = result["brightness_ceiling"]
                assert 0.0 <= val <= 1.0, (
                    f"brightness_ceiling={val} out of range for role={role}, energy={energy}"
                )

    def test_chorus_high_brightness_at_least_085(self):
        """Chorus at high energy should be very bright."""
        result = map_lighting("chorus", "high")
        assert result["brightness_ceiling"] >= 0.85

    def test_intro_low_brightness_at_most_060(self):
        """Intro at low energy should be subdued."""
        result = map_lighting("intro", "low")
        assert result["brightness_ceiling"] <= 0.6

    def test_climax_high_brightness_near_max(self):
        """Climax at high energy should approach maximum brightness."""
        result = map_lighting("climax", "high")
        assert result["brightness_ceiling"] >= 0.9

    def test_ambient_bridge_low_brightness(self):
        """Ambient bridge should have lower brightness regardless of energy."""
        result = map_lighting("ambient_bridge", "low")
        assert result["brightness_ceiling"] <= 0.6


# ---------------------------------------------------------------------------
# Beat effect density bounds
# ---------------------------------------------------------------------------

class TestBeatEffectDensity:
    def test_density_always_in_unit_interval(self):
        """beat_effect_density must always be in [0.0, 1.0]."""
        for role in ALL_ROLES:
            for energy in ENERGY_LEVELS:
                result = map_lighting(role, energy)
                val = result["beat_effect_density"]
                assert 0.0 <= val <= 1.0, (
                    f"beat_effect_density={val} out of range for role={role}, energy={energy}"
                )

    def test_high_energy_density_at_least_070(self):
        """Any role with high energy should have density >= 0.7."""
        for role in ["chorus", "climax", "post_chorus"]:
            result = map_lighting(role, "high")
            assert result["beat_effect_density"] >= 0.7, (
                f"Expected density >= 0.7 for {role}/high, got {result['beat_effect_density']}"
            )

    def test_low_energy_density_at_most_040(self):
        """Low-energy sections should have sparse beat effects."""
        for role in ["intro", "outro", "ambient_bridge"]:
            result = map_lighting(role, "low")
            assert result["beat_effect_density"] <= 0.4, (
                f"Expected density <= 0.4 for {role}/low, got {result['beat_effect_density']}"
            )


# ---------------------------------------------------------------------------
# Active tiers
# ---------------------------------------------------------------------------

class TestActiveTiers:
    def test_active_tiers_never_empty(self):
        """All valid role+energy combinations must activate at least one tier."""
        for role in ALL_ROLES:
            for energy in ENERGY_LEVELS:
                result = map_lighting(role, energy)
                assert len(result["active_tiers"]) > 0, (
                    f"active_tiers is empty for role={role}, energy={energy}"
                )

    def test_chorus_high_includes_upper_tiers(self):
        """Chorus at high energy should activate tiers 5-8 (high-tier effects)."""
        result = map_lighting("chorus", "high")
        tiers = result["active_tiers"]
        assert any(t >= 5 for t in tiers), (
            f"chorus/high active_tiers {tiers} does not include any tier >= 5"
        )

    def test_intro_low_only_low_numbered_tiers(self):
        """Intro at low energy should only activate tiers 1-3."""
        result = map_lighting("intro", "low")
        tiers = result["active_tiers"]
        assert all(t <= 3 for t in tiers), (
            f"intro/low active_tiers {tiers} includes tiers > 3"
        )

    def test_chorus_low_retains_chorus_base_tiers(self):
        """Chorus with low energy should still have chorus-level tiers, just dimmer."""
        high_result = map_lighting("chorus", "high")
        low_result = map_lighting("chorus", "low")
        high_max = max(high_result["active_tiers"])
        low_max = max(low_result["active_tiers"])
        # Chorus/low should reach at least as far as verse/medium tiers
        assert low_max >= 3, (
            f"chorus/low max tier {low_max} is unexpectedly low"
        )

    def test_verse_medium_moderate_tier_range(self):
        """Verse at medium energy uses a moderate tier set (not all low, not all high)."""
        result = map_lighting("verse", "medium")
        tiers = result["active_tiers"]
        # Should have some mid-range tiers but not require tier 7+
        assert len(tiers) >= 2

    def test_tiers_are_positive_integers(self):
        """All tier values must be positive integers."""
        for role in ALL_ROLES:
            result = map_lighting(role, "medium")
            for t in result["active_tiers"]:
                assert isinstance(t, int) and t >= 1, (
                    f"Invalid tier value {t!r} for role={role}"
                )


# ---------------------------------------------------------------------------
# Transition mode
# ---------------------------------------------------------------------------

class TestTransitionIn:
    def test_intro_transition_is_snap_on_or_quick_build(self):
        """Intro should open with either snap_on or quick_build."""
        result = map_lighting("intro", "low")
        assert result["transition_in"] in ("snap_on", "quick_build"), (
            f"Expected snap_on or quick_build for intro, got '{result['transition_in']}'"
        )

    def test_chorus_transition_is_hard_cut_or_quick_build(self):
        """Chorus transitions should be energetic: hard_cut or quick_build."""
        result = map_lighting("chorus", "high")
        assert result["transition_in"] in ("hard_cut", "quick_build"), (
            f"Expected hard_cut or quick_build for chorus, got '{result['transition_in']}'"
        )

    def test_all_roles_have_non_empty_transition(self):
        """No role should produce an empty transition_in string."""
        for role in ALL_ROLES:
            result = map_lighting(role, "medium")
            assert result["transition_in"] != "", (
                f"transition_in is empty for role={role}"
            )


# ---------------------------------------------------------------------------
# Theme layer mode
# ---------------------------------------------------------------------------

class TestThemeLayerMode:
    def test_chorus_is_full_or_base_mid(self):
        """Chorus should use full theme stack or at least base+mid layers."""
        result = map_lighting("chorus", "high")
        assert result["theme_layer_mode"] in ("full", "base_mid"), (
            f"Expected full or base_mid for chorus, got '{result['theme_layer_mode']}'"
        )

    def test_intro_is_base_only(self):
        """Intro should use only the base layer for a minimal opening look."""
        result = map_lighting("intro", "low")
        assert result["theme_layer_mode"] == "base_only", (
            f"Expected base_only for intro, got '{result['theme_layer_mode']}'"
        )

    def test_outro_is_base_only_or_base_mid(self):
        """Outro should wind down: base_only or base_mid."""
        result = map_lighting("outro", "low")
        assert result["theme_layer_mode"] in ("base_only", "base_mid"), (
            f"Expected base_only or base_mid for outro, got '{result['theme_layer_mode']}'"
        )

    def test_all_roles_have_non_empty_theme_layer_mode(self):
        """No role should return an empty theme_layer_mode."""
        for role in ALL_ROLES:
            result = map_lighting(role, "medium")
            assert result["theme_layer_mode"] != "", (
                f"theme_layer_mode is empty for role={role}"
            )


# ---------------------------------------------------------------------------
# Energy level ordering (brightness and density should scale with energy)
# ---------------------------------------------------------------------------

class TestEnergyOrdering:
    @pytest.mark.parametrize("role", ["chorus", "verse", "bridge", "instrumental_break"])
    def test_brightness_scales_with_energy(self, role: str):
        """For the same role, higher energy must produce equal-or-higher brightness."""
        low = map_lighting(role, "low")["brightness_ceiling"]
        med = map_lighting(role, "medium")["brightness_ceiling"]
        high = map_lighting(role, "high")["brightness_ceiling"]
        assert low <= med, f"{role}: low brightness {low} > medium {med}"
        assert med <= high, f"{role}: medium brightness {med} > high {high}"

    @pytest.mark.parametrize("role", ["chorus", "verse", "bridge", "instrumental_break"])
    def test_density_scales_with_energy(self, role: str):
        """For the same role, higher energy must produce equal-or-higher beat density."""
        low = map_lighting(role, "low")["beat_effect_density"]
        med = map_lighting(role, "medium")["beat_effect_density"]
        high = map_lighting(role, "high")["beat_effect_density"]
        assert low <= med, f"{role}: low density {low} > medium {med}"
        assert med <= high, f"{role}: medium density {med} > high {high}"
