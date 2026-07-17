"""Tests for moving_head.place_moving_head_moves (gated per-section moves
mined from the MH Samples.xsq reference sequence)."""
from __future__ import annotations

from pathlib import Path

from src.generator.models import SectionAssignment, SectionEnergy
from src.generator.moving_head import (
    _DIMMER_FULL_ON,
    _MAX_MOVE_DURATION_MS,
    _MIN_SECTION_DURATION_MS,
    _STRONG_ENERGY_GATE,
    _WARMUP_DURATION_MS,
    place_moving_head_moves,
)
from src.grouper.layout import parse_layout
from src.themes.models import EffectLayer, Theme

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "grouper"


def _theme() -> Theme:
    return Theme(
        name="Test", mood="structural", occasion="general", genre="any", intent="test",
        layers=[EffectLayer(variant="Fire")], palette=["#FF0000", "#00FF00"],
    )


def _section(label: str, start_ms: int, end_ms: int, energy: int) -> SectionEnergy:
    return SectionEnergy(
        label=label, start_ms=start_ms, end_ms=end_ms,
        energy_score=energy, mood_tier="structural", impact_count=0,
    )


def _assignment(label: str, start_ms: int, end_ms: int, energy: int, variation_seed: int = 0) -> SectionAssignment:
    return SectionAssignment(
        section=_section(label, start_ms, end_ms, energy),
        theme=_theme(),
        variation_seed=variation_seed,
    )


class TestPlaceMovingHeadMoves:
    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assignments = [_assignment("verse", 0, 30_000, 40)]
        assert place_moving_head_moves(layout, assignments) == {}

    def test_low_energy_verse_gets_no_move(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 30_000, 40)]
        assert place_moving_head_moves(layout, assignments) == {}

    def test_short_chorus_below_min_duration_gets_no_move(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, _MIN_SECTION_DURATION_MS - 1000, 50)]
        assert place_moving_head_moves(layout, assignments) == {}

    def test_chorus_role_qualifies_even_at_low_energy(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40)]
        result = place_moving_head_moves(layout, assignments)
        assert result

    def test_top_energy_tier_qualifies_regardless_of_role(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE)]
        result = place_moving_head_moves(layout, assignments)
        assert result

    def test_per_head_move_places_on_individual_models_not_group(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        # variation_seed=2, section_index=0 -> static pool index 2 ("r_static"),
        # a per_head move -> placements land on MH1/MH2, not "MH GRP".
        assert "MH GRP" not in result
        assert set(result) == {"MH1", "MH2"}
        for placements in result.values():
            assert all(p.effect_name == "Moving Head" for p in placements)

    def test_fan_move_places_on_group_not_individual_heads(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        # variation_seed=0, section_index=0, dynamic pool -> "fan_pan_move" (index 0).
        assignments = [_assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=0)]
        result = place_moving_head_moves(layout, assignments)
        assert set(result) == {"MH GRP"}

    def test_move_duration_capped_within_long_section(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 60_000, 40)]
        result = place_moving_head_moves(layout, assignments)
        for placements in result.values():
            for p in placements:
                assert (p.end_ms - p.start_ms) <= _MAX_MOVE_DURATION_MS + 25

    def test_heads_settings_use_single_head_slot(self):
        # Per-head placements always write "Heads: 1" into MH1_Settings --
        # the group-index number in that field (e.g. "Heads: 2" on MH2's own
        # placement) is a copy-paste artifact in the reference sequence, not
        # meaningful behavior (user confirmation, 2026-07-17).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        mh2_placement = result["MH2"][0]
        assert "Heads: 1" in mh2_placement.parameters["E_TEXTCTRL_MH1_Settings"]

    def test_multiple_qualifying_sections_rotate_moves(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 15_000, 40, variation_seed=0),
            _assignment("chorus", 15_000, 30_000, 40, variation_seed=0),
        ]
        result = place_moving_head_moves(layout, assignments)
        assert len(result) >= 1
        total_placements = sum(len(v) for v in result.values())
        assert total_placements >= 2

    def test_jitter_is_deterministic_for_same_seed(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=3)]
        result1 = place_moving_head_moves(layout, assignments)
        result2 = place_moving_head_moves(layout, assignments)
        for key in result1:
            for p1, p2 in zip(result1[key], result2[key]):
                assert p1.parameters == p2.parameters

    def test_move_dimmer_defaults_to_instant_full_on_not_ramped(self):
        # variation_seed=2 -> "r_static" (a per_head static pose move).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        move = result["MH1"][-1]  # last placement for this target is the move itself
        assert _DIMMER_FULL_ON in move.parameters["E_TEXTCTRL_MH1_Settings"]

    def test_warmup_precedes_static_move_and_matches_its_pose(self):
        # A gap before the section (starts at 10_000, not 0) so the warmup
        # has room to fire (nothing already occupies 9_500-10_000).
        # variation_seed=2, section_index=0 -> "r_static" (Pan 45.0, Tilt 60.0).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 10_000, 25_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        placements = result["MH1"]
        assert len(placements) == 2
        warmup, move = placements
        assert warmup.end_ms == move.start_ms == 10_000
        assert abs((warmup.end_ms - warmup.start_ms) - _WARMUP_DURATION_MS) <= 25
        settings = warmup.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Pan: 45.0" in settings
        assert "Tilt: 60.0" in settings
        assert "Dimmer:" not in settings
        assert "Wheel:" not in settings
        assert "Shutter:" not in settings

    def test_warmup_matches_sweep_start_angle_not_end_angle(self):
        # variation_seed=1, dynamic pool -> "l_r_sweep"; head 1's pose sweeps
        # Pan -45.0 -> 45.0 (jittered -5.0 for this seed/section -> -50.0),
        # so the warmup should aim at the sweep's start (negative), not its
        # end (positive, ~40.0).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 10_000, 25_000, _STRONG_ENERGY_GATE, variation_seed=1)]
        result = place_moving_head_moves(layout, assignments)
        warmup = result["MH1"][0]
        settings = warmup.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Pan: -50.0" in settings

    def test_no_warmup_when_section_starts_at_zero(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        assert len(result["MH1"]) == 1

    def test_warmup_skipped_for_back_to_back_qualifying_sections(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 15_000, 40, variation_seed=2),
            _assignment("chorus", 15_000, 30_000, 40, variation_seed=2),
        ]
        result = place_moving_head_moves(layout, assignments)
        # No gap between the two sections -> no room/need for a second
        # warmup; exactly one placement per section, no warmups at all.
        assert len(result["MH1"]) == 2
