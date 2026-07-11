"""Unit tests for src/evaluation/section_fidelity.py.

The module is shared by ``scripts/library_fidelity.py`` and the
acceptance gate's ``section_fidelity`` suite, so its math contract has
two consumers — both verified here.
"""
from __future__ import annotations

import io
import json
import statistics
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.evaluation import section_fidelity as sf


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _story(sections: list[dict], section_source: str = "heuristic") -> dict:
    return {
        "sections": sections,
        "global": {"section_source": section_source},
    }


def _section(role: str, agreement: int) -> dict:
    return {"role": role, "agreement_score": agreement}


# ---------------------------------------------------------------------------
# load_stories
# ---------------------------------------------------------------------------

def test_load_stories_skips_stems_dir(tmp_path: Path) -> None:
    """`stems/` subdirectories carry their own JSON; they're not full stories."""
    real = tmp_path / "alpha_story.json"
    real.write_text(json.dumps(_story([_section("verse", 2)])))
    stems = tmp_path / "stems" / "beta_story.json"
    stems.parent.mkdir()
    stems.write_text(json.dumps(_story([_section("chorus", 4)])))
    out = sf.load_stories(tmp_path)
    names = [name for name, _story in out]
    assert "alpha" in names
    assert "beta" not in names


def test_load_stories_skips_unparseable(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    bad = tmp_path / "bad_story.json"
    bad.write_text("{not json")
    good = tmp_path / "good_story.json"
    good.write_text(json.dumps(_story([_section("verse", 1)])))
    out = sf.load_stories(tmp_path)
    names = [name for name, _ in out]
    assert "good" in names
    assert "bad" not in names
    err = capsys.readouterr().err
    assert "skipping" in err


# ---------------------------------------------------------------------------
# summarize_song
# ---------------------------------------------------------------------------

def test_summarize_song_basic_counts() -> None:
    story = _story([
        _section("verse", 0),
        _section("chorus", 3),
        _section("verse", 0),
        _section("outro", 4),
    ])
    s = sf.summarize_song("song-x", story)
    assert s["name"] == "song-x"
    assert s["source"] == "heuristic"
    assert s["n_sections"] == 4
    assert s["n_zero"] == 2
    assert s["n_strong"] == 2
    assert s["zero_roles"] == ["verse", "verse"]
    assert s["mean_score"] == pytest.approx((0 + 3 + 0 + 4) / 4)


def test_summarize_song_handles_missing_agreement() -> None:
    """Legacy stories (pre-PR-#84) had no `agreement_score`; default to 0."""
    story = {
        "sections": [{"role": "verse"}, {"role": "chorus"}],
        "global": {"section_source": "heuristic"},
    }
    s = sf.summarize_song("legacy", story)
    assert s["n_sections"] == 2
    assert s["n_zero"] == 2
    assert s["mean_score"] == 0.0


def test_summarize_song_no_sections() -> None:
    story = _story([])
    s = sf.summarize_song("empty", story)
    assert s["n_sections"] == 0
    assert s["mean_score"] == 0.0
    assert s["median_score"] == 0.0


# ---------------------------------------------------------------------------
# compute_library_mean / compute_per_fixture_breakdown
# ---------------------------------------------------------------------------

def test_compute_library_mean_averages_per_song_means() -> None:
    stories = [
        ("a", _story([_section("v", 2), _section("c", 4)])),  # mean 3
        ("b", _story([_section("v", 1), _section("c", 1)])),  # mean 1
    ]
    assert sf.compute_library_mean(stories) == pytest.approx(2.0)


def test_compute_library_mean_skips_empty_stories() -> None:
    stories = [
        ("a", _story([_section("v", 4)])),  # mean 4
        ("b", _story([])),                  # skipped
    ]
    assert sf.compute_library_mean(stories) == pytest.approx(4.0)


def test_compute_library_mean_empty_corpus() -> None:
    assert sf.compute_library_mean([]) == 0.0


def test_per_fixture_breakdown_shape() -> None:
    stories = [
        ("alpha", _story([_section("v", 0)])),
        ("beta", _story([_section("c", 3)])),
    ]
    out = sf.compute_per_fixture_breakdown(stories)
    assert set(out.keys()) == {"alpha", "beta"}
    assert out["alpha"]["mean_score"] == 0.0
    assert out["beta"]["n_strong"] == 1


# ---------------------------------------------------------------------------
# print_report — preserves PR #84's stdout format
# ---------------------------------------------------------------------------

def test_print_report_columns_match_pr84() -> None:
    """The script's stdout shape is the contract; check the header & totals."""
    per_song = [sf.summarize_song("foo", _story([_section("v", 2)]))]
    buf = io.StringIO()
    with redirect_stdout(buf):
        sf.print_report(per_song)
    output = buf.getvalue()
    # PR #84's header (verbatim from the source script before refactor)
    assert "song" in output and "source" in output and "zero_roles" in output
    assert "Library totals:" in output
    assert "Per-song mean score — library mean:" in output


# ---------------------------------------------------------------------------
# Baseline serialization
# ---------------------------------------------------------------------------

def test_build_baseline_aggregates_per_song() -> None:
    per_song = [
        sf.summarize_song("a", _story([_section("v", 2), _section("c", 0)])),
        sf.summarize_song("b", _story([_section("v", 4), _section("c", 4)])),
    ]
    baseline = sf.build_baseline(per_song)
    assert baseline.library_mean == pytest.approx((1.0 + 4.0) / 2)
    assert baseline.per_fixture["a"]["n_zero"] == 1
    assert baseline.per_fixture["b"]["n_strong"] == 2
    assert baseline.n_zero_pct == pytest.approx(25.0)  # 1 of 4 sections


def test_baseline_round_trip(tmp_path: Path) -> None:
    per_song = [sf.summarize_song("a", _story([_section("v", 2)]))]
    baseline = sf.build_baseline(per_song)
    path = tmp_path / "baseline.json"
    sf.save_baseline(baseline, path)
    loaded = sf.load_baseline(path)
    assert loaded.library_mean == pytest.approx(baseline.library_mean)
    assert loaded.per_fixture == baseline.per_fixture


def test_baseline_load_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sf.load_baseline(tmp_path / "nope.json")


# ---------------------------------------------------------------------------
# load_stories_for_corpus (gate-suite path)
# ---------------------------------------------------------------------------

def test_load_stories_for_corpus_finds_next_to_mp3(tmp_path: Path) -> None:
    mp3 = tmp_path / "alpha.mp3"
    mp3.write_bytes(b"\x00")
    story_path = tmp_path / "alpha_story.json"
    story_payload = _story([_section("v", 3)])
    story_path.write_text(json.dumps(story_payload))

    entry = SimpleNamespace(slug="alpha", path=mp3)
    out = sf.load_stories_for_corpus([entry])
    assert len(out) == 1
    slug, story = out[0]
    assert slug == "alpha"
    assert story == story_payload


def test_load_stories_for_corpus_skips_missing(tmp_path: Path) -> None:
    mp3 = tmp_path / "no-story.mp3"
    mp3.write_bytes(b"\x00")
    entry = SimpleNamespace(slug="no-story", path=mp3)
    assert sf.load_stories_for_corpus([entry]) == []


# ---------------------------------------------------------------------------
# Equivalence with the manual script's per-song math (spec contract)
# ---------------------------------------------------------------------------

def test_library_mean_matches_per_song_summary_mean() -> None:
    """Spec: 'Script and gate produce identical library-mean for the same corpus.'

    The script computes the library mean by averaging per-song means; the
    gate calls compute_library_mean. The two values must agree to at
    least 4 decimal places (the spec's stated precision).
    """
    stories = [
        ("a", _story([_section("v", 0), _section("c", 4), _section("v", 2)])),
        ("b", _story([_section("v", 1), _section("c", 3)])),
        ("c", _story([_section("v", 2), _section("c", 2), _section("v", 4), _section("o", 1)])),
    ]
    library_mean = sf.compute_library_mean(stories)
    # Recompute from per-song summaries (the script's path)
    per_song = [sf.summarize_song(n, s) for n, s in stories]
    script_mean = statistics.mean(r["mean_score"] for r in per_song)
    assert round(library_mean, 4) == round(script_mean, 4)
