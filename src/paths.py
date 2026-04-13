"""Cross-environment path resolution for the xLights show directory.

The show directory (where xlights_rgbeffects.xml lives) is mounted at
different absolute locations per machine:

  - macOS host:   ~/xLights   or   ~/xlights
  - devcontainer: /home/node/xlights

Paths stored in JSON should be *relative to the show dir* so they work on
every machine without manual path translation.

Module-level helpers (preferred for new code)
---------------------------------------------
get_show_dir()            -> Path | None
to_show_relative(path)    -> str          ("mp3/song.mp3")
resolve_show_path(stored) -> Path         (relative or legacy absolute → absolute)

PathContext class (kept for backwards compatibility)
----------------------------------------------------
PathContext.in_container, .to_relative(), .to_absolute(), .suggest_path()
"""
from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

def get_show_dir() -> Path | None:
    """Return the absolute path to the xLights show directory, or None.

    Resolution order:
    1. XLIGHTS_SHOW_DIR env var (explicit override)
    2. Parent of layout_path in ~/.xlight/settings.json (if it exists)
    3. Well-known candidates: ~/xlights, ~/xLights, /home/node/xlights
    """
    # 1. Explicit env var
    env_val = os.environ.get("XLIGHTS_SHOW_DIR")
    if env_val:
        p = Path(env_val)
        if p.is_dir():
            return p

    # 2. Derive from settings.json — only when layout_path is absolute.
    #    Relative paths in settings are already show-dir-relative, so we can't
    #    resolve them here without knowing the show dir (which is what we're finding).
    try:
        import json
        settings_path = Path.home() / ".xlight" / "settings.json"
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            raw = data.get("layout_path", "")
            if raw:
                p = Path(raw)
                if p.is_absolute() and p.parent.is_dir():
                    return p.parent
    except Exception:
        pass

    # 3. Well-known locations
    for candidate in [
        Path.home() / "xlights",
        Path.home() / "xLights",
        Path("/home/node/xlights"),
    ]:
        if (candidate / "xlights_rgbeffects.xml").exists():
            return candidate

    return None


def to_show_relative(path: str | Path) -> str:
    """Convert an absolute path to a show-dir-relative string.

    Returns the path unchanged (as a string) if it cannot be made relative
    (outside the show dir, or show dir unknown).

    Examples
    --------
    >>> to_show_relative("/home/node/xlights/mp3/song.mp3")
    "mp3/song.mp3"
    >>> to_show_relative("/workspace/src/foo.py")   # outside show dir
    "/workspace/src/foo.py"
    """
    show = get_show_dir()
    if show is None:
        return str(path)
    try:
        return str(Path(path).relative_to(show))
    except ValueError:
        return str(path)


def resolve_show_path(stored: str) -> Path:
    """Resolve a stored path (relative or legacy absolute) to an absolute Path.

    Resolution order:
    1. Absolute path that already exists → return as-is.
    2. Relative path → resolve against current show dir.
    3. Absolute path that doesn't exist → strip the foreign show-dir prefix
       and re-root under the current show dir (cross-env translation).

    The returned path may not exist; callers check existence as needed.
    """
    if not stored:
        return Path(stored)

    p = Path(stored)

    # Fast path: absolute and exists
    if p.is_absolute() and p.exists():
        return p

    show = get_show_dir()

    # Relative: resolve against show dir
    if not p.is_absolute():
        if show is not None:
            return show / p
        return p  # best effort

    # Absolute but missing: try cross-env translation.
    # Drop leading parts of the stored path one by one until the remainder
    # exists under the current show dir.
    # e.g. /Users/rob/xLights/mp3/song.mp3 → show/mp3/song.mp3
    if show is not None:
        parts = p.parts  # ('/', 'Users', 'rob', 'xLights', 'mp3', 'song.mp3')
        for i in range(1, len(parts)):
            candidate = show.joinpath(*parts[i:])
            if candidate.exists():
                return candidate

    return p  # give up — return original; caller handles


# ---------------------------------------------------------------------------
# PathContext class (backwards compatible)
# ---------------------------------------------------------------------------

# Container-side mount point for the xLights show directory (fixed by devcontainer.json)
_CONTAINER_SHOW_DIR: str = "/home/node/xlights"


class PathContext:
    """Encapsulates runtime environment (container vs host) and path mapping.

    Construct once at startup (or use the module-level helpers above).

    The show dir is resolved via ``get_show_dir()`` so this works on both
    the host and inside the dev container.
    """

    def __init__(self) -> None:
        host_show: str = os.environ.get("XLIGHTS_HOST_SHOW_DIR", "").strip()
        self.in_container: bool = bool(host_show)
        self.container_show_dir: str | None = (
            _CONTAINER_SHOW_DIR if self.in_container else None
        )
        self.host_show_dir: str | None = host_show if self.in_container else None

        # Resolved show dir valid in the current environment
        _resolved = get_show_dir()
        self._resolved_show_dir: str | None = str(_resolved) if _resolved else None

    # ── Path helpers ──────────────────────────────────────────────────────────

    def is_in_show_dir(self, path: str | Path) -> bool:
        """Return True if *path* is inside the show directory."""
        show = self._resolved_show_dir
        if not show:
            return False
        return str(path).startswith(show + "/")

    def to_relative(self, path: str | Path) -> str | None:
        """Convert *path* to a show-directory-relative path, or None if not mappable."""
        show = self._resolved_show_dir
        if not show:
            return None
        normalised = os.path.normpath(str(path))
        prefix = show + os.sep
        if not normalised.startswith(prefix):
            return None
        rel = normalised[len(prefix):]
        if ".." in Path(rel).parts:
            return None
        return rel

    def to_absolute(self, relative_path: str) -> str:
        """Convert a show-directory-relative path to absolute in the current environment."""
        show = self._resolved_show_dir
        if not show:
            return relative_path
        return str(Path(show) / relative_path)

    def suggest_path(self, missing_path: str | Path) -> str | None:
        """Return the equivalent path in the current environment for a cross-env path."""
        path_str = os.path.normpath(str(missing_path))
        if self.in_container and self.host_show_dir:
            host_prefix = self.host_show_dir + os.sep
            if path_str.startswith(host_prefix):
                rel = path_str[len(host_prefix):]
                return str(Path(_CONTAINER_SHOW_DIR) / rel)
        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    @property
    def _current_show_dir(self) -> str | None:
        """Show directory path valid in the current environment."""
        return self._resolved_show_dir
