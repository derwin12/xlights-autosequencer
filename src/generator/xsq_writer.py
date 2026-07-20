"""XSQ writer — serializes a SequencePlan to xLights .xsq XML format."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.generator.image_catalog import load_image_library
from src.generator.models import EffectPlacement, SequencePlan, XsqDocument, FRAME_INTERVAL_MS

logger = logging.getLogger(__name__)

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
        "E_SLIDER_Bars_Cycles": "1",
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
        "E_SLIDER_Morph_Repeat_Count": "0",
        "E_SLIDER_Morph_Repeat_Skip": "1",
        "E_SLIDER_Morph_Stagger": "30",
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
        "E_TEXTCTRL_Shimmer_Cycles": "1.0",
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
        "E_TEXTCTRL_Ripple_Cycles": "1.0",
        "E_SLIDER_Ripple_Scale": "100",
    },
    "Spirals": {
        "E_CHECKBOX_Spirals_3D": "0",
        "E_CHECKBOX_Spirals_Blend": "0",
        "E_CHECKBOX_Spirals_Grow": "0",
        "E_CHECKBOX_Spirals_Shrink": "0",
        "E_SLIDER_Spirals_Count": "1",
        "E_TEXTCTRL_Spirals_Movement": "1",
        "E_SLIDER_Spirals_Rotation": "20",
        "E_SLIDER_Spirals_Thickness": "50",
    },
    "Single Strand": {
        "E_CHOICE_SingleStrand_Colors": "Palette",
        "E_CHOICE_Chase_Type1": "Left-Right",
        "E_CHOICE_Fade_Type": "None",
        "E_SLIDER_Number_Chases": "1",
        "E_TEXTCTRL_Chase_Rotations": "1.0",
        "E_SLIDER_Color_Mix1": "10",
        "E_TEXTCTRL_Chase_Offset": "0.0",
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
        "E_TEXTCTRL_Garlands_Cycles": "1.0",
        "E_SLIDER_Garlands_Spacing": "10",
        "E_SLIDER_Garlands_Type": "0",
        "E_CHOICE_Garlands_Direction": "Up",
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
        "E_CHECKBOX_Circles_Linear_Fade": "0",
        "E_CHECKBOX_Circles_Plasma": "0",
        "E_CHECKBOX_Circles_Radial": "0",
        "E_CHECKBOX_Circles_Radial_3D": "0",
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
        "E_TEXTCTRL_Liquid_Gravity": "10.0",
        "E_TEXTCTRL_Liquid_GravityAngle": "0",
        "E_TEXTCTRL_LifeTime": "1000",
        "E_TEXTCTRL_X1": "50",
        "E_TEXTCTRL_Y1": "100",
        "E_TEXTCTRL_Direction1": "270",
        "E_TEXTCTRL_Velocity1": "100",
        "E_TEXTCTRL_Flow1": "100",
    },
    "Galaxy": {
        "E_CHECKBOX_Galaxy_Blend_Edges": "1",
        "E_CHECKBOX_Galaxy_Inward": "0",
        "E_CHECKBOX_Galaxy_Reverse": "0",
        "E_CHECKBOX_Galaxy_Scale": "1",
        "E_CHOICE_Galaxy_RenderStyle": "New Render Method",
        "E_SLIDER_Galaxy_Accel": "0",
        "E_SLIDER_Galaxy_CenterX": "50",
        "E_SLIDER_Galaxy_CenterY": "50",
        "E_SLIDER_Galaxy_Duration": "20",
        "E_SLIDER_Galaxy_End_Radius": "10",
        "E_SLIDER_Galaxy_End_Width": "5",
        "E_SLIDER_Galaxy_Revolutions": "1440",
        "E_SLIDER_Galaxy_Start_Angle": "0",
        "E_SLIDER_Galaxy_Start_Radius": "1",
        "E_SLIDER_Galaxy_Start_Width": "5",
    },
    "Wave": {
        "E_CHECKBOX_Mirror_Wave": "0",
        "E_CHOICE_Fill_Colors": "None",
        "E_CHOICE_Wave_Direction": "Right to Left",
        "E_CHOICE_Wave_Type": "Sine",
        "E_SLIDER_Number_Waves": "180",
        "E_SLIDER_Thickness_Percentage": "25",
        "E_SLIDER_Wave_Height": "50",
        "E_TEXTCTRL_Wave_Speed": "10.0",
    },
    # Copied verbatim from a user-verified working effect (2026-07-12).
    # FaceDefinition and TimingTrack are per-placement parameters set by
    # effect_placer._place_singing_faces.
    "Faces": {
        "E_CHECKBOX_Faces_Fade": "0",
        "E_CHECKBOX_Faces_Outline": "1",
        "E_CHECKBOX_Faces_SuppressShimmer": "0",
        "E_CHECKBOX_Faces_SuppressWhenNotSinging": "0",
        "E_CHECKBOX_Faces_TransparentBlack": "0",
        "E_CHOICE_Faces_EyeBlinkDuration": "Normal",
        "E_CHOICE_Faces_EyeBlinkFrequency": "Normal",
        "E_CHOICE_Faces_Eyes": "Auto",
        "E_CHOICE_Faces_UseState": "",
        "E_TEXTCTRL_Faces_TransparentBlack": "0",
        "T_CHECKBOX_LayerMorph": "0",
        "T_CHOICE_LayerMethod": "Normal",
        "T_SLIDER_EffectLayerMix": "0",
    },
    # Copied verbatim from a user-verified working effect (2026-07-12).
    # LyricTrack is a per-placement parameter set by
    # effect_placer._place_lyric_text ("<track> - Words" form).
    "Text": {
        "E_CHECKBOX_Text_Color_PerWord": "0",
        "E_CHECKBOX_Text_PixelOffsets": "0",
        "E_CHOICE_Text_Count": "none",
        "E_CHOICE_Text_Dir": "none",
        "E_CHOICE_Text_Effect": "normal",
        "E_CHOICE_Text_Font": "10-12x12 Bold",
        "E_FILEPICKERCTRL_Text_File": "",
        "E_FONTPICKER_Text_Font": "'segoe ui'",
        "E_NOTEBOOK": "Start Position",
        "E_SLIDER_Text_XEnd": "0",
        "E_SLIDER_Text_XStart": "0",
        "E_SLIDER_Text_YEnd": "0",
        "E_SLIDER_Text_YStart": "0",
        "E_TEXTCTRL_Text": "",
        "E_TEXTCTRL_Text_Speed": "10",
        "T_CHECKBOX_LayerMorph": "0",
        "T_CHOICE_LayerMethod": "Normal",
        "T_SLIDER_EffectLayerMix": "0",
    },
    # Copied verbatim from a user-verified working effect (2026-07-14).
    # Video_Filename and Duration are per-placement parameters set by
    # effect_placer._place_video_effect.
    "Video": {
        "E_CHECKBOX_SynchroniseWithAudio": "0",
        "E_CHECKBOX_Video_AspectRatio": "0",
        "E_CHECKBOX_Video_TransparentBlack": "0",
        "E_CHOICE_Video_DurationTreatment": "Normal",
        "E_TEXTCTRL_SampleSpacing": "0",
        "E_TEXTCTRL_Video_CropBottom": "0",
        "E_TEXTCTRL_Video_CropLeft": "0",
        "E_TEXTCTRL_Video_CropRight": "100",
        "E_TEXTCTRL_Video_CropTop": "100",
        "E_TEXTCTRL_Video_Starttime": "0.0",
        "E_TEXTCTRL_Video_TransparentBlack": "0",
        "T_CHECKBOX_LayerMorph": "0",
        "T_CHOICE_LayerMethod": "Normal",
        "T_SLIDER_EffectLayerMix": "0",
    },
}


def write_xsq(
    plan: SequencePlan,
    output_path: Path,
    hierarchy: HierarchyResult | None = None,
    audio_path: Path | None = None,
    scoped_duration_ms: int | None = None,
    audio_offset_ms: int | None = None,
    lyrics: list[dict] | None = None,
    words: list[dict] | None = None,
    phonemes: list[dict] | None = None,
    include_extra_timing: bool = True,
) -> None:
    """Write a SequencePlan as a valid xLights .xsq XML file.

    Follows the xLights 2024+ schema:
    - FixedPointTiming="25" (40fps)
    - Deduplicates EffectDB entries and ColorPalettes
    - Frame-aligns all times to 25ms multiples
    - Model names from DisplayElements match layout

    Optional kwargs for section preview (spec 049):
    - scoped_duration_ms: when set, overrides sequenceDuration in <head>.
      Use for a short-section preview so the xLights timeline covers only
      the previewed window.
    - audio_offset_ms: when set, (a) emits a <mediaOffset> element in <head>
      with this value (milliseconds), and (b) subtracts this from every
      placement's startTime/endTime so the output timeline starts at 0.
      EffectPlacement objects are NOT mutated — the shift is applied only
      during serialization.
    - lyrics: optional synced-lyrics lines (``{t_ms, duration_ms, text}``,
      from ``story["lyrics"]``) embedded as a "Lyrics" timing track,
      alongside Beats/Bars/Sections/Chords.
    - words / phonemes: optional WhisperX-aligned marks (``{label,
      start_ms, end_ms}``). When both are present, "Lyrics" becomes a
      3-layer timing track (phrases / words / phonemes — xLights' native
      lyric-track shape). Faces placements reference the track
      ("Lyrics"); the matrix Text effect references its word layer
      ("Lyrics - Words").
    - include_extra_timing: when False, the Chords and per-stem
      Onsets (...) timing tracks are omitted from the output (they are
      display-only — no placed effect references them by name). Beats,
      Bars, Sections, and Lyrics are always written.
    """
    # Warn if audio is outside the mounted show directory (devcontainer-specific).
    # The XSQ will still be written, but xLights on the host won't find the audio.
    if audio_path is not None:
        from src.paths import PathContext as _PathContext
        _pc = _PathContext()
        if _pc.in_container and not _pc.is_in_show_dir(str(audio_path)):
            import warnings as _warnings
            _warnings.warn(
                f"Audio file '{audio_path}' is outside the mounted show directory "
                f"({_pc.container_show_dir}). xLights on the host may not find the "
                f"audio. Copy the file into the show directory for reliable playback.",
                UserWarning,
                stacklevel=2,
            )

    # Collect all placements across sections
    unordered: dict[str, list[EffectPlacement]] = {}
    for section in plan.sections:
        for group_name, placements in section.group_effects.items():
            unordered.setdefault(group_name, []).extend(placements)

    # Song-scoped vocal placements (Faces / lyric Text) live on the plan, not
    # on section assignments, so they survive a 0-section analysis (bug-159).
    for group_name, placements in plan.vocal_effects.items():
        unordered.setdefault(group_name, []).extend(placements)

    # Song-scoped rare crash/transient accents (Shockwave on
    # 01_BASE_All_FADES) — same rationale as vocal_effects.
    for group_name, placements in plan.crash_effects.items():
        unordered.setdefault(group_name, []).extend(placements)

    # Song-scoped Pictures placements (image library entries cycling on
    # Matrix/Mega Tree props) — same rationale as vocal_effects. Filenames
    # hold absolute paths into the container-local image library
    # (~/.xlight/library/images/), unusable by xLights on the host — copied
    # next to output_path and rewritten to a bare filename, same treatment
    # as plan.video_effects below. Multiple placements commonly reference
    # the same library file (e.g. every 20s segment of one prop's rotation
    # before it cycles to the next image), so each source is only copied once.
    #
    # The stored filename is `<id>_<original>` (id prefix added purely to
    # avoid collisions inside the library folder, see image_catalog.py) — the
    # exported name should be the original upload name so users recognize it
    # in xLights, falling back to the id-prefixed name only if two different
    # library entries in this song share the same original filename.
    _original_filenames = {
        e["stored_path"]: e["filename"]
        for e in load_image_library()
        if e.get("stored_path") and e.get("filename")
    }
    _copied_pictures: dict[str, str] = {}
    _used_dest_names: set[str] = set()
    for group_name, placements in plan.picture_effects.items():
        unordered.setdefault(group_name, []).extend(placements)
        for placement in placements:
            src = placement.parameters.get("E_TEXTCTRL_Pictures_Filename")
            if not src:
                continue
            if src in _copied_pictures:
                placement.parameters["E_TEXTCTRL_Pictures_Filename"] = _copied_pictures[src]
                continue
            src_path = Path(src)
            dest_name = _original_filenames.get(src, src_path.name)
            if dest_name in _used_dest_names:
                dest_name = src_path.name
            dest = output_path.parent / dest_name
            if dest.exists():
                logger.info(
                    "picture_effect: '%s' already present at '%s' — skipping copy",
                    dest_name, dest,
                )
            elif src_path.exists():
                import shutil
                shutil.copy2(src_path, dest)
                logger.info("picture_effect: copied '%s' -> '%s'", src_path, dest)
            else:
                logger.warning(
                    "picture_effect: source '%s' does not exist — xLights won't "
                    "find '%s'", src_path, dest_name,
                )
            _used_dest_names.add(dest_name)
            _copied_pictures[src] = dest_name
            placement.parameters["E_TEXTCTRL_Pictures_Filename"] = dest_name

    # Song-scoped Moving Head color-wash placements (DMX fixture groups) --
    # same rationale as vocal_effects.
    for group_name, placements in plan.moving_head_effects.items():
        unordered.setdefault(group_name, []).extend(placements)

    # Song-scoped Video placement (imported video clip on a matrix). Its
    # E_FILEPICKERCTRL_Video_Filename holds an absolute path into
    # ~/.xlight/library/ — a devcontainer-only location with no host
    # equivalent, so the raw path is unusable by xLights on the host.
    # Copied next to output_path and rewritten to a bare filename, exactly
    # like mediaFile — done here, before EffectDB strings are built below,
    # so the serialized entry carries the rewritten path. The caller is
    # responsible for delivering output_path's sibling files (e.g. zipping
    # them together for download) when output_path is a throwaway temp dir.
    for group_name, placements in plan.video_effects.items():
        unordered.setdefault(group_name, []).extend(placements)
        for placement in placements:
            src = placement.parameters.get("E_FILEPICKERCTRL_Video_Filename")
            if not src:
                continue
            src_path = Path(src)
            dest = output_path.parent / src_path.name
            if dest.exists():
                logger.info(
                    "video_effect: '%s' already present at '%s' — skipping copy",
                    src_path.name, dest,
                )
            elif src_path.exists():
                import shutil
                shutil.copy2(src_path, dest)
                logger.info("video_effect: copied '%s' -> '%s'", src_path, dest)
            else:
                logger.warning(
                    "video_effect: source '%s' does not exist — xLights won't "
                    "find '%s'", src_path, src_path.name,
                )
            placement.parameters["E_FILEPICKERCTRL_Video_Filename"] = src_path.name

    # Sort groups by tier prefix so BASE (01) renders behind HERO (08).
    # Groups without a 2-digit tier prefix sort last.
    #
    # 01_BASE_All / 01_BASE_All_FADES are whole-house *override* canvases
    # (not ordinary tier-1 base wash groups): the mined corpus consistently
    # names their equivalents "All (Put on bottom for GLOBAL EFFECTS)" /
    # "All (put on bottom for FADES)" and places them at the END of the
    # DisplayElements/ElementEffects list, after every other model/group —
    # not with the rest of tier 01. They sort last here to match.
    def _tier_sort_key(name: str) -> tuple[int, str]:
        if name in ("01_BASE_All", "01_BASE_All_FADES"):
            return (100, name)
        if len(name) >= 2 and name[:2].isdigit():
            return (int(name[:2]), name)
        return (99, name)

    def _buffer_style_for_group(name: str) -> str | None:
        """Return the B_CHOICE_BufferStyle xLights should apply for a group,
        or None when tier convention leaves it unset (tiers 01-03, other
        than the 01_BASE_All(_FADES) override canvases).

        xLights derives an effect's actually-applied buffer style from each
        EFFECT's own settings string (the EffectDB entry _serialize_effect_params
        builds), not from EffectLayer's separate "settings" attribute -- an
        effect with no B_CHOICE_BufferStyle key falls back to "Default"
        regardless of what the layer says. Must be folded into every
        placement's own params, not set once at the layer level.
        """
        if name in ("01_BASE_All", "01_BASE_All_FADES"):
            return "Default"
        tier_num = int(name[:2]) if len(name) >= 2 and name[:2].isdigit() else 0
        if tier_num >= 4:
            return "Per Model Default"
        return None

    # Strobe and Marquee render as a per-model effect even on the whole-house
    # ALL canvases, where every other effect uses the group's unified "Default"
    # buffer style -- those two look wrong stretched across the group's
    # bounding box (Strobe flattens to a single flash, Marquee's scrolling
    # marquee reads as one prop instead of many).
    _ALL_GROUP_PER_MODEL_EFFECTS = {"Strobe", "Marquee"}

    # The "...Per Preview" variant of whichever tier-based style would
    # otherwise apply (user request, 2026-07-18) -- preserves the
    # underlying Default-vs-Per-Model-Default semantics per tier, just
    # adds the per-preview qualifier. Bug found same day: individual
    # model-targeted placements (e.g. "Snowflake Prop", "Spinner Prop" --
    # type="model" in DisplayElements, not routed through any
    # tier-prefixed group) get base=None from _buffer_style_for_group
    # since there's no tier convention to read, and the fixed two-entry
    # map left those with no override at all (rendered as unset/"Default"
    # on import). A single-model target is inherently "per model"
    # already, so the .get() fallback below treats any other base (None
    # included) as "Per Model Per Preview" too.
    _PREVIEW_VARIANT = {
        "Default": "Per Preview",
        "Per Model Default": "Per Model Per Preview",
    }
    # Every effect on the four BEAT groups gets the preview variant too
    # (user request, 2026-07-18), not just Shockwave -- these are tier 4
    # (base="Per Model Default"), so in practice this always resolves to
    # "Per Model Per Preview", but goes through the same base-driven
    # mapping as Shockwave rather than a hardcoded string, in case a
    # future tier convention change ever puts BEAT groups on "Default".
    _ALWAYS_PREVIEW_GROUPS = {"04_BEAT_1", "04_BEAT_2", "04_BEAT_3", "04_BEAT_4"}

    def _buffer_style_for_placement(group_name: str, effect_name: str) -> str | None:
        if group_name in ("01_BASE_All", "01_BASE_All_FADES") and effect_name in _ALL_GROUP_PER_MODEL_EFFECTS:
            base = "Per Model Default"
        else:
            base = _buffer_style_for_group(group_name)
        if effect_name == "Shockwave" or group_name in _ALWAYS_PREVIEW_GROUPS:
            return _PREVIEW_VARIANT.get(base, "Per Model Per Preview")
        return base

    all_placements: dict[str, list[EffectPlacement]] = {
        k: unordered[k] for k in sorted(unordered, key=_tier_sort_key)
    }

    # Remove overlaps per layer: effects on different layers can legitimately overlap
    # (accent layer 1 is meant to play simultaneously over base layer 0).
    for group_name in all_placements:
        all_placements[group_name] = _remove_overlaps_per_layer(all_placements[group_name])

    # Build deduplication indexes and cache serialized strings per placement
    palette_index: dict[str, int] = {}
    palette_list: list[str] = []
    effect_db_index: dict[str, int] = {}
    effect_db_list: list[str] = []
    placement_cache: dict[int, tuple[int, int]] = {}  # id(p) -> (effect_ref, palette_ref)

    for group_name, placements in all_placements.items():
        for p in placements:
            buffer_style = _buffer_style_for_placement(group_name, p.effect_name)
            pal_idx = _ensure_palette(p.color_palette, palette_index, palette_list, p.music_sparkles)
            eff_idx = _ensure_effect_entry(p, effect_db_index, effect_db_list, buffer_style)
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
    ET.SubElement(head, "author").text = "xOnset"
    ET.SubElement(head, "song").text = plan.song_profile.title
    ET.SubElement(head, "artist").text = plan.song_profile.artist
    # Write media path and ensure the MP3 is alongside the XSQ.
    # mediaFile stores only the filename (basename), not an absolute path, so the
    # XSQ resolves the audio relative to its own location. This makes sequences
    # portable across devcontainer and host environments without path translation.
    if audio_path is not None:
        dest = output_path.parent / audio_path.name
        if not dest.exists() and audio_path.exists():
            import shutil
            shutil.copy2(audio_path, dest)
        ET.SubElement(head, "mediaFile").text = audio_path.name
    else:
        ET.SubElement(head, "mediaFile").text = plan.song_profile.title + ".mp3"
    ET.SubElement(head, "sequenceType").text = "Media"
    ET.SubElement(head, "sequenceTiming").text = f"{FRAME_INTERVAL_MS} ms"
    # Use scoped_duration_ms when provided (spec 049: section preview window).
    # Fall back to the full song duration for normal renders.
    effective_duration_ms = scoped_duration_ms if scoped_duration_ms is not None else plan.song_profile.duration_ms
    duration_sec = effective_duration_ms / 1000.0
    ET.SubElement(head, "sequenceDuration").text = f"{duration_sec:.3f}"
    # Emit <mediaOffset> for section preview so xLights starts audio playback
    # at the correct offset into the original MP3 (xLights 2024+ feature).
    if audio_offset_ms is not None:
        ET.SubElement(head, "mediaOffset").text = str(audio_offset_ms)

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
            # 01_BASE_All(_FADES) are real xLights modelGroups (written by
            # src/grouper/writer.py), not individual models -- mislabeling
            # them "model" makes xLights apply per-model buffer-style
            # semantics regardless of our B_CHOICE_BufferStyle=Default
            # setting below. Every other group name keeps "model" as-is.
            elem.set(
                "type",
                "modelGroup" if group_name in ("01_BASE_All", "01_BASE_All_FADES") else "model",
            )
            elem.set("name", group_name)
            elem.set("visible", "1")
            elem.set("collapsed", "0")
            elem.set("active", "1")
            displayed_models.add(group_name)

    # Lyric layers: xLights consumes lyrics as ONE timing track with three
    # EffectLayers — phrases, words, phonemes. The Faces effect reads the
    # phoneme layer via E_CHOICE_Faces_TimingTrack=Lyrics; the Text effect
    # reads the word layer via E_CHOICE_Text_LyricTrack="Lyrics - Words".
    # When word/phoneme marks are absent, "Lyrics" stays a plain single-layer
    # line track (pre-singing-faces behavior).
    lyric_layers = _build_lyric_layers(lyrics, words, phonemes)

    # Add timing track display elements
    timing_tracks = (_collect_timing_tracks(hierarchy, None if lyric_layers else lyrics,
                                            include_extra_timing=include_extra_timing)
                     if (hierarchy or lyrics) else {})
    timing_names = list(timing_tracks)
    if lyric_layers:
        timing_names.append("Lyrics")
    for track_name in timing_names:
        elem = ET.SubElement(display_el, "Element")
        elem.set("type", "timing")
        elem.set("name", track_name)
        elem.set("visible", "0" if track_name.startswith("Onsets") else "1")
        elem.set("collapsed", "0")
        elem.set("active", "1" if track_name == "Beats" else "0")

    # <ElementEffects>
    effects_el = ET.SubElement(root, "ElementEffects")
    for group_name, placements in all_placements.items():
        model_el = ET.SubElement(effects_el, "Element")
        model_el.set(
            "type",
            "modelGroup" if group_name in ("01_BASE_All", "01_BASE_All_FADES") else "model",
        )
        model_el.set("name", group_name)

        # Group placements by layer index.  Layer 0 = primary effect; layer 1+ = accent overlays.
        layers_map: dict[int, list] = {}
        for p in placements:
            layers_map.setdefault(getattr(p, "layer", 0), []).append(p)

        # 01_BASE_All is a whole-house wash group — render as a single unified canvas.
        # Tiers 4+ (BEAT / PROP / COMPOUND / HERO) use "Per Model Default" so each
        # individual prop in the group renders the effect on its own pixel layout rather
        # than across the group's bounding box.  Lower tiers (01–03) render as a unified
        # group. The value that actually takes effect in xLights is folded into each
        # effect's own EffectDB entry (see _buffer_style_for_group / _serialize_effect_params);
        # this layer-level attribute is set alongside it for the layer's own display default.
        group_buffer_style = _buffer_style_for_group(group_name)

        for layer_idx in sorted(layers_map.keys()):
            layer_el = ET.SubElement(model_el, "EffectLayer")
            if group_buffer_style is not None:
                layer_el.set("settings", f"B_CHOICE_BufferStyle={group_buffer_style}")
            for p in sorted(layers_map[layer_idx], key=lambda p: p.start_ms):
                effect_el = ET.SubElement(layer_el, "Effect")

                ref_idx, palette_idx = placement_cache.get(id(p), (0, 0))

                effect_el.set("ref", str(ref_idx))
                effect_el.set("name", p.effect_name)
                # Apply audio offset shift for section preview (spec 049).
                # We do NOT mutate the EffectPlacement — shift is serialization-only.
                offset = audio_offset_ms if audio_offset_ms is not None else 0
                effect_el.set("startTime", str(p.start_ms - offset))
                effect_el.set("endTime", str(p.end_ms - offset))
                effect_el.set("palette", str(palette_idx))
                effect_el.set("selected", "0")

    # Add timing tracks to ElementEffects
    offset = audio_offset_ms if audio_offset_ms is not None else 0
    for track_name, marks in timing_tracks.items():
        timing_el = ET.SubElement(effects_el, "Element")
        timing_el.set("type", "timing")
        timing_el.set("name", track_name)

        layer_el = ET.SubElement(timing_el, "EffectLayer")
        _emit_timing_layer(layer_el, marks, offset, int(plan.song_profile.duration_ms))

    # Multi-layer "Lyrics" track (phrases / words / phonemes) — see above.
    if lyric_layers:
        timing_el = ET.SubElement(effects_el, "Element")
        timing_el.set("type", "timing")
        timing_el.set("name", "Lyrics")
        for layer_marks in lyric_layers:
            layer_el = ET.SubElement(timing_el, "EffectLayer")
            _emit_timing_layer(layer_el, layer_marks, offset,
                               int(plan.song_profile.duration_ms))

    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="UTF-8", xml_declaration=True)


_DEFAULT_PALETTE_COLORS = [
    "#FF0000", "#00FF00", "#0000FF", "#FFFF00",
    "#000000", "#00FFFF", "#FF00FF", "#FFFFFF",
]


def _serialize_palette(colors: list[str], music_sparkles: int = 0) -> str:
    """Convert a list of hex colors to xLights C_BUTTON_Palette format.

    Always fills all 8 palette slots — theme colors first, then defaults.
    xLights expects C_BUTTON entries grouped before C_CHECKBOX entries.
    Only the slots with theme colors get C_CHECKBOX enabled.
    When music_sparkles > 0, appends C_CHECKBOX_MusicSparkles=1 and
    C_SLIDER_SparkleFrequency={value} -- both are required (bug, 2026-07-15):
    a real xLights palette string with sparkles active always carries the
    checkbox alongside the slider, and without it the slider value alone
    does nothing, so every prior sparkle placement (tier-1 BASE, palette-
    restraint pool effects) rendered with sparkles silently off.
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
    parts = buttons + checkboxes
    if music_sparkles > 0:
        parts.append("C_CHECKBOX_MusicSparkles=1")
        parts.append(f"C_SLIDER_SparkleFrequency={music_sparkles}")
    return ",".join(parts)


def _serialize_effect_params(
    placement: EffectPlacement, buffer_style: str | None = None,
) -> str:
    """Serialize effect parameters to xLights comma-separated format.

    Merges xLights defaults for the effect so all required params are present.
    Theme/user overrides take precedence over defaults. ``buffer_style``, when
    given, is folded in as B_CHOICE_BufferStyle -- this is the value xLights
    actually applies (see _buffer_style_for_group); a group-level EffectLayer
    "settings" attribute alone has no effect on rendering.
    """
    # Start with xLights defaults for this effect
    defaults = dict(_XLIGHTS_EFFECT_DEFAULTS.get(placement.effect_name, {}))

    # Override with our explicit parameters
    for key, val in placement.parameters.items():
        if isinstance(val, bool):
            defaults[key] = "1" if val else "0"
        else:
            defaults[key] = str(val)

    if buffer_style is not None:
        defaults["B_CHOICE_BufferStyle"] = buffer_style

    # Add fades -- capped to 25% of the effect's own duration so a fade
    # computed from a section/crossfade-region length (e.g. apply_crossfades,
    # apply_fadeout in transitions.py) never swallows a short placement
    # whole. This is the single point where placement duration and fade
    # values are both available, so it guards every fade producer, present
    # and future (mirrors the B_CHOICE_BufferStyle single-source-of-truth
    # precedent above).
    duration_ms = placement.end_ms - placement.start_ms
    max_fade_ms = duration_ms * 0.25 if duration_ms > 0 else 0
    fade_in_ms = min(placement.fade_in_ms, max_fade_ms)
    fade_out_ms = min(placement.fade_out_ms, max_fade_ms)
    if fade_in_ms > 0:
        defaults["T_TEXTCTRL_Fadein"] = f"{fade_in_ms / 1000:.2f}".rstrip("0").rstrip(".")
    if fade_out_ms > 0:
        defaults["T_TEXTCTRL_Fadeout"] = f"{fade_out_ms / 1000:.2f}".rstrip("0").rstrip(".")

    # Encode value curves inline
    for param_name, curve_data in placement.value_curves.items():
        # param_name is the storage_name (e.g. "E_SLIDER_Wave_YOffset").
        # xLights expects the value-curve key without the widget-type prefix:
        # "E_VALUECURVE_Wave_YOffset", not "E_VALUECURVE_E_SLIDER_Wave_YOffset".
        short = _strip_storage_prefix(param_name)
        # curve_data is either (points, min, max) or legacy list of points
        if isinstance(curve_data, tuple) and len(curve_data) == 3:
            points, p_min, p_max = curve_data
        else:
            points = curve_data
            p_min, p_max = 0.0, 100.0
        defaults[f"E_VALUECURVE_{short}"] = _encode_value_curve(short, points, p_min, p_max)

    # Rule (user request, 2026-07-18): never emit T_CHECKBOX_Canvas, on any
    # effect, regardless of whether a mined vendor .xsqz template includes
    # it. Enforced here rather than just omitted from
    # _XLIGHTS_EFFECT_DEFAULTS/moving_head._build_parameters so it can't
    # come back in via a placement's own parameters, a future template
    # mining pass, or any other producer.
    defaults.pop("T_CHECKBOX_Canvas", None)

    parts = [f"{k}={v}" for k, v in sorted(defaults.items())]
    return ",".join(parts)


def _strip_storage_prefix(storage_name: str) -> str:
    """Strip widget-type prefix from a storage_name to get the bare parameter name.

    xLights value curve keys use the bare name: "E_VALUECURVE_Wave_YOffset",
    not "E_VALUECURVE_E_SLIDER_Wave_YOffset".
    """
    for prefix in ("E_SLIDER_", "E_TEXTCTRL_", "E_CHECKBOX_", "E_CHOICE_", "E_NOTEBOOK_"):
        if storage_name.startswith(prefix):
            return storage_name[len(prefix):]
    return storage_name


def _encode_value_curve(
    short_name: str,
    points: list[tuple[float, float]],
    p_min: float = 0.0,
    p_max: float = 100.0,
) -> str:
    """Encode a value curve in xLights inline format.

    ``p_min``/``p_max`` are the parameter's actual slider range (e.g. -250/250
    for Wave_YOffset).  xLights uses these to interpret the curve values.
    ``RV=TRUE`` tells xLights the values are real (not 0-100 percentages).
    """
    # xLights stores custom value curve points as (x, y) where y is normalized
    # to 0.0-1.0 representing the fraction of the Min-Max range.
    # e.g. Min=-250, Max=250: y=0.50 means 0 (center), y=0.85 means 175.
    p_range = p_max - p_min if p_max != p_min else 1.0
    values_str = ";".join(
        f"{x:.2f}:{max(0.0, min(1.0, (y - p_min) / p_range)):.2f}"
        for x, y in points
    )
    return (
        f"Active=TRUE|Id=ID_VALUECURVE_{short_name}|Type=Custom"
        f"|Min={p_min:.2f}|Max={p_max:.2f}|RV=TRUE|Values={values_str}|"
    )


def _ensure_palette(
    colors: list[str],
    index: dict[str, int],
    palette_list: list[str],
    music_sparkles: int = 0,
) -> int:
    """Add palette to dedup index if not already present. Return index."""
    key = _serialize_palette(colors, music_sparkles)
    if key not in index:
        index[key] = len(palette_list)
        palette_list.append(key)
    return index[key]


def _ensure_effect_entry(
    placement: EffectPlacement,
    index: dict[str, int],
    effect_list: list[str],
    buffer_style: str | None = None,
) -> int:
    """Add effect params to dedup index if not already present. Return index.

    Moving Head effects are exempt from dedup -- always get their own fresh
    EffectDB entry, never shared with another placement even when the
    serialized content is byte-identical. Every other effect type shares
    entries safely; Moving Head placements from this module are always
    built as immediately-adjacent warmup+punch pairs (warmup's endTime ==
    punch's startTime, zero gap), and a real xLights round-trip test
    (2026-07-17) showed clicking one such effect in the UI can corrupt a
    *different* placement's content on save -- confirmed via a real
    before/after file diff where a silent warmup pose got replaced with an
    unrelated punch's Wheel/Shutter/Dimmer content from elsewhere in the
    timeline, for placements the user never directly touched. Two
    placements sharing one EffectDB entry gives xLights' editor a path to
    conflate them; a dedicated entry per placement removes that path
    entirely, regardless of the exact internal xLights mechanism.
    """
    key = _serialize_effect_params(placement, buffer_style)
    if placement.effect_name == "Moving Head":
        effect_list.append(key)
        return len(effect_list) - 1
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


def _remove_overlaps_per_layer(placements: list[EffectPlacement]) -> list[EffectPlacement]:
    """Run overlap removal independently per layer and reassemble.

    Accent effects (layer 1) are designed to overlap base effects (layer 0) in
    time — that is the whole point of layering.  Merging them before dedup would
    incorrectly trim or drop accent placements that share a time range with a
    longer base effect.
    """
    from collections import defaultdict
    by_layer: dict[int, list[EffectPlacement]] = defaultdict(list)
    for p in placements:
        by_layer[getattr(p, "layer", 0)].append(p)
    result: list[EffectPlacement] = []
    for layer_placements in by_layer.values():
        result.extend(_remove_overlaps(layer_placements))
    return result


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


def _emit_timing_layer(
    layer_el: ET.Element,
    marks: list[TimingMark],
    offset: int,
    song_duration_ms: int,
) -> None:
    """Write one timing EffectLayer's <Effect> children from marks.

    Marks carrying an explicit duration (lyric lines, words, phonemes) end at
    start+duration — a word must not stretch across the silence to the next
    word. Duration-less marks (beats, bars, sections) span to the next mark.
    """
    for i, mark in enumerate(marks):
        raw_start = mark.time_ms
        if mark.duration_ms:
            raw_end = raw_start + mark.duration_ms
            if i + 1 < len(marks):
                raw_end = min(raw_end, marks[i + 1].time_ms)
        else:
            raw_end = marks[i + 1].time_ms if i + 1 < len(marks) else song_duration_ms
        # Apply audio offset shift for section preview (serialization-only)
        start = raw_start - offset
        end = raw_end - offset
        if end <= start:
            continue
        effect_el = ET.SubElement(layer_el, "Effect")
        effect_el.set("label", mark.label or "")
        effect_el.set("startTime", str(start))
        effect_el.set("endTime", str(end))


def _build_lyric_layers(
    lyrics: list[dict] | None,
    words: list[dict] | None,
    phonemes: list[dict] | None,
) -> list[list[TimingMark]]:
    """Build the 3-layer xLights lyric track: [phrases, words, phonemes].

    Returns [] unless BOTH word and phoneme marks are present — a plain line
    track stays single-layer (handled by _collect_timing_tracks), and the
    layer positions are fixed by xLights convention (1=phrases, 2=words,
    3=phonemes), so partial data must not shift layers.

    When no lyric lines exist (free transcription), the phrase layer holds
    unlabeled spans covering each contiguous word run so words/phonemes stay
    on layers 2 and 3.
    """
    if not (words and phonemes):
        return []

    def _label_marks(marks: list[dict]) -> list[TimingMark]:
        return [
            TimingMark(time_ms=m["start_ms"], confidence=None, label=m["label"],
                       duration_ms=max(1, int(m["end_ms"]) - int(m["start_ms"])))
            for m in marks
        ]

    word_marks = _label_marks(words)
    phoneme_marks = _label_marks(phonemes)

    if lyrics:
        phrase_marks = [
            TimingMark(time_ms=line["t_ms"], confidence=None,
                       label=line["text"], duration_ms=line["duration_ms"])
            for line in lyrics
        ]
    else:
        # Merge words into contiguous spans (gap >= 5s splits) as unlabeled phrases.
        phrase_marks = []
        for wm in sorted(word_marks, key=lambda m: m.time_ms):
            end = wm.time_ms + (wm.duration_ms or 0)
            if phrase_marks and wm.time_ms - (phrase_marks[-1].time_ms + phrase_marks[-1].duration_ms) < 5000:
                prev = phrase_marks[-1]
                prev.duration_ms = max(prev.duration_ms, end - prev.time_ms)
            else:
                phrase_marks.append(TimingMark(time_ms=wm.time_ms, confidence=None,
                                                label="", duration_ms=end - wm.time_ms))

    return [phrase_marks, word_marks, phoneme_marks]


def _collect_timing_tracks(
    hierarchy: HierarchyResult | None,
    lyrics: list[dict] | None = None,
    include_extra_timing: bool = True,
) -> dict[str, list[TimingMark]]:
    """Collect single-layer timing tracks from hierarchy (+ optional lyric lines)."""
    tracks: dict[str, list[TimingMark]] = {}

    if hierarchy is not None:
        if hierarchy.beats and hierarchy.beats.marks:
            tracks["Beats"] = hierarchy.beats.marks

        if hierarchy.bars and hierarchy.bars.marks:
            tracks["Bars"] = hierarchy.bars.marks

        if hierarchy.sections:
            tracks["Sections"] = hierarchy.sections

        if include_extra_timing:
            if hierarchy.chords and hierarchy.chords.marks:
                tracks["Chords"] = hierarchy.chords.marks

            # Emit one timing track per stem with onsets.  Stem-aware trigger
            # placement (drum Shockwaves, vocal accents, bass pulses) routes to
            # its matching Onsets (<stem>) track, so every stem with marks must
            # be emitted — not only the first one.
            for stem_name, track in hierarchy.events.items():
                if track.marks:
                    tracks[f"Onsets ({stem_name})"] = track.marks

            # Per-instrument drum hits, split from the classified "drums"
            # onset track (see src/analyzer/drum_classifier.py) — previously
            # only visible in the standalone analyzer .xtiming export, never
            # in the generated .xsq itself.
            if hierarchy.kick_hits:
                tracks["Kick Hits"] = hierarchy.kick_hits
            if hierarchy.snare_hits:
                tracks["Snare Hits"] = hierarchy.snare_hits
            if hierarchy.hihat_hits:
                tracks["Hihat Hits"] = hierarchy.hihat_hits

    if lyrics:
        tracks["Lyrics"] = [
            TimingMark(time_ms=line["t_ms"], confidence=None,
                       label=line["text"], duration_ms=line["duration_ms"])
            for line in lyrics
        ]

    return tracks


def fseq_guidance(output_path: Path) -> str:
    """Return FSEQ rendering guidance message."""
    return (
        f"\nTo render FSEQ: Open {output_path} in xLights → "
        "Tools → Batch Render (F9) → File → Export Sequence → FSEQ\n"
    )
