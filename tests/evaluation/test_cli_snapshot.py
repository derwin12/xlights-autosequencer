"""Tests for the `xlight-evaluate snapshot` CLI subcommand."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.evaluation.generator_runner import GeneratorError

TINY_XSQ = Path(__file__).parent / "fixtures" / "minimal_xsq" / "tiny.xsq"


# ---------------------------------------------------------------------------
# Helpers (shared with test_cli_check.py — duplicated for isolation)
# ---------------------------------------------------------------------------

def _make_corpus(tmp_path: Path) -> Path:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    mp3 = corpus_dir / "song-00.mp3"
    mp3.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    xsq = corpus_dir / "pro-00.xsq"
    xsq.write_bytes(TINY_XSQ.read_bytes())

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-00",
                    "pro_id": "pro-00",
                    "xsq_path": str(xsq),
                    "mp3_path": str(mp3),
                    "audio_hash": "md5:aabbccdd11223344aabbccdd11223344",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                }
            ]
        }),
        encoding="utf-8",
    )
    return corpus_dir


def _make_baseline_with_ppm(tmp_path: Path, ppm_value: float) -> Path:
    baseline_path = tmp_path / "baseline.json"
    data = {
        "schema_version": 1,
        "generator_commit": "deadbeef",
        "generated_at": "2026-01-01T00:00:00Z",
        "entries": {
            "song-00": {
                "metrics": [
                    {
                        "name": "placements_per_minute",
                        "kind": "scalar",
                        "value": ppm_value,
                        "payload": None,
                        "reliability": "ok",
                    }
                ]
            }
        },
    }
    baseline_path.write_text(json.dumps(data), encoding="utf-8")
    return baseline_path


# ---------------------------------------------------------------------------
# T022-1: exit 0 — writes baseline with correct schema
# ---------------------------------------------------------------------------

def test_snapshot_exit_0_writes_baseline(tmp_path: Path) -> None:
    from src.cli.evaluate import cli
    from src.evaluation.baseline import SCHEMA_VERSION

    corpus_dir = _make_corpus(tmp_path)
    baseline_path = tmp_path / "baseline.json"

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "snapshot",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}. Output:\n{result.output}"
    assert baseline_path.exists(), "Baseline file should be written"

    data = json.loads(baseline_path.read_text())
    assert data["schema_version"] == SCHEMA_VERSION
    assert "entries" in data
    assert "song-00" in data["entries"]
    assert "metrics" in data["entries"]["song-00"]
    assert len(data["entries"]["song-00"]["metrics"]) > 0


# ---------------------------------------------------------------------------
# T022-2: exit 3 — generator error, no baseline written
# ---------------------------------------------------------------------------

def test_snapshot_exit_3_generator_error(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    baseline_path = tmp_path / "baseline.json"

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", side_effect=GeneratorError("oops")):
        result = runner.invoke(cli, [
            "snapshot",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 3
    assert not baseline_path.exists(), "Baseline should NOT be written on generator error"


# ---------------------------------------------------------------------------
# T022-3: exit 8 — would regress without --force
# ---------------------------------------------------------------------------

def test_snapshot_exit_8_would_regress_no_force(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    # Set existing baseline with ppm=999.0 (way higher than tiny.xsq produces)
    baseline_path = _make_baseline_with_ppm(tmp_path, 999.0)

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "snapshot",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 8


# ---------------------------------------------------------------------------
# T022-4: --force overwrites despite regression
# ---------------------------------------------------------------------------

def test_snapshot_force_overwrites(tmp_path: Path) -> None:
    from src.cli.evaluate import cli
    from src.evaluation.baseline import SCHEMA_VERSION

    corpus_dir = _make_corpus(tmp_path)
    baseline_path = _make_baseline_with_ppm(tmp_path, 999.0)

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "snapshot",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
            "--force",
        ])

    assert result.exit_code == 0, f"Expected exit 0 with --force, got {result.exit_code}. Output:\n{result.output}"
    data = json.loads(baseline_path.read_text())
    # New baseline should have the actual ppm, not 999
    metrics = {m["name"]: m for m in data["entries"]["song-00"]["metrics"]}
    ppm = metrics.get("placements_per_minute", {}).get("value")
    assert ppm is not None
    assert ppm < 100.0, f"Expected real ppm < 100, got {ppm}"


# ---------------------------------------------------------------------------
# T022-5: after snapshot, running check → exit 0
# ---------------------------------------------------------------------------

def test_snapshot_baseline_check_after_write(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    baseline_path = tmp_path / "baseline.json"

    runner = CliRunner()
    xsq_bytes = TINY_XSQ.read_bytes()

    # Step 1: snapshot
    with patch("src.evaluation.generator_runner.run", return_value=xsq_bytes):
        snap_result = runner.invoke(cli, [
            "snapshot",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])
    assert snap_result.exit_code == 0, f"Snapshot failed:\n{snap_result.output}"

    # Step 2: check against that baseline
    with patch("src.evaluation.generator_runner.run", return_value=xsq_bytes):
        check_result = runner.invoke(cli, [
            "check",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])
    assert check_result.exit_code == 0, f"Check failed:\n{check_result.output}"
