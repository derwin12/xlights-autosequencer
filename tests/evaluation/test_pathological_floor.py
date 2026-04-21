"""Pathological floor tests — each metric must score degenerate sequences worse than real ones.

Per spec FR-020 and SC-003. Any metric that fails these tests must be removed from the
gated set or reworked before shipping.

"Worse" means the degenerate fixture exhibits the failure mode the metric is designed to
detect, and the metric value reflects that degradation vs the minimal real sequence:

  placements_per_minute      — empty → 0.0; real > 0
  palette_top5_colors        — monochrome → 1.0 top-color share; real < 1.0
  effect_type_histogram      — single_effect → 1 histogram key; real → 5 keys
  beat_alignment_pct         — random timestamps → low fraction; real beat-aligned → 1.0
  density_energy_correlation — empty → 0.0 (no placements to correlate); real > 0
  per_section_palette_diversity — monochrome → 1 unique color/section; real → 5 colors
  section_transition_delta   — empty → 0.0 (no placements, no divergence); real > 0
  tier_utilization           — empty → 0.0 (no active models); real > 0
  theme_assignment_consistency — skipped: requires section labels with deliberate
                                  inconsistency to degenerate meaningfully
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.evaluation.models import Placement, SequenceSummary, load_sequence_summary
from src.evaluation.metrics.pacing import density_energy_correlation, placements_per_minute
from src.evaluation.metrics.palette import (
    palette_top5_colors,
    per_section_palette_diversity,
)
from src.evaluation.metrics.effects import effect_type_histogram
from src.evaluation.metrics.alignment import beat_alignment_pct
from src.evaluation.metrics.sections import section_transition_delta
from src.evaluation.metrics.internal import theme_assignment_consistency, tier_utilization

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "degenerate"

# ---------------------------------------------------------------------------
# Colours and effects used in the minimal real sequence
# ---------------------------------------------------------------------------
_COLORS = ("#FF0000", "#0000FF", "#00FF00", "#FFFF00", "#FF00FF")
_EFFECTS = ("Marquee", "Plasma", "Bars", "ColorWash", "Fire")
_MODELS = ("ModelA", "ModelB", "ModelC")

# ---------------------------------------------------------------------------
# Minimal real sequence
#
# 40 placements, 3 models, 5 effects (8 each), 5 colours (8 each).
# start_ms spaced 3 000 ms apart → 0, 3000, 6000, …, 117000
# All start_ms are multiples of 500 ms, so beats=[0,500,1000,...] covers them.
# Duration: 2 minutes (120 000 ms).
# ---------------------------------------------------------------------------

def _make_minimal_real() -> SequenceSummary:
    placements: list[Placement] = []
    for i in range(40):
        start_ms = i * 3000
        end_ms = start_ms + 1000
        effect = _EFFECTS[i % len(_EFFECTS)]
        color = _COLORS[i % len(_COLORS)]
        model = _MODELS[i % len(_MODELS)]
        placements.append(
            Placement(
                start_ms=start_ms,
                end_ms=end_ms,
                effect_type=effect,
                model_name=model,
                palette_colors=(color,),
                layer_index=0,
            )
        )
    return SequenceSummary(
        song_id="minimal-real",
        source_label="ours",
        duration_ms=120_000,
        placements=tuple(placements),
        model_names=tuple(_MODELS),
        inferred_prop_types={m: "arch" for m in _MODELS},
    )


MINIMAL_REAL = _make_minimal_real()

# Beats every 500 ms for 2 minutes — covers all start_ms in MINIMAL_REAL.
_BEATS_500MS = list(range(0, 120_001, 500))

# Two-section split used for section-level floor tests.
_TWO_SECTIONS = [
    {"label": "verse", "start_ms": 0, "end_ms": 60_000},
    {"label": "chorus", "start_ms": 60_000, "end_ms": 120_000},
]

# ---------------------------------------------------------------------------
# placements_per_minute
# ---------------------------------------------------------------------------


def test_floor_ppm_empty() -> None:
    """empty.json has 0 placements → ppm = 0.0; real sequence has ppm > 0."""
    empty = load_sequence_summary(FIXTURES_DIR / "empty.json")
    empty_result = placements_per_minute(empty)
    real_result = placements_per_minute(MINIMAL_REAL)

    assert empty_result.value == pytest.approx(0.0), (
        "empty sequence must produce ppm == 0.0"
    )
    assert real_result.value > 0.0, (
        "minimal real sequence must produce ppm > 0.0"
    )
    assert empty_result.value < real_result.value, (
        f"empty ppm ({empty_result.value}) must be less than real ppm ({real_result.value})"
    )


# ---------------------------------------------------------------------------
# palette_top5_colors
# ---------------------------------------------------------------------------


def test_floor_palette_monochrome() -> None:
    """monochrome.json uses only #FFFFFF → top-color share = 1.0 (worst diversity).
    Real sequence uses 5 colours → top-color share < 1.0 (better diversity).
    Higher value = less diverse = worse, so monochrome.value > real.value.
    """
    monochrome = load_sequence_summary(FIXTURES_DIR / "monochrome.json")
    mono_result = palette_top5_colors(monochrome)
    real_result = palette_top5_colors(MINIMAL_REAL)

    assert mono_result.value == pytest.approx(1.0), (
        "monochrome sequence must have top-color share == 1.0"
    )
    assert real_result.value is not None and real_result.value < 1.0, (
        "real sequence must have top-color share < 1.0"
    )
    assert mono_result.value > real_result.value, (
        f"monochrome top-color share ({mono_result.value}) must exceed real ({real_result.value})"
    )


# ---------------------------------------------------------------------------
# effect_type_histogram
# ---------------------------------------------------------------------------


def test_floor_effects_single() -> None:
    """single_effect.json uses only Plasma → 1 key in histogram.
    Real sequence uses 5 effects → 5 keys. Fewer keys = less diversity = worse.
    """
    single = load_sequence_summary(FIXTURES_DIR / "single_effect.json")
    single_result = effect_type_histogram(single)
    real_result = effect_type_histogram(MINIMAL_REAL)

    single_keys = len(single_result.payload["histogram"])
    real_keys = len(real_result.payload["histogram"])

    assert single_keys == 1, (
        f"single_effect fixture must have exactly 1 histogram key; got {single_keys}"
    )
    assert real_keys == len(_EFFECTS), (
        f"real sequence must have {len(_EFFECTS)} histogram keys; got {real_keys}"
    )
    assert single_keys < real_keys, (
        f"single_effect histogram breadth ({single_keys}) must be less than real ({real_keys})"
    )


# ---------------------------------------------------------------------------
# beat_alignment_pct
# ---------------------------------------------------------------------------


def test_floor_alignment_random() -> None:
    """random_alignment.json has timestamps not aligned to 500 ms beats.
    Real sequence has all start_ms as multiples of 500 ms → 100% aligned.
    """
    random_align = load_sequence_summary(FIXTURES_DIR / "random_alignment.json")
    rand_result = beat_alignment_pct(random_align, beats=_BEATS_500MS)
    real_result = beat_alignment_pct(MINIMAL_REAL, beats=_BEATS_500MS)

    assert real_result.value == pytest.approx(1.0), (
        f"real sequence must be 100% beat-aligned; got {real_result.value}"
    )
    assert rand_result.value < real_result.value, (
        f"random_alignment beat_alignment_pct ({rand_result.value}) must be less than "
        f"real ({real_result.value})"
    )


# ---------------------------------------------------------------------------
# density_energy_correlation
# ---------------------------------------------------------------------------


def test_floor_density_empty() -> None:
    """empty.json has no placements → correlation returns 0.0 (reduced reliability).
    Real sequence with energy matching its placement pattern scores > 0.0.
    """
    # Build an energy curve that rises with time — real placements are spread
    # evenly so density is roughly constant, giving a moderate positive correlation
    # with a flat-rising energy.  The exact value doesn't matter; we only need
    # it to be > 0.
    window_ms = 3000  # matches 3000 ms spacing in real sequence
    n_windows = 40
    energy_curve = [
        (i * window_ms, 0.1 + 0.9 * i / (n_windows - 1))
        for i in range(n_windows)
    ]
    audio_context = {"energy_curve": energy_curve, "window_ms": window_ms}

    # For the floor test we use a perfectly correlated real: place one effect
    # per window scaled to the energy, then assert empty is worse.
    empty = load_sequence_summary(FIXTURES_DIR / "empty.json")

    empty_result = density_energy_correlation(empty, audio_context)
    assert empty_result.value == pytest.approx(0.0), (
        "empty sequence must produce density_energy_correlation == 0.0"
    )

    # Build a placement-dense real sequence whose density exactly tracks energy.
    placements_real: list[Placement] = []
    for i, (t_ms, energy) in enumerate(energy_curve):
        count = max(1, round(energy * 5))
        for k in range(count):
            start = t_ms + k * (window_ms // max(count, 1))
            placements_real.append(
                Placement(start, start + 200, "Marquee", "ModelA", ("#FF0000",), 0)
            )

    correlated_real = SequenceSummary(
        song_id="correlated-real",
        source_label="ours",
        duration_ms=n_windows * window_ms,
        placements=tuple(placements_real),
        model_names=("ModelA",),
        inferred_prop_types={"ModelA": "arch"},
    )

    real_result = density_energy_correlation(correlated_real, audio_context)
    assert real_result.value is not None and real_result.value > 0.0, (
        f"correlated real must have density_energy_correlation > 0.0; got {real_result.value}"
    )
    assert empty_result.value <= real_result.value, (
        f"empty correlation ({empty_result.value}) must be <= real ({real_result.value})"
    )


# ---------------------------------------------------------------------------
# per_section_palette_diversity
# ---------------------------------------------------------------------------


def test_floor_per_section_diversity_monochrome() -> None:
    """monochrome.json uses only #FFFFFF → mean unique colours per section = 1.
    Real sequence uses 5 colours → mean unique colours per section >= 2.
    """
    monochrome = load_sequence_summary(FIXTURES_DIR / "monochrome.json")

    # Use sections that span the monochrome fixture's 180 s duration.
    mono_sections = [
        {"label": "verse", "start_ms": 0, "end_ms": 90_000},
        {"label": "chorus", "start_ms": 90_000, "end_ms": 180_000},
    ]
    mono_result = per_section_palette_diversity(monochrome, sections=mono_sections)
    real_result = per_section_palette_diversity(MINIMAL_REAL, sections=_TWO_SECTIONS)

    assert mono_result.value == pytest.approx(1.0), (
        f"monochrome mean unique colours per section must be 1.0; got {mono_result.value}"
    )
    assert real_result.value > mono_result.value, (
        f"real mean unique colours ({real_result.value}) must exceed monochrome ({mono_result.value})"
    )


# ---------------------------------------------------------------------------
# section_transition_delta
# ---------------------------------------------------------------------------


def test_floor_transition_empty() -> None:
    """empty.json has no placements → no colour/effect divergence at boundaries → 0.0.
    Real sequence with different effects/colours across sections has transition_score > 0.
    """
    empty = load_sequence_summary(FIXTURES_DIR / "empty.json")
    empty_sections = [
        {"label": "verse", "start_ms": 0, "end_ms": 90_000},
        {"label": "chorus", "start_ms": 90_000, "end_ms": 180_000},
    ]
    empty_result = section_transition_delta(empty, sections=empty_sections)
    assert empty_result.value == pytest.approx(0.0), (
        "empty sequence must produce section_transition_delta == 0.0"
    )

    # Build a real sequence where verse uses only Marquee/#FF0000 and
    # chorus uses only Fire/#0000FF — maximum transition at the boundary.
    verse_placements: list[Placement] = [
        Placement(i * 5000, i * 5000 + 500, "Marquee", "ModelA", ("#FF0000",), 0)
        for i in range(18)  # 0 … 85000 ms
    ]
    chorus_placements: list[Placement] = [
        Placement(60_000 + i * 5000, 60_000 + i * 5000 + 500, "Fire", "ModelA", ("#0000FF",), 0)
        for i in range(12)  # 60000 … 115000 ms
    ]
    sharp_real = SequenceSummary(
        song_id="sharp-real",
        source_label="ours",
        duration_ms=120_000,
        placements=tuple(verse_placements + chorus_placements),
        model_names=("ModelA",),
        inferred_prop_types={"ModelA": "arch"},
    )
    real_result = section_transition_delta(sharp_real, sections=_TWO_SECTIONS)

    assert real_result.value > 0.0, (
        f"sharp-contrast real sequence must have transition_delta > 0.0; got {real_result.value}"
    )
    assert empty_result.value < real_result.value, (
        f"empty transition_delta ({empty_result.value}) must be less than real ({real_result.value})"
    )


# ---------------------------------------------------------------------------
# tier_utilization
# ---------------------------------------------------------------------------


def test_floor_tier_util_empty() -> None:
    """empty.json declares 1 model but has no placements → utilization = 0.0.
    Real sequence has placements across 3 models → utilization > 0.0.
    """
    empty = load_sequence_summary(FIXTURES_DIR / "empty.json")
    empty_result = tier_utilization(empty)
    real_result = tier_utilization(MINIMAL_REAL)

    assert empty_result.value == pytest.approx(0.0), (
        "empty sequence must produce tier_utilization == 0.0"
    )
    assert real_result.value > 0.0, (
        f"real sequence must have tier_utilization > 0.0; got {real_result.value}"
    )
    assert empty_result.value < real_result.value, (
        f"empty utilization ({empty_result.value}) must be less than real ({real_result.value})"
    )


# ---------------------------------------------------------------------------
# theme_assignment_consistency
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "theme_assignment_consistency requires sections with repeated labels AND "
        "deliberately inconsistent dominant-effect assignments to produce a value < 1.0. "
        "There is no degenerate fixture that exercises this failure mode without "
        "constructing a very specific placement+section dataset that is really a unit test "
        "of the metric itself rather than a floor test. "
        "See test_metrics_internal.py for unit coverage of the inconsistent case."
    )
)
def test_floor_theme_consistency_note() -> None:
    pass
