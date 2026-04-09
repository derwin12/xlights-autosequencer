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
    variant_library,
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
            variant_name = layer.get("variant", "")

            # Validate variant exists in variant library
            variant = variant_library.get(variant_name)
            if variant is None:
                errors.append(f"Layer {i}: variant '{variant_name}' not found in variant library")
                # Cannot derive effect — skip effect-dependent checks for this layer
            else:
                # Derive effect from variant's base_effect
                effect_name = variant.base_effect
                effect_def = effect_library.get(effect_name)
                if effect_def is None:
                    errors.append(
                        f"Layer {i}: variant '{variant_name}' references base_effect "
                        f"'{effect_name}' not found in effect library"
                    )
                elif i == 0 and effect_def.layer_role == "modifier":
                    errors.append(
                        f"Layer {i}: modifier effect '{effect_name}' (via variant "
                        f"'{variant_name}') cannot be on the bottom layer"
                    )

            # Check blend mode
            blend = layer.get("blend_mode", "Normal")
            if blend not in VALID_BLEND_MODES:
                errors.append(f"Layer {i}: invalid blend_mode '{blend}'")

            # Check effect_pool entries
            effect_pool = layer.get("effect_pool", [])
            for pool_entry in effect_pool:
                if variant_library.get(pool_entry) is None:
                    errors.append(
                        f"Layer {i}: effect_pool entry '{pool_entry}' not found in variant library"
                    )

    # Alternates (optional)
    for vi, alternate in enumerate(data.get("alternates", [])):
        a_layers = alternate.get("layers", [])
        if not a_layers:
            errors.append(f"Alternate {vi}: must have at least one layer")
            continue
        a_bottom_blend = a_layers[0].get("blend_mode", "Normal")
        if a_bottom_blend != "Normal":
            errors.append(
                f"Alternate {vi} layer 0: bottom blend_mode must be 'Normal', got '{a_bottom_blend}'"
            )
        for j, a_layer in enumerate(a_layers):
            a_variant_name = a_layer.get("variant", "")
            a_variant = variant_library.get(a_variant_name)
            if a_variant is None:
                errors.append(
                    f"Alternate {vi} layer {j}: variant '{a_variant_name}' not found in variant library"
                )
            else:
                a_effect_name = a_variant.base_effect
                a_effect_def = effect_library.get(a_effect_name)
                if a_effect_def is None:
                    errors.append(
                        f"Alternate {vi} layer {j}: variant '{a_variant_name}' references "
                        f"base_effect '{a_effect_name}' not found in effect library"
                    )
                elif j == 0 and a_effect_def.layer_role == "modifier":
                    errors.append(
                        f"Alternate {vi} layer {j}: modifier effect '{a_effect_name}' "
                        f"(via variant '{a_variant_name}') cannot be on the bottom layer"
                    )
            a_blend = a_layer.get("blend_mode", "Normal")
            if a_blend not in VALID_BLEND_MODES:
                errors.append(f"Alternate {vi} layer {j}: invalid blend_mode '{a_blend}'")

    # Palette
    palette = data.get("palette", [])
    if len(palette) < 2:
        errors.append(f"Palette must have at least 2 colors, got {len(palette)}")

    # Accent palette (optional)
    accent_palette = data.get("accent_palette", [])
    if accent_palette and len(accent_palette) < 2:
        errors.append(f"accent_palette must have at least 2 colors, got {len(accent_palette)}")

    return errors
