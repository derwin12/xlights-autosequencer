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


@api_v1.get("/manifest")
def manifest():
    m = get_manifest()
    if m is not None:
        m.setdefault("backend_started_at", _SERVER_STARTED_AT)
        return jsonify(m)
    # Dev stub — frontend still uses this to render the About dialog.
    return jsonify({
        "app_version": "dev",
        "build_timestamp": None,
        "target_arch": None,
        "frontend_commit": None,
        "backend_commit": _BACKEND_COMMIT,
        "backend_started_at": _SERVER_STARTED_AT,
        "bundled_vamp_plugins": [],
        "download_model_manifest_url": None,
        "is_bundled": is_bundled(),
    })
