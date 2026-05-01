"""Suitability metrics — variety + parallel pairing-fit signals.

This module implements six metrics:

Variety (3):
- ``distinct_effect_count``       — unique non-"Unknown" effect types in use.
- ``effect_repeat_rate``          — fraction of placements that repeat the same
                                    ``(model, effect)`` pair within a window.
- ``per_prop_type_diversity``     — distinct effect count per inferred prop
                                    type; scalar = the minimum across types.

Pairing fit (3 — computed in parallel; no winner is picked):
- ``bad_pairing_pct_handlist``    — fraction flagged by HANDLIST_BAD_PAIRINGS.
- ``bad_pairing_pct_catalog``     — fraction flagged by
                                    ``builtin_effects.json:prop_suitability``
                                    value ``"not_recommended"``.
- ``pairing_disagreement_pct``    — fraction where exactly one of the two
                                    signals flags the placement.

The two pairing signals encode different opinions about which effect/prop
combinations look bad. Neither has been validated against rendered output, so
neither is treated as ground truth. ``pairing_disagreement_pct`` surfaces the
gap as its own headline number; that is the finding, not noise.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    register,
)


# INITIAL DRAFT — not validated against rendered output. First-principles
# guesses about pairings that "obviously look wrong" on each prop type.
# Disagrees with src/effects/builtin_effects.json:prop_suitability on
# most entries; both signals are computed in parallel and
# `pairing_disagreement_pct` surfaces the gap. Revise this dict (or the
# catalog) only after the first corpus measurement says the
# disagreement is concentrated somewhere actionable.
HANDLIST_BAD_PAIRINGS: dict[str, set[str]] = {
    "Plasma":        {"outline", "arch"},
    "Pinwheel":      {"outline", "arch"},
    "Single Strand": {"matrix"},
    "Bars":          {"radial", "matrix"},
    "Strobe":        {"matrix"},
    "Curtain":       {"matrix"},
    "Fire":          {"arch", "outline"},
    "Butterfly":     {"outline", "arch"},
}


# ``audio_context`` plumbing in src/evaluation/compare.py is per-metric
# hardcoded today, so a new metric registered with the standard
# ``compute(summary)`` signature does NOT receive ``audio_context``. The
# repeat window is therefore parameterised at module level until the
# dispatcher is generalised.
_DEFAULT_REPEAT_WINDOW_MS: int = 30_000


# ---------------------------------------------------------------------------
# Catalog load (once at import time; missing file is non-fatal)
# ---------------------------------------------------------------------------

_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "effects" / "builtin_effects.json"
)


def _load_catalog() -> dict | None:
    """Read ``builtin_effects.json`` once. Return None on any failure."""
    try:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        effects = data.get("effects", {})
        if not isinstance(effects, dict):
            return None
        return effects
    except (OSError, json.JSONDecodeError):
        return None


_CATALOG: dict | None = _load_catalog()


# ---------------------------------------------------------------------------
# Pairing helpers
# ---------------------------------------------------------------------------

def _handlist_flags(effect_type: str, prop_type: str) -> bool:
    """True if HANDLIST flags this (effect, prop) pair as bad."""
    return prop_type in HANDLIST_BAD_PAIRINGS.get(effect_type, set())


def _catalog_flags(effect_type: str, prop_type: str) -> bool | None:
    """True/False if the catalog has a verdict; None if unknown.

    A verdict exists only when both the effect AND prop entry are present.
    A verdict of True means the catalog says ``"not_recommended"``.
    """
    if _CATALOG is None:
        return None
    effect_entry = _CATALOG.get(effect_type)
    if not isinstance(effect_entry, dict):
        return None
    suit = effect_entry.get("prop_suitability")
    if not isinstance(suit, dict):
        return None
    if prop_type not in suit:
        return None
    return suit[prop_type] == "not_recommended"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def distinct_effect_count(summary: SequenceSummary) -> MetricValue:
    """Number of unique non-``Unknown`` effect types used."""
    distinct = {
        p.effect_type
        for p in summary.placements
        if p.effect_type != "Unknown"
    }
    return MetricValue(
        name="distinct_effect_count",
        kind=MetricKind.SCALAR.value,
        value=float(len(distinct)),
        payload=None,
        reliability="ok",
    )


def effect_repeat_rate(summary: SequenceSummary) -> MetricValue:
    """Fraction of placements that repeat the same (model, effect) pair within
    ``_DEFAULT_REPEAT_WINDOW_MS`` of a previous matching placement on the same
    model."""
    placements = summary.placements
    if not placements:
        return MetricValue(
            name="effect_repeat_rate",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_placements",
        )

    last_seen: dict[tuple[str, str], int] = {}
    repeats = 0
    # Iterate in start_ms order so "previous" is well-defined.
    ordered = sorted(placements, key=lambda p: p.start_ms)
    for p in ordered:
        key = (p.model_name, p.effect_type)
        prev = last_seen.get(key)
        if prev is not None and (p.start_ms - prev) < _DEFAULT_REPEAT_WINDOW_MS:
            repeats += 1
        last_seen[key] = p.start_ms

    return MetricValue(
        name="effect_repeat_rate",
        kind=MetricKind.SCALAR.value,
        value=repeats / len(placements),
        payload=None,
        reliability="ok",
    )


def per_prop_type_diversity(summary: SequenceSummary) -> MetricValue:
    """Distinct effect count per inferred prop type; scalar = min across types.

    Returns a structured payload ``{by_type, min_diversity}``. Placements whose
    model is missing from ``inferred_prop_types`` or whose prop type is
    ``"Unknown"`` are skipped. If no placements have a known prop type, the
    metric returns 0.0 with ``reliability="no_known_props"``.
    """
    by_type: dict[str, set[str]] = {}
    for p in summary.placements:
        prop_type = summary.inferred_prop_types.get(p.model_name)
        if not prop_type or prop_type == "Unknown":
            continue
        by_type.setdefault(prop_type, set()).add(p.effect_type)

    if not by_type:
        return MetricValue(
            name="per_prop_type_diversity",
            kind=MetricKind.STRUCTURED.value,
            value=0.0,
            payload={"by_type": {}, "min_diversity": 0},
            reliability="no_known_props",
        )

    counts = {t: len(effects) for t, effects in by_type.items()}
    min_diversity = min(counts.values())
    return MetricValue(
        name="per_prop_type_diversity",
        kind=MetricKind.STRUCTURED.value,
        value=float(min_diversity),
        payload={"by_type": counts, "min_diversity": min_diversity},
        reliability="ok",
    )


def bad_pairing_pct_handlist(summary: SequenceSummary) -> MetricValue:
    """Fraction of evaluable placements flagged by HANDLIST_BAD_PAIRINGS.

    Evaluable = the placement's model has a known, non-Unknown inferred prop
    type. Effects absent from HANDLIST simply never flag (treated as not bad).
    """
    evaluable = 0
    flagged = 0
    for p in summary.placements:
        prop_type = summary.inferred_prop_types.get(p.model_name)
        if not prop_type or prop_type == "Unknown":
            continue
        evaluable += 1
        if _handlist_flags(p.effect_type, prop_type):
            flagged += 1

    if evaluable == 0:
        return MetricValue(
            name="bad_pairing_pct_handlist",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_known_props",
        )
    return MetricValue(
        name="bad_pairing_pct_handlist",
        kind=MetricKind.SCALAR.value,
        value=flagged / evaluable,
        payload=None,
        reliability="ok",
    )


def bad_pairing_pct_catalog(summary: SequenceSummary) -> MetricValue:
    """Fraction of evaluable placements where the catalog records the
    ``(effect, prop)`` pair as ``"not_recommended"``.

    Evaluable = the catalog has a verdict for that pair (both effect and prop
    are present in ``prop_suitability``).
    """
    if _CATALOG is None:
        return MetricValue(
            name="bad_pairing_pct_catalog",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="catalog_missing",
        )

    evaluable = 0
    flagged = 0
    for p in summary.placements:
        prop_type = summary.inferred_prop_types.get(p.model_name)
        if not prop_type or prop_type == "Unknown":
            continue
        verdict = _catalog_flags(p.effect_type, prop_type)
        if verdict is None:
            continue
        evaluable += 1
        if verdict:
            flagged += 1

    if evaluable == 0:
        return MetricValue(
            name="bad_pairing_pct_catalog",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_known_props",
        )
    return MetricValue(
        name="bad_pairing_pct_catalog",
        kind=MetricKind.SCALAR.value,
        value=flagged / evaluable,
        payload=None,
        reliability="ok",
    )


def pairing_disagreement_pct(summary: SequenceSummary) -> MetricValue:
    """Fraction of doubly-evaluable placements where the two pairing signals
    disagree (exactly one of them flags the placement).

    Doubly-evaluable = the placement has a known prop type AND the catalog has
    a verdict for the ``(effect, prop)`` pair. A placement is also doubly
    evaluable if the effect is in ``HANDLIST_BAD_PAIRINGS`` but the catalog
    has a non-flagging verdict (or vice versa).
    """
    if _CATALOG is None:
        return MetricValue(
            name="pairing_disagreement_pct",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="catalog_missing",
        )

    evaluable = 0
    disagreements = 0
    for p in summary.placements:
        prop_type = summary.inferred_prop_types.get(p.model_name)
        if not prop_type or prop_type == "Unknown":
            continue
        catalog_verdict = _catalog_flags(p.effect_type, prop_type)
        if catalog_verdict is None:
            continue
        handlist_verdict = _handlist_flags(p.effect_type, prop_type)
        evaluable += 1
        if handlist_verdict != catalog_verdict:
            disagreements += 1

    if evaluable == 0:
        return MetricValue(
            name="pairing_disagreement_pct",
            kind=MetricKind.SCALAR.value,
            value=0.0,
            payload=None,
            reliability="no_known_props",
        )
    return MetricValue(
        name="pairing_disagreement_pct",
        kind=MetricKind.SCALAR.value,
        value=disagreements / evaluable,
        payload=None,
        reliability="ok",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register(MetricDefinition(
    name="distinct_effect_count",
    kind=MetricKind.SCALAR,
    gated=True,
    tolerance=None,
    compute=distinct_effect_count,
    pro_comparable=False,
    higher_is_better=None,
))

register(MetricDefinition(
    name="effect_repeat_rate",
    kind=MetricKind.SCALAR,
    gated=True,
    tolerance=None,
    compute=effect_repeat_rate,
    pro_comparable=False,
    # Direction is user preference, not validated against rendered output.
    higher_is_better=False,
))

register(MetricDefinition(
    name="per_prop_type_diversity",
    kind=MetricKind.STRUCTURED,
    gated=True,
    tolerance=None,
    compute=per_prop_type_diversity,
    pro_comparable=False,
    higher_is_better=None,
))

register(MetricDefinition(
    name="bad_pairing_pct_handlist",
    kind=MetricKind.SCALAR,
    gated=True,
    tolerance=None,
    compute=bad_pairing_pct_handlist,
    pro_comparable=False,
    # Direction is unvalidated; HANDLIST_BAD_PAIRINGS is a first-principles
    # draft, not measured against rendered output.
    higher_is_better=False,
))

register(MetricDefinition(
    name="bad_pairing_pct_catalog",
    kind=MetricKind.SCALAR,
    gated=True,
    tolerance=None,
    compute=bad_pairing_pct_catalog,
    pro_comparable=False,
    # Direction is unvalidated; the catalog itself has not been measured
    # against rendered output.
    higher_is_better=False,
))

register(MetricDefinition(
    name="pairing_disagreement_pct",
    kind=MetricKind.SCALAR,
    gated=True,
    tolerance=None,
    compute=pairing_disagreement_pct,
    pro_comparable=False,
    # This metric IS the finding; direction is meaningless.
    higher_is_better=None,
))
