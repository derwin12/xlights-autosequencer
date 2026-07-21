"""GET /api/v1/manifest — package build metadata.

In bundled mode, returns the contents of the Contents/Resources/
packaging-manifest.json shipped with the .app. In dev mode, returns a
stub indicating dev build, enriched with the git commit of the checkout
this server process is running from so the UI can show whether the
backend is up to date (a restarted-vs-stale server is otherwise
invisible — the header build stamp only covers the frontend bundle).
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify

from src.packaging.bundled_mode import get_manifest, is_bundled
from src.review.api.v1 import api_v1

# Captured at import (= process start). The commit is deliberately NOT
# re-read per request: modules are loaded once, so the value at import
# time describes the code this process actually runs — committing or
# pulling afterwards changes the repo but not the loaded code, and the
# stale stamp in the UI is exactly the signal this exists to provide.
_SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _backend_commit() -> str | None:
    """Short HEAD hash of this file's checkout, '-dirty' suffixed when the
    working tree has uncommitted tracked changes. None outside a git repo
    (e.g. bundled builds, where the packaging manifest is used instead)."""
    cwd = Path(__file__).resolve().parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=cwd, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        # The dirty check walks the whole working tree, which can exceed the
        # timeout on bind-mounted repos (devcontainer over a Windows drive).
        # It only refines the label — never let it cost us the commit itself.
        status = ""
    return f"{commit}-dirty" if status else commit


_BACKEND_COMMIT = _backend_commit()

# Most Docker deployments never restart the process on every request, so
# repo_head_commit (a free local `git rev-parse`) already catches "pulled
# but forgot to restart." It can't catch "haven't pulled yet" -- that needs
# a network round-trip to the remote, so it's cached separately from the
# free local checks above.
_ORIGIN_CHECK_TTL_SECONDS = 30 * 60
_origin_main_commit_cache: str | None = None
_origin_ahead_cache: bool | None = None
_origin_main_checked_at: float = 0.0


def _refresh_origin_main_state() -> None:
    """Fetches origin/main and updates both the cached SHA and whether it's
    strictly ahead of HEAD.

    A plain SHA comparison (the previous implementation, via `git
    ls-remote`) can't distinguish "origin is ahead -- pull to update" from
    "HEAD is ahead of origin -- committed locally but not pushed yet": both
    just produce two different SHAs. `git fetch` (unlike `ls-remote`) pulls
    the actual commit objects into FETCH_HEAD, which lets a local
    `git rev-list --count HEAD..FETCH_HEAD` answer the real question --
    the count is 0 both when the two are equal and when HEAD is ahead
    (nothing reachable from FETCH_HEAD that isn't already reachable from
    HEAD), and only positive when origin genuinely has commits this
    checkout doesn't (a plain `--is-ancestor` check was tried first but
    rejected: it treats a commit as an ancestor of itself, so it can't
    distinguish "equal" from "strictly ahead" on its own). `git fetch` only
    updates FETCH_HEAD (not any local branch ref), so it can't disturb the
    user's own working tree or branch state. Never raises: offline dev
    environments, corporate proxies, or a missing remote must not break the
    manifest endpoint -- a transient failure keeps serving the last
    known-good values instead of clearing them.
    """
    global _origin_main_commit_cache, _origin_ahead_cache, _origin_main_checked_at
    now = time.monotonic()
    if _origin_main_checked_at > 0 and (now - _origin_main_checked_at) < _ORIGIN_CHECK_TTL_SECONDS:
        return
    _origin_main_checked_at = now
    cwd = Path(__file__).resolve().parent
    try:
        subprocess.run(
            ["git", "fetch", "--quiet", "origin", "main"],
            cwd=cwd, capture_output=True, text=True, timeout=15, check=True,
        )
        origin_sha = subprocess.run(
            ["git", "rev-parse", "--short", "FETCH_HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        if origin_sha:
            _origin_main_commit_cache = origin_sha
        ahead_count = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..FETCH_HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        _origin_ahead_cache = ahead_count.isdigit() and int(ahead_count) > 0
    except (OSError, subprocess.SubprocessError):
        pass


def _origin_main_commit() -> str | None:
    """Short SHA of origin/main, cached for _ORIGIN_CHECK_TTL_SECONDS."""
    _refresh_origin_main_state()
    return _origin_main_commit_cache


def _origin_ahead_of_head() -> bool | None:
    """True when origin/main is strictly ahead of this checkout's HEAD --
    i.e. a `git pull` would bring in new commits. False when HEAD is even
    with or ahead of origin/main (including "committed locally, not pushed
    yet" -- a different SHA that is NOT a case for pulling). None when the
    remote couldn't be reached at all."""
    _refresh_origin_main_state()
    return _origin_ahead_cache


@api_v1.get("/manifest")
def manifest():
    m = get_manifest()
    if m is not None:
        m.setdefault("backend_started_at", _SERVER_STARTED_AT)
        return jsonify(m)
    # Dev stub — frontend still uses this to render the About dialog.
    # repo_head_commit is read FRESH on every request (unlike
    # backend_commit, cached once at process start) so the UI can detect
    # "code was committed/pulled since this process launched" -- the
    # exact confusion that kept recurring when checking whether a restart
    # actually picked up the latest change (user request, 2026-07-18).
    return jsonify({
        "app_version": "dev",
        "build_timestamp": None,
        "target_arch": None,
        "frontend_commit": None,
        "backend_commit": _BACKEND_COMMIT,
        "repo_head_commit": _backend_commit(),
        "origin_main_commit": _origin_main_commit(),
        "origin_ahead_of_head": _origin_ahead_of_head(),
        "backend_started_at": _SERVER_STARTED_AT,
        "bundled_vamp_plugins": [],
        "download_model_manifest_url": None,
        "is_bundled": is_bundled(),
    })
