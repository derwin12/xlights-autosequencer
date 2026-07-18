"""Tests for moving_head.place_moving_head_riff_bursts (mid-height fan-out
Pan/Tilt punch on the moving-head group at each hierarchy.riff_bursts mark,
plus an optional dark warmup lead-in). Twin of
test_moving_head_crash_accents.py with the riff pose's own constants."""
from __future__ import annotations

from pathlib import Path

from src.analyzer.result import HierarchyResult, TimingMark
from src.generator.models import EffectPlacement
from src.generator.moving_head import (
    _RIFF_EFFECT_DURATION_MS,
    _RIFF_LEAD_MS,
    _RIFF_PAN_OFFSET_DEG,
    _RIFF_TILT_DEG,
    place_moving_head_riff_bursts,
)
from src.grouper.layout import parse_layout

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "grouper"


def _hierarchy(riff_times_ms: list[int], duration_ms: int = 200_000) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.3.0",
        source_file="song.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        riff_bursts=[TimingMark(time_ms=t, confidence=None, label="riff_burst") for t in riff_times_ms],
    )


def _punch(placements: list[EffectPlacement]) -> EffectPlacement:
    return next(p for p in placements if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"])


def _warmup(placements: list[EffectPlacement]) -> EffectPlacement:
    return next(p for p in placements if "Shutter: On" not in p.parameters["E_TEXTCTRL_MH1_Settings"])


class TestPlaceMovingHeadRiffBursts:
    def test_no_riff_marks_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_riff_bursts(layout, _hierarchy([]), vocal_words=None)
        assert result == {}

    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        result = place_moving_head_riff_bursts(layout, _hierarchy([33_000]), vocal_words=None)
        assert result == {}

    def test_punch_starts_before_mark_and_ends_after_it(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_riff_bursts(layout, _hierarchy([33_000]), vocal_words=None)
        assert set(result) == {"MH GRP"}
        p = _punch(result["MH GRP"])
        assert p.effect_name == "Moving Head"
        assert p.model_or_group == "MH GRP"
        assert abs(p.start_ms - (33_000 - _RIFF_LEAD_MS)) <= 25
        assert abs(p.end_ms - (33_000 + _RIFF_EFFECT_DURATION_MS)) <= 25

    def test_pose_is_mid_height_wide_fan_distinct_from_crash(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_riff_bursts(layout, _hierarchy([33_000]), vocal_words=None)
        settings = _punch(result["MH GRP"]).parameters["E_TEXTCTRL_MH1_Settings"]
        assert f"Tilt: {_RIFF_TILT_DEG}" in settings
        assert f"PanOffset: {_RIFF_PAN_OFFSET_DEG}" in settings
        assert "Wheel: 0.000000&comma;0.000000&comma;1.000000" in settings
        assert "Shutter: On" in settings
        # Distinct from the crash punch's pose (Tilt 78.5 / PanOffset 10.5).
        assert _RIFF_TILT_DEG != "78.5"
        assert _RIFF_PAN_OFFSET_DEG != "10.5"

    def test_shared_sliders_match_the_punch_pose(self):
        expected_tilt = str(round(float(_RIFF_TILT_DEG) * 10))
        expected_pan_offset = str(round(float(_RIFF_PAN_OFFSET_DEG) * 10))
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_riff_bursts(layout, _hierarchy([33_000]), vocal_words=None)
        punch = _punch(result["MH GRP"])
        assert punch.parameters["E_SLIDER_MHTilt"] == expected_tilt
        assert punch.parameters["E_SLIDER_MHPanOffset"] == expected_pan_offset
        warmup = _warmup(result["MH GRP"])
        assert warmup.parameters["E_SLIDER_MHTilt"] == expected_tilt
        assert warmup.parameters["E_SLIDER_MHPanOffset"] == expected_pan_offset

    def test_vocal_word_near_mark_excludes_it(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        vocal_words = [{"start_ms": 32_900, "end_ms": 33_100}]
        result = place_moving_head_riff_bursts(
            layout, _hierarchy([33_000]), vocal_words=vocal_words,
        )
        assert result == {}

    def test_fade_exclusion_drops_marks_at_or_after_boundary(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_riff_bursts(
            layout, _hierarchy([33_000, 190_000]), vocal_words=None,
            fade_exclusion_start_ms=180_000,
        )
        marks = sorted(p.start_ms for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"])
        assert len(marks) == 1

    def test_existing_channel_placement_skips_the_mark(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        blocker = EffectPlacement(
            effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
            model_or_group="MH GRP", start_ms=32_500, end_ms=34_000,
            parameters={},
        )
        result = place_moving_head_riff_bursts(
            layout, _hierarchy([33_000]), vocal_words=None,
            existing_placements={"MH GRP": [blocker]},
        )
        assert result == {}
