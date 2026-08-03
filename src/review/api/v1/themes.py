"""GET /api/v1/themes — theme catalog loaded from the real theme library (T041)."""
from __future__ import annotations

import json
import pathlib
import re

from flask import jsonify, request

from src.review.ai_palette import suggest_palette
from src.review.storage.library import load_library
from src.settings import load_settings

from . import api_v1

_DEFAULT_OLLAMA_HOST = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "qwen3:8b"

_BUILTIN_THEMES_PATH = pathlib.Path(__file__).parents[3] / "themes" / "builtin_themes.json"
_CUSTOM_THEMES_DIR = pathlib.Path.home() / ".xlight" / "custom_themes"

_SCHEMA_VERSION = 1

# mood → section kinds for default_for_kinds (FR-012a)
_MOOD_KINDS: dict[str, list[str]] = {
    "ethereal": ["intro", "outro"],
    "aggressive": ["chorus", "drop"],
    "dark": ["verse", "bridge"],
    "structural": ["verse", "chorus"],
}
_OCCASION_KINDS: dict[str, list[str]] = {
    "christmas": ["intro", "verse", "chorus", "outro"],
    "halloween": ["verse", "chorus", "bridge"],
}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _theme_to_api(raw: dict, theme_id: str, editable: bool = False) -> dict:
    """Map internal theme schema → frontend API shape."""
    mood = raw.get("mood", "structural")
    occasion = raw.get("occasion", "general")
    if occasion != "general":
        kinds = _OCCASION_KINDS.get(occasion, ["unknown"])
    else:
        kinds = _MOOD_KINDS.get(mood, ["unknown"])

    palette: list[str] = raw.get("palette", [])
    accent_palette: list[str] = raw.get("accent_palette", [])
    accent = accent_palette[0] if accent_palette else (palette[0] if palette else "#ffffff")
    # Every distinct color the theme actually uses, deduped -- NOT capped at
    # 5 (bug found 2026-07-28, user report: "The Void"'s theme-browser card
    # showed only its palette + accent_palette[0], silently truncating off
    # accent_palette[1:] -- 4 mismatched red accent colors were fully
    # active in generated sequences but invisible in this preview the whole
    # time, since palette alone already used up 4 of the old 5-slot cap).
    swatches = list(dict.fromkeys(palette + accent_palette))

    result: dict = {
        "theme_id": theme_id,
        "name": raw.get("name", theme_id),
        "description": raw.get("intent", ""),
        "accent": accent,
        "swatches": swatches,
        "default_for_kinds": kinds,
        "mood": mood,
        "occasion": occasion,
        "genre": raw.get("genre", "any"),
        "editable": editable,
    }
    return result


def _load_themes() -> list[dict]:
    themes: list[dict] = []

    # Built-in themes (read-only)
    if _BUILTIN_THEMES_PATH.exists():
        try:
            raw = json.loads(_BUILTIN_THEMES_PATH.read_text(encoding="utf-8"))
            for name, entry in raw.get("themes", {}).items():
                themes.append(_theme_to_api(entry, _slugify(name), editable=False))
        except Exception:
            pass

    # Custom themes (editable)
    if _CUSTOM_THEMES_DIR.exists():
        for path in sorted(_CUSTOM_THEMES_DIR.glob("*.json")):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                theme_id = path.stem
                themes.append(_theme_to_api(entry, theme_id, editable=True))
            except Exception:
                pass

    return themes


@api_v1.route("/themes", methods=["GET"])
def get_themes():
    return jsonify({
        "schema_version": _SCHEMA_VERSION,
        "themes": _load_themes(),
    }), 200


@api_v1.route("/themes/<theme_id>", methods=["PUT"])
def update_theme(theme_id: str):
    """Update a custom theme. Built-in themes are read-only."""
    # Verify it's not a built-in
    if _BUILTIN_THEMES_PATH.exists():
        try:
            raw = json.loads(_BUILTIN_THEMES_PATH.read_text(encoding="utf-8"))
            builtin_ids = {_slugify(n) for n in raw.get("themes", {})}
            if theme_id in builtin_ids:
                return jsonify({"error": {"message": "Built-in themes are read-only"}}), 403
        except Exception:
            pass

    _CUSTOM_THEMES_DIR.mkdir(parents=True, exist_ok=True)
    path = _CUSTOM_THEMES_DIR / f"{theme_id}.json"
    if not path.exists():
        return jsonify({"error": {"message": "Theme not found"}}), 404

    body = request.get_json(silent=True) or {}
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        existing = {}

    # Merge allowed fields
    for field in ("name", "intent", "mood", "occasion", "genre", "palette", "accent_palette"):
        if field in body:
            existing[field] = body[field]

    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"theme": _theme_to_api(existing, theme_id, editable=True)}), 200


@api_v1.route("/themes", methods=["POST"])
def create_theme():
    """Create a new custom theme."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": {"message": "name is required"}}), 400

    theme_id = _slugify(name)
    _CUSTOM_THEMES_DIR.mkdir(parents=True, exist_ok=True)
    path = _CUSTOM_THEMES_DIR / f"{theme_id}.json"
    if path.exists():
        return jsonify({"error": {"message": "Theme ID already exists"}}), 409

    entry: dict = {
        "name": name,
        "mood": body.get("mood", "structural"),
        "occasion": body.get("occasion", "general"),
        "genre": body.get("genre", "any"),
        "intent": body.get("intent", body.get("description", "")),
        "layers": body.get("layers", []),
        "alternates": body.get("alternates", []),
        "palette": body.get("palette", []),
        "accent_palette": body.get("accent_palette", []),
    }
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"theme": _theme_to_api(entry, theme_id, editable=True)}), 201


@api_v1.route("/songs/<song_id>/theme-suggest-palette", methods=["POST"])
def suggest_theme_palette(song_id: str):
    """AI-suggest a 4-color palette for a song, via a local Ollama model.

    See openspec/changes/theme-ai-palette-suggest. Genre/occasion come from
    the request body (the theme editor's current in-progress values, not
    necessarily the song's saved genre) so a suggestion reflects whatever
    the user is actively editing. Returns 200 with an error payload (not a
    4xx) when the AI call fails -- this is an expected, non-exceptional
    outcome the frontend handles gracefully, not a request error.
    """
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found", "message": "Song not found"}}), 404

    body = request.get_json(silent=True) or {}
    settings = load_settings()

    palette = suggest_palette(
        title=song.get("title") or "",
        artist=song.get("artist") or "",
        genre=body.get("genre") or "",
        occasion=body.get("occasion") or "general",
        ollama_host=settings.get("ollama_host", _DEFAULT_OLLAMA_HOST),
        ollama_model=settings.get("ollama_model", _DEFAULT_OLLAMA_MODEL),
    )
    if palette is None:
        return jsonify({"error": {
            "code": "ai_unavailable",
            "message": "AI suggestion unavailable — check Ollama is running",
        }}), 200

    return jsonify({"palette": palette}), 200
