"""Plan builder — orchestrates the full sequence generation pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.analyzer.result import HierarchyResult
from src.effects.library import EffectLibrary, load_effect_library
from src.generator.effect_placer import place_effects
from src.generator.energy import derive_section_energies
from src.generator.models import (
    GenerationConfig,
    SectionAssignment,
    SectionEnergy,
    SequencePlan,
    SongProfile,
)
from src.generator.theme_selector import select_themes
from src.generator.value_curves import generate_value_curves
from src.generator.xsq_writer import write_xsq
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

    # 2. Derive section energies (dynamic complexity + LUFS normalization)
    ef = hierarchy.essentia_features or {}
    section_energies = derive_section_energies(
        hierarchy.sections,
        hierarchy.energy_curves,
        hierarchy.energy_impacts,
        dynamic_complexity=ef.get("dynamic_complexity"),
        loudness_lufs=ef.get("loudness_lufs"),
    )

    # 3. Select themes (key/scale can infer mood automatically)
    inferred_genre = config.genre
    inferred_occasion = config.occasion

    # Auto-infer mood-appropriate genre from essentia key analysis
    if inferred_genre == "pop" and ef.get("scale"):
        # If user didn't explicitly set genre, let the key/scale inform it
        if ef["scale"] == "minor" and ef.get("key_strength", 0) > 0.6:
            inferred_genre = "classical"  # minor key → favor darker themes

    assignments = select_themes(
        section_energies, theme_library, inferred_genre, inferred_occasion,
        scale=ef.get("scale"),
    )

    # Apply theme overrides if specified
    if config.theme_overrides:
        for idx, theme_name in config.theme_overrides.items():
            if 0 <= idx < len(assignments):
                theme = theme_library.themes.get(theme_name)
                if theme is not None:
                    assignments[idx].theme = theme

    # 4. Place effects for each section
    model_names = [p.name for p in props]
    for assignment in assignments:
        group_effects = place_effects(
            assignment, groups, effect_library, hierarchy
        )
        assignment.group_effects = group_effects

    # 5. Value curves — disabled for phase 1 (static parameters only).
    # Will be re-enabled once base layer rendering is validated in xLights.

    # 6. Assemble plan
    return SequencePlan(
        song_profile=profile,
        sections=assignments,
        layout_groups=groups,
        models=model_names,
    )


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

    # Parse layout
    layout = parse_layout(config.layout_path)
    props = layout.props

    # Generate power groups
    groups = generate_groups(props)

    # Load libraries
    effect_library = load_effect_library()
    theme_library = load_theme_library(effect_library=effect_library)

    # Build plan
    plan = build_plan(config, hierarchy, props, groups, effect_library, theme_library)

    # Write XSQ with timing tracks
    output_name = config.audio_path.stem + ".xsq"
    output_path = config.output_dir / output_name
    write_xsq(plan, output_path, hierarchy=hierarchy)

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

    # Parse layout
    layout = parse_layout(config.layout_path)
    props = layout.props
    groups = generate_groups(props)

    # Load libraries
    effect_library = load_effect_library()
    theme_library = load_theme_library(effect_library=effect_library)

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

    for assignment in assignments:
        group_effects = place_effects(assignment, groups, effect_library, hierarchy)
        assignment.group_effects = group_effects

        for placements in group_effects.values():
            for placement in placements:
                effect_def = effect_library.effects.get(placement.effect_name)
                if effect_def:
                    placement.value_curves = generate_value_curves(
                        placement, effect_def, hierarchy
                    )

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
