"""Flask blueprint for the variant library browse API."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, jsonify, request

from src.effects.library import EffectLibrary, load_effect_library
from src.variants.library import VariantLibrary, load_variant_library
from src.variants.scorer import ScoringContext, rank_variants_with_fallback

logger = logging.getLogger(__name__)

variant_bp = Blueprint("variants", __name__, url_prefix="/variants")

# Module-level library references — lazy-loaded on first request.
# Tests override these directly before calling create_app().
_library: VariantLibrary | None = None
_effect_library: EffectLibrary | None = None
_custom_dir: str | Path | None = None
_builtin_path: str | Path | None = None

_DEFAULT_CUSTOM_DIR = Path.home() / ".xlight" / "custom_variants"


def _get_custom_dir() -> Path:
    return Path(_custom_dir) if _custom_dir else _DEFAULT_CUSTOM_DIR


def _get_effect_library() -> EffectLibrary:
    global _effect_library
    if _effect_library is None:
        _effect_library = load_effect_library()
    return _effect_library


def _get_library() -> VariantLibrary:
    global _library
    if _library is None:
        kwargs: dict = {"effect_library": _get_effect_library()}
        if _builtin_path:
            kwargs["builtin_path"] = _builtin_path
        if _custom_dir:
            kwargs["custom_dir"] = _custom_dir
        _library = load_variant_library(**kwargs)
    return _library


def _get_builtin_names() -> set[str]:
    return _get_library().builtin_names


def _variant_to_dict(variant, is_builtin: bool, effect_library: EffectLibrary) -> dict:
    """Serialize a variant to a JSON-safe dict, adding is_builtin and inherited base effect info."""
    d = variant.to_dict()
    d["is_builtin"] = is_builtin
    base_defn = effect_library.get(variant.base_effect)
    if base_defn:
        d["inherited"] = {
            "category": base_defn.category,
            "layer_role": base_defn.layer_role,
            "duration_type": base_defn.duration_type,
            "prop_suitability": base_defn.prop_suitability,
        }
    else:
        d["inherited"] = None
    return d


# ── Routes ───────────────────────────────────────────────────────────────────
# NOTE: static routes (/query, /coverage) must be declared before /<path:name>
# so Flask routes them as static segments rather than matching the dynamic param.


@variant_bp.route("/", methods=["GET"])
def variant_browser_or_list():
    """Serve the browser page for HTML requests, or list variants for JSON/API requests.

    If the request has query params (effect, energy, tier, section, scope, q)
    or accepts JSON, serve the API response. Otherwise serve the HTML page.
    """
    # API requests: have filter params, or explicitly accept JSON
    has_filters = any(request.args.get(k) for k in ("effect", "energy", "tier", "section", "scope", "q"))
    wants_json = "application/json" in (request.accept_mimetypes.best or "")
    if has_filters or wants_json:
        return _list_variants_json()
    # Browser navigation: serve the HTML page
    from flask import send_from_directory
    static_dir = Path(__file__).parent / "static"
    return send_from_directory(static_dir, "variant-library.html")


@variant_bp.route("", methods=["GET"])
def list_variants():
    """List all variants with optional filtering and free-text search.

    Query params: effect, energy, tier, section, scope, q (free-text)
    """
    return _list_variants_json()


def _list_variants_json():
    """Shared implementation for listing variants as JSON."""
    lib = _get_library()
    elib = _get_effect_library()
    builtin_names = _get_builtin_names()

    effect = request.args.get("effect") or None
    energy = request.args.get("energy") or None
    tier = request.args.get("tier") or None
    section = request.args.get("section") or None
    scope = request.args.get("scope") or None
    q = (request.args.get("q") or "").lower().strip()

    results = lib.query(
        base_effect=effect,
        energy_level=energy,
        tier_affinity=tier,
        scope=scope,
        section_role=section,
    )

    if q:
        results = [
            v for v in results
            if q in v.name.lower() or q in v.description.lower()
        ]

    filters_applied = {
        k: v for k, v in {
            "effect": effect,
            "energy": energy,
            "tier": tier,
            "section": section,
            "scope": scope,
            "q": q or None,
        }.items()
        if v is not None
    }

    return jsonify({
        "variants": [
            _variant_to_dict(v, v.name in builtin_names, elib)
            for v in results
        ],
        "total": len(results),
        "filters_applied": filters_applied,
    })


@variant_bp.route("/query", methods=["POST"])
def query_variants():
    """Score and rank variants by a placement context.

    Body (JSON): ScoringContext fields (all optional):
        base_effect, prop_type, energy_level, tier_affinity,
        section_role, scope, genre

    Returns:
        {
            "results": [{"variant": {...}, "score": 0.85, "breakdown": {...}}],
            "relaxed_filters": [],
            "total": N
        }
    """
    lib = _get_library()
    elib = _get_effect_library()

    body = request.get_json(silent=True) or {}

    ctx = ScoringContext(
        base_effect=body.get("base_effect") or None,
        prop_type=body.get("prop_type") or None,
        energy_level=body.get("energy_level") or None,
        tier_affinity=body.get("tier_affinity") or None,
        section_role=body.get("section_role") or None,
        scope=body.get("scope") or None,
        genre=body.get("genre") or None,
    )

    scored, relaxed_filters = rank_variants_with_fallback(ctx, lib, elib)

    min_score = body.get("min_score", 0.0)
    results = [
        {
            "variant": variant.to_dict(),
            "score": round(score, 6),
            "breakdown": {k: round(v, 6) for k, v in breakdown.items()},
        }
        for variant, score, breakdown in scored
        if score >= min_score
    ]

    return jsonify({
        "results": results,
        "relaxed_filters": relaxed_filters,
        "total": len(results),
    })


@variant_bp.route("/api/list-grouped", methods=["GET"])
def list_grouped():
    """Return all variants grouped by base_effect, for use in theme editor dropdowns.

    Response: { "groups": [ { "effect": str, "variants": [ { "name", "description", "energy_level" } ] } ] }
    """
    lib = _get_library()
    by_effect: dict[str, list] = {}
    for v in lib.variants.values():
        by_effect.setdefault(v.base_effect, []).append(v)

    groups = []
    for effect_name in sorted(by_effect):
        variants_list = sorted(by_effect[effect_name], key=lambda v: v.name)
        groups.append({
            "effect": effect_name,
            "variants": [
                {
                    "name": v.name,
                    "description": v.description,
                    "energy_level": v.tags.energy_level if v.tags else None,
                }
                for v in variants_list
            ],
        })

    return jsonify({"groups": groups})


@variant_bp.route("/coverage", methods=["GET"])
def variant_coverage():
    """Return variant coverage statistics across all catalogued base effects."""
    lib = _get_library()
    elib = _get_effect_library()

    by_effect: dict[str, list] = {}
    for v in lib.variants.values():
        by_effect.setdefault(v.base_effect, []).append(v)

    coverage = []
    for effect_name, defn in elib.effects.items():
        variants = by_effect.get(effect_name, [])
        if variants:
            complete = sum(
                1 for v in variants
                if v.tags.energy_level and v.tags.tier_affinity
                and v.tags.scope and v.tags.speed_feel
            )
            tag_completeness = round(complete / len(variants), 2)
        else:
            tag_completeness = 0.0
        coverage.append({
            "effect": effect_name,
            "category": defn.category,
            "variant_count": len(variants),
            "tag_completeness": tag_completeness,
        })

    coverage.sort(key=lambda x: (-x["variant_count"], x["effect"]))

    total_variants = sum(x["variant_count"] for x in coverage)
    return jsonify({
        "coverage": coverage,
        "total_variants": total_variants,
        "effects_with_variants": sum(1 for x in coverage if x["variant_count"] > 0),
        "effects_without_variants": sum(1 for x in coverage if x["variant_count"] == 0),
    })


@variant_bp.route("/import", methods=["POST"])
def import_variants():
    """Multipart file upload. Query params: dry_run, skip_duplicates."""
    from src.variants.importer import extract_variants_from_xsq
    import tempfile
    import os

    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
    if request.content_length and request.content_length > MAX_UPLOAD_SIZE:
        return jsonify({"error": "File too large (max 50 MB)"}), 413

    dry_run = request.args.get("dry_run", "").lower() in ("true", "1")
    skip_dupes = request.args.get("skip_duplicates", "").lower() in ("true", "1")

    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' field"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    with tempfile.NamedTemporaryFile(suffix=".xsq", delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name
    try:
        lib = _get_library()
        elib = _get_effect_library()
        results = extract_variants_from_xsq(
            tmp_path, elib,
            skip_duplicates=skip_dupes,
            existing_library=lib if not dry_run else None,
            dry_run=dry_run,
            custom_dir=_get_custom_dir() if not dry_run else None,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        os.unlink(tmp_path)

    imported = [r for r in results if r["status"] == "imported"]
    duplicates = [r for r in results if r["status"] == "duplicate"]
    unknown = [r for r in results if r["status"] == "unknown"]

    if not dry_run:
        global _library
        _library = None  # force reload

    return jsonify({
        "imported": imported,
        "duplicates": duplicates,
        "unknown": unknown,
        "summary": {
            "imported": len(imported),
            "duplicates": len(duplicates),
            "unknown": len(unknown),
        },
    })


@variant_bp.route("", methods=["POST"])
def create_variant():
    """Create a new custom variant."""
    from src.variants.validator import validate_variant
    from src.variants.models import EffectVariant

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"errors": ["Request body must be valid JSON"]}), 400
    elib = _get_effect_library()
    errors = validate_variant(data, elib)
    if errors:
        return jsonify({"errors": errors}), 400
    lib = _get_library()
    if lib.get(data.get("name", "")) is not None:
        return jsonify({"error": f"Variant '{data['name']}' already exists"}), 409
    variant = EffectVariant.from_dict(data)
    lib.save_custom_variant(variant, _get_custom_dir())
    global _library
    _library = None
    builtin_names = _get_builtin_names()
    return jsonify(_variant_to_dict(variant, variant.name in builtin_names, elib)), 201


@variant_bp.route("/<path:name>", methods=["GET"])
def get_variant(name: str):
    """Get full detail for a single variant by name (case-insensitive)."""
    lib = _get_library()
    elib = _get_effect_library()
    builtin_names = _get_builtin_names()

    variant = lib.get(name)
    if variant is None:
        return jsonify({"error": f"Variant not found: {name}"}), 404

    return jsonify(_variant_to_dict(variant, variant.name in builtin_names, elib))


@variant_bp.route("/<path:name>", methods=["PUT"])
def update_variant(name: str):
    """Update a custom variant by name."""
    from src.variants.validator import validate_variant
    from src.variants.models import EffectVariant

    lib = _get_library()
    elib = _get_effect_library()
    builtin_names = _get_builtin_names()

    existing = lib.get(name)
    if existing is None:
        return jsonify({"error": f"Variant not found: {name}"}), 404
    if existing.name in builtin_names:
        return jsonify({"error": f"Cannot modify built-in variant '{name}'"}), 403

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"errors": ["Request body must be valid JSON"]}), 400
    data["name"] = existing.name  # name is immutable via PUT

    errors = validate_variant(data, elib)
    if errors:
        return jsonify({"errors": errors}), 400

    variant = EffectVariant.from_dict(data)
    lib.save_custom_variant(variant, _get_custom_dir())
    global _library
    _library = None

    return jsonify(_variant_to_dict(variant, variant.name in builtin_names, elib))


@variant_bp.route("/<path:name>", methods=["DELETE"])
def delete_variant(name: str):
    """Delete a custom variant by name."""
    lib = _get_library()
    builtin_names = _get_builtin_names()

    existing = lib.get(name)
    if existing is None:
        return jsonify({"error": f"Variant not found: {name}"}), 404
    if existing.name in builtin_names:
        return jsonify({"error": f"Cannot delete built-in variant '{name}'"}), 403

    lib.delete_custom_variant(name, _get_custom_dir())
    global _library
    _library = None

    return "", 204
