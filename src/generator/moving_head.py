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

v1 scope (deliberately minimal): one static white wash placement per
section, dimmer fully on, no pan/tilt movement. No fan-out, no motion
paths, no per-head choreography -- those are natural follow-ups once this
renders correctly against real hardware.

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
wheel-type fixture -- white sidesteps the problem entirely.
"""
from __future__ import annotations

from src.generator.models import EffectPlacement, SectionAssignment
from src.grouper.layout import Layout, MovingHeadGroup, find_moving_head_groups

# "Dimmer: x1,y1,x2,y2,..." is a value-curve point list, not an opaque bit
# pattern -- confirmed by reading MovingHeadEffect::CalculateDimmer() in the
# real xLights source (H:\XlightsSourceDir\xLights\src-core\effects\
# MovingHeadEffect.cpp): x is position (0-1) across the effect's duration,
# y is dimmer output (0-1, i.e. 0-255). Two points (0,1) and (1,1) is a flat
# curve at 100% for the whole effect -- "dimmer fully on". Matches a real
# working effect the user copied out of xLights (2026-07-16) against their
# own MH-1..MH-4 fixtures. Commas are pre-escaped (see _COMMA_ESCAPE below).
_DIMMER_FULL_ON = "0.000000&comma;1.000000&comma;1.000000&comma;1.000000"

# xLights always writes all 8 MH{n}_Settings slots regardless of how many
# heads are actually in the group (confirmed in the same real working
# effect: a 4-head group still had MH5_Settings..MH8_Settings present, just
# empty) -- unused slots get an empty string.
_MAX_HEAD_SLOTS = 8

# The top-level effect settings string xLights writes is itself
# comma-delimited ("key1=val1,key2=val2,..."), so any literal comma inside
# an E_TEXTCTRL_* value must be escaped or xLights splits the value on it
# and misparses everything after. Confirmed against a real rendered
# Moving Head sequence, where every comma inside MH{n}_Settings text is
# written as "&comma;" rather than ",".
_COMMA_ESCAPE = "&comma;"

# Hue 0.0, saturation 0.0, value 1.0 -- pure white. See the module
# docstring for why this is a fixed constant rather than a derived color.
_COLOR_WHITE = _COMMA_ESCAPE.join(("0.000000", "0.000000", "1.000000"))


def _build_head_settings(head_count: int) -> str:
    heads = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    return (
        "Pan: 0.0;Tilt: 0;PanOffset: 0;TiltOffset: 0.0;"
        "Groupings: 1.0;Cycles: 1.0;"
        f"Heads: {heads};"
        f"Dimmer: {_DIMMER_FULL_ON};"
        # "Wheel:" (not "Color:") for a genuine color-wheel fixture --
        # confirmed against the user's real MH-1..MH-4 (configured as
        # DmxColorAbilityWheel). Reading RenderMovingHead() in the real
        # xLights source shows "AutoShutter: true" is only ever consulted
        # inside the has_color_wheel branch (i.e. only when the command is
        # "Wheel:", never "Color:") -- pairing "Color:" with "AutoShutter"
        # would silently do nothing.
        f"Wheel: {_COLOR_WHITE};"
        "AutoShutter: true;"
        # Confirmed by reading MovingHeadEffect::RenderMovingHead(): this
        # "Shutter: On" per-head command is what opens the shutter (writes
        # the model's configured ShutterOnValue to its shutter channel) --
        # the top-level E_CHECKBOX_MHShutterEnable/E_CHECKBOX_AUTO_SHUTTER
        # checkboxes are UI-only (MovingHeadPanel::UpdateColorSettings() is
        # what appends this text when the user ticks "Enable Shutter"); the
        # renderer never reads the checkboxes themselves. Without it the
        # shutter stays closed and the fixture is dark regardless of
        # Wheel/Dimmer.
        "Shutter: On"
    )


def _build_parameters(mh_group: MovingHeadGroup) -> dict[str, str]:
    per_head_settings = _build_head_settings(len(mh_group.head_names))
    params: dict[str, str] = {
        "B_CHOICE_BufferStyle": "Per Model Default",
        "E_NOTEBOOK1": "Position",
        "E_NOTEBOOK2": "ColorWheel",
        "E_SLIDER_MHPan": "0",
        "E_SLIDER_MHTilt": "0",
        "E_SLIDER_MHPanOffset": "0",
        "E_SLIDER_MHTiltOffset": "0",
        "E_SLIDER_MHGroupings": "1",
        "E_SLIDER_MHCycles": "1",
        "E_SLIDER_MHPathScale": "0",
        "E_SLIDER_MHTimeOffset": "0",
        "E_CHECKBOX_MHIgnorePan": "0",
        "E_CHECKBOX_MHIgnoreTilt": "0",
        "E_CHECKBOX_AUTO_SHUTTER": "1",
        # Newer xLights builds gate the shutter DMX channel behind this
        # checkbox; without it the shutter never opens regardless of
        # Dimmer/Auto Shutter, so real hardware stays dark. Confirmed
        # against real xLights (user, 2026-07-16) -- makes the shutter
        # choreography seen in the vendor examples' separate "MH Shutters"
        # channel model unnecessary for this pipeline.
        "E_CHECKBOX_MHShutterEnable": "1",
        # Motion-pattern preset (Circle/Figure8/...) -- disabled in v1
        # (no motion), but xLights always writes these keys with defaults
        # regardless of whether the pattern is enabled.
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
        "T_CHECKBOX_Canvas": "0",
        "T_CHECKBOX_LayerMorph": "0",
        "T_CHOICE_LayerMethod": "Normal",
        "T_SLIDER_EffectLayerMix": "0",
    }
    head_count = len(mh_group.head_names)
    for i in range(1, _MAX_HEAD_SLOTS + 1):
        params[f"E_TEXTCTRL_MH{i}_Settings"] = per_head_settings if i <= head_count else ""
    return params


def place_moving_head_effects(
    layout: Layout,
    assignments: list[SectionAssignment],
) -> dict[str, list[EffectPlacement]]:
    """Place a static white wash "Moving Head" effect per section, per group.

    Song-scoped rather than folded into the per-section `place_effects()`
    pass: moving-head groups aren't in the tiered `groups` list at all (see
    grouper.generate_groups), so there's no tier/recipe machinery for them
    to plug into. Returns {} when the layout has no moving-head groups.
    """
    mh_groups = find_moving_head_groups(layout)
    if not mh_groups or not assignments:
        return {}

    result: dict[str, list[EffectPlacement]] = {}
    for mh_group in mh_groups:
        params = _build_parameters(mh_group)
        placements = [
            EffectPlacement(
                effect_name="Moving Head",
                xlights_id="eff_MOVINGHEAD",
                model_or_group=mh_group.name,
                start_ms=assignment.section.start_ms,
                end_ms=assignment.section.end_ms,
                parameters=dict(params),
            )
            for assignment in assignments
        ]
        result[mh_group.name] = placements
    return result
