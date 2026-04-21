"""Tests for baseline snapshot read/write and regression gate logic."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.evaluation.models import MetricValue
from src.evaluation.metrics import MetricDefinition, MetricKind, MetricTolerance, DEFAULT_TOLERANCE
from src.evaluation.baseline import (
    BaselineMissingError,
    BaselineSchemaError,
    CompareResult,
    RegressionViolation,
    write_baseline,
    load_baseline,
    compare_against_baseline,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metric(name: str, value: float | None, kind: str = "scalar") -> MetricValue:
    return MetricValue(name=name, kind=kind, value=value, payload=None, reliability="ok")


def _registry_with(*defns: MetricDefinition) -> dict:
    return {d.name: d for d in defns}


def _defn(name: str, tolerance: MetricTolerance | None = None, gated: bool = True) -> MetricDefinition:
    return MetricDefinition(
        name=name,
        kind=MetricKind.SCALAR,
        gated=gated,
        tolerance=tolerance,
        compute=lambda *a, **kw: None,
        pro_comparable=False,
    )


# ---------------------------------------------------------------------------
# T020-1: write and read back
# ---------------------------------------------------------------------------

def test_write_and_read_baseline(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    song_metrics = {
        "song-a": [
            _metric("placements_per_minute", 42.3),
            _metric("beat_alignment_pct", 0.85),
            _metric("palette_diversity", 0.60),
        ],
        "song-b": [
            _metric("placements_per_minute", 38.1),
            _metric("beat_alignment_pct", 0.78),
            _metric("palette_diversity", 0.55),
        ],
    }
    write_baseline(song_metrics, path)

    result = load_baseline(path)

    assert result["schema_version"] == SCHEMA_VERSION
    assert "generator_commit" in result
    assert "generated_at" in result
    assert set(result["entries"].keys()) == {"song-a", "song-b"}

    for song_id, metrics in song_metrics.items():
        stored = result["entries"][song_id]["metrics"]
        assert len(stored) == len(metrics)
        stored_by_name = {m["name"]: m for m in stored}
        for mv in metrics:
            assert mv.name in stored_by_name
            assert stored_by_name[mv.name]["value"] == mv.value
            assert stored_by_name[mv.name]["kind"] == mv.kind


# ---------------------------------------------------------------------------
# T020-2: schema version mismatch
# ---------------------------------------------------------------------------

def test_schema_version_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "bad_baseline.json"
    path.write_text(
        json.dumps({
            "schema_version": 99,
            "generator_commit": "abc",
            "generated_at": "2026-01-01T00:00:00Z",
            "entries": {},
        }),
        encoding="utf-8",
    )
    with pytest.raises(BaselineSchemaError):
        load_baseline(path)


# ---------------------------------------------------------------------------
# T020-3: regression detected — relative tolerance
# ---------------------------------------------------------------------------

def test_regression_detected_relative(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    write_baseline({"song-x": [_metric("placements_per_minute", 100.0)]}, path)
    baseline = load_baseline(path)

    registry = _registry_with(
        _defn("placements_per_minute", MetricTolerance(kind="relative", value=0.15))
    )
    current = {"song-x": [_metric("placements_per_minute", 70.0)]}

    result = compare_against_baseline(baseline, current, registry)

    assert not result.passed
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.song_id == "song-x"
    assert v.metric_name == "placements_per_minute"
    assert v.baseline_value == pytest.approx(100.0)
    assert v.current_value == pytest.approx(70.0)


# ---------------------------------------------------------------------------
# T020-4: regression NOT detected — relative tolerance
# ---------------------------------------------------------------------------

def test_regression_not_detected_relative(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    write_baseline({"song-x": [_metric("placements_per_minute", 100.0)]}, path)
    baseline = load_baseline(path)

    registry = _registry_with(
        _defn("placements_per_minute", MetricTolerance(kind="relative", value=0.15))
    )
    current = {"song-x": [_metric("placements_per_minute", 112.0)]}

    result = compare_against_baseline(baseline, current, registry)

    assert result.passed
    assert result.violations == []


# ---------------------------------------------------------------------------
# T020-5: regression detected — absolute tolerance
# ---------------------------------------------------------------------------

def test_regression_detected_absolute(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    write_baseline({"song-x": [_metric("beat_alignment_pct", 0.80)]}, path)
    baseline = load_baseline(path)

    registry = _registry_with(
        _defn("beat_alignment_pct", MetricTolerance(kind="absolute", value=0.03))
    )
    current = {"song-x": [_metric("beat_alignment_pct", 0.76)]}

    result = compare_against_baseline(baseline, current, registry)

    assert not result.passed
    assert len(result.violations) == 1
    assert result.violations[0].metric_name == "beat_alignment_pct"


# ---------------------------------------------------------------------------
# T020-6: regression NOT detected — absolute tolerance
# ---------------------------------------------------------------------------

def test_regression_not_detected_absolute(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    write_baseline({"song-x": [_metric("beat_alignment_pct", 0.80)]}, path)
    baseline = load_baseline(path)

    registry = _registry_with(
        _defn("beat_alignment_pct", MetricTolerance(kind="absolute", value=0.03))
    )
    current = {"song-x": [_metric("beat_alignment_pct", 0.82)]}

    result = compare_against_baseline(baseline, current, registry)

    assert result.passed
    assert result.violations == []


# ---------------------------------------------------------------------------
# T020-7: missing baseline file raises BaselineMissingError
# ---------------------------------------------------------------------------

def test_missing_baseline_raises(tmp_path: Path) -> None:
    with pytest.raises(BaselineMissingError):
        load_baseline(tmp_path / "nonexistent_baseline.json")


# ---------------------------------------------------------------------------
# T020-8: None baseline value is skipped (not a regression)
# ---------------------------------------------------------------------------

def test_none_baseline_value_skipped(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    write_baseline({"song-x": [_metric("placements_per_minute", None)]}, path)
    baseline = load_baseline(path)

    registry = _registry_with(
        _defn("placements_per_minute", MetricTolerance(kind="relative", value=0.10))
    )
    # current has a value; baseline had None — should be skipped, not a regression
    current = {"song-x": [_metric("placements_per_minute", 50.0)]}

    result = compare_against_baseline(baseline, current, registry)

    assert result.passed
    assert result.violations == []


# ---------------------------------------------------------------------------
# T020-9: song count mismatch
# ---------------------------------------------------------------------------

def test_song_count_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force CI=true so the mismatch check runs
    monkeypatch.setenv("CI", "true")

    path = tmp_path / "baseline.json"
    write_baseline(
        {
            "song-a": [_metric("placements_per_minute", 42.0)],
            "song-b": [_metric("placements_per_minute", 38.0)],
            "song-c": [_metric("placements_per_minute", 55.0)],
        },
        path,
    )
    baseline = load_baseline(path)

    registry = _registry_with(_defn("placements_per_minute"))
    # Only 2 of the 3 songs present in current
    current = {
        "song-a": [_metric("placements_per_minute", 42.0)],
        "song-b": [_metric("placements_per_minute", 38.0)],
    }

    result = compare_against_baseline(baseline, current, registry)

    assert result.song_count_mismatch is True
    assert not result.passed


# ---------------------------------------------------------------------------
# T020-10: multiple regressions all returned
# ---------------------------------------------------------------------------

def test_compare_returns_all_regressions(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    write_baseline(
        {
            "song-a": [
                _metric("placements_per_minute", 100.0),
                _metric("beat_alignment_pct", 0.90),
                _metric("palette_diversity", 0.70),
            ],
        },
        path,
    )
    baseline = load_baseline(path)

    registry = _registry_with(
        _defn("placements_per_minute", MetricTolerance(kind="relative", value=0.10)),
        _defn("beat_alignment_pct", MetricTolerance(kind="absolute", value=0.03)),
        _defn("palette_diversity", MetricTolerance(kind="relative", value=0.10)),
    )
    # All three metrics regress
    current = {
        "song-a": [
            _metric("placements_per_minute", 50.0),   # 50% drop — regression
            _metric("beat_alignment_pct", 0.80),       # 0.10 drop — regression
            _metric("palette_diversity", 0.50),        # 28% drop — regression
        ],
    }

    result = compare_against_baseline(baseline, current, registry)

    assert not result.passed
    assert len(result.violations) == 3
    regressed_names = {v.metric_name for v in result.violations}
    assert regressed_names == {"placements_per_minute", "beat_alignment_pct", "palette_diversity"}
