"""T041/T042: Integration tests for wizard non-interactive and non-TTY modes."""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import cli

FIXTURE = Path(__file__).parent.parent / "fixtures" / "beat_120bpm_10s.wav"


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Fixture audio file not found",
)
class TestWizardNonInteractive:
    """T041: --non-interactive flag suppresses all questionary prompts."""

    def test_noninteractive_exits_zero(self, tmp_path):
        runner = CliRunner()
        out_path = tmp_path / "result_analysis.json"
        result = runner.invoke(cli, [
            "wizard",
            str(FIXTURE),
            "--non-interactive",
            "--no-stems",
            "--no-phonemes",
            "--no-structure",
            "--output", str(out_path),
        ])
        assert result.exit_code == 0, f"wizard failed:\n{result.output}"

    def test_noninteractive_produces_json(self, tmp_path):
        runner = CliRunner()
        out_path = tmp_path / "result_analysis.json"
        runner.invoke(cli, [
            "wizard",
            str(FIXTURE),
            "--non-interactive",
            "--no-stems",
            "--no-phonemes",
            "--no-structure",
            "--output", str(out_path),
        ])
        assert out_path.exists(), "Expected analysis JSON not created"

    def test_noninteractive_no_tty_interaction(self, tmp_path):
        """The CliRunner provides no TTY — wizard must not block on prompts."""
        runner = CliRunner()
        out_path = tmp_path / "result_analysis.json"
        result = runner.invoke(cli, [
            "wizard",
            str(FIXTURE),
            "--non-interactive",
            "--no-stems",
            "--no-phonemes",
            "--no-structure",
            "--output", str(out_path),
        ])
        assert "Non-interactive mode" in result.output or result.exit_code == 0


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Fixture audio file not found",
)
class TestWizardNonTTYFallback:
    """T042: Piping stdin (non-TTY) falls back to non-interactive mode."""

    def test_non_tty_completes_without_error(self, tmp_path):
        runner = CliRunner()
        out_path = tmp_path / "result_analysis.json"
        # CliRunner already provides a non-TTY stdin
        result = runner.invoke(cli, [
            "wizard",
            str(FIXTURE),
            "--no-stems",
            "--no-phonemes",
            "--no-structure",
            "--output", str(out_path),
        ], input="")  # empty stdin simulates piped input
        # Should either succeed or print non-interactive notice
        assert result.exit_code == 0, f"non-TTY wizard failed:\n{result.output}"
