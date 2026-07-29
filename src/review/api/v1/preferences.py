"""Preferences endpoints: GET/PUT /api/v1/preferences."""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1
from src.review.storage.library import load_library, save_library

_VALID_MODES = {"dark", "light"}
_VALID_DENSITIES = {"comfortable", "compact"}
# Mirrors the genre/occasion vocabulary in src/themes/builtin_themes.json.
_VALID_GENRES = {"any", "pop", "rock", "classical"}
_VALID_OCCASIONS = {"general", "christmas", "halloween"}


@api_v1.route("/preferences", methods=["GET"])
def get_preferences():
    lib = load_library()
    return jsonify(lib["preferences"]), 200


@api_v1.route("/preferences", methods=["PUT"])
def put_preferences():
    body = request.get_json(silent=True) or {}

    mode = body.get("mode")
    if mode is not None and mode not in _VALID_MODES:
        return (
            jsonify({"error": {"code": "invalid_preferences", "message": f"Invalid mode: {mode!r}"}}),
            400,
        )

    density = body.get("density")
    if density is not None and density not in _VALID_DENSITIES:
        return (
            jsonify({"error": {"code": "invalid_preferences", "message": f"Invalid density: {density!r}"}}),
            400,
        )

    genre = body.get("genre")
    if genre is not None and genre not in _VALID_GENRES:
        return (
            jsonify({"error": {"code": "invalid_preferences", "message": f"Invalid genre: {genre!r}"}}),
            400,
        )

    occasion = body.get("occasion")
    if occasion is not None and occasion not in _VALID_OCCASIONS:
        return (
            jsonify({"error": {"code": "invalid_preferences", "message": f"Invalid occasion: {occasion!r}"}}),
            400,
        )

    randomness = body.get("randomness")
    if randomness is not None:
        try:
            randomness = float(randomness)
        except (TypeError, ValueError):
            randomness = None
        if randomness is None or not 0.0 <= randomness <= 1.0:
            return (
                jsonify({"error": {"code": "invalid_preferences", "message": f"Invalid randomness: {body.get('randomness')!r}. Must be between 0.0 and 1.0"}}),
                400,
            )
        body["randomness"] = randomness

    lib = load_library()
    prefs = lib["preferences"]
    prefs.update(body)
    lib["preferences"] = prefs
    save_library(lib)
    return jsonify(prefs), 200
