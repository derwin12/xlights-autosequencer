"""Tests for moving_head.place_moving_head_crash_accents (fan-out Pan/Tilt
punch on the moving-head group, matching effect_placer._place_crash_accents'
Shockwave at the same marks, plus an optional dark warmup lead-in)."""
from __future__ import annotations

from pathlib import Path

from src.analyzer.result import HierarchyResult, TimingMark
from src.generator.models import EffectPlacement
from src.generator.moving_head import (
    _CRASH_EFFECT_DURATION_MS,
    _CRASH_LEAD_MS,
    _CRASH_VOCAL_EXCLUSION_MS,
    _PREFERRED_WARMUP_DURATION_MS,
    place_moving_head_crash_accents,
)
from src.grouper.layout import parse_layout

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "grouper"


def _hierarchy(crash_times_ms: list[int], duration_ms: int = 200_000) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="song.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        crash_accents=[TimingMark(time_ms=t, confidence=None, label="crash") for t in crash_times_ms],
    )


def _punch(placements: list[EffectPlacement]) -> EffectPlacement:
    return next(p for p in placements if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"])


def _warmup(placements: list[EffectPlacement]) -> EffectPlacement:
    return next(p for p in placements if "Shutter: On" not in p.parameters["E_TEXTCTRL_MH1_Settings"])


class TestPlaceMovingHeadCrashAccents:
    def test_no_crash_marks_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([]), vocal_words=None)
        assert result == {}

    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=None)
        assert result == {}

    def test_punch_starts_before_mark_and_ends_after_it(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=None)
        assert set(result) == {"MH GRP"}
        p = _punch(result["MH GRP"])
        assert p.effect_name == "Moving Head"
        assert p.model_or_group == "MH GRP"
        assert abs(p.start_ms - (50_850 - _CRASH_LEAD_MS)) <= 25
        assert abs(p.end_ms - (50_850 + _CRASH_EFFECT_DURATION_MS)) <= 25

    def test_fans_out_pan_and_tilts_up_per_head(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=None)
        settings = _punch(result["MH GRP"]).parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Tilt: 78.5" in settings
        assert "PanOffset: 10.5" in settings
        assert "Wheel: 0.000000&comma;0.000000&comma;1.000000" in settings
        assert "Shutter: On" in settings

    def test_punch_dimmer_is_a_random_flicker_not_a_flat_flash(self):
        # Mined from the user's own preset (mhpresets/Random.xmh, 2026-07-17):
        # a point list bouncing between near-off and near-on, not a flat
        # "always on" flash.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=None)
        settings = _punch(result["MH GRP"]).parameters["E_TEXTCTRL_MH1_Settings"]
        # "&comma;" itself ends in a literal ';', so protect it before
        # splitting on ';' (the real per-command delimiter).
        safe = settings.replace("&comma;", "\x00")
        dimmer_value = safe.split("Dimmer: ", 1)[1].split(";", 1)[0]
        values = [float(v) for v in dimmer_value.replace("\x00", ",").split(",")]
        assert values[0:2] == [0.0, 1.0]
        assert values[-2:] == [1.0, 1.0]
        y_values = values[1::2]
        assert any(y < 0.2 for y in y_values)  # at least one real dip
        assert any(y > 0.9 for y in y_values)  # at least one real peak

    def test_punch_dimmer_is_deterministic_per_mark(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result1 = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=None)
        result2 = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=None)
        settings1 = _punch(result1["MH GRP"]).parameters["E_TEXTCTRL_MH1_Settings"]
        settings2 = _punch(result2["MH GRP"]).parameters["E_TEXTCTRL_MH1_Settings"]
        assert settings1 == settings2

    def test_two_crash_marks_get_different_dimmer_flicker(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([10_000, 50_000]), vocal_words=None)
        punches = [p for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"]]
        assert len(punches) == 2
        settings = [p.parameters["E_TEXTCTRL_MH1_Settings"] for p in punches]
        assert settings[0] != settings[1]

    def test_warmup_inserted_when_nothing_already_there(self):
        # No existing_placements passed and nothing before it on the
        # timeline -> the warmup uses the full preferred length, not a
        # short fixed one (user-observed real .xsq, 2026-07-17: a fixed
        # 750ms warmup was needlessly short when the whole timeline
        # before the mark was wide open).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=None)
        placements = result["MH GRP"]
        assert len(placements) == 2
        punch = _punch(placements)
        warmup = _warmup(placements)
        settings = warmup.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Tilt: 78.5" in settings
        assert "PanOffset: 10.5" in settings
        assert "Dimmer:" not in settings
        assert "Wheel:" not in settings
        assert "Shutter:" not in settings
        assert warmup.end_ms == punch.start_ms
        assert abs((warmup.end_ms - warmup.start_ms) - _PREFERRED_WARMUP_DURATION_MS) <= 25

    def test_warmup_skipped_when_wash_already_covers_the_window(self):
        # The existing placement ends exactly where the punch itself
        # starts -- it covers the warmup's lead-in window but does not
        # reach into the punch's own duration, so only the warmup is
        # skipped and the punch still fires.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        mark_ms = 50_850
        punch_start = mark_ms - _CRASH_LEAD_MS
        existing = {
            "MH GRP": [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group="MH GRP", start_ms=0, end_ms=punch_start,
            )],
        }
        result = place_moving_head_crash_accents(
            layout, _hierarchy([mark_ms]), vocal_words=None, existing_placements=existing,
        )
        placements = result["MH GRP"]
        assert len(placements) == 1
        assert "Shutter: On" in placements[0].parameters["E_TEXTCTRL_MH1_Settings"]

    def test_warmup_uses_only_the_natural_gap_when_something_precedes_it(self):
        # An existing placement ends 400ms before the punch's own lead-in
        # starts -- less than the preferred 3s, so the warmup should use
        # exactly that 400ms gap rather than the full preferred length
        # (the crash mark's timing is fixed, so nothing gets trimmed to
        # open more room; it just uses what's naturally there).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        mark_ms = 50_850
        punch_start = mark_ms - _CRASH_LEAD_MS
        existing = {
            "MH GRP": [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group="MH GRP", start_ms=0, end_ms=punch_start - 400,
            )],
        }
        result = place_moving_head_crash_accents(
            layout, _hierarchy([mark_ms]), vocal_words=None, existing_placements=existing,
        )
        placements = result["MH GRP"]
        warmup = _warmup(placements)
        assert warmup.start_ms == punch_start - 400
        assert warmup.end_ms == punch_start

    def test_two_close_crash_marks_warmup_never_overlaps_first_punch(self):
        # Two crash marks close enough together that the second mark's
        # preferred 3s warmup would otherwise reach back into the first
        # mark's own punch -- must be capped by that punch's end, not
        # just by place_moving_head_moves' placements.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        first_mark, second_mark = 10_000, 12_000  # 2s apart
        result = place_moving_head_crash_accents(layout, _hierarchy([first_mark, second_mark]), vocal_words=None)
        placements = sorted(result["MH GRP"], key=lambda p: p.start_ms)
        assert len(placements) == 4  # mark1: warmup+punch; mark2: a short (300ms) warmup+punch
        second_warmup = placements[2]
        assert "Shutter: On" not in second_warmup.parameters["E_TEXTCTRL_MH1_Settings"]
        assert second_warmup.start_ms == placements[1].end_ms  # starts exactly where the first punch ends
        for i, p in enumerate(placements):
            for q in placements[i + 1:]:
                assert not (p.start_ms < q.end_ms and p.end_ms > q.start_ms), (
                    f"overlap: [{p.start_ms},{p.end_ms}) vs [{q.start_ms},{q.end_ms})"
                )

    def test_crash_skipped_entirely_when_a_per_head_move_still_active(self):
        # A per-head move (e.g. from place_moving_head_moves) running on
        # MH1 during the crash's own window -- same DMX channels as the
        # group-targeted punch -- must cancel the crash outright, not just
        # its warmup (user-observed real xLights overlap, 2026-07-17).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        mark_ms = 50_850
        punch_start = mark_ms - _CRASH_LEAD_MS
        existing = {
            "MH1": [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group="MH1", start_ms=0, end_ms=punch_start + 1000,
            )],
        }
        result = place_moving_head_crash_accents(
            layout, _hierarchy([mark_ms]), vocal_words=None, existing_placements=existing,
        )
        assert result == {}

    def test_excludes_crash_near_vocal_word(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        vocal_words = [{"start_ms": 50_500, "end_ms": 51_000}]
        result = place_moving_head_crash_accents(layout, _hierarchy([50_850]), vocal_words=vocal_words)
        assert result == {}

    def test_keeps_crash_far_from_vocal_word(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        vocal_words = [{"start_ms": 10_000, "end_ms": 10_500}]
        far_time = 10_500 + _CRASH_VOCAL_EXCLUSION_MS + 1000
        result = place_moving_head_crash_accents(layout, _hierarchy([far_time]), vocal_words=vocal_words)
        assert set(result) == {"MH GRP"}

    def test_excludes_crash_at_or_after_fade_start(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(
            layout, _hierarchy([190_000], duration_ms=201_900), vocal_words=None,
            fade_exclusion_start_ms=189_000,
        )
        assert result == {}

    def test_multiple_crash_marks_each_placed(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_crash_accents(layout, _hierarchy([10_000, 50_000]), vocal_words=None)
        punches = [p for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"]]
        assert sorted(p.start_ms + _CRASH_LEAD_MS for p in punches) == [10_000, 50_000]
