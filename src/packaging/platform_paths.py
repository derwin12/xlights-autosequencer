"""Cross-platform application-support root for the packaged app.

Single source of truth for where cache-like data (downloaded model weights,
stem separation output fallback) lives outside the small `~/.xlight/` JSON
config directory, so a reinstall or config reset doesn't lose large
re-downloadable/re-derivable assets.

  - macOS:   ~/Library/Application Support/XLight
  - Windows: %LOCALAPPDATA%\\XLight (falls back to ~/AppData/Local/XLight
             if the env var is unset)
  - Linux:   ~/.local/share/XLight
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_support_root() -> Path:
    """Return the platform-appropriate Application Support root for XLight."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "XLight"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        local = Path(base) if base else Path.home() / "AppData" / "Local"
        return local / "XLight"
    return Path.home() / ".local" / "share" / "XLight"
