"""Tests for the `xlight-evaluate check` CLI subcommand."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.evaluation.generator_runner import GeneratorError

TINY_XSQ = Path(__file__).parent / "fixtures" / "minimal_xsq" / "tiny.xsq"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_corpus(tmp_path: Path, *, num_songs: int = 1) -> Path:
    """Create a minimal corpus directory with a manifest and fake mp3 files."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    entries = []
    for i in range(num_songs):
        song_id = f"song-{i:02d}"
        pro_id = f"pro-{i:02d}"
        mp3 = corpus_dir / f"{song_id}.mp3"
        mp3.write_bytes(b"\xff\xfb" + b"\x00" * 64)  # fake mp3 bytes

        xsq = corpus_dir / f"{pro_id}.xsq"
        xsq.write_bytes(TINY_XSQ.read_bytes())  # valid xsq for corpus-side

        entries.append({
            "song_id": song_id,
            "pro_id": pro_id,
            "xsq_path": str(xsq),
            "mp3_path": str(mp3),
            "audio_hash": "md5:aabbccdd11223344aabbccdd11223344",
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        })

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return corpus_dir


def _make_baseline(tmp_path: Path, entries: dict) -> Path:
    """Write a raw baseline JSON file (bypassing write_baseline to control values)."""
    baseline_path = tmp_path / "baseline.json"
    data = {
        "schema_version": 1,
        "generator_commit": "deadbeef",
        "generated_at": "2026-01-01T00:00:00Z",
        "entries": entries,
    }
    baseline_path.write_text(json.dumps(data), encoding="utf-8")
    return baseline_path


def _compute_tiny_metrics() -> list[dict]:
    """Compute real metric values from tiny.xsq to use as a passing baseline."""
    import src.evaluation.metrics.pacing  # noqa: F401
    import src.evaluation.metrics.palette  # noqa: F401
    import src.evaluation.metrics.effects  # noqa: F401
    import src.evaluation.metrics.alignment  # noqa: F401
    import src.evaluation.metrics.sections  # noqa: F401
    import src.evaluation.metrics.internal  # noqa: F401
    from src.evaluation.xsq_reader import parse_bytes
    from src.cli.evaluate import _compute_metrics_for_summary

    xsq_bytes = TINY_XSQ.read_bytes()
    summary = parse_bytes(xsq_bytes, song_id="song-00", source_label="ours")
    metrics = _compute_metrics_for_summary(summary, audio_context={
        "beats": [],
        "energy_curve": [],
        "sections": None,
        "window_ms": 500,
    })
    return [mv.to_dict() for mv in metrics]


# ---------------------------------------------------------------------------
# T021-1: exit 4 — baseline missing
# ---------------------------------------------------------------------------

def test_check_exit_4_no_baseline(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    baseline_path = tmp_path / "nonexistent_baseline.json"

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "check",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 4
    assert "No baseline" in result.output or "baseline" in result.output.lower()


# ---------------------------------------------------------------------------
# T021-2: exit 5 — schema version mismatch
# ---------------------------------------------------------------------------

def test_check_exit_5_schema_mismatch(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({
            "schema_version": 99,
            "generator_commit": "abc",
            "generated_at": "2026-01-01T00:00:00Z",
            "entries": {},
        }),
        encoding="utf-8",
    )

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "check",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 5


# ---------------------------------------------------------------------------
# T021-3: exit 0 — all metrics pass
# ---------------------------------------------------------------------------

def test_check_exit_0_pass(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    tiny_metrics = _compute_tiny_metrics()
    baseline_path = _make_baseline(tmp_path, {"song-00": {"metrics": tiny_metrics}})

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "check",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}. Output:\n{result.output}"


# ---------------------------------------------------------------------------
# T021-4: exit 6 — gated metric regression
# ---------------------------------------------------------------------------

def test_check_exit_6_regression(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)

    # Use placements_per_minute=999.0 — tiny.xsq produces ~18 ppm, 999 is way off
    baseline_path = _make_baseline(tmp_path, {
        "song-00": {
            "metrics": [
                {
                    "name": "placements_per_minute",
                    "kind": "scalar",
                    "value": 999.0,
                    "payload": None,
                    "reliability": "ok",
                }
            ]
        }
    })

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "check",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 6
    assert "placements_per_minute" in result.output


# ---------------------------------------------------------------------------
# T021-5: exit 3 — generator error
# ---------------------------------------------------------------------------

def test_check_exit_3_generator_error(tmp_path: Path) -> None:
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    tiny_metrics = _compute_tiny_metrics()
    baseline_path = _make_baseline(tmp_path, {"song-00": {"metrics": tiny_metrics}})

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", side_effect=GeneratorError("no layout")):
        result = runner.invoke(cli, [
            "check",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 3


# ---------------------------------------------------------------------------
# T021-6: exit 7 — song count mismatch (CI env)
# ---------------------------------------------------------------------------

def test_check_exit_7_song_count_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.cli.evaluate import cli

    monkeypatch.setenv("CI", "1")

    # Corpus has only 1 song, but baseline records 2
    corpus_dir = _make_corpus(tmp_path, num_songs=1)
    tiny_metrics = _compute_tiny_metrics()
    baseline_path = _make_baseline(tmp_path, {
        "song-00": {"metrics": tiny_metrics},
        "song-99": {"metrics": tiny_metrics},  # extra song not in corpus
    })

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        result = runner.invoke(cli, [
            "check",
            "--corpus", str(corpus_dir),
            "--baseline", str(baseline_path),
        ])

    assert result.exit_code == 7
