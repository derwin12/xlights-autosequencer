"""Tests for the `xlight-evaluate compare` CLI subcommand."""
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
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    entries = []
    for i in range(num_songs):
        song_id = f"song-{i:02d}"
        pro_id = f"pro-{i:02d}"
        mp3 = corpus_dir / f"{song_id}.mp3"
        mp3.write_bytes(b"\xff\xfb" + b"\x00" * 64)

        xsq = corpus_dir / f"{pro_id}.xsq"
        xsq.write_bytes(TINY_XSQ.read_bytes())

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


def _make_all_skipped_corpus(tmp_path: Path) -> Path:
    """Create a corpus where all entries are corpus-side skips (missing mp3)."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    xsq = corpus_dir / "pro.xsq"
    xsq.write_bytes(TINY_XSQ.read_bytes())

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-00",
                    "pro_id": "pro-00",
                    "xsq_path": str(xsq),
                    "mp3_path": str(corpus_dir / "nonexistent.mp3"),
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                }
            ]
        }),
        encoding="utf-8",
    )
    return corpus_dir


# ---------------------------------------------------------------------------
# T034-1: --json flag writes report, exit 0
# ---------------------------------------------------------------------------


def test_compare_json_flag_writes_report(tmp_path: Path) -> None:
    """With --json flag, a report JSON is written to the reports dir, exit 0."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        with patch("src.evaluation.compare.REPORT_DIR", reports_dir):
            result = runner.invoke(cli, [
                "compare",
                "--corpus", str(corpus_dir),
                "--json",
            ])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}. Output:\n{result.output}"
    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1, f"Expected 1 report file, got {report_files}"

    # --json should emit only the path, not the full terminal summary
    output = result.output.strip()
    assert str(report_files[0]) in output


# ---------------------------------------------------------------------------
# T034-2: --song filters to only that song
# ---------------------------------------------------------------------------


def test_compare_song_filter(tmp_path: Path) -> None:
    """With --song song-a, only that song is included in the report."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path, num_songs=2)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        with patch("src.evaluation.compare.REPORT_DIR", reports_dir):
            result = runner.invoke(cli, [
                "compare",
                "--corpus", str(corpus_dir),
                "--song", "song-00",
                "--json",
            ])

    assert result.exit_code == 0, f"Expected exit 0. Output:\n{result.output}"

    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text())

    # Only song-00 should be in entries (measured entries, not skips)
    measured_ids = [
        e["song_id"] for e in report["entries"] if e.get("ours") is not None
    ]
    assert measured_ids == ["song-00"]


# ---------------------------------------------------------------------------
# T034-3: all entries skipped → exit 2
# ---------------------------------------------------------------------------


def test_compare_exit_2_no_measurable(tmp_path: Path) -> None:
    """When all corpus entries are corpus-side skips, exit code is 2."""
    from src.cli.evaluate import cli

    corpus_dir = _make_all_skipped_corpus(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    runner = CliRunner()
    with patch("src.evaluation.compare.REPORT_DIR", reports_dir):
        result = runner.invoke(cli, [
            "compare",
            "--corpus", str(corpus_dir),
        ])

    assert result.exit_code == 2, f"Expected exit 2, got {result.exit_code}. Output:\n{result.output}"


# ---------------------------------------------------------------------------
# T034-4: generator error → exit 3
# ---------------------------------------------------------------------------


def test_compare_exit_3_generator_error(tmp_path: Path) -> None:
    """When generator raises GeneratorError, exit code is 3 (report still written)."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", side_effect=GeneratorError("no layout")):
        with patch("src.evaluation.compare.REPORT_DIR", reports_dir):
            result = runner.invoke(cli, [
                "compare",
                "--corpus", str(corpus_dir),
            ])

    assert result.exit_code == 3, f"Expected exit 3, got {result.exit_code}. Output:\n{result.output}"

    # Report should still be written (exit 3 != fatal)
    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1


# ---------------------------------------------------------------------------
# T034-5: report JSON has all required top-level keys
# ---------------------------------------------------------------------------


def test_compare_report_schema(tmp_path: Path) -> None:
    """Report JSON contains all required top-level keys."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    runner = CliRunner()
    with patch("src.evaluation.generator_runner.run", return_value=TINY_XSQ.read_bytes()):
        with patch("src.evaluation.compare.REPORT_DIR", reports_dir):
            result = runner.invoke(cli, [
                "compare",
                "--corpus", str(corpus_dir),
                "--json",
            ])

    assert result.exit_code == 0

    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text())

    required_keys = {
        "schema_version",
        "generated_at",
        "generator_commit",
        "corpus_manifest_hash",
        "entries",
        "cross_song_trends",
        "summary",
    }
    for key in required_keys:
        assert key in report, f"Missing key {key!r} in report"
