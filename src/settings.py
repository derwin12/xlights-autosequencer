"""Installation-wide settings stored at ~/.xlight/settings.json."""
from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH: Path = Path.home() / ".xlight" / "settings.json"


def load_settings() -> dict:
    """Read ~/.xlight/settings.json and return its contents as a dict.

    Returns an empty dict if the file is missing or contains invalid JSON.
    """
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(updates: dict) -> None:
    """Merge *updates* into ~/.xlight/settings.json, creating the file if needed.

    ``layout_path`` values are stored show-dir-relative when possible so the
    settings file works across environments (devcontainer ↔ host).
    """
    from src.paths import to_show_relative

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = load_settings()
    if "layout_path" in updates and updates["layout_path"]:
        updates = {**updates, "layout_path": to_show_relative(updates["layout_path"])}
    existing.update(updates)
    SETTINGS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


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
