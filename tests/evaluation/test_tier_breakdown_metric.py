"""Tests for ``tier_placement_breakdown`` and ``group_utilization``
diagnostic metrics."""
from __future__ import annotations

import src.evaluation.metrics.tier_breakdown as _tier_breakdown  # noqa: F401  (registers)
from src.evaluation.metrics import get_registry
from src.evaluation.metrics.tier_breakdown import (
    _tier_prefix,
    group_utilization,
    tier_placement_breakdown,
)
from src.evaluation.models import Placement, SequenceSummary


def _summary(placement_models: tuple[str, ...]) -> SequenceSummary:
    placements = tuple(
        Placement(
            start_ms=i * 1000,
            end_ms=(i + 1) * 1000,
            effect_type="Plasma",
            model_name=name,
            palette_colors=("#FF0000",),
            layer_index=0,
        )
        for i, name in enumerate(placement_models)
    )
    return SequenceSummary(
        song_id="t",
        source_label="ours",
        duration_ms=10_000,
        placements=placements,
        model_names=tuple(set(placement_models)),
        inferred_prop_types={n: "Unknown" for n in placement_models},
    )


def test_tier_prefix_extracts_two_digit_role():
    assert _tier_prefix("08_HERO_MegaTree") == "08_HERO"
    assert _tier_prefix("02_GEO_Bot") == "02_GEO"
    assert _tier_prefix("04_BEAT_1") == "04_BEAT"


def test_tier_prefix_unknown_for_non_conformant_names():
    assert _tier_prefix("MegaTree") == "unknown"
    assert _tier_prefix("AB_NoPrefix") == "unknown"
    assert _tier_prefix("") == "unknown"


def test_tier_breakdown_counts_per_prefix():
    s = _summary(
        ("08_HERO_MegaTree", "08_HERO_MegaTree", "02_GEO_Left", "02_GEO_Bot")
    )
    mv = tier_placement_breakdown(s)
    assert mv.payload["counts"] == {"02_GEO": 2, "08_HERO": 2}
    # Two distinct active tier prefixes.
    assert mv.value == 2.0
    assert mv.payload["active_tiers"] == ["02_GEO", "08_HERO"]


def test_tier_breakdown_unknown_bucketed_separately():
    s = _summary(("MegaTree", "08_HERO_MegaTree"))
    mv = tier_placement_breakdown(s)
    assert mv.payload["counts"] == {"08_HERO": 1, "unknown": 1}
    # Unknown isn't counted as an "active tier".
    assert mv.value == 1.0
    assert mv.payload["active_tiers"] == ["08_HERO"]


def test_tier_breakdown_no_placements():
    s = _summary(())
    mv = tier_placement_breakdown(s)
    assert mv.value == 0.0
    assert mv.reliability == "no_placements"


def test_group_utilization_counts_each_target():
    s = _summary(
        ("08_HERO_MegaTree", "08_HERO_MegaTree", "02_GEO_Left", "02_GEO_Bot")
    )
    mv = group_utilization(s)
    assert mv.payload["counts"] == {
        "02_GEO_Bot": 1,
        "02_GEO_Left": 1,
        "08_HERO_MegaTree": 2,
    }
    assert mv.value == 3.0


def test_both_metrics_registered():
    reg = get_registry()
    assert "tier_placement_breakdown" in reg
    assert "group_utilization" in reg
    assert reg["tier_placement_breakdown"].higher_is_better is True
