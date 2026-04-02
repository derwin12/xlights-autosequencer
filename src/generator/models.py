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
    value_curves: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.start_ms = frame_align(self.start_ms)
        self.end_ms = frame_align(self.end_ms)
        if self.end_ms <= self.start_ms:
            self.end_ms = self.start_ms + FRAME_INTERVAL_MS


@dataclass
class SectionAssignment:
    """One section's theme and effect mapping."""

    section: SectionEnergy
    theme: Theme
    group_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    variation_seed: int = 0


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
    curves_mode: str = "all"            # Value curve generation: all, brightness, speed, color, none

    def __post_init__(self) -> None:
        self.audio_path = Path(self.audio_path)
        self.layout_path = Path(self.layout_path)
        if self.output_dir is None:
            self.output_dir = self.audio_path.parent
        else:
            self.output_dir = Path(self.output_dir)
