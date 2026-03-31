"""PathContext: environment detection and path mapping for devcontainer vs local host.

The dev container mounts the host's xLights show directory at /home/node/xlights/.
The XLIGHTS_HOST_SHOW_DIR environment variable (set in devcontainer.json) carries
the host-side path (e.g. /Users/bob/xlights). Its presence is the signal that we
are running inside the container.

Usage::

    ctx = PathContext()
    if ctx.in_container:
        rel = ctx.to_relative("/home/node/xlights/show/song.mp3")
        # rel == "show/song.mp3"

All methods are side-effect-free and sub-millisecond. PathContext is immutable
after construction.
"""
from __future__ import annotations

import os
from pathlib import Path


# Container-side mount point for the xLights show directory (fixed by devcontainer.json)
_CONTAINER_SHOW_DIR: str = "/home/node/xlights"


class PathContext:
    """Encapsulates runtime environment (container vs host) and path mapping.

    Construct once at startup. Detection is based on the XLIGHTS_HOST_SHOW_DIR
    environment variable:
    - Set (non-empty) → running inside the dev container
    - Absent or empty → running on the host / local machine
    """

    def __init__(self) -> None:
        host_show: str = os.environ.get("XLIGHTS_HOST_SHOW_DIR", "").strip()
        self.in_container: bool = bool(host_show)
        self.container_show_dir: str | None = (
            _CONTAINER_SHOW_DIR if self.in_container else None
        )
        self.host_show_dir: str | None = host_show if self.in_container else None

    # ── Path helpers ──────────────────────────────────────────────────────────

    def is_in_show_dir(self, path: str | Path) -> bool:
        """Return True if *path* is inside the show directory for the current environment."""
        show = self._current_show_dir
        if not show:
            return False
        return str(path).startswith(show + "/")

    def to_relative(self, path: str | Path) -> str | None:
        """Convert *path* to a show-directory-relative path, or None if not mappable.

        The relative path is safe (no leading slash, no ``..`` components).
        The input is normalised via :func:`os.path.normpath` before comparison.
        """
        show = self._current_show_dir
        if not show:
            return None
        normalised = os.path.normpath(str(path))
        prefix = show + os.sep
        if not normalised.startswith(prefix):
            return None
        rel = normalised[len(prefix):]
        # Guard: reject any path that escaped show_dir via ..
        if ".." in Path(rel).parts:
            return None
        return rel

    def to_absolute(self, relative_path: str) -> str:
        """Convert a show-directory-relative path to absolute in the current environment.

        If no show directory is known (local env with no mount), returns *relative_path*
        unchanged so callers can fall back gracefully.
        """
        show = self._current_show_dir
        if not show:
            return relative_path
        return str(Path(show) / relative_path)

    def suggest_path(self, missing_path: str | Path) -> str | None:
        """Return the equivalent path in the current environment for a cross-env path.

        Returns None if no mapping applies (path is not a known cross-env prefix).

        Example (inside container, user typed a host path)::

            ctx.suggest_path("/Users/bob/xlights/show/song.mp3")
            # → "/home/node/xlights/show/song.mp3"
        """
        path_str = os.path.normpath(str(missing_path))
        if self.in_container and self.host_show_dir:
            host_prefix = self.host_show_dir + os.sep
            if path_str.startswith(host_prefix):
                rel = path_str[len(host_prefix):]
                return str(Path(_CONTAINER_SHOW_DIR) / rel)
        # On host: container paths can't be reverse-mapped without knowing host home
        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    @property
    def _current_show_dir(self) -> str | None:
        """Show directory path valid in the current environment."""
        return self.container_show_dir if self.in_container else None
