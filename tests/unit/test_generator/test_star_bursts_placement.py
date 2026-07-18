"""Tests for effect_placer._place_star_bursts (rare Pinwheel accent on
Star-family groups at each hierarchy.riff_bursts mark)."""
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

    def test_places_pinwheel_on_star_group(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        assert set(result) == {"06_PROP_Star"}
        p = result["06_PROP_Star"][0]
        assert p.effect_name == "Pinwheel"
        assert p.model_or_group == "06_PROP_Star"
        assert p.start_ms == 33_000
        assert p.end_ms == 33_000 + _STAR_BURST_DURATION_MS
        assert p.color_palette == ["#FF0000", "#FFFF00", "#FF8000"]
        assert p.parameters["E_SLIDER_Pinwheel_Arms"] == "3"
        assert "T_CHECKBOX_Canvas" not in p.parameters

    def test_renders_above_recipe_layers(self):
        result = _place_star_bursts(
            groups=[_star_group()], hierarchy=_hierarchy([33_000]), vocal_words=None,
        )
        assert all(p.layer < 0 for p in result["06_PROP_Star"])

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
        marks = sorted(p.start_ms for p in result["06_PROP_Star"])
        assert marks == [33_000]

    def test_multiple_star_groups_all_get_the_burst(self):
        other_star = PowerGroup(name="06_PROP_Star_Alt", tier=6, members=["Star 3"])
        result = _place_star_bursts(
            groups=[_star_group(), other_star], hierarchy=_hierarchy([33_000]),
            vocal_words=None,
        )
        assert set(result) == {"06_PROP_Star", "06_PROP_Star_Alt"}
