"""Tests for ``xlight-analyze library refresh`` and its staleness checks.

Covers:
- Pluggable staleness checks (missing/zero agreement_score, missing chorus_ssm_supported)
- Per-entry refresh verdicts (stale rebuilt, fresh skipped, no hierarchy skipped,
  reviewed skipped)
- End-to-end CLI invocation against a synthetic library: stale + fresh +
  no-hierarchy entries — assert output line-for-line.

Test isolation: every test uses a ``tmp_path``-scoped library index and audio
files under ``tmp_path``. No test reads ``~/.xlight/`` (per Test Isolation
Conventions in CLAUDE.md).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import cli
from src.cli.library import (
    STALENESS_CHECKS,
    _detect_staleness,
    _missing_chorus_ssm_supported,
    _missing_or_zero_agreement_score,
    _refresh_entry,
)
from src.library import Library, LibraryEntry


# ── Fixture builders ────────────────────────────────────────────────────────────

def _make_audio_and_hierarchy(song_dir: Path, stem: str = "song") -> Path:
    """Create a minimal audio file + matching ``_hierarchy.json`` on disk.

    The hierarchy is the smallest dict ``build_song_story`` accepts — empty
    sections list and an empty repetition_groups field. Returns the audio path.
    """
    song_dir.mkdir(parents=True, exist_ok=True)
    audio_path = song_dir / f"{stem}.mp3"
    audio_path.write_bytes(b"fake mp3")

    hierarchy_path = song_dir / f"{stem}_hierarchy.json"
    hierarchy = {
        "schema_version": "2.0.0",
        "audio_file": str(audio_path),
        "duration_ms": 10000,
        "estimated_tempo_bpm": 120.0,
        "sections": [],
        "tracks": [],
        "repetition_groups": [],
    }
    hierarchy_path.write_text(json.dumps(hierarchy), encoding="utf-8")
    return audio_path


def _stale_story_pre_pr84() -> dict:
    """A story shaped like the ones the bug was discovered on — sections
    present, but no ``agreement_score`` field on any of them.
    """
    return {
        "schema_version": "1.0.0",
        "song": {"title": "Stale Song", "file": "stale.mp3", "duration_seconds": 10},
        "sections": [
            {"id": "s00", "role": "verse", "start": 0.0, "end": 5.0},
            {"id": "s01", "role": "chorus", "start": 5.0, "end": 10.0,
             "chorus_ssm_supported": True},
        ],
    }


def _stale_story_zero_scores() -> dict:
    """A story with ``agreement_score`` present but zero on every section
    (the WIP-window placeholder pattern).
    """
    return {
        "schema_version": "1.0.0",
        "song": {"title": "Zeroed", "file": "zero.mp3", "duration_seconds": 10},
        "sections": [
            {"id": "s00", "role": "verse", "start": 0.0, "end": 5.0,
             "agreement_score": 0},
            {"id": "s01", "role": "chorus", "start": 5.0, "end": 10.0,
             "agreement_score": 0, "chorus_ssm_supported": True},
        ],
    }


def _fresh_story() -> dict:
    """A story that should pass every staleness check."""
    return {
        "schema_version": "1.0.0",
        "song": {"title": "Fresh", "file": "fresh.mp3", "duration_seconds": 10},
        "sections": [
            {"id": "s00", "role": "verse", "start": 0.0, "end": 5.0,
             "agreement_score": 2},
            {"id": "s01", "role": "chorus", "start": 5.0, "end": 10.0,
             "agreement_score": 3, "chorus_ssm_supported": True},
        ],
    }


def _make_entry(audio_path: Path, *, source_hash: str = "h", title: str = "T") -> LibraryEntry:
    return LibraryEntry(
        source_hash=source_hash,
        source_file=str(audio_path),
        filename=audio_path.name,
        analysis_path=str(audio_path.with_name(audio_path.stem + "_analysis.json")),
        duration_ms=10000,
        estimated_tempo_bpm=120.0,
        track_count=1,
        stem_separation=False,
        analyzed_at=1000,
        title=title,
    )


# ── Staleness checks ────────────────────────────────────────────────────────────

class TestStalenessChecks:
    def test_missing_agreement_score_flagged_stale(self):
        story = _stale_story_pre_pr84()
        assert _missing_or_zero_agreement_score(story) == "missing agreement_score"

    def test_all_zero_agreement_score_flagged_stale(self):
        story = _stale_story_zero_scores()
        assert _missing_or_zero_agreement_score(story) == "agreement_score all zero"

    def test_present_nonzero_agreement_score_passes(self):
        story = _fresh_story()
        assert _missing_or_zero_agreement_score(story) is None

    def test_non_numeric_agreement_score_flagged_stale(self):
        story = {"sections": [{"agreement_score": "two"}]}
        assert _missing_or_zero_agreement_score(story) == "agreement_score non-numeric"

    def test_empty_sections_passes_check(self):
        # Edge: no sections to judge → check defers to the next check.
        assert _missing_or_zero_agreement_score({"sections": []}) is None

    def test_chorus_without_ssm_field_flagged_stale(self):
        story = {
            "sections": [
                {"id": "s00", "role": "verse", "agreement_score": 1},
                {"id": "s01", "role": "chorus", "agreement_score": 2},  # missing field
            ],
        }
        assert _missing_chorus_ssm_supported(story) == "missing chorus_ssm_supported"

    def test_chorus_with_ssm_field_passes(self):
        assert _missing_chorus_ssm_supported(_fresh_story()) is None

    def test_no_chorus_passes_check(self):
        story = {"sections": [{"id": "s00", "role": "verse", "agreement_score": 1}]}
        assert _missing_chorus_ssm_supported(story) is None

    def test_combined_detect_returns_first_reason(self):
        # Pre-PR-#84 stories trigger the agreement check before the chorus check.
        story = _stale_story_pre_pr84()
        assert _detect_staleness(story) == "missing agreement_score"

    def test_fresh_story_returns_none(self):
        assert _detect_staleness(_fresh_story()) is None

    def test_pluggable_check_list_is_iterable(self):
        # Spec contract: STALENESS_CHECKS is the single extension point.
        assert callable(STALENESS_CHECKS[0])
        assert all(callable(c) for c in STALENESS_CHECKS)


# ── Per-entry refresh verdicts ─────────────────────────────────────────────────

class TestRefreshEntry:
    def test_stale_story_with_hierarchy_refreshed(self, tmp_path):
        audio_path = _make_audio_and_hierarchy(tmp_path / "song1", stem="song1")
        story_path = audio_path.parent / "song1_story.json"
        story_path.write_text(json.dumps(_stale_story_pre_pr84()))
        entry = _make_entry(audio_path)

        captured: dict = {}

        def fake_build(hierarchy: dict, audio: str) -> dict:
            captured["called"] = (hierarchy, audio)
            return _fresh_story()

        def fake_write(story: dict, output: str) -> None:
            Path(output).write_text(json.dumps(story))

        verdict = _refresh_entry(
            entry, dry_run=False, build_fn=fake_build, write_fn=fake_write,
        )
        assert verdict.action == "refreshed"
        assert verdict.reason == "missing agreement_score"
        # Builder was called with the cached hierarchy and audio path.
        assert captured["called"][1] == str(audio_path)
        # Story file now contains the refreshed (fresh) story.
        assert json.loads(story_path.read_text())["song"]["title"] == "Fresh"

    def test_fresh_story_skipped(self, tmp_path):
        audio_path = _make_audio_and_hierarchy(tmp_path / "song", stem="song")
        story_path = audio_path.parent / "song_story.json"
        story_path.write_text(json.dumps(_fresh_story()))
        entry = _make_entry(audio_path)

        called = {"build": 0, "write": 0}

        def never_build(*a, **kw): called["build"] += 1; raise AssertionError
        def never_write(*a, **kw): called["write"] += 1; raise AssertionError

        verdict = _refresh_entry(
            entry, dry_run=False, build_fn=never_build, write_fn=never_write,
        )
        assert verdict.action == "skipped"
        assert verdict.reason == "fresh"
        assert called == {"build": 0, "write": 0}

    def test_missing_hierarchy_skipped(self, tmp_path):
        # Stale story but no _hierarchy.json on disk.
        song_dir = tmp_path / "songX"
        song_dir.mkdir()
        audio_path = song_dir / "songX.mp3"
        audio_path.write_bytes(b"")
        story_path = song_dir / "songX_story.json"
        story_path.write_text(json.dumps(_stale_story_pre_pr84()))
        entry = _make_entry(audio_path)

        verdict = _refresh_entry(
            entry, dry_run=False,
            build_fn=lambda *a, **kw: pytest.fail("must not call build"),
            write_fn=lambda *a, **kw: pytest.fail("must not call write"),
        )
        assert verdict.action == "skipped"
        assert verdict.reason == "no _hierarchy.json"

    def test_missing_story_skipped(self, tmp_path):
        # Hierarchy present but no story → nothing to refresh.
        audio_path = _make_audio_and_hierarchy(tmp_path / "song", stem="song")
        entry = _make_entry(audio_path)

        verdict = _refresh_entry(
            entry, dry_run=False,
            build_fn=lambda *a, **kw: pytest.fail("must not call build"),
            write_fn=lambda *a, **kw: pytest.fail("must not call write"),
        )
        assert verdict.action == "skipped"
        assert verdict.reason == "no _story.json"

    def test_reviewed_story_never_overwritten(self, tmp_path):
        # Even if stale by every other criterion, a reviewed story is preserved.
        audio_path = _make_audio_and_hierarchy(tmp_path / "song", stem="song")
        story_path = audio_path.parent / "song_story.json"
        story = _stale_story_pre_pr84()
        story["review"] = {"status": "reviewed"}
        story_path.write_text(json.dumps(story))
        entry = _make_entry(audio_path)

        verdict = _refresh_entry(
            entry, dry_run=False,
            build_fn=lambda *a, **kw: pytest.fail("must not call build"),
            write_fn=lambda *a, **kw: pytest.fail("must not call write"),
        )
        assert verdict.action == "skipped"
        assert verdict.reason == "reviewed (user-edited)"

    def test_dry_run_does_not_write(self, tmp_path):
        audio_path = _make_audio_and_hierarchy(tmp_path / "song", stem="song")
        story_path = audio_path.parent / "song_story.json"
        original = json.dumps(_stale_story_pre_pr84())
        story_path.write_text(original)
        entry = _make_entry(audio_path)

        verdict = _refresh_entry(
            entry, dry_run=True,
            build_fn=lambda *a, **kw: pytest.fail("must not build in dry-run"),
            write_fn=lambda *a, **kw: pytest.fail("must not write in dry-run"),
        )
        assert verdict.action == "would-refresh"
        assert verdict.reason == "missing agreement_score"
        # File untouched.
        assert story_path.read_text() == original


# ── End-to-end CLI invocation ──────────────────────────────────────────────────

class TestRefreshCLI:
    def test_synthetic_library_outputs_expected_lines(self, tmp_path, monkeypatch):
        # Build a library with three entries:
        #   stale + has hierarchy → refreshed
        #   fresh                  → skipped (fresh)
        #   stale + no hierarchy   → skipped (no _hierarchy.json)
        stale_audio = _make_audio_and_hierarchy(tmp_path / "stale", stem="stale")
        (stale_audio.parent / "stale_story.json").write_text(
            json.dumps(_stale_story_pre_pr84())
        )

        fresh_audio = _make_audio_and_hierarchy(tmp_path / "fresh", stem="fresh")
        (fresh_audio.parent / "fresh_story.json").write_text(
            json.dumps(_fresh_story())
        )

        # No-hierarchy: build the audio + stale story manually (no hierarchy.json).
        nohier_dir = tmp_path / "nohier"
        nohier_dir.mkdir()
        nohier_audio = nohier_dir / "nohier.mp3"
        nohier_audio.write_bytes(b"")
        (nohier_dir / "nohier_story.json").write_text(
            json.dumps(_stale_story_pre_pr84())
        )

        lib_path = tmp_path / "library.json"
        library = Library(index_path=lib_path)
        library.upsert(_make_entry(stale_audio, source_hash="h_stale", title="Stale Song"))
        library.upsert(_make_entry(fresh_audio, source_hash="h_fresh", title="Fresh Song"))
        library.upsert(_make_entry(nohier_audio, source_hash="h_nohier", title="No-Hierarchy"))

        # Patch build_song_story so the test is deterministic and doesn't run
        # the real analyzer pipeline.  The patch lives in src.story.builder
        # (the consumer's import path: src.cli.library imports it inside the
        # function body, so monkeypatching the source module works).
        monkeypatch.setattr(
            "src.story.builder.build_song_story",
            lambda hierarchy, audio_path: _fresh_story(),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["library", "refresh", "--library-path", str(lib_path)])
        assert result.exit_code == 0, result.output

        lines = [ln for ln in result.output.splitlines() if ln.strip()]
        # all_entries() returns newest-first by analyzed_at (all == 1000 here),
        # so we only assert presence of each line, not order.
        assert "[refreshed] Stale Song (missing agreement_score)" in lines
        assert "[skipped: fresh] Fresh Song" in lines
        assert "[skipped: no _hierarchy.json] No-Hierarchy" in lines
        assert "Refreshed 1 / scanned 3" in lines

        # Side effect check: the stale story on disk is now the fresh one.
        refreshed_path = stale_audio.parent / "stale_story.json"
        assert json.loads(refreshed_path.read_text())["song"]["title"] == "Fresh"

    def test_empty_library_prints_message(self, tmp_path):
        lib_path = tmp_path / "library.json"
        # Initialise empty library.
        Library(index_path=lib_path)._save({"version": "1.0", "entries": []})

        runner = CliRunner()
        result = runner.invoke(cli, ["library", "refresh", "--library-path", str(lib_path)])
        assert result.exit_code == 0
        assert "Library is empty" in result.output

    def test_dry_run_reports_would_refresh(self, tmp_path, monkeypatch):
        audio_path = _make_audio_and_hierarchy(tmp_path / "stale", stem="stale")
        (audio_path.parent / "stale_story.json").write_text(
            json.dumps(_stale_story_pre_pr84())
        )

        lib_path = tmp_path / "library.json"
        Library(index_path=lib_path).upsert(
            _make_entry(audio_path, source_hash="h", title="Stale Song")
        )

        # Build is patched to fail loudly if invoked — dry-run must not call it.
        def _must_not_run(*a, **kw):
            raise AssertionError("dry-run must not invoke the builder")
        monkeypatch.setattr("src.story.builder.build_song_story", _must_not_run)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["library", "refresh", "--library-path", str(lib_path), "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "[would-refresh] Stale Song (missing agreement_score)" in result.output
        assert "Refreshed 1 / scanned 1 (dry-run)" in result.output
        # File unchanged.
        story_after = json.loads((audio_path.parent / "stale_story.json").read_text())
        assert story_after["song"]["title"] == "Stale Song"
