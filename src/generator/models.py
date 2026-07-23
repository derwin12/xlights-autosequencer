"""Data models for the sequence generator."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.themes.models import Theme


MOOD_TIERS = {
    "ethereal": (0, 33),
    "structural": (34, 66),
    "aggressive": (67, 100),
}

FRAME_INTERVAL_MS = 25

# "Basic units" fade durations (user request, 2026-07-23): every fade
# computation across the generator (per-effect scaling, section-boundary
# crossfades, end-of-song fadeout) snaps to one of these instead of an
# arbitrary continuous value, so fade lengths read as a small deliberate
# set rather than a different decimal on every placement.
FADE_UNIT_MS: tuple[int, ...] = (250, 500, 750, 1000, 1500, 2000)


def snap_fade_ms(fade_ms: int) -> int:
    """Snap a computed fade duration to the nearest FADE_UNIT_MS value.

    fade_ms <= 0 is returned unchanged — a deliberate "no fade" case
    (crisp cut). Values below the smallest unit (250ms) are also left
    unchanged rather than rounded up: a short accent effect's naturally
    tiny proportional fade (e.g. 40-50ms on a 500ms placement) is a
    deliberate near-instant cut, not an arbitrary value to snap onto the
    grid — inflating it to 250ms would eat a large fraction of the
    effect's own duration.
    """
    if fade_ms <= 0 or fade_ms < FADE_UNIT_MS[0]:
        return fade_ms
    return min(FADE_UNIT_MS, key=lambda unit: abs(unit - fade_ms))


def energy_to_mood(score: int) -> str:
    """Map a 0-100 energy score to a mood tier string."""
    if score <= 33:
        return "ethereal"
    elif score <= 66:
        return "structural"
    return "aggressive"


def frame_align(ms: int) -> int:
    """Round a millisecond value to the nearest frame boundary (25ms)."""
    return round(ms / FRAME_INTERVAL_MS) * FRAME_INTERVAL_MS


@dataclass
class SongProfile:
    """Song identity and characteristics for theme selection."""

    title: str
    artist: str
    genre: str
    occasion: str
    duration_ms: int
    estimated_bpm: float


@dataclass
class SectionEnergy:
    """A song section enriched with derived energy data."""

    label: str
    start_ms: int
    end_ms: int
    energy_score: int
    mood_tier: str
    impact_count: int


@dataclass
class EffectPlacement:
    """A single effect instance on the timeline."""

    effect_name: str
    xlights_id: str
    model_or_group: str
    start_ms: int
    end_ms: int
    parameters: dict[str, Any] = field(default_factory=dict)
    color_palette: list[str] = field(default_factory=list)
    blend_mode: str = "Normal"
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    value_curves: dict[str, Any] = field(default_factory=dict)
    # Values are either:
    #   list[tuple[float, float]]  — legacy (points only, assumes 0-100 range)
    #   tuple[list[tuple[float,float]], float, float] — (points, min, max)
    music_sparkles: int = 0  # 0=off, 1-100=sparkle frequency
    # xsq_writer serializes <EffectLayer> children per group in ascending
    # order of this field. For 06_PROP_Matrix on a real generated .xsq
    # (bug-248, 2026-07-15), xLights rendered the FIRST child on top and
    # each subsequent one further behind -- the opposite of this field's
    # prior comment ("1=accent overlay"), which had assumed higher numbers
    # sit in front and caused a visible regression (Pictures effect placed
    # "on top" at the highest layer number instead rendered at the bottom
    # of the stack). Only confirmed against that one group/theme so far --
    # if another song/prop family's layered overlay (e.g. the tier-1
    # background_accent_variant placement at layer=1 over a layer=0 base,
    # effect_placer.py's "Tier 1 background accent overlay" block) turns
    # out to render in the opposite order, verify against a real .xsq
    # before trusting either direction as universal.
    layer: int = 0

    def __post_init__(self) -> None:
        self.start_ms = frame_align(self.start_ms)
        self.end_ms = frame_align(self.end_ms)
        if self.end_ms <= self.start_ms:
            self.end_ms = self.start_ms + FRAME_INTERVAL_MS


@dataclass
class AccentPolicy:
    """Per-section gate outcomes for accent placement (spec 048, FR-001).

    Populated in `build_plan()` from `config.beat_accent_effects` combined with
    section-level gates (energy, role, duration, drum-event presence).  Accent
    placement helpers MUST trust these flags and not re-evaluate the underlying
    gates (FR-022).
    """

    drum_hits: bool = False  # spec 042A — per-hit Shockwave on small radial props
    impact: bool = False     # spec 042B — whole-house white Shockwave at section start
    # Number of extra energy-gated composite layers to stack on the tier-1
    # BASE whole-house group (mined from the corpus's "All" group idiom —
    # see _whole_house_layer_count). 0 = no composite this section.
    whole_house_layers: int = 0


@dataclass
class SectionAssignment:
    """One section's theme and effect mapping.

    As of spec 048 (pipeline decision-ordering refactor), every per-section
    creative decision is stored here as a populated field.  `build_plan()`
    writes these fields before calling `place_effects()`; the placer reads
    them as a read-only recipe.
    """

    section: SectionEnergy
    theme: Theme
    group_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    variation_seed: int = 0
    # Per-section decisions precomputed by build_plan() (spec 048).
    active_tiers: frozenset[int] = field(default_factory=frozenset)
    palette_target: Optional[dict[int, int]] = None
    duration_target: Optional["DurationTarget"] = None
    accent_policy: AccentPolicy = field(default_factory=AccentPolicy)
    working_set: Optional["WorkingSet"] = None
    section_index: int = 0
    # Corpus-recipe occurrence index per recipe family: how many earlier
    # sections in this song qualified for that family's recipe. Drives
    # rotation-pool selection (occurrence % pool length) so every pool slot
    # is reachable regardless of song structure — the previous
    # variation_seed arithmetic aliased with regular section strides and
    # silently skipped slots (Lightning never fired on 1999/Prince).
    # Populated by plan._populate_assignment_decisions; when absent
    # (e.g. assignments built directly in tests) the placer falls back to
    # the old seed-based index.
    corpus_occurrence: dict[str, int] = field(default_factory=dict)
    # Song-level anchor palette: 4 dominant colors shared across all sections so the
    # background wash tiers (1-2) feel like a consistent song identity rather than
    # resetting at every section boundary.  Empty list → fall back to theme.palette.
    anchor_palette: list[str] = field(default_factory=list)
    # Fraction of groups within each active tier to populate (0.0-1.0).
    # Low-energy sections use fewer groups so most props stay dark, matching pro
    # sequences where only key focal elements are lit in quiet passages.
    # Tier 8 (HERO) is always fully active regardless of this value.
    group_density: float = 1.0
    # True only for the last section of the song. Set by `_populate_assignment_decisions`.
    # Used by `place_effects` to apply an end-of-song fade-out when the final
    # section also has fade-worthy character (low/falling energy or outro role).
    is_final_section: bool = False


@dataclass
class SequencePlan:
    """The complete blueprint for generating a sequence."""

    song_profile: SongProfile
    sections: list[SectionAssignment]
    layout_groups: list = field(default_factory=list)  # list[PowerGroup]
    models: list[str] = field(default_factory=list)
    frame_interval_ms: int = FRAME_INTERVAL_MS
    rotation_plan: Optional[Any] = None  # RotationPlan when variant rotation is active
    # Song-scoped vocal placements (Faces on singing props, lyric Text on a
    # matrix), keyed by model name. Kept off the section assignments so a
    # 0-section analysis (bug-159) still renders them.
    vocal_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    # Song-scoped Video effect placement (imported video clip on a matrix),
    # keyed by model name. Same rationale as vocal_effects: not tied to a
    # section assignment, so it survives a 0-section analysis.
    video_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    # Song-scoped rare crash/transient accents (Shockwave on
    # 01_BASE_All_FADES), keyed by group name. Same rationale as
    # vocal_effects/video_effects.
    crash_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    # Song-scoped Pictures placements (catalog images cycling on matrix/tree
    # props), keyed by model name. Same rationale as vocal_effects/video_effects.
    picture_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    # Song-scoped Moving Head color-wash placements, keyed by moving-head
    # modelGroup name. Same rationale as vocal_effects/video_effects: these
    # groups aren't part of layout_groups at all (see grouper.generate_groups),
    # so there's no per-section tier for them to ride on.
    moving_head_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)


@dataclass
class XsqDocument:
    """Intermediate representation of .xsq XML before serialization."""

    media_file: str
    duration_sec: float
    frame_interval_ms: int = FRAME_INTERVAL_MS
    color_palettes: list[list[str]] = field(default_factory=list)
    effect_db: list[str] = field(default_factory=list)
    display_elements: list[str] = field(default_factory=list)
    element_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)


@dataclass
class DurationTarget:
    """Target duration range for a section, derived from BPM and energy."""

    min_ms: int    # Minimum allowed effect duration
    target_ms: int # Ideal effect duration for this section
    max_ms: int    # Maximum before subdividing further


@dataclass
class WorkingSetEntry:
    """A single effect in a theme's working set with its selection weight."""

    effect_name: str        # Base effect name (e.g., "Butterfly")
    variant_name: str       # Specific variant name (e.g., "Butterfly Medium Fast")
    weight: float           # Selection probability (0.0-1.0, all entries sum to 1.0)
    source: str             # "layer_0", "layer_1", "effect_pool", "alternate"


@dataclass
class WorkingSet:
    """Weighted list of effects derived from a theme's layer structure at generation time."""

    effects: list[WorkingSetEntry]      # Ordered by weight descending
    theme_name: str                     # Source theme name (for debugging)


@dataclass
class GenerationConfig:
    """User choices from the wizard or CLI flags."""

    audio_path: Path
    layout_path: Path
    output_dir: Optional[Path] = None
    video_path: Optional[Path] = None   # Song's imported video, for matrix Video effect
    genre: str = "pop"
    occasion: str = "general"
    force_reanalyze: bool = False
    target_sections: Optional[list[str]] = None
    theme_overrides: Optional[dict[int, str]] = None
    tiers: Optional[set[int]] = None
    story_path: Optional[Path] = None   # Optional path to song story JSON
    transition_mode: str = "subtle"     # "none", "subtle", or "dramatic"
    curves_mode: str = "none"           # Value curve generation: all, brightness, speed, color, none
    focused_vocabulary: bool = True     # Derive weighted working set per theme (Phase 1)
    embrace_repetition: bool = True     # Remove intra-section dedup, relax cross-section penalty (Phase 1)
    palette_restraint: bool = True      # Trim active palette colors to 2-4 based on energy/tier
    duration_scaling: bool = True       # Scale effect durations by BPM and section energy
    beat_accent_effects: bool = True    # Drum-hit Shockwave on small radials + whole-house impact accents
    whole_house_composite: bool = True  # Energy-gated multi-layer accent on tier-1 BASE_All (spec: whole-house-composite)
    tier_selection: bool = True         # Energy/mood-driven single partition tier per section
    crash_accents: bool = True          # Rare whole-house Shockwave on 01_BASE_All_FADES at extreme percussive transients
    picture_effects: bool = True        # Cycle catalog images (show_dir/Images) on matrix/tree props
    moving_head_effects: bool = True    # Gated reference-sequence moves + crash punch on DMX moving-head fixture groups
    # User-curated lyric keywords that trigger a Moving Head accent when
    # sung (moving_head.place_moving_head_keyword_accents) -- NOT mined
    # from the corpus (checked: neither vendor reference package with real
    # Moving Head content ties a placement to a single keyword), so this is
    # a deliberate per-song choice rather than a general idiom. Runs before
    # every other Moving Head pass so a specific lyric moment always claims
    # its accent. "shake"=Pan L-R-L, "spin"=Pattern Circle, "bounce"=Tilt
    # up-down-up; an unrecognized keyword is silently ignored.
    moving_head_keywords: tuple[str, ...] = ("shake", "spin", "bounce")
    # Pinwheel burst on Star-family groups at each rare drum fill
    # (hierarchy.riff_bursts, riff_bursts.detect_riff_bursts — snare-roll
    # detection on an isolated snare stem). Replaced an earlier bass+chord
    # detector + Moving Head placement (2026-07-18) that missed both of the
    # user's original confirmations and collided with the crash-accent
    # Moving Head warmup; the snare-based version found both original
    # moments natively and 5/5 spot-checked follow-ups confirmed, and
    # targeting Stars instead of Moving Head avoids the warmup collision
    # entirely — see CLAUDE.md -> "Riff/Fill Detector for Moving Head
    # Accent". Was False pending real-world listening; enabled 2026-07-22
    # after switching placement to rotate through individual star members
    # (bug-514) instead of flashing the whole family at once, and verifying
    # against a real generated sequence.
    riff_bursts: bool = True
    # Short "On" pulse on one individual floodlight at each rare kick-roll
    # flourish (hierarchy.kick_pulses, kick_pulses.detect_kick_pulses —
    # grouped from the already-classified kick_hits track). Rotates through
    # every floodlight (or other single-pixel prop with no buffer
    # resolution for a burst-style effect) the same way riff_bursts rotates
    # through star-family members (bug-514). Was False pending real-world
    # listening; enabled 2026-07-22 after verifying against real audio
    # (Chattahoochee) — found 0 marks on that song (no kick rolls in a
    # standard country kit, same "rare by design" behavior as
    # crash_accents), and synthetic-burst unit tests confirm the detector
    # fires correctly when the underlying kick-roll signal exists.
    floodlight_pulses: bool = True
    # Short "On" tick on one individual floodlight at every classified hihat
    # hit (hierarchy.hihat_hits), rotating through every floodlight the same
    # way floodlight_pulses/riff_bursts do. Unlike floodlight_pulses (a rare
    # kick-roll flourish), this wires the raw hihat track directly -- no
    # burst filtering -- since hihat_hits is already a validated per-
    # instrument classification, not an experimental detector. Enabled
    # 2026-07-22 after a listen-through — same rollout discipline as
    # riff_bursts/floodlight_pulses.
    floodlight_hihat_accents: bool = True
    # Nominal fields (spec 047) — stored but not read in Phase 3. Phase 4
    # (spec 048 follow-up) will wire them into build_plan/theme_selector so
    # the Brief tab can drop its client-side MOOD_DEFAULTS ruleset.
    mood_intent: str = "auto"           # Brief mood axis: auto/party/emotional/dramatic/playful
    duration_feel: str = "auto"         # Brief duration axis: auto/snappy/balanced/flowing
    accent_strength: str = "auto"       # Brief accent axis: auto/subtle/strong
    # Base seed for theme selection variation. Each section's ThemeAssignment
    # gets variation_seed = config.variation_seed + section_index, so changing
    # this value reproducibly shifts every section's alternate selection. The
    # microscope tool relies on this for deterministic runs (OpenSpec
    # ``visual-quality-microscope``).
    variation_seed: int = 0
    # Word-level vocal marks ({label, start_ms, end_ms, speaker}) from
    # WhisperX alignment. When present alongside face-capable props in the
    # layout, build_plan places Faces effects over the vocal regions
    # (singing faces).
    vocal_words: Optional[list[dict]] = None
    # Route words tagged speaker=1 (src.analyzer.vocal_diarization) to a
    # second face-capable prop and a second "Lyrics - Backup" timing track,
    # for duets/featured-artist songs -- e.g. Natalie Grant feat. Bart
    # Millard, where clustering held together as one coherent multi-
    # utterance voice distinct from the lead (validated by ear, 2026-07-21).
    # Diarization itself always runs at analysis time (cheap: collapses to
    # speaker=0 for everyone when no confident second voice is found); this
    # flag only gates whether the GENERATOR acts on a speaker=1 tag. Enabled
    # by default per explicit user request (2026-07-21) to try it on real
    # songs; the conservative accept-gate in vocal_diarization.py means a
    # solo song is unaffected (no confident second voice -> no-op).
    vocal_diarization: bool = True
    # Lyric words the user unmapped on the Pictures screen (per-song ignore).
    # Suppresses lyric-matched Pictures bursts for these words without
    # removing the image from the shared library. Case-insensitive.
    ignored_image_words: Optional[list[str]] = None
    # Caller-supplied title/artist (e.g. the review library's corrected
    # values) that win over read_song_metadata()'s raw ID3/filename-stem
    # result — written into the .xsq's <song>/<artist> Meta Data fields.
    title_override: Optional[str] = None
    artist_override: Optional[str] = None

    _VALID_CURVES_MODES = frozenset({"all", "brightness", "speed", "color", "none"})
    _VALID_MOOD_INTENTS = frozenset({"auto", "party", "emotional", "dramatic", "playful"})
    _VALID_DURATION_FEELS = frozenset({"auto", "snappy", "balanced", "flowing"})
    _VALID_ACCENT_STRENGTHS = frozenset({"auto", "subtle", "strong"})

    def __post_init__(self) -> None:
        self.audio_path = Path(self.audio_path)
        self.layout_path = Path(self.layout_path)
        if self.video_path is not None:
            self.video_path = Path(self.video_path)
        if self.output_dir is None:
            from src.paths import get_show_dir as _get_show_dir
            show_dir = _get_show_dir()
            self.output_dir = show_dir if show_dir is not None else self.audio_path.parent
        else:
            self.output_dir = Path(self.output_dir)
        if self.curves_mode not in self._VALID_CURVES_MODES:
            raise ValueError(
                f"Invalid curves_mode {self.curves_mode!r}. "
                f"Must be one of: {sorted(self._VALID_CURVES_MODES)}"
            )
        if self.mood_intent not in self._VALID_MOOD_INTENTS:
            raise ValueError(
                f"Invalid mood_intent {self.mood_intent!r}. "
                f"Must be one of: {sorted(self._VALID_MOOD_INTENTS)}"
            )
        if self.duration_feel not in self._VALID_DURATION_FEELS:
            raise ValueError(
                f"Invalid duration_feel {self.duration_feel!r}. "
                f"Must be one of: {sorted(self._VALID_DURATION_FEELS)}"
            )
        if self.accent_strength not in self._VALID_ACCENT_STRENGTHS:
            raise ValueError(
                f"Invalid accent_strength {self.accent_strength!r}. "
                f"Must be one of: {sorted(self._VALID_ACCENT_STRENGTHS)}"
            )
