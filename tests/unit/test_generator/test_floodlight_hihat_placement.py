"""Tests for effect_placer._place_floodlight_hihat_accents (direct hihat-hit
-> individual floodlight rotation, no rarity filtering unlike
_place_floodlight_pulses)."""
from __future__ import annotations

from src.analyzer.result import HierarchyResult, TimingMark
from src.generator.effect_placer import (
    _FLOODLIGHT_HIHAT_DURATION_MS,
    _place_floodlight_hihat_accents,
)
from src.generator.models import frame_align
from src.grouper.grouper import PowerGroup


def _hierarchy(hihat_times_ms: list[int], duration_ms: int = 200_000) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.6.0",
        source_file="song.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        hihat_hits=[TimingMark(time_ms=t, confidence=None, label="hihat") for t in hihat_times_ms],
    )


def _floodlight_group() -> PowerGroup:
    return PowerGroup(name="06_PROP_FloodLight", tier=6, members=["FloodLight1", "FloodLight2"])


class TestPlaceFloodlightHihatAccents:
    def test_no_hihat_hits_returns_empty(self):
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group()], hierarchy=_hierarchy([]),
        )
        assert result == {}

    def test_no_floodlight_group_returns_empty(self):
        result = _place_floodlight_hihat_accents(
            groups=[PowerGroup(name="06_PROP_Snowflakes", tier=6, members=["m1"])],
            hierarchy=_hierarchy([1_000]),
        )
        assert result == {}

    def test_every_hihat_hit_places_a_tick(self):
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group()], hierarchy=_hierarchy([1_000, 1_250, 1_500]),
        )
        total = sum(len(v) for v in result.values())
        assert total == 3

    def test_places_on_one_individual_floodlight(self):
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group()], hierarchy=_hierarchy([1_000]),
        )
        assert set(result) == {"FloodLight1"}
        p = result["FloodLight1"][0]
        assert p.effect_name == "On"
        assert p.model_or_group == "FloodLight1"
        assert p.start_ms == 1_000
        assert p.end_ms == frame_align(1_000 + _FLOODLIGHT_HIHAT_DURATION_MS)
        assert p.color_palette == ["#FFFFFF"]
        assert p.fade_in_ms > 0
        assert p.fade_out_ms > 0

    def test_successive_hits_rotate_across_members(self):
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group()], hierarchy=_hierarchy([1_000, 1_250, 1_500]),
        )
        assert set(result) == {"FloodLight1", "FloodLight2"}
        assert result["FloodLight1"][0].start_ms == 1_000
        assert result["FloodLight2"][0].start_ms == 1_250
        assert result["FloodLight1"][1].start_ms == 1_500

    def test_renders_above_recipe_layers(self):
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group()], hierarchy=_hierarchy([1_000]),
        )
        assert all(p.layer < 0 for p in result["FloodLight1"])

    def test_no_vocal_exclusion_unlike_floodlight_pulses(self):
        # Deliberately no vocal_words parameter at all -- hihat accents are
        # a background texture, not a discrete accent, so there is nothing
        # to exclude near vocals.
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group()], hierarchy=_hierarchy([1_000]),
        )
        assert result != {}

    def test_fade_exclusion_drops_marks_at_or_after_boundary(self):
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group()], hierarchy=_hierarchy([1_000, 190_000]),
            fade_exclusion_start_ms=180_000,
        )
        marks = sorted(p.start_ms for p in result["FloodLight1"])
        assert marks == [1_000]

    def test_multiple_floodlight_groups_share_the_rotation(self):
        other = PowerGroup(name="06_PROP_FloodLight_Alt", tier=6, members=["FloodLight3"])
        result = _place_floodlight_hihat_accents(
            groups=[_floodlight_group(), other], hierarchy=_hierarchy([1_000, 1_250, 1_500]),
        )
        assert set(result) == {"FloodLight1", "FloodLight2", "FloodLight3"}
