"""GET /api/v1/themes — theme catalog loaded from the real theme library (T041)."""
from __future__ import annotations

import json
import pathlib
import re

from flask import jsonify, request

from . import api_v1
from src.review.storage.assignments import load_session
from src.review.storage.library import load_library
from src.themes.library import DEFAULT_THEME_LAYERS

_BUILTIN_THEMES_PATH = pathlib.Path(__file__).parents[3] / "themes" / "builtin_themes.json"
_CUSTOM_THEMES_DIR = pathlib.Path.home() / ".xlight" / "custom_themes"

_SCHEMA_VERSION = 1

# See src.themes.library.DEFAULT_THEME_LAYERS for why: themes created via
# this screen's dialog have no layer/effect picker, so a saved theme with no
# layers would otherwise be silently dropped by the real generator.
_DEFAULT_THEME_LAYERS = DEFAULT_THEME_LAYERS

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


def _is_builtin_theme_id(theme_id: str) -> bool:
    if not _BUILTIN_THEMES_PATH.exists():
        return False
    try:
        raw = json.loads(_BUILTIN_THEMES_PATH.read_text(encoding="utf-8"))
        return theme_id in {_slugify(n) for n in raw.get("themes", {})}
    except Exception:
        return False


def _theme_to_api(
    raw: dict, theme_id: str, editable: bool = False, validation_errors: list[str] | None = None,
) -> dict:
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
        "validation_errors": validation_errors or [],
    }
    return result


def _validate_custom_theme(raw: dict) -> list[str]:
    """Errors that would make the real generator silently drop this theme.

    Runs the exact same check src.themes.library.load_theme_library() runs
    before adding a custom theme to the generator's catalog -- a theme that
    fails this looks completely normal in the Theme screen (assignable,
    has swatches) but is silently skipped (a logger.warning, never surfaced
    to the user) the moment a real export runs (user report 2026-08-03: a
    theme assigned to a section didn't show up in the exported .xsq's
    "Themes" diagnostic track at all). Applies the same layers backfill
    load_theme_library() applies, so a theme this dialog can't add a real
    layer to doesn't show a scary warning for something the generator will
    actually heal transparently.
    """
    from src.effects.library import load_effect_library
    from src.themes.validator import validate_theme
    from src.variants.library import load_variant_library

    if not raw.get("layers"):
        raw = {**raw, "layers": _DEFAULT_THEME_LAYERS}

    effect_library = load_effect_library()
    variant_library = load_variant_library(effect_library=effect_library)
    return validate_theme(raw, effect_library, variant_library)


def _load_themes() -> list[dict]:
    themes: list[dict] = []

    # Built-in themes (read-only) -- assumed already valid (covered by the
    # repo's own test suite), so skip the validation pass for these.
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
                errors = _validate_custom_theme(entry)
                themes.append(_theme_to_api(entry, theme_id, editable=True, validation_errors=errors))
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
    if _is_builtin_theme_id(theme_id):
        return jsonify({"error": {"message": "Built-in themes are read-only"}}), 403

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

    # Backfill a working default layer for themes saved before this dialog
    # generated one automatically (see _DEFAULT_THEME_LAYERS above) -- an
    # empty-layers theme edited and re-saved here should come out fixed,
    # not still silently inert.
    if not existing.get("layers"):
        existing["layers"] = _DEFAULT_THEME_LAYERS

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
        "layers": body.get("layers") or _DEFAULT_THEME_LAYERS,
        "alternates": body.get("alternates", []),
        "palette": body.get("palette", []),
        "accent_palette": body.get("accent_palette", []),
    }
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"theme": _theme_to_api(entry, theme_id, editable=True)}), 201


def _songs_using_theme(theme_id: str) -> list[str]:
    """Titles of songs whose saved section assignments still reference theme_id."""
    lib = load_library()
    titles = []
    for song in lib["songs"]:
        session = load_session(song["song_id"])
        if not session:
            continue
        if any(a.get("theme_id") == theme_id for a in session.get("assignments", [])):
            titles.append(song.get("title") or song["song_id"])
    return titles


@api_v1.route("/themes/<theme_id>", methods=["DELETE"])
def delete_theme(theme_id: str):
    """Delete a custom theme. Built-in themes are read-only; a theme still
    assigned to any song's sections can't be deleted (would leave a dangling
    theme_id reference) until it's unassigned there first.
    """
    if _is_builtin_theme_id(theme_id):
        return jsonify({"error": {"message": "Built-in themes are read-only"}}), 403

    path = _CUSTOM_THEMES_DIR / f"{theme_id}.json"
    if not path.exists():
        return jsonify({"error": {"message": "Theme not found"}}), 404

    in_use = _songs_using_theme(theme_id)
    if in_use:
        return jsonify({"error": {
            "code": "theme_in_use",
            "message": f"Theme is still assigned in: {', '.join(in_use)}. Unassign it there first.",
        }}), 409

    path.unlink()
    return jsonify({"theme_id": theme_id}), 200
