"""Tests for moving_head.place_moving_head_moves (gated per-section moves
mined from the MH Samples.xsq reference sequence)."""
from __future__ import annotations

from pathlib import Path

from src.analyzer.result import TimingMark, TimingTrack
from src.generator.models import EffectPlacement, SectionAssignment, SectionEnergy
from src.generator.moving_head import (
    _choose_lit_pair,
    _choose_move,
    _DIMMER_FULL_ON,
    _DIMMER_OFF,
    _free_windows,
    _FULL_HEADS_ENERGY_GATE,
    _jitter,
    _MAX_MOVE_DURATION_MS,
    _MIN_SECTION_DURATION_MS,
    _MIN_SPLIT_SEGMENT_MS,
    _MIN_WARMUP_DURATION_MS,
    _MOVE_BAR_CAP,
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


def _bars(interval_ms: int, count: int) -> TimingTrack:
    return TimingTrack(
        name="Bars", algorithm_name="test", element_type="segment",
        marks=[TimingMark(time_ms=i * interval_ms, confidence=1.0) for i in range(count)],
        quality_score=1.0,
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

    def test_qualifying_but_not_peak_energy_darkens_two_of_four_heads(self):
        # User request (2026-07-18): a qualifying section that clears the
        # gate but isn't genuinely peak energy shouldn't always run all 4
        # heads -- only 2 should light, the other 2 stay dark.
        # role="chorus" + energy=40 qualifies (is_strong) but is well under
        # _FULL_HEADS_ENERGY_GATE, and under _STRONG_ENERGY_GATE too so
        # dynamic=False -> static pool. variation_seed=1, section_index=0
        # -> static pool index 1 ("l_r_static", per_head): heads 1&2 posed
        # pan=-45, heads 3&4 posed pan=45. lit_pair for
        # (section_index=0, variation_seed=1) -> _HEAD_PAIRS[1] = (3, 4).
        # A second, much louder section (95) is included so the song's own
        # peak-relative check doesn't also treat 40 as "near this song's
        # peak" -- see test_song_relative_gate_* below for that behavior
        # in isolation.
        layout = parse_layout(FIXTURES / "moving_head_layout_4heads.xml")
        assignments = [
            _assignment("chorus", 0, 15_000, 40, variation_seed=1),
            _assignment("verse", 20_000, 35_000, 95, variation_seed=1),
        ]
        result = place_moving_head_moves(layout, assignments)
        lit_pair = _choose_lit_pair(section_index=0, variation_seed=1)
        assert lit_pair == (3, 4)

        def move_settings(head_name, head_index):
            # Warmups carry no "Shutter" command; pick the FIRST real move
            # (this section's, not the second section's).
            key = f"E_TEXTCTRL_MH{head_index}_Settings"
            moves = [p for p in result[head_name] if "Shutter: On" in p.parameters[key]]
            return moves[0].parameters[key]

        assert f"Dimmer: {_DIMMER_OFF}" in move_settings("MH1", 1)
        assert f"Dimmer: {_DIMMER_OFF}" in move_settings("MH2", 2)
        assert f"Dimmer: {_DIMMER_FULL_ON}" in move_settings("MH3", 3)
        assert f"Dimmer: {_DIMMER_FULL_ON}" in move_settings("MH4", 4)

    def test_static_held_move_alternates_full_and_half_lit_per_bar(self):
        # User request (2026-07-22): a long held static pose (e.g.
        # l_r_static) read as boring -- alternate all-4-heads-lit /
        # half-heads-lit per bar instead of one flat 4-heads-lit hold for
        # the whole move. Bar 0 (first bar) is always full; bars after
        # that alternate. Purely a Dimmer toggle -- Pan/Tilt/PanOffset
        # never change (same held pose throughout).
        # role="chorus" + energy=40 -> qualifies via role, dynamic=False
        # (40 < _STRONG_ENERGY_GATE) -> static pool. variation_seed=1,
        # section_index=0 -> static pool index 1 ("l_r_static", per_head).
        # toggle_pair = _choose_lit_pair(0, variation_seed+1=2) = (1, 4) --
        # MH1/MH4 stay lit every bar, MH2/MH3 toggle off on odd bars.
        layout = parse_layout(FIXTURES / "moving_head_layout_4heads.xml")
        assignments = [_assignment("chorus", 0, 8_000, 40, variation_seed=1)]
        bars = _bars(2_000, 5)  # bar marks at 0, 2000, 4000, 6000, 8000
        result = place_moving_head_moves(layout, assignments, bars=bars)

        def dimmer_states(head_name, head_index):
            key = f"E_TEXTCTRL_MH{head_index}_Settings"
            placements = sorted(
                (p for p in result[head_name] if "Shutter: On" in p.parameters[key]),
                key=lambda p: p.start_ms,
            )
            return [
                "full" if f"Dimmer: {_DIMMER_FULL_ON}" in p.parameters[key]
                else "off" if f"Dimmer: {_DIMMER_OFF}" in p.parameters[key]
                else "?"
                for p in placements
            ]

        assert dimmer_states("MH1", 1) == ["full", "full", "full", "full"]
        assert dimmer_states("MH4", 4) == ["full", "full", "full", "full"]
        assert dimmer_states("MH2", 2) == ["full", "off", "full", "off"]
        assert dimmer_states("MH3", 3) == ["full", "off", "full", "off"]

        # Position never changes across bars for the toggling heads --
        # only Dimmer varies.
        key2 = "E_TEXTCTRL_MH2_Settings"
        placements2 = sorted(
            (p for p in result["MH2"] if "Shutter: On" in p.parameters[key2]),
            key=lambda p: p.start_ms,
        )
        pan_tilt = {p.parameters[key2].split("Pan:")[1].split(";Tilt")[0] for p in placements2}
        assert len(pan_tilt) == 1  # identical Pan value on every bar

    def test_short_static_move_under_one_bar_is_unaffected(self):
        # A move too short to contain more than one bar shouldn't split at
        # all -- degrades to the original single-placement behavior.
        layout = parse_layout(FIXTURES / "moving_head_layout_4heads.xml")
        assignments = [_assignment("chorus", 0, 8_000, 40, variation_seed=1)]
        bars = _bars(20_000, 3)  # bar marks far apart -- none fall inside the move
        result = place_moving_head_moves(layout, assignments, bars=bars)
        for head_name, head_index in (("MH1", 1), ("MH2", 2)):
            key = f"E_TEXTCTRL_MH{head_index}_Settings"
            moves = [p for p in result[head_name] if "Shutter: On" in p.parameters[key]]
            assert len(moves) == 1

    def test_group_static_held_move_also_alternates_per_bar(self):
        # Same bar-level 4-heads/2-heads alternation as the per-head test
        # above, but for a group-targeted static move (fan_pan_static) --
        # user-reported 2026-07-22: a real generated .xsq showed this
        # specific move flat/unmodified even after the per-head fix, since
        # fan_pan_static is target="group", not "per_head". All 4 heads'
        # settings are combined into ONE "MH GRP" effect per bar, with
        # different Dimmer values per head slot (confirmed against two
        # real reference-sequence samples pasted directly by the user).
        # variation_seed=0, static_occurrence=0 -> static pool index 0
        # ("fan_pan_static", group). toggle_pair =
        # _choose_lit_pair(0, variation_seed+1=1) = (3, 4).
        layout = parse_layout(FIXTURES / "moving_head_layout_4heads.xml")
        assignments = [_assignment("chorus", 0, 8_000, 40, variation_seed=0)]
        bars = _bars(2_000, 5)  # bar marks at 0, 2000, 4000, 6000, 8000
        result = place_moving_head_moves(layout, assignments, bars=bars)
        assert set(result) == {"MH GRP"}

        def dimmer_states_by_head():
            placements = sorted(
                (p for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"]),
                key=lambda p: p.start_ms,
            )
            per_head = {i: [] for i in range(1, 5)}
            for p in placements:
                for i in range(1, 5):
                    text = p.parameters[f"E_TEXTCTRL_MH{i}_Settings"]
                    per_head[i].append(
                        "full" if f"Dimmer: {_DIMMER_FULL_ON}" in text
                        else "off" if f"Dimmer: {_DIMMER_OFF}" in text
                        else "?"
                    )
            return per_head

        states = dimmer_states_by_head()
        assert states[3] == ["full", "full", "full", "full"]
        assert states[4] == ["full", "full", "full", "full"]
        assert states[1] == ["full", "off", "full", "off"]
        assert states[2] == ["full", "off", "full", "off"]

    def test_consistently_intense_song_never_reduces_below_own_peak(self):
        # User concern (2026-07-18): a song that's intense throughout but
        # whose sections never numerically clear _FULL_HEADS_ENERGY_GATE
        # (e.g. normalized so everything scores in the low-to-mid 80s)
        # shouldn't get reduced moves almost everywhere just because of a
        # fixed absolute number -- every qualifying section here is within
        # _RELATIVE_PEAK_MARGIN of the song's own peak (84), so none of
        # them should reduce even though all are under the absolute 85 gate.
        layout = parse_layout(FIXTURES / "moving_head_layout_4heads.xml")
        assignments = [
            _assignment("verse", 0, 15_000, 80, variation_seed=1),
            _assignment("chorus", 20_000, 35_000, 84, variation_seed=1),
            _assignment("verse", 40_000, 55_000, 82, variation_seed=1),
        ]
        result = place_moving_head_moves(layout, assignments)
        for head_name in ("MH1", "MH2", "MH3", "MH4"):
            head_index = int(head_name[-1])
            key = f"E_TEXTCTRL_MH{head_index}_Settings"
            for placement in result[head_name]:
                if "Shutter: On" in placement.parameters[key]:
                    assert f"Dimmer: {_DIMMER_OFF}" not in placement.parameters[key]

    def test_peak_energy_lights_all_four_heads(self):
        # Comfortably clears _FULL_HEADS_ENERGY_GATE -- no head goes dark.
        layout = parse_layout(FIXTURES / "moving_head_layout_4heads.xml")
        assignments = [_assignment("verse", 0, 15_000, _FULL_HEADS_ENERGY_GATE + 5, variation_seed=1)]
        result = place_moving_head_moves(layout, assignments)
        for head_name in ("MH1", "MH2", "MH3", "MH4"):
            move_placement = result[head_name][-1]
            head_index = int(head_name[-1])
            settings = move_placement.parameters[f"E_TEXTCTRL_MH{head_index}_Settings"]
            assert f"Dimmer: {_DIMMER_OFF}" not in settings

    def test_two_head_group_never_gets_reduced(self):
        # _HEAD_PAIRS assumes the reference's 4-head arrangement -- a
        # smaller group (this fixture's MH1/MH2) has no well-defined
        # "half" to darken, so every head stays lit regardless of energy.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 15_000, 40, variation_seed=1)]
        result = place_moving_head_moves(layout, assignments)
        for head_name in ("MH1", "MH2"):
            move_placement = result[head_name][-1]
            head_index = int(head_name[-1])
            settings = move_placement.parameters[f"E_TEXTCTRL_MH{head_index}_Settings"]
            assert f"Dimmer: {_DIMMER_OFF}" not in settings

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

    def test_repeated_static_alternates_direction(self):
        # Same alternation rule extended (2026-07-18) to every genuine
        # directional pair in MOVE_LIBRARY, not just the sweeps.
        # section_index=2 and 10 both land on "r_static" via the natural
        # (variation_seed + section_index) % 8 rotation in the static pool.
        first = _choose_move(2, variation_seed=0, dynamic=False)
        assert first == "r_static"
        second = _choose_move(10, variation_seed=0, dynamic=False, previous_move=first)
        assert second == "l_static"

    def test_repeated_stagger_alternates_direction(self):
        # section_index=6 and 14 both land on "stagger_o_i".
        first = _choose_move(6, variation_seed=0, dynamic=False)
        assert first == "stagger_o_i"
        second = _choose_move(14, variation_seed=0, dynamic=False, previous_move=first)
        assert second == "stagger_i_o"

    def test_l_r_crisscross_repeat_is_left_alone(self):
        # l_r_crisscross has no direction-reversed partner in MOVE_LIBRARY
        # (ll_rr_crisscross is a different pattern, not its flip), so a
        # repeat isn't forced to change.
        first = _choose_move(4, variation_seed=0, dynamic=False)
        assert first == "l_r_crisscross"
        second = _choose_move(12, variation_seed=0, dynamic=False, previous_move=first)
        assert second == "l_r_crisscross"

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
            # variation_seed=1 (not 0): with the per-pool qualifying-occurrence
            # counter fix (2026-07-21), the FIRST static-qualifying section at
            # variation_seed=0 would land on _STATIC_MOVES[0] ("fan_pan_static",
            # also a group move) -- seed=1 shifts it to index 1 ("l_r_static",
            # per_head), matching what this test actually exercises.
            _assignment("chorus", 10_000, 25_000, 40, variation_seed=1),  # per_head l_r_static, natural start 10_000
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
            # variation_seed=1: see comment in
            # test_per_head_move_trims_prior_group_moves_tail_to_open_warmup_gap
            _assignment("chorus", 1_500, 25_000, 40, variation_seed=1),  # per_head l_r_static
        ]
        result = place_moving_head_moves(layout, assignments)
        group_move = result["MH GRP"][0]
        assert group_move.end_ms == 1_000  # trimmed all the way to its own floor
        warmup, move = result["MH1"]
        assert warmup.start_ms == 1_000 and warmup.end_ms == 1_750
        assert (warmup.end_ms - warmup.start_ms) == _MIN_WARMUP_DURATION_MS
        assert move.start_ms == 1_750  # pushed past its natural 1_500 to guarantee the minimum


class TestMoveBarCap:
    def test_bar_cap_shortens_move_when_room_permits(self):
        # variation_seed=2, section 0-30_000 -> per_head "r_static". Without
        # bars, natural_end_ms would be min(30_000, 0+20_000)=20_000. With
        # 1s bars, 4 bars after start(0) end at 4_000, and the section has
        # 26_000ms left after that -- comfortably clears the warmup floor,
        # so the cap applies.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments, bars=_bars(1_000, 31))
        move = result["MH1"][-1]
        assert move.end_ms == _MOVE_BAR_CAP * 1_000

    def test_bar_cap_lets_back_to_back_section_get_full_preferred_warmup(self):
        # Same two back-to-back sections as
        # test_warmup_still_fits_for_back_to_back_qualifying_sections, but
        # with bars supplied: section 0's move ends at bar 4 (4_000) instead
        # of filling the section to 15_000, leaving an 11_000ms natural gap
        # before section 1 starts -- comfortably over the 3s preferred
        # warmup, so no trim is needed at all (contrast with the no-bars
        # test, which trims section 0's tail down to the bare minimum).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 15_000, 40, variation_seed=2),
            _assignment("chorus", 15_000, 30_000, 40, variation_seed=2),
        ]
        result = place_moving_head_moves(layout, assignments, bars=_bars(1_000, 31))
        placements = result["MH1"]
        assert len(placements) == 3  # section0 move (bar-capped), section1 warmup, section1 move
        first_move, warmup, second_move = placements
        assert first_move.end_ms == 4_000
        assert warmup.start_ms == 15_000 - _PREFERRED_WARMUP_DURATION_MS
        assert warmup.end_ms == 15_000
        assert second_move.start_ms == 15_000

    def test_bar_cap_skipped_when_it_would_leave_no_warmup_room(self):
        # 4s bars -> 4 bars after start(0) end at 16_000. The section ends
        # at 16_500, only 500ms after that -- under the warmup floor, so the
        # cap is skipped and the move fills the section as it would without
        # bars.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 16_500, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments, bars=_bars(4_000, 5))
        move = result["MH1"][-1]
        assert move.end_ms == 16_500

    def test_no_bars_preserves_fill_the_section_behavior(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, 40, variation_seed=2)]
        result = place_moving_head_moves(layout, assignments, bars=None)
        move = result["MH1"][-1]
        assert move.end_ms == _MAX_MOVE_DURATION_MS


class TestQualifyingOccurrenceRotation:
    """_choose_move must be indexed by a per-pool qualifying-occurrence
    counter, not the absolute section index -- otherwise a regular stride
    between qualifying sections aliases onto a subset of pool slots for the
    whole song (same failure shape as bug-346/bug-182/bug-188), and since
    both pools put their "group" move at index 0, an aliased rotation can
    make the group move dominate almost the entire song instead of its
    intended 1-in-4/1-in-8 share (user-reported 2026-07-21)."""

    def test_every_dynamic_slot_reachable_across_consecutive_occurrences(self):
        from src.generator.moving_head import _DYNAMIC_MOVES
        seen = {
            _choose_move(i, variation_seed=0, dynamic=True)
            for i in range(len(_DYNAMIC_MOVES))
        }
        assert seen == set(_DYNAMIC_MOVES)

    def test_every_static_slot_reachable_across_consecutive_occurrences(self):
        from src.generator.moving_head import _STATIC_MOVES
        seen = {
            _choose_move(i, variation_seed=0, dynamic=False)
            for i in range(len(_STATIC_MOVES))
        }
        assert seen == set(_STATIC_MOVES)

    def test_group_move_does_not_dominate_regularly_spaced_qualifying_sections(self):
        # Reproduces the reported bug: qualifying "chorus" sections at a
        # fixed stride (chorus/verse/chorus/verse/...), all landing on the
        # same "dynamic" pool. Before the fix, aliasing on the absolute
        # section_index could make EVERY one of these pick the group move
        # (fan_pan_move, pool index 0); after the fix, the qualifying-
        # occurrence counter must cycle through the pool normally.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = []
        t = 0
        for i in range(8):
            if i % 2 == 0:
                assignments.append(_assignment("chorus", t, t + 20_000, _STRONG_ENERGY_GATE, variation_seed=0))
            else:
                assignments.append(_assignment("verse", t, t + 20_000, 10, variation_seed=0))
            t += 20_000
        result = place_moving_head_moves(layout, assignments)

        group_move_count = len(result.get("MH GRP", []))
        # 4 qualifying (chorus) sections in the dynamic pool of 4 moves,
        # only 1 of which ("fan_pan_move") targets the group -- must not
        # produce a group move for every single qualifying section.
        assert group_move_count < 4, (
            f"Expected group moves to rotate away from fan_pan_move sometimes, "
            f"got {group_move_count} group-move placements across 4 qualifying sections"
        )


def _obstacle(model: str, start_ms: int, end_ms: int) -> EffectPlacement:
    return EffectPlacement(
        effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
        model_or_group=model, start_ms=start_ms, end_ms=end_ms,
    )


class TestFreeWindows:
    """_free_windows splits a section's natural window around obstacles
    instead of an all-or-nothing overlap check (user-reported 2026-07-21:
    a song whose lyrics repeat "shake" throughout the chorus had every
    chorus/pre_chorus move dropped entirely, one scattered 250ms
    keyword-accent pulse at a time)."""

    def test_no_obstacles_returns_whole_window(self):
        assert _free_windows(0, 10_000, []) == [(0, 10_000)]

    def test_single_obstacle_in_middle_splits_into_two(self):
        blocking = [_obstacle("MH GRP", 4_000, 4_250)]
        assert _free_windows(0, 10_000, blocking) == [(0, 4_000), (4_250, 10_000)]

    def test_obstacle_covering_entire_window_yields_nothing(self):
        blocking = [_obstacle("MH GRP", 0, 10_000)]
        assert _free_windows(0, 10_000, blocking) == []

    def test_obstacle_at_the_very_start(self):
        blocking = [_obstacle("MH GRP", 0, 500)]
        assert _free_windows(0, 10_000, blocking) == [(500, 10_000)]

    def test_obstacle_at_the_very_end(self):
        blocking = [_obstacle("MH GRP", 9_500, 10_000)]
        assert _free_windows(0, 10_000, blocking) == [(0, 9_500)]

    def test_multiple_scattered_obstacles(self):
        # Mirrors the real scenario: several short "shake" pulses through
        # a single chorus section.
        blocking = [
            _obstacle("MH GRP", 2_000, 2_250),
            _obstacle("MH GRP", 5_000, 5_250),
            _obstacle("MH GRP", 8_000, 8_250),
        ]
        assert _free_windows(0, 10_000, blocking) == [
            (0, 2_000), (2_250, 5_000), (5_250, 8_000), (8_250, 10_000),
        ]

    def test_overlapping_obstacles_merge(self):
        blocking = [
            _obstacle("MH GRP", 2_000, 3_000),
            _obstacle("MH1", 2_500, 3_500),
        ]
        assert _free_windows(0, 10_000, blocking) == [(0, 2_000), (3_500, 10_000)]

    def test_obstacle_outside_window_ignored(self):
        blocking = [_obstacle("MH GRP", 20_000, 21_000)]
        assert _free_windows(0, 10_000, blocking) == [(0, 10_000)]


class TestSectionMoveSplitsAroundObstacle:
    def test_small_obstacle_in_middle_still_places_moves_before_and_after(self):
        # Before this fix: a single 250ms obstacle anywhere in the section
        # dropped the WHOLE section's move. Now it should still place
        # moves in the usable segments on either side.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 20_000, _STRONG_ENERGY_GATE, variation_seed=0),
        ]
        existing = {"MH GRP": [_obstacle("MH GRP", 10_000, 10_250)]}
        result = place_moving_head_moves(layout, assignments, existing_placements=existing)
        assert result, "Expected moves to survive around the small obstacle, got nothing"
        all_placements = [p for placements in result.values() for p in placements]
        # Nothing placed should overlap the obstacle itself.
        assert not any(p.start_ms < 10_250 and p.end_ms > 10_000 for p in all_placements)
        # Something should exist on both sides of the obstacle.
        assert any(p.end_ms <= 10_000 for p in all_placements)
        assert any(p.start_ms >= 10_250 for p in all_placements)

    def test_obstacle_covering_whole_section_still_skips_entirely(self):
        # A genuinely substantial obstacle (not a tiny pulse) should still
        # result in no moves for that section -- there's no usable segment.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 20_000, _STRONG_ENERGY_GATE, variation_seed=0),
        ]
        existing = {"MH GRP": [_obstacle("MH GRP", 0, 20_000)]}
        result = place_moving_head_moves(layout, assignments, existing_placements=existing)
        assert result == {}

    def test_tiny_leftover_segment_below_threshold_is_skipped(self):
        # An obstacle leaving only a sliver (<_MIN_SPLIT_SEGMENT_MS) on one
        # side must not produce a degenerate near-zero-duration move there.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", 0, 20_000, _STRONG_ENERGY_GATE, variation_seed=0),
        ]
        existing = {"MH GRP": [_obstacle("MH GRP", 500, 20_000)]}
        result = place_moving_head_moves(layout, assignments, existing_placements=existing)
        all_placements = [p for placements in result.values() for p in placements]
        # The only free window is (0, 500), well under _MIN_SPLIT_SEGMENT_MS.
        assert not any(p.end_ms <= 500 for p in all_placements)
