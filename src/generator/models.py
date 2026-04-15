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
    layer: int = 0            # 0=primary effect layer, 1=accent overlay (Per Model Default)

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


@dataclass
class SequencePlan:
    """The complete blueprint for generating a sequence."""

    song_profile: SongProfile
    sections: list[SectionAssignment]
    layout_groups: list = field(default_factory=list)  # list[PowerGroup]
    models: list[str] = field(default_factory=list)
    frame_interval_ms: int = FRAME_INTERVAL_MS
    rotation_plan: Optional[Any] = None  # RotationPlan when variant rotation is active


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
    tier_selection: bool = True         # Energy/mood-driven single partition tier per section
    # Nominal fields (spec 047) — stored but not read in Phase 3. Phase 4
    # (spec 048 follow-up) will wire them into build_plan/theme_selector so
    # the Brief tab can drop its client-side MOOD_DEFAULTS ruleset.
    mood_intent: str = "auto"           # Brief mood axis: auto/party/emotional/dramatic/playful
    duration_feel: str = "auto"         # Brief duration axis: auto/snappy/balanced/flowing
    accent_strength: str = "auto"       # Brief accent axis: auto/subtle/strong

    _VALID_CURVES_MODES = frozenset({"all", "brightness", "speed", "color", "none"})
    _VALID_MOOD_INTENTS = frozenset({"auto", "party", "emotional", "dramatic", "playful"})
    _VALID_DURATION_FEELS = frozenset({"auto", "snappy", "balanced", "flowing"})
    _VALID_ACCENT_STRENGTHS = frozenset({"auto", "subtle", "strong"})

    def __post_init__(self) -> None:
        self.audio_path = Path(self.audio_path)
        self.layout_path = Path(self.layout_path)
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
