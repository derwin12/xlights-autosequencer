"""Tests for ``xlight-evaluate microscope`` subcommand group.

The microscope CLI is registered on ``src.cli.evaluate.cli``. These tests
exercise help output, argument validation, and the sensitivity-gate
refusal logic in ``baseline``. The actual ``run`` / ``panel`` /
``sensitivity`` execution paths depend on the parallel-phase modules
(``src/microscope/panel.py`` and ``src/microscope/sensitivity.py``) and
are exercised in those phases' own test files.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import microscope as microscope_cli
from src.cli.evaluate import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Help output
# ---------------------------------------------------------------------------


def test_evaluate_help_lists_microscope(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "microscope" in result.output


def test_microscope_group_help_lists_all_four_subcommands(
    runner: CliRunner,
) -> None:
    result = runner.invoke(cli, ["microscope", "--help"])
    assert result.exit_code == 0
    for sub in ("run", "panel", "baseline", "sensitivity"):
        assert sub in result.output, (
            f"Expected '{sub}' in microscope --help output:\n{result.output}"
        )


def test_microscope_run_help_shows_documented_options(
    runner: CliRunner,
) -> None:
    result = runner.invoke(cli, ["microscope", "run", "--help"])
    assert result.exit_code == 0
    for opt in (
        "--layout",
        "--output-dir",
        "--curves-mode",
        "--variation-seed",
        "--baseline",
    ):
        assert opt in result.output, (
            f"Expected '{opt}' in run --help output:\n{result.output}"
        )


def test_microscope_panel_help_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["microscope", "panel", "--help"])
    assert result.exit_code == 0
    for opt in (
        "--manifest",
        "--layout",
        "--output-dir",
        "--parallel",
        "--baseline",
        "--variation-seed",
    ):
        assert opt in result.output


def test_microscope_baseline_help_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["microscope", "baseline", "--help"])
    assert result.exit_code == 0
    for opt in ("--input-dir", "--golden-dir"):
        assert opt in result.output


def test_microscope_sensitivity_help_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["microscope", "sensitivity", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_microscope_run_without_audio_path_errors(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["microscope", "run"])
    assert result.exit_code != 0
    # Click's "Missing argument" usage error.
    assert "AUDIO_PATH" in result.output.upper() or "Missing" in result.output


def test_microscope_panel_with_missing_manifest_errors(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        cli,
        ["microscope", "panel", "--manifest", str(tmp_path / "nope.json")],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "manifest" in result.output.lower()


# ---------------------------------------------------------------------------
# Baseline sensitivity-gate refusal
# ---------------------------------------------------------------------------


def test_baseline_refuses_when_proof_missing(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`baseline` exits 1 and mentions sensitivity when the proof is absent."""
    # Point the proof path at an empty tmp_path so it's guaranteed missing.
    missing_proof = tmp_path / "sensitivity_passed.json"
    monkeypatch.setattr(
        microscope_cli,
        "_SENSITIVITY_PROOF_PATH",
        missing_proof,
    )

    result = runner.invoke(
        cli,
        [
            "microscope",
            "baseline",
            "--input-dir",
            str(tmp_path / "in"),
            "--golden-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1
    assert "sensitivity" in result.output.lower()


def test_baseline_refuses_when_proof_is_stale(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cone has a commit newer than the proof's run_at, exit 1."""
    proof_path = tmp_path / "sensitivity_passed.json"
    # Write a proof with a very old run_at.
    old_run_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    proof_path.write_text(
        json.dumps({"run_at": old_run_at.isoformat()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        microscope_cli,
        "_SENSITIVITY_PROOF_PATH",
        proof_path,
    )

    # Mock the cone-commit lookup to a newer timestamp.
    newer_ts = int(
        datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc).timestamp()
    )
    monkeypatch.setattr(
        microscope_cli,
        "_latest_cone_commit_timestamp",
        lambda repo_root: newer_ts,
    )

    result = runner.invoke(
        cli,
        [
            "microscope",
            "baseline",
            "--input-dir",
            str(tmp_path / "in"),
            "--golden-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1
    out = result.output.lower()
    assert "sensitivity" in out or "stale" in out or "newer" in out
