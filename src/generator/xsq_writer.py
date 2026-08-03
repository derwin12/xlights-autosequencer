"""XSQ writer — serializes a SequencePlan to xLights .xsq XML format."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.generator.effect_placer import _WHOLE_HOUSE_HIGH_ENERGY_GATE, _WHOLE_HOUSE_LOW_ENERGY_GATE
from src.generator.image_catalog import load_image_library
from src.generator.models import EffectPlacement, SequencePlan, XsqDocument, FRAME_INTERVAL_MS

logger = logging.getLogger(__name__)

# Pinwheel speed-by-energy buckets (user request, 2026-08-03: "tailor the
# speed of the pinwheel based on the tempo or speed of the music... at 13s
# the song seems slow so the speed should be slow"). This codebase only
# tracks a single song-wide estimated_bpm, not a per-section/local tempo
# curve, so per-section energy_score (already computed for every section and
# already used to gate whole-house Shader bucket selection, same
# LOW/HIGH thresholds) is used as the available proxy for "feels slow/fast".
# Values chosen to track the mined Pinwheel variant library's own
# speed_feel-tagged Speed values (src/variants/builtins/Pinwheel.json:
# slow ~1-10, moderate ~15-20).
_PINWHEEL_SPEED_LOW_ENERGY = 6
_PINWHEEL_SPEED_MEDIUM_ENERGY = 13
_PINWHEEL_SPEED_HIGH_ENERGY = 22

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
        "E_TEXTCTRL_Shimmer_Cycles": "0.4",
    },
    "Strobe": {
        "E_CHECKBOX_Strobe_Music": "1",
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
        "E_SLIDER_Pinwheel_Thickness": "5",
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
        # Was "E_SLIDER_Number_Waves" -- not a real xLights key (confirmed
        # against a real xLights clipboard paste, 2026-07-23); the actual
        # parameter is a textctrl, not a slider, so this default silently
        # never applied and Wave always rendered at xLights' own UI
        # default instead.
        "E_TEXTCTRL_Number_Waves": "1.00",
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
        "C_SLIDER_Brightness": "200",
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
    vocal_diarization: bool = False,
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
    - vocal_diarization: when True and ``words`` carries WhisperX marks
      tagged ``speaker`` (0=lead, 1=featured/backup — see
      ``src.analyzer.vocal_diarization``) with a confidently-detected
      second voice, a second 3-layer "Lyrics - Backup" timing track is
      written from the speaker-1 words/phonemes, and the primary "Lyrics"
      track carries only speaker-0 words/phonemes. Phonemes (which have no
      speaker tag of their own) inherit the speaker of whichever word's
      time span contains them. Degrades to the original single-track
      behavior when off, or when no speaker-1 words are present.
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

    # start_ms/end_ms/energy_score per section, for the Pinwheel speed-by-
    # energy lookup below. Built once here (not per-placement) since this is
    # the same list regardless of which producer created a given placement —
    # covers song-scoped placements (e.g. star-burst Pinwheel) too, not just
    # per-section ones, by looking up whichever section's time range a
    # placement's own start_ms falls within.
    section_energy_ranges = [
        (a.section.start_ms, a.section.end_ms, a.section.energy_score) for a in plan.sections
    ]

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

    # Song-scoped Shadow Text placements (two-layer word-in-shadow Text
    # effect on user-tagged words) -- same rationale as vocal_effects. No
    # file copying needed, unlike Pictures above: E_TEXTCTRL_Text carries
    # the literal word, not a filesystem path.
    for group_name, placements in plan.shadow_text_effects.items():
        unordered.setdefault(group_name, []).extend(placements)

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

    # A matrix that received both a Video import and a Shader substitution
    # (effect_placer.py's matrix-fallback rotation, user request 2026-07-20)
    # would otherwise both default to layer 0 -- _remove_overlaps_per_layer
    # below only exempts DIFFERENT layers from its same-layer trim, so two
    # full-section effects sharing layer 0 get silently cut into fragments
    # around each other. Push Shader onto a layer strictly behind Video's so
    # the video always reads as the dominant foreground content and the
    # shader is a background wash. Per EffectPlacement.layer's docstring
    # (bug-248, confirmed specifically on a matrix prop): LOWER layer
    # numbers render in FRONT here, opposite of the usual "higher = on top"
    # intuition -- Shader must go to a HIGHER number, not layer 0.
    for group_name, placements in unordered.items():
        video_placements = [p for p in placements if p.effect_name == "Video"]
        shader_placements = [p for p in placements if p.effect_name == "Shader"]
        if not (video_placements and shader_placements):
            continue
        max_video_layer = max(p.layer for p in video_placements)
        for p in shader_placements:
            p.layer = max(p.layer, max_video_layer + 1)

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

    def _buffer_style_for_placement(group_name: str, effect_name: str, override: str | None) -> str | None:
        # A placement-level override (e.g. the snowflake Single Strand
        # render-style rotation) takes precedence over tier convention --
        # it names an explicit mined/requested style, not a fallback default.
        if override is not None:
            return override
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
            buffer_style = _buffer_style_for_placement(group_name, p.effect_name, p.buffer_style_override)
            hue_adjust = None
            if p.effect_name == "Shader":
                ifs = str(p.parameters.get("E_0FILEPICKERCTRL_IFS", ""))
                baseline_hue = next(
                    (deg for suffix, deg in _HUE_RESPONSIVE_SHADER_BASELINES.items()
                     if ifs.endswith(suffix)),
                    None,
                )
                if baseline_hue is not None:
                    dominant_hue = _dominant_hue_degrees(p.color_palette)
                    if dominant_hue is not None:
                        hue_adjust = _shader_hue_adjust_for_hue(dominant_hue, baseline_hue)
            pal_idx = _ensure_palette(
                p.color_palette, palette_index, palette_list, p.music_sparkles, hue_adjust,
                p.sparkle_color,
            )
            energy_score = _energy_score_at_ms(p.start_ms, section_energy_ranges)
            eff_idx = _ensure_effect_entry(
                p, effect_db_index, effect_db_list, buffer_style, energy_score,
            )
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
    #
    # When vocal_diarization detected a confident second voice (speaker=1),
    # split into a second "Lyrics - Backup" 3-layer track instead of one
    # combined track — see _place_singing_faces/_place_lyric_text in
    # effect_placer.py for the matching Faces/Text placement split.
    backup_words: list[dict] = []
    backup_phonemes: list[dict] = []
    if vocal_diarization and words and phonemes:
        phonemes_with_speaker = _attribute_phoneme_speakers(phonemes, words)
        lead_words = [w for w in words if w.get("speaker", 0) == 0]
        backup_words = [w for w in words if w.get("speaker", 0) == 1]
        lead_phonemes = [p for p in phonemes_with_speaker if p["speaker"] == 0]
        backup_phonemes = [p for p in phonemes_with_speaker if p["speaker"] == 1]
        if backup_words and backup_phonemes:
            words, phonemes = lead_words, lead_phonemes
        else:
            backup_words, backup_phonemes = [], []

    lyric_layers = _build_lyric_layers(lyrics, words, phonemes)
    backup_lyric_layers = (
        _build_lyric_layers(None, backup_words, backup_phonemes)
        if backup_words else []
    )

    # Add timing track display elements. "Sections" uses the classified
    # section roles (verse/chorus/bridge/...) instead of the raw segmentino/
    # QM-segmenter labels (letters, N#, "qm_boundary") when available (user
    # request 2026-07-21) -- see _section_role_marks. "Themes" shows which
    # theme each section was assigned (user request 2026-07-28) -- see
    # _section_theme_marks.
    section_role_marks = _section_role_marks(plan) if plan.sections else None
    section_theme_marks = _section_theme_marks(plan) if plan.sections else None
    timing_tracks = (_collect_timing_tracks(hierarchy, None if lyric_layers else lyrics,
                                            include_extra_timing=include_extra_timing,
                                            section_role_marks=section_role_marks,
                                            force_include=_referenced_timing_track_names(all_placements),
                                            section_theme_marks=section_theme_marks)
                     if (hierarchy or lyrics or section_role_marks or section_theme_marks) else {})
    timing_names = list(timing_tracks)
    if lyric_layers:
        timing_names.append("Lyrics")
    if backup_lyric_layers:
        timing_names.append("Lyrics - Backup")
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

    # Second "Lyrics - Backup" track for a diarized featured/backup singer.
    if backup_lyric_layers:
        timing_el = ET.SubElement(effects_el, "Element")
        timing_el.set("type", "timing")
        timing_el.set("name", "Lyrics - Backup")
        for layer_marks in backup_lyric_layers:
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

# Hard ceiling on C_SLIDER_SparkleFrequency (user request, 2026-07-28):
# applies to every sparkle value regardless of which upstream formula
# produced it or whether MusicSparkles came from a corpus recipe's
# mask_sparkles, the tier-1/_ALWAYS_SPARKLE_EFFECTS unconditional pass, or
# the palette-restraint probabilistic roll -- upstream formulas already
# produce values well above this (15-65), so every real placement gets
# clamped down to this ceiling. Raised from 10 to 20 the same day after a
# 392-song reference-corpus scan: real vendor sequences use 0-200 (median
# 50), but the user specifically liked how the sub-10 clamp looked and,
# after inspecting a real 20-valued reference example (Carol of the
# Bells), settled on 20 as the ceiling.
_SPARKLE_FREQUENCY_MAX = 20


def _serialize_palette(
    colors: list[str], music_sparkles: int = 0, hue_adjust: int | None = None,
    sparkle_color: str | None = None,
) -> str:
    """Convert a list of hex colors to xLights C_BUTTON_Palette format.

    Always fills all 8 palette slots — theme colors first, then defaults.
    xLights expects C_BUTTON entries grouped before C_CHECKBOX entries.
    Only the slots with theme colors get C_CHECKBOX enabled.
    When music_sparkles > 0, appends C_CHECKBOX_MusicSparkles=1 and
    C_SLIDER_SparkleFrequency={value} -- both are required (bug, 2026-07-15):
    a real xLights palette string with sparkles active always carries the
    checkbox alongside the slider, and without it the slider value alone
    does nothing, so every prior sparkle placement (tier-1 BASE, palette-
    restraint pool effects) rendered with sparkles silently off. The slider
    value itself is capped at ``_SPARKLE_FREQUENCY_MAX`` (user request,
    2026-07-28) regardless of which upstream formula computed it (mask_
    sparkles' energy-scaled value, compute_music_sparkles' palette-restraint
    roll, etc.) -- clamped here, the single point every sparkle value passes
    through before serialization, rather than in each caller.
    ``sparkle_color``, when given alongside music_sparkles > 0, appends
    C_COLOURPICKERCTRL_SparklesColour -- a real xLights clipboard sample
    (user-supplied, 2026-07-28) showed sparkles rendering in a distinct
    color from the base palette (red sparkles over a blue Bars effect) via
    this dedicated field, not by flashing the base palette color itself.
    ``hue_adjust``, when given, appends C_SLIDER_Color_HueAdjust -- the
    generic Color-tab hue-rotation slider (see _shader_hue_adjust_for_hue).
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
        parts.append(f"C_SLIDER_SparkleFrequency={min(music_sparkles, _SPARKLE_FREQUENCY_MAX)}")
        if sparkle_color is not None:
            parts.append(f"C_COLOURPICKERCTRL_SparklesColour={sparkle_color}")
    if hue_adjust is not None:
        parts.append(f"C_SLIDER_Color_HueAdjust={hue_adjust}")
    return ",".join(parts)


# A flat/plain Pinwheel (E_CHOICE_Pinwheel_3D="None") reads as dull on real
# hardware (user request, 2026-07-23) -- every Pinwheel placement must pick
# one of these instead. Order matters only in that it's the rotation table
# _serialize_effect_params indexes into. "3D Inverted" excluded entirely
# (user request, 2026-08-03) -- never use it, on top of it never being a
# valid flat-Pinwheel replacement pick.
_PINWHEEL_3D_OPTIONS = ("3D", "Sweep")

# Fire_HueShift calibration (user request, 2026-07-26): xLights' Fire effect
# always renders from a fixed red/orange gradient unless E_SLIDER_Fire_HueShift
# rotates it -- every Fire placement previously left this at its xLights
# default of 0 (or a hardcoded creative value baked into a specific variant,
# e.g. "Fire Medium"'s 79), so Fire never matched a theme's actual color.
# These bands are the user's own real-xLights-tested hue->shift calibration
# table (hue_start, hue_end, shift_at_start, shift_at_end); a hue inside a
# band interpolates linearly across it. The blue band's stated lower bound
# (210deg) is nudged to 220deg here to remove its overlap with cyan's stated
# upper bound (also 220deg) -- both can't hold simultaneously, and 220 is the
# shared edge either table entry would round to anyway. A hue that falls in
# a gap between bands (e.g. 60-90deg, the untabulated red->green transition)
# holds at the nearer band edge rather than inventing a cross-fade the
# table doesn't specify.
_FIRE_HUE_SHIFT_BANDS: list[tuple[float, float, float, float]] = [
    (0.0, 60.0, 0.0, 0.0),      # red-yellow -- normal fire, no shift
    (90.0, 150.0, 25.0, 40.0),  # green
    (160.0, 220.0, 45.0, 50.0), # cyan
    (220.0, 270.0, 58.0, 65.0), # blue
    (270.0, 330.0, 75.0, 85.0), # purple/magenta
]


def _dominant_hue_degrees(colors: list[str]) -> float | None:
    """Return the hue (0-360) of the most saturated color in the list.

    Returns None when no color is saturated enough to carry a meaningful hue
    (all white/gray/near-black) -- callers should leave Fire's hue-shift at
    its existing value in that case rather than snapping to red.
    """
    import colorsys
    best_hue: float | None = None
    best_sat = 0.0
    for color in colors:
        c = color.lstrip("#")
        if len(c) != 6:
            continue
        r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s > best_sat and s >= 0.25 and v >= 0.15:
            best_sat = s
            best_hue = h * 360.0
    return best_hue


def _shader_hue_adjust_for_hue(
    hue_degrees: float, baseline_hue_degrees: float,
) -> int:
    """Map a theme hue to xLights' generic C_SLIDER_Color_HueAdjust (-100-100).

    Live-tested in xLights (user request, 2026-07-26) on the Black Cherry
    Cosmos shader: unlike Fire's own hand-tuned band table, this slider is
    a plain circular HSV hue rotation applied to whatever the effect
    already renders, at ~3.6deg/unit (100 units = 360deg -- v=100 measured
    back to within ~8deg of v=0's own baseline color). ``baseline_hue_degrees``
    is that shader's native (unadjusted) hue -- e.g. Black Cherry Cosmos's own
    hardcoded magenta/crimson measures ~336deg. Returns the shortest-rotation
    value in [-50, 50] (both signs reach every hue once each way around).
    """
    raw = ((hue_degrees - baseline_hue_degrees) % 360.0) / 3.6
    if raw > 50.0:
        raw -= 100.0
    return round(raw)


# Which Shaders/*.fs files actually respond to C_SLIDER_Color_HueAdjust, and
# each one's own baseline (unadjusted, hue_adjust=0) dominant hue in degrees --
# see _shader_hue_adjust_for_hue. Measured via live xLights render_frame /
# render_clip captures (user request, 2026-07-26): rotating this slider only
# visibly changes a shader's output when that shader's own rendered content
# carries real saturation at hue_adjust=0 -- an achromatic (white/gray)
# shader has no hue for the rotation to move, so it looks unchanged
# regardless of the slider value. Confirmed responsive: Black Cherry Cosmos
# (336deg, hardcoded magenta/crimson, no color uniform in its .fs), Plasma
# Emitter (87deg), Continua Variation (247deg), xLights Audio - fractal audio
# (229deg), Creation by Silexars (207deg, a low-saturation glow -- the shift
# is real but subtle), Audio - Audio Surf (245deg), Fly Through (0deg).
# Confirmed NOT responsive (user-verified, 2026-07-26) and deliberately
# excluded here: Electrocardiogram.fs, Hex 3D Spiral.fs (both render
# achromatic white/gray noise regardless of E_CHOICE_SHADERXYZZY_uColMode),
# Warp Vincent'sStorm.fs (warps/distorts whatever base effect layer is
# beneath it rather than carrying its own color, so hue_adjust on the warp
# layer itself has no visible effect -- recolor the base effect underneath
# instead). String Art.fs is additionally excluded from the variant library
# entirely (not just this hue table) -- it crashed live xLights twice in a
# row during testing (both with and without hue_adjust set), so treat it as
# unstable rather than merely achromatic; do not re-add without confirming
# the crash is fixed. Warp Kaleidoscope Tile.fs initially failed two live
# tests (default settings, then a real production CopyFormat string with the
# required E_SLIDER_SHADERXYZZY_* uniforms and T_CHECKBOX_Canvas=1) -- both
# rendered nothing. The actual root cause (user-confirmed, 2026-07-26): the
# base layer underneath had no (or only one) active palette color -- "if no
# colors are chosen the warp shader renders white," and by extension a
# single-color palette renders flat/monochrome the same way. It is NOT about
# the base effect being a smooth wash vs. a textured chase -- Single Strand
# (2 active colors) and Butterfly (3 active colors) both render correctly
# underneath it once given a real multi-color palette; Plasma/Butterfly with
# too few active colors is what actually failed both times. Any base effect
# works as long as it has >=2 (ideally 3) active palette colors -- see
# `_ensure_min_palette_colors` used when auto-pairing this shader with a
# companion base.
_HUE_RESPONSIVE_SHADER_BASELINES: dict[str, float] = {
    "Black Cherry Cosmos.fs": 336.0,
    "Plasma Emitter.fs": 87.0,
    "Continua Variation.fs": 247.0,
    "xLights Audio - fractal audio.fs": 229.0,
    "Creation by Silexars.fs": 207.0,
    "Audio - Audio Surf.fs": 245.0,
    "Fly Through.fs": 0.0,
}


def _fire_hue_shift_for_hue(hue_degrees: float) -> int:
    """Map a theme color's hue to xLights' E_SLIDER_Fire_HueShift (0-100)."""
    h = hue_degrees % 360.0

    for h0, h1, s0, s1 in _FIRE_HUE_SHIFT_BANDS:
        if h0 <= h <= h1:
            frac = (h - h0) / (h1 - h0) if h1 != h0 else 0.0
            return round(s0 + frac * (s1 - s0))

    # Hue falls in an untabulated gap between bands -- hold at whichever
    # band edge is circularly closest rather than inventing a cross-fade.
    best_shift = 0.0
    best_dist = None
    for h0, h1, s0, s1 in _FIRE_HUE_SHIFT_BANDS:
        for edge_h, edge_s in ((h0, s0), (h1, s1)):
            dist = min(abs(h - edge_h), 360.0 - abs(h - edge_h))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_shift = edge_s
    return round(best_shift)


def _energy_score_at_ms(ms: int, section_energy_ranges: list[tuple[int, int, int]]) -> int | None:
    """The energy_score of whichever section's [start_ms, end_ms) range contains ms.

    None when ms falls outside every section (e.g. a song-scoped placement
    starting before the first section or after the last, or a 0-section
    analysis).
    """
    for start_ms, end_ms, energy_score in section_energy_ranges:
        if start_ms <= ms < end_ms:
            return energy_score
    return None


def _serialize_effect_params(
    placement: EffectPlacement, buffer_style: str | None = None, energy_score: int | None = None,
) -> str:
    """Serialize effect parameters to xLights comma-separated format.

    Merges xLights defaults for the effect so all required params are present.
    Theme/user overrides take precedence over defaults. ``buffer_style``, when
    given, is folded in as B_CHOICE_BufferStyle -- this is the value xLights
    actually applies (see _buffer_style_for_group); a group-level EffectLayer
    "settings" attribute alone has no effect on rendering. ``energy_score``,
    when given, drives the Pinwheel speed-by-energy override below.
    """
    # Start with xLights defaults for this effect
    defaults = dict(_XLIGHTS_EFFECT_DEFAULTS.get(placement.effect_name, {}))

    # Override with our explicit parameters
    for key, val in placement.parameters.items():
        if isinstance(val, bool):
            defaults[key] = "1" if val else "0"
        else:
            defaults[key] = str(val)

    # Wave floor (user request, 2026-07-23): Number_Waves=0 or a very thin
    # Thickness_Percentage both render as barely-visible/invisible on real
    # hardware. Enforced here -- the single point every Wave placement's
    # final parameters are assembled, mirroring the B_CHOICE_BufferStyle/
    # fade-cap precedent below -- so it guards every producer (mined
    # presets, defaults, future callers), not just the ones known today.
    if placement.effect_name == "Wave":
        try:
            if float(defaults.get("E_TEXTCTRL_Number_Waves", 1.0)) < 1.0:
                defaults["E_TEXTCTRL_Number_Waves"] = "1.00"
        except ValueError:
            pass
        try:
            if float(defaults.get("E_SLIDER_Thickness_Percentage", 10)) < 10:
                defaults["E_SLIDER_Thickness_Percentage"] = "10"
        except ValueError:
            pass

    # Never render a flat/plain Pinwheel (user request, 2026-07-23): a
    # handful of producers (the whole-house composite pool, the generic
    # prop rotation pool, the star-burst preset) either omit
    # E_CHOICE_Pinwheel_3D entirely or bake in "None", both of which fall
    # back to xLights' own flat default. Enforced here so it guards every
    # producer, not just the ones known today. The choice among the
    # non-flat options is deterministic per placement (same model+time
    # always picks the same one) rather than random, so re-running the
    # same generation reproduces identical output.
    #
    # "3D Inverted" is also never used (user request, 2026-08-03) -- not
    # just excluded from this fallback pool, but replaced outright even
    # when a producer bakes it in explicitly (e.g. corpus_recipes.py's
    # mined "megatree twin-spiral" preset), so the membership check below
    # covers any value other than the two allowed options, not just "None".
    # Match Fire's flame color to this placement's own theme color instead
    # of always rendering as plain red/yellow fire (user request, 2026-07-26).
    # Overrides any variant-baked HueShift too, since a fixed creative value
    # (e.g. "Fire Medium"'s 79) would otherwise ignore the song's actual
    # theme -- the whole point is theme consistency, not a specific variant's
    # fixed look. Section/backdrop palettes without a real saturated color
    # (all white/gray) leave the existing value alone rather than forcing red.
    if placement.effect_name == "Fire":
        dominant_hue = _dominant_hue_degrees(placement.color_palette)
        if dominant_hue is not None:
            defaults["E_SLIDER_Fire_HueShift"] = str(_fire_hue_shift_for_hue(dominant_hue))

    if (
        placement.effect_name == "Pinwheel"
        and defaults.get("E_CHOICE_Pinwheel_3D", "None") not in _PINWHEEL_3D_OPTIONS
    ):
        # zlib.crc32, not Python's hash() -- string hashing is randomized
        # per-process (PYTHONHASHSEED), which would make the same
        # generation pick a different option on every run.
        style_seed = zlib.crc32(f"{placement.model_or_group}:{placement.start_ms}".encode("utf-8"))
        defaults["E_CHOICE_Pinwheel_3D"] = _PINWHEEL_3D_OPTIONS[style_seed % len(_PINWHEEL_3D_OPTIONS)]

    # Pinwheel thickness floor (user request, 2026-08-03, found via a real
    # exported .xsq: "Pinwheel 4-Arm Twist" and 3 other built-in variants
    # never set E_SLIDER_Pinwheel_Thickness, so it fell through to the
    # xLights-defaults 0 -- a flat/invisible pinwheel). Enforced here so it
    # guards every producer (mined presets, defaults, future callers), not
    # just the ones known today -- same precedent as the Wave floor and
    # flat-Pinwheel-3D ban above. 01_BASE_All(_FADES) is the whole-house
    # canvas every prop belongs to, so a too-thin pinwheel there is far more
    # visible than on a single prop and gets a stricter floor.
    if placement.effect_name == "Pinwheel":
        min_thickness = 40 if placement.model_or_group in ("01_BASE_All", "01_BASE_All_FADES") else 5
        try:
            if float(defaults.get("E_SLIDER_Pinwheel_Thickness", 0)) < min_thickness:
                defaults["E_SLIDER_Pinwheel_Thickness"] = str(min_thickness)
        except ValueError:
            defaults["E_SLIDER_Pinwheel_Thickness"] = str(min_thickness)

    # Pinwheel speed-by-energy (user request, 2026-08-03: see module-level
    # comment on _PINWHEEL_SPEED_* above). Overrides even a variant's own
    # baked Speed value, same "guards every producer" precedent as the
    # thickness floor -- deliberate per user choice, since the alternative
    # (leave curated per-variant speeds alone) would miss the exact case
    # that prompted this: a "moderate" 15-speed variant firing during a
    # genuinely slow/quiet section. No-op when energy_score is unavailable
    # (placement's start_ms falls outside every section's range).
    if placement.effect_name == "Pinwheel" and energy_score is not None:
        if energy_score < _WHOLE_HOUSE_LOW_ENERGY_GATE:
            defaults["E_SLIDER_Pinwheel_Speed"] = str(_PINWHEEL_SPEED_LOW_ENERGY)
        elif energy_score < _WHOLE_HOUSE_HIGH_ENERGY_GATE:
            defaults["E_SLIDER_Pinwheel_Speed"] = str(_PINWHEEL_SPEED_MEDIUM_ENERGY)
        else:
            defaults["E_SLIDER_Pinwheel_Speed"] = str(_PINWHEEL_SPEED_HIGH_ENERGY)

    # Color Wash never renders with Shimmer (user request, 2026-08-03) --
    # overrides even a mined variant's own baked value (e.g. the "Color
    # Wash Shimmer"/"Color Wash Shimmer Cycles" builtin variants), same
    # "guards every producer" precedent as the Pinwheel bans above.
    if placement.effect_name == "Color Wash":
        defaults["E_CHECKBOX_ColorWash_Shimmer"] = "0"

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

    # Rule (user request, 2026-07-18, narrowed 2026-07-26): T_CHECKBOX_Canvas
    # is stripped from every effect except Warp, Kaleidoscope, and Shader.
    # The original rule banned it everywhere regardless of what a mined
    # vendor .xsqz template included; the user later clarified that was too
    # harsh -- Canvas mode is a real, required setting for these three
    # effect types specifically (e.g. the Warp Kaleidoscope Tile shader
    # renders blank without T_CHECKBOX_Canvas=1 -- see
    # _HUE_RESPONSIVE_SHADER_BASELINES / Shader.json's Warp Kaleidoscope Tile
    # variant). Still enforced here (not just omitted from
    # _XLIGHTS_EFFECT_DEFAULTS/moving_head._build_parameters) for every other
    # effect, so it can't come back in via a placement's own parameters, a
    # future template-mining pass, or any other producer.
    if placement.effect_name not in ("Warp", "Kaleidoscope", "Shader"):
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
    hue_adjust: int | None = None,
    sparkle_color: str | None = None,
) -> int:
    """Add palette to dedup index if not already present. Return index."""
    key = _serialize_palette(colors, music_sparkles, hue_adjust, sparkle_color)
    if key not in index:
        index[key] = len(palette_list)
        palette_list.append(key)
    return index[key]


def _ensure_effect_entry(
    placement: EffectPlacement,
    index: dict[str, int],
    effect_list: list[str],
    buffer_style: str | None = None,
    energy_score: int | None = None,
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
    key = _serialize_effect_params(placement, buffer_style, energy_score)
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


def _attribute_phoneme_speakers(phonemes: list[dict], words: list[dict]) -> list[dict]:
    """Tag each phoneme mark with the ``speaker`` of the word it falls within.

    Phoneme marks carry no speaker tag of their own (diarization clusters
    at the word/utterance level, see ``src.analyzer.vocal_diarization``) —
    a phoneme inherits the speaker of whichever word's ``[start_ms,
    end_ms)`` span contains its own ``start_ms``, defaulting to 0 (lead)
    when no word overlaps.
    """
    sorted_words = sorted(words, key=lambda w: w["start_ms"])
    tagged: list[dict] = []
    for p in phonemes:
        speaker = 0
        for w in sorted_words:
            if w["start_ms"] > p["start_ms"]:
                break
            if w["start_ms"] <= p["start_ms"] < w["end_ms"]:
                speaker = w.get("speaker", 0)
                break
        tagged.append({**p, "speaker": speaker})
    return tagged


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


def _section_role_marks(plan: SequencePlan) -> list[TimingMark]:
    """Build 'Sections' timing marks from classified section roles.

    Replaces the raw segmentino/QM-segmenter labels (single letters, N#,
    "qm_boundary" -- see src.analyzer.boundary_cluster/orchestrator) with
    the human-readable role each section was actually classified as
    (verse/chorus/bridge/...), from ``SectionAssignment.section.label``
    (populated from the story's "role" field in plan.py). Repeated roles
    get a numeric suffix (verse_1, verse_2) so each section is
    distinguishable in xLights; a role that appears once keeps its bare
    name -- same convention as ``xtiming.append_roles_layer`` (user
    request 2026-07-21).
    """
    role_total: dict[str, int] = {}
    for a in plan.sections:
        role_total[a.section.label] = role_total.get(a.section.label, 0) + 1

    marks: list[TimingMark] = []
    role_seen: dict[str, int] = {}
    for a in plan.sections:
        role = a.section.label
        role_seen[role] = role_seen.get(role, 0) + 1
        label = f"{role}_{role_seen[role]}" if role_total[role] > 1 else role
        marks.append(TimingMark(
            time_ms=a.section.start_ms, confidence=None, label=label,
            duration_ms=max(1, a.section.end_ms - a.section.start_ms),
        ))
    return marks


def _section_theme_marks(plan: SequencePlan) -> list[TimingMark]:
    """Build a 'Themes' timing track showing which theme each section uses.

    Diagnostic track (user request 2026-07-28, after investigating a real
    generated .xsq where two same-role chorus sections rendered in
    unrelated color families -- tier-6+ prop colors follow each section's
    OWN assigned theme, not one song-wide identity, and there was no way to
    see which theme was active from the .xsq alone). Same repeated-label
    numeric-suffix convention as _section_role_marks.
    """
    theme_total: dict[str, int] = {}
    for a in plan.sections:
        theme_total[a.theme.name] = theme_total.get(a.theme.name, 0) + 1

    marks: list[TimingMark] = []
    theme_seen: dict[str, int] = {}
    for a in plan.sections:
        name = a.theme.name
        theme_seen[name] = theme_seen.get(name, 0) + 1
        label = f"{name}_{theme_seen[name]}" if theme_total[name] > 1 else name
        marks.append(TimingMark(
            time_ms=a.section.start_ms, confidence=None, label=label,
            duration_ms=max(1, a.section.end_ms - a.section.start_ms),
        ))
    return marks


def _referenced_timing_track_names(
    all_placements: dict[str, list[EffectPlacement]],
) -> set[str]:
    """Timing track names actually depended on by a placed effect's own
    parameters (e.g. VU Meter's E_CHOICE_VUMeter_TimingTrack) — these must
    be exported regardless of include_extra_timing, since omitting one
    doesn't declutter the timeline, it breaks that effect (the referenced
    track silently doesn't exist)."""
    names: set[str] = set()
    for placements in all_placements.values():
        for p in placements:
            if p.effect_name == "VU Meter":
                track = p.parameters.get("E_CHOICE_VUMeter_TimingTrack")
                if track:
                    names.add(track)
    return names


def _collect_timing_tracks(
    hierarchy: HierarchyResult | None,
    lyrics: list[dict] | None = None,
    include_extra_timing: bool = True,
    section_role_marks: list[TimingMark] | None = None,
    force_include: set[str] | None = None,
    section_theme_marks: list[TimingMark] | None = None,
) -> dict[str, list[TimingMark]]:
    """Collect single-layer timing tracks from hierarchy (+ optional lyric lines).

    force_include names tracks that a placed effect actually references by
    name (see _referenced_timing_track_names) — these are added even when
    include_extra_timing is False, since they're a real dependency, not
    just an informational display track.
    """
    tracks: dict[str, list[TimingMark]] = {}
    force_include = force_include or set()

    if section_role_marks:
        tracks["Sections"] = section_role_marks

    if section_theme_marks:
        tracks["Themes"] = section_theme_marks

    if hierarchy is not None:
        if hierarchy.beats and hierarchy.beats.marks:
            tracks["Beats"] = hierarchy.beats.marks

        if hierarchy.bars and hierarchy.bars.marks:
            tracks["Bars"] = hierarchy.bars.marks

        if "Sections" not in tracks and hierarchy.sections:
            tracks["Sections"] = hierarchy.sections

        if include_extra_timing or "Chords" in force_include:
            if hierarchy.chords and hierarchy.chords.marks:
                tracks["Chords"] = hierarchy.chords.marks

        # Emit one timing track per stem with onsets.  Stem-aware trigger
        # placement (drum Shockwaves, vocal accents, bass pulses) routes to
        # its matching Onsets (<stem>) track, so every stem with marks must
        # be emitted — not only the first one.
        for stem_name, track in hierarchy.events.items():
            track_name = f"Onsets ({stem_name})"
            if track.marks and (include_extra_timing or track_name in force_include):
                tracks[track_name] = track.marks

        # Per-instrument drum hits, split from the classified "drums"
        # onset track (see src/analyzer/drum_classifier.py) — previously
        # only visible in the standalone analyzer .xtiming export, never
        # in the generated .xsq itself.
        if hierarchy.kick_hits and (include_extra_timing or "Kick Hits" in force_include):
            tracks["Kick Hits"] = hierarchy.kick_hits
        if hierarchy.snare_hits and (include_extra_timing or "Snare Hits" in force_include):
            tracks["Snare Hits"] = hierarchy.snare_hits
        if hierarchy.hihat_hits and (include_extra_timing or "Hihat Hits" in force_include):
            tracks["Hihat Hits"] = hierarchy.hihat_hits
        if hierarchy.riff_bursts and (include_extra_timing or "Riff Bursts" in force_include):
            tracks["Riff Bursts"] = hierarchy.riff_bursts

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
