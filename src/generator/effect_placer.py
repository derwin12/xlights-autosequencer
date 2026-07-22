"""Effect placement engine — maps theme layers to power groups and timing tracks."""
from __future__ import annotations

import logging
import random
import re
from typing import Any, Callable, Optional

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.effects.library import EffectLibrary
from src.generator.corpus_recipes import (
    _LIGHTNING_FLICKER,
    PropFamilyRecipe,
    recipe_for_group,
    section_qualifies,
)
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

# Effects whose visual pattern doesn't exploit 2D matrix resolution.  Applied
# at the tier-8 HERO placement path (hero placements don't go through
# _build_effect_pool, so the prop_type filter there can't fire).  Surfaced by
# the matrix-heavy microscope panel: large matrices that auto-promote to HERO
# were rendering Bars / Single Strand even when prop_suitability data marks
# the pairing as not_recommended, because the layer's primary effect skips
# the rotation pool.
_MATRIX_LOW_VALUE_EFFECTS: frozenset[str] = frozenset({
    "Bars", "Single Strand", "Strobe", "Curtain",
})

# 2D-friendly fallbacks for matrix props, in preference order.
_MATRIX_FRIENDLY_FALLBACKS: tuple[str, ...] = (
    "Plasma", "Fire", "Pinwheel", "Spirals", "Shockwave", "Galaxy",
)

# Real GLSL Shader presets for matrix substitution, mined from the corpus's
# whole-house "All" element usage (207/28/11/15/8 placements respectively,
# out of 312 total) -- see src/variants/builtins/Shader.json for the
# parameter presets. Rotated into the same candidate pool as
# _MATRIX_FRIENDLY_FALLBACKS below so matrix substitution stops always
# rendering the single static "Plasma" (native effect, bare defaults).
_MATRIX_SHADER_VARIANTS: tuple[str, ...] = (
    "Shader Plasma Emitter Drift",
    "Shader Hex 3D Spiral",
    "Shader Creation Silexars",
    "Shader Black Cherry Cosmos",
    "Shader Continua Variation",
    "Shader xLights Fractal Audio",
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


# Solid saturated primaries used by the reference packages' On unmask layers
# (mined mask-color histogram: blue, cyan, red, yellow dominate), used as the
# fallback rotation when a section palette has no saturated color to promote.
_CORPUS_MASK_PRIMARIES: tuple[str, ...] = (
    "#0000FF", "#00FFFF", "#FF0000", "#FFFF00", "#00FF00", "#FF00FF",
)


_MIN_MASK_HUE_SEPARATION_DEG = 25.0

# Bar-to-bar rotation needs at least this many distinct entries to read as
# movement rather than a frozen color.
_MIN_MASK_ROTATION_CANDIDATES = 3

# (saturation, value) pairs used to synthesize extra rotation entries from a
# theme's own accepted hue(s) when the palette has real color but not enough
# distinct hues (see the "in-hue variants" branch below). Deliberately
# distinct from the (0.75, 0.95) floor used when vivifying the original
# palette color, so a variant never lands on the exact same RGB.
_MASK_HUE_VARIANT_SV: tuple[tuple[float, float], ...] = (
    (0.55, 1.0), (1.0, 0.6), (0.85, 0.8),
)


def _hue_distance_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _vivid_mask_color(
    palette: list[str] | None, variation_seed: int, group_name: str = "",
    offset: int = 0,
) -> str:
    """Pick a vivid color for a corpus recipe's On unmask layer.

    White-over-white reads as colorless, so candidates are the palette's
    *saturated* colors pushed to near-full saturation/value the way the
    reference packages' mask colors are. The pick is spread by group name and
    section so different prop families carry different colors in the same
    section (the corpus runs blue/cyan/red/yellow masks simultaneously) —
    without spreading, every family inherits the same shared anchor color and
    the whole yard converges on one hue.

    Candidates within ``_MIN_MASK_HUE_SEPARATION_DEG`` of an already-picked
    hue are dropped rather than kept as a "different" candidate: a palette
    built from several near-identical blues (e.g. a monochrome theme) used to
    produce multiple candidate strings that were technically distinct RGB
    values but visually the same color, so bar-to-bar color_cycle_bars
    rotation looked frozen even though the index was changing every bar.

    Bug-419: that hue-separation dedup left most builtin themes with only
    1-2 distinct-hue accent candidates (many themes' accent_palette is one
    hue at two lightness levels, by design), which used to trip a "< 3
    candidates" fallback that padded the rotation out with
    ``_CORPUS_MASK_PRIMARIES`` — an unrelated rainbow (blue/cyan/magenta/
    yellow) that overrides the theme's own deliberate accent choice (e.g. a
    red/green Christmas theme's mask flashing blue). The corpus primaries
    are now reserved for the case the palette has genuinely NO usable
    saturated color at all (all white/gray); when the theme has 1-2 real
    hues, rotation variety comes from lightness/saturation variants of those
    SAME hues instead, so the mask never drifts outside the theme's own
    color identity.
    """
    import colorsys
    import zlib
    candidates: list[str] = []
    candidate_hues: list[float] = []

    def add_candidate(vivid: str, hue_deg: float) -> None:
        if all(
            _hue_distance_deg(hue_deg, h) >= _MIN_MASK_HUE_SEPARATION_DEG
            for h in candidate_hues
        ):
            candidates.append(vivid)
            candidate_hues.append(hue_deg)

    for color in palette or []:
        c = color.lstrip("#")
        if len(c) != 6:
            continue
        r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s >= 0.25 and v >= 0.15:
            r, g, b = colorsys.hsv_to_rgb(h, max(s, 0.75), max(v, 0.95))
            vivid = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"
            add_candidate(vivid, h * 360.0)

    if not candidates:
        # No usable saturated color anywhere in the palette (e.g. an
        # all-white/gray theme) -- there's no theme hue to vary, so borrow
        # the corpus's validated primary rotation rather than freezing on
        # white.
        for c in _CORPUS_MASK_PRIMARIES:
            pr, pg, pb = (int(c[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
            ph, _, _ = colorsys.rgb_to_hsv(pr, pg, pb)
            add_candidate(c, ph * 360.0)
    elif len(candidates) < _MIN_MASK_ROTATION_CANDIDATES:
        # The palette DOES carry real color, just not enough distinct hues
        # for bar-to-bar movement -- stay in-hue rather than importing an
        # off-brand primary.
        own_hues = list(candidate_hues)
        variant_idx = 0
        while (
            len(candidates) < _MIN_MASK_ROTATION_CANDIDATES
            and variant_idx < len(own_hues) * len(_MASK_HUE_VARIANT_SV)
        ):
            hue = own_hues[variant_idx % len(own_hues)]
            sat, val = _MASK_HUE_VARIANT_SV[variant_idx // len(own_hues)]
            r, g, b = colorsys.hsv_to_rgb(hue / 360.0, sat, val)
            variant = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"
            if variant not in candidates:
                candidates.append(variant)
            variant_idx += 1

    spread = zlib.crc32(group_name.encode("utf-8")) if group_name else 0
    return candidates[(variation_seed + spread + offset) % len(candidates)]


def _saturated_colors(palette: list[str]) -> list[str]:
    """Return the palette's saturated colors (drops whites/grays/near-blacks).

    Used before background darkening: darkening white just makes gray, so a
    backdrop built from the palette's saturated colors keeps the song's color
    identity even at low lightness.
    """
    import colorsys
    kept: list[str] = []
    for color in palette:
        c = color.lstrip("#")
        if len(c) != 6:
            continue
        r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        _, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s >= 0.25 and v >= 0.15:
            kept.append(color)
    return kept


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

# Effects that always get MusicSparkles on any tier (user request, 2026-07-18:
# a Color Wash without music-reactive sparkles reads as a static gradient).
_ALWAYS_SPARKLE_EFFECTS: set[str] = {"Color Wash"}

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
    "kick":  "Shockwave Full Fast",  # hardest hit → radial burst
    "snare": "On Bold",              # punchy solid flash for snare
    "hihat": "Strobe Dual Fast",     # quick strobe for hi-hat ticks
}
_DRUM_ACCENT_DEFAULT_VARIANT = "Shockwave Full Fast"
_DRUM_ACCENT_ALTERNATING = ("Shockwave Full Fast", "On Bold")

# xLights effects that render only the first palette color — checking more
# colors on these is invalid in the sequencer and the extras never show.
_FIRST_COLOR_ONLY_EFFECTS: frozenset[str] = frozenset({"On", "Shockwave"})

# Corpus-recipe per-beat placements of these effects get a mirrored buffer
# transform on alternating occurrences within a 4-beat bar (user request,
# 2026-07-15, matching a real xLights clipboard paste of a Spirals effect
# with B_CHOICE_BufferTransform="Flip Horizontal"). Only applies at the
# normal 1-beat-per-segment stride -- the sparser "alt style" bar pacing
# (beats_per_placement_alt, e.g. cane/horizontal's whole-song 4-beat mode)
# places only one segment per bar, so there's no "2nd and 4th of the bar"
# to flip.
_FLIP_TRANSFORM_EFFECTS: frozenset[str] = frozenset({"Spirals", "Single Strand"})
_DRUM_BIAS_THRESHOLD = 0.80  # >80% same label → use alternating kick/snare fallback

# 042B: Whole-house impact accent at section peaks
_IMPACT_ENERGY_GATE = 80
_IMPACT_QUALIFYING_ROLES = frozenset({"chorus", "drop", "climax", "build_peak"})
_IMPACT_MIN_DURATION_MS = 4000
_IMPACT_ACCENT_DURATION_MS = 800
_IMPACT_ACCENT_PALETTE = ["#FFFFFF"]
_IMPACT_ACCENT_TIERS = frozenset({4, 5, 6, 7, 8})

# Whole-house composite accent — mined from the reference corpus's "All"
# whole-house group idiom (docs/*_sequencing_corpus, 12 songs). Simultaneous
# active-layer-count sampled every 250ms across the whole song: 0=18%, 1=23%,
# 2=10%, 3=6%, 4=32% (modal), 5=4%, 6=2%, 7=1%. Activity strongly tracks
# section energy: chorus sections carry the bulk of placements, quiet/bridge
# sections are near-silent. Bucketed onto our energy_score scale (0-100);
# gates deliberately distinct from _IMPACT_ENERGY_GATE (that's a single
# section-start flash, this is a sustained per-section layer stack).
_WHOLE_HOUSE_LOW_ENERGY_GATE = 40
_WHOLE_HOUSE_MID_ENERGY_GATE = 60
_WHOLE_HOUSE_HIGH_ENERGY_GATE = 85
# Effect-pool weights mined from the "All" group's aggregate effect usage:
# Shockwave 27%, On 25%, Shader 17%, Pinwheel 12%, Ripple 4% (Fan/Liquid/Warp/
# Morph/Meteors/Spirals/Wave omitted -- each under 2%, and Fan/Liquid/Warp
# have no mined whole-house preset yet). Repeated entries approximate the
# mined ratios; effects rotate across layers by (variation_seed + layer_idx).
_WHOLE_HOUSE_EFFECT_POOL = (
    "Shockwave", "Shockwave", "Shockwave",
    "On", "On", "On",
    "Shader", "Shader",
    "Pinwheel", "Pinwheel",
    "Ripple",
)
# Whole-house Pinwheel variety pools -- grounded in the corpus's own mined
# Pinwheel presets (corpus_recipes.py's matrix recipes use Thickness 15-30 /
# Twist 0-20; the Star-burst preset uses Thickness 28 / Twist 148), not
# invented values. Picked deterministically from variation_seed so a
# whole-house Pinwheel stack no longer renders identically on every
# placement (previously always Thickness=0/Twist=0/Arms=3, the bare
# builtin_effects.json defaults -- see bug report 2026-07-20).
_WHOLE_HOUSE_PINWHEEL_THICKNESS = (10, 18, 25, 32)
_WHOLE_HOUSE_PINWHEEL_TWIST = (0, 45, 90, 135, -45, -90)
_WHOLE_HOUSE_PINWHEEL_ARMS = (3, 4, 5)

# Whole-house Shockwave variety pools. Center stays fixed at 50/50 and
# Blend_Edges stays on -- the "All" group spans every prop's differing
# physical geometry, so an off-center ring or a hard edge risks looking
# broken on some prop shapes even though it would vary fine in isolation.
# Radius/width/cycle/accel ranges stay within builtin_effects.json's min/max
# and close to the effect's own defaults (Start_Radius=1/End_Radius=100/
# Start_Width=5/End_Width=1/Cycles=1/Accel=0) so every combination still
# reads as "an expanding ring," just not byte-identical every time.
_WHOLE_HOUSE_SHOCKWAVE_START_RADIUS = (0, 5, 10)
_WHOLE_HOUSE_SHOCKWAVE_END_RADIUS = (100, 130, 160)
_WHOLE_HOUSE_SHOCKWAVE_START_WIDTH = (3, 6, 10)
_WHOLE_HOUSE_SHOCKWAVE_END_WIDTH = (1, 3, 6)
_WHOLE_HOUSE_SHOCKWAVE_CYCLES = (1, 2, 3)
_WHOLE_HOUSE_SHOCKWAVE_ACCEL = (-3, 0, 3)

# Whole-house Ripple variety pools. Object_To_Draw is restricted to abstract
# shapes -- the full builtin_effects.json choice list also includes holiday
# shapes (Candy Cane, Snow Flake, Present, Crucifix) that would look wrong on
# a non-holiday song. Draw_Style favors the newer Solid/Highlight styles
# (recently added to builtin_effects.json) over the flat "Old" default that
# every whole-house Ripple previously rendered with. Thickness is raised off
# its thin default of 3.
_WHOLE_HOUSE_RIPPLE_OBJECT = ("Circle", "Square", "Triangle", "Star", "Polygon")
_WHOLE_HOUSE_RIPPLE_MOVEMENT = ("Explode", "Explode", "Implode")
_WHOLE_HOUSE_RIPPLE_DRAW_STYLE = (
    "Solid Outward", "Solid Both", "Highlight Outward", "Highlight Both",
    "Lines Outward Ripple",
)
_WHOLE_HOUSE_RIPPLE_THICKNESS = (8, 15, 25, 35)
_WHOLE_HOUSE_RIPPLE_SCALE = (80, 100, 120, 150)


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


# Tiers eligible for end-of-song fade-out. Tier 8 HERO is intentionally
# excluded — heroes can stay punchy at the very end so the song's focal
# props remain crisp even as the wash/beat/prop layers fade. Tier 3 TYPE
# and tier 5 TEX are also excluded because they're partition tiers whose
# placements are typically short (per-bar/per-beat) and adding fade_out_ms
# to many short placements creates flicker rather than a smooth fade.
_FADE_OUT_ELIGIBLE_TIERS = frozenset({1, 2, 4, 6, 7})

# Section labels (lowercased substrings) that indicate a fade-worthy ending.
_FADE_OUT_LABEL_KEYWORDS = ("outro", "fadeout", "fade_out")

# Cap for how long the end-of-song fade lasts. xLights renders fade_out_ms
# as a brightness ramp at the end of the effect; we want a noticeable fade
# without consuming most of the section.
_FADE_OUT_MAX_MS = 4000


def _compute_fadeout_ms_for_final_section(assignment: SectionAssignment) -> int:
    """Return a fade_out_ms value for the final section, or 0 if not fade-worthy.

    Triggers when the final section has low-energy character indicating the
    song dies out rather than cuts: ethereal mood tier, an outro/fadeout
    label, or a low energy score (<= 35). For songs that end on a high-energy
    chorus/drop this returns 0 — those endings are meant to be abrupt.

    Returns half the section duration, capped at 4000ms, so the fade lives
    in the tail of the section without dominating it.
    """
    if not assignment.is_final_section:
        return 0
    section = assignment.section
    label = (section.label or "").lower()
    fade_worthy = (
        section.mood_tier == "ethereal"
        or section.energy_score <= 35
        or any(kw in label for kw in _FADE_OUT_LABEL_KEYWORDS)
    )
    if not fade_worthy:
        return 0
    duration_ms = section.end_ms - section.start_ms
    return min(duration_ms // 2, _FADE_OUT_MAX_MS)


def place_effects(
    assignment: SectionAssignment,
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    hierarchy: HierarchyResult,
    variant_library=None,
    rotation_plan: RotationPlan | None = None,
    progress_cb: Callable[[str], None] | None = None,
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
    # Groups already announced to progress_cb this call (a group can appear
    # under several theme layers — report it once per section).
    _announced: set[str] = set()
    section_index = assignment.section_index
    working_set = assignment.working_set
    focused_vocabulary = working_set is not None
    palette_target = assignment.palette_target
    duration_target = assignment.duration_target
    duration_scaling = duration_target is not None
    bpm = hierarchy.estimated_bpm

    # Use alternate layers for repeated sections (variation_seed > 0).
    # Alternates intentionally simplify to a single layer for variation
    # purposes; if the main theme has additional layers, top them up so
    # multi-layer compositions (esp. tier-1 BASE depth from A1) still
    # apply. The alternate's layer 0 still wins — only the missing
    # higher layers come from the main theme.
    if assignment.variation_seed > 0 and theme.alternates:
        variant_idx = (assignment.variation_seed - 1) % len(theme.alternates)
        layers = list(theme.alternates[variant_idx].layers)
        if len(layers) < len(theme.layers):
            layers.extend(theme.layers[len(layers):])
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
    # Per-frame chroma curve for inter-chord color modulation; None when the
    # NNLS Chroma plugin wasn't available. Consumed by _resolve_palette via
    # chord_color_for_time when chord_marks gaps exceed CHROMA_FALLBACK_GAP_MS.
    chroma_curve = getattr(hierarchy, "chroma_curve", None)

    # Extract essentia features if available
    ef = hierarchy.essentia_features or {}
    danceability = ef.get("danceability")

    # Adaptive chord weight: songs with rich harmony get more chord-color
    # influence; simple I-IV-V songs rely more on theme palette. Capped low —
    # heavier hue rotation drags saturated theme colors into the olive/khaki
    # midpoints and the whole yard reads as muted mud (the reference packages
    # stay on solid saturated colors throughout).
    chord_weight = 0.0
    if chord_marks:
        unique_chords = len({m.label for m in chord_marks if m.label and m.label != "N"})
        chord_weight = min(0.15, unique_chords / 80.0)

    # Song-level anchor palette: when available, derive BOTH the background wash
    # (tiers 1-2) AND the accent tier (3+) from the same song-level colors.
    # This ensures the dominant colors repeat across all sections so the song
    # has a consistent color identity rather than swapping palettes at each
    # section boundary.  Visual variety between sections comes from effect TYPE,
    # not color changes — matching how pro sequences work.
    if assignment.anchor_palette:
        effective_base = assignment.anchor_palette
    else:
        effective_base = theme.palette
    # Always prefer the theme's explicit accent_palette when defined — it
    # encodes the theme designer's deliberate accent-color intent (e.g. Candy
    # Cane's green/pink drum shockwaves).  Fall back to a lightened base only
    # when the theme has no accent_palette configured.
    if theme.accent_palette:
        accent = theme.accent_palette
    else:
        accent = _lighten_palette(effective_base, 0.5)

    # Backdrop from the palette's saturated colors only (darkened white is
    # just gray), at a lightness that still reads as color from the street.
    bg_source = _saturated_colors(effective_base) or effective_base
    bg_palette = _darken_palette_hsl(bg_source, target_lightness=0.25)

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
        # *_FADES groups are reserved master-dimmer canvases (e.g.
        # 01_BASE_All_FADES) — build_plan places their single fade effect
        # directly; theme layers must never land on them.
        if g.name.endswith("_FADES"):
            continue
        tier_groups.setdefault(g.tier, []).append(g)

    # Group density: limit the number of active groups per tier for lower-energy
    # sections so most props stay dark, matching the pro pattern where quiet
    # passages only light the key focal elements.
    #
    # Only categorisation tiers (6 PROP, 7 COMP) get truncated.  Partition
    # tiers (2 GEO, 3 TYPE, 4 BEAT, 5 TEX) place every prop in exactly one
    # group — truncating drops a partition slice and means a fraction of
    # props never fire on that tier (e.g. BEAT_4 would silently disappear
    # at group_density=0.75, leaving 1/4 of props never beat-synced).  Tier
    # 1 BASE has a single whole-house group (no truncation possible).
    # Tier 8 HERO is already a curated focal subset.
    group_density = assignment.group_density
    if group_density < 1.0:
        for tier in list(tier_groups.keys()):
            if tier not in (6, 7):
                continue
            grps = tier_groups[tier]
            keep = max(1, round(len(grps) * group_density))
            tier_groups[tier] = grps[:keep]

    # If no groups provided, create a pseudo-group for each model
    if not groups:
        return _flat_model_fallback(assignment, effect_library, hierarchy, variant_library=variant_library)

    result: dict[str, list[EffectPlacement]] = {}

    # Tier-6 groups already placed via a corpus recipe this call — prevents
    # duplicate per-beat stacks when multiple theme layers target tier 6.
    corpus_recipe_done: set[str] = set()

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
            # Progress detail for the export UI: name each prop-level group
            # once per section as it comes up for placement. Tiers 6-8 carry
            # the names users recognize (Arches, Snowflakes, Mega Tree);
            # lower tiers are partitions/canvases with synthetic names.
            if progress_cb is not None and tier in (6, 7, 8):
                for g in groups_for_tier:
                    if g.name not in _announced:
                        _announced.add(g.name)
                        progress_cb(f"placing {_humanize_group_name(g.name)}")

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
                for gi, group in enumerate(groups_for_tier):
                    # Corpus-mined prop-family idiom (snowflakes, arches,
                    # mega trees) overrides rotation on qualifying sections.
                    # Tier 8 included: a solo mega tree is a HERO group.
                    recipe = recipe_for_group(group)
                    if (
                        tier in (6, 8)
                        and recipe is not None
                        and group.name not in corpus_recipe_done
                        and section_qualifies(recipe, section)
                    ):
                        recipe_placements = _place_corpus_recipe(
                            group, recipe, layer, section, hierarchy,
                            effect_library, assignment.variation_seed,
                            theme_palette=tier_palette,
                            occurrence_index=assignment.corpus_occurrence.get(recipe.family),
                        )
                        if recipe_placements:
                            corpus_recipe_done.add(group.name)
                            result.setdefault(group.name, []).extend(recipe_placements)
                            continue

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

                    # Radial sub-groups: chase across members on the beat
                    # rather than firing a single section-span placement on
                    # the parent.  Members are "Parent/SubModel" addresses;
                    # each beat lights one ring in declaration order.
                    if getattr(group, "prop_type", None) == "radial" and len(group.members) >= 2:
                        rad_placements = _place_radial_chase_on_subgroup(
                            effect_def=rotated_def,
                            layer=layer,
                            group=group,
                            section=assignment.section,
                            hierarchy=hierarchy,
                            palette=tier_palette,
                            params=rot_params,
                            direction_cycle=rot_direction_cycle,
                        )
                        for p in rad_placements:
                            result.setdefault(p.model_or_group, []).append(p)
                        continue

                    # Matrix-prop guard for tier-8 HERO via rotation plan
                    # (peer of the rotation-pool prop_type filter inside
                    # _build_effect_pool, which only runs on tier-6/7).
                    placement_rotated_def = rotated_def
                    matrix_params: dict[str, Any] = {}
                    if (
                        tier == 8
                        and getattr(group, "prop_type", None) == "matrix"
                    ):
                        placement_rotated_def, matrix_params = _substitute_matrix_effect(
                            rotated_def, effect_library,
                            variant_library=variant_library,
                            variation_seed=assignment.variation_seed + gi,
                        )

                    rot_placements = _place_effect_on_group(
                        effect_def=placement_rotated_def,
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
                    # Override params from variant — but only if the variant's
                    # base_effect matches the placement effect.  When matrix
                    # substitution rewrote rotated_def → placement_rotated_def,
                    # the original variant's params target a different effect
                    # and would scramble the substitute's parameter space; use
                    # the substitution's own resolved params instead.
                    if placement_rotated_def is rotated_def:
                        for p in rot_placements:
                            p.parameters.update(rot_params)
                    elif matrix_params:
                        for p in rot_placements:
                            p.parameters.update(matrix_params)
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
                        # Corpus-mined prop-family idiom (snowflakes, arches)
                        # overrides the working set on qualifying sections.
                        recipe = recipe_for_group(group)
                        if (
                            tier == 6
                            and recipe is not None
                            and group.name not in corpus_recipe_done
                            and section_qualifies(recipe, section)
                        ):
                            recipe_placements = _place_corpus_recipe(
                                group, recipe, layer, section, hierarchy,
                                effect_library, assignment.variation_seed,
                                theme_palette=tier_palette,
                                occurrence_index=assignment.corpus_occurrence.get(recipe.family),
                            )
                            if recipe_placements:
                                corpus_recipe_done.add(group.name)
                                result.setdefault(group.name, []).extend(recipe_placements)
                                continue

                        ws_rng = random.Random(section_index * 10000 + gi * 100 + tier)
                        ws_entry = select_from_working_set(working_set, ws_rng)
                        ws_def = effect_library.effects.get(ws_entry.effect_name)
                        if ws_def is None:
                            ws_def = effect_def  # fallback to layer effect

                        # Radial sub-groups: chase across members on the beat.
                        if getattr(group, "prop_type", None) == "radial" and len(group.members) >= 2:
                            ws_params: dict[str, Any] = {}
                            ws_dc = None
                            if variant_library is not None:
                                ws_variant = variant_library.get(layer.variant)
                                if ws_variant is not None:
                                    ws_params = dict(ws_variant.parameter_overrides)
                                    ws_dc = ws_variant.direction_cycle
                            rad_placements = _place_radial_chase_on_subgroup(
                                effect_def=ws_def,
                                layer=layer,
                                group=group,
                                section=assignment.section,
                                hierarchy=hierarchy,
                                palette=tier_palette,
                                params=ws_params,
                                direction_cycle=ws_dc,
                            )
                            for p in rad_placements:
                                result.setdefault(p.model_or_group, []).append(p)
                            continue

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
                        # Corpus-mined prop-family idiom (snowflakes, arches)
                        # overrides the pool on qualifying sections.
                        recipe = recipe_for_group(group)
                        if (
                            tier == 6
                            and recipe is not None
                            and group.name not in corpus_recipe_done
                            and section_qualifies(recipe, section)
                        ):
                            recipe_placements = _place_corpus_recipe(
                                group, recipe, layer, section, hierarchy,
                                effect_library, assignment.variation_seed,
                                theme_palette=tier_palette,
                                occurrence_index=assignment.corpus_occurrence.get(recipe.family),
                            )
                            if recipe_placements:
                                corpus_recipe_done.add(group.name)
                                result.setdefault(group.name, []).extend(recipe_placements)
                                continue

                        group_prop_type = getattr(group, "prop_type", None)

                        # Radial sub-groups: chase the layer's effect across
                        # members on the beat.  Bypass the pool entirely —
                        # the radial sequence wants the same effect on every
                        # ring, not a rotated alternative.
                        if group_prop_type == "radial" and len(group.members) >= 2:
                            pool_params: dict[str, Any] = {}
                            pool_dc = None
                            if variant_library is not None:
                                pool_variant = variant_library.get(layer.variant)
                                if pool_variant is not None:
                                    pool_params = dict(pool_variant.parameter_overrides)
                                    pool_dc = pool_variant.direction_cycle
                            rad_placements = _place_radial_chase_on_subgroup(
                                effect_def=effect_def,
                                layer=layer,
                                group=group,
                                section=assignment.section,
                                hierarchy=hierarchy,
                                palette=tier_palette,
                                params=pool_params,
                                direction_cycle=pool_dc,
                            )
                            for p in rad_placements:
                                result.setdefault(p.model_or_group, []).append(p)
                            continue

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

            # Tier 4 (BEAT): use chase pattern — distribute beats across groups.
            # Substitute blocky/chase effects the same way GEO (tier 2) does —
            # 04_BEAT_N groups are round-robin mixes of dissimilar prop types
            # (src/grouper/grouper.py::_tier4_rhythm), not one physical linear
            # prop, so Single Strand/Bars/Curtain don't read as a chase here.
            if tier == 4 and groups_for_tier:
                beat_effect_def = _substitute_beat_canvas_effect(effect_def, effect_library)
                chase_result = _place_chase_across_groups(
                    beat_effect_def, layer, groups_for_tier,
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
            for gi, group in enumerate(groups_for_tier):
                # Corpus-mined prop-family idiom for HERO props: a solo mega
                # tree never forms a tier-6 pair group, so it reaches this
                # default path as 08_HERO_Mega_Tree. Same override semantics
                # as the tier-6 recipe sites above.
                recipe = recipe_for_group(group)
                if (
                    tier == 8
                    and recipe is not None
                    and group.name not in corpus_recipe_done
                    and section_qualifies(recipe, section)
                ):
                    recipe_placements = _place_corpus_recipe(
                        group, recipe, layer, section, hierarchy,
                        effect_library, assignment.variation_seed,
                        theme_palette=tier_palette,
                        occurrence_index=assignment.corpus_occurrence.get(recipe.family),
                    )
                    if recipe_placements:
                        corpus_recipe_done.add(group.name)
                        result.setdefault(group.name, []).extend(recipe_placements)
                        continue

                # Matrix-prop guard for tier-8 HERO (peer of the rotation-pool
                # filter inside _build_effect_pool, which only runs on tier-6/7).
                placement_effect_def = effect_def
                matrix_params: dict[str, Any] = {}
                if (
                    tier == 8
                    and getattr(group, "prop_type", None) == "matrix"
                ):
                    placement_effect_def, matrix_params = _substitute_matrix_effect(
                        effect_def, effect_library,
                        variant_library=variant_library,
                        variation_seed=assignment.variation_seed + gi,
                    )
                substituted = placement_effect_def is not effect_def
                placements = _place_effect_on_group(
                    effect_def=placement_effect_def,
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
                    # When matrix substitution rewrote the effect, the theme
                    # layer's own variant targets the original (pre-
                    # substitution) effect and would scramble the
                    # substitute's parameter space -- apply matrix_params
                    # instead, below, rather than looking up a mismatched
                    # variant here.
                    variant_library=None if substituted else variant_library,
                    bar_parity=None,
                    duration_scaling=duration_scaling,
                    bpm=bpm,
                )
                if substituted and matrix_params:
                    for p in placements:
                        p.parameters.update(matrix_params)
                if placements:
                    # A1: stamp the theme-layer index onto each placement so
                    # multi-layer compositions (especially tier 1 BASE) land
                    # on distinct xLights EffectLayers and blend properly,
                    # rather than collapsing onto layer 0 and rendering with
                    # last-write-wins semantics.
                    for p in placements:
                        p.layer = layer_idx
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

    # Tier 1 BASE always gets MusicSparkles regardless of palette restraint —
    # the single section-spanning placement on BASE_All would otherwise read
    # as a static sine wave; sparkles are the music-reactive overlay that
    # gives the wash visual life. Same rule for _ALWAYS_SPARKLE_EFFECTS on
    # any tier (user request, 2026-07-18: Color Wash should always have
    # "Sparkles Reflect Music" toggled). These sparkles are unconditional
    # (not the probabilistic compute_music_sparkles gate) but still skip
    # already-audio-reactive effects to avoid double-coverage.
    for group_name, placements in result.items():
        is_base = group_name.startswith("01_BASE")
        for p in placements:
            if not is_base and p.effect_name not in _ALWAYS_SPARKLE_EFFECTS:
                continue
            if p.music_sparkles > 0:
                continue  # already set (e.g. by palette-restraint pass above)
            if p.effect_name in _AUDIO_REACTIVE_EFFECTS:
                continue
            p.music_sparkles = 15 + round(section.energy_score * 0.5)

    # End-of-song fade-out (D1, CLAUDE.md "End-of-Song Fade Out").
    # When this is the final section and the section's character indicates a
    # natural fade ending (low/ethereal energy, outro role), apply fade_out_ms
    # to the placement that ends latest in each eligible group so xLights
    # renders a brightness ramp into silence instead of cutting hard.
    fadeout_ms = _compute_fadeout_ms_for_final_section(assignment)
    if fadeout_ms > 0:
        tier_of_group = {g.name: g.tier for g in groups}
        for group_name, placements in result.items():
            tier = tier_of_group.get(group_name)
            if tier not in _FADE_OUT_ELIGIBLE_TIERS:
                continue
            if not placements:
                continue
            # Apply to the placement(s) ending closest to the section end so
            # short per-beat placements early in the section aren't truncated.
            latest_end = max(p.end_ms for p in placements)
            for p in placements:
                if p.end_ms == latest_end:
                    # Don't exceed the placement's own duration.
                    p.fade_out_ms = min(fadeout_ms, p.end_ms - p.start_ms)

    return result


def _select_groups_for_layer(
    target_tiers: set[int],
    tier_groups: dict[int, list[PowerGroup]],
    layer_idx: int,
    total_layers: int,
) -> dict[int, list[PowerGroup]]:
    """Select which groups to use per tier, avoiding overlap.

    Strategy per tier:
    - Tier 1 (BASE): Whole-house group on every layer that targets it.
      Multi-layer BASE composition (A1) — was previously gated to
      layer 0; now any theme layer mapped to tier 1 by
      ``_assign_layers_to_tiers`` places its variant on BASE so the
      wash gets layered depth.
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
            # BASE: whole-house group on every layer that targets it.
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
            # HERO: rotate the spotlight pick per layer — but corpus-paired
            # heroes (those with a family recipe, e.g. mega tree + mega
            # topper) always place together: the reference packages run the
            # topper co-active with the tree 85% of the time, never solo'd
            # away by a spotlight rotation.
            spotlight = available[layer_idx % len(available)]
            paired = [
                g for g in available
                if g is not spotlight and recipe_for_group(g) is not None
            ]
            selected[tier] = [spotlight] + paired

    return selected


def _assign_layers_to_tiers(layers: list[EffectLayer]) -> dict[int, set[int]]:
    """Map each layer index to a set of target tiers.

    Iteration backlog A1 (multi-layer BASE composition): theme layer 1 (and
    middle layers in 3+-layer themes) also lands on tier 1 BASE. Previously
    only layer 0 covered BASE, so BASE rendered as a single effect with no
    accent layered on top. Stacking layer 1 onto BASE gives the wash visual
    depth (e.g. Color Wash + Twinkle accent) without changing how upper
    tiers are assigned.
    """
    n = len(layers)
    mapping: dict[int, set[int]] = {}

    if n == 1:
        # Single-layer: cover all tier families including HERO (8).  For ethereal
        # sections where only Tier 8 is active, this guarantees the hero group
        # still receives the layer's effect even without a dedicated hero layer.
        mapping[0] = _LOW_TIERS | {4, 6, 8}
    elif n == 2:
        mapping[0] = _LOW_TIERS | {4, 6}
        # A1: layer 1 also accents BASE (tier 1) on top of HERO tiers.
        mapping[1] = _HIGH_TIERS | {1}
    else:
        mapping[0] = _LOW_TIERS | {4, 6}
        mapping[n - 1] = _HIGH_TIERS
        for i in range(1, n - 1):
            # A1: middle layers also accent BASE (tier 1) on top of MID tiers.
            mapping[i] = _MID_TIERS | {1}

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
    resolved_palette = _resolve_palette(
        palette, chord_marks, tension_curve, start_ms, end_ms, chord_weight,
        chroma_curve=getattr(hierarchy, "chroma_curve", None),
    )

    # Duration scaling: for standard effects, subdivide by BPM and energy target.
    # Sustained effects (On, Color Wash, etc.) always span full sections.
    # Accent effects (Shockwave, Strobe, etc.) always use beat placement.
    duration_behavior = getattr(effect_def, "duration_behavior", "standard")
    # Tier 1 BASE is always a section-spanning undertone wash, regardless
    # of the effect's nominal duration_behavior. Without this override
    # tier-1 background variants like Wave / Spirals / Plasma get
    # subdivided into ~10 bar-aligned placements per section, which
    # reads as pulses instead of a constant backdrop.
    if group.tier == 1:
        duration_behavior = "sustained"
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
            # Drop segments shorter than the effect's minimum duration.
            # Fall back to a single section-span placement when all are filtered.
            if effect_def.min_duration_ms > 0:
                placements = [p for p in placements if p.end_ms - p.start_ms >= effect_def.min_duration_ms]
                if not placements:
                    placements = [_make_placement(
                        effect_def, group.name, start_ms, end_ms,
                        params, resolved_palette, layer.blend_mode, "section",
                        direction_cycle=direction_cycle,
                    )]
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
            stem=getattr(layer, "stem", None),
            direction_cycle=direction_cycle,
        )

    return [_make_placement(
        effect_def, group.name, start_ms, end_ms,
        params, resolved_palette, layer.blend_mode, "section",
        direction_cycle=direction_cycle,
    )]


# Beats averaged on each side of the rising/falling comparison in
# _place_chase_across_groups -- smooths ordinary beat-to-beat energy jitter
# so direction doesn't flicker on noise (mirrors the windowed-average style
# already used by derive_energy_impacts).
_CHASE_TREND_WINDOW_BEATS = 2
# Ignore energy differences smaller than this (curve values are 0-100)
# when comparing windows -- a near-flat trend keeps the current direction
# instead of picking one arbitrarily.
_CHASE_TREND_EPSILON = 2


def _place_chase_across_groups(
    effect_def: EffectDefinition,
    layer: EffectLayer,
    groups: list[PowerGroup],
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    palette: list[str],
    variant_library=None,
) -> dict[str, list[EffectPlacement]]:
    """Chase pattern: assign each beat to one group.

    When a full_mix energy curve is available, the chase direction follows
    the music: it steps forward through the groups while energy is rising
    and backward while it's falling (trend measured over a short trailing
    window, not beat-to-beat, to avoid flickering on ordinary jitter), so a
    build feels like it's climbing (1->2->3->4) and a come-down feels like
    it's receding (4->3->2->1). Falls back to the previous fixed forward
    round-robin when no energy curve is available (e.g. --profile quick).
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

    curve = (getattr(hierarchy, "energy_curves", None) or {}).get("full_mix")
    # -1 so the first step (position + direction, direction starts at 1)
    # lands on index 0 rather than skipping straight to index 1.
    position = -1
    direction = 1
    w = _CHASE_TREND_WINDOW_BEATS

    for i, mark in enumerate(marks):
        if curve is None:
            group = groups[i % num_groups]
        else:
            if i >= 2 * w:
                cur_avg = sum(
                    _sample_energy_curve(curve, marks[j].time_ms) for j in range(i - w, i)
                ) / w
                prev_avg = sum(
                    _sample_energy_curve(curve, marks[j].time_ms)
                    for j in range(i - 2 * w, i - w)
                ) / w
                if cur_avg > prev_avg + _CHASE_TREND_EPSILON:
                    direction = 1
                elif cur_avg < prev_avg - _CHASE_TREND_EPSILON:
                    direction = -1
                # else: trend is flat -- keep the current direction.
            position = (position + direction) % num_groups
            group = groups[position]

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


def _place_radial_chase_on_subgroup(
    effect_def: EffectDefinition,
    layer: EffectLayer,
    group: PowerGroup,
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    palette: list[str],
    params: dict[str, Any],
    direction_cycle: dict | None = None,
) -> list[EffectPlacement]:
    """Sequence a radial group's members on successive beats.

    Used for tier-6 radial sub-groups (Ring 1, Ring 2, …) where each
    member is a fully-qualified ``"Parent/SubModel"`` address.  Beat i
    fires on ``members[i % len(members)]`` so the rings light up in
    declaration order, producing a center-out (or rotational) bloom.

    Falls back to a single section-span placement on the whole group
    name when the hierarchy has no beats track.  This keeps the radial
    group from going dark in songs that lack reliable beat detection.
    """
    members = group.members
    if not members:
        return []

    beats_track = getattr(hierarchy, "beats", None)
    if beats_track is None:
        return [_make_placement(
            effect_def, group.name, section.start_ms, section.end_ms,
            params, palette, layer.blend_mode, "section",
            direction_cycle=direction_cycle,
        )]

    marks = _marks_in_range(beats_track.marks, section.start_ms, section.end_ms)
    marks = _apply_density_filter(marks, section.energy_score)
    if not marks:
        return [_make_placement(
            effect_def, group.name, section.start_ms, section.end_ms,
            params, palette, layer.blend_mode, "section",
            direction_cycle=direction_cycle,
        )]

    placements: list[EffectPlacement] = []
    for i, mark in enumerate(marks):
        member = members[i % len(members)]
        beat_start = mark.time_ms
        beat_end = marks[i + 1].time_ms if i + 1 < len(marks) else min(
            beat_start + 500, section.end_ms
        )
        if beat_end <= beat_start:
            continue
        placements.append(_make_placement(
            effect_def, member, beat_start, beat_end,
            params, palette, layer.blend_mode, "beat",
            direction_cycle=direction_cycle,
            instance_index=i,
        ))
    return placements


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


def _substitute_beat_canvas_effect(
    effect_def: EffectDefinition,
    effect_library: EffectLibrary,
) -> EffectDefinition:
    """Substitute blocky/chase effects with Color Wash for BEAT-tier canvases.

    04_BEAT_N groups are round-robin mixes of dissimilar prop types (see
    src/grouper/grouper.py::_tier4_rhythm), the same "bounding box of
    dissimilar props" situation as GEO (tier 2) -- a chase effect like
    Single Strand doesn't read as a chase across unrelated props. Uses
    ``_BLOCKY_ON_BOUNDING_BOX`` (already covers Single Strand/Bars/Curtain)
    but substitutes specifically Color Wash rather than GEO's fallback
    chain (user request, 2026-07-15): that chain leads with motion effects
    (Plasma/Spirals/...) which weren't wanted here.
    """
    if effect_def.name not in _BLOCKY_ON_BOUNDING_BOX:
        return effect_def
    alt = effect_library.effects.get("Color Wash")
    return alt if alt is not None else effect_def


def _substitute_matrix_effect(
    effect_def: EffectDefinition,
    effect_library: EffectLibrary,
    variant_library: Any = None,
    variation_seed: int = 0,
) -> tuple[EffectDefinition, dict[str, Any]]:
    """Swap 1D-oriented effects with 2D-friendly alternatives for matrix props.

    Matrix props have 2D resolution that flat or column-oriented effects
    (Bars, Single Strand, Strobe, Curtain) don't exploit — they render as
    flat color blocks on a 12×48 wall.  This is the HERO-tier counterpart
    to the rotation-pool prop_type filter inside ``_build_effect_pool``;
    that filter only runs on tier-6/7 PROP rotation, so large matrices
    that auto-promote to HERO need this separate guard.

    Returns ``(effect_def, params)`` — previously this returned only the
    effect definition, always resolving to the first available entry in
    ``_MATRIX_FRIENDLY_FALLBACKS`` ("Plasma", always with bare
    builtin_effects.json defaults since nothing downstream could resolve
    matching parameters for a substituted effect). Candidates now rotate
    deterministically by ``variation_seed`` across the native fallbacks
    plus real mined GLSL Shader presets (``_MATRIX_SHADER_VARIANTS``), and
    the caller must apply the returned ``params`` directly — the original
    theme layer's variant lookup targets the pre-substitution effect and
    would scramble the substitute's parameter space.
    """
    if effect_def.name not in _MATRIX_LOW_VALUE_EFFECTS:
        return effect_def, {}

    candidates: list[tuple[str, str | None]] = [
        (name, None) for name in _MATRIX_FRIENDLY_FALLBACKS
        if name in effect_library.effects
    ]
    if variant_library is not None:
        for variant_name in _MATRIX_SHADER_VARIANTS:
            if variant_library.get(variant_name) is not None:
                candidates.append(("Shader", variant_name))

    if not candidates:
        return effect_def, {}

    name, variant_name = candidates[variation_seed % len(candidates)]
    alt = effect_library.effects.get(name)
    if alt is None:
        return effect_def, {}
    if variant_name is None:
        return alt, {}
    variant = variant_library.get(variant_name)
    return alt, dict(variant.parameter_overrides) if variant is not None else {}


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
    chroma_curve: "object | None" = None,
) -> list[str]:
    """Blend theme palette with chord colors and apply tension brightness.

    When ``chroma_curve`` is provided and the gap from the most recent
    Chordino chord at the window midpoint exceeds the chroma-fallback
    threshold, the dominant pitch class from the chroma curve contributes
    an additional color to the chord palette before blending. This adds
    inter-chord modulation when Chordino's coverage is sparse.
    """
    if not chord_marks or chord_weight <= 0:
        return theme_palette

    chord_pal = generate_chord_palette(chord_marks, start_ms, end_ms)

    # Chroma-aware fallback: when chord coverage at the section midpoint is
    # stale (>CHROMA_FALLBACK_GAP_MS since last chord event) and chroma_curve
    # is available, pull the chroma-derived color in. Per fix-misclassified-curves
    # design D3 (chroma is fallback only — never overrides Chordino).
    if chroma_curve is not None:
        from src.generator.chord_colors import chord_color_for_time
        mid_ms = (start_ms + end_ms) // 2
        chroma_color = chord_color_for_time(mid_ms, chord_marks, chroma_curve)
        # Only prepend if not already present and not the no-chord neutral.
        if chroma_color != "#404040" and chroma_color not in chord_pal:
            chord_pal = [chroma_color] + chord_pal

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
        bar_palette = _resolve_palette(
            palette, chord_marks, tension_curve, bar_start, bar_end, chord_weight,
            chroma_curve=getattr(hierarchy, "chroma_curve", None),
        )
        placements.append(_make_placement(
            effect_def, group_name, bar_start, bar_end,
            params, bar_palette, blend_mode, "bar",
            instance_index=i, direction_cycle=direction_cycle,
        ))
    return placements


# Per-beat punch duration (ms). When a beat mark carries cross-tracker
# agreement confidence ≥ _BEAT_PUNCH_CONFIDENCE_THRESHOLD, the placement is
# shortened to this duration so the effect reads as a brief accent (Strobe /
# Shockwave-style punch) rather than spanning the full beat as a wash. The
# threshold corresponds to "≥2-of-3 losers agree" with 4 trackers — see
# design.md for the rationale.
_BEAT_PUNCH_CONFIDENCE_THRESHOLD = 0.7
_BEAT_PUNCH_DURATION_MS = 250


def _humanize_group_name(name: str) -> str:
    """'06_PROP_Mega_Tree' → 'Mega Tree' — tier prefix stripped, underscores
    spaced, for progress display in the export UI."""
    m = re.match(r"^\d{2}_[A-Z]+_(.+)$", name)
    label = m.group(1) if m else name
    return label.replace("_", " ").strip()


def _place_corpus_recipe(
    group: PowerGroup,
    recipe: PropFamilyRecipe,
    layer: EffectLayer,
    section: SectionEnergy,
    hierarchy: HierarchyResult,
    effect_library: EffectLibrary,
    variation_seed: int,
    theme_palette: list[str] | None = None,
    occurrence_index: int | None = None,
) -> list[EffectPlacement] | None:
    """Place a corpus-mined prop-family idiom: solid-palette segments spanning
    consecutive beats, back-to-back across the section (the mined shows place
    one full-beat segment per beat with no gaps — no density filter, no
    confidence-based punch shortening, no chord-color blending).

    Returns None when preconditions are missing (unknown effect, no beats
    track, too few beats in section) so the caller falls back to normal
    placement — never an empty list, which would silently suppress placement
    (bug-159 lesson).
    """
    # Alternate primary/alt effect between qualifying sections. variation_seed
    # is the global section index; qualifying (chorus-like) sections typically
    # occupy every other slot, so raw parity would lock one effect in for the
    # whole song — halving first alternates per occurrence instead. Families
    # with a motion_rotation walk its full cycle the same way; a rotation
    # effect missing from the catalog falls back to the primary pair. A
    # label-keyed alternate (e.g. arch bridges -> Spirals) takes priority over
    # both when the section's own label names a genuinely different mined
    # idiom rather than just a repeat variation.
    section_label = (section.label or "").lower()
    rotation_params: tuple[tuple[str, str], ...] | None = None
    effect_name = recipe.effect_name
    if recipe.label_alt_effect_name is not None and any(
        keyword in section_label for keyword in recipe.label_alt_labels
    ):
        effect_name = recipe.label_alt_effect_name
    elif recipe.motion_rotation:
        # Rotate by qualifying-occurrence count when available: the seed is
        # the global section index, and (seed // 2) % len aliases with
        # regular section strides, silently skipping pool slots (verified on
        # a real song: the walk was 0,1,0,3 — slot 2 unreachable). The seed
        # form remains only as a fallback for callers that never populate
        # SectionAssignment.corpus_occurrence.
        if occurrence_index is not None:
            idx = occurrence_index % len(recipe.motion_rotation)
        else:
            idx = (variation_seed // 2) % len(recipe.motion_rotation)
        rotated_name, rotated_params = recipe.motion_rotation[idx]
        if effect_library.effects.get(rotated_name) is not None:
            effect_name = rotated_name
            rotation_params = rotated_params
    elif recipe.alt_effect_name is not None and (variation_seed // 2) % 2 == 1:
        effect_name = recipe.alt_effect_name
    effect_def = effect_library.effects.get(effect_name)
    if effect_def is None:
        return None
    beats_track = getattr(hierarchy, "beats", None)
    if beats_track is None or not beats_track.marks:
        return None
    marks = _marks_in_range(beats_track.marks, section.start_ms, section.end_ms)
    if len(marks) < 2:
        return None

    median_interval = marks[len(marks) // 2].time_ms - marks[len(marks) // 2 - 1].time_ms
    placements: list[EffectPlacement] = []
    palette = list(recipe.palette)
    # Each effect gets its own mined preset; their parameter spaces differ.
    if rotation_params is not None:
        params: dict[str, Any] = dict(rotation_params)
    elif effect_name == recipe.effect_name:
        params = dict(recipe.parameter_overrides)
    elif effect_name == recipe.label_alt_effect_name:
        params = dict(recipe.label_alt_parameter_overrides)
    else:
        params = dict(recipe.alt_parameter_overrides)

    # Occurrence style rotation applies only to the primary effect's own
    # preset (see PropFamilyRecipe.direction_field/size_field docstrings): one
    # section occurrence holds a constant alt direction and the larger/
    # smaller mined chase-size alternate together as one coherent style; the
    # other occurrence ping-pongs direction per beat below and keeps the
    # primary size. The mined corpus shows both traits held constant across
    # the same continuous run, so they're driven by the same parity bit
    # rather than independent axes.
    use_alt_style = effect_name == recipe.effect_name and variation_seed % 2 == 1
    use_bounce_direction = (
        use_alt_style
        and recipe.direction_field is not None
        and recipe.direction_alt_value is not None
    )
    if use_bounce_direction:
        params[recipe.direction_field] = recipe.direction_alt_value
    use_ping_pong_direction = (
        not use_bounce_direction
        and effect_name == recipe.effect_name
        and recipe.direction_field is not None
        and len(recipe.direction_ping_pong_values) == 2
    )
    if (
        effect_name == recipe.effect_name
        and recipe.size_field is not None
        and len(recipe.size_values) == 2
    ):
        params[recipe.size_field] = recipe.size_values[1 if use_alt_style else 0]
    # Two-layer "color over mask" (mega trees): a section-spanning On sits on
    # the top layer with LayerMethod "2 is Unmask", so the motion effect on
    # the layer below only contributes shape/brightness while the On supplies
    # the color. Falls back to the flat single-layer form when the catalog
    # has no On definition. When recipe.mask_sparkles is set (horizontal/
    # vertical/cane/minitree, user request 2026-07-15, matching a real
    # xLights clipboard paste), the On block also gets MusicSparkles at the
    # same deterministic energy-scaled frequency tier-1 BASE already uses.
    on_def = (
        effect_library.effects.get("On") if recipe.color_over_mask else None
    )
    mask_layer_idx = 1 if on_def is not None else 0

    # Primary-motion segment length in beats: 1 for the burst families,
    # longer for calmer ones (icicles run 2-beat segments per the corpus).
    # The alt-style occurrence swaps in a sparser mined stride (cane/
    # horizontal: whole-song ~4-beat pacing), bundled with the same
    # direction/size occurrence bit rather than a fourth independent axis.
    stride = recipe.beats_per_placement
    if use_alt_style and recipe.beats_per_placement_alt is not None:
        stride = recipe.beats_per_placement_alt
    beat_stride = max(1, stride)
    for i in range(0, len(marks), beat_stride):
        start = marks[i].time_ms
        if i + beat_stride < len(marks):
            end = marks[i + beat_stride].time_ms
        else:
            end = min(
                start + max(beat_stride * median_interval, FRAME_INTERVAL_MS),
                section.end_ms,
            )
        if end <= start:
            continue
        direction_cycle = (
            {"param": recipe.direction_field, "values": list(recipe.direction_ping_pong_values)}
            if use_ping_pong_direction
            else None
        )
        instance_index = i // beat_stride
        beat_params = params
        if (
            beat_stride == 1
            and effect_name in _FLIP_TRANSFORM_EFFECTS
            and instance_index % 2 == 1
        ):
            beat_params = dict(params)
            beat_params["B_CHOICE_BufferTransform"] = "Flip Horizontal"
        if effect_name == "Lightning":
            if beat_params is params:
                beat_params = dict(params)
            beat_params.update(_randomized_lightning_fields(
                f"{variation_seed}:lightning:{group.name}:{start}"
            ))
        p = _make_placement(
            effect_def, group.name, start, end,
            beat_params, palette, layer.blend_mode, "beat",
            instance_index=instance_index,
            direction_cycle=direction_cycle, preserve_directions=True,
        )
        p.layer = mask_layer_idx
        placements.append(p)
    if not placements:
        return None

    if on_def is not None:
        on_params = {"T_CHOICE_LayerMethod": "2 is Unmask"}
        if recipe.color_cycle_bars:
            # One On block per color_cycle_beats, stepping through the
            # palette's vivid colors. The alt-style occurrence (same
            # variation_seed parity bit as direction/size/pacing) swaps in
            # color_cycle_beats_alt when set -- confirmed NOT BPM-derived
            # (see color_cycle_beats_alt docstring), so this is a
            # deterministic per-occurrence style pick, not a tempo rule:
            # re-rendering the same song with the same variation_seed always
            # reproduces the same cycle length.
            cycle_beats = (
                recipe.color_cycle_beats_alt
                if use_alt_style and recipe.color_cycle_beats_alt is not None
                else recipe.color_cycle_beats
            )
            for bar_idx, j in enumerate(range(0, len(marks), cycle_beats)):
                bar_start = section.start_ms if j == 0 else marks[j].time_ms
                bar_end = (
                    marks[j + cycle_beats].time_ms
                    if j + cycle_beats < len(marks)
                    else section.end_ms
                )
                if bar_end <= bar_start:
                    continue
                color = _vivid_mask_color(
                    theme_palette, variation_seed, group.name, offset=bar_idx,
                )
                color_layer = _make_placement(
                    on_def, group.name, bar_start, bar_end,
                    dict(on_params), [color], layer.blend_mode, "bar",
                    instance_index=bar_idx,
                )
                color_layer.layer = 0
                if recipe.mask_sparkles:
                    color_layer.music_sparkles = 15 + round(section.energy_score * 0.5)
                placements.append(color_layer)
        else:
            color = _vivid_mask_color(theme_palette, variation_seed, group.name)
            color_layer = _make_placement(
                on_def, group.name, section.start_ms, section.end_ms,
                on_params, [color], layer.blend_mode, "section",
            )
            color_layer.layer = 0
            if recipe.mask_sparkles:
                color_layer.music_sparkles = 15 + round(section.energy_score * 0.5)
            placements.append(color_layer)

    # Optional sustained motion layer beneath the per-beat bursts (matrix
    # idiom — the reference matrices run 2-3 motion layers under the On
    # color layer). One white segment per secondary_beats_per_placement
    # beats so the spin persists between bursts. Same alternating Flip
    # Horizontal as the primary per-beat loop above (user request,
    # 2026-07-15: identical back-to-back Spirals segments here read as
    # repetitive too) -- every other segment flips regardless of stride,
    # since this layer's pacing is its own beats-per-segment setting, not
    # the primary loop's bar-relative one.
    bottom_layer_idx = mask_layer_idx
    secondary_def = (
        effect_library.effects.get(recipe.secondary_effect_name)
        if recipe.secondary_effect_name is not None
        else None
    )
    if secondary_def is not None:
        stride = max(1, recipe.secondary_beats_per_placement)
        # secondary_rotation pool: pick one complete mined preset per
        # qualifying occurrence so repeated sections walk through the mined
        # looks instead of freezing one for the whole song (same occurrence
        # counter and seed fallback as the motion_rotation branch above).
        if recipe.secondary_rotation:
            if occurrence_index is not None:
                pool_idx = occurrence_index % len(recipe.secondary_rotation)
            else:
                pool_idx = (variation_seed // 2) % len(recipe.secondary_rotation)
            secondary_params = dict(recipe.secondary_rotation[pool_idx])
        else:
            secondary_params = dict(recipe.secondary_parameter_overrides)
        bottom_layer_idx = mask_layer_idx + 1
        for j in range(0, len(marks), stride):
            start = marks[j].time_ms
            end = (
                marks[j + stride].time_ms
                if j + stride < len(marks)
                else section.end_ms
            )
            if end <= start:
                continue
            secondary_instance_index = j // stride
            bar_params = secondary_params
            if (
                recipe.secondary_effect_name in _FLIP_TRANSFORM_EFFECTS
                and secondary_instance_index % 2 == 1
            ):
                bar_params = dict(secondary_params)
                bar_params["B_CHOICE_BufferTransform"] = "Flip Horizontal"
            p = _make_placement(
                secondary_def, group.name, start, end,
                bar_params, list(recipe.palette), layer.blend_mode,
                "bar", instance_index=secondary_instance_index, preserve_directions=True,
            )
            p.layer = bottom_layer_idx
            placements.append(p)

    # Corpus idiom for snowflakes/arches: a section-spanning Off on the layer
    # beneath the bursts keeps the group black between bursts instead of
    # picking up whole-house bleed (the reference packages tile qualifying
    # sections with 12-15s Off blocks on the group's second layer).
    if recipe.off_backdrop:
        off_def = effect_library.effects.get("Off")
        if off_def is not None:
            backdrop = _make_placement(
                off_def, group.name, section.start_ms, section.end_ms,
                {}, ["#000000"], layer.blend_mode, "section",
            )
            backdrop.layer = bottom_layer_idx + 1
            placements.append(backdrop)
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
    """Place effect instances per beat, subject to energy-driven density.

    When a beat mark's ``confidence`` (cross-tracker agreement, written by
    ``selector.annotate_agreement_confidence``) is at least
    ``_BEAT_PUNCH_CONFIDENCE_THRESHOLD``, the placement is shortened to
    ``_BEAT_PUNCH_DURATION_MS`` so the effect reads as a brief accent. When
    confidence is ``None`` or below the threshold, the placement spans the
    full beat (pre-change wash behavior) — preserved bit-for-bit when no
    confidence values are written (single-tracker fallback / older fixtures).
    """
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
        wash_end = marks[i + 1].time_ms if i + 1 < len(marks) else min(
            beat_start + 500, section.end_ms
        )
        is_high_confidence = (
            mark.confidence is not None
            and mark.confidence >= _BEAT_PUNCH_CONFIDENCE_THRESHOLD
        )
        if is_high_confidence:
            # Punch path: brief accent flash at the beat onset.
            beat_end = min(beat_start + _BEAT_PUNCH_DURATION_MS, wash_end)
        else:
            # Default wash path — unchanged from pre-confidence behavior.
            beat_end = wash_end
        if beat_end <= beat_start:
            continue
        beat_palette = _resolve_palette(
            palette, chord_marks, tension_curve, beat_start, beat_end, chord_weight,
            chroma_curve=getattr(hierarchy, "chroma_curve", None),
        )
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
    stem: str | None = None,
    direction_cycle: dict | None = None,
) -> list[EffectPlacement]:
    """Place one-shot effect instances on onset/impact events.

    ``stem`` selects which stem's onset track to use (e.g. "vocals", "bass",
    "guitar", "drums").  When None or not found, falls back to the first
    available events track.
    """
    events_track = None
    if stem is not None:
        events_track = hierarchy.events.get(stem)
    if events_track is None:
        # fallback: first available stem
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
                palette, chord_marks, tension_curve, seg_start, seg_end, chord_weight,
                chroma_curve=getattr(hierarchy, "chroma_curve", None),
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
                    palette, chord_marks, tension_curve, sub_start, sub_end, chord_weight,
                    chroma_curve=getattr(hierarchy, "chroma_curve", None),
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
                palette, chord_marks, tension_curve, seg_start, seg_end, chord_weight,
                chroma_curve=getattr(hierarchy, "chroma_curve", None),
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
            palette, chord_marks, tension_curve, section_start, section_end, chord_weight,
            chroma_curve=getattr(hierarchy, "chroma_curve", None),
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
    preserve_directions: bool = False,
) -> EffectPlacement:
    """Create a single EffectPlacement with appropriate fades.

    ``preserve_directions=True`` skips the per-instance direction alternation
    — corpus-recipe placements carry mined direction presets that must not
    be rewritten.
    """
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
    elif not preserve_directions:
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

    Layered tier model (2026-05-06, tier-layering-policy):
    Layers compose correctly in xLights — earlier "silent overwrite"
    concerns were a misdiagnosis of bold-effect-on-BASE producing
    visual overwhelming, not structural overwrite.  Activating multiple
    tiers simultaneously is the right approach so long as each tier
    selects effects appropriate to its role; the variant tier_affinity
    map in `rotation.py` biases tier 1 BASE / 2 GEO toward
    background-tagged variants (Twinkle, Liquid, low-contrast Plasma)
    so they sit underneath the partition tier rather than competing
    with it.

    Tier 1 BASE is now always active — it's the quiet wash that
    provides a constant undertone.  The mood branch then selects which
    partition tier (2 GEO / 4 BEAT / 6 PROP) layers on top of BASE,
    and HERO always runs.  Tiers 3 TYPE, 5 TEX, 7 COMP are not
    activated here; they remain dormant pending separate work.
    """
    if section.mood_tier == "ethereal":
        # Quiet sections: BASE wash + HERO focal props only.  No
        # partition tier — for low-energy passages we want the rest
        # of the display to stay dark so the matrices/mega trees read.
        return frozenset({1, 8})
    if section.mood_tier == "structural":
        if _has_strong_phrase_structure(section, hierarchy):
            return frozenset({1, 2, 8})             # BASE + GEO call-response + HERO
        return frozenset({1, 6, 8})                 # BASE + prop-type variety + HERO
    # Aggressive: BASE + beat chase + prop variety + HERO.  Tier 6
    # is added here because BEAT_1..BEAT_4 partition props four ways,
    # leaving many props dark per section without PROP backing.
    return frozenset({1, 4, 6, 8})


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
    #
    # Exception: props whose tier-6 PROP or tier-8 HERO group received placements
    # this section are skipped — in xLights a model-level effect covers the
    # group's render on that model, so per-model accents would hide the group
    # effect (e.g. the corpus snowflake Shockwave, or a solo mega-topper HERO
    # group's own continuous sequence). The per-model scan is a fallback for
    # layouts where no tier-6/8 group formed around these props, not an
    # additive layer on top of a group that already covers them.
    covered_by_prop_group: set[str] = {
        member
        for g in groups
        if g.tier in (6, 8) and assignment.group_effects.get(g.name)
        for member in g.members
    }
    small_radial_model_names: list[str] = []
    for model_name, prop in props_by_name.items():
        if model_name in covered_by_prop_group:
            logger.debug(
                "drum_accents: prop '%s' covered by a placed tier-6 group, skipping",
                model_name,
            )
            continue
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
            effect_base = variant.base_effect if variant is not None else "Shockwave"

            accent_palette = list(assignment.theme.palette[:2])
            if effect_base in _FIRST_COLOR_ONLY_EFFECTS:
                accent_palette = accent_palette[:1]

            start_ms = frame_align(hit.time_ms)
            end_ms = frame_align(hit.time_ms + _DRUM_ACCENT_DURATION_MS)
            placement = EffectPlacement(
                effect_name=effect_base,
                xlights_id=effect_base,
                model_or_group=model_name,
                start_ms=start_ms,
                end_ms=end_ms,
                parameters=params,
                color_palette=accent_palette,
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


def _whole_house_layer_count(energy_score: int, variation_seed: int) -> int:
    """Extra composite layer count for tier-1 BASE_All, mined from the
    corpus's "All" whole-house group idiom (see _WHOLE_HOUSE_* constants).

    Deterministic in variation_seed so re-running the same song/seed
    reproduces the same layer counts (microscope relies on this).
    """
    if energy_score < _WHOLE_HOUSE_LOW_ENERGY_GATE:
        return 0
    if energy_score < _WHOLE_HOUSE_MID_ENERGY_GATE:
        return 1
    if energy_score < _WHOLE_HOUSE_HIGH_ENERGY_GATE:
        return 3
    # Peak energy: 4 layers is the corpus's single most common state (32% of
    # samples); rare climactic occurrences push to a fuller 6-layer stack
    # (the corpus's 6-7 layer states are together only ~3% of samples).
    return 6 if variation_seed % 4 == 0 else 4


def _place_whole_house_composite(
    groups: list[PowerGroup],
    assignment: SectionAssignment,
    variant_library: Any,
) -> dict[str, list[EffectPlacement]]:
    """Stack energy-gated extra layers on tier-1 BASE_All, mined from the
    reference corpus's "All" whole-house group idiom (see _WHOLE_HOUSE_*
    constants above).

    ``assignment.accent_policy.whole_house_layers`` is the mined TOTAL
    simultaneous-layer target (matching the corpus's own measured
    distribution on the "All" element as a whole), not an extra count on top
    of the theme wash. The wash's own layers (``len(assignment.theme.layers)``,
    typically 1-3, see _assign_layers_to_tiers) are already active for the
    same section, so the composite only adds however many MORE layers are
    needed to reach that total -- placing the full target as pure extras
    would double-count the wash and overshoot the mined distribution (e.g. a
    2-layer wash + a "4" target composite reads as 6 simultaneous layers,
    not 4). New layers start at ``len(assignment.theme.layers)`` so they
    never collide with the wash's own layer indices.

    Section-level gating (``assignment.accent_policy.whole_house_layers``)
    is computed once in ``build_plan`` from ``config.whole_house_composite``
    and ``section.energy_score``; this helper is mechanical and trusts it.
    """
    result: dict[str, list[EffectPlacement]] = {}
    base_layer = len(assignment.theme.layers)
    layer_count = max(0, assignment.accent_policy.whole_house_layers - base_layer)
    if layer_count <= 0:
        return result

    base_group = next((g for g in groups if g.tier == 1), None)
    if base_group is None:
        return result

    section = assignment.section
    variation_seed = assignment.variation_seed
    palette = list(assignment.theme.palette[:2]) or ["#FFFFFF"]

    # All layers in this call share the same start/end (the whole section),
    # so they render simultaneously -- indexing straight into the repeated
    # weighted pool let adjacent i's land on the same effect (e.g. the two
    # "Shader" entries), stacking an effect on top of itself. Rotate through
    # the distinct effect names instead so the mined frequency ranking is
    # preserved but a single stack never repeats an effect except in the
    # rare layer_count=6 case (only 5 distinct effects exist to draw from).
    distinct_pool = list(dict.fromkeys(_WHOLE_HOUSE_EFFECT_POOL))

    for i in range(layer_count):
        effect_name = distinct_pool[(variation_seed + i) % len(distinct_pool)]
        if effect_name == "Shockwave":
            local_seed = variation_seed + i
            params = {
                "E_CHECKBOX_Shockwave_Blend_Edges": "1",
                "E_SLIDER_Shockwave_CenterX": "50",
                "E_SLIDER_Shockwave_CenterY": "50",
                "E_SLIDER_Shockwave_Start_Radius": str(
                    _WHOLE_HOUSE_SHOCKWAVE_START_RADIUS[local_seed % len(_WHOLE_HOUSE_SHOCKWAVE_START_RADIUS)]
                ),
                "E_SLIDER_Shockwave_End_Radius": str(
                    _WHOLE_HOUSE_SHOCKWAVE_END_RADIUS[(local_seed // 3) % len(_WHOLE_HOUSE_SHOCKWAVE_END_RADIUS)]
                ),
                "E_SLIDER_Shockwave_Start_Width": str(
                    _WHOLE_HOUSE_SHOCKWAVE_START_WIDTH[(local_seed // 5) % len(_WHOLE_HOUSE_SHOCKWAVE_START_WIDTH)]
                ),
                "E_SLIDER_Shockwave_End_Width": str(
                    _WHOLE_HOUSE_SHOCKWAVE_END_WIDTH[(local_seed // 7) % len(_WHOLE_HOUSE_SHOCKWAVE_END_WIDTH)]
                ),
                "E_SLIDER_Shockwave_Cycles": str(
                    _WHOLE_HOUSE_SHOCKWAVE_CYCLES[(local_seed // 11) % len(_WHOLE_HOUSE_SHOCKWAVE_CYCLES)]
                ),
                "E_SLIDER_Shockwave_Accel": str(
                    _WHOLE_HOUSE_SHOCKWAVE_ACCEL[(local_seed // 13) % len(_WHOLE_HOUSE_SHOCKWAVE_ACCEL)]
                ),
            }
        elif effect_name == "Shader":
            variant_name = (
                "Shader Plasma Emitter Surge"
                if section.energy_score >= _WHOLE_HOUSE_HIGH_ENERGY_GATE
                else "Shader Plasma Emitter Drift"
            )
            variant = variant_library.get(variant_name) if variant_library is not None else None
            params = dict(variant.parameter_overrides) if variant is not None else {}
        elif effect_name == "Pinwheel":
            local_seed = variation_seed + i
            params = {
                "E_SLIDER_Pinwheel_Thickness": str(
                    _WHOLE_HOUSE_PINWHEEL_THICKNESS[local_seed % len(_WHOLE_HOUSE_PINWHEEL_THICKNESS)]
                ),
                "E_SLIDER_Pinwheel_Twist": str(
                    _WHOLE_HOUSE_PINWHEEL_TWIST[(local_seed // 7) % len(_WHOLE_HOUSE_PINWHEEL_TWIST)]
                ),
                "E_SLIDER_Pinwheel_Arms": str(
                    _WHOLE_HOUSE_PINWHEEL_ARMS[(local_seed // 11) % len(_WHOLE_HOUSE_PINWHEEL_ARMS)]
                ),
            }
        elif effect_name == "Ripple":
            local_seed = variation_seed + i
            params = {
                "E_CHOICE_Ripple_Object_To_Draw": _WHOLE_HOUSE_RIPPLE_OBJECT[
                    local_seed % len(_WHOLE_HOUSE_RIPPLE_OBJECT)
                ],
                "E_CHOICE_Ripple_Movement": _WHOLE_HOUSE_RIPPLE_MOVEMENT[
                    (local_seed // 5) % len(_WHOLE_HOUSE_RIPPLE_MOVEMENT)
                ],
                "E_CHOICE_Ripple_Draw_Style": _WHOLE_HOUSE_RIPPLE_DRAW_STYLE[
                    (local_seed // 7) % len(_WHOLE_HOUSE_RIPPLE_DRAW_STYLE)
                ],
                "E_SLIDER_Ripple_Thickness": str(
                    _WHOLE_HOUSE_RIPPLE_THICKNESS[(local_seed // 11) % len(_WHOLE_HOUSE_RIPPLE_THICKNESS)]
                ),
                "E_SLIDER_Ripple_Scale": str(
                    _WHOLE_HOUSE_RIPPLE_SCALE[(local_seed // 13) % len(_WHOLE_HOUSE_RIPPLE_SCALE)]
                ),
            }
        else:
            params = {}
        placement = EffectPlacement(
            effect_name=effect_name,
            xlights_id=effect_name,
            model_or_group=base_group.name,
            start_ms=section.start_ms,
            end_ms=section.end_ms,
            parameters=params,
            color_palette=list(palette),
            layer=base_layer + i,
        )
        result.setdefault(base_group.name, []).append(placement)

    return result


# Singing faces (spec: singing-faces-on-export). Words closer together than
# this gap belong to the same vocal region; larger gaps split regions so no
# Faces effect sits over long instrumental passages.
_FACES_VOCAL_GAP_MS = 5000
# xLights consumes lyrics as one 3-layer timing track named "Lyrics"
# (phrases/words/phonemes — see xsq_writer._build_lyric_layers). Faces takes
# the track name; Text takes "<track> - Words" to select the word layer.
_FACES_TIMING_TRACK = "Lyrics"
_LYRIC_TEXT_TIMING_TRACK = "Lyrics - Words"
# Second track for a featured/backup singer (src.analyzer.vocal_diarization),
# gated by GenerationConfig.vocal_diarization. Mirrors the lead-singer track
# names above; see xsq_writer._build_lyric_layers for the second Element.
_FACES_BACKUP_TIMING_TRACK = "Lyrics - Backup"
_LYRIC_TEXT_BACKUP_TIMING_TRACK = "Lyrics - Backup - Words"


def _split_words_by_speaker(vocal_words: Optional[list[dict]]) -> tuple[list[dict], list[dict]]:
    """Split word marks into (speaker 0, speaker 1) lists.

    Words without a ``speaker`` key (e.g. from an analysis run before
    diarization existed) default to speaker 0. Returns ``([], [])`` for
    empty/``None`` input.
    """
    if not vocal_words:
        return [], []
    lead = [w for w in vocal_words if w.get("speaker", 0) == 0]
    backup = [w for w in vocal_words if w.get("speaker", 0) == 1]
    return lead, backup


def _place_singing_faces(
    props: list[Any],
    vocal_words: Optional[list[dict]],
    vocal_diarization: bool = False,
) -> dict[str, list[EffectPlacement]]:
    """Place xLights Faces effects on dedicated singing props over vocal regions.

    Targets only props with a NodeRange face definition
    (``Prop.face_definitions``) — node-mapped mouth shapes on singer cutouts.
    Matrices/trees with image-based (Matrix-type) face sets are excluded by
    the layout parser. One placement per contiguous vocal region (word marks
    merged across gaps < ``_FACES_VOCAL_GAP_MS``), each pointed at the
    3-layer "Lyrics" timing track; xLights renders the matching mouth per
    phoneme-layer label. Effect settings are copied verbatim from a
    user-verified working effect.

    When ``vocal_diarization`` is on, ``vocal_words`` carries WhisperX marks
    tagged with a ``speaker`` key (0=lead, 1=featured/backup — see
    ``src.analyzer.vocal_diarization``), and at least two face-capable props
    exist, the second face prop (by layout order — no per-song "which prop
    is the backup singer" config, per explicit user choice 2026-07-21)
    renders only the speaker-1 words on a second "Lyrics - Backup" timing
    track, while every other face prop renders only speaker-0 words. With
    only one face prop, or no confidently-detected second voice
    (``vocal_diarization.diarize_words`` collapses everyone to speaker 0),
    this degrades to the original behavior: every face prop gets every word.

    Deliberately independent of hierarchy sections (bug-159: a 0-section
    analysis must not zero out face placements): regions derive from the
    word marks alone. Returns ``{}`` when there are no words or no
    face-capable props.
    """
    result: dict[str, list[EffectPlacement]] = {}
    face_props = [p for p in props if getattr(p, "face_definitions", None)]
    if not face_props:
        return result

    if vocal_diarization:
        lead_only_words, backup_words = _split_words_by_speaker(vocal_words)
    else:
        lead_only_words, backup_words = vocal_words, []
    backup_prop = face_props[1] if (backup_words and len(face_props) >= 2) else None
    lead_words = vocal_words if backup_prop is None else lead_only_words

    lead_regions = _vocal_regions(lead_words)
    backup_regions = _vocal_regions(backup_words) if backup_prop is not None else []
    if not lead_regions and not backup_regions:
        return result

    for prop in face_props:
        is_backup = prop is backup_prop
        regions = backup_regions if is_backup else lead_regions
        if not regions:
            continue
        face_name = _best_face_definition(prop.name, prop.face_definitions)
        placements: list[EffectPlacement] = []
        for start, end in regions:
            placements.append(EffectPlacement(
                effect_name="Faces",
                xlights_id="Faces",
                model_or_group=prop.name,
                start_ms=start,
                end_ms=end,
                parameters={
                    "E_CHOICE_Faces_FaceDefinition": face_name,
                    "E_CHOICE_Faces_TimingTrack": (
                        _FACES_BACKUP_TIMING_TRACK if is_backup else _FACES_TIMING_TRACK
                    ),
                },
                color_palette=["#FFFFFF"],
            ))
        result[prop.name] = placements

    logger.info(
        "singing_faces: %d face prop(s) placed%s",
        len(result), " (with backup singer track)" if backup_prop is not None else "",
    )
    return result


def _best_face_definition(prop_name: str, face_definitions: list[str]) -> str:
    """Pick the face definition that best matches the prop's name.

    A model can carry several NodeRange definitions (e.g. "Singing Tree Male"
    holds both "Female Face" and "Male Face"); blindly taking the first would
    give the male tree the female mouth mapping. Score by shared name tokens
    and fall back to the first definition when nothing matches.
    """
    if len(face_definitions) == 1:
        return face_definitions[0]
    prop_tokens = set(prop_name.lower().split())
    best = max(
        face_definitions,
        key=lambda d: len(prop_tokens & set(d.lower().split())),
    )
    return best


# Bitmap font for a "*Lyrics*Small*"-named matrix (user request,
# 2026-07-18, changed to 5-5x5 Thin 2026-07-21): xLights has no numeric
# font-size slider for the Text effect's bitmap-font mode, only a fixed
# choice list; "5-5x5 Thin" is 5px tall vs. the default "10-12x12 Bold"'s
# 12px (_XLIGHTS_EFFECT_DEFAULTS["Text"]["E_CHOICE_Text_Font"] in
# xsq_writer.py).
_LYRIC_TEXT_SMALL_FONT = "5-5x5 Thin"


def _place_lyric_text(
    props: list[Any],
    vocal_words: Optional[list[dict]],
    vocal_diarization: bool = False,
) -> dict[str, list[EffectPlacement]]:
    """Place a word-synced Text effect on every matrix prop named for lyrics.

    Uses the xLights Text effect's ``Lyric Track`` mode
    (``E_CHOICE_Text_LyricTrack``) pointed at the "Words" timing track, so
    the matrix displays each sung word as it lands. One placement per
    contiguous vocal region per target, on layer 0 — the first (top)
    render layer of the matrix's own model element. Returns ``{}`` when
    there are no words or no Matrix props in the layout.

    Every matrix prop whose name contains "lyric" (e.g. "Lyrics Matrix",
    "Lyrics Matrix Small") gets the same placement -- not just the
    largest one (2026-07-18: previously only ever targeted a single
    matrix, so a second lyrics-display prop got nothing). A prop whose
    name also contains "small" renders at ``_LYRIC_TEXT_SMALL_FONT``
    instead of the catalog default; everything else about the effect is
    identical between targets. When no prop is named for lyrics at all,
    falls back to the single largest matrix prop (unchanged behavior).

    When ``vocal_diarization`` is on and at least two targets exist, the
    second target (by the same order as above) renders only speaker-1
    words on a second "Lyrics - Backup - Words" track (see
    ``_place_singing_faces`` for the matching Faces behavior); every other
    target renders only speaker-0 words. Degrades to the original
    behavior — every target gets every word — with one target or no
    confidently-detected second voice.
    """
    result: dict[str, list[EffectPlacement]] = {}
    matrix_props = [p for p in props if getattr(p, "display_as", "") == "Matrix"]
    if not matrix_props:
        return result

    named = [p for p in matrix_props if "lyric" in p.name.lower()]
    if named:
        targets = named
    else:
        targets = [max(matrix_props, key=lambda p: (getattr(p, "pixel_count", 0), p.name))]

    if vocal_diarization:
        lead_only_words, backup_words = _split_words_by_speaker(vocal_words)
    else:
        lead_only_words, backup_words = vocal_words, []
    backup_target = targets[1] if (backup_words and len(targets) >= 2) else None
    lead_words = vocal_words if backup_target is None else lead_only_words

    lead_regions = _vocal_regions(lead_words)
    backup_regions = _vocal_regions(backup_words) if backup_target is not None else []
    if not lead_regions and not backup_regions:
        return result

    for target in targets:
        is_backup = target is backup_target
        regions = backup_regions if is_backup else lead_regions
        if not regions:
            continue
        parameters: dict[str, Any] = {
            "E_CHOICE_Text_LyricTrack": (
                _LYRIC_TEXT_BACKUP_TIMING_TRACK if is_backup else _LYRIC_TEXT_TIMING_TRACK
            ),
        }
        if "small" in target.name.lower():
            parameters["E_CHOICE_Text_Font"] = _LYRIC_TEXT_SMALL_FONT
        placements: list[EffectPlacement] = []
        for start, end in regions:
            placements.append(EffectPlacement(
                effect_name="Text",
                xlights_id="Text",
                model_or_group=target.name,
                start_ms=start,
                end_ms=end,
                parameters=dict(parameters),
                color_palette=["#FFFFFF"],
            ))
        result[target.name] = placements

        logger.info(
            "lyric_text: Text/LyricTrack placed on matrix '%s' over %d vocal region(s)",
            target.name, len(regions),
        )
    return result


def _format_video_duration(duration_ms: int) -> str:
    """Format milliseconds as xLights' Video Duration string: ``m:ss.mmm``."""
    total_seconds, ms = divmod(duration_ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}.{ms:03d}"


def _place_video_effect(
    props: list[Any],
    video_path: Any,
    duration_ms: int,
) -> dict[str, list[EffectPlacement]]:
    """Place a Video effect spanning the whole song on the largest matrix prop.

    Explicit opt-in only: fires when the song has a ``video_path`` (from a
    video-file import), never selected as part of the general effect pool —
    corpus-mined matrix recipes deliberately don't replicate Video content
    (see ``corpus_recipes.py``). Returns ``{}`` when there's no video or no
    Matrix props in the layout.
    """
    if video_path is None:
        return {}
    matrix_props = [p for p in props if getattr(p, "display_as", "") == "Matrix"]
    if not matrix_props:
        return {}

    target = max(matrix_props, key=lambda p: (getattr(p, "pixel_count", 0), p.name))
    placement = EffectPlacement(
        effect_name="Video",
        xlights_id="Video",
        model_or_group=target.name,
        start_ms=0,
        end_ms=duration_ms,
        parameters={
            "E_FILEPICKERCTRL_Video_Filename": str(video_path),
            "E_TEXTCTRL_Duration": _format_video_duration(duration_ms),
        },
        color_palette=["#FFFFFF"],
    )

    logger.info(
        "video_effect: Video placed on matrix '%s' from '%s'",
        target.name, video_path,
    )
    return {target.name: [placement]}


# How long a lyric-matched image stays on screen per burst, and the minimum
# cooldown before the *same* image can repeat on a target (distinct images
# only need to not overlap in time -- see the placement loop below). A word
# that recurs often across the song (e.g. "sing" through a repeated chorus)
# can generate a match every single time it's sung; a short cooldown just
# thinned out the closest repeats and still let one image dominate the whole
# song. User request (2026-07-15): stay selective -- the same picture should
# resurface only a handful of times across a whole song, not every time its
# word comes up.
# Burst duration scales with the matched word's own duration
# (match["end_ms"] - match["start_ms"]) instead of a flat length, so a
# quick word doesn't trigger a picture that visibly outlives it (user
# request, 2026-07-21). Floored so very short words still give the image
# enough screen time to register, and jittered per-burst (seeded, same
# pattern as direction/motion/speed below) so same-length words don't all
# produce identically-sized bursts.
_PICTURE_MIN_BURST_MS = 3_000
_PICTURE_BURST_JITTER_MS = 1_500
_PICTURE_MIN_GAP_MS = 90_000
_PICTURE_FADE_MS = 800
# Start the burst this far ahead of the matched word's own start time, so the
# image (plus its fade-in) is already fully visible by the moment the lyric
# is actually sung, rather than popping in right on top of it (user request,
# 2026-07-15).
_PICTURE_LEAD_MS = 1_000
# Keep the image a modest accent rather than filling the whole buffer, per
# user request (2026-07-15): the picture should feel like a small addition
# to the sequence, not overwhelm it.
_PICTURE_SCALE_PERCENT = 55
# Movement speed varies per burst within this inclusive range (user request,
# 2026-07-18: the fixed 3 made every pan glide at the same rate).
_PICTURE_SPEED_RANGE = (2, 6)
# All 8 cardinal/diagonal xLights Pictures_Direction pan directions (user
# request, 2026-07-15: the original 4 felt monotonous burst-to-burst).
_PICTURE_DIRECTIONS = (
    "left", "right", "up", "down",
    "up-left", "up-right", "down-left", "down-right",
)

# Lightning randomization (user request, 2026-07-18): xLights' own field IDs
# and UI labels are swapped for two sliders (verified against
# resources/effectmetadata/Lightning.json) -- E_SLIDER_Lightning_WIDTH is
# labeled "Width", E_SLIDER_Number_Segments is labeled "Width of Bolt", and
# E_SLIDER_Number_Bolts is labeled "Number of Segments". Only the two
# UI-labeled "Width"/"Width of Bolt" sliders and Direction vary per bolt;
# Number_Bolts stays fixed at the mined value of 10.
_LIGHTNING_WIDTH_RANGE = (1, 3)          # E_SLIDER_Lightning_WIDTH ("Width")
_LIGHTNING_SEGMENTS_RANGE = (1, 5)       # E_SLIDER_Number_Segments ("Width of Bolt")
_LIGHTNING_DIRECTIONS = ("Up", "Down")   # E_CHOICE_Lightning_Direction


def _randomized_lightning_fields(seed_key: str) -> dict[str, str]:
    rng = random.Random(seed_key)
    return {
        "E_CHOICE_Lightning_Direction": rng.choice(_LIGHTNING_DIRECTIONS),
        "E_SLIDER_Lightning_WIDTH": str(rng.randint(*_LIGHTNING_WIDTH_RANGE)),
        "E_SLIDER_Number_Segments": str(rng.randint(*_LIGHTNING_SEGMENTS_RANGE)),
    }

# Occasional buffer-transform motion overlays for picture bursts (user
# request, 2026-07-18). The value-curve strings are copied verbatim from
# working xLights clipboard samples — parametric Ramp/Sine curves, passed
# straight through placement.parameters (they contain no commas, so they
# survive the comma-joined settings string). "normal" keeps today's plain
# pan and dominates the weighting so motion stays an occasional accent.
_PICTURE_MOTION_ZOOM_RAMP = (
    "Active=TRUE|Id=ID_VALUECURVE_Zoom|Type=Ramp|Min=0.00|Max=30.00|P2=10.00|RV=TRUE|"
)
_PICTURE_MOTIONS: dict[str, dict[str, str]] = {
    "normal": {},
    "explode": {"B_VALUECURVE_Zoom": _PICTURE_MOTION_ZOOM_RAMP},
    "shake": {
        # Original values (Rotations=10, Cycles=50) came from xLights' own
        # built-in "Shake" Roto-Zoom preset, copied verbatim -- not a
        # copy-paste mistake on our end, the stock preset itself just
        # doesn't read well as a picture-burst accent (user-confirmed
        # 2026-07-21, "not good as we found out"). Tuned down instead:
        # Rotations=0 (no continuous full-circle spin underneath) + a Sine
        # value curve for the wobble itself (Start=P1/Min baseline,
        # Amplitude=P2, Cycles=P3, Vertical Offset=P4 -- field mapping
        # confirmed against xLights' own Value Curve dialog, 2026-07-21).
        # Cycles dropped from 50 to 5: 50 sine oscillations across one
        # effect read as a rapid buzz/vibration, not a shake.
        "B_SLIDER_Rotations": "0",
        "B_SLIDER_ZoomQuality": "2",
        "B_VALUECURVE_Rotation": (
            "Active=TRUE|Id=ID_VALUECURVE_Rotation|Type=Sine|Min=0.00|Max=100.00"
            "|P2=10.00|P3=5.00|P4=25.00|WRAP=TRUE|RV=TRUE|"
        ),
    },
    "explode_spin": {
        "B_SLIDER_Rotations": "10",
        "B_SLIDER_ZoomQuality": "2",
        "B_VALUECURVE_Rotation": (
            "Active=TRUE|Id=ID_VALUECURVE_Rotation|Type=Ramp|Min=0.00|Max=100.00"
            "|P2=100.00|RV=TRUE|"
        ),
        "B_VALUECURVE_Zoom": _PICTURE_MOTION_ZOOM_RAMP,
    },
}
_PICTURE_MOTION_NAMES = tuple(_PICTURE_MOTIONS)
_PICTURE_MOTION_WEIGHTS = (60, 13, 13, 13)

# Name tokens identifying mega tree props — matches corpus_recipes.py's
# megatree PropFamilyRecipe.match_tokens so eligibility stays consistent
# with how the rest of the generator identifies this family.
_MEGATREE_NAME_TOKENS = ("megatree", "mega_tree", "mega tree")


def _place_picture_effects(
    props: list[Any],
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    duration_ms: int,
    variation_seed: int,
    word_image_matches: list[dict] | None = None,
    existing_layers: dict[str, int] | None = None,
) -> dict[str, list[EffectPlacement]]:
    """Place Pictures effects as a top-layer accent overlay on Matrix/Mega Tree
    props, timed to lyric-image matches (``word_image_matches``, from
    ``image_catalog.suggest_images_for_words``) rather than a fixed clock —
    every burst corresponds to a specific matched lyric word. Returns ``{}``
    when there are no matches; there is no generic filler/rotation content.

    ``existing_layers`` maps each target group/model name to the lowest
    (i.e. topmost-rendering) xLights EffectLayer index already occupied
    there by the per-section theme/rotation content (see ``plan.py``'s
    call site, which derives it from ``assignment.group_effects`` before
    this runs). Each burst is placed one layer below that number (bug-243
    follow-up, 2026-07-15) -- xsq_writer serializes ``<EffectLayer>``
    children in ascending layer-index order, and xLights renders the
    *first* EffectLayer child on top, not the last: a fixed ``layer=1``
    first collided with whatever theme layer a group's rotation pool
    already occupied (a densely-packed pool, Ripple/Shockwave/Pinwheel
    running nearly back-to-back for the whole song, meant xsq_writer's
    per-layer overlap remover trimmed 6000ms bursts down to 100-275ms
    slivers), and a first attempt at fixing that moved the burst to the
    *highest* layer number under the assumption higher-number-renders-on-
    top -- confirmed wrong by inspecting a real generated .xsq (burst
    landed as the LAST EffectLayer child, i.e. visually at the bottom of
    the stack, matching the user's screenshot of it hidden behind an
    opaque "On" layer). Going one below whatever the group's topmost
    layer already uses guarantees no collision and puts the burst first
    in the serialized layer order regardless of how many layers a given
    theme's composition occupies.

    Song-scoped, same rationale as ``_place_video_effect``/``_place_singing_faces``:
    fires once per generation, not part of the per-section theme/pool rotation.
    Eligibility is deliberately narrow (Matrix display type or a Mega Tree name
    match) rather than the ``Pictures`` effect's broader ``prop_suitability``
    rating: reviewing the reference corpus (2026-07-15) showed only Matrix/Mega
    Tree props carry real varied Pictures content.

    Each eligible prop is redirected to its most specific enclosing tier
    group (looked up in ``groups`` by membership) rather than placed on its
    own raw model row. This matters because of a previously-hit xLights
    rendering quirk (bug-184, 2026-07-12): when a model has its own direct
    effect on its own row, that row's effect covers/overrides whatever the
    model's parent group renders onto it — group and direct-model content
    do not blend. Placing the picture burst on the group instead lets it
    stack as an ordinary extra layer alongside the group's existing theme
    content (confirmed 2026-07-15 against a real generated .xsq: Pictures
    placed directly on the raw "Matrix"/"Mega Tree" model blanked out all
    the theme content the "06_PROP_Matrix"/"08_HERO_Mega_Tree" groups carry
    for those same props).

    "Most specific" deliberately excludes tier-1 whole-house canvas groups
    (bug-243, 2026-07-15): every prop is also a member of ``01_BASE_All``,
    which ``groups`` always lists before any tier-6/8 group, so a plain
    first-match lookup always redirected the burst onto the entire-display
    canvas instead of the intended matrix — the overlay was in the file but
    never visible as a matrix accent. Candidates are filtered to non-tier-1,
    non-``_FADES`` groups and the smallest-membership (tightest) match wins.
    A prop with no such enclosing group falls back to its own row directly,
    same as before.

    Each burst uses a modest fixed scale (``_PICTURE_SCALE_PERCENT``) so the
    image reads as an accent rather than filling the whole buffer, a short
    fade in/out (``_PICTURE_FADE_MS``), and a gentle pan (seeded per burst so
    it isn't always the same direction) — user request (2026-07-15): overlay
    the picture with movement, don't just cut it in statically. A weighted
    seeded pick (``_PICTURE_MOTIONS``/``_PICTURE_MOTION_WEIGHTS``) occasionally
    adds a buffer-transform motion on top — explode (zoom ramp), shake
    (rotation sine), or explode+spin — with plain "normal" dominating so the
    motions stay an accent (user request, 2026-07-18).
    """
    if duration_ms <= 0:
        return {}
    pictures_def = effect_library.get("Pictures")
    if pictures_def is None:
        return {}

    eligible = [
        p for p in props
        if (
            getattr(p, "display_as", "") == "Matrix"
            or any(tok in getattr(p, "name", "").lower() for tok in _MEGATREE_NAME_TOKENS)
        )
        and "lyric" not in getattr(p, "name", "").lower()
    ]
    if not eligible:
        return {}

    targets: dict[str, str] = {}
    for prop in eligible:
        name = getattr(prop, "name", "")
        candidates = [
            g for g in groups
            if name in g.members and g.tier > 1 and not g.name.endswith("_FADES")
        ]
        group = min(candidates, key=lambda g: (len(g.members), g.name), default=None)
        targets[name] = group.name if group is not None else name

    picture_layer_by_target: dict[str, int] = {
        target_name: (existing_layers or {}).get(target_name, 1) - 1
        for target_name in set(targets.values())
    }

    matches = sorted(
        (
            m for m in (word_image_matches or [])
            if m.get("stored_path") is not None
            and m.get("start_ms") is not None
            and m.get("end_ms") is not None
        ),
        key=lambda m: m["start_ms"],
    )
    if not matches:
        return {}

    result: dict[str, list[EffectPlacement]] = {}
    scheduled_end_by_target: dict[str, int] = {}
    last_end_by_target_and_file: dict[tuple[str, str], int] = {}
    for match in matches:
        word_start = int(match["start_ms"])
        start = max(0, word_start - _PICTURE_LEAD_MS)
        if start >= duration_ms:
            continue
        word_duration_ms = max(0, int(match["end_ms"]) - word_start)
        jitter_ms = random.Random(
            f"{variation_seed}:duration:{match.get('word')}:{word_start}"
        ).randint(0, _PICTURE_BURST_JITTER_MS)
        burst_ms = max(_PICTURE_MIN_BURST_MS, word_duration_ms) + jitter_ms
        end = min(start + burst_ms, duration_ms)
        if end <= start:
            continue
        filename = match["stored_path"]
        direction = _PICTURE_DIRECTIONS[
            random.Random(f"{variation_seed}:{match.get('word')}:{word_start}")
            .randrange(len(_PICTURE_DIRECTIONS))
        ]
        motion = random.Random(
            f"{variation_seed}:motion:{match.get('word')}:{word_start}"
        ).choices(_PICTURE_MOTION_NAMES, weights=_PICTURE_MOTION_WEIGHTS)[0]
        speed = random.Random(
            f"{variation_seed}:speed:{match.get('word')}:{word_start}"
        ).randint(*_PICTURE_SPEED_RANGE)
        for target_name in set(targets.values()):
            # Bursts on the same target may never overlap in time regardless
            # of image, but the _PICTURE_MIN_GAP_MS cooldown only applies to
            # *repeating the same image* (bug, 2026-07-15): a word that
            # recurs often in the lyrics (e.g. a repeated chorus line) used
            # to monopolize every nearby slot and silently crowd out a rarer,
            # differently-imaged match that fell within the same gap window,
            # even though showing a different picture back-to-back doesn't
            # read as flicker the way repeating one does.
            last_end = scheduled_end_by_target.get(target_name)
            if last_end is not None and start < last_end:
                continue
            last_same_file_end = last_end_by_target_and_file.get((target_name, filename))
            if last_same_file_end is not None and start - last_same_file_end < _PICTURE_MIN_GAP_MS:
                continue
            scheduled_end_by_target[target_name] = end
            last_end_by_target_and_file[(target_name, filename)] = end
            result.setdefault(target_name, []).append(EffectPlacement(
                effect_name="Pictures",
                xlights_id="Pictures",
                model_or_group=target_name,
                start_ms=start,
                end_ms=end,
                parameters={
                    "E_TEXTCTRL_Pictures_Filename": filename,
                    "E_CHECKBOX_Pictures_TransparentBlack": "1",
                    # Threshold (sum of R+G+B, 0-300) so near-black JPEG
                    # backgrounds from AI-generated images key out too,
                    # not just pure #000000.
                    "E_TEXTCTRL_Pictures_TransparentBlack": "30",
                    "E_CHOICE_Pictures_Direction": direction,
                    "E_CHOICE_Scaling": "Scale To Fit",
                    "E_TEXTCTRL_Pictures_Speed": speed,
                    "E_SLIDER_Pictures_StartScale": _PICTURE_SCALE_PERCENT,
                    "E_SLIDER_Pictures_EndScale": _PICTURE_SCALE_PERCENT,
                    **_PICTURE_MOTIONS[motion],
                },
                color_palette=["#FFFFFF"],
                layer=picture_layer_by_target[target_name],
                fade_in_ms=_PICTURE_FADE_MS,
                fade_out_ms=_PICTURE_FADE_MS,
            ))
            logger.debug(
                "picture_effects: %s burst %d-%d -> lyric match %r (%s, motion=%s)",
                target_name, start, end, match.get("word"), filename, motion,
            )

    logger.info(
        "picture_effects: %d target(s), %d lyric-matched burst(s) scheduled",
        len(result), sum(len(v) for v in result.values()),
    )
    return result


def _vocal_regions(vocal_words: Optional[list[dict]]) -> list[tuple[int, int]]:
    """Merge word marks into contiguous vocal regions.

    Words separated by less than ``_FACES_VOCAL_GAP_MS`` share a region;
    larger silences split regions. Returns ``[]`` for empty input.
    """
    if not vocal_words:
        return []
    spans = sorted(
        (int(w["start_ms"]), int(w["end_ms"]))
        for w in vocal_words
        if int(w["end_ms"]) > int(w["start_ms"])
    )
    if not spans:
        return []
    regions: list[tuple[int, int]] = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = regions[-1]
        if start - prev_end < _FACES_VOCAL_GAP_MS:
            regions[-1] = (prev_start, max(prev_end, end))
        else:
            regions.append((start, end))
    return regions


# Rare whole-house crash accent (see src/analyzer/crash_accents.py). A short
# Shockwave burst on 01_BASE_All_FADES at the song's most extreme percussive
# transients -- by design most songs get zero of these.
_CRASH_EFFECT_DURATION_MS = 700
# A crash landing inside a sung word reads as accompaniment, not a standalone
# accent; per user design decision (2026-07-14) losing a true-positive crash
# this way is preferred over letting vocal transients through as false hits.
_CRASH_VOCAL_EXCLUSION_MS = 500
# The effect starts this long before the actual crash mark and still ends
# _CRASH_EFFECT_DURATION_MS after it (user request, 2026-07-16) -- the
# build/lead-in gives the flash room to peak right as the crash sound
# hits, rather than snapping on exactly at the mark. Vocal/fade exclusion
# checks still key off the mark's true timestamp, not this shifted start.
_CRASH_LEAD_MS = 1000


def _place_crash_accents(
    groups: list[PowerGroup],
    hierarchy: HierarchyResult,
    vocal_words: Optional[list[dict]],
    variant_library: Any,
    fade_exclusion_start_ms: Optional[int] = None,
) -> dict[str, list[EffectPlacement]]:
    """Place a short Shockwave on ``01_BASE_All_FADES`` at each rare crash
    mark from ``hierarchy.crash_accents``.

    Starts ``_CRASH_LEAD_MS`` before the mark and ends
    ``_CRASH_EFFECT_DURATION_MS`` after it, so the flash builds into and
    peaks at the actual crash sound. Excludes marks within
    ``_CRASH_VOCAL_EXCLUSION_MS`` of any vocal word,
    and marks at or after ``fade_exclusion_start_ms`` (the same group's
    existing end-of-song Min-blend fade -- see ``plan._place_end_of_song_fade``
    -- covers that span and a Shockwave there would collide with it).
    Song-scoped like ``_place_singing_faces``/``_place_video_effect``, not
    routed through the per-section pipeline.

    Matrix-family groups get a white Lightning burst over the same window
    (user request 2026-07-18): the reference packages use matrix Lightning
    as a rare accent, not a section texture, so it pairs with the crash
    choreography (whole-house Shockwave + Moving Head punch) instead of
    living in the recipe's motion rotation. Alternating marks rotate the
    bolts 90 degrees, the second-most-common mined Lightning variant.
    """
    result: dict[str, list[EffectPlacement]] = {}
    if not hierarchy.crash_accents:
        return result
    if not any(g.name == "01_BASE_All_FADES" for g in groups):
        return result

    word_spans = [
        (int(w["start_ms"]), int(w["end_ms"]))
        for w in (vocal_words or [])
        if int(w["end_ms"]) > int(w["start_ms"])
    ]

    def _near_vocal(time_ms: int) -> bool:
        return any(
            start - _CRASH_VOCAL_EXCLUSION_MS <= time_ms <= end + _CRASH_VOCAL_EXCLUSION_MS
            for start, end in word_spans
        )

    variant = variant_library.get("Shockwave Full Fast") if variant_library is not None else None
    params = dict(variant.parameter_overrides) if variant is not None else {}

    matrix_groups = [
        g for g in groups
        if (recipe := recipe_for_group(g)) is not None and recipe.family == "matrix"
    ]

    placements: list[EffectPlacement] = []
    matrix_placements: dict[str, list[EffectPlacement]] = {}
    accent_index = 0
    for mark in hierarchy.crash_accents:
        if _near_vocal(mark.time_ms):
            continue
        if fade_exclusion_start_ms is not None and mark.time_ms >= fade_exclusion_start_ms:
            continue
        start_ms = max(0, mark.time_ms - _CRASH_LEAD_MS)
        end_ms = min(mark.time_ms + _CRASH_EFFECT_DURATION_MS, hierarchy.duration_ms)
        if end_ms <= start_ms:
            continue
        placements.append(EffectPlacement(
            effect_name="Shockwave",
            xlights_id="Shockwave",
            model_or_group="01_BASE_All_FADES",
            start_ms=start_ms,
            end_ms=end_ms,
            parameters=params,
            color_palette=["#FFFFFF"],
        ))
        lightning_params: dict[str, Any] = dict(_LIGHTNING_FLICKER)
        lightning_params.update(_randomized_lightning_fields(f"lightning:{mark.time_ms}"))
        if accent_index % 2 == 1:
            lightning_params["B_CHOICE_BufferTransform"] = "Rotate CC 90"
        for g in matrix_groups:
            p = EffectPlacement(
                effect_name="Lightning",
                xlights_id="Lightning",
                model_or_group=g.name,
                start_ms=start_ms,
                end_ms=end_ms,
                parameters=dict(lightning_params),
                color_palette=["#FFFFFF"],
            )
            # xLights renders the FIRST EffectLayer on top (bug-248); a
            # negative index sorts above the recipe's layers 0-2.
            p.layer = -1
            matrix_placements.setdefault(g.name, []).append(p)
        accent_index += 1

    if placements:
        result["01_BASE_All_FADES"] = placements
        result.update(matrix_placements)
    return result


# Riff-burst accent on Star-family groups (see src/analyzer/riff_bursts.py:
# snare-roll/fill detection, user request 2026-07-18). Deliberately targets
# a prop group rather than Moving Head: the crash-accent MH warmup fills
# the entire natural gap back to the previous placement, which silently
# blocked every riff-burst window when tried on Moving Head earlier the
# same day (see CLAUDE.md -> "Riff/Fill Detector for Moving Head Accent").
# Stars don't share DMX channels with anything else, so no such collision.
# Pinwheel preset supplied directly by the user (real xLights clipboard
# paste, 2026-07-18): 3 arms, twist 148, thickness 28, speed ramping 10->45
# over the placement via value curve, red/yellow/orange palette.
_STAR_BURST_DURATION_MS = 1050
_STAR_BURST_VOCAL_EXCLUSION_MS = 500
_STAR_BURST_PARAMS: dict[str, str] = {
    "B_CHOICE_BufferStyle": "Per Model Per Preview",
    "E_CHECKBOX_Pinwheel_Rotation": "0",
    "E_CHOICE_Pinwheel_3D": "None",
    "E_CHOICE_Pinwheel_Style": "New Render Method",
    "E_SLIDER_PinwheelXC": "0",
    "E_SLIDER_PinwheelYC": "0",
    "E_SLIDER_Pinwheel_ArmSize": "100",
    "E_SLIDER_Pinwheel_Arms": "3",
    "E_SLIDER_Pinwheel_Offset": "0",
    "E_SLIDER_Pinwheel_Thickness": "28",
    "E_SLIDER_Pinwheel_Twist": "148",
    "E_VALUECURVE_Pinwheel_Speed": (
        "Active=TRUE|Id=ID_VALUECURVE_Pinwheel_Speed|Type=Ramp|"
        "Min=0.00|Max=50.00|P1=10.00|P2=45.00|RV=TRUE|"
    ),
    "T_CHOICE_LayerMethod": "Normal",
    "T_SLIDER_EffectLayerMix": "0",
    # T_CHECKBOX_Canvas deliberately omitted -- never emit it (see
    # CLAUDE.md engineering rule; xsq_writer strips it unconditionally
    # anyway, but the source of truth shouldn't carry it either).
}
_STAR_BURST_PALETTE = ["#FF0000", "#FFFF00", "#FF8000"]


def _place_star_bursts(
    groups: list[PowerGroup],
    hierarchy: HierarchyResult,
    vocal_words: Optional[list[dict]],
    fade_exclusion_start_ms: Optional[int] = None,
) -> dict[str, list[EffectPlacement]]:
    """Place a short Pinwheel burst on Star-family groups at each rare
    riff/fill mark from ``hierarchy.riff_bursts``.

    Song-scoped like ``_place_crash_accents``, not routed through the
    per-section pipeline. Layered above the star group's regular recipe
    content (layer -1) so it reads as a distinct one-off pop rather than
    blending into the family's normal Shockwave rotation.
    """
    result: dict[str, list[EffectPlacement]] = {}
    if not hierarchy.riff_bursts:
        return result

    star_groups = [
        g for g in groups
        if (recipe := recipe_for_group(g)) is not None and recipe.family == "star"
    ]
    if not star_groups:
        return result

    word_spans = [
        (int(w["start_ms"]), int(w["end_ms"]))
        for w in (vocal_words or [])
        if int(w["end_ms"]) > int(w["start_ms"])
    ]

    def _near_vocal(time_ms: int) -> bool:
        return any(
            start - _STAR_BURST_VOCAL_EXCLUSION_MS <= time_ms <= end + _STAR_BURST_VOCAL_EXCLUSION_MS
            for start, end in word_spans
        )

    for mark in hierarchy.riff_bursts:
        if _near_vocal(mark.time_ms):
            continue
        if fade_exclusion_start_ms is not None and mark.time_ms >= fade_exclusion_start_ms:
            continue
        start_ms = mark.time_ms
        end_ms = min(mark.time_ms + _STAR_BURST_DURATION_MS, hierarchy.duration_ms)
        if end_ms <= start_ms:
            continue
        for g in star_groups:
            p = EffectPlacement(
                effect_name="Pinwheel",
                xlights_id="eff_PINWHEEL",
                model_or_group=g.name,
                start_ms=start_ms,
                end_ms=end_ms,
                parameters=dict(_STAR_BURST_PARAMS),
                color_palette=list(_STAR_BURST_PALETTE),
            )
            # xLights renders the FIRST EffectLayer on top (bug-248); a
            # negative index sorts above the recipe's layers 0-2.
            p.layer = -1
            result.setdefault(g.name, []).append(p)

    return result
