"""Validate effect definitions against the library schema."""
from __future__ import annotations

from src.effects.models import (
    PROP_TYPES,
    SUITABILITY_RATINGS,
    VALID_ANALYSIS_LEVELS,
    VALID_CATEGORIES,
    VALID_CURVE_SHAPES,
    VALID_DURATION_TYPES,
    VALID_LAYER_ROLES,
    VALID_MAPPING_TYPES,
    VALID_VALUE_TYPES,
    VALID_WIDGET_TYPES,
)

_REQUIRED_FIELDS = ("name", "category", "description", "intent", "parameters", "prop_suitability")


def validate_effect_definition(data: dict) -> list[str]:
    """Validate a parsed effect definition dict. Returns list of error messages (empty = valid)."""
    errors: list[str] = []

    # Required top-level fields
    for field in _REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors  # can't validate further without required fields

    # Layer role (optional, defaults to standalone)
    layer_role = data.get("layer_role", "standalone")
    if layer_role not in VALID_LAYER_ROLES:
        errors.append(f"Invalid layer_role '{layer_role}' — must be one of {VALID_LAYER_ROLES}")

    # Duration type (optional, defaults to section)
    duration_type = data.get("duration_type", "section")
    if duration_type not in VALID_DURATION_TYPES:
        errors.append(f"Invalid duration_type '{duration_type}' — must be one of {VALID_DURATION_TYPES}")

    # Category
    if data["category"] not in VALID_CATEGORIES:
        errors.append(f"Invalid category '{data['category']}' — must be one of {VALID_CATEGORIES}")

    # Prop suitability
    suit = data.get("prop_suitability", {})
    for pt in PROP_TYPES:
        if pt not in suit:
            errors.append(f"Missing prop_suitability for '{pt}'")
        elif suit[pt] not in SUITABILITY_RATINGS:
            errors.append(f"Invalid suitability rating '{suit[pt]}' for prop type '{pt}'")

    # Parameters
    param_names: set[str] = set()
    for i, param in enumerate(data.get("parameters", [])):
        pname = param.get("name", f"param[{i}]")
        param_names.add(pname)

        wt = param.get("widget_type", "")
        if wt not in VALID_WIDGET_TYPES:
            errors.append(f"Parameter '{pname}': invalid widget_type '{wt}'")

        vt = param.get("value_type", "")
        if vt not in VALID_VALUE_TYPES:
            errors.append(f"Parameter '{pname}': invalid value_type '{vt}'")

        pmin = param.get("min")
        pmax = param.get("max")
        if pmin is not None and pmax is not None and pmin > pmax:
            errors.append(f"Parameter '{pname}': min ({pmin}) > max ({pmax})")

    # Analysis mappings
    for mapping in data.get("analysis_mappings", []):
        mp = mapping.get("parameter", "")
        if mp not in param_names:
            errors.append(f"Analysis mapping references unknown parameter '{mp}'")

        level = mapping.get("analysis_level", "")
        if level not in VALID_ANALYSIS_LEVELS:
            errors.append(f"Invalid analysis_level '{level}'")

        mt = mapping.get("mapping_type", "")
        if mt not in VALID_MAPPING_TYPES:
            errors.append(f"Invalid mapping_type '{mt}'")

        cs = mapping.get("curve_shape", "linear")
        if cs not in VALID_CURVE_SHAPES:
            errors.append(f"Invalid curve_shape '{cs}' — must be one of {VALID_CURVE_SHAPES}")

    return errors
