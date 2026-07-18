"""Tests for moving_head.place_moving_head_ending_punches (quick straight-up
full-white flash on the moving-head group at each ending-'button' cymbal hit,
see crash_accents.detect_ending_punches, preceded by a single dark warmup)."""
from __future__ import annotations

from pathlib import Path

from src.analyzer.result import HierarchyResult, TimingMark
from src.generator.models import EffectPlacement
from src.generator.moving_head import (
    _ENDING_FLASH_DURATION_MS,
    _ENDING_FLASH_OFF_GAP_MS,
    find_moving_head_groups,
    place_moving_head_ending_punches,
)
from src.grouper.layout import parse_layout

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "grouper"


def _hierarchy(punch_times_ms: list[int], duration_ms: int = 200_000) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.2.0",
        source_file="song.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        ending_punches=[
            TimingMark(time_ms=t, confidence=None, label="ending_punch")
            for t in punch_times_ms
        ],
    )


def _flashes(placements: list[EffectPlacement]) -> list[EffectPlacement]:
    return [p for p in placements if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"]]


def _warmups(placements: list[EffectPlacement]) -> list[EffectPlacement]:
    return [p for p in placements if "Shutter: On" not in p.parameters["E_TEXTCTRL_MH1_Settings"]]


class TestPlaceMovingHeadEndingPunches:
    def test_no_marks_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assert place_moving_head_ending_punches(layout, _hierarchy([])) == {}

    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assert place_moving_head_ending_punches(layout, _hierarchy([190_700])) == {}

    def test_flash_starts_on_mark_full_white_straight_up(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_ending_punches(layout, _hierarchy([190_700]))
        assert set(result) == {"MH GRP"}
        (p,) = _flashes(result["MH GRP"])
        assert p.effect_name == "Moving Head"
        assert p.start_ms == 190_700
        assert p.end_ms == 190_700 + _ENDING_FLASH_DURATION_MS
        settings = p.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Tilt: 0.0" in settings
        assert "Pan: 0.0" in settings
        assert "PanOffset: 0.0" in settings
        assert "Shutter: On" in settings
        # Shared sliders authoritative on xLights save (bug-304 family):
        # must match the per-head text pose (0 degrees -> "0").
        assert p.parameters["E_SLIDER_MHTilt"] == "0"
        assert p.parameters["E_SLIDER_MHPan"] == "0"

    def test_dark_warmups_fill_every_gap(self):
        """Heads return to home whenever no effect is active (user-confirmed
        on real hardware, 2026-07-18), so a dark position-hold warmup fills
        the lead-in AND every off-gap between flashes — the timeline is
        contiguous from song start through the last flash."""
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        marks = [192_000, 192_500]
        result = place_moving_head_ending_punches(layout, _hierarchy(marks))
        placements = sorted(result["MH GRP"], key=lambda p: p.start_ms)
        warmups = _warmups(result["MH GRP"])
        assert len(warmups) == 2  # lead-in + the off-gap between the flashes
        # Lead-in fills the entire natural gap — back to song start when
        # nothing else occupies the channels (user request, 2026-07-18).
        assert placements[0].start_ms == 0
        for prev, nxt in zip(placements, placements[1:]):
            assert prev.end_ms == nxt.start_ms, "timeline must be contiguous"
        for w in warmups:
            settings = w.parameters["E_TEXTCTRL_MH1_Settings"]
            assert "Tilt: 0.0" in settings
            assert "Dimmer" not in settings and "Wheel" not in settings
        settings = w.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Tilt: 0.0" in settings
        assert "Dimmer" not in settings and "Wheel" not in settings

    def test_warmup_adapts_to_natural_gap(self):
        """An existing placement ending shortly before the first mark leaves
        only the gap between them for the warmup."""
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        existing = {
            "MH GRP": [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group="MH GRP",
                start_ms=190_000, end_ms=191_500, parameters={},
            )],
        }
        result = place_moving_head_ending_punches(
            layout, _hierarchy([192_000]), existing_placements=existing)
        (w,) = _warmups(result["MH GRP"])
        assert w.start_ms == 191_500
        assert w.end_ms == 192_000

    def test_warmup_skipped_only_when_back_to_back_in_same_pose(self):
        """User rule (2026-07-18): no warmup if and only if the previous
        placement ends EXACTLY where the flash starts AND its ending pose
        matches — with no active effect the heads return home, so a
        matching pose across any gap has already been lost."""
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        # Steal a real flash's parameters to build a prior placement whose
        # pose fields exactly match what the warmup would set.
        seed = place_moving_head_ending_punches(layout, _hierarchy([192_000]))
        flash_params = _flashes(seed["MH GRP"])[0].parameters

        def _place_with_prior_ending_at(end_ms: int):
            existing = {
                "MH GRP": [EffectPlacement(
                    effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                    model_or_group="MH GRP",
                    start_ms=190_000, end_ms=end_ms, parameters=dict(flash_params),
                )],
            }
            return place_moving_head_ending_punches(
                layout, _hierarchy([192_000]), existing_placements=existing)

        # Back-to-back + same pose -> no warmup.
        back_to_back = _place_with_prior_ending_at(192_000)
        assert _warmups(back_to_back["MH GRP"]) == []
        assert len(_flashes(back_to_back["MH GRP"])) == 1
        # Same pose but a 1s gap -> heads went home -> warmup fills the gap.
        gapped = _place_with_prior_ending_at(191_000)
        (w,) = _warmups(gapped["MH GRP"])
        assert w.start_ms == 191_000
        assert w.end_ms == 192_000

    def test_cluster_flashes_trimmed_to_leave_off_gap(self):
        """Machine-gun marks closer than the flash duration: each flash ends
        _ENDING_FLASH_OFF_GAP_MS before the next mark so the hits stay
        visually distinct instead of merging into continuous light."""
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        # Frame-aligned (25ms grid) so EffectPlacement's snap doesn't shift them.
        marks = [192_000, 192_250, 192_500]
        result = place_moving_head_ending_punches(layout, _hierarchy(marks))
        flashes = _flashes(result["MH GRP"])
        assert [p.start_ms for p in flashes] == marks
        assert flashes[0].end_ms == 192_250 - _ENDING_FLASH_OFF_GAP_MS
        assert flashes[1].end_ms == 192_500 - _ENDING_FLASH_OFF_GAP_MS
        assert flashes[2].end_ms == 192_500 + _ENDING_FLASH_DURATION_MS

    def test_mark_at_or_after_fade_exclusion_is_skipped(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_ending_punches(
            layout, _hierarchy([190_700, 195_000]),
            fade_exclusion_start_ms=193_000,
        )
        assert [p.start_ms for p in _flashes(result["MH GRP"])] == [190_700]

    def test_overlapping_existing_placement_skips_the_flash(self):
        """Same channel-conflict rule as the crash punch: a placement on the
        group's own key OR any individual head model blocks the flash."""
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        existing = {
            "MH GRP": [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group="MH GRP",
                start_ms=190_500, end_ms=191_500, parameters={},
            )],
        }
        result = place_moving_head_ending_punches(
            layout, _hierarchy([190_700, 192_000]),
            existing_placements=existing,
        )
        assert [p.start_ms for p in _flashes(result["MH GRP"])] == [192_000]

    def test_per_head_existing_placement_also_blocks(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        head = find_moving_head_groups(layout)[0].head_names[0]
        existing = {
            head: [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group=head,
                start_ms=190_500, end_ms=191_500, parameters={},
            )],
        }
        result = place_moving_head_ending_punches(
            layout, _hierarchy([190_700]), existing_placements=existing,
        )
        assert result == {}

    def test_flash_clamped_to_song_duration(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        result = place_moving_head_ending_punches(
            layout, _hierarchy([199_900], duration_ms=200_000))
        (p,) = _flashes(result["MH GRP"])
        assert p.end_ms == 200_000
