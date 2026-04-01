"""Write, delete, and rename custom theme JSON files."""
from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CUSTOM_DIR = Path.home() / ".xlight" / "custom_themes"


def slugify(name: str) -> str:
    """Convert a theme name to a filesystem-safe slug.

    Lowercase, replace spaces and special chars with hyphens,
    strip non-alphanumeric except hyphens, collapse multiple hyphens.
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"


def _theme_file_path(name: str, custom_dir: Path) -> Path:
    """Return the expected file path for a theme by name."""
    return custom_dir / f"{slugify(name)}.json"


def save_theme(
    theme_data: dict,
    custom_dir: str | Path | None = None,
) -> dict:
    """Save a theme dict as a JSON file.

    Args:
        theme_data: Complete theme dict (must include 'name').
        custom_dir: Target directory. Defaults to ~/.xlight/custom_themes/.

    Returns:
        Dict with keys: success (bool), theme_name (str),
        file_path (str), error (str|None).
    """
    custom_dir = Path(custom_dir) if custom_dir else _DEFAULT_CUSTOM_DIR
    name = theme_data.get("name", "")

    if not name:
        return {"success": False, "theme_name": "", "file_path": "",
                "error": "Theme name is required"}

    custom_dir.mkdir(parents=True, exist_ok=True)

    target = _theme_file_path(name, custom_dir)

    # Atomic write: write to temp file, then rename
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".json", dir=str(custom_dir), prefix=".tmp_theme_",
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=2, ensure_ascii=False)
            Path(tmp_path).replace(target)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise
    except OSError as exc:
        logger.error("Failed to save theme '%s': %s", name, exc)
        return {"success": False, "theme_name": name,
                "file_path": str(target), "error": str(exc)}

    return {"success": True, "theme_name": name,
            "file_path": str(target), "error": None}


def delete_theme(
    name: str,
    custom_dir: str | Path | None = None,
) -> dict:
    """Delete a custom theme file by name.

    Returns:
        Dict with keys: success (bool), theme_name (str),
        file_path (str), error (str|None).
    """
    custom_dir = Path(custom_dir) if custom_dir else _DEFAULT_CUSTOM_DIR
    target = _theme_file_path(name, custom_dir)

    if not target.exists():
        return {"success": False, "theme_name": name,
                "file_path": str(target),
                "error": f"Custom theme file not found: {target}"}

    try:
        target.unlink()
    except OSError as exc:
        logger.error("Failed to delete theme '%s': %s", name, exc)
        return {"success": False, "theme_name": name,
                "file_path": str(target), "error": str(exc)}

    return {"success": True, "theme_name": name,
            "file_path": str(target), "error": None}


def rename_theme(
    old_name: str,
    new_theme_data: dict,
    custom_dir: str | Path | None = None,
) -> dict:
    """Rename a theme: save new data under new name, delete old file.

    Args:
        old_name: The previous theme name (to delete).
        new_theme_data: Complete theme dict with the new name.
        custom_dir: Target directory.

    Returns:
        Dict with keys: success (bool), theme_name (str),
        file_path (str), error (str|None).
    """
    custom_dir = Path(custom_dir) if custom_dir else _DEFAULT_CUSTOM_DIR

    # Save the new file first
    result = save_theme(new_theme_data, custom_dir=custom_dir)
    if not result["success"]:
        return result

    # Delete the old file (only if name actually changed)
    new_name = new_theme_data.get("name", "")
    if slugify(old_name) != slugify(new_name):
        delete_result = delete_theme(old_name, custom_dir=custom_dir)
        if not delete_result["success"]:
            logger.warning(
                "Saved new theme '%s' but failed to delete old '%s': %s",
                new_name, old_name, delete_result["error"],
            )

    return result
