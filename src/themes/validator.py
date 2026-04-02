"""Validate theme definitions against the schema and effect library."""
from __future__ import annotations

import logging

from src.effects.library import EffectLibrary
from src.themes.models import (
    VALID_BLEND_MODES,
    VALID_GENRES,
    VALID_MOODS,
    VALID_OCCASIONS,
)

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("name", "mood", "intent", "layers", "palette")


def validate_theme(
    data: dict,
    effect_library: EffectLibrary,
    variant_library=None,
) -> list[str]:
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

            # Check effect_pool entries (optional)
            effect_pool = layer.get("effect_pool", [])
            if effect_pool and variant_library is not None:
                for pool_entry in effect_pool:
                    if variant_library.get(pool_entry) is None:
                        logger.warning(
                            "Layer %d: effect_pool entry '%s' not found in variant library",
                            i, pool_entry,
                        )

            # Check variant_ref (optional)
            variant_ref = layer.get("variant_ref")
            if variant_ref is not None and variant_library is not None:
                variant = variant_library.get(variant_ref)
                if variant is None:
                    logger.warning(
                        "Layer %d: variant_ref '%s' not found in variant library — "
                        "effect will fall back to base defaults",
                        i, variant_ref,
                    )
                elif variant.base_effect != effect_name:
                    errors.append(
                        f"Layer {i}: variant_ref '{variant_ref}' has base_effect "
                        f"'{variant.base_effect}' but layer effect is '{effect_name}' — "
                        "base_effect mismatch"
                    )

    # Variants (optional)
    for vi, variant in enumerate(data.get("variants", [])):
        v_layers = variant.get("layers", [])
        if not v_layers:
            errors.append(f"Variant {vi}: must have at least one layer")
            continue
        v_bottom_blend = v_layers[0].get("blend_mode", "Normal")
        if v_bottom_blend != "Normal":
            errors.append(
                f"Variant {vi} layer 0: bottom blend_mode must be 'Normal', got '{v_bottom_blend}'"
            )
        for j, v_layer in enumerate(v_layers):
            v_effect_name = v_layer.get("effect", "")
            v_effect_def = effect_library.get(v_effect_name)
            if v_effect_def is None:
                errors.append(
                    f"Variant {vi} layer {j}: effect '{v_effect_name}' not found in effect library"
                )
            elif j == 0 and v_effect_def.layer_role == "modifier":
                errors.append(
                    f"Variant {vi} layer {j}: modifier effect '{v_effect_name}' "
                    "cannot be on the bottom layer"
                )
            v_blend = v_layer.get("blend_mode", "Normal")
            if v_blend not in VALID_BLEND_MODES:
                errors.append(f"Variant {vi} layer {j}: invalid blend_mode '{v_blend}'")

    # Palette
    palette = data.get("palette", [])
    if len(palette) < 2:
        errors.append(f"Palette must have at least 2 colors, got {len(palette)}")

    # Accent palette (optional)
    accent_palette = data.get("accent_palette", [])
    if accent_palette and len(accent_palette) < 2:
        errors.append(f"accent_palette must have at least 2 colors, got {len(accent_palette)}")

    return errors
