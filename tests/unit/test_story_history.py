"""Unit tests for per-song _story.json history archive.

Covers:
- write_song_story archives the previous version on overwrite
- retention cap honors XLIGHT_STORY_HISTORY_MAX env var
- list_story_history / resolve_history_entry helpers
- xlight-analyze story-history and story-diff CLI commands
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.story.builder import (
    DEFAULT_STORY_HISTORY_MAX,
    _story_history_dir,
    list_story_history,
    resolve_history_entry,
    write_song_story,
)
from src.cli import cli


def _story(n_sections: int = 3, *, marker: str = "v1") -> dict:
    """Build a small valid story dict with N sections and a marker label."""
    return {
        "schema_version": "1.0.0",
        "audio_path": "fixture.mp3",
        "review": {"status": "draft"},
        "sections": [
            {
                "id": f"s{i:02d}",
                "role": "verse" if i % 2 == 0 else "chorus",
                "start_ms": i * 10_000,
                "end_ms": (i + 1) * 10_000,
                "label": f"{marker}-{i}",
                "agreement_score": 0.5 + 0.1 * i,
                "chorus_ssm_supported": (i == 1),
                "source": "heuristic",
            }
            for i in range(n_sections)
        ],
        "moments": [],
        "stems": {"sample_rate_hz": 2},
    }


# ── Archive-on-overwrite ───────────────────────────────────────────────────────

def test_first_write_creates_no_history(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    assert p.exists()
    assert _story_history_dir(p).exists() is False


def test_second_write_archives_previous_version(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    write_song_story(_story(marker="v2"), str(p))

    history = list_story_history(p)
    assert len(history) == 1, f"expected exactly 1 archived snapshot, got {history}"

    archived = json.loads(history[0].read_text(encoding="utf-8"))
    assert archived["sections"][0]["label"] == "v1-0", (
        "archived snapshot should hold the old version's content"
    )

    current = json.loads(p.read_text(encoding="utf-8"))
    assert current["sections"][0]["label"] == "v2-0"


def test_archive_filename_is_iso_timestamped(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    write_song_story(_story(marker="v2"), str(p))

    history = list_story_history(p)
    name = history[0].name
    # e.g. 2026-04-25T19-24-31Z.json
    assert name.endswith("Z.json"), f"unexpected archive name format: {name}"
    assert name[4] == "-" and name[7] == "-", f"missing date separators: {name}"


def test_rapid_overwrites_avoid_collisions(tmp_path: Path) -> None:
    """Two overwrites in the same second must not stomp on each other."""
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    write_song_story(_story(marker="v2"), str(p))
    write_song_story(_story(marker="v3"), str(p))

    history = list_story_history(p)
    assert len(history) == 2, f"expected 2 archives for 3 writes, got {history}"
    # Names must be unique
    assert len({h.name for h in history}) == 2


# ── Retention cap ──────────────────────────────────────────────────────────────

def test_retention_cap_keeps_only_n_most_recent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XLIGHT_STORY_HISTORY_MAX", "3")
    p = tmp_path / "song_story.json"

    # Write N+1 distinct versions (4 archives expected before pruning, 3 after).
    for i in range(5):
        write_song_story(_story(marker=f"v{i}"), str(p))
        # Force unique seconds so name-sort matches creation order.
        time.sleep(1.05)

    history = list_story_history(p)
    assert len(history) == 3, f"expected exactly 3 entries, got {len(history)}"

    # The kept entries must be the most recent: their content must be v1, v2, v3
    # (v0 archived first → pruned; v4 is the live file).
    labels = [
        json.loads(h.read_text(encoding="utf-8"))["sections"][0]["label"]
        for h in history
    ]
    assert labels == ["v1-0", "v2-0", "v3-0"], labels


def test_default_retention_used_when_env_unset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("XLIGHT_STORY_HISTORY_MAX", raising=False)
    assert DEFAULT_STORY_HISTORY_MAX == 5


def test_invalid_env_falls_back_to_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XLIGHT_STORY_HISTORY_MAX", "not-a-number")
    p = tmp_path / "song_story.json"
    # Should not raise — just use the default.
    write_song_story(_story(marker="v1"), str(p))
    write_song_story(_story(marker="v2"), str(p))
    assert len(list_story_history(p)) == 1


# ── resolve_history_entry ──────────────────────────────────────────────────────

def test_resolve_history_entry_current(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    assert resolve_history_entry(p, "current") == p


def test_resolve_history_entry_by_prefix(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    write_song_story(_story(marker="v2"), str(p))
    history = list_story_history(p)
    prefix = history[0].stem[:10]  # "YYYY-MM-DD"
    resolved = resolve_history_entry(p, prefix)
    assert resolved == history[0]


def test_resolve_history_entry_missing_raises(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    with pytest.raises(FileNotFoundError):
        resolve_history_entry(p, "1999-01-01")


def test_resolve_history_entry_ambiguous_raises(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))
    write_song_story(_story(marker="v2"), str(p))
    write_song_story(_story(marker="v3"), str(p))
    history = list_story_history(p)
    if len(history) < 2:
        pytest.fail("test setup should produce >= 2 archives")
    common_prefix = history[0].name[:4]  # "YYYY"
    with pytest.raises(ValueError):
        resolve_history_entry(p, common_prefix)


# ── CLI: story-history ─────────────────────────────────────────────────────────

def test_cli_story_history_zero_entries(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    runner = CliRunner()
    result = runner.invoke(cli, ["story-history", str(p)])
    assert result.exit_code == 0, result.output
    assert "No story history" in result.output


def test_cli_story_history_one_entry(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(n_sections=4, marker="v1"), str(p))
    write_song_story(_story(n_sections=5, marker="v2"), str(p))
    runner = CliRunner()
    result = runner.invoke(cli, ["story-history", str(p)])
    assert result.exit_code == 0, result.output
    # one archive (v1, 4 sections) + current (v2, 5 sections)
    assert "4 sections" in result.output
    assert "5 sections" in result.output
    assert "current" in result.output


def test_cli_story_history_three_entries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XLIGHT_STORY_HISTORY_MAX", "10")
    p = tmp_path / "song_story.json"
    for i in range(4):
        write_song_story(_story(n_sections=i + 1, marker=f"v{i}"), str(p))
        time.sleep(1.05)

    runner = CliRunner()
    result = runner.invoke(cli, ["story-history", str(p)])
    assert result.exit_code == 0, result.output
    # 3 archives (v0/1s, v1/2s, v2/3s) + current (v3/4s)
    for label in ("1 sections", "2 sections", "3 sections", "4 sections"):
        assert label in result.output, f"missing {label!r} in: {result.output}"


# ── CLI: story-diff ────────────────────────────────────────────────────────────

def test_cli_story_diff_reports_section_changes(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    s1 = _story(n_sections=3, marker="v1")
    s2 = _story(n_sections=3, marker="v2")
    # Mutate one field on a known section so the diff has something to report.
    s2["sections"][1]["role"] = "bridge"
    s2["sections"][1]["agreement_score"] = 0.99

    write_song_story(s1, str(p))
    write_song_story(s2, str(p))

    history = list_story_history(p)
    prefix = history[0].stem[:10]

    runner = CliRunner()
    result = runner.invoke(
        cli, ["story-diff", str(p), "--from", prefix, "--to", "current"]
    )
    assert result.exit_code == 0, result.output
    assert "s01" in result.output
    assert "role" in result.output
    assert "bridge" in result.output
    assert "agreement_score" in result.output


def test_cli_story_diff_reports_added_and_removed(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(n_sections=3, marker="v1"), str(p))
    write_song_story(_story(n_sections=5, marker="v2"), str(p))

    history = list_story_history(p)
    prefix = history[0].stem[:10]

    runner = CliRunner()
    result = runner.invoke(
        cli, ["story-diff", str(p), "--from", prefix, "--to", "current"]
    )
    assert result.exit_code == 0, result.output
    assert "s03" in result.output and "s04" in result.output
    assert "added" in result.output


def test_cli_story_diff_missing_revision_errors(tmp_path: Path) -> None:
    p = tmp_path / "song_story.json"
    write_song_story(_story(marker="v1"), str(p))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["story-diff", str(p), "--from", "1999-01-01", "--to", "current"]
    )
    assert result.exit_code != 0
    assert "ERROR" in result.output or "ERROR" in (result.stderr or "")
