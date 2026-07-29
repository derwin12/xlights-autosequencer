import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .paths import library_json_path, library_root

SCHEMA_VERSION = 1


class LibraryCorruptError(Exception):
    pass


def _default_library() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "songs": [],
        "folders": [
            {
                "id": "unfiled",
                "name": "Unfiled",
                "created_at": "2026-04-21T00:00:00Z",
            }
        ],
        "preferences": {
            "mode": "dark",
            "density": "comfortable",
            "inspector_open": True,
            "tweaks_open": False,
            "last_song_id": None,
            "last_screen": "library",
            "last_playhead_ms_by_song": {},
            "layout_id": None,
            "library_state_version": 0,
            "randomness": 0.0,
        },
        "layout": None,
    }


def load_library() -> dict[str, Any]:
    p = library_json_path()
    if not p.exists():
        return _default_library()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LibraryCorruptError(f"library.json is not valid JSON: {exc}") from exc


def save_library(lib: dict[str, Any]) -> None:
    p = library_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(lib, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
