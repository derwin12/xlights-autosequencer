"""Plan builder — orchestrates the full sequence generation pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from src.analyzer.result import HierarchyResult
from src.effects.library import EffectLibrary, load_effect_library
from src.generator.effect_placer import (
    _IMPACT_ENERGY_GATE,
    _IMPACT_MIN_DURATION_MS,
    _IMPACT_QUALIFYING_ROLES,
    _compute_active_tiers,
    _place_drum_accents,
    _place_impact_accent,
    _place_crash_accents,
    _place_lyric_text,
    _place_picture_effects,
    _place_singing_faces,
    _place_star_bursts,
    _place_video_effect,
    _place_whole_house_composite,
    _whole_house_layer_count,
    compute_duration_target,
    place_effects,
    restrain_palette,
)
from src.generator.corpus_recipes import CORPUS_RECIPES, section_qualifies
from src.generator.image_catalog import suggest_images_for_words
from src.generator.energy import derive_section_energies
from src.generator.moving_head import (
    place_moving_head_crash_accents,
    place_moving_head_ending_punches,
    place_moving_head_moves,
)
from src.generator.rotation import RotationEngine
from src.generator.transitions import TransitionConfig, apply_transitions
from src.story.builder import load_song_story
from src.generator.models import (
    AccentPolicy,
    EffectPlacement,
    GenerationConfig,
    SectionAssignment,
    SectionEnergy,
    SequencePlan,
    SongProfile,
)
from src.generator.theme_selector import select_themes
from src.generator.value_curves import generate_value_curves
from src.generator.xsq_writer import write_xsq
from src.grouper.classifier import classify_props, normalize_coords
from src.grouper.grouper import PowerGroup, generate_groups
from src.grouper.layout import Layout, Prop, parse_layout
from src.themes.library import ThemeLibrary, load_theme_library


def read_song_metadata(audio_path: Path, hierarchy: Optional[HierarchyResult] = None) -> SongProfile:
    """Read song metadata from ID3 tags via mutagen.

    Falls back to filename-based title and empty fields if tags unavailable.
    """
    title = audio_path.stem
    artist = ""
    genre = "pop"
    duration_ms = 0
    estimated_bpm = 120.0

    if hierarchy is not None:
        duration_ms = hierarchy.duration_ms
        estimated_bpm = hierarchy.estimated_bpm

    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(audio_path), easy=True)
        if audio is not None:
            title = _first_tag(audio, "title", title)
            artist = _first_tag(audio, "artist", artist)
            genre = _first_tag(audio, "genre", genre)
    except Exception:
        pass

    return SongProfile(
        title=title,
        artist=artist,
        genre=genre.lower(),
        occasion="general",
        duration_ms=duration_ms,
        estimated_bpm=estimated_bpm,
    )


def _first_tag(audio, key: str, default: str) -> str:
    """Extract first value of an ID3 tag, or return default."""
    vals = audio.get(key)
    if vals and len(vals) > 0:
        return str(vals[0])
    return default


def build_plan(
    config: GenerationConfig,
    hierarchy: HierarchyResult,
    props: list[Prop],
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    theme_library: ThemeLibrary,
    progress_cb: Callable[[str, float], None] | None = None,
    layout: Optional[Layout] = None,
) -> SequencePlan:
    """Build a SequencePlan from all upstream data.

    Pipeline:
    1. Read song metadata -> SongProfile
    2. Derive section energies -> SectionEnergy[]
    3. Select themes -> SectionAssignment[]
    4. Place effects -> EffectPlacement[] per group
    5. Generate value curves
    6. Assemble SequencePlan
    """
    # 1. Song profile
    profile = read_song_metadata(config.audio_path, hierarchy)
    profile.genre = config.genre
    profile.occasion = config.occasion

    # 2. Derive section energies — use song story if available, else derive from hierarchy
    story: Optional[dict] = None
    if config.story_path is not None:
        story_path = config.story_path
        # Look for reviewed story first, fall back to base story
        reviewed_path = story_path.parent / (story_path.stem.replace("_story", "_story_reviewed") + ".json")
        if reviewed_path.exists():
            story = load_song_story(reviewed_path)
        elif story_path.exists():
            story = load_song_story(story_path)

    if story is not None:
        section_energies = _section_energies_from_story(story)
        # UI-selected config values should win over story defaults.  The story's
        # preferences may contain literal defaults ("general" occasion, "pop"/
        # "any" genre) that don't reflect an explicit user choice — those
        # defaults should never override what the user picked at generation
        # time.  Use the story value only when (a) it's non-empty and (b)
        # either the config is at its own default or matches the story value.
        prefs = story.get("preferences", {})
        story_genre = prefs.get("genre")
        story_occasion = prefs.get("occasion")

        if config.occasion and config.occasion != "general":
            inferred_occasion = config.occasion
        else:
            inferred_occasion = story_occasion or config.occasion

        if config.genre and config.genre not in ("any", "pop"):
            inferred_genre = config.genre
        else:
            inferred_genre = story_genre or config.genre
        scale = None  # story handles mood directly
    else:
        ef = hierarchy.essentia_features or {}
        section_energies = derive_section_energies(
            hierarchy.sections,
            hierarchy.energy_curves,
            hierarchy.energy_impacts,
            dynamic_complexity=ef.get("dynamic_complexity"),
            loudness_lufs=ef.get("loudness_lufs"),
            song_duration_ms=hierarchy.duration_ms,
        )
        inferred_genre = config.genre
        inferred_occasion = config.occasion
        scale = ef.get("scale")
        # Auto-infer mood-appropriate genre from essentia key analysis
        if inferred_genre == "pop" and ef.get("scale"):
            if ef["scale"] == "minor" and ef.get("key_strength", 0) > 0.6:
                inferred_genre = "classical"  # minor key → favor darker themes

    # 3. Select themes
    assignments = select_themes(
        section_energies, theme_library, inferred_genre, inferred_occasion,
        scale=scale,
        base_variation_seed=config.variation_seed,
    )

    # Apply theme overrides before deriving the anchor palette so the anchor
    # reflects the themes that will actually be used (not the auto-selected ones).
    #
    # theme_overrides values arrive in TWO different formats depending on the
    # caller (2026-07-18 bug find): the CLI (src/cli_old.py) and
    # tests/integration/test_phase1_metrics.py pass display names
    # ("Stellar Wind"), while the review API (export.py's session
    # assignments, generate_routes.py's theme_slug/story overrides) passes
    # slug IDs ("stellar-wind") -- the same slug format _load_themes() uses
    # for its theme_id catalog (src/review/api/v1/themes.py::_slugify). The
    # direct dict lookup below only ever matched display names, so every
    # slug-based override (i.e. every theme choice made through the Theme
    # screen) silently no-op'd and fell through to the auto-selected theme
    # -- confirmed on a real export where NONE of a song's 4 confirmed
    # theme assignments' colors appeared anywhere in the output. Resolve
    # against both a name-keyed and a slug-keyed index so either caller
    # format works.
    if config.theme_overrides:
        from src.themes.library import _slugify as _theme_slugify
        _themes_by_slug = {
            _theme_slugify(t.name): t for t in theme_library.themes.values()
        }
        for idx, theme_name in config.theme_overrides.items():
            if 0 <= idx < len(assignments):
                theme = (
                    theme_library.themes.get(theme_name)
                    or _themes_by_slug.get(theme_name)
                )
                if theme is not None:
                    assignments[idx].theme = theme

    # 3a. Derive song-level anchor palette and stamp it onto every assignment.
    # This ensures the background wash tiers (1-2) use a consistent set of 4
    # dominant colors across all sections instead of each section pulling its own
    # independent palette.  Per-section accent tiers (3+) still use each theme's
    # own colors for variety.
    _anchor = _derive_anchor_palette(assignments)
    for _a in assignments:
        _a.anchor_palette = _anchor

    # 3b. Load variant library and build rotation plan
    from src.variants.library import load_variant_library
    from src.generator.effect_placer import derive_working_set

    variant_library = load_variant_library(effect_library=effect_library)

    # 3c. Derive WorkingSet per unique theme (when focused_vocabulary=True)
    working_sets: dict = {}
    if config.focused_vocabulary:
        for assignment in assignments:
            theme_name = assignment.theme.name
            if theme_name not in working_sets:
                working_sets[theme_name] = derive_working_set(assignment.theme, variant_library)

    rotation_engine = RotationEngine(variant_library, effect_library)
    rotation_plan = rotation_engine.build_rotation_plan(
        sections=[a.section for a in assignments],
        groups=groups,
        theme_assignments=assignments,
        embrace_repetition=config.embrace_repetition,
        working_sets=working_sets if config.focused_vocabulary else None,
    )

    # 4. Precompute per-section decisions onto each SectionAssignment (spec 048).
    # Every creative knob that shapes a section — active tiers, palette cap per tier,
    # duration band, accent policy, working set, section index — is decided here and
    # stored on the assignment.  `place_effects` below consumes the assignment as a
    # read-only recipe.
    _populate_assignment_decisions(assignments, config, hierarchy, working_sets)

    # 4b. When a video was imported, its target matrix (5c below) renders
    # exclusively the full-song Video effect — strip that matrix out of every
    # group's membership and out of the vocal-effect prop list so no other
    # effect (section pool, drum/impact accents, faces, lyric text) also
    # lands on it. `props` itself stays unfiltered so 5c can still find the
    # matrix as its target.
    effect_props = props
    if config.video_path is not None:
        video_matrix_props = [p for p in props if getattr(p, "display_as", "") == "Matrix"]
        if video_matrix_props:
            video_target_name = max(
                video_matrix_props, key=lambda p: (getattr(p, "pixel_count", 0), p.name)
            ).name
            effect_props = [p for p in props if p.name != video_target_name]
            for group in groups:
                group.members = [m for m in group.members if m != video_target_name]
            groups = [g for g in groups if g.members]

    # 5. Place effects for each section.  `place_effects` reads every per-section
    # decision off the assignment fields populated above.
    model_names = [p.name for p in props]
    props_by_name = {p.name: p for p in effect_props}
    n_sections = max(len(assignments), 1)
    for si, assignment in enumerate(assignments):
        section_cb = None
        if progress_cb is not None:
            label = assignment.section.label or "section"
            progress_cb(f"section {si + 1}/{n_sections} · {label}", si / n_sections)
            section_cb = (
                lambda msg, _si=si, _label=label:
                progress_cb(f"{msg} · section {_si + 1}/{n_sections} ({_label})",
                            _si / n_sections)
            )
        group_effects = place_effects(
            assignment, groups, effect_library, hierarchy,
            variant_library=variant_library,
            rotation_plan=rotation_plan,
            progress_cb=section_cb,
        )
        assignment.group_effects = group_effects

        # Beat accent effects (spec 042).  The helpers early-return when
        # `assignment.accent_policy` has the corresponding flag unset, so we
        # call unconditionally — policy is the single source of truth.
        drum_accents = _place_drum_accents(
            groups=groups,
            hierarchy=hierarchy,
            assignment=assignment,
            variant_library=variant_library,
            props_by_name=props_by_name,
        )
        for gname, placements in drum_accents.items():
            assignment.group_effects.setdefault(gname, []).extend(placements)

        impact_accents = _place_impact_accent(
            groups=groups,
            assignment=assignment,
            variant_library=variant_library,
        )
        for gname, placements in impact_accents.items():
            assignment.group_effects.setdefault(gname, []).extend(placements)

        whole_house_composite = _place_whole_house_composite(
            groups=groups,
            assignment=assignment,
            variant_library=variant_library,
        )
        for gname, placements in whole_house_composite.items():
            assignment.group_effects.setdefault(gname, []).extend(placements)

    # 5b. Singing faces + word-synced lyric text (config.vocal_words).
    # Song-scoped, not per-section — vocal regions derive from the word marks
    # alone and ride on plan.vocal_effects, so a 0-section analysis (bug-159:
    # no assignments at all) still renders them.
    vocal_effects: dict[str, list] = {}
    if config.vocal_words:
        vocal_effects = _place_singing_faces(effect_props, config.vocal_words)
        for gname, placements in _place_lyric_text(effect_props, config.vocal_words).items():
            vocal_effects.setdefault(gname, []).extend(placements)

    # 5c. Imported video on a matrix (config.video_path). Song-scoped,
    # same rationale as vocal_effects. Used as uploaded — no rescale/rename;
    # that was built for a since-abandoned YouTube-pull-and-rescale flow.
    video_effects: dict[str, list] = {}
    if config.video_path is not None:
        video_effects = _place_video_effect(props, config.video_path, hierarchy.duration_ms)

    # 5d0. DMX moving-head fixture groups (config.moving_head_effects) --
    # one gated move per section that's genuinely "strong and powerful"
    # (top energy tier or chorus/drop role), placed per individual head
    # model (or the group itself for the two "Fan" moves), mined from a
    # user-provided reference sequence. See moving_head.py's module
    # docstring for the v1 continuous-wash rationale this replaced.
    moving_head_effects: dict[str, list] = {}
    if config.moving_head_effects and layout is not None:
        moving_head_effects = place_moving_head_moves(layout, assignments)

    # 5d. Rare whole-house crash accents (config.crash_accents). Song-scoped,
    # same rationale as vocal_effects/video_effects. Computed here (before
    # transitions/end-of-song fade) so the fade's own start boundary can be
    # used to exclude any crash mark that would collide with it.
    crash_effects: dict[str, list] = {}
    if config.crash_accents and hierarchy.crash_accents:
        fade_exclusion_start_ms = max(
            0, min(_audible_end_ms(assignments, hierarchy), hierarchy.duration_ms - _FADE_MIN_MS)
        )
        crash_effects = _place_crash_accents(
            groups=groups,
            hierarchy=hierarchy,
            vocal_words=config.vocal_words,
            variant_library=variant_library,
            fade_exclusion_start_ms=fade_exclusion_start_ms,
        )
        # Matching fan-out Moving Head punch at the same marks (config.
        # moving_head_effects) -- same duration/exclusion rules as the
        # Shockwave above, see place_moving_head_crash_accents.
        if config.moving_head_effects and layout is not None:
            for gname, placements in place_moving_head_crash_accents(
                layout, hierarchy, config.vocal_words,
                fade_exclusion_start_ms=fade_exclusion_start_ms,
                existing_placements=moving_head_effects,
            ).items():
                crash_effects.setdefault(gname, []).extend(placements)

    # 5d-2. Ending punches: quick straight-up Moving Head flash on each
    # cymbal hit of the song's ending "button" (hierarchy.ending_punches,
    # crash_accents.detect_ending_punches). Same rare-transient-accents
    # umbrella as 5d (config.crash_accents), merged into the same dict.
    if (
        config.crash_accents and config.moving_head_effects
        and layout is not None and hierarchy.ending_punches
    ):
        fade_exclusion_start_ms = max(
            0, min(_audible_end_ms(assignments, hierarchy), hierarchy.duration_ms - _FADE_MIN_MS)
        )
        existing_mh = dict(moving_head_effects)
        for gname, placements in crash_effects.items():
            existing_mh.setdefault(gname, [])
            existing_mh[gname] = existing_mh[gname] + placements
        for gname, placements in place_moving_head_ending_punches(
            layout, hierarchy,
            fade_exclusion_start_ms=fade_exclusion_start_ms,
            existing_placements=existing_mh,
        ).items():
            crash_effects.setdefault(gname, []).extend(placements)

    # 5d-3. Riff bursts: short Pinwheel burst on Star-family groups at each
    # rare drum fill (hierarchy.riff_bursts, riff_bursts.detect_riff_bursts
    # -- snare-roll detection, replaced the earlier bass+chord version that
    # missed both user-confirmed moments). Targets Stars rather than Moving
    # Head specifically to avoid the crash-accent warmup collision (see
    # CLAUDE.md -> "Riff/Fill Detector for Moving Head Accent"). Gated on
    # config.riff_bursts.
    if config.riff_bursts and hierarchy.riff_bursts:
        fade_exclusion_start_ms = max(
            0, min(_audible_end_ms(assignments, hierarchy), hierarchy.duration_ms - _FADE_MIN_MS)
        )
        for gname, placements in _place_star_bursts(
            groups, hierarchy, config.vocal_words,
            fade_exclusion_start_ms=fade_exclusion_start_ms,
        ).items():
            crash_effects.setdefault(gname, []).extend(placements)

    # 5e. Library images on Matrix/Mega Tree props, timed to lyric matches
    # (config.picture_effects). Song-scoped, same rationale as
    # vocal_effects/video_effects/crash_effects. No generic filler rotation —
    # only fires where a lyric word actually matches a library image.
    picture_effects: dict[str, list] = {}
    if config.picture_effects and config.vocal_words:
        word_image_matches = suggest_images_for_words(
            config.vocal_words, ignored_words=config.ignored_image_words,
        )
        if word_image_matches:
            # Bug-243 follow-up: Pictures must render above whatever the
            # per-section theme/rotation content already occupies on its
            # target group. xsq_writer serializes <EffectLayer> children in
            # ascending layer-index order and xLights renders the *first*
            # child on top -- so "above" means one layer *below* the lowest
            # index currently in use, not above the highest (confirmed by
            # inspecting a real generated .xsq: placing it at the highest
            # index put it last in the file and visually at the bottom of
            # the stack, hidden behind an opaque "On" layer).
            existing_layers: dict[str, int] = {}
            for a in assignments:
                for gname, placements in a.group_effects.items():
                    for p in placements:
                        if gname not in existing_layers or p.layer < existing_layers[gname]:
                            existing_layers[gname] = p.layer
            picture_effects = _place_picture_effects(
                props=effect_props,
                groups=groups,
                effect_library=effect_library,
                duration_ms=hierarchy.duration_ms,
                variation_seed=config.variation_seed,
                word_image_matches=word_image_matches,
                existing_layers=existing_layers,
            )

    # 5. Value curves — generate for each placement when curves are enabled
    if config.curves_mode != "none":
        for assignment in assignments:
            for placements in assignment.group_effects.values():
                for placement in placements:
                    effect_def = effect_library.effects.get(placement.effect_name)
                    if effect_def:
                        curves = generate_value_curves(
                            placement, effect_def, hierarchy, config.curves_mode
                        )
                        # Remap from logical param name to xLights storage_name,
                        # and bundle the parameter's min/max range so the XSQ writer
                        # can emit the correct Min/Max in the value curve encoding.
                        param_lookup = {p.name: p for p in effect_def.parameters}
                        vc: dict = {}
                        for k, v in curves.items():
                            p = param_lookup.get(k)
                            if p is not None:
                                p_min = p.min if p.min is not None else 0.0
                                p_max = p.max if p.max is not None else 100.0
                                vc[p.storage_name] = (v, float(p_min), float(p_max))
                            else:
                                vc[k] = v
                        placement.value_curves = vc

    # 6. Apply transitions (crossfades at section boundaries + end-of-song fade-out)
    transition_config = TransitionConfig(mode=config.transition_mode)
    apply_transitions(assignments, transition_config, bpm=profile.estimated_bpm)

    # 6b. End-of-song fade — when the sequence runs past the last musical
    # section (trailing silence), one white Min-blend On on 01_BASE_All_FADES
    # ramps the whole display to black by the end of the sequence.
    _place_end_of_song_fade(assignments, groups, effect_library, hierarchy)

    # 6c. Start-of-song fade-in — mirrors 6b: when the audio has more than
    # _FADE_IN_MIN_SILENCE_MS of leading silence (user request, 2026-07-15),
    # one white Min-blend On on 01_BASE_All_FADES ramps the whole display up
    # from black over that intro silence instead of snapping on abruptly
    # ahead of the beat.
    _place_start_of_song_fade(assignments, groups, effect_library, hierarchy)

    # 7. Assemble plan
    return SequencePlan(
        song_profile=profile,
        sections=assignments,
        layout_groups=groups,
        models=model_names,
        rotation_plan=rotation_plan,
        vocal_effects=vocal_effects,
        video_effects=video_effects,
        crash_effects=crash_effects,
        picture_effects=picture_effects,
        moving_head_effects=moving_head_effects,
    )


# The end-of-song fade always fires and spans at least this long: when the
# audio runs right to the end of the sequence, the fade covers the final
# stretch of audio itself so the display never cuts to black abruptly.
_FADE_MIN_MS = 2000

# Energy (0-100) below which the full-mix curve counts as silence. The section
# builder tiles the entire audio duration — the last section's end_ms extends
# over trailing silence — so audible-end detection must come from the energy
# curve, not from section boundaries.
_SILENCE_ENERGY_THRESHOLD = 5


def _audible_end_ms(
    assignments: list[SectionAssignment], hierarchy: HierarchyResult
) -> int:
    """Return when the song's audio actually goes quiet.

    Uses the last full-mix energy frame at or above
    ``_SILENCE_ENERGY_THRESHOLD``; falls back to the latest section end when
    no energy curve is available (curves are optional analyzer output).
    """
    curve = hierarchy.energy_curves.get("full_mix")
    if curve is not None and curve.values and curve.fps > 0:
        last_idx = max(
            (i for i, v in enumerate(curve.values) if v >= _SILENCE_ENERGY_THRESHOLD),
            default=-1,
        )
        if last_idx >= 0:
            return int((last_idx + 1) * 1000 / curve.fps)
    return max(a.section.end_ms for a in assignments)


def _place_end_of_song_fade(
    assignments: list[SectionAssignment],
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    hierarchy: HierarchyResult,
) -> None:
    """Fade the whole display to black at the end of every sequence.

    One white On effect on the ``01_BASE_All_FADES`` group spans from the
    audible end of the song (see ``_audible_end_ms``) to the end of the
    sequence: brightness ramps 100 -> 0 (``Eff_On_End=0``) and
    ``LayerMethod=Min`` clamps every layer rendered beneath it, so the
    display is black by the end of the sequence no matter what other tiers
    are doing. The fade always fires and covers at least ``_FADE_MIN_MS`` —
    when the audio runs right to the end of the sequence, it overlaps the
    final stretch of audio rather than letting the display cut hard.
    """
    if not assignments:
        return
    if not any(g.name == "01_BASE_All_FADES" for g in groups):
        return
    song_end = _audible_end_ms(assignments, hierarchy)
    fade_start = max(0, min(song_end, hierarchy.duration_ms - _FADE_MIN_MS))
    if fade_start >= hierarchy.duration_ms:
        return
    on_def = effect_library.effects.get("On")
    if on_def is None:
        return
    fade = EffectPlacement(
        effect_name="On",
        xlights_id=on_def.xlights_id,
        model_or_group="01_BASE_All_FADES",
        start_ms=fade_start,
        end_ms=hierarchy.duration_ms,
        parameters={
            "E_TEXTCTRL_Eff_On_End": "0",
            "T_CHOICE_LayerMethod": "Min",
            "T_SLIDER_EffectLayerMix": "0",
        },
        color_palette=["#FFFFFF"],
    )
    assignments[-1].group_effects.setdefault("01_BASE_All_FADES", []).append(fade)


# Only fade in when the intro silence exceeds this — most songs start right
# on the beat and shouldn't get an artificial fade-in (user request,
# 2026-07-15: "if there is more than 1 second of silence").
_FADE_IN_MIN_SILENCE_MS = 1000


def _audible_start_ms(hierarchy: HierarchyResult) -> int:
    """Return when the song's audio actually starts (mirrors ``_audible_end_ms``).

    Uses the first full-mix energy frame at or above
    ``_SILENCE_ENERGY_THRESHOLD``; falls back to 0 when no energy curve is
    available (curves are optional analyzer output).
    """
    curve = hierarchy.energy_curves.get("full_mix")
    if curve is not None and curve.values and curve.fps > 0:
        first_idx = next(
            (i for i, v in enumerate(curve.values) if v >= _SILENCE_ENERGY_THRESHOLD),
            None,
        )
        if first_idx is not None:
            return int(first_idx * 1000 / curve.fps)
    return 0


def _place_start_of_song_fade(
    assignments: list[SectionAssignment],
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    hierarchy: HierarchyResult,
) -> None:
    """Fade the whole display in from black over intro silence, mirroring
    ``_place_end_of_song_fade``.

    One white On effect on ``01_BASE_All_FADES`` spans from 0 to the audible
    start of the song (see ``_audible_start_ms``): brightness ramps 0 -> 100
    (``Eff_On_Start=0``) and ``LayerMethod=Min`` clamps every layer rendered
    beneath it, same mechanism as the end-of-song fade just reversed. Only
    fires when the intro silence exceeds ``_FADE_IN_MIN_SILENCE_MS`` — a
    song that starts right on the beat gets no fade at all.
    """
    if not assignments:
        return
    if not any(g.name == "01_BASE_All_FADES" for g in groups):
        return
    audible_start = _audible_start_ms(hierarchy)
    if audible_start < _FADE_IN_MIN_SILENCE_MS:
        return
    on_def = effect_library.effects.get("On")
    if on_def is None:
        return
    fade = EffectPlacement(
        effect_name="On",
        xlights_id=on_def.xlights_id,
        model_or_group="01_BASE_All_FADES",
        start_ms=0,
        end_ms=audible_start,
        parameters={
            "E_TEXTCTRL_Eff_On_Start": "0",
            "T_CHOICE_LayerMethod": "Min",
            "T_SLIDER_EffectLayerMix": "0",
        },
        color_palette=["#FFFFFF"],
    )
    assignments[0].group_effects.setdefault("01_BASE_All_FADES", []).append(fade)


def _populate_assignment_decisions(
    assignments: list[SectionAssignment],
    config: GenerationConfig,
    hierarchy: HierarchyResult,
    working_sets: dict,
) -> None:
    """Precompute per-section creative decisions and store them on each assignment.

    Runs after theme selection and before placement.  Every field written here is
    consumed by `place_effects()` (and the accent helpers) as a read-only recipe.
    See spec 048 plan.md Phase B and data-model.md for the field contracts.
    """
    dummy_palette = ["#000000"] * 6
    drum_track_present = hierarchy.events.get("drums") is not None
    last_idx = len(assignments) - 1
    corpus_family_counts: dict[str, int] = {}
    for idx, assignment in enumerate(assignments):
        section = assignment.section
        assignment.section_index = idx
        assignment.is_final_section = (idx == last_idx)

        # Corpus-recipe rotation: per-family running count of qualifying
        # sections, consumed by _place_corpus_recipe as the rotation-pool
        # index (see SectionAssignment.corpus_occurrence).
        assignment.corpus_occurrence = {}
        for recipe in CORPUS_RECIPES:
            if section_qualifies(recipe, section):
                n = corpus_family_counts.get(recipe.family, 0)
                assignment.corpus_occurrence[recipe.family] = n
                corpus_family_counts[recipe.family] = n + 1

        # Active tiers — user override (`config.tiers`) wins; else energy/mood-driven
        # selection when enabled; else all tiers.
        if config.tier_selection:
            if config.tiers is not None:
                assignment.active_tiers = frozenset(config.tiers)
            else:
                assignment.active_tiers = _compute_active_tiers(section, idx, hierarchy)
        else:
            assignment.active_tiers = frozenset(range(1, 9))

        # Palette target — per-tier cap mapping. Populated from restrain_palette's
        # length at (energy, tier) with a dummy 6-colour palette; the actual colour
        # selection still happens inside place_effects against the real per-tier
        # palette using the stored count.
        if config.palette_restraint:
            assignment.palette_target = {
                tier: len(restrain_palette(dummy_palette, section.energy_score, tier))
                for tier in assignment.active_tiers
            }
        else:
            assignment.palette_target = None

        # Duration target
        if config.duration_scaling:
            assignment.duration_target = compute_duration_target(
                hierarchy.estimated_bpm, section.energy_score,
            )
        else:
            assignment.duration_target = None

        # Accent policy — apply all section-level gates here, once, so accent
        # helpers become mechanical.  Per-hit drum energy sampling stays inside
        # `_place_drum_accents` (per-hit, not per-section).
        drum_ok = bool(
            config.beat_accent_effects
            and section.energy_score >= 60
            and drum_track_present
        )
        role = (section.label or "").lower()
        impact_ok = bool(
            config.beat_accent_effects
            and section.energy_score > _IMPACT_ENERGY_GATE
            and (section.end_ms - section.start_ms) >= _IMPACT_MIN_DURATION_MS
            and (not role or role in _IMPACT_QUALIFYING_ROLES)
        )
        whole_house_layers = (
            _whole_house_layer_count(section.energy_score, assignment.variation_seed)
            if config.whole_house_composite
            else 0
        )
        assignment.accent_policy = AccentPolicy(
            drum_hits=drum_ok, impact=impact_ok, whole_house_layers=whole_house_layers,
        )

        # Group density — fraction of groups per tier to activate.
        # Low-energy sections leave most props dark; only the prominent hero/focal
        # props are lit, matching pro sequences where quiet passages use ≤30% of models.
        #
        # Lower bracket boundary tightened from `<= 50` → `<= 35` (Apr 2026): the
        # original `<= 50` lumped most mid-tempo pop sections (energy 40-50) into
        # the 0.40 bucket, culling 60% of tier-6 groups in songs that should still
        # look populated. Empirical evidence in
        # openspec/changes/dim-section-real-cause/design.md: Baby Shark sections
        # at energy 47-50 were rendering at 3-6% channel activation. The middle
        # band now covers energy 36-70 where most pop / mid-tempo / kid songs sit.
        energy = section.energy_score
        if energy <= 35:
            assignment.group_density = 0.40
        elif energy <= 70:
            assignment.group_density = 0.70
        else:
            assignment.group_density = 1.0

        # Working set — per-theme reference, shared across sections using the same theme.
        assignment.working_set = (
            working_sets.get(assignment.theme.name) if config.focused_vocabulary else None
        )


def _derive_anchor_palette(assignments: list[SectionAssignment]) -> list[str]:
    """Derive a 4-color song-level anchor palette from the dominant section themes.

    Colors are weighted by the total duration of sections that use them.  The
    top 4 by weighted time become the anchor so that the most-used section
    (typically chorus) defines the song's color identity.
    """
    weighted: dict[str, float] = {}
    for a in assignments:
        duration = a.section.end_ms - a.section.start_ms
        for color in a.theme.palette:
            weighted[color] = weighted.get(color, 0.0) + duration

    sorted_colors = sorted(weighted, key=lambda c: weighted[c], reverse=True)
    anchor = sorted_colors[:4]
    # Always return something — fall back to first assignment's palette if empty
    if not anchor and assignments:
        anchor = list(assignments[0].theme.palette[:4])
    return anchor


def _section_energies_from_story(story: dict) -> list[SectionEnergy]:
    """Convert song story sections to SectionEnergy objects.

    Applies three-level precedence: per-section override > song-wide preference > auto-derived.
    """
    from src.generator.models import energy_to_mood

    prefs = story.get("preferences", {})
    global_mood = prefs.get("mood")

    energies: list[SectionEnergy] = []
    for sec in story.get("sections", []):
        overrides = sec.get("overrides", {})
        # Three-level precedence for mood
        mood = (
            overrides.get("mood")
            or global_mood
            or energy_to_mood(sec["character"]["energy_score"])
        )
        energy_score = sec["character"]["energy_score"]
        # Apply per-section intensity scaler to energy score
        section_intensity = overrides.get("intensity") or 1.0
        global_intensity = prefs.get("intensity", 1.0)
        adjusted_score = min(100, int(energy_score * section_intensity * global_intensity))

        impact_count = sec.get("lighting", {}).get("moment_count", 0)
        energies.append(SectionEnergy(
            label=sec["role"],
            start_ms=int(sec["start"] * 1000),
            end_ms=int(sec["end"] * 1000),
            energy_score=adjusted_score,
            mood_tier=mood,
            impact_count=impact_count,
        ))

    # Enforce contiguity — extend each section to meet the next, fill any gaps
    for i in range(len(energies) - 1):
        energies[i].end_ms = energies[i + 1].start_ms

    return energies


def _write_plan_json(plan: SequencePlan, output_path: Path) -> None:
    """Write the rotation plan as a JSON file for diagnostics and the rotation-report CLI."""
    import json

    data: dict = {
        "song_profile": {
            "title": plan.song_profile.title,
            "artist": plan.song_profile.artist,
            "genre": plan.song_profile.genre,
            "occasion": plan.song_profile.occasion,
            "duration_ms": plan.song_profile.duration_ms,
            "estimated_bpm": plan.song_profile.estimated_bpm,
        },
        "rotation_plan": plan.rotation_plan.to_dict(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))
    logger.info("Wrote rotation plan: %s", output_path)


def generate_sequence(config: GenerationConfig) -> Path:
    """Top-level function: run the full pipeline from config to .xsq file.

    Returns the path to the generated .xsq file.
    """
    from src.analyzer.orchestrator import run_orchestrator

    # Run analysis (or use cache)
    hierarchy = run_orchestrator(
        str(config.audio_path),
        fresh=config.force_reanalyze,
    )

    # Parse layout and classify props (normalize coords, compute pixel count)
    layout = parse_layout(config.layout_path)
    props = layout.props
    normalize_coords(props)
    classify_props(props)

    # Generate power groups
    groups = generate_groups(props)

    # Load libraries
    from src.variants.library import load_variant_library

    effect_library = load_effect_library()
    variant_library = load_variant_library(effect_library=effect_library)
    theme_library = load_theme_library(effect_library=effect_library, variant_library=variant_library)

    # Build plan
    plan = build_plan(config, hierarchy, props, groups, effect_library, theme_library, layout=layout)

    # Write XSQ with timing tracks
    output_name = config.audio_path.stem + ".xsq"
    output_path = config.output_dir / output_name
    write_xsq(plan, output_path, hierarchy=hierarchy, audio_path=config.audio_path)

    # Write rotation plan JSON alongside the XSQ for diagnostics
    if plan.rotation_plan is not None:
        _write_plan_json(plan, output_path.with_suffix(".plan.json"))

    return output_path


def regenerate_sections(config: GenerationConfig, existing_xsq: Path) -> Path:
    """Re-run generation on specific sections of an existing .xsq file.

    Parses the existing .xsq, removes effects in the target section time ranges,
    regenerates those sections with new themes, and writes back.
    """
    from src.analyzer.orchestrator import run_orchestrator
    from src.generator.xsq_writer import parse_xsq, remove_effects_in_range

    hierarchy = run_orchestrator(
        str(config.audio_path),
        fresh=config.force_reanalyze,
    )

    # Parse existing XSQ
    doc = parse_xsq(existing_xsq)

    # Parse layout and classify props
    layout = parse_layout(config.layout_path)
    props = layout.props
    normalize_coords(props)
    classify_props(props)
    groups = generate_groups(props)

    # Load libraries
    from src.variants.library import load_variant_library

    effect_library = load_effect_library()
    variant_library = load_variant_library(effect_library=effect_library)
    theme_library = load_theme_library(effect_library=effect_library, variant_library=variant_library)

    # Derive section energies
    section_energies = derive_section_energies(
        hierarchy.sections, hierarchy.energy_curves, hierarchy.energy_impacts,
        song_duration_ms=hierarchy.duration_ms,
    )

    # Find target sections and remove their effects
    target_labels = set(config.target_sections or [])
    for se in section_energies:
        if se.label in target_labels:
            remove_effects_in_range(doc, se.start_ms, se.end_ms)

    # Rebuild only the target sections
    profile = read_song_metadata(config.audio_path, hierarchy)
    profile.genre = config.genre
    profile.occasion = config.occasion

    target_section_energies = [s for s in section_energies if s.label in target_labels]
    ef_regen = hierarchy.essentia_features or {}
    assignments = select_themes(
        target_section_energies, theme_library, config.genre, config.occasion,
        scale=ef_regen.get("scale"),
        base_variation_seed=config.variation_seed,
    )

    # Build rotation plan for regenerated sections
    variant_library = None
    rotation_plan = None
    try:
        from src.variants.library import load_variant_library

        variant_library = load_variant_library(effect_library=effect_library)
        rotation_engine = RotationEngine(variant_library, effect_library)
        rotation_plan = rotation_engine.build_rotation_plan(
            sections=[a.section for a in assignments],
            groups=groups,
            theme_assignments=assignments,
        )
    except Exception:
        logger.debug("Variant library unavailable — falling back to pool rotation")

    # Derive per-theme working sets when focused_vocabulary is enabled, same as
    # `build_plan` step 3c.
    from src.generator.effect_placer import derive_working_set
    working_sets: dict = {}
    if config.focused_vocabulary and variant_library is not None:
        for assignment in assignments:
            theme_name = assignment.theme.name
            if theme_name not in working_sets:
                working_sets[theme_name] = derive_working_set(assignment.theme, variant_library)

    # Precompute per-section decisions on each assignment, then place using the
    # same assignment-driven path as `build_plan` (spec 048, FR-023).
    _populate_assignment_decisions(assignments, config, hierarchy, working_sets)
    for assignment in assignments:
        group_effects = place_effects(
            assignment, groups, effect_library, hierarchy,
            variant_library=variant_library,
            rotation_plan=rotation_plan,
        )
        assignment.group_effects = group_effects

        curves_mode = getattr(config, "curves_mode", "none")
        for placements in group_effects.values():
            for placement in placements:
                effect_def = effect_library.effects.get(placement.effect_name)
                if effect_def:
                    curves = generate_value_curves(
                        placement, effect_def, hierarchy, curves_mode
                    )
                    storage = {p.name: p.storage_name for p in effect_def.parameters}
                    placement.value_curves = {storage.get(k, k): v for k, v in curves.items()}

    # Merge new effects into the document
    for assignment in assignments:
        for group_name, placements in assignment.group_effects.items():
            doc.element_effects.setdefault(group_name, []).extend(placements)
            if group_name not in doc.display_elements:
                doc.display_elements.append(group_name)

    # Build a plan with a single synthetic section carrying all merged effects
    synthetic = SectionAssignment(
        section=SectionEnergy(
            label="full", start_ms=0, end_ms=hierarchy.duration_ms,
            energy_score=50, mood_tier="structural", impact_count=0,
        ),
        theme=assignments[0].theme if assignments else list(theme_library.themes.values())[0],
        group_effects=dict(doc.element_effects),
    )
    plan = SequencePlan(
        song_profile=profile,
        sections=[synthetic],
        layout_groups=groups,
        models=[p.name for p in props],
    )

    write_xsq(plan, existing_xsq)
    return existing_xsq
