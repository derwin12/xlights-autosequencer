"""Tests for effect_placer._place_crash_accents (rare whole-house crash accent)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.analyzer.result import HierarchyResult, TimingMark
from src.generator.effect_placer import (
    _CRASH_EFFECT_DURATION_MS,
    _CRASH_LEAD_MS,
    _CRASH_VOCAL_EXCLUSION_MS,
    _place_crash_accents,
)
from src.generator.models import GenerationConfig
from src.grouper.grouper import PowerGroup


def _hierarchy(crash_times_ms: list[int], duration_ms: int = 200_000) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="song.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        crash_accents=[TimingMark(time_ms=t, confidence=None, label="crash") for t in crash_times_ms],
    )


def _fades_group() -> PowerGroup:
    return PowerGroup(name="01_BASE_All_FADES", tier=1, members=["m1", "m2"])


def _variant_library() -> MagicMock:
    lib = MagicMock()
    variant = MagicMock()
    variant.parameter_overrides = {"E_SLIDER_Shockwave_End_Radius": "100"}
    lib.get.side_effect = lambda name: variant if name == "Shockwave Full Fast" else None
    return lib


class TestPlaceCrashAccents:
    def test_no_crash_marks_returns_empty(self):
        result = _place_crash_accents(
            groups=[_fades_group()], hierarchy=_hierarchy([]),
            vocal_words=None, variant_library=_variant_library(),
        )
        assert result == {}

    def test_missing_fades_group_returns_empty(self):
        result = _place_crash_accents(
            groups=[PowerGroup(name="06_PROP_Snowflakes", tier=6, members=["m1"])],
            hierarchy=_hierarchy([50_850]),
            vocal_words=None, variant_library=_variant_library(),
        )
        assert result == {}

    def test_places_shockwave_on_fades_group(self):
        result = _place_crash_accents(
            groups=[_fades_group()], hierarchy=_hierarchy([50_850]),
            vocal_words=None, variant_library=_variant_library(),
        )
        assert set(result) == {"01_BASE_All_FADES"}
        placements = result["01_BASE_All_FADES"]
        assert len(placements) == 1
        p = placements[0]
        assert p.effect_name == "Shockwave"
        assert p.model_or_group == "01_BASE_All_FADES"
        assert abs(p.start_ms - (50_850 - _CRASH_LEAD_MS)) <= 25
        assert abs(p.end_ms - (50_850 + _CRASH_EFFECT_DURATION_MS)) <= 25
        assert p.parameters == {"E_SLIDER_Shockwave_End_Radius": "100"}

    def test_excludes_crash_near_vocal_word(self):
        vocal_words = [{"start_ms": 50_500, "end_ms": 51_000}]
        result = _place_crash_accents(
            groups=[_fades_group()], hierarchy=_hierarchy([50_850]),
            vocal_words=vocal_words, variant_library=_variant_library(),
        )
        assert result == {}

    def test_keeps_crash_far_from_vocal_word(self):
        vocal_words = [{"start_ms": 10_000, "end_ms": 10_500}]
        far_time = 10_500 + _CRASH_VOCAL_EXCLUSION_MS + 1000
        result = _place_crash_accents(
            groups=[_fades_group()], hierarchy=_hierarchy([far_time]),
            vocal_words=vocal_words, variant_library=_variant_library(),
        )
        assert set(result) == {"01_BASE_All_FADES"}

    def test_excludes_crash_at_or_after_fade_start(self):
        result = _place_crash_accents(
            groups=[_fades_group()], hierarchy=_hierarchy([190_000], duration_ms=201_900),
            vocal_words=None, variant_library=_variant_library(),
            fade_exclusion_start_ms=189_000,
        )
        assert result == {}

    def test_keeps_crash_before_fade_start(self):
        result = _place_crash_accents(
            groups=[_fades_group()], hierarchy=_hierarchy([50_850], duration_ms=201_900),
            vocal_words=None, variant_library=_variant_library(),
            fade_exclusion_start_ms=199_900,
        )
        assert set(result) == {"01_BASE_All_FADES"}

    def test_multiple_crash_marks_each_placed(self):
        result = _place_crash_accents(
            groups=[_fades_group()], hierarchy=_hierarchy([10_000, 50_000]),
            vocal_words=None, variant_library=_variant_library(),
        )
        placements = result["01_BASE_All_FADES"]
        assert sorted(p.start_ms + _CRASH_LEAD_MS for p in placements) == [10_000, 50_000]


class TestCrashAccentsConfigFlag:
    def test_flag_defaults_to_true(self):
        config = GenerationConfig(
            audio_path=Path("/fake/song.mp3"),
            layout_path=Path("/fake/layout.xml"),
        )
        assert config.crash_accents is True

    def test_flag_can_be_disabled(self):
        config = GenerationConfig(
            audio_path=Path("/fake/song.mp3"),
            layout_path=Path("/fake/layout.xml"),
            crash_accents=False,
        )
        assert config.crash_accents is False
