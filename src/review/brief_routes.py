"""Flask blueprint for per-song Creative Brief persistence (spec 047).

Provides GET/PUT endpoints for ``/brief/<source_hash>``. The Brief JSON is
stored alongside the audio file as ``<audio_stem>_brief.json``.

See ``specs/047-creative-brief/`` for schema and behavior.

Priority order for generation fields (spec §3):
  1. POST body (from Brief tab)
  2. On-disk Brief JSON (this module writes it)
  3. Legacy _story_reviewed.json (generate_routes fallback for un-briefed songs)
  4. GenerationConfig defaults
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from src.library import Library

brief_bp = Blueprint("brief", __name__, url_prefix="/brief")

# Valid values — mirror GenerationConfig._VALID_* frozensets (kept in sync manually;
# if GenerationConfig validation changes, update these too).
_VALID_GENRES = frozenset({"auto", "any", "pop", "rock", "classical"})
_VALID_OCCASIONS = frozenset({"auto", "general", "christmas", "halloween"})
_VALID_MOOD_INTENTS = frozenset({"auto", "party", "emotional", "dramatic", "playful"})
_VALID_VARIATION = frozenset({"auto", "focused", "balanced", "varied"})
_VALID_PALETTE = frozenset({"auto", "restrained", "balanced", "full"})
_VALID_DURATION = frozenset({"auto", "snappy", "balanced", "flowing"})
_VALID_ACCENTS = frozenset({"auto", "none", "subtle", "strong"})
_VALID_TRANSITIONS = frozenset({"auto", "none", "subtle", "dramatic"})
_VALID_CURVES = frozenset({"auto", "on", "off"})
# Advanced raw-field enums
_VALID_CURVES_MODES = frozenset({"all", "brightness", "speed", "color", "none"})
_VALID_DURATION_FEELS = frozenset({"auto", "snappy", "balanced", "flowing"})
_VALID_ACCENT_STRENGTHS = frozenset({"auto", "subtle", "strong"})

BRIEF_SCHEMA_VERSION = 1

# Axis preset-id validators: axis_name → valid set
_AXIS_VALIDATORS: dict[str, frozenset[str]] = {
    "genre": _VALID_GENRES,
    "occasion": _VALID_OCCASIONS,
    "mood_intent": _VALID_MOOD_INTENTS,
    "variation": _VALID_VARIATION,
    "palette": _VALID_PALETTE,
    "duration": _VALID_DURATION,
    "accents": _VALID_ACCENTS,
    "transitions": _VALID_TRANSITIONS,
    "curves": _VALID_CURVES,
}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _brief_path(source_hash: str) -> Path:
    """Resolve the brief JSON path for a song given its source hash.

    Returns the path even if the file does not yet exist.
    Raises a 404-friendly ValueError if the song is not in the library.
    """
    entry = Library().find_by_hash(source_hash)
    if entry is None:
        raise ValueError(f"Song {source_hash!r} not found in library")
    audio_path = Path(entry.source_file)
    return audio_path.parent / f"{audio_path.stem}_brief.json"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_brief(body: dict[str, Any]) -> tuple[bool, str, str]:
    """Validate the incoming PUT body.

    Returns ``(ok, field_name, error_message)``.
    ``field_name`` is empty string when ``ok`` is True.
    """
    # Schema version check
    version = body.get("brief_schema_version", BRIEF_SCHEMA_VERSION)
    if int(version) != BRIEF_SCHEMA_VERSION:
        return False, "brief_schema_version", (
            f"Unsupported brief_schema_version {version!r}. "
            f"Expected {BRIEF_SCHEMA_VERSION}."
        )

    # Axis preset id validation
    for axis, valid_set in _AXIS_VALIDATORS.items():
        val = body.get(axis, "auto")
        if val not in valid_set:
            return False, axis, f"Invalid {axis} value {val!r}. Must be one of: {sorted(valid_set)}"

    # Advanced field validation
    advanced = body.get("advanced") or {}
    if not isinstance(advanced, dict):
        return False, "advanced", "advanced must be a JSON object"

    curves_mode = advanced.get("curves_mode")
    if curves_mode is not None and curves_mode not in _VALID_CURVES_MODES:
        return False, "advanced.curves_mode", (
            f"Invalid curves_mode {curves_mode!r}. "
            f"Must be one of: {sorted(_VALID_CURVES_MODES)}"
        )

    duration_feel = advanced.get("duration_feel")
    if duration_feel is not None and duration_feel not in _VALID_DURATION_FEELS:
        return False, "advanced.duration_feel", (
            f"Invalid duration_feel {duration_feel!r}. "
            f"Must be one of: {sorted(_VALID_DURATION_FEELS)}"
        )

    accent_strength = advanced.get("accent_strength")
    if accent_strength is not None and accent_strength not in _VALID_ACCENT_STRENGTHS:
        return False, "advanced.accent_strength", (
            f"Invalid accent_strength {accent_strength!r}. "
            f"Must be one of: {sorted(_VALID_ACCENT_STRENGTHS)}"
        )

    # Per-section overrides validation
    overrides = body.get("per_section_overrides") or []
    if not isinstance(overrides, list):
        return False, "per_section_overrides", "per_section_overrides must be an array"

    for i, row in enumerate(overrides):
        if not isinstance(row, dict):
            return False, "per_section_overrides", f"override row {i} must be a JSON object"
        if not isinstance(row.get("section_index"), int):
            return False, "per_section_overrides", f"override row {i} missing integer section_index"
        theme_slug = row.get("theme_slug")
        if not theme_slug or not isinstance(theme_slug, str):
            return False, "per_section_overrides", f"override row {i} missing theme_slug string"
        if theme_slug == "auto":
            return False, "per_section_overrides", (
                f"override row {i} theme_slug must not be 'auto' — omit the row instead"
            )

    return True, "", ""


def _validate_theme_slugs(overrides: list[dict]) -> list[str]:
    """Return a list of theme_slug values that are not in the theme catalog.

    This is a best-effort check; if the theme library cannot be loaded,
    returns empty list (no slugs rejected).
    """
    if not overrides:
        return []
    try:
        from src.themes.library import load_theme_library
        from src.effects.library import load_effect_library
        lib = load_theme_library(effect_library=load_effect_library())
        valid_names = set(lib.themes.keys())
        # Also accept any lowercased match
        valid_lower = {n.lower() for n in valid_names}
        bad = []
        for row in overrides:
            slug = row.get("theme_slug", "")
            if slug and slug != "auto":
                if slug not in valid_names and slug.lower() not in valid_lower:
                    bad.append(slug)
        return bad
    except Exception:
        return []


# ---------------------------------------------------------------------------
# GET /brief/<source_hash>
# ---------------------------------------------------------------------------

@brief_bp.route("/<source_hash>", methods=["GET"])
def get_brief(source_hash: str):
    """Return the persisted Brief JSON for a song, or 404 if not yet saved."""
    try:
        path = _brief_path(source_hash)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    if not path.exists():
        return jsonify({"error": "no brief"}), 404

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({"error": f"Could not read brief: {exc}"}), 500


# ---------------------------------------------------------------------------
# PUT /brief/<source_hash>
# ---------------------------------------------------------------------------

@brief_bp.route("/<source_hash>", methods=["PUT"])
def put_brief(source_hash: str):
    """Persist the Brief JSON for a song.

    Validates schema version and all axis values. On any validation failure,
    returns 400 with ``{field, error}``. Returns the stored JSON with 200.
    """
    try:
        path = _brief_path(source_hash)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    body = request.get_json(silent=True) or {}

    # Validate schema version — returns 409 for version mismatch
    version = body.get("brief_schema_version", BRIEF_SCHEMA_VERSION)
    try:
        version_int = int(version)
    except (TypeError, ValueError):
        return jsonify({"field": "brief_schema_version", "error": "Must be an integer"}), 400

    if version_int != BRIEF_SCHEMA_VERSION:
        return jsonify({
            "field": "brief_schema_version",
            "error": (
                f"Unsupported brief_schema_version {version_int}. "
                f"Expected {BRIEF_SCHEMA_VERSION}. "
                "Submit a new Brief from the UI to migrate."
            ),
        }), 409

    # Validate all fields
    ok, field_name, error_msg = _validate_brief(body)
    if not ok:
        return jsonify({"field": field_name, "error": error_msg}), 400

    # Validate theme slugs in per_section_overrides
    overrides = body.get("per_section_overrides") or []
    bad_slugs = _validate_theme_slugs(overrides)
    if bad_slugs:
        return jsonify({
            "field": "per_section_overrides",
            "error": (
                f"Unknown theme slug(s): {bad_slugs}. "
                "Use 'auto' or a valid theme name."
            ),
        }), 400

    # Normalise and stamp updated_at
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    axes = ["genre", "occasion", "mood_intent", "variation", "palette",
            "duration", "accents", "transitions", "curves"]
    stored: dict[str, Any] = {
        "brief_schema_version": BRIEF_SCHEMA_VERSION,
        "source_hash": source_hash,
        "updated_at": updated_at,
        "advanced": dict(body.get("advanced") or {}),
        "per_section_overrides": list(body.get("per_section_overrides") or []),
    }
    for axis in axes:
        stored[axis] = body.get(axis, "auto")

    # Atomic write: write to temp file then os.replace
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".brief_tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(stored, f, indent=2)
        except Exception:
            os.unlink(tmp_path)
            raise
        os.replace(tmp_path, str(path))
    except OSError as exc:
        return jsonify({"error": f"Could not write brief: {exc}"}), 500

    return jsonify(stored), 200
