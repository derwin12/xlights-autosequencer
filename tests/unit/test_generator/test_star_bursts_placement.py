"""Tests for effect_placer._place_star_bursts (rare Pinwheel accent on
individual star models, rotating through the star family's members, at each
hierarchy.riff_bursts mark)."""
from __future__ import annotations

from src.analyzer.result import HierarchyResult, TimingMark
from src.generator.effect_placer import (
    _STAR_BURST_DURATION_MS,
    _STAR_BURST_VOCAL_EXCLUSION_MS,
    _place_star_bursts,
)
from src.grouper.grouper import PowerGroup


def _hierarchy(riff_times_ms: list[int], duration_ms: int = 200_000) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.4.0",
        source_file="song.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        riff_bursts=[TimingMark(time_ms=t, confidence=None, label="riff_burst") for t in riff_times_ms],
    )


def _star_group() -> PowerGroup:
    return PowerGroup(name="06_PROP_Star", tier=6, members=["Star 1", "Star 2"])


class TestPlaceStarBursts:
    def test_no_riff_marks_returns_empty(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([]), vocal_words=None,
        )
        assert result == {}

    def test_no_star_group_returns_empty(self):
        result = _place_star_bursts(
            groups=[PowerGroup(name="06_PROP_Snowflakes", tier=6, members=["m1"])],
            hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        assert result == {}

    def test_places_pinwheel_on_one_individual_star_member(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        # "Star 2" never won a burst this round, so it doesn't appear at all
        # -- the Off is local to each burst's own window, not a whole-song
        # backdrop (see TestStarBurstOffBackdrop).
        assert set(result) == {"Star 1"}
        pinwheels = [p for p in result["Star 1"] if p.effect_name == "Pinwheel"]
        assert len(pinwheels) == 1
        p = pinwheels[0]
        assert p.effect_name == "Pinwheel"
        assert p.model_or_group == "Star 1"
        assert p.start_ms == 33_000
        assert p.end_ms == 33_000 + _STAR_BURST_DURATION_MS
        assert p.color_palette == ["#FF0000", "#FFFF00", "#FF8000"]
        assert p.parameters["E_SLIDER_Pinwheel_Arms"] == "3"
        assert "T_CHECKBOX_Canvas" not in p.parameters

    def test_successive_marks_rotate_across_members(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([10_000, 33_000, 60_000]),
            vocal_words=None,
        )
        assert set(result) == {"Star 1", "Star 2"}
        star1_pinwheels = [p.start_ms for p in result["Star 1"] if p.effect_name == "Pinwheel"]
        star2_pinwheels = [p.start_ms for p in result["Star 2"] if p.effect_name == "Pinwheel"]
        assert star1_pinwheels == [10_000, 60_000]
        assert star2_pinwheels == [33_000]

    def test_renders_above_recipe_layers(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        bursts = [p for p in result["Star 1"] if p.effect_name == "Pinwheel"]
        assert all(p.layer < 0 for p in bursts)

    def test_vocal_word_near_mark_excludes_it(self):
        vocal_words = [{"start_ms": 32_900, "end_ms": 33_100}]
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000]),
            vocal_words=vocal_words,
        )
        assert result == {}

    def test_vocal_exclusion_boundary_is_exact(self):
        vocal_words = [{"start_ms": 0, "end_ms": 1000}]
        just_outside = 1000 + _STAR_BURST_VOCAL_EXCLUSION_MS + 1
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([just_outside]),
            vocal_words=vocal_words,
        )
        assert result != {}

    def test_fade_exclusion_drops_marks_at_or_after_boundary(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000, 190_000]),
            vocal_words=None, fade_exclusion_start_ms=180_000,
        )
        marks = sorted(p.start_ms for p in result["Star 1"] if p.effect_name == "Pinwheel")
        assert marks == [33_000]

    def test_multiple_star_groups_share_the_rotation(self):
        other_star = PowerGroup(name="06_PROP_Star_Alt", tier=6, members=["Star 3"])
        result = _place_star_bursts(
            groups=[_star_group(), other_star], hierarchy=_hierarchy([10_000, 33_000, 60_000]),
            vocal_words=None,
        )
        assert set(result) == {"Star 1", "Star 2", "Star 3"}
        assert result["Star 1"][0].start_ms == 10_000
        assert result["Star 2"][0].start_ms == 33_000
        assert result["Star 3"][0].start_ms == 60_000


class TestStarBurstOffBackdrop:
    """An Off with the SAME start/end as each burst keeps nothing bleeding
    through from another source during the burst's own window, wherever the
    Pinwheel doesn't fully cover the buffer (user request, 2026-08-04;
    corrected 2026-08-07 to match the burst's window exactly rather than a
    lead-in before it). Deliberately scoped to that one burst, not a
    whole-song backdrop -- an earlier whole-song version blacked out the
    star family GROUP's own per-section content for the entire song, since
    an individual member model renders after (and overrides) the group for
    its own pixels whenever it has ANY effect active (user report,
    2026-08-07)."""

    def test_member_with_a_burst_gets_a_matching_off(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000], duration_ms=200_000),
            vocal_words=None,
        )
        burst = next(p for p in result["Star 1"] if p.effect_name == "Pinwheel")
        off = [p for p in result["Star 1"] if p.effect_name == "Off"]
        assert len(off) == 1
        assert off[0].start_ms == burst.start_ms
        assert off[0].end_ms == burst.end_ms
        assert off[0].model_or_group == "Star 1"

    def test_off_renders_below_the_burst_and_the_recipe(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        burst = next(p for p in result["Star 1"] if p.effect_name == "Pinwheel")
        off = next(p for p in result["Star 1"] if p.effect_name == "Off")
        assert off.layer > burst.layer
        # Must render behind the star recipe's own layers (0-2), not level
        # with them -- a lower layer number renders in FRONT (models.py:144).
        assert off.layer == 5

    def test_member_never_hit_gets_no_off(self):
        # Only "Star 1" receives the single mark, so "Star 2" (never a burst
        # target) shouldn't appear in the result at all -- there's no burst
        # to protect.
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000], duration_ms=200_000),
            vocal_words=None,
        )
        assert "Star 2" not in result

    def test_no_riff_marks_gets_no_off_either(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([]), vocal_words=None,
        )
        assert result == {}
