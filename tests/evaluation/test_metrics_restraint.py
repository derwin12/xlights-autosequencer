"""Tests for restraint metric: whole_house_cluster_count."""
import pytest

from src.evaluation.models import SequenceSummary, Placement
from src.evaluation.metrics.restraint import whole_house_cluster_count, _CLUSTER_GAP_MS


def make_summary(placements: list[Placement], duration_ms: int = 200_000) -> SequenceSummary:
    return SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=duration_ms,
        placements=tuple(placements),
        model_names=("01_BASE_All",),
        inferred_prop_types={},
    )


def _p(model_name: str, start_ms: int, end_ms: int) -> Placement:
    return Placement(start_ms, end_ms, "Shockwave", model_name, ("#FFFFFF",), 0)


def test_no_placements_returns_zero():
    summary = make_summary([])
    result = whole_house_cluster_count(summary)
    assert result.value == 0.0
    assert result.payload == []


def test_single_whole_house_placement_returns_zero():
    summary = make_summary([_p("01_BASE_All", 0, 1000)])
    assert whole_house_cluster_count(summary).value == 0.0


def test_two_widely_spaced_whole_house_placements_no_cluster():
    summary = make_summary([
        _p("01_BASE_All", 0, 1000),
        _p("01_BASE_All", 1000 + _CLUSTER_GAP_MS + 500, 2000 + _CLUSTER_GAP_MS + 500),
    ])
    result = whole_house_cluster_count(summary)
    assert result.value == 0.0
    assert result.payload == []


def test_two_tightly_clustered_whole_house_placements_counted():
    summary = make_summary([
        _p("01_BASE_All", 0, 1000),
        _p("01_BASE_All", 1000 + 500, 2000 + 500),  # 500ms gap, under _CLUSTER_GAP_MS
    ])
    result = whole_house_cluster_count(summary)
    assert result.value == 1.0
    assert result.payload[0]["gap_ms"] == 500


def test_exactly_at_threshold_gap_not_counted():
    summary = make_summary([
        _p("01_BASE_All", 0, 1000),
        _p("01_BASE_All", 1000 + _CLUSTER_GAP_MS, 2000 + _CLUSTER_GAP_MS),
    ])
    assert whole_house_cluster_count(summary).value == 0.0


def test_only_the_fades_variant_still_matches_whole_house_prefix():
    summary = make_summary([
        _p("01_BASE_All_FADES", 0, 1000),
        _p("01_BASE_All_FADES", 1200, 2200),
    ])
    assert whole_house_cluster_count(summary).value == 1.0


def test_non_whole_house_placements_ignored_even_when_clustered():
    summary = make_summary([
        _p("06_PROP_Snowflake", 0, 1000),
        _p("06_PROP_Snowflake", 1100, 2100),
    ])
    assert whole_house_cluster_count(summary).value == 0.0


def test_multiple_clusters_counted_independently():
    summary = make_summary([
        _p("01_BASE_All", 0, 1000),
        _p("01_BASE_All", 1200, 2200),      # cluster 1 (200ms gap)
        _p("01_BASE_All", 100_000, 101_000),
        _p("01_BASE_All", 101_100, 102_100),  # cluster 2 (100ms gap)
    ])
    result = whole_house_cluster_count(summary)
    assert result.value == 2.0
    assert len(result.payload) == 2


def test_disable_env_var_skips_registration(monkeypatch):
    """XLIGHT_DISABLE_RESTRAINT_METRIC=1 must skip registering the metric
    entirely (no code change needed to turn it off) -- re-imports the
    module fresh under the env var to exercise the module-level guard.
    The registry has no unregister() API and never drops an entry on its
    own, so the earlier (enabled) registration from this file's own import
    is removed directly before re-importing under the disabled env var."""
    import importlib
    import sys

    import src.evaluation.metrics as metrics_module

    monkeypatch.setenv("XLIGHT_DISABLE_RESTRAINT_METRIC", "1")
    metrics_module._REGISTRY.pop("whole_house_cluster_count", None)
    sys.modules.pop("src.evaluation.metrics.restraint", None)
    try:
        importlib.import_module("src.evaluation.metrics.restraint")
        assert "whole_house_cluster_count" not in metrics_module.get_registry()
    finally:
        sys.modules.pop("src.evaluation.metrics.restraint", None)
        monkeypatch.delenv("XLIGHT_DISABLE_RESTRAINT_METRIC", raising=False)
        importlib.import_module("src.evaluation.metrics.restraint")
