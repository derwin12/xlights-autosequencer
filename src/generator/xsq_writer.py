"""XSQ writer — serializes a SequencePlan to xLights .xsq XML format."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.generator.models import EffectPlacement, SequencePlan, XsqDocument, FRAME_INTERVAL_MS

# Complete xLights default parameters per effect.
# Without these, xLights may not render effects correctly.
_XLIGHTS_EFFECT_DEFAULTS: dict[str, dict[str, str]] = {
    "Bars": {
        "E_CHECKBOX_Bars_3D": "0",
        "E_CHECKBOX_Bars_Gradient": "0",
        "E_CHECKBOX_Bars_Highlight": "0",
        "E_CHECKBOX_Bars_UseFirstColorForHighlight": "0",
        "E_CHOICE_Bars_Direction": "Left",
        "E_SLIDER_Bars_BarCount": "1",
        "E_TEXTCTRL_Bars_Cycles": "1.0",
    },
    "Butterfly": {
        "E_CHOICE_Butterfly_Colors": "Palette",
        "E_CHOICE_Butterfly_Direction": "Normal",
        "E_SLIDER_Butterfly_Chunks": "1",
        "E_SLIDER_Butterfly_Skip": "2",
        "E_SLIDER_Butterfly_Speed": "10",
        "E_SLIDER_Butterfly_Style": "1",
    },
    "Color Wash": {
        "E_CHECKBOX_ColorWash_HFade": "0",
        "E_CHECKBOX_ColorWash_VFade": "0",
        "E_CHECKBOX_ColorWash_Shimmer": "0",
        "E_SLIDER_ColorWash_Count": "1",
        "E_TEXTCTRL_ColorWash_Cycles": "1.0",
    },
    "Meteors": {
        "E_CHECKBOX_Meteors_UseMusic": "0",
        "E_CHOICE_Meteors_Effect": "Down",
        "E_CHOICE_Meteors_Type": "Palette",
        "E_SLIDER_Meteors_Count": "10",
        "E_SLIDER_Meteors_Length": "25",
        "E_SLIDER_Meteors_Speed": "10",
        "E_SLIDER_Meteors_Swirl_Intensity": "0",
        "E_SLIDER_Meteors_WamupFrames": "0",
    },
    "Morph": {
        "E_CHECKBOX_Morph_AutoRepeat": "0",
        "E_CHECKBOX_Morph_End_Link": "0",
        "E_CHECKBOX_Morph_Start_Link": "0",
        "E_CHECKBOX_ShowHeadAtStart": "0",
        "E_NOTEBOOK_Morph": "Start",
        "E_SLIDER_MorphAccel": "0",
        "E_SLIDER_MorphDuration": "20",
        "E_SLIDER_MorphEndLength": "1",
        "E_SLIDER_MorphStartLength": "1",
        "E_SLIDER_Morph_End_X1": "0",
        "E_SLIDER_Morph_End_X2": "100",
        "E_SLIDER_Morph_End_Y1": "100",
        "E_SLIDER_Morph_End_Y2": "100",
        "E_SLIDER_Morph_Repeat_Count": "0",
        "E_SLIDER_Morph_Repeat_Skip": "1",
        "E_SLIDER_Morph_Stagger": "30",
        "E_SLIDER_Morph_Start_X1": "0",
        "E_SLIDER_Morph_Start_X2": "100",
        "E_SLIDER_Morph_Start_Y1": "0",
        "E_SLIDER_Morph_Start_Y2": "0",
    },
    "Fire": {
        "E_CHECKBOX_Fire_GrowWithMusic": "0",
        "E_SLIDER_Fire_Height": "50",
        "E_SLIDER_Fire_HueShift": "0",
    },
    "Twinkle": {
        "E_CHECKBOX_Twinkle_ReRandom": "0",
        "E_CHECKBOX_Twinkle_Strobe": "0",
        "E_SLIDER_Twinkle_Count": "3",
        "E_SLIDER_Twinkle_Steps": "30",
    },
    "Shimmer": {
        "E_CHECKBOX_Shimmer_Use_All_Colors": "0",
        "E_SLIDER_Shimmer_Duty_Factor": "50",
        "E_SLIDER_Shimmer_Cycles": "10",
    },
    "Strobe": {
        "E_SLIDER_Number_Strobes": "3",
        "E_SLIDER_Strobe_Duration": "10",
        "E_SLIDER_Strobe_Type": "1",
    },
    "Snowflakes": {
        "E_CHOICE_Falling": "Driving",
        "E_SLIDER_Snowflakes_Count": "5",
        "E_SLIDER_Snowflakes_Speed": "10",
        "E_SLIDER_Snowflakes_Type": "1",
    },
    "Ripple": {
        "E_CHECKBOX_Ripple3D": "0",
        "E_CHOICE_Ripple_Movement": "Explode",
        "E_CHOICE_Ripple_Object_To_Draw": "Circle",
        "E_CHOICE_Ripple_Draw_Style": "Old",
        "E_SLIDER_RIPPLE_POINTS": "5",
        "E_SLIDER_Ripple_Thickness": "3",
        "E_SLIDER_Ripple_Cycles": "10",
        "E_SLIDER_Ripple_Scale": "100",
    },
    "Spirals": {
        "E_CHECKBOX_Spirals_3D": "0",
        "E_CHECKBOX_Spirals_Blend": "0",
        "E_CHECKBOX_Spirals_Grow": "0",
        "E_CHECKBOX_Spirals_Shrink": "0",
        "E_CHOICE_Spirals_Direction": "Up",
        "E_SLIDER_Spirals_Count": "1",
        "E_SLIDER_Spirals_Rotation": "20",
        "E_SLIDER_Spirals_Thickness": "50",
        "E_SLIDER_Spirals_Movement": "10",
    },
    "Single Strand": {
        "E_CHOICE_SingleStrand_Colors": "Palette",
        "E_CHOICE_Chase_Type1": "Left-Right",
        "E_CHOICE_Fade_Type": "None",
        "E_SLIDER_Number_Chases": "1",
        "E_SLIDER_Chase_Rotations": "10",
        "E_SLIDER_Color_Mix1": "10",
        "E_SLIDER_Chase_Offset": "0",
        "E_CHECKBOX_Chase_Group_All": "0",
    },
    "Pinwheel": {
        "E_CHOICE_Pinwheel_Style": "New Render Method",
        "E_SLIDER_Pinwheel_Arms": "3",
        "E_SLIDER_Pinwheel_ArmSize": "100",
        "E_SLIDER_Pinwheel_Speed": "10",
        "E_SLIDER_Pinwheel_Thickness": "0",
        "E_SLIDER_Pinwheel_Twist": "0",
    },
    "Plasma": {
        "E_CHOICE_Plasma_Color": "Normal",
        "E_SLIDER_Plasma_Line_Density": "1",
        "E_SLIDER_Plasma_Speed": "10",
        "E_SLIDER_Plasma_Style": "1",
    },
    "Garlands": {
        "E_SLIDER_Garlands_Cycles": "1",
        "E_SLIDER_Garlands_Spacing": "0",
        "E_SLIDER_Garlands_Type": "0",
    },
    "Curtain": {
        "E_CHECKBOX_Curtain_Repeat": "0",
        "E_CHOICE_Curtain_Edge": "center",
        "E_CHOICE_Curtain_Effect": "open",
        "E_SLIDER_Curtain_Swag": "3",
        "E_SLIDER_Curtain_Speed": "1",
    },
    "Circles": {
        "E_CHECKBOX_Circles_Bounce": "0",
        "E_CHECKBOX_Circles_Collide": "0",
        "E_CHECKBOX_Circles_Linear_Fade": "0",
        "E_CHECKBOX_Circles_Plasma": "0",
        "E_CHECKBOX_Circles_Radial": "0",
        "E_CHECKBOX_Circles_Radial_3D": "0",
        "E_CHECKBOX_Circles_Random_m": "0",
        "E_SLIDER_Circles_Count": "3",
        "E_SLIDER_Circles_Size": "5",
        "E_SLIDER_Circles_Speed": "1",
    },
    "Shockwave": {
        "E_SLIDER_Shockwave_Accel": "0",
        "E_SLIDER_Shockwave_CenterX": "50",
        "E_SLIDER_Shockwave_CenterY": "50",
        "E_SLIDER_Shockwave_End_Radius": "10",
        "E_SLIDER_Shockwave_End_Width": "10",
        "E_SLIDER_Shockwave_Start_Radius": "1",
        "E_SLIDER_Shockwave_Start_Width": "5",
    },
    "Liquid": {
        "E_CHECKBOX_MixColors": "0",
        "E_CHECKBOX_HoldColor": "1",
        "E_CHECKBOX_BottomBarrier": "1",
        "E_CHECKBOX_TopBarrier": "0",
        "E_CHECKBOX_LeftBarrier": "0",
        "E_CHECKBOX_RightBarrier": "0",
        "E_CHOICE_ParticleType": "Elastic",
        "E_SLIDER_Liquid_Gravity": "100",
        "E_SLIDER_Liquid_GravityAngle": "0",
        "E_SLIDER_LifeTime": "1000",
        "E_SLIDER_X1": "50",
        "E_SLIDER_Y1": "100",
        "E_SLIDER_Direction1": "270",
        "E_SLIDER_Velocity1": "100",
        "E_SLIDER_Flow1": "100",
    },
    "Galaxy": {
        "E_CHECKBOX_Galaxy_Blend_Edges": "1",
        "E_CHECKBOX_Galaxy_Inward": "0",
        "E_CHECKBOX_Galaxy_Reverse": "0",
        "E_SLIDER_Galaxy_Accel": "0",
        "E_SLIDER_Galaxy_CenterX": "50",
        "E_SLIDER_Galaxy_CenterY": "50",
        "E_SLIDER_Galaxy_Duration": "20",
        "E_SLIDER_Galaxy_End_Radius": "10",
        "E_SLIDER_Galaxy_End_Width": "5",
        "E_SLIDER_Galaxy_Revolutions": "3",
        "E_SLIDER_Galaxy_Start_Angle": "0",
        "E_SLIDER_Galaxy_Start_Radius": "1",
        "E_SLIDER_Galaxy_Start_Width": "5",
    },
    "Wave": {
        "E_CHOICE_Wave_Direction": "Right to Left",
        "E_CHOICE_Wave_FillColor": "None",
        "E_CHECKBOX_Wave_Mirror_Wave": "0",
        "E_SLIDER_Wave_Number_Of_Waves": "1",
        "E_SLIDER_Wave_Speed": "10",
        "E_SLIDER_Wave_Thickness": "20",
    },
}


def write_xsq(plan: SequencePlan, output_path: Path, hierarchy: HierarchyResult | None = None, audio_path: Path | None = None) -> None:
    """Write a SequencePlan as a valid xLights .xsq XML file.

    Follows the xLights 2024+ schema:
    - FixedPointTiming="25" (40fps)
    - Deduplicates EffectDB entries and ColorPalettes
    - Frame-aligns all times to 25ms multiples
    - Model names from DisplayElements match layout
    """
    # Collect all placements across sections
    all_placements: dict[str, list[EffectPlacement]] = {}
    for section in plan.sections:
        for group_name, placements in section.group_effects.items():
            all_placements.setdefault(group_name, []).extend(placements)

    # Remove overlaps: sort by start time and trim/remove overlapping effects
    for group_name in all_placements:
        all_placements[group_name] = _remove_overlaps(all_placements[group_name])

    # Build deduplication indexes and cache serialized strings per placement
    palette_index: dict[str, int] = {}
    palette_list: list[str] = []
    effect_db_index: dict[str, int] = {}
    effect_db_list: list[str] = []
    placement_cache: dict[int, tuple[int, int]] = {}  # id(p) -> (effect_ref, palette_ref)

    for placements in all_placements.values():
        for p in placements:
            pal_idx = _ensure_palette(p.color_palette, palette_index, palette_list)
            eff_idx = _ensure_effect_entry(p, effect_db_index, effect_db_list)
            placement_cache[id(p)] = (eff_idx, pal_idx)

    # Build XML tree
    root = ET.Element("xsequence")
    root.set("BaseChannel", "0")
    root.set("ChanCtrlBasic", "0")
    root.set("ChanCtrlColor", "0")
    root.set("FixedPointTiming", str(FRAME_INTERVAL_MS))
    root.set("ModelBlending", "true")

    # <head>
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "version").text = "2026.03"
    ET.SubElement(head, "author").text = "xlight-autosequencer"
    ET.SubElement(head, "song").text = plan.song_profile.title
    ET.SubElement(head, "artist").text = plan.song_profile.artist
    # Use a relative path — xLights resolves relative to the show/sequence directory
    if audio_path is not None:
        try:
            media_ref = str(audio_path.resolve().relative_to(output_path.parent.resolve()))
        except ValueError:
            media_ref = audio_path.name
    else:
        media_ref = plan.song_profile.title + ".mp3"
    ET.SubElement(head, "mediaFile").text = media_ref
    ET.SubElement(head, "sequenceType").text = "Media"
    ET.SubElement(head, "sequenceTiming").text = f"{FRAME_INTERVAL_MS} ms"
    duration_sec = plan.song_profile.duration_ms / 1000.0
    ET.SubElement(head, "sequenceDuration").text = f"{duration_sec:.3f}"

    # <ColorPalettes>
    palettes_el = ET.SubElement(root, "ColorPalettes")
    for palette_str in palette_list:
        cp = ET.SubElement(palettes_el, "ColorPalette")
        cp.text = palette_str

    # <EffectDB>
    effectdb_el = ET.SubElement(root, "EffectDB")
    for effect_str in effect_db_list:
        ef = ET.SubElement(effectdb_el, "Effect")
        ef.text = effect_str

    # <DisplayElements> — only include groups/models that have effects
    display_el = ET.SubElement(root, "DisplayElements")
    displayed_models = set()
    for group_name in all_placements:
        if group_name not in displayed_models:
            elem = ET.SubElement(display_el, "Element")
            elem.set("type", "model")
            elem.set("name", group_name)
            elem.set("visible", "1")
            elem.set("collapsed", "0")
            elem.set("active", "1")
            displayed_models.add(group_name)

    # Add timing track display elements
    timing_tracks = _collect_timing_tracks(hierarchy) if hierarchy else {}
    for track_name in timing_tracks:
        elem = ET.SubElement(display_el, "Element")
        elem.set("type", "timing")
        elem.set("name", track_name)
        elem.set("visible", "1")
        elem.set("collapsed", "0")
        elem.set("active", "1" if track_name == "Beats" else "0")

    # <ElementEffects>
    effects_el = ET.SubElement(root, "ElementEffects")
    for group_name, placements in all_placements.items():
        model_el = ET.SubElement(effects_el, "Element")
        model_el.set("type", "model")
        model_el.set("name", group_name)

        layer_el = ET.SubElement(model_el, "EffectLayer")
        for p in sorted(placements, key=lambda p: p.start_ms):
            effect_el = ET.SubElement(layer_el, "Effect")

            ref_idx, palette_idx = placement_cache.get(id(p), (0, 0))

            effect_el.set("ref", str(ref_idx))
            effect_el.set("name", p.effect_name)
            effect_el.set("startTime", str(p.start_ms))
            effect_el.set("endTime", str(p.end_ms))
            effect_el.set("palette", str(palette_idx))
            effect_el.set("selected", "0")

    # Add timing tracks to ElementEffects
    for track_name, marks in timing_tracks.items():
        timing_el = ET.SubElement(effects_el, "Element")
        timing_el.set("type", "timing")
        timing_el.set("name", track_name)

        layer_el = ET.SubElement(timing_el, "EffectLayer")
        for i, mark in enumerate(marks):
            start = mark.time_ms
            end = marks[i + 1].time_ms if i + 1 < len(marks) else int(plan.song_profile.duration_ms)
            if end <= start:
                continue
            effect_el = ET.SubElement(layer_el, "Effect")
            effect_el.set("label", mark.label or "")
            effect_el.set("startTime", str(start))
            effect_el.set("endTime", str(end))

    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="UTF-8", xml_declaration=True)


_DEFAULT_PALETTE_COLORS = [
    "#FF0000", "#00FF00", "#0000FF", "#FFFF00",
    "#000000", "#00FFFF", "#FF00FF", "#FFFFFF",
]


def _serialize_palette(colors: list[str]) -> str:
    """Convert a list of hex colors to xLights C_BUTTON_Palette format.

    Always fills all 8 palette slots — theme colors first, then defaults.
    xLights expects C_BUTTON entries grouped before C_CHECKBOX entries.
    Only the slots with theme colors get C_CHECKBOX enabled.
    """
    padded = list(colors[:8])
    active_count = len(padded)
    while len(padded) < 8:
        padded.append(_DEFAULT_PALETTE_COLORS[len(padded)])

    buttons = [f"C_BUTTON_Palette{i}={c}" for i, c in enumerate(padded, start=1)]
    checkboxes = [
        f"C_CHECKBOX_Palette{i}={'1' if i <= active_count else '0'}"
        for i in range(1, 9)
    ]
    return ",".join(buttons + checkboxes)


def _serialize_effect_params(placement: EffectPlacement) -> str:
    """Serialize effect parameters to xLights comma-separated format.

    Merges xLights defaults for the effect so all required params are present.
    Theme/user overrides take precedence over defaults.
    """
    # Start with xLights defaults for this effect
    defaults = dict(_XLIGHTS_EFFECT_DEFAULTS.get(placement.effect_name, {}))

    # Override with our explicit parameters
    for key, val in placement.parameters.items():
        if isinstance(val, bool):
            defaults[key] = "1" if val else "0"
        else:
            defaults[key] = str(val)

    # Add fades
    if placement.fade_in_ms > 0:
        defaults["E_TEXTCTRL_Fadein"] = str(placement.fade_in_ms)
    if placement.fade_out_ms > 0:
        defaults["E_TEXTCTRL_Fadeout"] = str(placement.fade_out_ms)

    # Encode value curves inline
    for param_name, points in placement.value_curves.items():
        curve_str = _encode_value_curve(param_name, points)
        defaults[param_name] = curve_str

    parts = [f"{k}={v}" for k, v in sorted(defaults.items())]
    return ",".join(parts)


def _encode_value_curve(param_name: str, points: list[tuple[float, float]]) -> str:
    """Encode a value curve in xLights inline format."""
    values_str = "|".join(f"{x:.2f}:{y:.2f}" for x, y in points)
    return f"Active=TRUE|Id=ID_{param_name}|Type=Ramp|Min=0.00|Max=100.00|Values={values_str}"


def _ensure_palette(
    colors: list[str],
    index: dict[str, int],
    palette_list: list[str],
) -> int:
    """Add palette to dedup index if not already present. Return index."""
    key = _serialize_palette(colors)
    if key not in index:
        index[key] = len(palette_list)
        palette_list.append(key)
    return index[key]


def _ensure_effect_entry(
    placement: EffectPlacement,
    index: dict[str, int],
    effect_list: list[str],
) -> int:
    """Add effect params to dedup index if not already present. Return index."""
    key = _serialize_effect_params(placement)
    if key not in index:
        index[key] = len(effect_list)
        effect_list.append(key)
    return index[key]


def parse_xsq(path: Path) -> XsqDocument:
    """Parse an existing .xsq XML file into an XsqDocument."""
    tree = ET.parse(str(path))
    root = tree.getroot()

    head = root.find("head")
    media_file = ""
    duration_sec = 0.0
    if head is not None:
        media_el = head.find("mediaFile")
        if media_el is not None and media_el.text:
            media_file = media_el.text
        dur_el = head.find("sequenceDuration")
        if dur_el is not None and dur_el.text:
            duration_sec = float(dur_el.text)

    frame_interval = int(root.get("FixedPointTiming", "25"))

    # Parse color palettes
    color_palettes: list[list[str]] = []
    palettes_el = root.find("ColorPalettes")
    if palettes_el is not None:
        for cp in palettes_el:
            text = cp.text or ""
            color_palettes.append([text])

    # Parse effect DB
    effect_db: list[str] = []
    effectdb_el = root.find("EffectDB")
    if effectdb_el is not None:
        for ef in effectdb_el:
            effect_db.append(ef.text or "")

    # Parse display elements
    display_elements: list[str] = []
    display_el = root.find("DisplayElements")
    if display_el is not None:
        for elem in display_el:
            name = elem.get("name", "")
            if name:
                display_elements.append(name)

    # Parse element effects
    element_effects: dict[str, list[EffectPlacement]] = {}
    effects_el = root.find("ElementEffects")
    if effects_el is not None:
        for model_el in effects_el:
            model_name = model_el.get("name", "")
            placements: list[EffectPlacement] = []
            for layer_el in model_el:
                for effect_el in layer_el:
                    placements.append(EffectPlacement(
                        effect_name=effect_el.get("name", ""),
                        xlights_id=effect_el.get("name", ""),
                        model_or_group=model_name,
                        start_ms=int(effect_el.get("startTime", "0")),
                        end_ms=int(effect_el.get("endTime", "0")),
                    ))
            if placements:
                element_effects[model_name] = placements

    return XsqDocument(
        media_file=media_file,
        duration_sec=duration_sec,
        frame_interval_ms=frame_interval,
        color_palettes=color_palettes,
        effect_db=effect_db,
        display_elements=display_elements,
        element_effects=element_effects,
    )


def remove_effects_in_range(doc: XsqDocument, start_ms: int, end_ms: int) -> None:
    """Remove all effect placements that overlap with the given time range."""
    for model_name in list(doc.element_effects.keys()):
        doc.element_effects[model_name] = [
            p for p in doc.element_effects[model_name]
            if not (p.start_ms >= start_ms and p.end_ms <= end_ms)
        ]
        if not doc.element_effects[model_name]:
            del doc.element_effects[model_name]


def _remove_overlaps(placements: list[EffectPlacement]) -> list[EffectPlacement]:
    """Sort placements by start time and trim so none overlap on the same layer.

    If two effects overlap, the earlier one's end_ms is trimmed to the later
    one's start_ms. Effects that become zero-length are dropped.
    """
    if len(placements) <= 1:
        return placements

    sorted_placements = sorted(placements, key=lambda p: p.start_ms)
    result: list[EffectPlacement] = [sorted_placements[0]]

    for p in sorted_placements[1:]:
        prev = result[-1]
        if p.start_ms < prev.end_ms:
            # Overlap — trim the previous effect to end where this one starts
            prev.end_ms = p.start_ms
            if prev.end_ms <= prev.start_ms:
                result.pop()  # previous effect collapsed to nothing
        result.append(p)

    return [p for p in result if p.end_ms > p.start_ms]


def _collect_timing_tracks(hierarchy: HierarchyResult | None) -> dict[str, list[TimingMark]]:
    """Collect timing tracks from hierarchy for embedding in the .xsq."""
    if hierarchy is None:
        return {}

    tracks: dict[str, list[TimingMark]] = {}

    if hierarchy.beats and hierarchy.beats.marks:
        tracks["Beats"] = hierarchy.beats.marks

    if hierarchy.bars and hierarchy.bars.marks:
        tracks["Bars"] = hierarchy.bars.marks

    if hierarchy.sections:
        tracks["Sections"] = hierarchy.sections

    if hierarchy.chords and hierarchy.chords.marks:
        tracks["Chords"] = hierarchy.chords.marks

    # Add onset events for the best stem
    for stem_name, track in hierarchy.events.items():
        if track.marks:
            tracks[f"Onsets ({stem_name})"] = track.marks
            break  # just the first/best one

    return tracks


def fseq_guidance(output_path: Path) -> str:
    """Return FSEQ rendering guidance message."""
    return (
        f"\nTo render FSEQ: Open {output_path} in xLights → "
        "Tools → Batch Render (F9) → File → Export Sequence → FSEQ\n"
    )
