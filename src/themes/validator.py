"""Validate theme definitions against the schema and effect library."""
from __future__ import annotations

from src.effects.library import EffectLibrary
from src.themes.models import (
    VALID_BLEND_MODES,
    VALID_GENRES,
    VALID_MOODS,
    VALID_OCCASIONS,
)

_REQUIRED_FIELDS = ("name", "mood", "intent", "layers", "palette")


def validate_theme(data: dict, effect_library: EffectLibrary) -> list[str]:
    """Validate a parsed theme definition dict. Returns list of error messages."""
    errors: list[str] = []

    for field in _REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    # Mood
    if data["mood"] not in VALID_MOODS:
        errors.append(f"Invalid mood '{data['mood']}' — must be one of {VALID_MOODS}")

    # Occasion (optional, default general)
    occasion = data.get("occasion", "general")
    if occasion not in VALID_OCCASIONS:
        errors.append(f"Invalid occasion '{occasion}' — must be one of {VALID_OCCASIONS}")

    # Genre (optional, default any)
    genre = data.get("genre", "any")
    if genre not in VALID_GENRES:
        errors.append(f"Invalid genre '{genre}' — must be one of {VALID_GENRES}")

    # Layers
    layers = data.get("layers", [])
    if not layers:
        errors.append("Theme must have at least one layer")
    else:
        # Bottom layer must be Normal
        bottom_blend = layers[0].get("blend_mode", "Normal")
        if bottom_blend != "Normal":
            errors.append(f"Bottom layer blend_mode must be 'Normal', got '{bottom_blend}'")

        for i, layer in enumerate(layers):
            effect_name = layer.get("effect", "")

            # Check effect exists in library
            effect_def = effect_library.get(effect_name)
            if effect_def is None:
                errors.append(f"Layer {i}: effect '{effect_name}' not found in effect library")
            elif i == 0 and effect_def.layer_role == "modifier":
                errors.append(
                    f"Layer {i}: modifier effect '{effect_name}' cannot be on the bottom layer"
                )

            # Check blend mode
            blend = layer.get("blend_mode", "Normal")
            if blend not in VALID_BLEND_MODES:
                errors.append(f"Layer {i}: invalid blend_mode '{blend}'")

    # Palette
    palette = data.get("palette", [])
    if len(palette) < 2:
        errors.append(f"Palette must have at least 2 colors, got {len(palette)}")

    return errors
