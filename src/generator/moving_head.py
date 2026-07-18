"""Song-scoped placement for DMX moving-head fixtures.

Moving-head models (xLights DisplayAs="DmxMovingHeadAdv") are not RGB pixel
props -- their "pixels" are placeholders for DMX channels (Pan, Tilt, Gobo,
Shutter, ...). The only effect that correctly drives them is xLights' own
"Moving Head" effect, which translates high-level Pan/Tilt/Color/Dimmer
commands into the right DMX channel values via the model's own channel
mapping. Any other effect (On, Color Wash, ...) would write raw per-node
values straight into those channels -- for Pan/Tilt that means snapping a
real physical fixture to garbage positions, which is why moving-head props
are excluded from every generic tier in grouper.generate_groups() and only
ever receive placements from this module.

v1 shipped a continuous static white wash placement per song section
(dimmer fully on, no movement). Removed 2026-07-16: with the wash always
on, the MH group was lit for the entire song regardless of energy/mood.

v2 (2026-07-17) replaces that with a library of 12 moves mined directly
from a user-provided vendor reference sequence (``MH Samples.xsq``, 4
heads, 12 timing-labeled moves). Per the user: static poses, sweeps,
tilt-oscillation and dimmer "stagger" chases are placed on the *individual*
head models (MH-1..MH-N), matching the reference -- only the two "Fan"
moves are placed on the whole group, since the reference does so too (a
uniform per-head pose that fans out identically via PanOffset needs no
per-head distinction). Moves are gated to sections that are genuinely
strong (top energy tier or chorus/drop role, user-confirmed 2026-07-17) so
most of the song stays dark, matching the same "rare, not continuous"
design constraint that killed the v1 wash. A small deterministic pan/tilt
jitter (keyed off variation_seed + section_index) keeps repeated strong
sections from looking identical. Every pose's Dimmer defaults to an
instant full-on (not the reference's soft fade-in) per user request
2026-07-17. Each move is preceded by a silent warmup lead-in
(``_add_with_warmup``) pre-positioned to the move's own starting Pan/Tilt
angle, so heads are already aimed correctly and dark before the move
itself opens the shutter -- the same mechanic the crash punch already
used, generalized to every move.

Always white, never a theme/section color, by design (user request,
2026-07-16) -- and not just for simplicity. Reading
DmxColorAbilityWheel::GetDMXWheelValue() in the real xLights source
(src-core/models/DMX/DmxColorAbilityWheel.cpp) showed a color-wheel
fixture only recognizes a commanded color if its hue
lands within ~0.01 (about 3.6 degrees) of one of the fixture's own
configured wheel-slot hues; anything else silently falls through to
whatever the wheel defaults to at DMX 0 (white, on the fixtures tested).
Confirmed against real hardware: a pure-red placement (hue 0.0) rendered
correctly, but a green placement (hue ~0.357) rendered as white because
it didn't land close enough to that fixture's configured green slot.
Arbitrary theme-derived hues are therefore fundamentally unreliable on a
wheel-type fixture -- white sidesteps the problem entirely. The reference
sequence is itself all-white, so this carries forward without conflict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

from src.analyzer.result import HierarchyResult
from src.generator.models import EffectPlacement, SectionAssignment, SectionEnergy, frame_align
from src.grouper.layout import Layout, find_moving_head_groups

# "Dimmer: x1,y1,x2,y2,..." is a value-curve point list, not an opaque bit
# pattern -- confirmed by reading MovingHeadEffect::CalculateDimmer() in the
# real xLights source (H:\XlightsSourceDir\xLights\src-core\effects\
# MovingHeadEffect.cpp): x is position (0-1) across the effect's duration,
# y is dimmer output (0-1, i.e. 0-255). Commas are pre-escaped (see
# _COMMA_ESCAPE below).
_DIMMER_FULL_ON = "0.000000&comma;1.000000&comma;1.000000&comma;1.000000"

# Flat zero the whole effect -- used to darken specific heads for a move
# without silencing them entirely the way the warmup mechanism does (the
# head still gets its Pan/Tilt/Wheel/Shutter commands and repositions,
# just stays invisible). See _reduce_to_lit_pair below.
_DIMMER_OFF = "0.000000&comma;0.000000&comma;1.000000&comma;0.000000"

# "Stagger" chase moves alternate which half of the effect a head is lit
# for. MID: on from ~13% to ~52% of the effect (an "early/middle" pulse).
_DIMMER_MID_PULSE = (
    "0.000000&comma;-0.017241&comma;0.000000&comma;0.000000&comma;"
    "0.131964&comma;0.000000&comma;0.132964&comma;1.000000&comma;"
    "0.521964&comma;1.000000&comma;0.522964&comma;0.000000&comma;"
    "1.000000&comma;0.000000"
)
# LATE: on from ~52% to 100% of the effect (the complementary half).
_DIMMER_LATE_PULSE = (
    "0.000000&comma;-0.017241&comma;0.000000&comma;0.000000&comma;"
    "0.519380&comma;0.005348&comma;0.521964&comma;1.000000&comma;"
    "1.000000&comma;1.000000"
)

# xLights always writes all 8 MH{n}_Settings slots regardless of how many
# heads are actually in the group (confirmed in a real working effect: a
# 4-head group still had MH5_Settings..MH8_Settings present, just empty)
# -- unused slots get an empty string.
_MAX_HEAD_SLOTS = 8

# The top-level effect settings string xLights writes is itself
# comma-delimited ("key1=val1,key2=val2,..."), so any literal comma inside
# an E_TEXTCTRL_* value must be escaped or xLights splits the value on it
# and misparses everything after. Confirmed against a real rendered
# Moving Head sequence, where every comma inside MH{n}_Settings text is
# written as "&comma;" rather than ",". Value-curve descriptors
# ("Key: Active=TRUE|...|") use "|" instead, so they need no escaping.
_COMMA_ESCAPE = "&comma;"

# Hue 0.0, saturation 0.0, value 1.0 -- pure white. See the module
# docstring for why this is a fixed constant rather than a derived color.
_COLOR_WHITE = _COMMA_ESCAPE.join(("0.000000", "0.000000", "1.000000"))


def _deg_to_slider(deg: float) -> str:
    """xLights' shared MH Pan/Tilt/PanOffset sliders store degrees*10 as a
    plain integer -- NOT the same plain-decimal-degrees format as the
    ``Pan: X``/``Tilt: X`` per-head text (confirmed against the vendor
    reference sequence, ``MH Samples.xsq``, 2026-07-18: e.g. text ``Pan:
    -45.0`` pairs with ``E_SLIDER_MHPan=-450``, ``PanOffset: 10.5`` pairs
    with ``E_SLIDER_MHPanOffset=105``). This matches the value-curve
    encoding's own ``Min=-1800.00|Max=1800.00`` scale. A prior fix
    (2026-07-17) wrote these sliders as plain decimal-degree strings
    (e.g. ``"-55.0"``) assuming the same scale as the text -- wrong scale
    *and* wrong format, which is why xLights silently discarded them on
    save regardless of the value supplied.
    """
    return str(round(deg * 10))


def _build_parameters(
    per_head_settings: dict[int, str],
    *,
    slider_pan: Optional[str] = None,
    slider_tilt: Optional[str] = None,
    slider_pan_offset: str = "0",
    slider_cycles: str = "10",
) -> dict[str, str]:
    """``per_head_settings`` maps 1-indexed head slot -> settings text for
    that slot; slots not present get an empty string (see _MAX_HEAD_SLOTS).

    ``slider_pan``/``slider_tilt`` are the shared ``E_SLIDER_MHPan``/
    ``E_SLIDER_MHTilt`` values xLights treats as authoritative for whichever
    axis isn't value-curve-driven -- confirmed by a real before/after diff
    (2026-07-17): opening a generated effect whose per-head text said
    ``Tilt: 65.0`` but whose ``E_SLIDER_MHTilt`` didn't match made xLights
    silently rewrite the per-head text to ``Tilt: 0.0`` on save, discarding
    the intended angle. Pass ``None`` (the default) for whichever axis is
    value-curve-driven -- the reference sequence OMITS that key entirely
    rather than setting it to any value, confirmed across every VC-driven
    entry in ``MH Samples.xsq``. Values must already be in the ``_deg_to_slider``
    scale (degrees*10), not plain degrees.
    """
    params: dict[str, str] = {
        "B_CHOICE_BufferStyle": "Per Model Default",
        "E_NOTEBOOK1": "Position",
        "E_NOTEBOOK2": "ColorWheel",
        "E_SLIDER_MHPanOffset": slider_pan_offset,
        "E_SLIDER_MHTiltOffset": "0",
        "E_SLIDER_MHGroupings": "1",
        "E_SLIDER_MHCycles": slider_cycles,
        "E_SLIDER_MHPathScale": "0",
        "E_SLIDER_MHTimeOffset": "0",
        "E_CHECKBOX_MHIgnorePan": "0",
        "E_CHECKBOX_MHIgnoreTilt": "0",
        "E_CHECKBOX_AUTO_SHUTTER": "1",
        # Newer xLights builds gate the shutter DMX channel behind this
        # checkbox; without it the shutter never opens regardless of
        # Dimmer/Auto Shutter, so real hardware stays dark. Confirmed
        # against real xLights (user, 2026-07-16).
        "E_CHECKBOX_MHShutterEnable": "1",
        # Motion-pattern preset (Circle/Figure8/...) -- unused by any move
        # in this module (all motion comes from Pan/Tilt value curves
        # instead), but xLights always writes these keys with defaults.
        "E_CHECKBOX_MHPatternEnable": "0",
        "E_CHOICE_MHPattern": "Circle",
        "E_SLIDER_MHPatternHeight": "45",
        "E_SLIDER_MHPatternPhaseOffset": "0",
        "E_SLIDER_MHPatternRotation": "0",
        "E_SLIDER_MHPatternStartOffset": "0",
        "E_SLIDER_MHPatternWidth": "90",
        "E_SLIDER_MHPatternXOffset": "0",
        "E_SLIDER_MHPatternYOffset": "0",
        "E_TEXTCTRL_MHPathDef": "",
        "T_CHECKBOX_LayerMorph": "0",
        "T_CHOICE_LayerMethod": "Normal",
        "T_SLIDER_EffectLayerMix": "0",
    }
    if slider_pan is not None:
        params["E_SLIDER_MHPan"] = slider_pan
    if slider_tilt is not None:
        params["E_SLIDER_MHTilt"] = slider_tilt
    for i in range(1, _MAX_HEAD_SLOTS + 1):
        params[f"E_TEXTCTRL_MH{i}_Settings"] = per_head_settings.get(i, "")
    return params


# ---------------------------------------------------------------------------
# Move library -- mined verbatim from MH Samples.xsq (4 heads, 12 timing-
# labeled moves, 2026-07-17). Pan/Tilt/PanOffset values are in degrees;
# xLights' own value-curve encoding stores degrees*10 (Min/Max=-1800/1800),
# which _format_pan/_format_tilt below convert to.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _HeadPose:
    """One head's Pan/Tilt/Dimmer recipe for a single move.

    Exactly one of (pan, pan_vc) and one of (tilt, tilt_vc) is set --
    static angle vs. a value-curve sweep. ``pan_offset`` is only ever
    non-zero for the two whole-group "Fan" moves.
    """
    pan: Optional[float] = None
    pan_vc: Optional[tuple[float, float]] = None  # (start_deg, end_deg), Ramp
    tilt: Optional[float] = None
    tilt_vc: Optional[tuple[float, float, float]] = None  # (lo, hi, lo), Ramp Up/Down
    pan_offset: float = 0.0
    dimmer: str = _DIMMER_FULL_ON


@dataclass(frozen=True)
class _Move:
    name: str
    target: str  # "group" | "per_head"
    # target="per_head": one pose per physical head role (cycled if the
    # real group has more/fewer heads than the reference's 4).
    # target="group": a single pose applied identically to every head.
    poses: tuple[_HeadPose, ...]


# The reference's 4 head roles, in the same "L pair / R pair" arrangement
# observed in every static/crisscross move (mined, not derived): heads 1-2
# fan left by default, heads 3-4 fan right.
MOVE_LIBRARY: dict[str, _Move] = {
    "l_r_static": _Move("l_r_static", "per_head", (
        _HeadPose(pan=-45.0, tilt=60.0), _HeadPose(pan=-45.0, tilt=60.0),
        _HeadPose(pan=45.0, tilt=60.0), _HeadPose(pan=45.0, tilt=60.0),
    )),
    "l_static": _Move("l_static", "per_head", (
        _HeadPose(pan=-45.0, tilt=60.0), _HeadPose(pan=-45.0, tilt=60.0),
        _HeadPose(pan=-45.0, tilt=60.0), _HeadPose(pan=-45.0, tilt=60.0),
    )),
    "r_static": _Move("r_static", "per_head", (
        _HeadPose(pan=45.0, tilt=60.0), _HeadPose(pan=45.0, tilt=60.0),
        _HeadPose(pan=45.0, tilt=60.0), _HeadPose(pan=45.0, tilt=60.0),
    )),
    "l_r_crisscross": _Move("l_r_crisscross", "per_head", (
        _HeadPose(pan=45.0, tilt=60.0), _HeadPose(pan=-45.0, tilt=60.0),
        _HeadPose(pan=45.0, tilt=60.0), _HeadPose(pan=-45.0, tilt=60.0),
    )),
    "ll_rr_crisscross": _Move("ll_rr_crisscross", "per_head", (
        _HeadPose(pan=45.0, tilt=60.0), _HeadPose(pan=45.0, tilt=60.0),
        _HeadPose(pan=-45.0, tilt=60.0), _HeadPose(pan=-45.0, tilt=60.0),
    )),
    "l_r_sweep": _Move("l_r_sweep", "per_head", (
        # All 4 heads sweep the same direction together -- confirmed
        # against the reference sequence (MH Samples.xsq, 2026-07-18): its
        # equivalent sweep segments have every head's Pan VC pointing the
        # same way, never alternating/crisscrossing. Head 2 previously had
        # a reversed tuple here (copy-paste from r_l_sweep) that fought
        # the other three (user-reported, 2026-07-18).
        _HeadPose(pan_vc=(-45.0, 45.0), tilt=60.0),
        _HeadPose(pan_vc=(-45.0, 45.0), tilt=60.0),
        _HeadPose(pan_vc=(-45.0, 45.0), tilt=60.0),
        _HeadPose(pan_vc=(-45.0, 45.0), tilt=60.0),
    )),
    "r_l_sweep": _Move("r_l_sweep", "per_head", (
        _HeadPose(pan_vc=(45.0, -45.0), tilt=60.0),
        _HeadPose(pan_vc=(45.0, -45.0), tilt=60.0),
        _HeadPose(pan_vc=(45.0, -45.0), tilt=60.0),
        _HeadPose(pan_vc=(45.0, -45.0), tilt=60.0),
    )),
    "u_d_tilt": _Move("u_d_tilt", "per_head", tuple(
        _HeadPose(pan=-45.0, tilt_vc=(25.0, 80.0, 25.0)) for _ in range(4)
    )),
    "stagger_o_i": _Move("stagger_o_i", "per_head", (
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_MID_PULSE),
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_LATE_PULSE),
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_MID_PULSE),
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_MID_PULSE),
    )),
    "stagger_i_o": _Move("stagger_i_o", "per_head", (
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_LATE_PULSE),
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_MID_PULSE),
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_LATE_PULSE),
        _HeadPose(pan=0.0, tilt=45.0, dimmer=_DIMMER_LATE_PULSE),
    )),
    "fan_pan_static": _Move("fan_pan_static", "group", (
        _HeadPose(pan=0.0, tilt=78.5, pan_offset=10.5),
    )),
    "fan_pan_move": _Move("fan_pan_move", "group", (
        _HeadPose(pan=0.0, tilt_vc=(25.0, 80.0, 25.0), pan_offset=10.5),
    )),
}

# Rotation pools for the two gate tiers (see place_moving_head_moves).
# Top-energy sections get the more dynamic motion moves; chorus/drop
# sections that don't clear the energy gate get static/stagger variety.
_DYNAMIC_MOVES = ("fan_pan_move", "l_r_sweep", "r_l_sweep", "u_d_tilt")
_STATIC_MOVES = (
    "fan_pan_static", "l_r_static", "r_static", "l_static",
    "l_r_crisscross", "ll_rr_crisscross", "stagger_o_i", "stagger_i_o",
)


def _format_pan(deg: float) -> str:
    return f"Pan: {deg:.1f}"


def _pan_vc_descriptor(start_deg: float, end_deg: float) -> str:
    return (
        "Active=TRUE|Id=ID_VALUECURVE_MHPan|Type=Ramp|"
        f"Min=-1800.00|Max=1800.00|P1={start_deg * 10:.2f}|"
        f"P2={end_deg * 10:.2f}|RV=TRUE|"
    )


def _format_pan_vc(start_deg: float, end_deg: float) -> str:
    return f"Pan VC: {_pan_vc_descriptor(start_deg, end_deg)}"


def _format_tilt(deg: float) -> str:
    return f"Tilt: {deg:.1f}"


def _tilt_vc_descriptor(lo_deg: float, hi_deg: float, lo2_deg: float) -> str:
    return (
        "Active=TRUE|Id=ID_VALUECURVE_MHTilt|Type=Ramp Up/Down|"
        f"Min=-1800.00|Max=1800.00|P1={lo_deg * 10:.2f}|"
        f"P2={hi_deg * 10:.2f}|P3={lo2_deg * 10:.2f}|RV=TRUE|"
    )


def _format_tilt_vc(lo_deg: float, hi_deg: float, lo2_deg: float) -> str:
    return f"Tilt VC: {_tilt_vc_descriptor(lo_deg, hi_deg, lo2_deg)}"


def _vc_top_level_params(pose: "_HeadPose", jitter_pan: float, jitter_tilt: float) -> dict[str, str]:
    """Whenever a pose's Pan or Tilt comes from a value curve, xLights
    also expects a top-level ``E_VALUECURVE_MHPan``/``E_VALUECURVE_MHTilt``
    key on the effect itself, mirroring the same curve descriptor written
    into the per-head text -- confirmed present on every VC-driven effect
    in the reference sequence (MH Samples.xsq) and absent on every
    static-pose effect. This module never wrote it; real-world testing
    (2026-07-17) found a generated Pan-VC effect didn't show its curve in
    the xLights UI at all -- clicking the effect only dropped an unrelated
    cosmetic key (B_CHOICE_BufferStyle), never adding this one, confirming
    it's the actual missing piece rather than something xLights
    self-repairs on selection."""
    extra: dict[str, str] = {}
    if pose.pan_vc is not None:
        start_deg, end_deg = pose.pan_vc
        extra["E_VALUECURVE_MHPan"] = _pan_vc_descriptor(start_deg + jitter_pan, end_deg + jitter_pan)
    if pose.tilt_vc is not None:
        lo_deg, hi_deg, lo2_deg = pose.tilt_vc
        extra["E_VALUECURVE_MHTilt"] = _tilt_vc_descriptor(
            lo_deg + jitter_tilt, hi_deg + jitter_tilt, lo2_deg + jitter_tilt,
        )
    return extra


def _build_pose_settings(pose: _HeadPose, jitter_pan: float, jitter_tilt: float, heads_field: str) -> str:
    """One MH{n}_Settings text-DSL value, jittered.

    ``heads_field`` is the comma-joined list of head indices this text
    applies to -- "1" for an individual head model's own placement
    (always just itself), or every index in the group ("1,2,3,4") for a
    group-targeted move, matching the reference sequence's group effects
    (Fan Pan-Static/-Move), where every slot's text lists all heads
    redundantly rather than just its own slot number.

    Key order matches the reference sequence's Position-tab effects
    (Wheel;Shutter;Dimmer;Pan;Tilt;PanOffset;TiltOffset;Groupings;Cycles;
    Heads) -- MovingHeadEffect parses this as a semicolon-delimited
    ``Key: value`` DSL, not positionally, so order has no render effect;
    kept consistent here purely for readability/diffing against the
    reference.
    """
    if pose.pan_vc is not None:
        start_deg, end_deg = pose.pan_vc
        pan_part = _format_pan_vc(start_deg + jitter_pan, end_deg + jitter_pan)
    else:
        pan_part = _format_pan((pose.pan or 0.0) + jitter_pan)

    if pose.tilt_vc is not None:
        lo_deg, hi_deg, lo2_deg = pose.tilt_vc
        tilt_part = _format_tilt_vc(lo_deg + jitter_tilt, hi_deg + jitter_tilt, lo2_deg + jitter_tilt)
    else:
        tilt_part = _format_tilt((pose.tilt or 0.0) + jitter_tilt)

    return (
        f"Wheel: {_COLOR_WHITE};"
        "Shutter: On;"
        f"Dimmer: {pose.dimmer};"
        f"{pan_part};"
        f"{tilt_part};"
        f"PanOffset: {pose.pan_offset:.1f};TiltOffset: 0.0;"
        "Groupings: 1;Cycles: 1.0;"
        f"Heads: {heads_field}"
    )


# Deterministic pan/tilt variety so repeated strong sections don't look
# identical (user request, 2026-07-17) -- small enough to stay within the
# reference's own observed safe ranges (pan +-45 base, tilt 25-80 base).
_PAN_JITTER_DEG = (-10.0, -5.0, 0.0, 5.0, 10.0)
_TILT_JITTER_DEG = (-5.0, -2.0, 0.0, 2.0, 5.0)


def _jitter(variation_seed: int, section_index: int) -> tuple[float, float]:
    pan = _PAN_JITTER_DEG[(variation_seed + section_index) % len(_PAN_JITTER_DEG)]
    tilt = _TILT_JITTER_DEG[(variation_seed + section_index * 2) % len(_TILT_JITTER_DEG)]
    return pan, tilt


# A repeated directional move back-to-back reads as the same move twice
# rather than variety (user request, 2026-07-18, extended same day to
# cover every genuine directional pair in MOVE_LIBRARY, not just sweeps);
# when the rotation would pick the same move as the immediately preceding
# qualifying section, swap to its direction-reversed partner instead.
# l_r_crisscross has no such partner (ll_rr_crisscross is a different
# pattern, not its direction-flip) so it isn't listed here on purpose.
_DIRECTIONAL_PARTNER = {
    "l_r_sweep": "r_l_sweep", "r_l_sweep": "l_r_sweep",
    "l_static": "r_static", "r_static": "l_static",
    "stagger_o_i": "stagger_i_o", "stagger_i_o": "stagger_o_i",
}


def _choose_move(
    section_index: int, variation_seed: int, *, dynamic: bool,
    previous_move: Optional[str] = None,
) -> str:
    pool = _DYNAMIC_MOVES if dynamic else _STATIC_MOVES
    choice = pool[(variation_seed + section_index) % len(pool)]
    if choice == previous_move and choice in _DIRECTIONAL_PARTNER:
        choice = _DIRECTIONAL_PARTNER[choice]
    return choice


# A qualifying section that clears _STRONG_ENERGY_GATE (or a chorus/drop
# role) still gets a move, but not every qualifying moment needs the same
# amount of moving-head presence -- user request (2026-07-18): scale it
# down by lighting only half the fixtures once a section is over the
# gate but short of genuinely peak energy, rather than always running
# all 4 heads. 1-based head-slot pairs (matching the mined arrangement:
# heads 1-2 are the "L pair", 3-4 the "R pair") -- left, right, outer,
# inner, so which two heads go dark rotates through every natural
# grouping, not just the L/R split.
_FULL_HEADS_ENERGY_GATE = 85  # matches effect_placer._WHOLE_HOUSE_HIGH_ENERGY_GATE
_HEAD_PAIRS = ((1, 2), (3, 4), (1, 4), (2, 3))
_MIN_HEADS_FOR_LIT_PAIR = 4

# A fixed absolute gate alone doesn't account for a song that's intense
# throughout but whose energy-scoring never quite reaches the absolute
# gate (e.g. a consistently loud song normalized so its sections all land
# at, say, 78-82) -- user concern (2026-07-18): such a song would get
# reduced moves almost everywhere despite having no genuinely "calm"
# contrast to justify it. A section within _RELATIVE_PEAK_MARGIN points of
# THIS song's own loudest qualifying section counts as full-intensity too,
# regardless of the absolute gate -- reduction is then reserved for
# sections that are meaningfully quieter than the song's own peak, not
# just quieter than a fixed number.
_RELATIVE_PEAK_MARGIN = 10


def _is_strong_section(section: SectionEnergy) -> bool:
    role = (section.label or "").lower()
    return section.energy_score >= _STRONG_ENERGY_GATE or role in _STRONG_ROLES


def _song_peak_qualifying_energy(assignments: list[SectionAssignment]) -> float:
    qualifying = [a.section.energy_score for a in assignments if _is_strong_section(a.section)]
    return max(qualifying) if qualifying else _FULL_HEADS_ENERGY_GATE


def _choose_lit_pair(section_index: int, variation_seed: int) -> tuple[int, int]:
    return _HEAD_PAIRS[(variation_seed + section_index) % len(_HEAD_PAIRS)]


def _reduce_to_lit_pair(pose: _HeadPose, head_index: int, lit_pair: tuple[int, int]) -> _HeadPose:
    """Darken ``pose`` (Dimmer only -- Pan/Tilt/PanOffset untouched, so a
    darkened head still repositions correctly in case a later move needs
    its current angle) when ``head_index`` isn't one of the two heads lit
    this move."""
    if head_index in lit_pair:
        return pose
    return replace(pose, dimmer=_DIMMER_OFF)


def _build_group_move_parameters(
    head_count: int, pose: "_HeadPose", jitter_pan: float, jitter_tilt: float,
) -> dict[str, str]:
    """A "Fan" move's single pose, written identically into every head's
    slot on the group effect itself (matches the reference sequence,
    where all 4 heads carry the exact same Fan Pan-Static/-Move text,
    each listing every head index)."""
    heads_field = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    settings = _build_pose_settings(pose, jitter_pan, jitter_tilt, heads_field)
    per_head = {i: settings for i in range(1, head_count + 1)}
    params = _build_parameters(
        per_head,
        slider_pan=None if pose.pan_vc is not None else _deg_to_slider((pose.pan or 0.0) + jitter_pan),
        slider_tilt=None if pose.tilt_vc is not None else _deg_to_slider((pose.tilt or 0.0) + jitter_tilt),
        slider_pan_offset=_deg_to_slider(pose.pan_offset),
    )
    params.update(_vc_top_level_params(pose, jitter_pan, jitter_tilt))
    return params


def _build_per_head_move_parameters(
    pose: "_HeadPose", jitter_pan: float, jitter_tilt: float, head_index: int,
) -> dict[str, str]:
    """A single head's own placement: the settings go into the
    ``E_TEXTCTRL_MH{head_index}_Settings`` slot matching that model's own
    position within the group, with ``Heads: {head_index}`` -- NOT always
    slot 1 / "Heads: 1". Reversed 2026-07-17 after real-hardware testing:
    a prior instruction here called the group-index number "a copy-paste
    artifact" and said to always use slot 1/"Heads: 1", but a real
    generated .xsq showed MH-2/MH-3 placements written that way silently
    failed to render until manually clicked in xLights -- diffing the
    file before/after clicking showed the fix was moving the settings
    into slot N with "Heads: N" (matching the model's group position, and
    matching the original MH Samples.xsq reference this module was mined
    from in the first place)."""
    settings = _build_pose_settings(pose, jitter_pan, jitter_tilt, heads_field=str(head_index))
    params = _build_parameters(
        {head_index: settings},
        slider_pan=None if pose.pan_vc is not None else _deg_to_slider((pose.pan or 0.0) + jitter_pan),
        slider_tilt=None if pose.tilt_vc is not None else _deg_to_slider((pose.tilt or 0.0) + jitter_tilt),
    )
    params.update(_vc_top_level_params(pose, jitter_pan, jitter_tilt))
    return params


def _pose_start_pan(pose: _HeadPose) -> float:
    """The pan angle a pose is AT when its effect begins -- the ramp's
    start point for a sweep, or the static angle otherwise."""
    return pose.pan_vc[0] if pose.pan_vc is not None else (pose.pan or 0.0)


def _pose_start_tilt(pose: _HeadPose) -> float:
    """Same as _pose_start_pan, for tilt (Ramp Up/Down's first point)."""
    return pose.tilt_vc[0] if pose.tilt_vc is not None else (pose.tilt or 0.0)


def _build_move_warmup_settings(
    pose: _HeadPose, jitter_pan: float, jitter_tilt: float, heads_field: str,
) -> str:
    """A silent lead-in pose matching the move's own starting Pan/Tilt, with
    no Dimmer/Wheel/Shutter commands (user request, 2026-07-17: "the pan and
    tilt need to match the starting position of the subsequent effect").
    Omitting Dimmer/Wheel/Shutter leaves the render's has_dimmers/shutter_open
    false (see _build_warmup_head_settings), so the head silently pre-positions
    in the dark instead of visibly snapping into place once the real move
    opens the shutter.
    """
    pan_deg = _pose_start_pan(pose) + jitter_pan
    tilt_deg = _pose_start_tilt(pose) + jitter_tilt
    return (
        f"{_format_pan(pan_deg)};{_format_tilt(tilt_deg)};"
        f"PanOffset: {pose.pan_offset:.1f};TiltOffset: 0.0;"
        "Groupings: 1;Cycles: 1.0;"
        f"Heads: {heads_field}"
    )


def _build_group_warmup_parameters(
    head_count: int, pose: _HeadPose, jitter_pan: float, jitter_tilt: float,
) -> dict[str, str]:
    heads_field = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    settings = _build_move_warmup_settings(pose, jitter_pan, jitter_tilt, heads_field)
    per_head = {i: settings for i in range(1, head_count + 1)}
    return _build_parameters(
        per_head,
        slider_pan=_deg_to_slider(_pose_start_pan(pose) + jitter_pan),
        slider_tilt=_deg_to_slider(_pose_start_tilt(pose) + jitter_tilt),
        slider_pan_offset=_deg_to_slider(pose.pan_offset),
    )


def _build_per_head_warmup_parameters(
    pose: _HeadPose, jitter_pan: float, jitter_tilt: float, head_index: int,
) -> dict[str, str]:
    settings = _build_move_warmup_settings(pose, jitter_pan, jitter_tilt, heads_field=str(head_index))
    return _build_parameters(
        {head_index: settings},
        slider_pan=_deg_to_slider(_pose_start_pan(pose) + jitter_pan),
        slider_tilt=_deg_to_slider(_pose_start_tilt(pose) + jitter_tilt),
    )


# "Strong and powerful" gate (user-confirmed 2026-07-17): the song's own
# top energy tier, or an explicit chorus/drop role, whichever fires first.
# Mirrors the precedent set by effect_placer._IMPACT_ENERGY_GATE (80) /
# _WHOLE_HOUSE_HIGH_ENERGY_GATE (85) for "this section is a standout".
_STRONG_ENERGY_GATE = 80
_STRONG_ROLES = frozenset({"chorus", "drop"})
# A move needs room to read -- shorter sections get skipped rather than
# truncated (a 10s reference move compressed into 3s reads as a glitch,
# not a wash).
_MIN_SECTION_DURATION_MS = 8000
# Cap so one continuous sweep/fan doesn't drag through a very long section.
_MAX_MOVE_DURATION_MS = 20000
# A moving head can't snap Pan/Tilt instantly -- each move gets a silent
# lead-in placement (Pan/Tilt/PanOffset only, no Dimmer/Wheel/Shutter)
# immediately before it, pre-positioned to the move's own starting angle
# (user request, 2026-07-17), so the head is already aimed correctly and
# dark by the time the real move opens the shutter, instead of visibly
# snapping into position while lit. Same "silent pre-position" mechanic
# the crash punch uses further down, just with its own adaptive-length
# rules (_resolve_warmup, below) instead of the crash punch's simpler
# natural-gap-only sizing.


def _add_with_warmup(
    by_target: dict[str, list[EffectPlacement]],
    target: str,
    warmup_params: dict[str, str],
    move_params: dict[str, str],
    start_ms: int,
    end_ms: int,
    warmup_duration_ms: int,
) -> EffectPlacement:
    """Append ``target``'s move placement, preceded by a silent warmup.
    Callers are expected to have already made room for the full warmup
    window via ``_resolve_warmup`` before calling this -- it does not
    re-check for conflicts itself. Returns the move placement (not the
    warmup) so the caller can track it as this head's new channel owner.
    """
    existing = by_target.setdefault(target, [])
    warmup_start_ms = max(0, start_ms - warmup_duration_ms)
    if warmup_start_ms < start_ms:
        existing.append(EffectPlacement(
            effect_name="Moving Head",
            xlights_id="eff_MOVINGHEAD",
            model_or_group=target,
            start_ms=warmup_start_ms,
            end_ms=start_ms,
            parameters=warmup_params,
        ))
    move_placement = EffectPlacement(
        effect_name="Moving Head",
        xlights_id="eff_MOVINGHEAD",
        model_or_group=target,
        start_ms=start_ms,
        end_ms=end_ms,
        parameters=move_params,
    )
    existing.append(move_placement)
    return move_placement


# The previous move keeps at least this much of its own duration when its
# tail is trimmed back to make room for the next move's warmup -- a
# sanity floor, not expected to bite in practice (sections are gated to
# >= _MIN_SECTION_DURATION_MS, far longer than one warmup).
_MIN_TRIMMED_MOVE_DURATION_MS = 1000


# Preferred warmup length when there's room for it -- gives the fixture a
# more comfortable, less rushed slew into position (user request,
# 2026-07-17). ``_MIN_WARMUP_DURATION_MS`` is the floor: used as-is when
# there's at least that much room, and guaranteed via a partial delay
# when even a maximal trim can't reach it.
_PREFERRED_WARMUP_DURATION_MS = 3000
_MIN_WARMUP_DURATION_MS = 750


def _best_trimmable_end_ms(owner: EffectPlacement) -> int:
    """The smallest ``owner.end_ms`` could ever be trimmed to while
    keeping at least ``_MIN_TRIMMED_MOVE_DURATION_MS`` of its own
    duration -- never proposes trimming a placement to a size larger
    than it already is."""
    floor_ms = owner.start_ms + _MIN_TRIMMED_MOVE_DURATION_MS
    return min(floor_ms, owner.end_ms)


def _resolve_warmup(
    owners: list[Optional[EffectPlacement]], desired_start_ms: int,
) -> tuple[int, int]:
    """Decide the upcoming move's actual start time and warmup duration,
    given every distinct placement currently occupying the channel(s) it
    needs (``owners`` may contain ``None`` entries for untouched heads).

    The full ``_PREFERRED_WARMUP_DURATION_MS`` (3s) is used ONLY when
    nothing needs to be shortened to get it -- no owner at all, or the
    natural gap before ``desired_start_ms`` already covers it. The moment
    an existing Moving Head placement is actually in the way (the natural
    gap is under the defined minimum), it is trimmed (mutated in place)
    down to open ONLY the defined ``_MIN_WARMUP_DURATION_MS`` -- never up
    to 3s -- reserving the longer warmup for genuinely idle stretches
    (user correction, 2026-07-17: a prior version of this trimmed existing
    effects by up to 3s to chase the preferred length, which visibly
    shortened them far more than necessary). Falls back to (partly)
    delaying the move to still guarantee ``_MIN_WARMUP_DURATION_MS`` only
    if even a maximal trim (down to an owner's own floor) can't reach it.

    Returns (start_ms, warmup_duration_ms).
    """
    real_owners = [o for o in owners if o is not None]
    if not real_owners:
        return desired_start_ms, max(0, min(_PREFERRED_WARMUP_DURATION_MS, desired_start_ms))

    latest_end_ms = max(o.end_ms for o in real_owners)
    natural_gap_ms = desired_start_ms - latest_end_ms
    if natural_gap_ms >= _PREFERRED_WARMUP_DURATION_MS:
        return desired_start_ms, _PREFERRED_WARMUP_DURATION_MS  # nothing in the way for the full 3s
    if natural_gap_ms >= _MIN_WARMUP_DURATION_MS:
        return desired_start_ms, natural_gap_ms  # no trim needed, use the natural gap as-is

    # An effect is genuinely in the way -- only ever trim it down to open
    # the defined minimum, not the full 3s.
    achievable_ms = min(
        _MIN_WARMUP_DURATION_MS,
        min(desired_start_ms - _best_trimmable_end_ms(o) for o in real_owners),
    )
    if achievable_ms >= _MIN_WARMUP_DURATION_MS:
        new_end_ms = desired_start_ms - achievable_ms
        for o in real_owners:
            if new_end_ms < o.end_ms:
                o.end_ms = frame_align(new_end_ms)
        return desired_start_ms, achievable_ms

    # Even a maximal trim can't open the defined minimum -- trim every
    # owner as far as safely possible and push the move's start out to
    # guarantee it.
    start_ms = desired_start_ms
    for o in real_owners:
        best_end_ms = _best_trimmable_end_ms(o)
        if best_end_ms < o.end_ms:
            o.end_ms = frame_align(best_end_ms)
        start_ms = max(start_ms, o.end_ms + _MIN_WARMUP_DURATION_MS)
    return start_ms, _MIN_WARMUP_DURATION_MS


def place_moving_head_moves(
    layout: Layout,
    assignments: list[SectionAssignment],
) -> dict[str, list[EffectPlacement]]:
    """Place one gated move per qualifying section on each moving-head
    group's fixtures, each preceded by a silent warmup pre-positioning
    lead-in.

    Only sections that are "strong and powerful" -- top energy tier
    (``_STRONG_ENERGY_GATE``) or an explicit chorus/drop role -- get a
    move; everything else stays dark, matching the same rarity design
    that removed the v1 continuous wash (see module docstring). Static
    poses, sweeps, tilt-oscillation, and dimmer "stagger" chases are
    placed per individual head model (mirroring the reference sequence);
    the two "Fan" moves are placed on the group itself. Returns {} when
    the layout has no moving-head group or no section qualifies.

    A group-targeted move (e.g. "Fan Pan-Static") and a per-head move on
    one of that group's members ultimately drive the exact same DMX
    channels, so the two must never touch in time, even at an exact
    boundary -- confirmed by the user finding an overlap warning in real
    xLights between "Moving Heads Group" and MH-1..MH-4 placements
    abutting with no gap (2026-07-17). ``channel_owner`` tracks, per
    physical head, the most recent placement occupying its channels so
    far (a group move becomes every head's owner; a per-head move
    becomes just its own).

    Every move also needs a full, uninterrupted warmup window right
    before it -- without one, a move immediately following another (any
    combination of group/per-head, or even the same target back-to-back)
    would start exactly where the prior one ends, leaving no silent
    lead-in at all: the head then visibly slews to its new pose instead
    of pre-positioning in the dark (user-observed in real xLights,
    2026-07-17: "the light will travel as it reaches the starting
    point"). ``_resolve_warmup`` opens that room (up to 3s when
    available, see its own docstring) by trimming the prior occupant's
    own tail (mutated in place) -- the user's stated preference over
    delaying the upcoming move, since shrinking a move that's already
    playing reads better than visibly pushing the next one off its
    section boundary -- falling back to a partial delay only if the
    prior occupant is too short to safely trim. A move is dropped
    entirely if there's no room for it at all after this.
    """
    mh_groups = find_moving_head_groups(layout)
    if not mh_groups:
        return {}

    song_peak_energy = _song_peak_qualifying_energy(assignments)

    result: dict[str, list[EffectPlacement]] = {}
    for mh_group in mh_groups:
        by_target: dict[str, list[EffectPlacement]] = {}
        channel_owner: dict[str, Optional[EffectPlacement]] = {
            name: None for name in mh_group.head_names
        }
        previous_move_name: Optional[str] = None
        for section_index, assignment in enumerate(assignments):
            section = assignment.section
            if not _is_strong_section(section):
                continue
            duration_ms = section.end_ms - section.start_ms
            if duration_ms < _MIN_SECTION_DURATION_MS:
                continue

            move_name = _choose_move(
                section_index, assignment.variation_seed,
                dynamic=section.energy_score >= _STRONG_ENERGY_GATE,
                previous_move=previous_move_name,
            )
            previous_move_name = move_name
            move = MOVE_LIBRARY[move_name]
            jitter_pan, jitter_tilt = _jitter(assignment.variation_seed, section_index)
            # Scale moving-head presence down for a per-head move on a
            # qualifying-but-not-peak section: only 2 of 4 heads render,
            # the other 2 stay dark (see _reduce_to_lit_pair). Doesn't
            # apply to "group" moves (Fan Pan-Static/-Move) -- those write
            # one identical pose into every head slot by design, matching
            # the reference sequence's own group effects.
            # _HEAD_PAIRS assumes the reference's 4-head arrangement; a
            # smaller group has no well-defined "half" to darken, so this
            # only applies once there are at least 4 heads to split. Full
            # intensity is either the absolute gate OR near THIS song's own
            # peak qualifying energy (_RELATIVE_PEAK_MARGIN) -- so a song
            # that's intense throughout but never numerically clears the
            # absolute gate still keeps all 4 heads rather than reducing
            # almost everywhere.
            full_intensity = (
                section.energy_score >= _FULL_HEADS_ENERGY_GATE
                or section.energy_score >= song_peak_energy - _RELATIVE_PEAK_MARGIN
            )
            lit_pair = (
                _choose_lit_pair(section_index, assignment.variation_seed)
                if not full_intensity and len(mh_group.head_names) >= _MIN_HEADS_FOR_LIT_PAIR
                else None
            )

            natural_start_ms = section.start_ms
            natural_end_ms = min(section.end_ms, natural_start_ms + _MAX_MOVE_DURATION_MS)

            if move.target == "group":
                heads = mh_group.head_names
                # A prior GROUP move leaves every head sharing ONE owner
                # object; a prior PER-HEAD move leaves each head with its
                # OWN distinct object -- dedupe by identity (EffectPlacement
                # isn't hashable), but trim every distinct owner (not just
                # whichever ends latest), since a group move touches every
                # head's channel and each one needs its own tail opened up.
                owners_by_id = {
                    id(channel_owner[h]): channel_owner[h] for h in heads if channel_owner[h] is not None
                }
                start_ms, warmup_duration_ms = _resolve_warmup(list(owners_by_id.values()), natural_start_ms)
                if start_ms >= natural_end_ms:
                    continue  # no room left after opening the warmup gap
                head_count = len(heads)
                pose = move.poses[0]
                move_params = _build_group_move_parameters(head_count, pose, jitter_pan, jitter_tilt)
                warmup_params = _build_group_warmup_parameters(head_count, pose, jitter_pan, jitter_tilt)
                move_placement = _add_with_warmup(
                    by_target, mh_group.name, warmup_params, move_params,
                    start_ms, natural_end_ms, warmup_duration_ms,
                )
                for h in heads:
                    channel_owner[h] = move_placement
            else:
                for head_idx, head_name in enumerate(mh_group.head_names):
                    head_index = head_idx + 1  # 1-based: matches this model's own MH{N}_Settings slot
                    pose = move.poses[head_idx % len(move.poses)]
                    move_pose = pose if lit_pair is None else _reduce_to_lit_pair(pose, head_index, lit_pair)
                    start_ms, warmup_duration_ms = _resolve_warmup(
                        [channel_owner[head_name]], natural_start_ms,
                    )
                    if start_ms >= natural_end_ms:
                        continue
                    move_params = _build_per_head_move_parameters(move_pose, jitter_pan, jitter_tilt, head_index)
                    warmup_params = _build_per_head_warmup_parameters(pose, jitter_pan, jitter_tilt, head_index)
                    move_placement = _add_with_warmup(
                        by_target, head_name, warmup_params, move_params,
                        start_ms, natural_end_ms, warmup_duration_ms,
                    )
                    channel_owner[head_name] = move_placement
        for target, placements in by_target.items():
            if placements:
                result.setdefault(target, []).extend(placements)
    return result


# Rare whole-house crash accent (see src/analyzer/crash_accents.py and
# effect_placer._place_crash_accents, which places a matching Shockwave on
# 01_BASE_All_FADES at the same marks) -- a short fan-out Pan/Tilt punch on
# the moving-head group, same duration/exclusion rules as the Shockwave so
# the two land together. Uses the reference sequence's "Fan Pan-Static"
# pose (Tilt 78.5, PanOffset 10.5) rather than the earlier hand-built
# fan-out, swapped 2026-07-17 per user request to base every Moving Head
# effect on the reference.
_CRASH_EFFECT_DURATION_MS = 700
_CRASH_VOCAL_EXCLUSION_MS = 500
_CRASH_TILT_DEG = "78.5"
_CRASH_PAN_OFFSET_DEG = "10.5"
# The punch starts this long before the crash mark and still ends
# _CRASH_EFFECT_DURATION_MS after it (user request, 2026-07-16), matching
# effect_placer._CRASH_LEAD_MS exactly so the two accents land together.
_CRASH_LEAD_MS = 1000
# The crash punch's own silent lead-in -- if nothing else is already
# lighting/positioning this group right before the punch, a warmup
# placement (Pan/Tilt/PanOffset only, no Dimmer/Wheel/Shutter) runs
# immediately before it so the heads are already fanned out and dark by
# the time the punch opens the shutter, instead of visibly snapping into
# position while lit. The mark's own timing is fixed (anchored to a real
# audio transient), so unlike the gated moves nothing here ever gets
# trimmed or delayed -- the warmup instead adapts to whatever natural gap
# already exists before it, up to _PREFERRED_WARMUP_DURATION_MS (see the
# mark loop below).


# Number of down-up notches in the crash punch's randomized flicker
# Dimmer curve (see _random_dimmer_curve) -- tuned for the punch's own
# ~700ms duration (_CRASH_EFFECT_DURATION_MS): dense enough to read as a
# stutter/strobe-burst, not so dense it blurs into an unreadable flicker.
_CRASH_DIMMER_NOTCH_COUNT = 4


def _random_dimmer_curve(seed: int, notch_count: int = _CRASH_DIMMER_NOTCH_COUNT) -> str:
    """A hand-drawn-style random flicker Dimmer curve -- full-on at both
    ends, dipping to near-off at ``notch_count`` jittered points in
    between, mined from the user's own preset (mhpresets/Random.xmh,
    2026-07-17): a point list, not a parametric curve type, alternating
    between near-0 and near-1 y-values at irregular x positions rather
    than a single flat "always on" flash. Deterministic per ``seed`` (the
    crash mark's own time_ms) so regenerating the same song reproduces
    the same flicker pattern.
    """
    def _jitter(i: int, salt: int) -> float:
        x = (seed * 2654435761 + i * 40503 + salt * 97) & 0xFFFFFFFF
        return (x % 1000) / 1000.0

    points: list[tuple[float, float]] = [(0.0, 1.0)]
    for i in range(notch_count):
        center = (i + 1) / (notch_count + 1)
        center += (_jitter(i, 1) - 0.5) * 0.1
        down_x = max(0.01, min(0.98, center))
        up_x = min(0.99, down_x + 0.02 + _jitter(i, 2) * 0.03)
        low_y = _jitter(i, 3) * 0.15
        points.append((down_x, low_y))
        points.append((up_x, 1.0))
    points.append((1.0, 1.0))

    flat: list[str] = []
    for x, y in points:
        flat.append(f"{x:.6f}")
        flat.append(f"{y:.6f}")
    return _COMMA_ESCAPE.join(flat)


def _build_crash_head_settings(head_count: int, dimmer_curve: str) -> str:
    # Group-targeted text: every slot lists every head index, matching the
    # reference sequence's group effects (Fan Pan-Static/-Move) rather
    # than a per-slot number.
    heads_field = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    return (
        f"Dimmer: {dimmer_curve};"
        f"Wheel: {_COLOR_WHITE};"
        "Shutter: On;"
        f"Pan: 0.0;Tilt: {_CRASH_TILT_DEG};"
        f"PanOffset: {_CRASH_PAN_OFFSET_DEG};TiltOffset: 0.0;"
        "Groupings: 1;Cycles: 1.0;"
        f"Heads: {heads_field}"
    )


def _build_warmup_head_settings(head_count: int) -> str:
    """Same Pan/Tilt/PanOffset pose as ``_build_crash_head_settings``, with
    no Dimmer/Wheel/Shutter commands. Confirmed by reading
    RenderMovingHead() in the real xLights source: omitting those commands
    leaves ``has_dimmers``/``shutter_open`` false, so the render never
    touches the dimmer or shutter channels at all -- they simply keep
    whatever value was already there (dark, if nothing else is active).
    """
    heads_field = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    return (
        f"Pan: 0.0;Tilt: {_CRASH_TILT_DEG};"
        f"PanOffset: {_CRASH_PAN_OFFSET_DEG};TiltOffset: 0.0;"
        "Groupings: 1;Cycles: 1.0;"
        f"Heads: {heads_field}"
    )


def _has_overlap(
    placements: list[EffectPlacement], start_ms: int, end_ms: int,
) -> bool:
    return any(p.start_ms < end_ms and p.end_ms > start_ms for p in placements)


# Pose fields of the per-head settings text DSL, longest alternatives first
# so "PanOffset:" doesn't half-match as "Pan".
_POSE_FIELD_RE = re.compile(r"(PanOffset|TiltOffset|Pan|Tilt):\s*([^;]*)")


def _pose_fields(params: dict) -> dict[str, dict[str, str]]:
    """Pan/Tilt/offset fields of every per-head settings text in ``params``."""
    out: dict[str, dict[str, str]] = {}
    for key, val in params.items():
        if key.startswith("E_TEXTCTRL_MH") and key.endswith("_Settings") and val:
            out[key] = dict(_POSE_FIELD_RE.findall(str(val)))
    return out


def _heads_already_posed(
    prior: list[EffectPlacement], before_ms: int, target_params: dict,
) -> bool:
    """True when a placement ends EXACTLY at ``before_ms`` (zero gap) having
    left every head in exactly the static pose ``target_params`` would set —
    only then does a warmup reposition nothing (user request, 2026-07-18).
    Zero gap is mandatory, not an optimization: with no active effect on
    the channels, the heads automatically return to their home position
    (user-confirmed on real hardware, 2026-07-18), so a matching pose from
    a placement that ended even slightly earlier has already been lost.
    Conservative on purpose: an active Pan/Tilt value curve on the previous
    placement means its ending pose isn't its static text fields, and a
    per-head move's placement carries a different settings-key set than a
    group-targeted one — both compare unequal, so the warmup deploys (the
    safe direction).
    """
    prev = max(
        (p for p in prior if p.end_ms <= before_ms),
        key=lambda p: p.end_ms, default=None,
    )
    if prev is None or prev.end_ms != before_ms:
        return False
    for key in ("E_VALUECURVE_MHPan", "E_VALUECURVE_MHTilt"):
        if "Active=TRUE" in str(prev.parameters.get(key, "")):
            return False
    target_pose = _pose_fields(target_params)
    return bool(target_pose) and _pose_fields(prev.parameters) == target_pose


def place_moving_head_crash_accents(
    layout: Layout,
    hierarchy: HierarchyResult,
    vocal_words: Optional[list[dict]],
    fade_exclusion_start_ms: Optional[int] = None,
    existing_placements: Optional[dict[str, list[EffectPlacement]]] = None,
) -> dict[str, list[EffectPlacement]]:
    """Place a short fan-out Pan/Tilt punch on the moving-head group at each
    rare crash mark from ``hierarchy.crash_accents``, preceded by a silent
    warmup placement when nothing already covers that lead-in window.

    Mirrors effect_placer._place_crash_accents' timing and exclusion rules
    exactly (same lead-in/duration, same vocal/fade exclusion windows) so
    the two accents land together -- see that function's docstring for the
    rationale behind the exclusion windows themselves. ``existing_placements``
    is normally the output of place_moving_head_moves -- checked across
    EVERY key (the group's own name AND every individual head model), not
    just the group's, since a per-head move and this group-targeted punch
    drive the same DMX channels (same root issue as place_moving_head_moves'
    channel_end tracking; user-observed real xLights overlap warning,
    2026-07-17). A crash mark landing while a per-head move is still
    running is skipped outright rather than shifted -- unlike the gated
    moves (anchored to a section, free to slide within it), a crash is
    anchored to a precise audio transient, so delaying it would drift it
    off the beat it's meant to land on. Returns {} when the layout has no
    moving-head group or there are no crash marks.
    """
    mh_groups = find_moving_head_groups(layout)
    if not mh_groups or not hierarchy.crash_accents:
        return {}

    existing_placements = existing_placements or {}
    word_spans = [
        (int(w["start_ms"]), int(w["end_ms"]))
        for w in (vocal_words or [])
        if int(w["end_ms"]) > int(w["start_ms"])
    ]

    def _near_vocal(time_ms: int) -> bool:
        return any(
            start - _CRASH_VOCAL_EXCLUSION_MS <= time_ms <= end + _CRASH_VOCAL_EXCLUSION_MS
            for start, end in word_spans
        )

    result: dict[str, list[EffectPlacement]] = {}
    for mh_group in mh_groups:
        head_count = len(mh_group.head_names)
        warmup_settings = _build_warmup_head_settings(head_count)
        warmup_params = _build_parameters(
            {i: warmup_settings for i in range(1, head_count + 1)},
            slider_pan=_deg_to_slider(0.0),
            slider_tilt=_deg_to_slider(float(_CRASH_TILT_DEG)),
            slider_pan_offset=_deg_to_slider(float(_CRASH_PAN_OFFSET_DEG)),
        )
        # Every existing placement that touches this group's channels --
        # the group's own key AND every individual head's, since a
        # per-head move (place_moving_head_moves) drives the same
        # channels this punch does.
        relevant_keys = (mh_group.name, *mh_group.head_names)
        channel_existing = [
            p for key in relevant_keys for p in existing_placements.get(key, [])
        ]

        placements: list[EffectPlacement] = []
        for mark in hierarchy.crash_accents:
            if _near_vocal(mark.time_ms):
                continue
            if fade_exclusion_start_ms is not None and mark.time_ms >= fade_exclusion_start_ms:
                continue
            start_ms = max(0, mark.time_ms - _CRASH_LEAD_MS)
            end_ms = min(mark.time_ms + _CRASH_EFFECT_DURATION_MS, hierarchy.duration_ms)
            if end_ms <= start_ms:
                continue
            # Randomized per mark (deterministic on mark.time_ms) so
            # back-to-back crashes in the same song don't all flicker
            # identically.
            dimmer_curve = _random_dimmer_curve(mark.time_ms)
            crash_settings = _build_crash_head_settings(head_count, dimmer_curve)
            params = _build_parameters(
                {i: crash_settings for i in range(1, head_count + 1)},
                slider_pan=_deg_to_slider(0.0),
                slider_tilt=_deg_to_slider(float(_CRASH_TILT_DEG)),
                slider_pan_offset=_deg_to_slider(float(_CRASH_PAN_OFFSET_DEG)),
            )
            # Includes crash marks already placed earlier in this same
            # loop, not just placements from place_moving_head_moves --
            # otherwise a close pair of crash marks could overlap each
            # other's punch/warmup undetected.
            all_prior = channel_existing + placements
            if _has_overlap(all_prior, start_ms, end_ms):
                continue  # a per-head move is already driving these channels

            # The crash mark's own timing is sacred (anchored to a real
            # audio transient) -- unlike the gated moves, nothing here
            # gets trimmed or delayed to open room. The warmup instead
            # fills the ENTIRE natural gap back to the previous placement
            # (user request 2026-07-18, extending the 2026-07-17 "750ms
            # was needlessly short" observation past the old 3s cap):
            # these channels are idle in that gap anyway, and parking the
            # heads in position early beats a last-moment slew.
            warmup_end_ms = start_ms
            prior_ends = [p.end_ms for p in all_prior if p.end_ms <= warmup_end_ms]
            warmup_duration_ms = max(0, warmup_end_ms - max(prior_ends, default=0))
            if _heads_already_posed(all_prior, warmup_end_ms, warmup_params):
                warmup_duration_ms = 0  # heads already in the punch pose
            warmup_start_ms = warmup_end_ms - warmup_duration_ms
            if warmup_start_ms < warmup_end_ms:
                placements.append(EffectPlacement(
                    effect_name="Moving Head",
                    xlights_id="eff_MOVINGHEAD",
                    model_or_group=mh_group.name,
                    start_ms=warmup_start_ms,
                    end_ms=warmup_end_ms,
                    parameters=dict(warmup_params),
                ))

            placements.append(EffectPlacement(
                effect_name="Moving Head",
                xlights_id="eff_MOVINGHEAD",
                model_or_group=mh_group.name,
                start_ms=start_ms,
                end_ms=end_ms,
                parameters=dict(params),
            ))
        if placements:
            result[mh_group.name] = placements
    return result


# ── Ending punches (2026-07-18) ──────────────────────────────────────────────
# Quick straight-up flash on each hierarchy.ending_punches mark — the song's
# ending "button" (cymbal hits in the final seconds before the audible end,
# see crash_accents.detect_ending_punches). Unlike the crash punch: no
# lead-in and no flicker curve — punches in a machine-gun cluster can be
# only ~200ms apart, so each flash is a hard full-on burst trimmed to leave
# a short off-gap before the next mark (back-to-back flashes with no gap
# would merge into continuous light and stop reading as hits). A dark
# position-hold warmup fills every gap — before the first flash AND inside
# the off-gaps between clustered flashes — because with no active effect
# the heads automatically return to home position (user-confirmed on real
# hardware, 2026-07-18): the hold keeps them vertical while dark, so the
# strobe look survives without the heads visibly traveling. No vocal
# exclusion either — the finale IS the moment; a shouted last word should
# not suppress it (design decision, 2026-07-18).
_ENDING_FLASH_DURATION_MS = 300
_ENDING_FLASH_OFF_GAP_MS = 50
_ENDING_TILT_DEG = "0.0"  # straight up (tilt 0 = vertical in this pose space)


def _build_ending_punch_head_settings(head_count: int) -> str:
    heads_field = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    return (
        f"Dimmer: {_DIMMER_FULL_ON};"
        f"Wheel: {_COLOR_WHITE};"
        "Shutter: On;"
        f"Pan: 0.0;Tilt: {_ENDING_TILT_DEG};"
        "PanOffset: 0.0;TiltOffset: 0.0;"
        "Groupings: 1;Cycles: 1.0;"
        f"Heads: {heads_field}"
    )


def _build_ending_warmup_head_settings(head_count: int) -> str:
    """Straight-up pose only — no Dimmer/Wheel/Shutter commands, so the
    render never touches those channels (dark pre-positioning; see
    _build_warmup_head_settings for the RenderMovingHead() confirmation)."""
    heads_field = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    return (
        f"Pan: 0.0;Tilt: {_ENDING_TILT_DEG};"
        "PanOffset: 0.0;TiltOffset: 0.0;"
        "Groupings: 1;Cycles: 1.0;"
        f"Heads: {heads_field}"
    )


def place_moving_head_ending_punches(
    layout: Layout,
    hierarchy: HierarchyResult,
    fade_exclusion_start_ms: Optional[int] = None,
    existing_placements: Optional[dict[str, list[EffectPlacement]]] = None,
) -> dict[str, list[EffectPlacement]]:
    """Place a short straight-up full-white flash on the moving-head group at
    each ``hierarchy.ending_punches`` mark.

    Mirrors place_moving_head_crash_accents' channel-conflict rule
    (``existing_placements`` checked across the group's own key AND every
    individual head model, since they drive the same DMX channels) and its
    fade-exclusion check — though ending punches sit before the audible end
    by construction, so the fade check is a safety net, not a routine
    filter. Marks are anchored to real audio transients: an overlapping
    prior placement skips the flash rather than shifting it. A dark
    position-hold warmup fills every gap before/between flashes (see the
    constants block above — heads home themselves when no effect is
    active). Returns {} when the layout has no moving-head group or there
    are no marks.
    """
    mh_groups = find_moving_head_groups(layout)
    if not mh_groups or not hierarchy.ending_punches:
        return {}

    existing_placements = existing_placements or {}
    marks = sorted(hierarchy.ending_punches, key=lambda m: m.time_ms)

    result: dict[str, list[EffectPlacement]] = {}
    for mh_group in mh_groups:
        head_count = len(mh_group.head_names)
        settings = _build_ending_punch_head_settings(head_count)
        params = _build_parameters(
            {i: settings for i in range(1, head_count + 1)},
            slider_pan=_deg_to_slider(0.0),
            slider_tilt=_deg_to_slider(0.0),
            slider_pan_offset=_deg_to_slider(0.0),
        )
        warmup_settings = _build_ending_warmup_head_settings(head_count)
        warmup_params = _build_parameters(
            {i: warmup_settings for i in range(1, head_count + 1)},
            slider_pan=_deg_to_slider(0.0),
            slider_tilt=_deg_to_slider(0.0),
            slider_pan_offset=_deg_to_slider(0.0),
        )
        relevant_keys = (mh_group.name, *mh_group.head_names)
        channel_existing = [
            p for key in relevant_keys for p in existing_placements.get(key, [])
        ]

        placements: list[EffectPlacement] = []
        for i, mark in enumerate(marks):
            if fade_exclusion_start_ms is not None and mark.time_ms >= fade_exclusion_start_ms:
                continue
            start_ms = mark.time_ms
            end_ms = min(mark.time_ms + _ENDING_FLASH_DURATION_MS,
                         hierarchy.duration_ms)
            if i + 1 < len(marks):
                end_ms = min(end_ms, marks[i + 1].time_ms - _ENDING_FLASH_OFF_GAP_MS)
            if end_ms <= start_ms:
                continue
            if _has_overlap(channel_existing + placements, start_ms, end_ms):
                continue

            # Dark position-hold warmup filling the entire gap back to the
            # previous placement (user request 2026-07-18; the mark's own
            # timing is sacred — never delayed). Before EVERY flash, not
            # just the first: with no active effect the heads automatically
            # return to home (user-confirmed on real hardware, 2026-07-18),
            # so even the deliberate off-gaps between clustered flashes
            # need a dark hold — position kept, light off, strobe look
            # preserved. Skipped only when the previous placement ends
            # exactly at this flash AND already leaves the heads in its
            # pose (_heads_already_posed).
            all_prior = channel_existing + placements
            prior_ends = [p.end_ms for p in all_prior if p.end_ms <= start_ms]
            warmup_duration_ms = max(0, start_ms - max(prior_ends, default=0))
            if _heads_already_posed(all_prior, start_ms, warmup_params):
                warmup_duration_ms = 0
            if warmup_duration_ms > 0:
                placements.append(EffectPlacement(
                    effect_name="Moving Head",
                    xlights_id="eff_MOVINGHEAD",
                    model_or_group=mh_group.name,
                    start_ms=start_ms - warmup_duration_ms,
                    end_ms=start_ms,
                    parameters=dict(warmup_params),
                ))

            placements.append(EffectPlacement(
                effect_name="Moving Head",
                xlights_id="eff_MOVINGHEAD",
                model_or_group=mh_group.name,
                start_ms=start_ms,
                end_ms=end_ms,
                parameters=dict(params),
            ))
        if placements:
            result[mh_group.name] = placements
    return result
