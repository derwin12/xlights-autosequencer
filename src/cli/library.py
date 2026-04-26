"""``library`` command group: list and refresh the user's analyzed song library.

The legacy ``xlight-analyze library <DIR>`` command (a directory scanner that
prints a quality table for ``*_hierarchy.json`` files) is preserved as
``library list``. The new ``library refresh`` walks the user's library index
(``~/.xlight/library.json``) and rebuilds stale ``_story.json`` files against
the current story-builder schema.

Staleness is detected by a pluggable list of checks (``STALENESS_CHECKS``).
Each check is a callable ``(story: dict) -> str | None`` that returns a short
reason string when the story is stale, or ``None`` when it passes. Adding a
new check for a future schema bump means appending one function — no other
refactor needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

import click

from src.cli import cli
from src.library import Library, LibraryEntry


# ── Staleness checks ────────────────────────────────────────────────────────────
# Each check inspects an already-loaded ``story`` dict and returns either a
# short reason string (the story is stale) or ``None`` (the story is fresh).
# Add new checks at the end of ``STALENESS_CHECKS`` when the story-builder
# schema gains a new field that older stories silently lack.

StalenessCheck = Callable[[dict], "str | None"]


def _missing_or_zero_agreement_score(story: dict) -> str | None:
    """Stories written before PR #84 lack ``agreement_score`` on every section,
    or have it present but uniformly zero (the placeholder default the field
    held during the WIP window). Either case is the canonical pre-#84 signal.
    """
    sections = story.get("sections") or []
    if not sections:
        return None  # No sections to judge — treat as fresh; other checks may catch.

    any_present = False
    any_nonzero = False
    for sec in sections:
        if "agreement_score" in sec:
            any_present = True
            try:
                if int(sec["agreement_score"]) != 0:
                    any_nonzero = True
                    break
            except (TypeError, ValueError):
                # Non-numeric value also counts as malformed → stale.
                return "agreement_score non-numeric"

    if not any_present:
        return "missing agreement_score"
    if not any_nonzero:
        return "agreement_score all zero"
    return None


def _missing_chorus_ssm_supported(story: dict) -> str | None:
    """Stories written before PR #108 lack ``chorus_ssm_supported`` on Chorus
    sections. The builder always tags Chorus sections (defaulting to True
    when SSM evidence is absent), so any Chorus without the field is stale.
    """
    for sec in story.get("sections") or []:
        if sec.get("role") == "chorus" and "chorus_ssm_supported" not in sec:
            return "missing chorus_ssm_supported"
    return None


# Pluggable list — append new checks here when the story schema bumps.
STALENESS_CHECKS: list[StalenessCheck] = [
    _missing_or_zero_agreement_score,
    _missing_chorus_ssm_supported,
]


def _detect_staleness(story: dict, checks: Iterable[StalenessCheck] = STALENESS_CHECKS) -> str | None:
    """Return the first staleness reason, or ``None`` if the story is fresh."""
    for check in checks:
        reason = check(story)
        if reason is not None:
            return reason
    return None


# ── library command group ──────────────────────────────────────────────────────

@cli.group("library")
def library_group() -> None:
    """Manage the user's analyzed song library."""


# ── library list (legacy ``xlight-analyze library DIR``) ───────────────────────

@library_group.command("list")
@click.argument("directory", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--min-score", default=0.0, type=float, show_default=True,
              help="Only show songs with overall_score >= this value")
@click.option("--flag-below", default=0.6, type=float, show_default=True,
              help="Flag songs with overall_score below this threshold")
@click.option("--sort", "sort_by", default="overall",
              type=click.Choice(["overall", "bars", "beats", "sections", "l4", "name"]),
              show_default=True, help="Sort column")
def library_list_cmd(directory: str, min_score: float, flag_below: float, sort_by: str) -> None:
    """Scan a directory tree for analyzed songs and show a ranked quality table.

    Equivalent to the legacy ``xlight-analyze library DIR``. Finds
    ``*_hierarchy.json`` files (schema 2.0.0) under DIRECTORY and prints
    a table sorted by overall validation score.
    """
    # Delegate to the legacy implementation in cli_old to avoid duplicating
    # ~70 lines of formatting logic. The function reads stdout via click.echo
    # and exits via sys.exit on error — matches the contract callers expect.
    from src.cli_old import library_cmd as _legacy_library_cmd

    ctx = click.get_current_context()
    ctx.invoke(
        _legacy_library_cmd,
        directory=directory,
        min_score=min_score,
        flag_below=flag_below,
        sort_by=sort_by,
    )


# ── library refresh (the new subcommand) ───────────────────────────────────────

@library_group.command("refresh")
@click.option(
    "--library-path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to library index JSON (default: ~/.xlight/library.json).",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Report what would be refreshed without writing any files.",
)
def library_refresh_cmd(library_path: str | None, dry_run: bool) -> None:
    """Walk the library and rebuild stale ``_story.json`` files.

    A story is considered stale when any of the pluggable checks in
    ``STALENESS_CHECKS`` flags it — currently: missing or all-zero
    ``agreement_score`` (pre-#84), and missing ``chorus_ssm_supported`` on
    Chorus sections (pre-#108).

    For each stale story this command re-invokes ``build_song_story`` against
    the cached ``_hierarchy.json``. Songs without a hierarchy file are skipped
    (the builder needs it as input). Reviewed stories are also skipped to
    preserve user edits.
    """
    from src.story.builder import build_song_story, write_song_story

    lib_path = Path(library_path) if library_path else None
    library = Library(index_path=lib_path)
    entries = library.all_entries()

    if not entries:
        click.echo(f"Library is empty: {lib_path or '~/.xlight/library.json'}")
        return

    refreshed = 0
    scanned = 0
    for entry in entries:
        scanned += 1
        slug = _slug_for(entry)
        verdict = _refresh_entry(
            entry,
            dry_run=dry_run,
            build_fn=build_song_story,
            write_fn=write_song_story,
        )

        if verdict.action == "refreshed":
            refreshed += 1
            click.echo(f"[refreshed] {slug} ({verdict.reason})")
        elif verdict.action == "would-refresh":
            refreshed += 1  # Counted as "would have been refreshed" for dry-run summary.
            click.echo(f"[would-refresh] {slug} ({verdict.reason})")
        else:
            click.echo(f"[skipped: {verdict.reason}] {slug}")

    suffix = " (dry-run)" if dry_run else ""
    click.echo(f"Refreshed {refreshed} / scanned {scanned}{suffix}")


# ── Internal: per-entry refresh ────────────────────────────────────────────────

class _Verdict:
    """Outcome of refreshing a single library entry.

    ``action`` is one of: ``refreshed``, ``would-refresh`` (dry-run),
    ``skipped``. ``reason`` is a short human-readable explanation.
    """

    __slots__ = ("action", "reason")

    def __init__(self, action: str, reason: str) -> None:
        self.action = action
        self.reason = reason


def _slug_for(entry: LibraryEntry) -> str:
    """Short label used in command output — title or filename, never a full path."""
    if entry.title:
        return entry.title
    return Path(entry.source_file).stem


def _refresh_entry(
    entry: LibraryEntry,
    *,
    dry_run: bool,
    build_fn,
    write_fn,
) -> _Verdict:
    """Refresh a single library entry's ``_story.json`` if it is stale.

    Returns a ``_Verdict``. Pure with respect to the filesystem when
    ``dry_run=True`` (still reads JSON to detect staleness, but never writes).
    """
    audio_path = Path(entry.source_file)
    story_path = audio_path.parent / (audio_path.stem + "_story.json")
    hierarchy_path = audio_path.parent / (audio_path.stem + "_hierarchy.json")

    if not story_path.exists():
        return _Verdict("skipped", "no _story.json")

    try:
        story = json.loads(story_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _Verdict("skipped", f"unreadable story ({exc.__class__.__name__})")

    # Reviewed stories are user-edited; never overwrite without explicit force.
    if story.get("review", {}).get("status") == "reviewed":
        return _Verdict("skipped", "reviewed (user-edited)")

    reason = _detect_staleness(story)
    if reason is None:
        return _Verdict("skipped", "fresh")

    if not hierarchy_path.exists():
        return _Verdict("skipped", "no _hierarchy.json")

    if dry_run:
        return _Verdict("would-refresh", reason)

    try:
        hierarchy = json.loads(hierarchy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _Verdict("skipped", f"unreadable hierarchy ({exc.__class__.__name__})")

    try:
        new_story = build_fn(hierarchy, str(audio_path))
    except Exception as exc:  # noqa: BLE001 — surface any builder failure as a skip
        return _Verdict("skipped", f"build failed: {exc.__class__.__name__}: {exc}")

    # ``write_song_story`` refuses to overwrite reviewed stories; we already
    # guarded that above, so a FileExistsError here would be a real bug.
    try:
        # Remove the stale file first so write_song_story doesn't see a
        # reviewed-stamp protection (we've already cleared that path above).
        story_path.unlink(missing_ok=True)
        write_fn(new_story, str(story_path))
    except Exception as exc:  # noqa: BLE001
        return _Verdict("skipped", f"write failed: {exc.__class__.__name__}: {exc}")

    return _Verdict("refreshed", reason)
