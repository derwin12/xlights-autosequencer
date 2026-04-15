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
    DurationTarget,
    EffectPlacement,
    SectionAssignment,
    SectionEnergy,
    WorkingSet,
    WorkingSetEntry,
    frame_align,
)
from src.grouper.grouper import PowerGroup
from src.grouper.layout import prop_type_for_display_as
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

# GEO axis classification — horizontal slices vs vertical slices.
# A prop can belong to one group from each axis (e.g. GEO_Top AND GEO_Left),
# so only one axis should be active at a time to avoid overrides.
_GEO_HORIZONTAL = {"02_GEO_Top", "02_GEO_Mid", "02_GEO_Bot"}
_GEO_VERTICAL = {"02_GEO_Left", "02_GEO_Center", "02_GEO_Right"}

# GEO call-and-response partitioning.  When Tier 2 is active, phrases alternate
# between the "call" side (Left + Top quadrants) and the "answer" side
# (Right + Bottom quadrants).  Center/Mid zones are excluded — they overlap
# with both sides spatially, so keeping them quiet yields a cleaner
# call/response read.
_GEO_CALL_SIDE = frozenset({"02_GEO_Left", "02_GEO_Top"})
_GEO_ANSWER_SIDE = frozenset({"02_GEO_Right", "02_GEO_Bot"})

# Phrase length in bars for call-response alternation and phrase-structure
# detection.  4 bars is the standard pop/orchestral phrase length.
_PHRASE_LEN_BARS = 4

# Pearson-correlation threshold on bar-sampled energy at lag = phrase length.
# Above this, the section is considered to have strong periodic phrase structure
# (the pre-condition for GEO call-response to feel musically grounded).
# 0.7 is calibrated after visual inspection on MRC — 0.5 fired GEO too eagerly,
# producing a blocky look on sections without clear call-response character.
_MIN_PHRASE_CORRELATION = 0.7

# Effects that read as geometric rectangles on bounding-box groups (GEO, COMP).
# They look fine on individual props (linear strings, arches, single trees) but
# awkward when xLights renders them across the bounding box of dissimilar props.
_BLOCKY_ON_BOUNDING_BOX: frozenset[str] = frozenset({
    "Bars", "Curtain", "Single Strand",
})

# Fallback effects to substitute when a theme's layer-0 effect would render as
# blocky on a bounding-box tier (e.g., GEO).  Organic / radial effects that work
# on arbitrary spatial groupings.  Order is preference: try the first available
# in the effect library; fall back to the next if missing.
_BOUNDING_BOX_SAFE_FALLBACKS: tuple[str, ...] = (
    "Plasma", "Spirals", "Galaxy", "Ripple", "Color Wash",
)


def _darken_palette_hsl(palette: list[str], target_lightness: float = 0.15) -> list[str]:
    """Darken a palette via HSL lightness reduction, preserving hue and saturation.

    Linear RGB scaling (_dim_palette) desaturates colors — a dimmed red becomes
    a muddy brown rather than a deep red.  This routine keeps the colour
    identity intact by only dropping lightness: a vivid #FF0000 becomes a deep
    ruby #4C0000 instead of the muddy #660000 that RGB scaling would produce.

    Used for Tier 1 / Tier 2 background palettes so the backdrop reads as a
    "dark version of this colour" rather than as a washed-out variant.
    Lightness values already below the target are preserved (we only ever
    darken, never brighten).
    """
    import colorsys
    result: list[str] = []
    for color in palette:
        c = color.lstrip("#")
        if len(c) != 6:
            result.append(color)
            continue
        r = int(c[0:2], 16) / 255.0
        g = int(c[2:4], 16) / 255.0
        b = int(c[4:6], 16) / 255.0
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        new_l = min(l, target_lightness)
        nr, ng, nb = colorsys.hls_to_rgb(h, new_l, s)
        result.append(f"#{int(nr * 255):02X}{int(ng * 255):02X}{int(nb * 255):02X}")
    return result


def _dim_palette(palette: list[str], multiplier: float) -> list[str]:
    """Scale hex color brightness by multiplier (0.0-1.0).

    Retained for effect-level brightness modulation (e.g., tension curves).
    For background-tier backdrops, prefer `_darken_palette_hsl` which better
    preserves color identity at low lightness values.
    """
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

# Maximum active palette colors per tier (palette restraint feature).
_TIER_PALETTE_CAP: dict[int, int] = {
    1: 3,   # BASE — simple background wash
    2: 3,   # GEO — zone background
    3: 4,   # TYPE — architecture groups
    4: 3,   # BEAT — beat accents (minimal palette)
    5: 4,   # TEX — texture/fidelity
    6: 4,   # PROP — individual props
    7: 6,   # COMP — compound groups (hero-adjacent)
    8: 6,   # HERO — matrices, mega trees (richest palette)
}

# Effects where MusicSparkles is suppressed (redundant with built-in audio reactivity).
_AUDIO_REACTIVE_EFFECTS: set[str] = {"VU Meter", "Music"}

# Effects that default to Rainbow but should use Palette when we provide colors.
# Maps effect name -> parameter storage_name -> value to force.
_FORCE_PALETTE_PARAMS: dict[str, dict[str, str]] = {
    "Butterfly": {"E_CHOICE_Butterfly_Colors": "Palette"},
    "Meteors": {"E_CHOICE_Meteors_Type": "Palette", "E_CHOICE_Meteors_Effect": "Down"},
    "Single Strand": {"E_CHOICE_SingleStrand_Colors": "Palette"},
    "Wave": {"E_CHOICE_Fill_Colors": "Color 1", "E_CHOICE_Wave_Direction": "Right to Left"},
    "Bars": {"E_CHOICE_Bars_Direction": "Left"},
    "Fire": {"E_CHECKBOX_Fire_GrowWithMusic": "0"},
    "Garlands": {},
    "Spirals": {},
    "Curtain": {"E_CHOICE_Curtain_Effect": "open"},
    "Liquid": {"E_CHOICE_ParticleType": "Elastic"},
}

# Direction parameters that should alternate between instances.
# Maps storage_name -> [even_value, odd_value]
_ALTERNATING_DIRECTIONS: dict[str, list[str]] = {
    "E_CHOICE_Bars_Direction": ["Left", "Right", "expand", "compress"],
    "E_SLIDER_Spirals_Rotation": ["20", "-20"],
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

# ---------------------------------------------------------------------------
# Beat accent constants (spec 042)
# ---------------------------------------------------------------------------

# 042A: Drum-hit Shockwave on small radial props
_DRUM_HIT_ENERGY_GATE = 15       # per-hit drum stem energy threshold (0-100 scale).
                                  # MRC data: p25=13, p50=18. At 15, ~70% of hits fire —
                                  # "if you can hear the drum, fire the accent."
                                  # Falls back to full_mix curve if drums curve absent;
                                  # allows all hits through if no curve is available at all.
_DRUM_ONSET_SAMPLE_OFFSET_MS = 25  # Sample the energy curve this many ms AFTER the onset.
                                    # Drum energy peaks slightly after the attack transient;
                                    # one frame at ~47fps captures the ring, not the pre-hit.
_DRUM_ACCENT_DURATION_MS = 275   # midpoint of 200-350ms spec range
_DRUM_ACCENT_MIN_SPACING_MS = 150  # minimum ms between consecutive placements
_SMALL_RADIAL_THRESHOLD = 200    # pixel count threshold for "small" radial props

# Name keywords that identify radial-style props even when DisplayAs='Custom'.
# Custom-modeled spinners, flakes, and similar shapes are classified as "outline"
# by prop_type_for_display_as(), so we fall back to name matching.
_RADIAL_NAME_KEYWORDS: frozenset[str] = frozenset({
    "spinner", "flake", "snowflake", "wreath", "star", "circle",
})

_DRUM_VARIANT_MAP: dict[str, str] = {
    "kick":  "Shockwave Full Fast",
    "snare": "Shockwave Medium Fast",
    "hihat": "Shockwave Small Thin",
}
_DRUM_ACCENT_DEFAULT_VARIANT = "Shockwave Full Fast"
_DRUM_ACCENT_ALTERNATING = ("Shockwave Full Fast", "Shockwave Medium Fast")
_DRUM_BIAS_THRESHOLD = 0.80  # >80% same label → use alternating kick/snare fallback

# 042B: Whole-house impact accent at section peaks
_IMPACT_ENERGY_GATE = 80
_IMPACT_QUALIFYING_ROLES = frozenset({"chorus", "drop", "climax", "build_peak"})
_IMPACT_MIN_DURATION_MS = 4000
_IMPACT_ACCENT_DURATION_MS = 800
_IMPACT_ACCENT_PALETTE = ["#FFFFFF"]
_IMPACT_ACCENT_TIERS = frozenset({4, 5, 6, 7, 8})


def _apply_palette_target(palette: list[str], target: int) -> list[str]:
    """Trim a palette to ``target`` colours using spread-based indexing.

    Identical spread-index math to `restrain_palette`; kept as a tiny helper so
    `place_effects` can apply a precomputed per-tier target (spec 048) without
    re-deriving from energy/tier.
    """
    effective = max(1, min(target, len(palette)))
    if effective >= len(palette):
        return list(palette)
    if effective == 1:
        return [palette[0]]
    indices = [round(i * (len(palette) - 1) / (effective - 1)) for i in range(effective)]
    return [palette[i] for i in indices]


def restrain_palette(palette: list[str], energy_score: int, tier: int) -> list[str]:
    """Trim palette to 2-4 active colors based on section energy and group tier.

    Algorithm: target = min(2 + energy // 33, _TIER_PALETTE_CAP[tier], len(palette))
    Colors are selected using spread-based indexing (evenly spaced across the full
    palette range) rather than a linear slice from the start, so that gradients produce
    contrasting colors instead of similar adjacent shades.
    """
    base_count = 2 + energy_score // 33
    tier_cap = _TIER_PALETTE_CAP.get(tier, 4)
    target = max(1, min(base_count, tier_cap, len(palette)))
    return _apply_palette_target(palette, target)


def compute_music_sparkles(energy_score: int, effect_name: str, rng: random.Random) -> int:
    """Compute MusicSparkles frequency for a palette placement.

    Returns 0 for audio-reactive effects. Otherwise uses probability = energy/200
    to decide whether to enable sparkles. When enabled, frequency = 20 + round(energy * 0.6).
    """
    if effect_name in _AUDIO_REACTIVE_EFFECTS:
        return 0
    probability = energy_score / 200.0
    if rng.random() < probability:
        return 20 + round(energy_score * 0.6)
    return 0


# BPM anchor points for duration scaling
_DURATION_BPM_SLOW = 80.0    # BPM at or below this → 3000ms base
_DURATION_BPM_FAST = 140.0   # BPM at or above this → 500ms base
_DURATION_MS_SLOW = 3000     # Target duration at slow anchor
_DURATION_MS_FAST = 500      # Target duration at fast anchor
_DURATION_MIN_MS = 250       # Hard floor (never shorter than this)
_DURATION_MAX_MS = 8000      # Hard ceiling for non-sustained effects


def compute_duration_target(bpm: float, energy_score: int) -> DurationTarget:
    """Compute a target duration range for a section based on BPM and energy.

    Formula:
    - BPM <= 80:  base = 3000ms
    - BPM >= 140: base = 500ms
    - BPM 80-140: linear interpolation
    - Energy multiplier: 1.3 - (energy / 100) * 0.6  (range 0.7-1.3)
    - Clamp final target to [250, 8000]ms
    """
    clamped_bpm = max(_DURATION_BPM_SLOW, min(_DURATION_BPM_FAST, bpm))
    t = (clamped_bpm - _DURATION_BPM_SLOW) / (_DURATION_BPM_FAST - _DURATION_BPM_SLOW)
    base_ms = _DURATION_MS_SLOW + t * (_DURATION_MS_FAST - _DURATION_MS_SLOW)

    energy_multiplier = 1.3 - (energy_score / 100.0) * 0.6
    target = max(_DURATION_MIN_MS, min(_DURATION_MAX_MS, round(base_ms * energy_multiplier)))

    return DurationTarget(
        min_ms=max(_DURATION_MIN_MS, target // 2),
        target_ms=target,
        max_ms=min(_DURATION_MAX_MS, target * 2),
    )


def compute_scaled_fades(duration_ms: int) -> tuple[int, int]:
    """Compute symmetric fade-in/fade-out times proportional to effect duration.

    Rules:
    - duration < 500ms:   0ms fades (crisp cuts)
    - duration 500-4000ms: 8% of duration, clamped to [50, 500]ms
    - duration > 4000ms:  10% of duration, clamped to [200, 2000]ms
    - Combined fades never exceed 40% of duration
    """
    if duration_ms < 500:
        return 0, 0

    if duration_ms <= 4000:
        fade = max(50, min(500, round(duration_ms * 0.08)))
    else:
        fade = max(200, min(2000, round(duration_ms * 0.10)))

    # Ensure combined fades <= 40% of duration
    max_each = int(duration_ms * 0.20)  # 20% each = 40% combined
    fade = min(fade, max_each)

    return fade, fade



def _build_effect_pool(
    effect_library: EffectLibrary,
    exclude: set[str] | None = None,
    prop_type: str | None = None,
) -> list[EffectDefinition]:
    """Return EffectDefinition objects for the prop-effect pool, minus exclusions.

    When ``prop_type`` is provided, effects rated ``not_recommended`` for that prop
    type are excluded (FR-003).  If filtering would empty the pool entirely, the
    filter is relaxed by re-calling without ``prop_type`` (FR-004).
    """
    exclude = exclude or set()
    pool = []
    for name in _PROP_EFFECT_POOL:
        if name in exclude:
            continue
        edef = effect_library.effects.get(name)
        if edef is None:
            continue
        if prop_type is not None:
            rating = edef.prop_suitability.get(prop_type, "possible")
            if rating == "not_recommended":
                continue
        pool.append(edef)
    # FR-004: if filtering emptied the pool, relax to unfiltered
    if not pool and prop_type is not None:
        return _build_effect_pool(effect_library, exclude=exclude, prop_type=None)
    return pool


def derive_working_set(theme, variant_library) -> WorkingSet:
    """Derive a weighted working set of effects from a theme's layer structure.

    Algorithm (from data-model.md):
    1. Layer weights: layer 0 = 0.40, each subsequent = previous / 2, min 0.05
    2. effect_pool expansion: split layer's weight evenly across pool variants
       (the layer's own variant is NOT included in pool splits — pool is separate)
    3. Alternate layers: each alternate set contributes variants at 0.05 each
    4. Normalize to sum = 1.0
    5. Dedup: same base effect across entries — sum weights under highest-weighted variant
    """
    raw: list[tuple[str, str, float, str]] = []  # (variant_name, effect_name, weight, source)

    # --- Layer weights ---
    layer_weight = 0.40
    for layer_idx, layer in enumerate(theme.layers):
        source_label = f"layer_{layer_idx}"
        if layer.effect_pool:
            # Split evenly across pool variants only (layer variant excluded from pool split)
            pool_names = list(layer.effect_pool)
            per_pool = layer_weight / len(pool_names)
            for pool_variant_name in pool_names:
                pool_variant = variant_library.get(pool_variant_name)
                if pool_variant is not None:
                    raw.append((pool_variant_name, pool_variant.base_effect, per_pool, "effect_pool"))
            # The layer's own variant does not get extra weight when pool is present
            # (its weight is already split into the pool)
            layer_variant = variant_library.get(layer.variant)
            if layer_variant is not None:
                raw.append((layer.variant, layer_variant.base_effect, per_pool, source_label))
        else:
            layer_variant = variant_library.get(layer.variant)
            if layer_variant is not None:
                raw.append((layer.variant, layer_variant.base_effect, layer_weight, source_label))

        layer_weight = max(0.05, layer_weight / 2)

    # --- Alternate layers ---
    for alternate in theme.alternates:
        for alt_layer in alternate.layers:
            alt_variant = variant_library.get(alt_layer.variant)
            if alt_variant is not None:
                raw.append((alt_layer.variant, alt_variant.base_effect, 0.05, "alternate"))

    if not raw:
        return WorkingSet(effects=[], theme_name=theme.name)

    # --- Deduplication: merge same base effect, keep highest-weighted variant ---
    # Group by effect_name; combine weights; retain variant of highest raw entry
    effect_groups: dict[str, list[tuple[str, float, str]]] = {}  # effect → [(variant, weight, source)]
    for variant_name, effect_name, weight, source in raw:
        effect_groups.setdefault(effect_name, []).append((variant_name, weight, source))

    deduped: list[tuple[str, str, float, str]] = []  # (effect_name, variant_name, combined_weight, source)
    for effect_name, entries in effect_groups.items():
        combined_weight = sum(w for _, w, _ in entries)
        # Use variant from the entry with the highest individual weight
        best_variant, _, best_source = max(entries, key=lambda x: x[1])
        deduped.append((effect_name, best_variant, combined_weight, best_source))

    # --- Normalize ---
    total = sum(w for _, _, w, _ in deduped)
    if total <= 0:
        return WorkingSet(effects=[], theme_name=theme.name)

    normalized = [(en, vn, w / total, src) for en, vn, w, src in deduped]

    # --- Sort by weight descending ---
    normalized.sort(key=lambda x: x[2], reverse=True)

    effects = [
        WorkingSetEntry(
            effect_name=en,
            variant_name=vn,
            weight=w,
            source=src,
        )
        for en, vn, w, src in normalized
    ]
    return WorkingSet(effects=effects, theme_name=theme.name)


def select_from_working_set(working_set: WorkingSet, rng) -> WorkingSetEntry:
    """Select an entry from a WorkingSet using weighted random selection.

    Args:
        working_set: The weighted effect pool to sample from
        rng: A random.Random instance for reproducibility

    Returns:
        A WorkingSetEntry chosen proportionally to its weight
    """
    if not working_set.effects:
        raise ValueError("WorkingSet is empty — cannot select")
    r = rng.random()
    cumulative = 0.0
    for entry in working_set.effects:
        cumulative += entry.weight
        if r <= cumulative:
            return entry
    # Floating point safety — return last entry
    return working_set.effects[-1]


def place_effects(
    assignment: SectionAssignment,
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    hierarchy: HierarchyResult,
    variant_library=None,
    rotation_plan: RotationPlan | None = None,
) -> dict[str, list[EffectPlacement]]:
    """Place effects from theme layers onto power groups, aligned to timing tracks.

    As of spec 048, every per-section creative decision is read off ``assignment``:
    ``active_tiers``, ``palette_target``, ``duration_target``, ``working_set``,
    ``section_index``.  Nothing is re-derived from config flags or ambient state.

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
    section_index = assignment.section_index
    working_set = assignment.working_set
    focused_vocabulary = working_set is not None
    palette_target = assignment.palette_target
    duration_target = assignment.duration_target
    duration_scaling = duration_target is not None
    bpm = hierarchy.estimated_bpm

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

    # Background palette: darkened via HSL lightness reduction for tiers 1-2.
    # HSL-dim preserves color identity (a vivid red stays red, just darker)
    # rather than desaturating it into a muddy brown as linear RGB dimming does.
    bg_palette = _darken_palette_hsl(theme.palette, target_lightness=0.15)

    # Detect drop/impact phase from section label (chorus, drop, bridge, etc.)
    section_label = (section.label or "").lower()
    is_high_energy = any(kw in section_label for kw in ("chorus", "drop", "hook", "climax"))

    # Map layers to tier sets
    layer_tier_map = _assign_layers_to_tiers(layers)

    # Tier selection: read the precomputed set off the assignment (spec 048).
    # `_compute_active_tiers` is no longer called here — it runs once per section
    # in `build_plan`'s decision-precompute pass.
    effective_tiers: frozenset[int] = assignment.active_tiers

    tier_groups: dict[int, list[PowerGroup]] = {}
    for g in groups:
        if g.tier not in effective_tiers:
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

            # Palette restraint: trim to the precomputed per-tier cap (spec 048).
            # The target colour count was decided in `build_plan` and stored on
            # the assignment; we simply apply it here with the same spread-index
            # math used by `restrain_palette`.
            if palette_target is not None and tier in palette_target:
                tier_palette = _apply_palette_target(tier_palette, palette_target[tier])

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
                        duration_scaling=duration_scaling,
                        bpm=bpm,
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

            # Tier 6-7 effect rotation (fallback): when rotation_plan is None, use WorkingSet
            # (focused_vocabulary=True) or prop-effect pool (focused_vocabulary=False)
            if tier in (6, 7) and groups_for_tier:
                if focused_vocabulary and working_set and working_set.effects:
                    # T011: Draw from WorkingSet — coherent with rest of sequence
                    for gi, group in enumerate(groups_for_tier):
                        ws_rng = random.Random(section_index * 10000 + gi * 100 + tier)
                        ws_entry = select_from_working_set(working_set, ws_rng)
                        ws_def = effect_library.effects.get(ws_entry.effect_name)
                        if ws_def is None:
                            ws_def = effect_def  # fallback to layer effect
                        rot_placements = _place_effect_on_group(
                            effect_def=ws_def,
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
                            duration_scaling=duration_scaling,
                            bpm=bpm,
                        )
                        if rot_placements:
                            result.setdefault(group.name, []).extend(rot_placements)
                    continue
                else:
                    # Original: cycle through prop-effect pool (T023: per-group prop_type filter)
                    for gi, group in enumerate(groups_for_tier):
                        group_prop_type = getattr(group, "prop_type", None)
                        pool = _build_effect_pool(
                            effect_library,
                            exclude={layer_variant.base_effect},
                            prop_type=group_prop_type,
                        )
                        if not pool:
                            continue
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
                            duration_scaling=duration_scaling,
                            bpm=bpm,
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

            # Tier 2 (GEO): phrase-paired call-and-response.
            # Alternate active zones between call side (Left + Top) and answer
            # side (Right + Bot) every _PHRASE_LEN_BARS bars, creating a natural
            # back-and-forth that aligns to musical phrase structure.  Gated
            # upstream by _compute_active_tiers — only reached when the
            # section has strong phrase periodicity.
            #
            # Substitute blocky effects (Bars, Curtain, Single Strand) with an
            # organic alternative — GEO groups are bounding-box canvases where
            # linear effects read as geometric rectangles, not lighting design.
            if tier == 2 and groups_for_tier:
                geo_effect_def = _substitute_bounding_box_effect(effect_def, effect_library)
                cr_result = _place_call_response(
                    geo_effect_def, layer, groups_for_tier,
                    assignment.section, hierarchy, tier_palette,
                    variant_library=variant_library,
                    phrase_len_bars=_PHRASE_LEN_BARS,
                )
                for gname, placements in cr_result.items():
                    result.setdefault(gname, []).extend(placements)
                continue

            # Default placement: one effect per group spanning the whole section.
            # Used by Tier 1 (BASE_All — ethereal only), Tier 6 (PROP), Tier 7
            # (COMP), and Tier 8 (HERO).  _compute_active_tiers guarantees only
            # one partition tier from {2, 4, 6, 7} is present, plus 1 and/or 8.
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
                    bar_parity=None,
                    duration_scaling=duration_scaling,
                    bpm=bpm,
                )
                if placements:
                    result.setdefault(group.name, []).extend(placements)

            # Tier 1 background accent overlay: when the theme declares a
            # `background_accent_variant` (e.g. "Snowflakes Driving Few" on
            # Christmas themes), layer it on top of the base effect as a
            # layer-1 placement.  Produces a breathing backdrop (wash + snow)
            # instead of a flat colour field.  Opt-in per theme — Halloween
            # and generic themes leave the field null and get no overlay.
            if (
                tier == 1
                and groups_for_tier
                and theme.background_accent_variant
                and variant_library is not None
            ):
                accent_variant = variant_library.get(theme.background_accent_variant)
                if accent_variant is not None:
                    accent_def = effect_library.effects.get(accent_variant.base_effect)
                    if accent_def is not None:
                        accent_params = dict(accent_variant.parameter_overrides)
                        for group in groups_for_tier:
                            accent_p = _make_placement(
                                accent_def, group.name,
                                assignment.section.start_ms,
                                assignment.section.end_ms,
                                accent_params,
                                tier_palette,
                                "Normal",
                                "section",
                            )
                            accent_p.layer = 1
                            result.setdefault(group.name, []).append(accent_p)

    # MusicSparkles: post-process placements when palette restraint is active.
    # Read the active state off the assignment (spec 048) — palette_target is
    # non-None iff restraint is enabled.
    if palette_target is not None:
        sparkle_rng = random.Random(section.start_ms * 31 + section.energy_score)
        for placements in result.values():
            for p in placements:
                p.music_sparkles = compute_music_sparkles(
                    section.energy_score, p.effect_name, sparkle_rng
                )

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
    bar_parity: int | None = None,
    duration_scaling: bool = False,
    bpm: float = 120.0,
) -> list[EffectPlacement]:
    """Create effect placement instances for a group within a section.

    When ``bar_parity`` is set (0 or 1), bar-based placements only use bars
    matching that parity.  Section-type effects are converted to per-bar
    placement so the parity filter can be applied.
    """
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

    # Duration scaling: for standard effects, subdivide by BPM and energy target.
    # Sustained effects (On, Color Wash, etc.) always span full sections.
    # Accent effects (Shockwave, Strobe, etc.) always use beat placement.
    duration_behavior = getattr(effect_def, "duration_behavior", "standard")
    if duration_scaling and bar_parity is None:
        if duration_behavior == "sustained":
            placements = [_make_placement(
                effect_def, group.name, start_ms, end_ms,
                params, resolved_palette, layer.blend_mode, "section",
                direction_cycle=direction_cycle,
            )]
            if duration_scaling:
                fade_in, fade_out = compute_scaled_fades(end_ms - start_ms)
                for p in placements:
                    p.fade_in_ms = fade_in
                    p.fade_out_ms = fade_out
            return placements
        elif duration_behavior == "accent":
            accent_placements = _place_per_beat(
                effect_def, group.name, section, hierarchy,
                params, resolved_palette, layer.blend_mode,
                chord_marks=chord_marks, tension_curve=tension_curve,
                danceability=danceability, chord_weight=chord_weight,
                direction_cycle=direction_cycle,
            )
            # Drop edge-case placements created by frame-alignment at section ends
            return [p for p in accent_placements if p.end_ms - p.start_ms >= _DURATION_MIN_MS]
        else:  # standard
            target = compute_duration_target(bpm, section.energy_score)
            placements = _place_by_duration(
                effect_def, group.name, section, hierarchy, target,
                params, resolved_palette, layer.blend_mode,
                chord_marks=chord_marks, tension_curve=tension_curve,
                chord_weight=chord_weight, direction_cycle=direction_cycle,
            )
            for p in placements:
                fade_in, fade_out = compute_scaled_fades(p.end_ms - p.start_ms)
                p.fade_in_ms = fade_in
                p.fade_out_ms = fade_out
            return placements

    # When bar_parity is active, force bar-based placement so the parity
    # filter can alternate which bars this group is active on.
    if bar_parity is not None:
        parity_placements = _place_per_bar(
            effect_def, group.name, section, hierarchy,
            params, resolved_palette, layer.blend_mode,
            chord_marks=chord_marks, tension_curve=tension_curve,
            chord_weight=chord_weight, direction_cycle=direction_cycle,
            bar_parity=bar_parity,
        )
        if duration_scaling:
            parity_placements = [
                p for p in parity_placements if p.end_ms - p.start_ms >= _DURATION_MIN_MS
            ]
        return parity_placements

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


def _substitute_bounding_box_effect(
    effect_def: EffectDefinition,
    effect_library: EffectLibrary,
) -> EffectDefinition:
    """Substitute blocky effects with a bounding-box-safe alternative.

    GEO zones render as spatial regions (a bounding box enclosing dissimilar
    props).  Linear effects like Bars look geometric in that context instead
    of visually meaningful.  Swap in the first available organic/radial
    effect from `_BOUNDING_BOX_SAFE_FALLBACKS`.  If the library has none of
    the fallbacks, returns the original (no substitution rather than failure).
    """
    if effect_def.name not in _BLOCKY_ON_BOUNDING_BOX:
        return effect_def
    for candidate in _BOUNDING_BOX_SAFE_FALLBACKS:
        alt = effect_library.effects.get(candidate)
        if alt is not None:
            return alt
    return effect_def


def _place_call_response(
    effect_def: EffectDefinition,
    layer: EffectLayer,
    groups: list[PowerGroup],
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    palette: list[str],
    variant_library=None,
    phrase_len_bars: int = _PHRASE_LEN_BARS,
) -> dict[str, list[EffectPlacement]]:
    """Place effects on GEO zones in phrase-paired call/answer alternation.

    Splits the section into `phrase_len_bars`-bar phrases and alternates which
    GEO zones play: even phrases → call side (Left + Top), odd phrases →
    answer side (Right + Bot).  This creates a natural back-and-forth that
    aligns to musical phrase structure.

    Falls back to whole-section placement on every supplied group if bar data
    is insufficient for phrase-level splitting — this shouldn't normally be
    reached because the caller gates on `_has_strong_phrase_structure`, but
    the fallback keeps the function safe to call in isolation (tests, future
    direct invocation).
    """
    result: dict[str, list[EffectPlacement]] = {}
    params: dict[str, Any] = {}
    if variant_library is not None:
        variant = variant_library.get(layer.variant)
        if variant is not None:
            params = dict(variant.parameter_overrides)

    bars = getattr(hierarchy, "bars", None)
    bar_marks = (
        _marks_in_range(bars.marks, section.start_ms, section.end_ms)
        if bars is not None else []
    )

    # Partition supplied groups into call / answer sides.  Groups outside both
    # sets (Center/Mid, or anything that somehow slipped through) are dropped
    # so the call/response pairing stays clean.
    call_groups = [g for g in groups if g.name in _GEO_CALL_SIDE]
    answer_groups = [g for g in groups if g.name in _GEO_ANSWER_SIDE]

    if not call_groups and not answer_groups:
        return result                              # no usable GEO sides

    if len(bar_marks) < phrase_len_bars:
        # Not enough bars for a single phrase — place once on each side for
        # the whole section.  Better than nothing when bar data is sparse.
        for group in call_groups + answer_groups:
            placement = _make_placement(
                effect_def, group.name, section.start_ms, section.end_ms,
                params, palette, layer.blend_mode, "section",
            )
            result.setdefault(group.name, []).append(placement)
        return result

    for phrase_idx in range(0, len(bar_marks), phrase_len_bars):
        phrase_start = bar_marks[phrase_idx].time_ms
        end_idx = phrase_idx + phrase_len_bars
        phrase_end = (
            bar_marks[end_idx].time_ms if end_idx < len(bar_marks) else section.end_ms
        )
        if phrase_end <= phrase_start:
            continue

        phrase_num = phrase_idx // phrase_len_bars
        active = call_groups if phrase_num % 2 == 0 else answer_groups
        for group in active:
            placement = _make_placement(
                effect_def, group.name, phrase_start, phrase_end,
                params, palette, layer.blend_mode, "section",
                instance_index=phrase_num,
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
    bar_parity: int | None = None,
) -> list[EffectPlacement]:
    """Place one effect instance per bar within the section.

    When ``bar_parity`` is set (0 or 1), only bars matching that parity are
    placed.  This enables the GEO axis-alternation pattern where horizontal
    zones get even bars and vertical zones get odd bars.
    """
    bars_track = hierarchy.bars
    if bars_track is None:
        return [_make_placement(
            effect_def, group_name, section.start_ms, section.end_ms,
            params, palette, blend_mode, "section",
        )]

    marks = _marks_in_range(bars_track.marks, section.start_ms, section.end_ms)
    placements = []
    for i, mark in enumerate(marks):
        if bar_parity is not None and (i % 2) != bar_parity:
            continue
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


def _place_by_duration(
    effect_def: EffectDefinition,
    group_name: str,
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    target: DurationTarget,
    params: dict[str, Any],
    palette: list[str],
    blend_mode: str,
    chord_marks: list[TimingMark] | None = None,
    tension_curve: list[tuple[int, int]] | None = None,
    chord_weight: float = 0.4,
    direction_cycle: dict | None = None,
) -> list[EffectPlacement]:
    """Place effects subdivided to approximate a target duration.

    Uses bar marks as subdivision boundaries. When target duration is shorter
    than the bar length, bars are subdivided into equal segments. When target
    is longer than a bar, bars are merged until the target is hit.
    """
    bars_track = hierarchy.bars
    section_start = section.start_ms
    section_end = section.end_ms

    # Collect candidate boundaries from bar marks
    if bars_track is not None:
        marks = _marks_in_range(bars_track.marks, section_start, section_end)
        boundaries = [m.time_ms for m in marks]
    else:
        boundaries = []

    # Always include section endpoints
    if not boundaries or boundaries[0] > section_start:
        boundaries.insert(0, section_start)
    if boundaries[-1] < section_end:
        boundaries.append(section_end)

    placements = []
    instance_idx = 0

    for i in range(len(boundaries) - 1):
        seg_start = boundaries[i]
        seg_end = boundaries[i + 1]
        seg_dur = seg_end - seg_start

        if seg_dur <= 0:
            continue

        # If segment is close to target, place as-is
        if target.min_ms <= seg_dur <= target.max_ms:
            seg_palette = _resolve_palette(
                palette, chord_marks, tension_curve, seg_start, seg_end, chord_weight
            )
            placements.append(_make_placement(
                effect_def, group_name, seg_start, seg_end,
                params, seg_palette, blend_mode, "bar",
                instance_index=instance_idx, direction_cycle=direction_cycle,
            ))
            instance_idx += 1

        # Segment much longer than target — subdivide
        elif seg_dur > target.max_ms:
            n_splits = max(2, round(seg_dur / target.target_ms))
            split_dur = seg_dur // n_splits
            for j in range(n_splits):
                sub_start = seg_start + j * split_dur
                sub_end = seg_start + (j + 1) * split_dur if j < n_splits - 1 else seg_end
                if sub_end - sub_start < target.min_ms:
                    continue
                sub_palette = _resolve_palette(
                    palette, chord_marks, tension_curve, sub_start, sub_end, chord_weight
                )
                placements.append(_make_placement(
                    effect_def, group_name, sub_start, sub_end,
                    params, sub_palette, blend_mode, "bar",
                    instance_index=instance_idx, direction_cycle=direction_cycle,
                ))
                instance_idx += 1

        # Segment shorter than minimum — still place if it meets the hard floor
        elif seg_dur >= _DURATION_MIN_MS:
            seg_palette = _resolve_palette(
                palette, chord_marks, tension_curve, seg_start, seg_end, chord_weight
            )
            placements.append(_make_placement(
                effect_def, group_name, seg_start, seg_end,
                params, seg_palette, blend_mode, "bar",
                instance_index=instance_idx, direction_cycle=direction_cycle,
            ))
            instance_idx += 1
        # else: segment too short — skip

    # Fallback: if no placements generated, place the whole section
    if not placements:
        seg_palette = _resolve_palette(
            palette, chord_marks, tension_curve, section_start, section_end, chord_weight
        )
        placements.append(_make_placement(
            effect_def, group_name, section_start, section_end,
            params, seg_palette, blend_mode, "section",
            direction_cycle=direction_cycle,
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


def _sample_energy_curve(curve: Any, t_ms: int) -> int:
    """Sample a ValueCurve (or duck-typed equivalent) at the given millisecond.

    Returns an integer in 0-100.  Safe to call when the curve object has unexpected
    shape — returns 0 on any out-of-bounds or missing attribute access.
    """
    fps = getattr(curve, "fps", 47)
    values = getattr(curve, "values", [])
    frame = int(t_ms * fps / 1000)
    if frame < len(values):
        return int(values[frame])
    return 0


def _pearson(a: list[float], b: list[float]) -> float:
    """Pearson correlation coefficient of two equal-length sequences.

    Returns 0.0 on degenerate input (length mismatch, fewer than 2 points, or
    zero variance in either sequence).  No external dependency — uses stdlib
    `statistics` for the means.
    """
    import statistics
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    mean_a = statistics.mean(a)
    mean_b = statistics.mean(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    den_a = sum((x - mean_a) ** 2 for x in a) ** 0.5
    den_b = sum((y - mean_b) ** 2 for y in b) ** 0.5
    if den_a == 0.0 or den_b == 0.0:
        return 0.0
    return num / (den_a * den_b)


def _has_strong_phrase_structure(
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    phrase_len_bars: int = _PHRASE_LEN_BARS,
    min_correlation: float = _MIN_PHRASE_CORRELATION,
) -> bool:
    """True if the section's energy curve repeats periodically at phrase length.

    Samples full_mix energy at each bar onset within the section, then computes
    the Pearson correlation between the bar-energy signal and itself shifted by
    `phrase_len_bars`.  High correlation means every Nth bar has the same
    relative energy — the acoustic signature of phrase structure that supports
    call-and-response.

    Returns False safely when bar data or energy curves are unavailable, or
    when there are fewer than two phrases' worth of bars to compare.
    """
    curves = getattr(hierarchy, "energy_curves", None) or {}
    curve = curves.get("full_mix")
    bars = getattr(hierarchy, "bars", None)
    if curve is None or bars is None:
        return False

    bar_marks = _marks_in_range(bars.marks, section.start_ms, section.end_ms)
    if len(bar_marks) < 2 * phrase_len_bars:
        return False

    bar_energies = [float(_sample_energy_curve(curve, b.time_ms)) for b in bar_marks]
    lead = bar_energies[:-phrase_len_bars]
    lag = bar_energies[phrase_len_bars:]
    return _pearson(lead, lag) >= min_correlation


def _compute_active_tiers(
    section: SectionEnergy,
    section_index: int,
    hierarchy: HierarchyResult,
) -> frozenset[int]:
    """Return the tier set that should be active for this section.

    Tiers 2, 4, 6, 7 are alternative partition schemes of the same physical
    props — activating multiple simultaneously causes the higher-numbered
    tier to silently overwrite the lower one on every shared prop.  To keep
    each section visually intentional, we activate exactly ONE partition
    tier at a time, chosen by mood and (for structural) phrase structure.

    Tier 8 (HERO) always runs independently — hero props don't appear in
    partition tiers by design.  Tier 1 (BASE_All) is only meaningful for
    ethereal sections; in other moods a partition tier covers every prop
    and BASE would be immediately overridden.
    """
    if section.mood_tier == "ethereal":
        return frozenset({1, 8})
    if section.mood_tier == "structural":
        if _has_strong_phrase_structure(section, hierarchy):
            return frozenset({2, 8})                # GEO call-response
        return frozenset({6, 8})                    # Prop-type variety
    return frozenset({4, 8})                        # aggressive: beat chase


def _place_drum_accents(
    groups: list[PowerGroup],
    hierarchy: HierarchyResult,
    assignment: SectionAssignment,
    variant_library: Any,
    props_by_name: dict[str, Any],
    small_radial_threshold: int = _SMALL_RADIAL_THRESHOLD,
) -> dict[str, list[EffectPlacement]]:
    """Place Shockwave accents on small radial props at every drum hit (spec 042A).

    Section-level gating — drum-track presence, section energy, `beat_accent_effects`
    config — lives on ``assignment.accent_policy.drum_hits`` after spec 048.  This
    function trusts the policy flag and applies only the per-hit energy gate.

    Each hit is gated individually by sampling `hierarchy.energy_curves["drums"]` at
    the hit's timestamp. A hit fires only if the drum stem energy at that moment is
    >= _DRUM_HIT_ENERGY_GATE (15/100). Falls back to the full_mix curve if the drums
    curve is absent; allows all hits through if no energy curve is available at all.

    Shockwave variant is chosen from the hit's label (kick/snare/hihat). When the
    classifier is biased (>80% single label in the section), alternates kick/snare
    variants by beat index for visual variety. Minimum 150ms spacing between
    placements on the same group prevents overlap on dense drum tracks.
    """
    result: dict[str, list[EffectPlacement]] = {}
    if not assignment.accent_policy.drum_hits:
        return result

    section = assignment.section
    drum_track = hierarchy.events.get("drums")
    if drum_track is None:
        return result

    # Identify small radial props directly from props_by_name.
    # Tier-6 groups for radial props often don't form (when only 1-2 exist with
    # different name prefixes), so we scan individual props instead of groups.
    # Each qualifying prop becomes its own placement target (model name, not group name).
    small_radial_model_names: list[str] = []
    for model_name, prop in props_by_name.items():
        display_as = getattr(prop, "display_as", "")
        is_radial = prop_type_for_display_as(display_as) == "radial"

        # Secondary check: Custom-modeled spinners/flakes/etc. map to "outline" via
        # prop_type_for_display_as, so fall back to name-keyword matching when the
        # primary DisplayAs classification doesn't identify the prop as radial.
        if not is_radial:
            name_lower = model_name.lower()
            is_radial = any(kw in name_lower for kw in _RADIAL_NAME_KEYWORDS)

        if not is_radial:
            continue

        px = getattr(prop, "pixel_count", 0)
        if px <= 0:
            continue  # pixel count not populated
        if px <= small_radial_threshold:
            small_radial_model_names.append(model_name)
        else:
            logger.debug(
                "drum_accents: prop '%s' — pixel_count %d > threshold %d, skipping",
                model_name, px, small_radial_threshold,
            )

    if not small_radial_model_names:
        radial_by_display = [
            n for n, p in props_by_name.items()
            if prop_type_for_display_as(getattr(p, "display_as", "")) == "radial"
        ]
        radial_by_name = [
            n for n in props_by_name
            if any(kw in n.lower() for kw in _RADIAL_NAME_KEYWORDS)
        ]
        logger.debug(
            "drum_accents: section '%s' — no small radial props "
            "(radial by DisplayAs: %s; radial by name keyword: %s)",
            section.label, radial_by_display, radial_by_name,
        )
        return result

    hits = [
        m for m in drum_track.marks
        if section.start_ms <= m.time_ms < section.end_ms
    ]
    if not hits:
        return result

    # Resolve the energy curve used for per-hit gating.
    # Preference: drums stem → full_mix → None (no gate, all hits allowed).
    _active_curve = (
        hierarchy.energy_curves.get("drums")
        or hierarchy.energy_curves.get("full_mix")
    )

    # Classifier bias check: >80% single label → alternate kick/snare variants
    labeled_hits = [h for h in hits if h.label in _DRUM_VARIANT_MAP]
    use_alternating = False
    if labeled_hits:
        from collections import Counter
        counts = Counter(h.label for h in labeled_hits)
        top_ratio = counts.most_common(1)[0][1] / len(labeled_hits)
        if top_ratio > _DRUM_BIAS_THRESHOLD:
            use_alternating = True

    for model_name in small_radial_model_names:
        last_ms: int = -_DRUM_ACCENT_MIN_SPACING_MS
        for beat_idx, hit in enumerate(hits):
            if hit.time_ms - last_ms < _DRUM_ACCENT_MIN_SPACING_MS:
                continue

            # Per-hit energy gate: skip low-energy hits that are bleed or noise.
            # Sample slightly after the onset so we capture the ring energy, not the
            # pre-attack window that the energy curve may have already averaged in.
            if _active_curve is not None:
                hit_energy = _sample_energy_curve(
                    _active_curve, hit.time_ms + _DRUM_ONSET_SAMPLE_OFFSET_MS
                )
                if hit_energy < _DRUM_HIT_ENERGY_GATE:
                    continue

            if use_alternating:
                variant_name = _DRUM_ACCENT_ALTERNATING[beat_idx % 2]
            else:
                variant_name = _DRUM_VARIANT_MAP.get(
                    hit.label or "", _DRUM_ACCENT_DEFAULT_VARIANT
                )

            variant = variant_library.get(variant_name) if variant_library is not None else None
            params = dict(variant.parameter_overrides) if variant is not None else {}

            start_ms = frame_align(hit.time_ms)
            end_ms = frame_align(hit.time_ms + _DRUM_ACCENT_DURATION_MS)
            placement = EffectPlacement(
                effect_name="Shockwave",
                xlights_id="Shockwave",
                model_or_group=model_name,
                start_ms=start_ms,
                end_ms=end_ms,
                parameters=params,
                color_palette=list(assignment.theme.palette[:2]),
                layer=1,
            )
            result.setdefault(model_name, []).append(placement)
            last_ms = hit.time_ms

    return result


def _place_impact_accent(
    groups: list[PowerGroup],
    assignment: SectionAssignment,
    variant_library: Any,
) -> dict[str, list[EffectPlacement]]:
    """Place a whole-house white Shockwave at the start of high-energy peaks (spec 042B).

    Section-level gates (energy, role, duration, ``beat_accent_effects`` config) were
    hoisted to ``build_plan``'s precompute pass in spec 048 and now live on
    ``assignment.accent_policy.impact``.  This helper is mechanical — it trusts the
    policy flag and places a single 800ms Shockwave on all tier 4–8 groups with
    pure white palette.
    """
    result: dict[str, list[EffectPlacement]] = {}
    if not assignment.accent_policy.impact:
        return result

    section = assignment.section
    variant = variant_library.get("Shockwave Full Fast") if variant_library is not None else None
    params = dict(variant.parameter_overrides) if variant is not None else {}

    start_ms = frame_align(section.start_ms)
    end_ms = frame_align(section.start_ms + _IMPACT_ACCENT_DURATION_MS)

    for group in groups:
        if group.tier not in _IMPACT_ACCENT_TIERS:
            continue
        placement = EffectPlacement(
            effect_name="Shockwave",
            xlights_id="Shockwave",
            model_or_group=group.name,
            start_ms=start_ms,
            end_ms=end_ms,
            parameters=dict(params),  # copy per group
            color_palette=list(_IMPACT_ACCENT_PALETTE),
            layer=1,
        )
        result.setdefault(group.name, []).append(placement)

    return result
