"""1-song end-to-end smoke test for the compare command."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

TINY_XSQ = Path(__file__).parent / "fixtures" / "minimal_xsq" / "tiny.xsq"


def _make_corpus(tmp_path: Path) -> Path:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    mp3 = corpus_dir / "song-a.mp3"
    mp3.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    xsq = corpus_dir / "pro.xsq"
    xsq.write_bytes(TINY_XSQ.read_bytes())

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-a",
                    "pro_id": "xatw",
                    "xsq_path": str(xsq),
                    "mp3_path": str(mp3),
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


def test_compare_end_to_end_smoke(tmp_path: Path) -> None:
    """Single song end-to-end: report is written with correct schema fields."""
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

    assert result.exit_code == 0, f"Expected exit 0. Output:\n{result.output}"

    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1, f"Expected 1 report file, found: {report_files}"

    report = json.loads(report_files[0].read_text())

    # Schema version present
    assert report.get("schema_version") == 1

    # entries has 1 entry for the song
    assert len(report["entries"]) == 1
    assert report["entries"][0]["song_id"] == "song-a"

    # cross_song_trends is a list (possibly empty with 1 song)
    assert isinstance(report["cross_song_trends"], list)

    # summary.songs_measured == 1
    assert report["summary"]["songs_measured"] == 1


# ---------------------------------------------------------------------------
# US3 — partial corpus graceful handling
# ---------------------------------------------------------------------------


def _make_corpus_all_missing_mp3(tmp_path: Path) -> Path:
    """Corpus where every entry has a non-existent mp3 → all corpus-side skips."""
    corpus_dir = tmp_path / "corpus_all_skip"
    corpus_dir.mkdir()

    xsq = corpus_dir / "pro.xsq"
    xsq.write_bytes(TINY_XSQ.read_bytes())

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-missing",
                    "pro_id": "xatw",
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


def _make_corpus_three_entries(tmp_path: Path) -> Path:
    """Corpus with 3 entries: 2 valid, 1 with missing mp3."""
    corpus_dir = tmp_path / "corpus_three"
    corpus_dir.mkdir()

    mp3_a = corpus_dir / "song-a.mp3"
    mp3_a.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    mp3_b = corpus_dir / "song-b.mp3"
    mp3_b.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    xsq = corpus_dir / "pro.xsq"
    xsq.write_bytes(TINY_XSQ.read_bytes())

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-a",
                    "pro_id": "xatw",
                    "xsq_path": str(xsq),
                    "mp3_path": str(mp3_a),
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                },
                {
                    "song_id": "song-b",
                    "pro_id": "xatw",
                    "xsq_path": str(xsq),
                    "mp3_path": str(mp3_b),
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                },
                {
                    "song_id": "song-missing",
                    "pro_id": "xatw",
                    "xsq_path": str(xsq),
                    "mp3_path": str(corpus_dir / "nonexistent.mp3"),
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                },
            ]
        }),
        encoding="utf-8",
    )
    return corpus_dir


def _make_corpus_master_may_differ(tmp_path: Path) -> Path:
    """Corpus with 1 entry where master_may_differ=true."""
    corpus_dir = tmp_path / "corpus_mmd"
    corpus_dir.mkdir()

    mp3 = corpus_dir / "song-mmd.mp3"
    mp3.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    xsq = corpus_dir / "pro.xsq"
    xsq.write_bytes(TINY_XSQ.read_bytes())

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-mmd",
                    "pro_id": "xatw",
                    "xsq_path": str(xsq),
                    "mp3_path": str(mp3),
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": True,
                }
            ]
        }),
        encoding="utf-8",
    )
    return corpus_dir


def _make_corpus_bad_xsq(tmp_path: Path) -> Path:
    """Corpus with 2 entries: 1 valid, 1 with an unparseable pro XSQ."""
    corpus_dir = tmp_path / "corpus_bad_xsq"
    corpus_dir.mkdir()

    mp3_a = corpus_dir / "song-a.mp3"
    mp3_a.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    mp3_b = corpus_dir / "song-b.mp3"
    mp3_b.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    good_xsq = corpus_dir / "pro_good.xsq"
    good_xsq.write_bytes(TINY_XSQ.read_bytes())

    bad_xsq = corpus_dir / "pro_bad.xsq"
    bad_xsq.write_bytes(b"not xml")

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-a",
                    "pro_id": "xatw-good",
                    "xsq_path": str(good_xsq),
                    "mp3_path": str(mp3_a),
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                },
                {
                    "song_id": "song-b",
                    "pro_id": "xatw-bad",
                    "xsq_path": str(bad_xsq),
                    "mp3_path": str(mp3_b),
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                },
            ]
        }),
        encoding="utf-8",
    )
    return corpus_dir


def test_all_entries_skipped_exit_2(tmp_path: Path) -> None:
    """All corpus entries have missing mp3 → exit 2 with 'No measurable entries' message."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus_all_missing_mp3(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "compare",
        "--corpus", str(corpus_dir),
    ])

    assert result.exit_code == 2, f"Expected exit 2. Output:\n{result.output}\nStderr:\n{result.output}"
    assert "No measurable" in (result.output + (result.stderr or "")), (
        f"Expected 'No measurable' in output. Got:\n{result.output}"
    )


def test_one_of_three_skipped_exit_0(tmp_path: Path) -> None:
    """2 valid songs + 1 missing mp3: exit 0, 2 measured, skip entry corpus-side."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus_three_entries(tmp_path)
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

    assert result.exit_code == 0, f"Expected exit 0. Output:\n{result.output}"

    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text())

    assert report["summary"]["songs_measured"] == 2

    # The missing-mp3 song should appear in entries as a skip
    skip_entry = next(
        (e for e in report["entries"] if e["song_id"] == "song-missing"), None
    )
    assert skip_entry is not None, "Expected 'song-missing' in entries"
    assert skip_entry["ours"] is None
    assert any(s["category"] == "corpus-side" for s in skip_entry["skips"]), (
        f"Expected corpus-side skip for song-missing. Got: {skip_entry['skips']}"
    )


def test_master_may_differ_reduced_reliability(tmp_path: Path) -> None:
    """master_may_differ=true → audio-dependent pro metrics get reliability='reduced'."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus_master_may_differ(tmp_path)
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

    assert result.exit_code == 0, f"Expected exit 0. Output:\n{result.output}"

    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text())

    song_entry = next(e for e in report["entries"] if e["song_id"] == "song-mmd")
    assert len(song_entry["pro_entries"]) == 1

    pro_metrics = song_entry["pro_entries"][0]["metrics"]
    audio_dependent = {"beat_alignment_pct", "section_transition_delta", "per_section_palette_diversity"}
    reduced_names = {m["name"] for m in pro_metrics if m["reliability"] == "reduced"}
    missing_reduced = audio_dependent - reduced_names
    assert not missing_reduced, (
        f"Expected these audio-dependent metrics to have reliability='reduced': {missing_reduced}"
    )


def test_unparseable_pro_xsq_corpus_side_skip(tmp_path: Path) -> None:
    """Unparseable pro XSQ → corpus-side skip with reason 'pro_unparseable'; other songs still measured."""
    from src.cli.evaluate import cli

    corpus_dir = _make_corpus_bad_xsq(tmp_path)
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

    assert result.exit_code == 0, f"Expected exit 0. Output:\n{result.output}"

    report_files = list(reports_dir.glob("*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text())

    # Both songs are measured (ours was generated successfully for both)
    assert report["summary"]["songs_measured"] == 2

    # song-b's pro entry should be listed as a corpus-side skip with pro_unparseable
    song_b = next(e for e in report["entries"] if e["song_id"] == "song-b")
    assert any(
        s["category"] == "corpus-side" and s["reason"] == "pro_unparseable"
        for s in song_b["skips"]
    ), f"Expected corpus-side/pro_unparseable skip. Got: {song_b['skips']}"

    # song-a should be measured normally (1 pro entry)
    song_a = next(e for e in report["entries"] if e["song_id"] == "song-a")
    assert len(song_a["pro_entries"]) == 1
