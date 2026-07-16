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

# Confirmed-working "dimmer fully on, no ramp" command from a real rendered
# moving-head sequence -- the trailing 4 floats are an internal xLights
# encoding we don't have documented, so this reuses the exact observed
# bit pattern rather than guessing at one. Commas are pre-escaped (see
# _COMMA_ESCAPE below).
_DIMMER_FULL_ON = "0.000000&comma;0.000000&comma;1.000000&comma;0.000000"

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
        f"Color: {color};"
        f"Dimmer: {_DIMMER_FULL_ON};"
        "Pan: 0.0;Tilt: 0;PanOffset: 0;TiltOffset: 0.0;"
        "Groupings: 1.0;Cycles: 1.0;"
        f"Heads: {heads}"
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
        "E_TEXTCTRL_MHPathDef": "",
    }
    for i in range(1, len(mh_group.head_names) + 1):
        params[f"E_TEXTCTRL_MH{i}_Settings"] = per_head_settings
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
