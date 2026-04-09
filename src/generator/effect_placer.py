"""Effect placement engine — maps theme layers to power groups and timing tracks."""
from __future__ import annotations

import logging
import random
from typing import Any

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.effects.library import EffectLibrary
from src.generator.rotation import RotationPlan
from src.effects.models import VALID_DURATION_TYPES, EffectDefinition
from src.generator.chord_colors import (
    adjust_palette_brightness,
    blend_palettes,
    build_tension_curve,
    generate_chord_palette,
    tension_at_time,
)
from src.generator.models import (
    FRAME_INTERVAL_MS,
    EffectPlacement,
    SectionAssignment,
    SectionEnergy,
    frame_align,
)
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer

logger = logging.getLogger(__name__)


# Tier ranges for layer-to-group mapping
_LOW_TIERS = {1, 2}        # base, geo
_MID_TIERS = {3, 4, 5, 6}  # type, beat, fidelity, prop

# Brightness multiplier per tier — low tiers are background, high tiers pop
_TIER_BRIGHTNESS: dict[int, float] = {
    1: 0.40,   # BASE: dim backdrop
    2: 0.40,   # GEO: dim backdrop
}


def _dim_palette(palette: list[str], multiplier: float) -> list[str]:
    """Scale hex color brightness by multiplier (0.0-1.0)."""
    result = []
    for color in palette:
        c = color.lstrip("#")
        if len(c) == 6:
            r = int(int(c[0:2], 16) * multiplier)
            g = int(int(c[2:4], 16) * multiplier)
            b = int(int(c[4:6], 16) * multiplier)
            result.append(f"#{r:02X}{g:02X}{b:02X}")
        else:
            result.append(color)
    return result


def _lighten_palette(palette: list[str], amount: float) -> list[str]:
    """Lighten hex colors by blending toward white. amount 0.0=no change, 1.0=white."""
    result = []
    for color in palette:
        c = color.lstrip("#")
        if len(c) == 6:
            r = int(int(c[0:2], 16) + (255 - int(c[0:2], 16)) * amount)
            g = int(int(c[2:4], 16) + (255 - int(c[2:4], 16)) * amount)
            b = int(int(c[4:6], 16) + (255 - int(c[4:6], 16)) * amount)
            result.append(f"#{r:02X}{g:02X}{b:02X}")
        else:
            result.append(color)
    return result

_HIGH_TIERS = {7, 8}       # compound, hero

# Effects that default to Rainbow but should use Palette when we provide colors.
# Maps effect name -> parameter storage_name -> value to force.
_FORCE_PALETTE_PARAMS: dict[str, dict[str, str]] = {
    "Butterfly": {"E_CHOICE_Butterfly_Colors": "Palette"},
    "Meteors": {"E_CHOICE_Meteors_Type": "Palette", "E_CHOICE_Meteors_Effect": "Down"},
    "Single Strand": {"E_CHOICE_SingleStrand_Colors": "Palette"},
    "Wave": {"E_CHOICE_Wave_FillColor": "Color 1", "E_CHOICE_Wave_Direction": "Right to Left"},
    "Bars": {"E_CHOICE_Bars_Direction": "Left"},
    "Fire": {"E_CHECKBOX_Fire_GrowWithMusic": "0"},
    "Garlands": {"E_CHOICE_Garlands_Type": "Palette"},
    "Spirals": {"E_CHOICE_Spirals_Direction": "Up"},
    "Curtain": {"E_CHOICE_Curtain_Effect": "open"},
    "Liquid": {"E_CHOICE_ParticleType": "Elastic"},
}

# Direction parameters that should alternate between instances.
# Maps storage_name -> [even_value, odd_value]
_ALTERNATING_DIRECTIONS: dict[str, list[str]] = {
    "E_CHOICE_Bars_Direction": ["Left", "Right", "expand", "compress"],
    "E_CHOICE_Spirals_Direction": ["Up", "Down"],
    "E_CHOICE_Meteors_Effect": ["Down", "Up", "Left", "Right"],
    "E_CHOICE_Curtain_Effect": ["open", "close", "open then close", "close then open"],
    "E_CHOICE_Curtain_Edge": ["center", "left", "right", "bottom", "top"],
    "E_CHOICE_Wave_Direction": ["Right to Left", "Left to Right"],
    "E_CHOICE_Chase_Type1": [
        "Left-Right", "Right-Left", "From Middle", "To Middle",
        "Bounce from Left", "Bounce from Right", "Dual Chase",
    ],
    "E_CHOICE_Skips_Direction": ["Left", "Right", "From Middle", "To Middle"],
    "E_CHOICE_Ripple_Movement": ["Explode", "Implode"],
    "E_CHOICE_Fire_Location": ["Bottom", "Top", "Left", "Right"],
    "E_CHOICE_Fill_Direction": ["Up", "Down", "Left", "Right"],
}

# Effects suitable for tier 6 (PROP) and tier 7 (COMP) rotation.
# These are punchy, visually distinct effects that look good on individual props.
_PROP_EFFECT_POOL: list[str] = [
    "Meteors", "Single Strand", "Ripple", "Spirals", "Bars",
    "Curtain", "Shockwave", "Fire", "Strobe", "Galaxy",
]


def _build_effect_pool(
    effect_library: EffectLibrary,
    exclude: set[str] | None = None,
) -> list[EffectDefinition]:
    """Return EffectDefinition objects for the prop-effect pool, minus exclusions."""
    exclude = exclude or set()
    pool = []
    for name in _PROP_EFFECT_POOL:
        if name in exclude:
            continue
        edef = effect_library.effects.get(name)
        if edef is not None:
            pool.append(edef)
    return pool


def place_effects(
    assignment: SectionAssignment,
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    hierarchy: HierarchyResult,
    tiers: set[int] | None = None,
    variant_library=None,
    rotation_plan: RotationPlan | None = None,
    section_index: int = 0,
) -> dict[str, list[EffectPlacement]]:
    """Place effects from theme layers onto power groups, aligned to timing tracks.

    Layer-to-tier mapping:
    - Bottom layer(s) -> tiers 1-2 (base/geo groups)
    - Middle layer(s) -> tiers 3-6 (type/beat/fidelity/prop groups)
    - Top layer(s) -> tiers 7-8 (compound/hero groups)

    When chord data is available (L6 Harmony), palettes are blended with
    chord-derived colors and brightness is modulated by harmonic tension.

    Returns: group_name -> list of EffectPlacement
    """
    section = assignment.section
    theme = assignment.theme

    # Use alternate layers for repeated sections (variation_seed > 0)
    if assignment.variation_seed > 0 and theme.alternates:
        variant_idx = (assignment.variation_seed - 1) % len(theme.alternates)
        layers = theme.alternates[variant_idx].layers
    else:
        layers = theme.layers

    if not layers:
        return {}

    # Build chord/tension data if available
    chord_marks = None
    tension_curve = None
    if hierarchy.chords and hierarchy.chords.marks:
        chord_marks = hierarchy.chords.marks
        tension_curve = build_tension_curve(chord_marks, hierarchy.duration_ms)

    # Extract essentia features if available
    ef = hierarchy.essentia_features or {}
    danceability = ef.get("danceability")

    # Adaptive chord weight: songs with rich harmony get more chord-color
    # influence; simple I-IV-V songs rely more on theme palette.
    # 40 unique chords → 0.50 (max), 10 unique → 0.12, 0 → 0.0
    chord_weight = 0.0
    if chord_marks:
        unique_chords = len({m.label for m in chord_marks if m.label and m.label != "N"})
        chord_weight = min(0.50, unique_chords / 80.0)

    # Accent palette: explicit or auto-lightened from main palette
    accent = theme.accent_palette if theme.accent_palette else _lighten_palette(theme.palette, 0.5)

    # Background palette: dimmed for tiers 1-2
    bg_palette = _dim_palette(theme.palette, 0.40)

    # Detect drop/impact phase from section label (chorus, drop, bridge, etc.)
    section_label = (section.label or "").lower()
    is_high_energy = any(kw in section_label for kw in ("chorus", "drop", "hook", "climax"))

    # Map layers to tier sets
    layer_tier_map = _assign_layers_to_tiers(layers)

    # Group groups by tier, filtering to requested tiers if specified
    tier_groups: dict[int, list[PowerGroup]] = {}
    for g in groups:
        if tiers is not None and g.tier not in tiers:
            continue
        tier_groups.setdefault(g.tier, []).append(g)

    # If no groups provided, create a pseudo-group for each model
    if not groups:
        return _flat_model_fallback(assignment, effect_library, hierarchy, variant_library=variant_library)

    result: dict[str, list[EffectPlacement]] = {}

    for layer_idx, layer in enumerate(layers):
        # Resolve variant → effect_def
        layer_variant = variant_library.get(layer.variant) if variant_library is not None else None
        if layer_variant is None:
            logger.warning("variant '%s' not found in variant library — skipping layer", layer.variant)
            continue
        effect_def = effect_library.effects.get(layer_variant.base_effect)
        if effect_def is None:
            continue

        target_tiers = layer_tier_map.get(layer_idx, set())
        selected = _select_groups_for_layer(
            target_tiers, tier_groups, layer_idx, len(layers),
        )

        for tier, groups_for_tier in selected.items():
            # Per-tier palette selection
            if tier in _TIER_BRIGHTNESS:
                # Tiers 1-2: dim background
                tier_palette = bg_palette
            elif tier >= 3:
                # Tiers 3+: use accent palette for punch
                tier_palette = accent
            else:
                tier_palette = theme.palette

            # Tier 5-8: use rotation plan when available
            if tier in (5, 6, 7, 8) and groups_for_tier and rotation_plan is not None:
                for group in groups_for_tier:
                    entry = rotation_plan.lookup(section_index, group.name)
                    if entry is None:
                        continue
                    rotated_def = effect_library.effects.get(entry.base_effect)
                    if rotated_def is None:
                        continue
                    # Look up variant for parameter overrides
                    variant = None
                    if variant_library is not None:
                        variant = variant_library.get(entry.variant_name)
                    rot_params: dict[str, Any] = {}
                    rot_direction_cycle = None
                    if variant is not None:
                        rot_params = dict(variant.parameter_overrides)
                        rot_direction_cycle = variant.direction_cycle
                    rot_placements = _place_effect_on_group(
                        effect_def=rotated_def,
                        layer=layer,
                        group=group,
                        section=assignment.section,
                        hierarchy=hierarchy,
                        palette=tier_palette,
                        variation_seed=assignment.variation_seed,
                        chord_marks=chord_marks,
                        tension_curve=tension_curve,
                        danceability=danceability,
                        chord_weight=chord_weight,
                        variant_library=None,  # already resolved
                    )
                    # Override params from variant
                    for p in rot_placements:
                        p.parameters.update(rot_params)
                    # Apply direction cycle from variant
                    if rot_direction_cycle is not None:
                        dc_param = rot_direction_cycle.get("param", "")
                        dc_values = rot_direction_cycle.get("values", [])
                        dc_mode = rot_direction_cycle.get("mode", "alternate")
                        if dc_param and dc_values:
                            for pi, p in enumerate(rot_placements):
                                if dc_mode == "random":
                                    p.parameters[dc_param] = dc_values[
                                        hash((pi, dc_param)) % len(dc_values)
                                    ]
                                else:
                                    p.parameters[dc_param] = dc_values[pi % len(dc_values)]
                    if rot_placements:
                        result.setdefault(group.name, []).extend(rot_placements)
                continue

            # Tier 6-7 effect rotation (fallback): cycle through prop-effect pool
            if tier in (6, 7) and groups_for_tier:
                pool = _build_effect_pool(effect_library, exclude={layer_variant.base_effect})
                if pool:
                    for gi, group in enumerate(groups_for_tier):
                        rotated_def = pool[gi % len(pool)]
                        rot_placements = _place_effect_on_group(
                            effect_def=rotated_def,
                            layer=layer,
                            group=group,
                            section=assignment.section,
                            hierarchy=hierarchy,
                            palette=tier_palette,
                            variation_seed=assignment.variation_seed,
                            chord_marks=chord_marks,
                            tension_curve=tension_curve,
                            danceability=danceability,
                            chord_weight=chord_weight,
                            variant_library=variant_library,
                        )
                        if rot_placements:
                            result.setdefault(group.name, []).extend(rot_placements)
                    continue

            # Tier 4 (BEAT): use chase pattern — distribute beats across groups
            if tier == 4 and groups_for_tier:
                chase_result = _place_chase_across_groups(
                    effect_def, layer, groups_for_tier,
                    assignment.section, hierarchy, tier_palette,
                    variant_library=variant_library,
                )
                for gname, placements in chase_result.items():
                    result.setdefault(gname, []).extend(placements)
                continue

            for group in groups_for_tier:
                placements = _place_effect_on_group(
                    effect_def=effect_def,
                    layer=layer,
                    group=group,
                    section=assignment.section,
                    hierarchy=hierarchy,
                    palette=tier_palette,
                    variation_seed=assignment.variation_seed,
                    chord_marks=chord_marks,
                    tension_curve=tension_curve,
                    danceability=danceability,
                    chord_weight=chord_weight,
                    variant_library=variant_library,
                )
                if placements:
                    result.setdefault(group.name, []).extend(placements)

    return result


def _select_groups_for_layer(
    target_tiers: set[int],
    tier_groups: dict[int, list[PowerGroup]],
    layer_idx: int,
    total_layers: int,
) -> dict[int, list[PowerGroup]]:
    """Select which groups to use per tier, avoiding overlap.

    Strategy per tier:
    - Tier 1 (BASE): Use the single whole-house group only for the bottom layer
    - Tier 2 (GEO): Pick one spatial zone for accent variety
    - Tier 3 (TYPE): Skip — overlaps too heavily with BASE
    - Tier 4 (BEAT): All groups (chase pattern handled separately)
    - Tier 5 (TEX): Skip — overlaps with BASE
    - Tier 6 (PROP): Pick 2-3 prop-type groups for targeted effects
    - Tier 7 (COMP): Pick 2-3 compound groups for layered fixture effects
    - Tier 8 (HERO): Pick one hero for spotlight
    """
    selected: dict[int, list[PowerGroup]] = {}

    for tier in sorted(target_tiers):
        available = tier_groups.get(tier, [])
        if not available:
            continue

        if tier == 1:
            # BASE: just the whole-house group, only for bottom layer
            if layer_idx == 0:
                selected[tier] = [available[0]]

        elif tier == 2:
            # GEO: use all spatial zones
            selected[tier] = available

        elif tier in (3, 5):
            # TYPE / TEX: skip to avoid overlap with BASE
            pass

        elif tier == 4:
            # BEAT: all groups — chase logic handles round-robin
            selected[tier] = available

        elif tier == 6:
            # PROP: all prop-type groups
            selected[tier] = available

        elif tier == 7:
            # COMP: all compound groups
            selected[tier] = available

        elif tier == 8:
            # HERO: pick one
            selected[tier] = [available[layer_idx % len(available)]]

    return selected


def _assign_layers_to_tiers(layers: list[EffectLayer]) -> dict[int, set[int]]:
    """Map each layer index to a set of target tiers."""
    n = len(layers)
    mapping: dict[int, set[int]] = {}

    if n == 1:
        mapping[0] = _LOW_TIERS | {4, 6}
    elif n == 2:
        mapping[0] = _LOW_TIERS | {4, 6}
        mapping[1] = _HIGH_TIERS
    else:
        mapping[0] = _LOW_TIERS | {4, 6}
        mapping[n - 1] = _HIGH_TIERS
        for i in range(1, n - 1):
            mapping[i] = _MID_TIERS

    return mapping


def _place_effect_on_group(
    effect_def: EffectDefinition,
    layer: EffectLayer,
    group: PowerGroup,
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    palette: list[str],
    variation_seed: int = 0,
    chord_marks: list[TimingMark] | None = None,
    tension_curve: list[tuple[int, int]] | None = None,
    danceability: float | None = None,
    chord_weight: float = 0.4,
    variant_library=None,
) -> list[EffectPlacement]:
    """Create effect placement instances for a group within a section."""
    start_ms = section.start_ms
    end_ms = section.end_ms
    duration_type = effect_def.duration_type

    # Resolve parameters from the variant (variant exclusively owns parameter config)
    params: dict[str, Any] = {}
    direction_cycle: dict | None = None
    if variant_library is not None:
        variant = variant_library.get(layer.variant)
        if variant is not None:
            params = dict(variant.parameter_overrides)
            direction_cycle = variant.direction_cycle

    # Resolve palette: blend with chord colors if available
    resolved_palette = _resolve_palette(palette, chord_marks, tension_curve, start_ms, end_ms, chord_weight)

    if duration_type == "section":
        return [_make_placement(
            effect_def, group.name, start_ms, end_ms,
            params, resolved_palette, layer.blend_mode, duration_type,
            direction_cycle=direction_cycle,
        )]

    elif duration_type == "bar":
        return _place_per_bar(
            effect_def, group.name, section, hierarchy,
            params, resolved_palette, layer.blend_mode,
            chord_marks=chord_marks, tension_curve=tension_curve,
            chord_weight=chord_weight, direction_cycle=direction_cycle,
        )

    elif duration_type == "beat":
        return _place_per_beat(
            effect_def, group.name, section, hierarchy,
            params, resolved_palette, layer.blend_mode,
            chord_marks=chord_marks, tension_curve=tension_curve,
            danceability=danceability, chord_weight=chord_weight,
            direction_cycle=direction_cycle,
        )

    elif duration_type == "trigger":
        return _place_per_trigger(
            effect_def, group.name, section, hierarchy,
            params, resolved_palette, layer.blend_mode,
            direction_cycle=direction_cycle,
        )

    return [_make_placement(
        effect_def, group.name, start_ms, end_ms,
        params, resolved_palette, layer.blend_mode, "section",
        direction_cycle=direction_cycle,
    )]


def _place_chase_across_groups(
    effect_def: EffectDefinition,
    layer: EffectLayer,
    groups: list[PowerGroup],
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    palette: list[str],
    variant_library=None,
) -> dict[str, list[EffectPlacement]]:
    """Chase pattern: assign each beat to one group in round-robin order.

    Beat 1 -> group 0, beat 2 -> group 1, ..., beat N -> group N % len(groups).
    Each group only lights up on "its" beats, creating a chase effect.
    """
    beats_track = hierarchy.beats
    if beats_track is None:
        return {}

    marks = _marks_in_range(beats_track.marks, section.start_ms, section.end_ms)
    marks = _apply_density_filter(marks, section.energy_score)

    params: dict[str, Any] = {}
    if variant_library is not None:
        variant = variant_library.get(layer.variant)
        if variant is not None:
            params = dict(variant.parameter_overrides)
    result: dict[str, list[EffectPlacement]] = {}
    num_groups = len(groups)

    for i, mark in enumerate(marks):
        group = groups[i % num_groups]
        beat_start = mark.time_ms
        beat_end = marks[i + 1].time_ms if i + 1 < len(marks) else min(
            beat_start + 500, section.end_ms
        )
        if beat_end <= beat_start:
            continue

        placement = _make_placement(
            effect_def, group.name, beat_start, beat_end,
            params, palette, layer.blend_mode, "beat",
            instance_index=i,
        )
        result.setdefault(group.name, []).append(placement)

    return result


def _resolve_palette(
    theme_palette: list[str],
    chord_marks: list[TimingMark] | None,
    tension_curve: list[tuple[int, int]] | None,
    start_ms: int,
    end_ms: int,
    chord_weight: float = 0.4,
) -> list[str]:
    """Blend theme palette with chord colors and apply tension brightness."""
    if not chord_marks or chord_weight <= 0:
        return theme_palette

    chord_pal = generate_chord_palette(chord_marks, start_ms, end_ms)
    blended = blend_palettes(theme_palette, chord_pal, chord_weight=chord_weight)

    if tension_curve:
        mid_ms = (start_ms + end_ms) // 2
        tension = tension_at_time(tension_curve, mid_ms)
        blended = adjust_palette_brightness(blended, tension)

    return blended


def _place_per_bar(
    effect_def: EffectDefinition, group_name: str, section: SectionEnergy,
    hierarchy: HierarchyResult, params: dict[str, Any],
    palette: list[str], blend_mode: str,
    chord_marks: list[TimingMark] | None = None,
    tension_curve: list[tuple[int, int]] | None = None,
    chord_weight: float = 0.4,
    direction_cycle: dict | None = None,
) -> list[EffectPlacement]:
    """Place one effect instance per bar within the section."""
    bars_track = hierarchy.bars
    if bars_track is None:
        return [_make_placement(
            effect_def, group_name, section.start_ms, section.end_ms,
            params, palette, blend_mode, "section",
        )]

    marks = _marks_in_range(bars_track.marks, section.start_ms, section.end_ms)
    placements = []
    for i, mark in enumerate(marks):
        bar_start = mark.time_ms
        bar_end = marks[i + 1].time_ms if i + 1 < len(marks) else section.end_ms
        if bar_end <= bar_start:
            continue
        bar_palette = _resolve_palette(palette, chord_marks, tension_curve, bar_start, bar_end, chord_weight)
        placements.append(_make_placement(
            effect_def, group_name, bar_start, bar_end,
            params, bar_palette, blend_mode, "bar",
            instance_index=i, direction_cycle=direction_cycle,
        ))
    return placements


def _place_per_beat(
    effect_def: EffectDefinition, group_name: str, section: SectionEnergy,
    hierarchy: HierarchyResult, params: dict[str, Any],
    palette: list[str], blend_mode: str,
    chord_marks: list[TimingMark] | None = None,
    tension_curve: list[tuple[int, int]] | None = None,
    danceability: float | None = None,
    chord_weight: float = 0.4,
    direction_cycle: dict | None = None,
) -> list[EffectPlacement]:
    """Place effect instances per beat, subject to energy-driven density."""
    beats_track = hierarchy.beats
    if beats_track is None:
        return [_make_placement(
            effect_def, group_name, section.start_ms, section.end_ms,
            params, palette, blend_mode, "section",
        )]

    marks = _marks_in_range(beats_track.marks, section.start_ms, section.end_ms)
    marks = _apply_density_filter(marks, section.energy_score, danceability=danceability)

    placements = []
    for i, mark in enumerate(marks):
        beat_start = mark.time_ms
        beat_end = marks[i + 1].time_ms if i + 1 < len(marks) else min(
            beat_start + 500, section.end_ms
        )
        if beat_end <= beat_start:
            continue
        beat_palette = _resolve_palette(palette, chord_marks, tension_curve, beat_start, beat_end, chord_weight)
        placements.append(_make_placement(
            effect_def, group_name, beat_start, beat_end,
            params, beat_palette, blend_mode, "beat",
            instance_index=i, direction_cycle=direction_cycle,
        ))
    return placements


def _place_per_trigger(
    effect_def: EffectDefinition, group_name: str, section: SectionEnergy,
    hierarchy: HierarchyResult, params: dict[str, Any],
    palette: list[str], blend_mode: str,
    direction_cycle: dict | None = None,
) -> list[EffectPlacement]:
    """Place one-shot effect instances on onset/impact events."""
    events_track = None
    for track in hierarchy.events.values():
        events_track = track
        break

    if events_track is None:
        return []

    marks = _marks_in_range(events_track.marks, section.start_ms, section.end_ms)
    placements = []
    for i, mark in enumerate(marks):
        trigger_start = mark.time_ms
        trigger_end = trigger_start + (mark.duration_ms or 100)
        trigger_end = min(trigger_end, section.end_ms)
        if trigger_end <= trigger_start:
            continue
        placements.append(_make_placement(
            effect_def, group_name, trigger_start, trigger_end,
            params, palette, blend_mode, "trigger",
            instance_index=i, direction_cycle=direction_cycle,
        ))
    return placements


def _make_placement(
    effect_def: EffectDefinition,
    group_name: str,
    start_ms: int,
    end_ms: int,
    params: dict[str, Any],
    palette: list[str],
    blend_mode: str,
    duration_type: str,
    instance_index: int = 0,
    direction_cycle: dict | None = None,
) -> EffectPlacement:
    """Create a single EffectPlacement with appropriate fades."""
    fade_in, fade_out = _calculate_fades(duration_type, end_ms - start_ms)

    # Force palette mode for effects that default to Rainbow
    resolved_params = dict(params)
    forced = _FORCE_PALETTE_PARAMS.get(effect_def.name, {})
    for key, val in forced.items():
        if key not in resolved_params:
            resolved_params[key] = val

    # Apply variant-defined direction cycling (takes precedence over hardcoded)
    if direction_cycle is not None:
        dc_param = direction_cycle.get("param", "")
        dc_values = direction_cycle.get("values", [])
        dc_mode = direction_cycle.get("mode", "alternate")
        if dc_param and dc_values:
            if dc_mode == "random":
                resolved_params[dc_param] = dc_values[
                    hash((instance_index, dc_param)) % len(dc_values)
                ]
            else:  # "alternate"
                resolved_params[dc_param] = dc_values[instance_index % len(dc_values)]
    else:
        # Fallback: hardcoded direction alternation for effects without variant cycle
        for key, directions in _ALTERNATING_DIRECTIONS.items():
            if key in resolved_params:
                resolved_params[key] = directions[instance_index % len(directions)]

        # Single Strand: alternate chase direction between instances
        if effect_def.name == "Single Strand":
            chase_key = "E_CHOICE_Chase_Type1"
            resolved_params[chase_key] = ["Left-Right", "Right-Left"][instance_index % 2]

    return EffectPlacement(
        effect_name=effect_def.name,
        xlights_id=effect_def.xlights_id,
        model_or_group=group_name,
        start_ms=start_ms,
        end_ms=end_ms,
        parameters=resolved_params,
        color_palette=palette,
        blend_mode=blend_mode,
        fade_in_ms=fade_in,
        fade_out_ms=fade_out,
    )


def _calculate_fades(duration_type: str, duration_ms: int) -> tuple[int, int]:
    """Calculate fade in/out based on duration type.

    No explicit fades — xLights manages transitions internally.
    Writing fade params causes xLights to strip and recalculate them on save,
    which changes the EffectDB and prevents clean round-trips.
    """
    return 0, 0


def _marks_in_range(
    marks: list[TimingMark], start_ms: int, end_ms: int
) -> list[TimingMark]:
    """Filter timing marks to those within a time range."""
    return [m for m in marks if start_ms <= m.time_ms < end_ms]


def _apply_density_filter(
    marks: list[TimingMark], energy_score: int,
    danceability: float | None = None,
) -> list[TimingMark]:
    """Filter marks based on energy-driven density.

    High energy (80+): use ~90% of marks
    Low energy (20): use ~50% of marks
    Linear interpolation between.

    If danceability is available (from essentia), high danceability (>1.0)
    boosts density by up to +0.10 — songs with strong rhythmic drive
    benefit from more beat-synced effects.
    """
    if not marks:
        return marks

    # Map energy 0-100 to density 0.5-0.9
    density = 0.5 + (energy_score / 100.0) * 0.4

    # Danceability boost: 0.0->+0.00, 1.0->+0.05, 2.0->+0.10
    if danceability is not None and danceability > 0:
        boost = min(0.10, danceability * 0.05)
        density += boost

    density = max(0.5, min(0.95, density))

    if density >= 0.95:
        return marks

    # Deterministic selection using step-based skipping
    keep_count = max(1, int(len(marks) * density))
    step = len(marks) / keep_count
    return [marks[int(i * step)] for i in range(keep_count)]



def _flat_model_fallback(
    assignment: SectionAssignment,
    effect_library: EffectLibrary,
    hierarchy: HierarchyResult,
    variant_library=None,
) -> dict[str, list[EffectPlacement]]:
    """Fallback when no power groups exist — distribute across models directly."""
    theme = assignment.theme
    section = assignment.section
    result: dict[str, list[EffectPlacement]] = {}

    # Use alternate layers for repeated sections
    if assignment.variation_seed > 0 and theme.alternates:
        variant_idx = (assignment.variation_seed - 1) % len(theme.alternates)
        layers = theme.alternates[variant_idx].layers
    else:
        layers = theme.layers

    if not layers:
        return result

    layer = layers[0]
    layer_variant = variant_library.get(layer.variant) if variant_library is not None else None
    if layer_variant is None:
        return result
    effect_def = effect_library.effects.get(layer_variant.base_effect)
    if effect_def is None:
        return result

    # Use a synthetic group with no members (direct placement)
    placement = _make_placement(
        effect_def, "ALL_MODELS", section.start_ms, section.end_ms,
        dict(layer_variant.parameter_overrides), theme.palette, layer.blend_mode,
        effect_def.duration_type,
    )
    result["ALL_MODELS"] = [placement]
    return result
