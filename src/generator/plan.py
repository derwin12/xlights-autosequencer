"""Plan builder — orchestrates the full sequence generation pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

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
    compute_duration_target,
    place_effects,
    restrain_palette,
)
from src.generator.energy import derive_section_energies
from src.generator.rotation import RotationEngine
from src.generator.transitions import TransitionConfig, apply_transitions
from src.story.builder import load_song_story
from src.generator.models import (
    AccentPolicy,
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
from src.grouper.layout import Prop, parse_layout
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
    )

    # Apply theme overrides if specified
    if config.theme_overrides:
        for idx, theme_name in config.theme_overrides.items():
            if 0 <= idx < len(assignments):
                theme = theme_library.themes.get(theme_name)
                if theme is not None:
                    assignments[idx].theme = theme

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

    # 5. Place effects for each section.  `place_effects` reads every per-section
    # decision off the assignment fields populated above.
    model_names = [p.name for p in props]
    props_by_name = {p.name: p for p in props}
    for assignment in assignments:
        group_effects = place_effects(
            assignment, groups, effect_library, hierarchy,
            variant_library=variant_library,
            rotation_plan=rotation_plan,
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

    # 7. Assemble plan
    return SequencePlan(
        song_profile=profile,
        sections=assignments,
        layout_groups=groups,
        models=model_names,
        rotation_plan=rotation_plan,
    )


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
    for idx, assignment in enumerate(assignments):
        section = assignment.section
        assignment.section_index = idx

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
        assignment.accent_policy = AccentPolicy(drum_hits=drum_ok, impact=impact_ok)

        # Working set — per-theme reference, shared across sections using the same theme.
        assignment.working_set = (
            working_sets.get(assignment.theme.name) if config.focused_vocabulary else None
        )


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
    plan = build_plan(config, hierarchy, props, groups, effect_library, theme_library)

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
