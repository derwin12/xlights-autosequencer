"""Tests for moving_head.place_moving_head_moves (gated per-section moves
mined from the MH Samples.xsq reference sequence)."""
from __future__ import annotations

from pathlib import Path

from src.generator.models import SectionAssignment, SectionEnergy
from src.generator.moving_head import (
    _choose_move,
    _DIMMER_FULL_ON,
    _jitter,
    _MAX_MOVE_DURATION_MS,
    _MIN_SECTION_DURATION_MS,
    _MIN_WARMUP_DURATION_MS,
    _PREFERRED_WARMUP_DURATION_MS,
    _STRONG_ENERGY_GATE,
    MOVE_LIBRARY,
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

    def test_repeated_sweep_alternates_direction(self):
        # User request (2026-07-18): a repeated l_r_sweep/r_l_sweep
        # back-to-back reads as the same move twice, not variety -- when
        # the rotation would naturally pick the same sweep direction as
        # the section right before it, swap to the other direction.
        # section_index=1 and section_index=5 both land on "l_r_sweep"
        # via the natural (variation_seed + section_index) % 4 rotation.
        first = _choose_move(1, variation_seed=0, dynamic=True)
        assert first == "l_r_sweep"
        second = _choose_move(5, variation_seed=0, dynamic=True, previous_move=first)
        assert second == "r_l_sweep"

    def test_non_sweep_repeat_is_left_alone(self):
        # The alternation rule only applies to the two sweep moves --
        # a naturally-repeated non-sweep move (e.g. two sections landing
        # on "fan_pan_move") isn't forced to change.
        first = _choose_move(0, variation_seed=0, dynamic=True)
        assert first == "fan_pan_move"
        second = _choose_move(4, variation_seed=0, dynamic=True, previous_move=first)
        assert second == "fan_pan_move"

    def test_l_r_sweep_moves_every_head_the_same_direction(self):
        # Regression (2026-07-18, user-reported): head 2's pose in
        # "l_r_sweep" had a reversed pan_vc tuple (a copy-paste from
        # r_l_sweep), fighting the other 3 heads mid-sweep instead of
        # moving with them. Confirmed against the vendor reference
        # sequence (MH Samples.xsq): its equivalent sweep segments have
        # every head's Pan VC pointing the same direction, never
        # alternating.
        move = MOVE_LIBRARY["l_r_sweep"]
        pan_vcs = [pose.pan_vc for pose in move.poses]
        assert len(set(pan_vcs)) == 1, f"Expected identical pan_vc across all heads, got {pan_vcs}"

    def test_shared_sliders_match_the_pose_not_the_zero_default(self):
        # Regression (2026-07-17/18, bug found via a real before/after xLights
        # diff, then corrected against the vendor reference sequence):
        # E_SLIDER_MHPan/E_SLIDER_MHTilt were always left at their "0"
        # default regardless of the pose's actual angle. xLights treats those
        # shared sliders as authoritative for whichever axis isn't
        # value-curve-driven -- opening a generated effect with a nonzero
        # static Tilt but a "0" slider made xLights silently zero the Tilt
        # out on save. Both sliders must reflect the pose's real angle
        # (jittered), not the unconditional "0" default -- and, confirmed
        # against MH Samples.xsq, in degrees*10 integer form (e.g. Pan:
        # 45.0 -> "450"), not the plain-decimal-degrees format the text
        # itself uses.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        # variation_seed=2, section_index=0 -> static pool index 2 ("r_static"),
        # every head posed at pan=45.0, tilt=60.0 (see MOVE_LIBRARY).
        jitter_pan, jitter_tilt = _jitter(variation_seed=2, section_index=0)
        params = result["MH2"][0].parameters
        assert params["E_SLIDER_MHPan"] == str(round((45.0 + jitter_pan) * 10))
        assert params["E_SLIDER_MHTilt"] == str(round((60.0 + jitter_tilt) * 10))

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
        # has room to fire -- nothing occupies anything before it, so it
        # gets the full preferred 3s (_PREFERRED_WARMUP_DURATION_MS).
        # variation_seed=2, section_index=0 -> "r_static" (Pan 45.0, Tilt 60.0).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 10_000, 25_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        placements = result["MH1"]
        assert len(placements) == 2
        warmup, move = placements
        assert warmup.end_ms == move.start_ms == 10_000
        assert abs((warmup.end_ms - warmup.start_ms) - _PREFERRED_WARMUP_DURATION_MS) <= 25
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
        # section0's move is genuinely in the way (zero natural gap), so
        # it's trimmed down to open ONLY the defined minimum -- never up
        # to the full 3s (user correction, 2026-07-17: reserve the longer
        # warmup for stretches where nothing needs to be shortened).
        assert first_move.end_ms == 14_250  # trimmed back from its natural 15_000 by 750ms
        assert warmup.start_ms == 14_250 and warmup.end_ms == 15_000
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
        # The group move is genuinely in the way (0 natural gap at
        # 10_000), so it's trimmed down to open ONLY the defined minimum,
        # never up to the full 3s.
        assert group_move.end_ms == 9_250  # trimmed back from its natural 15_000 by 750ms
        mh1_placements = result["MH1"]
        assert len(mh1_placements) == 2  # warmup + move -- not delayed, the trim alone was enough
        warmup, move = mh1_placements
        assert warmup.start_ms == 9_250 and warmup.end_ms == 10_000
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

    def test_vc_driven_axis_omits_its_shared_slider_entirely(self):
        # Regression (2026-07-18): confirmed against the vendor reference
        # sequence (MH Samples.xsq) that whichever axis is value-curve-driven
        # has its shared E_SLIDER_MHPan/E_SLIDER_MHTilt key OMITTED entirely
        # from the effect's parameters -- never present, not just zeroed.
        # variation_seed=1, dynamic pool -> "l_r_sweep" (per_head, Pan VC,
        # static Tilt).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=1)]
        result = place_moving_head_moves(layout, assignments)
        move = result["MH1"][-1]
        params = move.parameters
        assert "E_SLIDER_MHPan" not in params
        assert "E_SLIDER_MHTilt" in params

    def test_pan_vc_move_gets_matching_top_level_valuecurve_key(self):
        # variation_seed=1, dynamic pool -> "l_r_sweep" (per_head, Pan VC).
        # xLights doesn't recognize/display a per-head Pan VC unless the
        # effect also carries a top-level E_VALUECURVE_MHPan key mirroring
        # it -- confirmed missing from every generated Pan-VC effect and
        # present on every VC-driven effect in the reference sequence
        # (real-world testing, 2026-07-17: a generated effect's curve
        # never showed in the xLights UI, even after clicking).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=1)]
        result = place_moving_head_moves(layout, assignments)
        move = result["MH1"][-1]
        params = move.parameters
        assert "E_VALUECURVE_MHPan" in params
        # The top-level descriptor must mirror the same curve written
        # into the per-head text (same Min/Max/P1/P2), just without the
        # "Pan VC: " prefix.
        assert f"Pan VC: {params['E_VALUECURVE_MHPan']}" in params["E_TEXTCTRL_MH1_Settings"]
        assert "E_VALUECURVE_MHTilt" not in params

    def test_tilt_vc_move_gets_matching_top_level_valuecurve_key(self):
        # variation_seed=3, dynamic pool -> "u_d_tilt" (per_head, Tilt VC).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=3)]
        result = place_moving_head_moves(layout, assignments)
        move = result["MH1"][-1]
        params = move.parameters
        assert "E_VALUECURVE_MHTilt" in params
        assert "E_VALUECURVE_MHPan" not in params

    def test_group_fan_move_gets_matching_top_level_valuecurve_key(self):
        # variation_seed=0, dynamic pool -> "fan_pan_move" (group, Tilt VC).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=0)]
        result = place_moving_head_moves(layout, assignments)
        move = result["MH GRP"][-1]
        assert "E_VALUECURVE_MHTilt" in move.parameters

    def test_static_pose_move_gets_no_top_level_valuecurve_key(self):
        # variation_seed=2, static pool -> "r_static" (no VC at all).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        move = result["MH1"][-1]
        assert "E_VALUECURVE_MHPan" not in move.parameters
        assert "E_VALUECURVE_MHTilt" not in move.parameters

    def test_warmup_never_gets_a_top_level_valuecurve_key(self):
        # A warmup is always a static pre-position, even for a VC move --
        # it must never carry an active value curve of its own.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 10_000, 25_000, _STRONG_ENERGY_GATE, variation_seed=1)]
        result = place_moving_head_moves(layout, assignments)
        warmup = result["MH1"][0]
        assert "E_VALUECURVE_MHPan" not in warmup.parameters
        assert "E_VALUECURVE_MHTilt" not in warmup.parameters

    def test_warmup_uses_whatever_partial_room_is_available_up_to_3s(self):
        # Nothing occupies this head before the section, but the section
        # itself only starts at 2_000 -- less than the preferred 3s, more
        # than the defined minimum. The warmup should use exactly what's
        # available (2s), not clamp down to the defined minimum.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 2_000, 15_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments)
        warmup, move = result["MH1"]
        assert warmup.start_ms == 0 and warmup.end_ms == 2_000
        assert move.start_ms == 2_000

    def test_warmup_falls_back_to_defined_minimum_when_floor_blocks_a_bigger_trim(self):
        # Adversarial input: section 1 starts only 1_500ms into section 0
        # (group fan_pan_move), far too little room for even the defined
        # minimum warmup once section 0's floor (1s past its own start) is
        # respected. Trims section 0 down to its floor and pushes the
        # incoming move out just enough to guarantee the defined minimum
        # warmup -- "a bit of both" (user preference, 2026-07-17).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("verse", 0, 15_000, _STRONG_ENERGY_GATE, variation_seed=0),  # group fan_pan_move
            _assignment("chorus", 1_500, 25_000, 40, variation_seed=0),  # per_head l_r_static
        ]
        result = place_moving_head_moves(layout, assignments)
        group_move = result["MH GRP"][0]
        assert group_move.end_ms == 1_000  # trimmed all the way to its own floor
        warmup, move = result["MH1"]
        assert warmup.start_ms == 1_000 and warmup.end_ms == 1_750
        assert (warmup.end_ms - warmup.start_ms) == _MIN_WARMUP_DURATION_MS
        assert move.start_ms == 1_750  # pushed past its natural 1_500 to guarantee the minimum
