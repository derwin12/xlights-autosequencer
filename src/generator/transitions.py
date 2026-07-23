"""Transition infrastructure — crossfades at section boundaries and end-of-song fade-out."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.generator.models import FRAME_INTERVAL_MS, snap_fade_ms

if TYPE_CHECKING:
    from src.generator.models import EffectPlacement, SectionAssignment

logger = logging.getLogger(__name__)

VALID_MODES = ("none", "subtle", "dramatic")
VALID_FADEOUT_STRATEGIES = ("progressive", "uniform", "none")

# A fade shorter than 2 frames (at 40fps / 25ms per frame) is imperceptible
# and not worth rendering as anything but a crisp cut (user request,
# 2026-07-23). Only applied where clamping to half the section length could
# otherwise squeeze a crossfade down to a sub-frame sliver.
_MIN_CROSSFADE_MS = FRAME_INTERVAL_MS * 2

# Tier number → fade start offset as fraction of the fade region (progressive mode)
_PROGRESSIVE_TIER_OFFSETS: dict[int, float] = {
    8: 0.0,   # Hero: starts fading immediately
    7: 0.2,   # Compound
    6: 0.4,   # Prop
    5: 0.6,   # Fidelity
    4: 0.8,   # Beat
    3: 0.8,   # Type
    2: 0.8,   # Geo
    1: 0.8,   # Base: fades last
}

# Minimum outro duration for progressive staggering
_PROGRESSIVE_MIN_DURATION_MS = 8000


@dataclass
class TransitionConfig:
    """Settings controlling crossfade and fade-out behavior for a generation run."""

    mode: str = "subtle"
    snap_window_ms: int | None = None
    fadeout_strategy: str = "progressive"
    abrupt_end_fade_ms: int = 1000

    def __post_init__(self) -> None:
        if self.mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {self.mode!r}")
        if self.fadeout_strategy not in VALID_FADEOUT_STRATEGIES:
            raise ValueError(
                f"fadeout_strategy must be one of {VALID_FADEOUT_STRATEGIES}, "
                f"got {self.fadeout_strategy!r}"
            )


@dataclass
class CrossfadeRegion:
    """A computed region spanning a section boundary where fades are applied."""

    boundary_ms: int
    section_a_index: int
    section_b_index: int
    fade_duration_ms: int
    skip_groups: set[str] = field(default_factory=set)


@dataclass
class FadeOutPlan:
    """The brightness ramp for the final section, per tier."""

    start_ms: int
    end_ms: int
    is_outro: bool
    tier_offsets: dict[int, float] = field(default_factory=dict)


def compute_crossfade_duration(bpm: float, mode: str, section_duration_ms: int) -> int:
    """Return crossfade duration in milliseconds for the given tempo and mode.

    - none: 0ms
    - subtle: one beat duration (60000 / bpm), snapped to the nearest
      FADE_UNIT_MS "basic unit", clamped to half section length
    - dramatic: one bar duration (4 beats), same snapping/clamping
    - Clamping to a very short section can otherwise squeeze the result
      below 2 frames (imperceptible); when there's room for at least a
      2-frame fade, the floor wins over an even smaller clamp. When the
      section is too short even for that, no fade is better than a
      sub-frame sliver.
    """
    if mode == "none":
        return 0

    beat_ms = 60000.0 / bpm
    if mode == "subtle":
        raw = beat_ms
    elif mode == "dramatic":
        raw = beat_ms * 4  # one bar in 4/4 time
    else:
        return 0

    max_duration = section_duration_ms // 2
    fade = min(snap_fade_ms(round(raw)), max_duration)
    if 0 < fade < _MIN_CROSSFADE_MS:
        fade = _MIN_CROSSFADE_MS if max_duration >= _MIN_CROSSFADE_MS else 0
    return fade


def detect_same_effect_continuation(
    placement_a: EffectPlacement,
    placement_b: EffectPlacement,
) -> bool:
    """Return True if two placements represent the same effect continuing across a boundary.

    Checks effect_name, xlights_id, and parameters within 10% tolerance
    (to account for variation_seed tweaks).
    """
    if placement_a.effect_name != placement_b.effect_name:
        return False
    if placement_a.xlights_id != placement_b.xlights_id:
        return False

    params_a = placement_a.parameters
    params_b = placement_b.parameters
    if set(params_a.keys()) != set(params_b.keys()):
        return False

    for key in params_a:
        val_a = params_a[key]
        val_b = params_b[key]
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            if val_a == 0 and val_b == 0:
                continue
            ref = max(abs(val_a), abs(val_b))
            if ref == 0:
                continue
            if abs(val_a - val_b) / ref > 0.10:
                return False
        elif val_a != val_b:
            return False

    return True


def _resolve_mode(
    config: TransitionConfig,
    theme_transition_mode: str | None,
) -> str:
    """Resolve effective mode: theme override takes precedence over global config."""
    if theme_transition_mode is not None:
        return theme_transition_mode
    return config.mode


def apply_crossfades(
    assignments: list[SectionAssignment],
    config: TransitionConfig,
    bpm: float,
) -> None:
    """Apply fade_in_ms/fade_out_ms at section boundaries (in-place).

    For each adjacent section pair, finds the last placement in section A and first
    in section B for each group. Sets fade values unless same-effect continuation
    detected, or mode is "none".
    """
    if len(assignments) < 2:
        return

    for i in range(len(assignments) - 1):
        a = assignments[i]
        b = assignments[i + 1]

        # Resolve mode — theme on the outgoing section takes precedence
        theme_mode = getattr(a.theme, "transition_mode", None)
        mode = _resolve_mode(config, theme_mode)

        if mode == "none":
            continue

        # Compute fade duration using shorter of the two sections
        dur_a = a.section.end_ms - a.section.start_ms
        dur_b = b.section.end_ms - b.section.start_ms
        shorter = min(dur_a, dur_b)
        fade_ms = compute_crossfade_duration(bpm, mode, shorter)

        if fade_ms <= 0:
            continue

        # All groups present in both sections
        groups_a = set(a.group_effects.keys())
        groups_b = set(b.group_effects.keys())
        shared = groups_a | groups_b

        for group in shared:
            placements_a = a.group_effects.get(group, [])
            placements_b = b.group_effects.get(group, [])

            last_a = placements_a[-1] if placements_a else None
            first_b = placements_b[0] if placements_b else None

            if last_a is None or first_b is None:
                continue

            if detect_same_effect_continuation(last_a, first_b):
                continue

            last_a.fade_out_ms = fade_ms
            first_b.fade_in_ms = fade_ms


def build_fadeout_plan(
    assignments: list[SectionAssignment],
    fadeout_strategy: str,
    abrupt_end_fade_ms: int = 1000,
) -> FadeOutPlan | None:
    """Build a FadeOutPlan for the final section.

    Returns None if there are no assignments.
    """
    if not assignments:
        return None

    final = assignments[-1]
    section = final.section
    label = (section.label or "").lower()
    is_outro = label == "outro"

    if is_outro:
        start_ms = section.start_ms
        end_ms = section.end_ms
    else:
        # Abrupt ending: use last N ms
        end_ms = section.end_ms
        start_ms = max(section.start_ms, end_ms - abrupt_end_fade_ms)

    duration_ms = end_ms - start_ms
    use_progressive = (
        fadeout_strategy == "progressive"
        and duration_ms >= _PROGRESSIVE_MIN_DURATION_MS
    )

    if use_progressive:
        tier_offsets = dict(_PROGRESSIVE_TIER_OFFSETS)
    else:
        # Uniform: all tiers start at 0.0
        tier_offsets = {tier: 0.0 for tier in _PROGRESSIVE_TIER_OFFSETS}

    return FadeOutPlan(
        start_ms=start_ms,
        end_ms=end_ms,
        is_outro=is_outro,
        tier_offsets=tier_offsets,
    )


def _tier_from_group_name(group_name: str) -> int:
    """Infer tier number from group name prefix (e.g. '01_BASE' → 1, '08_HERO' → 8)."""
    prefix = group_name.split("_")[0]
    try:
        return int(prefix)
    except (ValueError, IndexError):
        return 1  # default to base tier if unparseable


def apply_fadeout(
    assignments: list[SectionAssignment],
    fadeout_plan: FadeOutPlan,
) -> None:
    """Apply fade_out_ms to the final section's placements (in-place).

    Each group's last placement gets a fade_out_ms based on its tier and the
    tier_offsets in the FadeOutPlan.
    """
    if not assignments:
        return

    final = assignments[-1]
    total_duration_ms = fadeout_plan.end_ms - fadeout_plan.start_ms

    for group_name, placements in final.group_effects.items():
        if not placements:
            continue

        tier = _tier_from_group_name(group_name)
        offset = fadeout_plan.tier_offsets.get(tier, 0.0)

        # Fade duration = (1.0 - offset) × total fade region. Deliberately
        # NOT snapped to FADE_UNIT_MS (unlike compute_scaled_fades/
        # compute_crossfade_duration) -- this is a multi-second, tier-
        # staggered end-of-song fadeout meant to scale with the fade
        # region's real duration (often 10-30s+), not a short per-effect
        # or crossfade transition; capping it to the 2s basic-unit ceiling
        # would break the whole progressive-fadeout feature.
        fade_ms = round((1.0 - offset) * total_duration_ms)
        if fade_ms <= 0:
            continue

        placements[-1].fade_out_ms = max(placements[-1].fade_out_ms, fade_ms)


def apply_transitions(
    assignments: list[SectionAssignment],
    config: TransitionConfig,
    bpm: float,
) -> None:
    """Apply all transition post-processing: crossfades + end-of-song fade-out.

    This is the single entry point called from build_plan() after all sections
    have their group_effects populated.
    """
    # Step 1: crossfades at section boundaries
    apply_crossfades(assignments, config, bpm)

    # Step 2: end-of-song fade-out
    if config.fadeout_strategy != "none":
        plan = build_fadeout_plan(
            assignments,
            fadeout_strategy=config.fadeout_strategy,
            abrupt_end_fade_ms=config.abrupt_end_fade_ms,
        )
        if plan is not None:
            apply_fadeout(assignments, plan)
