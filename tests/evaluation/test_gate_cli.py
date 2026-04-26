"""Tests for `xlight-evaluate gate` — orchestration + exit code + JSON report.

These tests mock the analyzer/generator/UI suites so they run in milliseconds.
Real audio analysis is exercised separately when the baseline is populated.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.cli.evaluate import cli
from src.evaluation import analyzer_baseline
from src.evaluation.acceptance_gate import (
    EXIT_INFRA,
    EXIT_NO_BASELINE,
    EXIT_PASS,
    EXIT_REGRESSION,
    GateOptions,
    SuiteResult,
    _aggregate_exit_code,
    format_summary,
    run_gate,
)
from src.evaluation.analyzer_baseline import (
    AnalyzerBaseline,
    FixtureSnapshot,
    TrackSnapshot,
)
from src.evaluation.corpus_resolver import CorpusEntry


# ---------- exit-code aggregation ----------

def test_aggregate_all_pass_returns_zero() -> None:
    suites = {
        "analyzer": SuiteResult("analyzer", "pass"),
        "generator": SuiteResult("generator", "pass"),
        "ui": SuiteResult("ui", "pass"),
    }
    assert _aggregate_exit_code(suites) == EXIT_PASS


def test_aggregate_any_regression_returns_six() -> None:
    suites = {
        "analyzer": SuiteResult("analyzer", "pass"),
        "generator": SuiteResult("generator", "fail"),
        "ui": SuiteResult("ui", "pass"),
    }
    assert _aggregate_exit_code(suites) == EXIT_REGRESSION


def test_aggregate_no_baseline_beats_regression() -> None:
    # Per spec priority: infra > no-baseline > regression > pass.
    suites = {
        "analyzer": SuiteResult("analyzer", "no-baseline"),
        "generator": SuiteResult("generator", "fail"),
    }
    assert _aggregate_exit_code(suites) == EXIT_NO_BASELINE


def test_aggregate_infra_error_beats_all() -> None:
    suites = {
        "analyzer": SuiteResult("analyzer", "infra-error"),
        "generator": SuiteResult("generator", "fail"),
        "ui": SuiteResult("ui", "no-baseline"),
    }
    assert _aggregate_exit_code(suites) == EXIT_INFRA


def test_aggregate_skip_treated_as_pass() -> None:
    suites = {
        "analyzer": SuiteResult("analyzer", "pass"),
        "ui": SuiteResult("ui", "skip"),
    }
    assert _aggregate_exit_code(suites) == EXIT_PASS


# ---------- run_gate integration (with mocks) ----------

def _mock_fixture_snapshot(entry: CorpusEntry) -> FixtureSnapshot:
    """Return a trivial snapshot — one 'librosa_beats' track with 4 events."""
    return FixtureSnapshot(
        fixture_slug=entry.slug,
        algorithms={
            "librosa_beats": TrackSnapshot(
                algorithm_name="librosa_beats",
                event_times_ms=[500, 1000, 1500, 2000],
                event_labels=[None, None, None, None],
                tolerance=analyzer_baseline.tolerance_for("librosa_beats"),
            ),
        },
    )


def _matching_baseline(slugs: list[str]) -> AnalyzerBaseline:
    return AnalyzerBaseline(
        fixtures={
            slug: _mock_fixture_snapshot(
                CorpusEntry(slug=slug, path=Path("/nope"), genre=None,
                            tempo_bpm=None, expected_section_count=None, source="cc0")
            )
            for slug in slugs
        }
    )


def _save_section_fidelity_baseline(path: Path) -> None:
    """Save a permissive section_fidelity baseline so tests don't trip the suite."""
    from src.evaluation import section_fidelity as sf
    sf.save_baseline(sf.FidelityBaseline(library_mean=0.0), path)


def test_run_gate_all_pass(tmp_path: Path) -> None:
    baseline_path = tmp_path / "analyzer_baseline.json"
    report_path = tmp_path / "gate-report.json"
    analyzer_baseline.save(_matching_baseline(["maple_leaf_rag"]), baseline_path)
    sf_baseline = tmp_path / "section_fidelity_baseline.json"
    _save_section_fidelity_baseline(sf_baseline)

    opts = GateOptions(
        quick=True,
        skip_ui=True,
        report_path=report_path,
        analyzer_baseline_path=baseline_path,
        section_fidelity_baseline_path=sf_baseline,
    )

    # Mock: analyzer snapshot returns matching data; generator + UI short-circuit.
    with patch(
        "src.evaluation.acceptance_gate._snapshot_fixture_live",
        side_effect=_mock_fixture_snapshot,
    ), patch(
        "src.evaluation.acceptance_gate.run_generator_suite",
        return_value=SuiteResult("generator", "pass"),
    ):
        report = run_gate(opts)

    assert report.exit_code == EXIT_PASS
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert data["exit_code"] == 0
    assert data["suites"]["analyzer"]["status"] == "pass"
    assert data["suites"]["ui"]["status"] == "skip"
    # Section-fidelity suite is wired in but corpus has no _story.json on disk
    # (the corpus entry is a real CC0 fixture, not a built story); the suite
    # therefore reports "skip" rather than fail/no-baseline. Still passes.
    assert data["suites"]["section_fidelity"]["status"] in ("pass", "skip")


def test_run_gate_no_analyzer_baseline_returns_four(tmp_path: Path) -> None:
    opts = GateOptions(
        quick=True,
        skip_ui=True,
        report_path=tmp_path / "gate-report.json",
        analyzer_baseline_path=tmp_path / "does-not-exist.json",
    )

    with patch(
        "src.evaluation.acceptance_gate.run_generator_suite",
        return_value=SuiteResult("generator", "pass"),
    ):
        report = run_gate(opts)

    assert report.exit_code == EXIT_NO_BASELINE


def test_run_gate_analyzer_regression_returns_six(tmp_path: Path) -> None:
    baseline_path = tmp_path / "analyzer_baseline.json"
    analyzer_baseline.save(_matching_baseline(["maple_leaf_rag"]), baseline_path)
    sf_baseline = tmp_path / "section_fidelity_baseline.json"
    _save_section_fidelity_baseline(sf_baseline)
    opts = GateOptions(
        quick=True,
        skip_ui=True,
        report_path=tmp_path / "gate-report.json",
        analyzer_baseline_path=baseline_path,
        section_fidelity_baseline_path=sf_baseline,
    )

    # Mock a fixture snapshot that drifts badly — 1 event instead of 4 (count fail).
    def drifted_snapshot(entry: CorpusEntry) -> FixtureSnapshot:
        return FixtureSnapshot(
            fixture_slug=entry.slug,
            algorithms={
                "librosa_beats": TrackSnapshot(
                    algorithm_name="librosa_beats",
                    event_times_ms=[500],
                    event_labels=[None],
                    tolerance=analyzer_baseline.tolerance_for("librosa_beats"),
                ),
            },
        )

    with patch(
        "src.evaluation.acceptance_gate._snapshot_fixture_live",
        side_effect=drifted_snapshot,
    ), patch(
        "src.evaluation.acceptance_gate.run_generator_suite",
        return_value=SuiteResult("generator", "pass"),
    ):
        report = run_gate(opts)

    assert report.exit_code == EXIT_REGRESSION
    assert report.suites["analyzer"].status == "fail"
    assert len(report.suites["analyzer"].violations) >= 1


def test_run_gate_infra_beats_regression(tmp_path: Path) -> None:
    """Unknown corpus fixture slug → infra error (8), even if other suites would fail."""
    opts = GateOptions(
        fixture_slug="nonexistent-slug",
        skip_ui=True,
        report_path=tmp_path / "report.json",
        analyzer_baseline_path=tmp_path / "baseline.json",
    )
    report = run_gate(opts)
    assert report.exit_code == EXIT_INFRA


# ---------- CLI plumbing ----------

def test_cli_gate_help_shows_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["gate", "--help"])
    assert result.exit_code == 0
    assert "--quick" in result.output
    assert "--skip-ui" in result.output
    assert "--fixture" in result.output
    assert "--report" in result.output


def test_cli_gate_command_registered() -> None:
    """Smoke test — `gate` shows up in top-level help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "gate" in result.output


def test_cli_snapshot_analyzer_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "snapshot-analyzer" in result.output


# ---------- format_summary output ----------

def test_format_summary_contains_verdict_and_stats() -> None:
    from src.evaluation.acceptance_gate import GateReport

    report = GateReport(
        started_at="2026-04-24T20:00:00Z",
        duration_seconds=12.34,
        exit_code=EXIT_PASS,
        corpus=["maple_leaf_rag"],
        suites={
            "analyzer": SuiteResult("analyzer", "pass", fixtures_checked=1,
                                     duration_seconds=8.0),
            "generator": SuiteResult("generator", "pass", fixtures_checked=1,
                                      duration_seconds=4.0),
            "ui": SuiteResult("ui", "skip", message="--skip-ui passed"),
        },
    )
    text = format_summary(report)
    assert "PASS" in text
    assert "analyzer" in text.lower()
    assert "maple_leaf_rag" in text
    assert "exit 0" in text


def test_format_summary_shows_fail_verdict_with_violations() -> None:
    from src.evaluation.acceptance_gate import GateReport

    report = GateReport(
        started_at="2026-04-24T20:00:00Z",
        duration_seconds=5.0,
        exit_code=EXIT_REGRESSION,
        corpus=["maple_leaf_rag"],
        suites={
            "analyzer": SuiteResult(
                "analyzer", "fail", fixtures_checked=1,
                violations=[{
                    "fixture_slug": "maple_leaf_rag",
                    "algorithm_name": "librosa_beats",
                    "kind": "count",
                    "detail": "event count drifted 75% (tolerance 2.0%): 4 → 1",
                }],
            ),
        },
    )
    text = format_summary(report)
    assert "FAIL" in text
    assert "librosa_beats" in text
    assert "count" in text


# ---------- report_path behavior ----------

def test_report_path_respected(tmp_path: Path) -> None:
    custom = tmp_path / "custom-report.json"
    baseline = tmp_path / "baseline.json"
    analyzer_baseline.save(AnalyzerBaseline(), baseline)
    sf_baseline = tmp_path / "sf_baseline.json"
    _save_section_fidelity_baseline(sf_baseline)

    opts = GateOptions(
        quick=True, skip_ui=True,
        report_path=custom,
        analyzer_baseline_path=baseline,
        section_fidelity_baseline_path=sf_baseline,
    )
    with patch(
        "src.evaluation.acceptance_gate.run_generator_suite",
        return_value=SuiteResult("generator", "pass"),
    ), patch(
        "src.evaluation.acceptance_gate._snapshot_fixture_live",
        side_effect=_mock_fixture_snapshot,
    ):
        run_gate(opts)

    assert custom.exists()
    assert not (tmp_path / "tests" / "golden" / "reports").exists()


# ---------- generator-suite subprocess path resolution ----------

def test_run_generator_suite_resolves_xlight_evaluate_via_sys_executable(tmp_path: Path) -> None:
    """The gate's generator-suite invocation should resolve `xlight-evaluate`
    via `sys.executable`'s bin directory rather than relying on PATH.

    Without this, callers had to prefix the gate with
    `PATH=".venv-vamp/bin:$PATH"` before invoking
    `.venv-vamp/bin/xlight-evaluate gate` — the subprocess would fail
    with FileNotFoundError because Python's interpreter was invoked by
    absolute path but the spawned subprocess inherited only the caller's PATH.
    """
    import sys
    from src.evaluation.acceptance_gate import run_generator_suite

    bin_dir = Path(sys.executable).parent
    fake_xe = bin_dir / "xlight-evaluate"
    fake_xe_existed = fake_xe.exists()
    if not fake_xe_existed:
        fake_xe.write_text("#!/bin/sh\nexit 0\n")
        fake_xe.chmod(0o755)
    try:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 0, "stdout": "", "stderr": "",
            })()
            run_generator_suite(corpus=[
                CorpusEntry(slug="x", path=tmp_path / "x.mp3", genre=None,
                            tempo_bpm=None, expected_section_count=None, source="cc0"),
            ])
        assert mock_run.called
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == str(fake_xe), f"expected {fake_xe}, got {cmd[0]!r}"
        assert cmd[1] == "check"
    finally:
        if not fake_xe_existed:
            fake_xe.unlink()


def test_run_generator_suite_falls_back_to_bare_name_when_not_in_bin(tmp_path: Path) -> None:
    """If sys.executable's bin dir doesn't contain xlight-evaluate, fall
    back to the bare command and let PATH resolve it (legacy compat for
    unconventional installs)."""
    from src.evaluation.acceptance_gate import run_generator_suite

    fake_python = tmp_path / "python"
    fake_python.write_text("")
    with patch("sys.executable", str(fake_python)):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 0, "stdout": "", "stderr": "",
            })()
            run_generator_suite(corpus=[
                CorpusEntry(slug="x", path=tmp_path / "x.mp3", genre=None,
                            tempo_bpm=None, expected_section_count=None, source="cc0"),
            ])
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "xlight-evaluate"


# ---------- --skip-ui behavior ----------

def test_skip_ui_flag_does_not_invoke_pytest(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    analyzer_baseline.save(AnalyzerBaseline(), baseline)
    sf_baseline = tmp_path / "sf_baseline.json"
    _save_section_fidelity_baseline(sf_baseline)
    opts = GateOptions(
        quick=True, skip_ui=True,
        report_path=tmp_path / "r.json",
        analyzer_baseline_path=baseline,
        section_fidelity_baseline_path=sf_baseline,
    )

    with patch(
        "src.evaluation.acceptance_gate.run_generator_suite",
        return_value=SuiteResult("generator", "pass"),
    ), patch(
        "src.evaluation.acceptance_gate._snapshot_fixture_live",
        side_effect=_mock_fixture_snapshot,
    ), patch(
        "subprocess.run",
    ) as mock_run:
        report = run_gate(opts)

    # pytest -m ui should NOT have been invoked.
    pytest_calls = [
        c for c in mock_run.call_args_list
        if c.args and isinstance(c.args[0], list) and "pytest" in c.args[0]
    ]
    assert not pytest_calls
    assert report.suites["ui"].status == "skip"
