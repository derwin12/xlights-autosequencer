"""Flask blueprint for theme editor CRUD API endpoints."""
from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from src.effects.library import EffectLibrary, load_effect_library
from src.themes.library import ThemeLibrary, load_theme_library
from src.themes.models import VALID_BLEND_MODES, VALID_GENRES, VALID_MOODS, VALID_OCCASIONS
from src.themes.writer import slugify as slugify_name
from src.variants.library import VariantLibrary, load_variant_library

logger = logging.getLogger(__name__)

theme_bp = Blueprint("themes", __name__, url_prefix="/themes")

# Module-level library references (lazy-loaded on first request)
_library: ThemeLibrary | None = None
_effect_library: EffectLibrary | None = None
_variant_library: VariantLibrary | None = None

# Overridable paths (set by tests to use fixtures/tmp dirs)
_custom_dir: str | Path | None = None
_builtin_path: str | Path | None = None

# Paths
_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_CUSTOM_DIR = Path.home() / ".xlight" / "custom_themes"


def _get_custom_dir() -> Path:
    return Path(_custom_dir) if _custom_dir else _DEFAULT_CUSTOM_DIR


def _get_library() -> ThemeLibrary:
    """Return the theme library, loading lazily on first call."""
    global _library
    if _library is None:
        kwargs: dict = {
            "effect_library": _get_effect_library(),
            "variant_library": _get_variant_library(),
        }
        if _builtin_path:
            kwargs["builtin_path"] = _builtin_path
        if _custom_dir:
            kwargs["custom_dir"] = _custom_dir
        _library = load_theme_library(**kwargs)
    return _library


def _get_effect_library() -> EffectLibrary:
    """Return the effect library, loading lazily on first call."""
    global _effect_library
    if _effect_library is None:
        _effect_library = load_effect_library()
    return _effect_library


def _get_variant_library() -> VariantLibrary:
    """Return the variant library, loading lazily on first call."""
    global _variant_library
    if _variant_library is None:
        _variant_library = load_variant_library(effect_library=_get_effect_library())
    return _variant_library


def _reload_library() -> ThemeLibrary:
    """Reload the theme library from disk after a write operation."""
    global _library, _builtin_names_cache
    _builtin_names_cache = None
    kwargs = {
        "effect_library": _get_effect_library(),
        "variant_library": _get_variant_library(),
    }
    if _builtin_path:
        kwargs["builtin_path"] = _builtin_path
    if _custom_dir:
        kwargs["custom_dir"] = _custom_dir
    _library = load_theme_library(**kwargs)
    return _library


def _theme_to_dict(theme, custom_dir: Path, builtin_names: set[str]) -> dict:
    """Serialize a Theme dataclass to a JSON-safe dict with editor flags."""
    d = asdict(theme)
    slug_file = custom_dir / f"{_slugify_name(theme.name)}.json"
    d["is_custom"] = slug_file.exists()
    d["has_builtin_override"] = theme.name in builtin_names and d["is_custom"]
    return d


def _slugify_name(name: str) -> str:
    """Slugify a theme name for file lookup."""
    return slugify_name(name)


_builtin_names_cache: set[str] | None = None


def _get_builtin_names() -> set[str]:
    """Return the set of built-in theme names (cached after first load)."""
    global _builtin_names_cache
    if _builtin_names_cache is not None:
        return _builtin_names_cache
    import json
    path = Path(_builtin_path) if _builtin_path else (Path(__file__).parent.parent / "themes" / "builtin_themes.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _builtin_names_cache = set(raw.get("themes", {}).keys())
    except (OSError, json.JSONDecodeError, KeyError):
        _builtin_names_cache = set()
    return _builtin_names_cache


# ── HTML page route ──────────────────────────────────────────────────────────

@theme_bp.route("/")
def theme_editor_page():
    """Serve the theme editor SPA."""
    return send_from_directory(str(_STATIC_DIR), "theme-editor.html")


# ── API endpoints ────────────────────────────────────────────────────────────

@theme_bp.route("/api/list")
def api_list_themes():
    """Return all themes with metadata and editor flags."""
    lib = _get_library()
    custom_dir = _get_custom_dir()
    builtin_names = _get_builtin_names()

    themes = [
        _theme_to_dict(t, custom_dir, builtin_names)
        for t in lib.themes.values()
    ]

    return jsonify({
        "themes": themes,
        "moods": VALID_MOODS,
        "occasions": VALID_OCCASIONS,
        "genres": VALID_GENRES,
    })


@theme_bp.route("/api/effects")
def api_list_effects():
    """Return all effects with parameters for the layer editor."""
    elib = _get_effect_library()

    effects = []
    for defn in elib.effects.values():
        params = []
        for p in defn.parameters:
            params.append({
                "name": p.name,
                "storage_name": p.storage_name,
                "widget_type": p.widget_type,
                "value_type": p.value_type,
                "default": p.default,
                "min": p.min,
                "max": p.max,
                "choices": p.choices,
            })
        effects.append({
            "name": defn.name,
            "category": defn.category,
            "layer_role": defn.layer_role,
            "parameters": params,
        })

    return jsonify({
        "effects": effects,
        "blend_modes": list(VALID_BLEND_MODES),
    })


@theme_bp.route("/api/save", methods=["POST"])
def api_save_theme():
    """Create or update a custom theme."""
    from src.themes.validator import validate_theme
    from src.themes.writer import save_theme, delete_theme

    body = request.get_json(force=True)
    theme_data = body.get("theme")
    original_name = body.get("original_name")

    if not theme_data or not theme_data.get("name"):
        return jsonify({"error": "Theme data with name is required"}), 400

    name = theme_data["name"]
    lib = _get_library()
    builtin_names = _get_builtin_names()

    # Validate original_name if provided — must be an existing custom file or a built-in being overridden
    if original_name:
        custom_dir = _get_custom_dir()
        orig_slug_file = custom_dir / f"{_slugify_name(original_name)}.json"
        orig_is_builtin = original_name in builtin_names
        if not orig_slug_file.exists() and not orig_is_builtin:
            return jsonify({
                "error": f"Cannot edit '{original_name}': theme not found.",
                "validation_errors": [f"original_name '{original_name}' does not match any existing theme"],
            }), 400

    # Name uniqueness check across ALL themes
    existing = lib.get(name)
    if existing:
        # Allow saving over own name (edit in place) or when renaming
        is_own_name = original_name and original_name.lower() == name.lower()
        if not is_own_name:
            return jsonify({
                "error": f"Theme name '{name}' already exists. Choose a different name.",
                "validation_errors": [f"Name '{name}' conflicts with existing theme"],
            }), 400

    # Structural validation
    elib = _get_effect_library()
    errors = validate_theme(theme_data, elib, _get_variant_library())
    if errors:
        return jsonify({
            "error": "Theme validation failed",
            "validation_errors": errors,
        }), 400

    # If renaming, delete the old file
    if original_name and original_name.lower() != name.lower():
        delete_theme(original_name, custom_dir=_get_custom_dir())

    # Save
    result = save_theme(theme_data, custom_dir=_get_custom_dir())
    if not result["success"]:
        return jsonify({"error": result["error"]}), 500

    _reload_library()

    return jsonify({
        "success": True,
        "theme_name": name,
        "file_path": result["file_path"],
    })


@theme_bp.route("/api/validate", methods=["POST"])
def api_validate_theme():
    """Validate a theme without saving."""
    from src.themes.validator import validate_theme

    body = request.get_json(force=True)
    theme_data = body.get("theme")
    original_name = body.get("original_name")

    if not theme_data:
        return jsonify({"valid": False, "errors": ["No theme data provided"]})

    errors = []

    # Name uniqueness
    name = theme_data.get("name", "")
    if name:
        lib = _get_library()
        existing = lib.get(name)
        if existing:
            is_own_name = original_name and original_name.lower() == name.lower()
            if not is_own_name:
                errors.append(f"Name '{name}' conflicts with existing theme")

    # Structural validation
    elib = _get_effect_library()
    errors.extend(validate_theme(theme_data, elib, _get_variant_library()))

    return jsonify({"valid": len(errors) == 0, "errors": errors})


@theme_bp.route("/api/delete", methods=["POST"])
def api_delete_theme():
    """Delete a custom theme."""
    from src.themes.writer import delete_theme

    body = request.get_json(force=True)
    name = body.get("name", "")

    if not name:
        return jsonify({"error": "Theme name is required"}), 400

    builtin_names = _get_builtin_names()
    custom_dir = _get_custom_dir()
    slug_file = custom_dir / f"{_slugify_name(name)}.json"

    # Check if it's a custom theme (file exists)
    if not slug_file.exists():
        # Could be a built-in only
        if name in builtin_names:
            return jsonify({
                "error": f"Cannot delete built-in theme '{name}'. Only custom themes can be deleted.",
            }), 400
        return jsonify({"error": f"Custom theme '{name}' not found."}), 404

    result = delete_theme(name, custom_dir=custom_dir)
    if not result["success"]:
        return jsonify({"error": result["error"]}), 500

    _reload_library()
    return jsonify({"success": True, "theme_name": name})


@theme_bp.route("/api/restore", methods=["POST"])
def api_restore_theme():
    """Restore a built-in theme by deleting its custom override."""
    from src.themes.writer import delete_theme

    body = request.get_json(force=True)
    name = body.get("name", "")

    if not name:
        return jsonify({"error": "Theme name is required"}), 400

    builtin_names = _get_builtin_names()
    if name not in builtin_names:
        return jsonify({
            "error": f"'{name}' is not a built-in theme. Use delete instead.",
        }), 400

    custom_dir = _get_custom_dir()
    slug_file = custom_dir / f"{_slugify_name(name)}.json"
    if not slug_file.exists():
        return jsonify({
            "error": f"No custom override exists for '{name}'. Nothing to restore.",
        }), 400

    result = delete_theme(name, custom_dir=custom_dir)
    if not result["success"]:
        return jsonify({"error": result["error"]}), 500

    _reload_library()
    return jsonify({
        "success": True,
        "theme_name": name,
        "message": f"Custom override removed. Built-in '{name}' restored.",
    })


@theme_bp.route("/api/effect-pools/<name>")
def api_theme_effect_pools(name):
    """Return the effect_pool configuration per layer for a theme."""
    lib = _get_library()
    theme = lib.get(name)
    if theme is None:
        return jsonify({"error": f"Theme '{name}' not found"}), 404
    layers = []
    for i, layer in enumerate(theme.layers):
        layers.append({
            "index": i,
            "variant": layer.variant,
            "blend_mode": layer.blend_mode,
            "effect_pool": layer.effect_pool,
        })
    return jsonify({"theme": theme.name, "layers": layers})
