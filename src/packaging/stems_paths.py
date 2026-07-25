"""Resolve the stem cache root with a writable-fallback.

In dev and CLI use we keep the current convention: stems live under
`<source_parent>/<source_stem>/stems/` (or `<source_parent>/stems/` when
parent directory name already matches the source stem). In packaged mode,
users drop files from locations where the packaged app may not have write
permission (macOS Music/Desktop/iCloud Drive; Windows OneDrive-synced or
Program Files-adjacent folders). When that happens we fall back to the
platform's Application Support root (see platform_paths.py),
`<app_support_root>/stems/<source_stem>/stems/`, so the cache is still
usable and discoverable.

Layout decisions live in `src.analyzer.stems.StemCache.__init__` — this
helper only decides whether to place the cache source-adjacent or in the
Application Support fallback.
"""
from __future__ import annotations

import os
from pathlib import Path

from src.packaging.platform_paths import app_support_root


def _user_fallback_root() -> Path:
    """The Application Support fallback root for stems."""
    return app_support_root() / "stems"


def _writable(directory: Path) -> bool:
    """Return True iff the first existing ancestor of *directory* is writable.

    We never create a test file. If *directory* doesn't exist, walk up
    until we find an ancestor that does, and check its permissions —
    that's where the eventual mkdir() will need to create its first new
    component.
    """
    probe = directory
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            # Walked all the way to root without finding anything — impossible
            # on a real filesystem, but guard against infinite loop.
            return False
        probe = parent
    return os.access(probe, os.W_OK)


def resolve_cache_root(source_path: Path) -> Path:
    """Return the stems root for *source_path*.

    Matches `StemCache.__init__` layout rules exactly:
      - `<parent>/stems/` when parent directory name matches the source stem
      - `<parent>/<source-stem>/stems/` otherwise
    Falls back to Application Support when the preferred location is not
    writable.
    """
    if source_path.parent.name == source_path.stem:
        preferred = source_path.parent / "stems"
    else:
        preferred = source_path.parent / source_path.stem / "stems"

    if _writable(preferred):
        return preferred

    fallback = _user_fallback_root() / source_path.stem / "stems"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback
