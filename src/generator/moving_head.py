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

v1 scope (deliberately minimal): one static color-wash placement per
section, matching the group's theme/anchor color, dimmer fully on, no
pan/tilt movement. No fan-out, no motion paths, no per-head choreography --
those are natural follow-ups once this renders correctly against real
hardware.
"""
from __future__ import annotations

import colorsys

from src.generator.models import EffectPlacement, SectionAssignment
from src.grouper.grouper import PowerGroup
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


def _hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return colorsys.rgb_to_hsv(r, g, b)


def _build_head_settings(hue: float, sat: float, val: float, head_count: int) -> str:
    heads = _COMMA_ESCAPE.join(str(i) for i in range(1, head_count + 1))
    color = _COMMA_ESCAPE.join(f"{c:.6f}" for c in (hue, sat, val))
    return (
        "Pan: 0.0;Tilt: 0;PanOffset: 0;TiltOffset: 0.0;"
        "Groupings: 1.0;Cycles: 1.0;"
        f"Heads: {heads};"
        f"Dimmer: {_DIMMER_FULL_ON};"
        f"Color: {color};"
        # Confirmed by reading MovingHeadEffect::RenderMovingHead() in the
        # real xLights source: this "Shutter: On" per-head command is the
        # ONLY thing that opens the shutter (writes the model's configured
        # ShutterOnValue to its shutter channel) -- the top-level
        # E_CHECKBOX_MHShutterEnable/E_CHECKBOX_AUTO_SHUTTER checkboxes are
        # UI-only (MovingHeadPanel::UpdateColorSettings() is what appends
        # this text when the user ticks "Enable Shutter"); the renderer
        # never reads the checkboxes themselves. Without this command the
        # shutter stays closed and the fixture is dark regardless of
        # Color/Dimmer.
        "Shutter: On"
    )


def _build_parameters(mh_group: MovingHeadGroup, hex_color: str) -> dict[str, str]:
    hue, sat, val = _hex_to_hsv(hex_color)
    per_head_settings = _build_head_settings(hue, sat, val, len(mh_group.head_names))
    params: dict[str, str] = {
        "B_CHOICE_BufferStyle": "Per Model Default",
        "E_NOTEBOOK1": "Position",
        "E_NOTEBOOK2": "Color",
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


def _section_wash_color(assignment: SectionAssignment) -> str:
    if assignment.anchor_palette:
        return assignment.anchor_palette[0]
    if assignment.theme.palette:
        return assignment.theme.palette[0]
    return "#FFFFFF"


def place_moving_head_effects(
    layout: Layout,
    assignments: list[SectionAssignment],
) -> dict[str, list[EffectPlacement]]:
    """Place a static color-wash "Moving Head" effect per section, per group.

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
        placements: list[EffectPlacement] = []
        for assignment in assignments:
            color = _section_wash_color(assignment)
            placements.append(EffectPlacement(
                effect_name="Moving Head",
                xlights_id="eff_MOVINGHEAD",
                model_or_group=mh_group.name,
                start_ms=assignment.section.start_ms,
                end_ms=assignment.section.end_ms,
                parameters=_build_parameters(mh_group, color),
            ))
        result[mh_group.name] = placements
    return result
