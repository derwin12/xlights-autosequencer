"""Tests for intra-pro variance computation and delta annotation."""
from __future__ import annotations

import pytest
from src.evaluation.compare import compute_intra_pro_variance, annotate_delta_vs_variance
from src.evaluation.models import MetricValue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mv(name: str, value: float) -> MetricValue:
    return MetricValue(name=name, kind="scalar", value=value, payload=None, reliability="ok")


# ---------------------------------------------------------------------------
# T042-1: two pro takes — min/max/range
# ---------------------------------------------------------------------------


def test_intra_pro_variance_two_pros() -> None:
    """Two pro takes compute correct min, max, range per metric."""
    pro_metrics_list = [
        [_mv("placements_per_minute", 38.0), _mv("beat_alignment_pct", 0.72)],
        [_mv("placements_per_minute", 44.1), _mv("beat_alignment_pct", 0.89)],
    ]
    result = compute_intra_pro_variance(pro_metrics_list)

    assert result is not None
    assert "placements_per_minute" in result
    ppm = result["placements_per_minute"]
    assert ppm["min"] == pytest.approx(38.0)
    assert ppm["max"] == pytest.approx(44.1)
    assert ppm["range"] == pytest.approx(44.1 - 38.0)

    assert "beat_alignment_pct" in result
    bap = result["beat_alignment_pct"]
    assert bap["min"] == pytest.approx(0.72)
    assert bap["max"] == pytest.approx(0.89)
    assert bap["range"] == pytest.approx(0.89 - 0.72)


# ---------------------------------------------------------------------------
# T042-2: three pro takes
# ---------------------------------------------------------------------------


def test_intra_pro_variance_three_pros() -> None:
    """Three pro takes: [38.0, 41.0, 44.1] → min=38.0, max=44.1, range=6.1."""
    pro_metrics_list = [
        [_mv("placements_per_minute", 38.0)],
        [_mv("placements_per_minute", 41.0)],
        [_mv("placements_per_minute", 44.1)],
    ]
    result = compute_intra_pro_variance(pro_metrics_list)

    assert result is not None
    ppm = result["placements_per_minute"]
    assert ppm["min"] == pytest.approx(38.0)
    assert ppm["max"] == pytest.approx(44.1)
    assert ppm["range"] == pytest.approx(6.1, abs=1e-9)


# ---------------------------------------------------------------------------
# T042-3: single pro take → None
# ---------------------------------------------------------------------------


def test_intra_pro_variance_single_pro_returns_none() -> None:
    """Single pro take → intra_pro_variance should be None (no variance to compute)."""
    pro_metrics_list = [
        [_mv("placements_per_minute", 38.0)],
    ]
    result = compute_intra_pro_variance(pro_metrics_list)

    assert result is None


# ---------------------------------------------------------------------------
# T042-4: delta within variance
# ---------------------------------------------------------------------------


def test_delta_within_variance() -> None:
    """ours_value within the pro range → annotation is 'within-variance'."""
    variance = {
        "placements_per_minute": {"min": 38.0, "max": 44.1, "range": 6.1},
    }
    # pro_mean = 41.05, range = 6.1, half = 3.05
    # ours = 42.0 — delta from mean = 0.95, well within half-range 3.05
    annotation = annotate_delta_vs_variance(
        ours_value=42.0,
        pro_mean=41.05,
        variance=variance,
        metric_name="placements_per_minute",
    )
    assert annotation == "within-variance"


# ---------------------------------------------------------------------------
# T042-5: delta exceeds variance
# ---------------------------------------------------------------------------


def test_delta_exceeds_variance() -> None:
    """ours_value far outside pro range → annotation is 'exceeds pro variance'."""
    variance = {
        "placements_per_minute": {"min": 38.0, "max": 44.1, "range": 6.1},
    }
    # pro_mean = 41.05, range = 6.1, half = 3.05
    # ours = 71.2 — delta from mean = 30.15, far outside half-range 3.05
    annotation = annotate_delta_vs_variance(
        ours_value=71.2,
        pro_mean=41.05,
        variance=variance,
        metric_name="placements_per_minute",
    )
    assert annotation == "exceeds pro variance"


# ---------------------------------------------------------------------------
# T042-6: delta exactly on boundary → within-variance (inclusive)
# ---------------------------------------------------------------------------


def test_delta_on_boundary() -> None:
    """ours_value exactly at range edge → 'within-variance' (inclusive)."""
    variance = {
        "placements_per_minute": {"min": 38.0, "max": 44.1, "range": 6.1},
    }
    # pro_mean = 41.05, half_range = 3.05
    # ours exactly at pro_mean + half_range = 44.1
    annotation = annotate_delta_vs_variance(
        ours_value=44.1,
        pro_mean=41.05,
        variance=variance,
        metric_name="placements_per_minute",
    )
    assert annotation == "within-variance"


# ---------------------------------------------------------------------------
# T042-7: variance populated in compare_song with 2 pro summaries
# ---------------------------------------------------------------------------


def test_variance_in_compare_song() -> None:
    """compare_song() with 2 pro summaries populates intra_pro_variance block."""
    from src.evaluation.compare import compare_song

    pro_summaries = [
        ("pro-a", [_mv("placements_per_minute", 38.0), _mv("beat_alignment_pct", 0.72)]),
        ("pro-b", [_mv("placements_per_minute", 44.1), _mv("beat_alignment_pct", 0.89)]),
    ]
    ours_metrics = [
        _mv("placements_per_minute", 50.0),
        _mv("beat_alignment_pct", 0.80),
    ]

    entry = compare_song(
        song_id="light-of-christmas",
        pro_summaries=pro_summaries,
        ours_metrics=ours_metrics,
    )

    assert entry["intra_pro_variance"] is not None
    var = entry["intra_pro_variance"]
    assert "placements_per_minute" in var
    assert var["placements_per_minute"]["min"] == pytest.approx(38.0)
    assert var["placements_per_minute"]["max"] == pytest.approx(44.1)
    assert var["placements_per_minute"]["range"] == pytest.approx(6.1, abs=1e-9)
    assert "beat_alignment_pct" in var


# ---------------------------------------------------------------------------
# T042-8: compare_song with 1 pro summary → intra_pro_variance is None
# ---------------------------------------------------------------------------


def test_no_variance_with_one_pro() -> None:
    """compare_song() with 1 pro summary → intra_pro_variance is None."""
    from src.evaluation.compare import compare_song

    pro_summaries = [
        ("pro-only", [_mv("placements_per_minute", 38.0)]),
    ]
    ours_metrics = [_mv("placements_per_minute", 50.0)]

    entry = compare_song(
        song_id="danger-zone",
        pro_summaries=pro_summaries,
        ours_metrics=ours_metrics,
    )

    assert entry["intra_pro_variance"] is None
