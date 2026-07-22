"""Tests for effect_placer._place_floodlight_pulses (rare "On" accent on
individual floodlight models, rotating through the family's members, at each
hierarchy.kick_pulses mark)."""
from __future__ import annotations

from src.analyzer.result import HierarchyResult, TimingMark
from src.generator.effect_placer import (
    _FLOODLIGHT_PULSE_DURATION_MS,
    _FLOODLIGHT_PULSE_VOCAL_EXCLUSION_MS,
    _place_floodlight_pulses,
)
from src.grouper.grouper import PowerGroup


def _hierarchy(kick_times_ms: list[int], duration_ms: int = 200_000) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.6.0",
        source_file="song.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        kick_pulses=[TimingMark(time_ms=t, confidence=None, label="kick_pulse") for t in kick_times_ms],
    )


def _floodlight_group() -> PowerGroup:
    return PowerGroup(name="06_PROP_FloodLight", tier=6, members=["FloodLight1", "FloodLight2"])


class TestPlaceFloodlightPulses:
    def test_no_kick_marks_returns_empty(self):
        result = _place_floodlight_pulses(
            groups=[_floodlight_group()], hierarchy=_hierarchy([]), vocal_words=None,
        )
        assert result == {}

    def test_no_floodlight_group_returns_empty(self):
        result = _place_floodlight_pulses(
            groups=[PowerGroup(name="06_PROP_Snowflakes", tier=6, members=["m1"])],
            hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        assert result == {}

    def test_places_on_pulse_on_one_individual_floodlight(self):
        result = _place_floodlight_pulses(
            groups=[_floodlight_group()], hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        assert set(result) == {"FloodLight1"}
        p = result["FloodLight1"][0]
        assert p.effect_name == "On"
        assert p.model_or_group == "FloodLight1"
        assert p.start_ms == 33_000
        assert p.end_ms == 33_000 + _FLOODLIGHT_PULSE_DURATION_MS
        assert p.color_palette == ["#FFFFFF"]
        assert p.fade_in_ms > 0
        assert p.fade_out_ms > 0

    def test_successive_marks_rotate_across_members(self):
        result = _place_floodlight_pulses(
            groups=[_floodlight_group()], hierarchy=_hierarchy([10_000, 33_000, 60_000]),
            vocal_words=None,
        )
        assert set(result) == {"FloodLight1", "FloodLight2"}
        assert result["FloodLight1"][0].start_ms == 10_000
        assert result["FloodLight2"][0].start_ms == 33_000
        assert result["FloodLight1"][1].start_ms == 60_000

    def test_renders_above_recipe_layers(self):
        result = _place_floodlight_pulses(
            groups=[_floodlight_group()], hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        assert all(p.layer < 0 for p in result["FloodLight1"])

    def test_vocal_word_near_mark_excludes_it(self):
        vocal_words = [{"start_ms": 32_900, "end_ms": 33_100}]
        result = _place_floodlight_pulses(
            groups=[_floodlight_group()], hierarchy=_hierarchy([33_000]),
            vocal_words=vocal_words,
        )
        assert result == {}

    def test_vocal_exclusion_boundary_is_exact(self):
        vocal_words = [{"start_ms": 0, "end_ms": 1000}]
        just_outside = 1000 + _FLOODLIGHT_PULSE_VOCAL_EXCLUSION_MS + 1
        result = _place_floodlight_pulses(
            groups=[_floodlight_group()], hierarchy=_hierarchy([just_outside]),
            vocal_words=vocal_words,
        )
        assert result != {}

    def test_fade_exclusion_drops_marks_at_or_after_boundary(self):
        result = _place_floodlight_pulses(
            groups=[_floodlight_group()], hierarchy=_hierarchy([33_000, 190_000]),
            vocal_words=None, fade_exclusion_start_ms=180_000,
        )
        marks = sorted(p.start_ms for p in result["FloodLight1"])
        assert marks == [33_000]

    def test_multiple_floodlight_groups_share_the_rotation(self):
        other = PowerGroup(name="06_PROP_FloodLight_Alt", tier=6, members=["FloodLight3"])
        result = _place_floodlight_pulses(
            groups=[_floodlight_group(), other], hierarchy=_hierarchy([10_000, 33_000, 60_000]),
            vocal_words=None,
        )
        assert set(result) == {"FloodLight1", "FloodLight2", "FloodLight3"}
