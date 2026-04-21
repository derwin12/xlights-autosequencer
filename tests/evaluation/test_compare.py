"""Tests for src/evaluation/compare.py — function-level unit tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.models import MetricValue, Placement, SequenceSummary

TINY_XSQ = Path(__file__).parent / "fixtures" / "minimal_xsq" / "tiny.xsq"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_summary(
    song_id: str = "song-a",
    source_label: str = "ours",
    num_placements: int = 10,
    duration_ms: int = 10_000,
) -> SequenceSummary:
    placements = tuple(
        Placement(
            start_ms=i * 1000,
            end_ms=i * 1000 + 500,
            effect_type="Marquee",
            model_name="Arch01",
            palette_colors=("#FF0000",),
            layer_index=0,
        )
        for i in range(num_placements)
    )
    return SequenceSummary(
        song_id=song_id,
        source_label=source_label,
        duration_ms=duration_ms,
        placements=placements,
        model_names=("Arch01",),
        inferred_prop_types={"Arch01": "arch"},
    )


def _mv(name: str, value: float) -> MetricValue:
    return MetricValue(name=name, kind="scalar", value=value, payload=None, reliability="ok")


# ---------------------------------------------------------------------------
# T033-1: compare_song returns pro_entries and ours
# ---------------------------------------------------------------------------


def test_compare_entry_has_pro_and_ours() -> None:
    """compare_song() returns a dict with pro_entries and ours fields."""
    import src.evaluation.metrics.pacing  # noqa: F401

    from src.evaluation.compare import compare_song

    pro_summary = _make_summary(song_id="song-a", source_label="pro:xatw", num_placements=5)
    ours_summary = _make_summary(song_id="song-a", source_label="ours", num_placements=8)

    pro_metrics = [_mv("placements_per_minute", 30.0)]
    ours_metrics = [_mv("placements_per_minute", 48.0)]

    entry = compare_song(
        song_id="song-a",
        pro_summaries=[("xatw", pro_metrics)],
        ours_metrics=ours_metrics,
    )

    assert "pro_entries" in entry
    assert "ours" in entry
    assert len(entry["pro_entries"]) == 1
    assert entry["pro_entries"][0]["pro_id"] == "xatw"
    assert entry["ours"] is not None
    assert entry["ours"]["metrics"][0]["name"] == "placements_per_minute"


# ---------------------------------------------------------------------------
# T033-2: cross_song_trends — 5/5 same direction → consistent_gap=True
# ---------------------------------------------------------------------------


def test_cross_song_trend_consistent_gap() -> None:
    """5 songs where ours > pro for placements_per_minute → consistent_gap=True."""
    import src.evaluation.metrics.pacing  # noqa: F401

    from src.evaluation.compare import compute_cross_song_trends
    from src.evaluation.metrics import get_registry

    # Each entry: ours.ppm > pro.ppm
    song_comparisons = []
    for i in range(5):
        song_id = f"song-{i:02d}"
        entry = {
            "song_id": song_id,
            "pro_entries": [{"pro_id": "p0", "metrics": [_mv("placements_per_minute", 30.0).to_dict()]}],
            "ours": {"metrics": [_mv("placements_per_minute", 60.0).to_dict()]},
            "skips": [],
        }
        song_comparisons.append(entry)

    registry = get_registry()
    trends = compute_cross_song_trends(song_comparisons, registry)

    ppm_trend = next(
        (t for t in trends if t["metric"] == "placements_per_minute"), None
    )
    assert ppm_trend is not None, "Expected a trend entry for placements_per_minute"
    assert ppm_trend["consistent_gap"] is True
    assert ppm_trend["direction"] == "ours>pro"
    assert ppm_trend["songs_agreeing"] == 5
    assert ppm_trend["songs_total"] == 5


# ---------------------------------------------------------------------------
# T033-3: cross_song_trends — 3/5 agree → consistent_gap=False
# ---------------------------------------------------------------------------


def test_cross_song_trend_not_consistent() -> None:
    """3 songs ours>pro, 2 songs ours<pro (3/5 = 60%, below 80%) → consistent_gap=False."""
    import src.evaluation.metrics.pacing  # noqa: F401

    from src.evaluation.compare import compute_cross_song_trends
    from src.evaluation.metrics import get_registry

    song_comparisons = []
    for i in range(3):
        song_comparisons.append({
            "song_id": f"song-high-{i}",
            "pro_entries": [{"pro_id": "p0", "metrics": [_mv("placements_per_minute", 30.0).to_dict()]}],
            "ours": {"metrics": [_mv("placements_per_minute", 60.0).to_dict()]},
            "skips": [],
        })
    for i in range(2):
        song_comparisons.append({
            "song_id": f"song-low-{i}",
            "pro_entries": [{"pro_id": "p0", "metrics": [_mv("placements_per_minute", 60.0).to_dict()]}],
            "ours": {"metrics": [_mv("placements_per_minute", 30.0).to_dict()]},
            "skips": [],
        })

    registry = get_registry()
    trends = compute_cross_song_trends(song_comparisons, registry)

    ppm_trend = next(
        (t for t in trends if t["metric"] == "placements_per_minute"), None
    )
    assert ppm_trend is not None
    assert ppm_trend["consistent_gap"] is False


# ---------------------------------------------------------------------------
# T033-4: consistency exactly at 80% threshold → consistent_gap=True
# ---------------------------------------------------------------------------


def test_consistency_exactly_at_threshold() -> None:
    """4/5 songs agree (80%) → consistent_gap=True (≥80%)."""
    import src.evaluation.metrics.pacing  # noqa: F401

    from src.evaluation.compare import compute_cross_song_trends
    from src.evaluation.metrics import get_registry

    song_comparisons = []
    # 4 songs ours > pro
    for i in range(4):
        song_comparisons.append({
            "song_id": f"song-high-{i}",
            "pro_entries": [{"pro_id": "p0", "metrics": [_mv("placements_per_minute", 30.0).to_dict()]}],
            "ours": {"metrics": [_mv("placements_per_minute", 60.0).to_dict()]},
            "skips": [],
        })
    # 1 song ours < pro
    song_comparisons.append({
        "song_id": "song-low-0",
        "pro_entries": [{"pro_id": "p0", "metrics": [_mv("placements_per_minute", 60.0).to_dict()]}],
        "ours": {"metrics": [_mv("placements_per_minute", 30.0).to_dict()]},
        "skips": [],
    })

    registry = get_registry()
    trends = compute_cross_song_trends(song_comparisons, registry)

    ppm_trend = next(
        (t for t in trends if t["metric"] == "placements_per_minute"), None
    )
    assert ppm_trend is not None
    assert ppm_trend["songs_agreeing"] == 4
    assert ppm_trend["songs_total"] == 5
    assert ppm_trend["consistent_gap"] is True  # 4/5 == 0.80 >= CONSISTENCY_THRESHOLD


# ---------------------------------------------------------------------------
# T033-5: corpus-side skip → entry has category="corpus-side" in skips
# ---------------------------------------------------------------------------


def test_skips_in_entry(tmp_path: Path) -> None:
    """A corpus-side skip (missing mp3) produces a skip entry with category='corpus-side'."""
    import json

    from src.evaluation.corpus import Corpus, SkipEntry

    # Create a corpus with a missing mp3
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    xsq = corpus_dir / "pro.xsq"
    xsq.write_bytes(TINY_XSQ.read_bytes())

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "entries": [
                {
                    "song_id": "song-a",
                    "pro_id": "p0",
                    "xsq_path": str(xsq),
                    "mp3_path": str(corpus_dir / "nonexistent.mp3"),  # missing
                    "audio_hash": "",
                    "tags": [],
                    "notes_ref": "",
                    "master_may_differ": False,
                }
            ]
        }),
        encoding="utf-8",
    )

    corpus = Corpus(manifest)
    skips = corpus.skips()
    assert len(skips) == 1
    assert skips[0].category == "corpus-side"
    assert skips[0].song_id == "song-a"


# ---------------------------------------------------------------------------
# T033-6: run_compare summary counts
# ---------------------------------------------------------------------------


def test_report_summary_counts(tmp_path: Path) -> None:
    """2 songs measured, 1 corpus-side skip → summary.songs_measured=2, songs_skipped_corpus_side=1."""
    import json

    from src.evaluation.compare import run_compare
    from src.evaluation.corpus import Corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    entries = []

    # 2 measurable songs
    for i in range(2):
        song_id = f"song-{i:02d}"
        mp3 = corpus_dir / f"{song_id}.mp3"
        mp3.write_bytes(b"\xff\xfb" + b"\x00" * 64)
        xsq = corpus_dir / f"{song_id}-pro.xsq"
        xsq.write_bytes(TINY_XSQ.read_bytes())
        entries.append({
            "song_id": song_id,
            "pro_id": f"p{i}",
            "xsq_path": str(xsq),
            "mp3_path": str(mp3),
            "audio_hash": "",
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        })

    # 1 corpus-side skip (missing mp3)
    skip_xsq = corpus_dir / "skip-pro.xsq"
    skip_xsq.write_bytes(TINY_XSQ.read_bytes())
    entries.append({
        "song_id": "song-skip",
        "pro_id": "p-skip",
        "xsq_path": str(skip_xsq),
        "mp3_path": str(corpus_dir / "nonexistent.mp3"),
        "audio_hash": "",
        "tags": [],
        "notes_ref": "",
        "master_may_differ": False,
    })

    manifest = corpus_dir / "manifest.json"
    manifest.write_text(json.dumps({"entries": entries}), encoding="utf-8")

    corpus = Corpus(manifest)

    with patch(
        "src.evaluation.generator_runner.run",
        return_value=TINY_XSQ.read_bytes(),
    ):
        report = run_compare(corpus)

    summary = report["summary"]
    assert summary["songs_measured"] == 2
    assert summary["songs_skipped_corpus_side"] == 1
