"""Tests for suitability metrics — variety + parallel pairing-fit signals.

Covers tasks.md §3.3 of the visual-quality-microscope OpenSpec change.
Tests build ``Placement`` / ``SequenceSummary`` instances directly; no XSQ
parsing is involved.
"""
from __future__ import annotations

import math

from src.evaluation.models import Placement, SequenceSummary
from src.evaluation.metrics.suitability import (
    bad_pairing_pct_catalog,
    bad_pairing_pct_handlist,
    distinct_effect_count,
    effect_repeat_rate,
    pairing_disagreement_pct,
    per_prop_type_diversity,
)


def _make_summary(
    placements: list[Placement],
    inferred_prop_types: dict[str, str],
    duration_ms: int = 60_000,
) -> SequenceSummary:
    model_names = tuple(sorted({p.model_name for p in placements}))
    return SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=duration_ms,
        placements=tuple(placements),
        model_names=model_names,
        inferred_prop_types=inferred_prop_types,
    )


def _placement(
    start_ms: int,
    end_ms: int,
    effect_type: str,
    model_name: str,
) -> Placement:
    return Placement(
        start_ms=start_ms,
        end_ms=end_ms,
        effect_type=effect_type,
        model_name=model_name,
        palette_colors=(),
        layer_index=0,
    )


# ---------------------------------------------------------------------------
# distinct_effect_count
# ---------------------------------------------------------------------------

def test_distinct_effect_count_empty_placements():
    summary = _make_summary([], {})
    result = distinct_effect_count(summary)
    assert result.value == 0.0


def test_distinct_effect_count_three_same_effect():
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(1000, 2000, "Plasma", "Arch02"),
        _placement(2000, 3000, "Plasma", "Tree01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch", "Arch02": "arch", "Tree01": "tree"})
    result = distinct_effect_count(summary)
    assert result.value == 1.0


def test_distinct_effect_count_three_different_effects():
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(1000, 2000, "Pinwheel", "Arch01"),
        _placement(2000, 3000, "Bars", "Arch01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch"})
    result = distinct_effect_count(summary)
    assert result.value == 3.0


def test_distinct_effect_count_excludes_unknown():
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(1000, 2000, "Unknown", "Arch01"),
        _placement(2000, 3000, "Unknown", "Arch01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch"})
    result = distinct_effect_count(summary)
    assert result.value == 1.0


# ---------------------------------------------------------------------------
# effect_repeat_rate
# ---------------------------------------------------------------------------

def test_effect_repeat_rate_no_repeats():
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(1000, 2000, "Pinwheel", "Arch01"),
        _placement(2000, 3000, "Bars", "Arch01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch"})
    result = effect_repeat_rate(summary)
    assert result.value == 0.0


def test_effect_repeat_rate_repeat_within_window():
    # Two Plasma placements on Arch01 separated by 29s → counted as repeat.
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(29_000, 30_000, "Plasma", "Arch01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch"})
    result = effect_repeat_rate(summary)
    # 1 repeat out of 2 placements = 0.5
    assert math.isclose(result.value, 0.5, abs_tol=1e-9)


def test_effect_repeat_rate_outside_window():
    # 31s apart → not counted.
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(31_000, 32_000, "Plasma", "Arch01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch"})
    result = effect_repeat_rate(summary)
    assert result.value == 0.0


def test_effect_repeat_rate_different_model_not_counted():
    # Same effect on different models is NOT a repeat.
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(5_000, 6_000, "Plasma", "Arch02"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch", "Arch02": "arch"})
    result = effect_repeat_rate(summary)
    assert result.value == 0.0


# ---------------------------------------------------------------------------
# per_prop_type_diversity
# ---------------------------------------------------------------------------

def test_per_prop_type_diversity_two_types_three_effects_each():
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(1000, 2000, "Pinwheel", "Arch01"),
        _placement(2000, 3000, "Bars", "Arch01"),
        _placement(3000, 4000, "Plasma", "Tree01"),
        _placement(4000, 5000, "Pinwheel", "Tree01"),
        _placement(5000, 6000, "Fire", "Tree01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch", "Tree01": "tree"})
    result = per_prop_type_diversity(summary)
    assert result.payload["min_diversity"] == 3
    assert result.payload["by_type"] == {"arch": 3, "tree": 3}
    assert result.value == 3.0


def test_per_prop_type_diversity_one_type_with_one_effect():
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(1000, 2000, "Pinwheel", "Arch01"),
        _placement(2000, 3000, "Bars", "Arch01"),
        _placement(3000, 4000, "Plasma", "Tree01"),  # tree has only 1 effect
    ]
    summary = _make_summary(placements, {"Arch01": "arch", "Tree01": "tree"})
    result = per_prop_type_diversity(summary)
    assert result.payload["min_diversity"] == 1
    assert result.payload["by_type"]["tree"] == 1
    assert result.value == 1.0


def test_per_prop_type_diversity_skips_models_without_prop_type():
    # Mystery01 is not in inferred_prop_types → skipped.
    placements = [
        _placement(0, 1000, "Plasma", "Arch01"),
        _placement(1000, 2000, "Pinwheel", "Arch01"),
        _placement(2000, 3000, "Bars", "Mystery01"),
    ]
    summary = _make_summary(placements, {"Arch01": "arch"})
    result = per_prop_type_diversity(summary)
    assert result.payload["by_type"] == {"arch": 2}
    assert result.payload["min_diversity"] == 2


# ---------------------------------------------------------------------------
# bad_pairing_pct_handlist
# ---------------------------------------------------------------------------

def test_bad_pairing_pct_handlist_plasma_on_outline_flagged():
    placements = [_placement(0, 1000, "Plasma", "OutlineRoof")]
    summary = _make_summary(placements, {"OutlineRoof": "outline"})
    result = bad_pairing_pct_handlist(summary)
    assert result.value == 1.0


def test_bad_pairing_pct_handlist_plasma_on_tree_not_flagged():
    placements = [_placement(0, 1000, "Plasma", "Tree01")]
    summary = _make_summary(placements, {"Tree01": "tree"})
    result = bad_pairing_pct_handlist(summary)
    assert result.value == 0.0


def test_bad_pairing_pct_handlist_unknown_model_skipped():
    # Mystery01 has no inferred prop type → skipped; only the known Tree01
    # placement is evaluable, and it is not flagged.
    placements = [
        _placement(0, 1000, "Plasma", "Mystery01"),
        _placement(1000, 2000, "Plasma", "Tree01"),
    ]
    summary = _make_summary(placements, {"Tree01": "tree"})
    result = bad_pairing_pct_handlist(summary)
    assert result.value == 0.0


def test_bad_pairing_pct_handlist_no_known_props_reliability():
    placements = [_placement(0, 1000, "Plasma", "Mystery01")]
    summary = _make_summary(placements, {})
    result = bad_pairing_pct_handlist(summary)
    assert result.value == 0.0
    assert result.reliability == "no_known_props"


# ---------------------------------------------------------------------------
# bad_pairing_pct_catalog
# ---------------------------------------------------------------------------

def test_bad_pairing_pct_catalog_pinwheel_on_arch_flagged():
    # Catalog records Pinwheel on arch as "not_recommended".
    placements = [_placement(0, 1000, "Pinwheel", "ArchLeft")]
    summary = _make_summary(placements, {"ArchLeft": "arch"})
    result = bad_pairing_pct_catalog(summary)
    assert result.value == 1.0


def test_bad_pairing_pct_catalog_plasma_on_outline_not_flagged():
    # Catalog records Plasma on outline as "possible" — not flagged.
    placements = [_placement(0, 1000, "Plasma", "OutlineRoof")]
    summary = _make_summary(placements, {"OutlineRoof": "outline"})
    result = bad_pairing_pct_catalog(summary)
    assert result.value == 0.0


def test_bad_pairing_pct_catalog_unknown_effect_skipped():
    # NonexistentEffect has no entry in the catalog → skipped.
    placements = [_placement(0, 1000, "NonexistentEffect", "ArchLeft")]
    summary = _make_summary(placements, {"ArchLeft": "arch"})
    result = bad_pairing_pct_catalog(summary)
    assert result.value == 0.0
    assert result.reliability == "no_known_props"


# ---------------------------------------------------------------------------
# pairing_disagreement_pct
# ---------------------------------------------------------------------------

def test_pairing_disagreement_pct_disagreement_case():
    # Plasma on outline: handlist=BAD, catalog=possible (not flagged).
    # Exactly one signal flags → disagreement.
    placements = [_placement(0, 1000, "Plasma", "OutlineRoof")]
    summary = _make_summary(placements, {"OutlineRoof": "outline"})
    result = pairing_disagreement_pct(summary)
    assert result.value == 1.0


def test_pairing_disagreement_pct_agreement_does_not_contribute():
    # Pinwheel on arch: handlist=BAD AND catalog=not_recommended.
    # Both flag → no disagreement. The placement is evaluable, so the
    # denominator is 1, and the numerator (disagreements) is 0.
    placements = [_placement(0, 1000, "Pinwheel", "ArchLeft")]
    summary = _make_summary(placements, {"ArchLeft": "arch"})
    result = pairing_disagreement_pct(summary)
    assert result.value == 0.0
    # Sanity: the placement WAS evaluable (both signals had a verdict).
    # If it weren't, value would still be 0.0 but reliability would say so.
    assert result.reliability == "ok"


def test_pairing_disagreement_pct_mixed_corpus():
    # 1 disagreement (Plasma+outline) + 1 agreement (Pinwheel+arch) → 0.5.
    placements = [
        _placement(0, 1000, "Plasma", "OutlineRoof"),
        _placement(1000, 2000, "Pinwheel", "ArchLeft"),
    ]
    summary = _make_summary(
        placements,
        {"OutlineRoof": "outline", "ArchLeft": "arch"},
    )
    result = pairing_disagreement_pct(summary)
    assert math.isclose(result.value, 0.5, abs_tol=1e-9)
