"""Tests for ``src.microscope.diff``.

Test-only ``MetricDefinition`` instances are registered in a module-scoped
fixture so direction-arrow lookups resolve, and unregistered after the
module finishes — otherwise they leak into the global registry and break
other tests that iterate it (e.g. ``test_integration_smoke``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    _REGISTRY,
    register,
)
from src.evaluation.models import MetricValue
from src.microscope.diff import DiffReport, diff_results


def _noop_compute(*_args, **_kwargs):  # pragma: no cover - registry stub only
    return None


_TEST_METRIC_NAMES = (
    "metric_unknown_dir",
    "metric_higher_better",
    "metric_lower_better",
)


@pytest.fixture(scope="module", autouse=True)
def _register_test_metrics():
    """Register test-only metrics for the duration of this module, then
    remove them so other tests that iterate the registry aren't polluted."""
    register(
        MetricDefinition(
            name="metric_unknown_dir",
            kind=MetricKind.SCALAR, gated=False, tolerance=None,
            compute=_noop_compute, pro_comparable=False,
            higher_is_better=None,
        )
    )
    register(
        MetricDefinition(
            name="metric_higher_better",
            kind=MetricKind.SCALAR, gated=False, tolerance=None,
            compute=_noop_compute, pro_comparable=False,
            higher_is_better=True,
        )
    )
    register(
        MetricDefinition(
            name="metric_lower_better",
            kind=MetricKind.SCALAR, gated=False, tolerance=None,
            compute=_noop_compute, pro_comparable=False,
            higher_is_better=False,
        )
    )
    yield
    for name in _TEST_METRIC_NAMES:
        _REGISTRY.pop(name, None)


@dataclass
class _FakeResult:
    slug: str
    metrics: dict[str, MetricValue]


def _scalar(name: str, value: float | None) -> MetricValue:
    return MetricValue(name=name, kind="scalar", value=value, payload=None, reliability="ok")


def _structured(name: str, value: float | None = None) -> MetricValue:
    return MetricValue(
        name=name, kind="structured", value=value, payload={"x": 1}, reliability="ok"
    )


def _write_baseline(baseline_dir: Path, slug: str, metrics: dict[str, dict]) -> None:
    song_dir = baseline_dir / slug
    song_dir.mkdir(parents=True, exist_ok=True)
    with (song_dir / "baseline.json").open("w", encoding="utf-8") as fh:
        json.dump({"slug": slug, "metrics": metrics}, fh)


def _row(report: DiffReport, slug: str, metric: str):
    for row in report.rows:
        if row.slug == slug and row.metric == metric:
            return row
    raise AssertionError(f"row not found: {slug}/{metric} in {[(r.slug, r.metric) for r in report.rows]}")


def test_unknown_direction_renders_bare_arrows(tmp_path):
    _write_baseline(
        tmp_path,
        "song_a",
        {
            "metric_unknown_dir": {"value": 10.0, "kind": "scalar"},
        },
    )
    # Positive delta.
    report_pos = diff_results(
        [_FakeResult("song_a", {"metric_unknown_dir": _scalar("metric_unknown_dir", 12.0)})],
        tmp_path,
    )
    assert _row(report_pos, "song_a", "metric_unknown_dir").direction == "↑"

    # Negative delta.
    report_neg = diff_results(
        [_FakeResult("song_a", {"metric_unknown_dir": _scalar("metric_unknown_dir", 8.0)})],
        tmp_path,
    )
    assert _row(report_neg, "song_a", "metric_unknown_dir").direction == "↓"

    # Zero delta -> empty string.
    report_zero = diff_results(
        [_FakeResult("song_a", {"metric_unknown_dir": _scalar("metric_unknown_dir", 10.0)})],
        tmp_path,
    )
    assert _row(report_zero, "song_a", "metric_unknown_dir").direction == ""


def test_higher_is_better_true_renders_check_or_x(tmp_path):
    _write_baseline(
        tmp_path,
        "song_b",
        {"metric_higher_better": {"value": 10.0, "kind": "scalar"}},
    )

    report_pos = diff_results(
        [_FakeResult("song_b", {"metric_higher_better": _scalar("metric_higher_better", 12.0)})],
        tmp_path,
    )
    assert _row(report_pos, "song_b", "metric_higher_better").direction == "↑✓"

    report_neg = diff_results(
        [_FakeResult("song_b", {"metric_higher_better": _scalar("metric_higher_better", 8.0)})],
        tmp_path,
    )
    assert _row(report_neg, "song_b", "metric_higher_better").direction == "↓✗"

    report_zero = diff_results(
        [_FakeResult("song_b", {"metric_higher_better": _scalar("metric_higher_better", 10.0)})],
        tmp_path,
    )
    assert _row(report_zero, "song_b", "metric_higher_better").direction == ""


def test_higher_is_better_false_inverts_arrows(tmp_path):
    _write_baseline(
        tmp_path,
        "song_c",
        {"metric_lower_better": {"value": 10.0, "kind": "scalar"}},
    )

    report_pos = diff_results(
        [_FakeResult("song_c", {"metric_lower_better": _scalar("metric_lower_better", 12.0)})],
        tmp_path,
    )
    # Got worse (went up when lower-is-better).
    assert _row(report_pos, "song_c", "metric_lower_better").direction == "↑✗"

    report_neg = diff_results(
        [_FakeResult("song_c", {"metric_lower_better": _scalar("metric_lower_better", 8.0)})],
        tmp_path,
    )
    # Improved (went down when lower-is-better).
    assert _row(report_neg, "song_c", "metric_lower_better").direction == "↓✓"

    report_zero = diff_results(
        [_FakeResult("song_c", {"metric_lower_better": _scalar("metric_lower_better", 10.0)})],
        tmp_path,
    )
    assert _row(report_zero, "song_c", "metric_lower_better").direction == ""


def test_missing_baseline_marks_rows_new(tmp_path):
    # No baseline file written for "fresh_song".
    result = _FakeResult(
        "fresh_song",
        {"metric_unknown_dir": _scalar("metric_unknown_dir", 7.0)},
    )
    report = diff_results([result], tmp_path)

    row = _row(report, "fresh_song", "metric_unknown_dir")
    assert row.note == "NEW"
    assert row.direction == ""
    assert row.baseline is None
    assert row.current == 7.0
    assert row.absolute_delta is None
    assert row.relative_pct is None


def test_missing_current_metric_marks_row_missing(tmp_path):
    _write_baseline(
        tmp_path,
        "song_d",
        {
            "metric_unknown_dir": {"value": 10.0, "kind": "scalar"},
            "metric_higher_better": {"value": 5.0, "kind": "scalar"},
        },
    )
    # Current run only computed one of the two metrics.
    result = _FakeResult(
        "song_d",
        {"metric_unknown_dir": _scalar("metric_unknown_dir", 11.0)},
    )
    report = diff_results([result], tmp_path)

    missing_row = _row(report, "song_d", "metric_higher_better")
    assert missing_row.note == "MISSING"
    assert missing_row.direction == ""
    assert missing_row.current is None
    assert missing_row.baseline == 5.0
    assert missing_row.absolute_delta is None


def test_structured_metric_excluded_and_counted(tmp_path):
    _write_baseline(
        tmp_path,
        "song_e",
        {
            "metric_unknown_dir": {"value": 10.0, "kind": "scalar"},
            "structured_metric": {"value": None, "kind": "structured"},
        },
    )
    result = _FakeResult(
        "song_e",
        {
            "metric_unknown_dir": _scalar("metric_unknown_dir", 12.0),
            "structured_metric": _structured("structured_metric"),
        },
    )
    report = diff_results([result], tmp_path)

    metric_names = {row.metric for row in report.rows}
    assert "structured_metric" not in metric_names
    assert "metric_unknown_dir" in metric_names
    assert report.structured_excluded == 1

    table = report.format_table()
    assert "1 structured metric(s) excluded" in table


def test_format_table_basic_tokens(tmp_path):
    _write_baseline(
        tmp_path,
        "song_f",
        {"metric_unknown_dir": {"value": 4.0, "kind": "scalar"}},
    )
    result = _FakeResult(
        "song_f",
        {"metric_unknown_dir": _scalar("metric_unknown_dir", 7.0)},
    )
    table = diff_results([result], tmp_path).format_table()

    lines = table.splitlines()
    # Header tokens present.
    header = lines[0]
    for token in ("Song", "Metric", "Baseline", "Current", "Delta", "%Change"):
        assert token in header
    # Separator line composed of dashes between columns.
    assert "---" in lines[1]
    # Data row contains slug and metric name and a recognizable delta token.
    data_line = next(line for line in lines[2:] if "song_f" in line)
    assert "metric_unknown_dir" in data_line
    assert "+3.0" in data_line  # absolute delta
    assert "+75.0%" in data_line  # relative_pct = (7-4)/4*100


def test_relative_pct_handles_zero_baseline(tmp_path):
    _write_baseline(
        tmp_path,
        "song_g",
        {"metric_unknown_dir": {"value": 0.0, "kind": "scalar"}},
    )
    result = _FakeResult(
        "song_g",
        {"metric_unknown_dir": _scalar("metric_unknown_dir", 5.0)},
    )
    report = diff_results([result], tmp_path)
    row = _row(report, "song_g", "metric_unknown_dir")
    assert row.absolute_delta == 5.0
    assert row.relative_pct is None
    # Baseline=0, delta>0, direction unknown -> bare up arrow.
    assert row.direction == "↑"
