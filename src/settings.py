"""Installation-wide settings stored at ~/.xlight/settings.json."""
from __future__ import annotations

import json
import os
from pathlib import Path


SETTINGS_PATH: Path = Path.home() / ".xlight" / "settings.json"


def _settings_path() -> Path:
    """Return the settings file path, honoring XLIGHT_STATE_HOME for test isolation.

    Checked fresh on every call (not cached at import time) so a test that sets
    XLIGHT_STATE_HOME via monkeypatch is isolated even though src.settings was
    already imported. Falls back to the module-level SETTINGS_PATH (also
    patchable directly, e.g. via unittest.mock.patch) when the env var is unset.
    """
    override = os.environ.get("XLIGHT_STATE_HOME")
    return Path(override) / "settings.json" if override else SETTINGS_PATH


def load_settings() -> dict:
    """Read ~/.xlight/settings.json and return its contents as a dict.

    Returns an empty dict if the file is missing or contains invalid JSON.
    """
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(updates: dict) -> None:
    """Merge *updates* into ~/.xlight/settings.json, creating the file if needed.

    ``layout_path`` values are stored show-dir-relative when possible so the
    settings file works across environments (devcontainer ↔ host).
    """
    from src.paths import to_show_relative

    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_settings()
    if "layout_path" in updates and updates["layout_path"]:
        updates = {**updates, "layout_path": to_show_relative(updates["layout_path"])}
    existing.update(updates)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def get_layout_path() -> Path | None:
    """Return the configured layout path as an absolute Path, or None if not set.

    Resolves show-dir-relative paths (new format) and translates legacy
    absolute paths from other environments via ``resolve_show_path``.
    """
    from src.paths import resolve_show_path

    value = load_settings().get("layout_path")
    if not value:
        return None
    resolved = resolve_show_path(value)
    return resolved if resolved.exists() else resolved
