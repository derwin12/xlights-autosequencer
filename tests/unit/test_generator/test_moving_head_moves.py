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

    def test_per_head_placement_uses_its_own_group_position_slot(self):
        # A per-head placement fills exactly ONE of the 8 MH{n}_Settings
        # slots -- but which one, and what its "Heads:" field says, must
        # match the model's own position in the group (MH2 -> slot 2,
        # "Heads: 2"), not always slot 1/"Heads: 1". Reversed 2026-07-17:
        # a real generated .xsq showed MH-2's placement silently failed to
        # render (needed a manual click in xLights to fix) when written
        # into slot 1/"Heads: 1" -- diffing before/after the click showed
        # the fix was moving it to slot 2/"Heads: 2".
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        mh2_placement = result["MH2"][0]
        params = mh2_placement.parameters
        assert params["E_TEXTCTRL_MH1_Settings"] == ""
        assert "Heads: 2" in params["E_TEXTCTRL_MH2_Settings"]
        for slot in range(3, 9):
            assert params[f"E_TEXTCTRL_MH{slot}_Settings"] == ""

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

    def test_warmup_still_fits_for_back_to_back_qualifying_sections(self):
        # No natural gap between the two sections -- the first section's
        # own move gets its tail trimmed back to open a full warmup
        # window for the second, rather than the warmup being skipped
        # (user request, 2026-07-17: prefer shrinking the earlier effect
        # over silently having no warmup at all).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 15_000, 40, variation_seed=2),
            _assignment("chorus", 15_000, 30_000, 40, variation_seed=2),
        ]
        result = place_moving_head_moves(layout, assignments)
        placements = result["MH1"]
        assert len(placements) == 3  # section0 move (trimmed), section1 warmup, section1 move
        first_move, warmup, second_move = placements
        assert first_move.end_ms == 14_500  # trimmed back from its natural 15_000
        assert warmup.start_ms == 14_500 and warmup.end_ms == 15_000
        assert second_move.start_ms == 15_000  # not delayed -- the trim alone opened the gap

    def test_group_and_per_head_placements_never_overlap(self):
        # Realistic, non-overlapping sections. variation_seed=0:
        # section 0 (verse, top energy) -> dynamic pool idx0 "fan_pan_move"
        # (group); section 1 (chorus, low energy) -> static pool idx1
        # "l_r_static" (per_head). Global invariant: nothing placed on
        # "MH GRP" may overlap anything placed on MH1/MH2 (same channels).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=0),
            _assignment("chorus", 15_000, 30_000, 40, variation_seed=0),
        ]
        result = place_moving_head_moves(layout, assignments)
        group_placements = result.get("MH GRP", [])
        head_placements = [p for name in ("MH1", "MH2") for p in result.get(name, [])]
        for g in group_placements:
            for h in head_placements:
                assert not (g.start_ms < h.end_ms and g.end_ms > h.start_ms), (
                    f"overlap: group [{g.start_ms},{g.end_ms}) vs head [{h.start_ms},{h.end_ms})"
                )

    def test_per_head_move_trims_prior_group_moves_tail_to_open_warmup_gap(self):
        # Adversarial input: section 1 (per_head move) is given a start
        # time that overlaps section 0's (group move) natural end -- e.g.
        # a hypothetical rounding/boundary bug upstream. Rather than
        # delaying the per-head move, the group move's tail gets trimmed
        # back to open a full warmup window right before the per-head
        # move's own natural start (user preference, 2026-07-17).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=0),  # group fan_pan_move, natural end 15_000
            _assignment("chorus", 10_000, 25_000, 40, variation_seed=0),  # per_head l_r_static, natural start 10_000
        ]
        result = place_moving_head_moves(layout, assignments)
        group_move = result["MH GRP"][0]
        assert group_move.end_ms == 9_500  # trimmed back from its natural 15_000
        mh1_placements = result["MH1"]
        assert len(mh1_placements) == 2  # warmup + move -- not delayed, the trim alone was enough
        warmup, move = mh1_placements
        assert warmup.start_ms == 9_500 and warmup.end_ms == 10_000
        assert move.start_ms == 10_000  # its own natural start, unmoved
        assert not (group_move.start_ms < move.end_ms and group_move.end_ms > move.start_ms)

    def test_group_move_never_overlaps_prior_per_head_moves_across_all_heads(self):
        # Symmetric to the above, and exercising the multi-owner case: a
        # per-head move first (variation_seed=1, section 0 -> static pool
        # idx1 "l_r_static", giving MH1 and MH2 each their OWN distinct
        # placement object), then a group move (variation_seed=3, section
        # 1 -> dynamic pool idx0 "fan_pan_move") whose natural start
        # overlaps both of them -- every distinct owner must get trimmed,
        # not just whichever ends latest.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 15_000, 40, variation_seed=1),
            _assignment("verse", 10_000, 25_000, _STRONG_ENERGY_GATE, variation_seed=3),
        ]
        result = place_moving_head_moves(layout, assignments)
        head_placements = [p for name in ("MH1", "MH2") for p in result.get(name, [])]
        group_placements = result.get("MH GRP", [])
        for h in head_placements:
            for g in group_placements:
                assert not (g.start_ms < h.end_ms and g.end_ms > h.start_ms), (
                    f"overlap: head [{h.start_ms},{h.end_ms}) vs group [{g.start_ms},{g.end_ms})"
                )
