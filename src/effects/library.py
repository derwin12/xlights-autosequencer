"""Load and query the xLights effect library."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.effects.models import (
    ALL_XLIGHTS_EFFECTS,
    CoverageResult,
    EffectDefinition,
)
from src.effects.validator import validate_effect_definition

logger = logging.getLogger(__name__)

_BUILTIN_PATH = Path(__file__).parent / "builtin_effects.json"
_DEFAULT_CUSTOM_DIR = Path.home() / ".xlight" / "custom_effects"


@dataclass
class EffectLibrary:
    schema_version: str
    target_xlights_version: str
    effects: dict[str, EffectDefinition]

    def get(self, name: str) -> EffectDefinition | None:
        """Look up an effect by name (case-insensitive)."""
        # Try exact match first
        if name in self.effects:
            return self.effects[name]
        # Case-insensitive fallback
        name_lower = name.lower()
        for key, defn in self.effects.items():
            if key.lower() == name_lower:
                return defn
        return None

    def for_prop_type(self, prop_type: str) -> list[EffectDefinition]:
        """Return effects rated 'ideal' or 'good' for the given prop type."""
        results = []
        for defn in self.effects.values():
            rating = defn.prop_suitability.get(prop_type)
            if rating in ("ideal", "good"):
                results.append(defn)
        return results

    def coverage(self) -> CoverageResult:
        """Return cataloged vs. uncatalogued xLights effect names."""
        cataloged = sorted(self.effects.keys())
        cataloged_lower = {n.lower() for n in cataloged}
        uncatalogued = sorted(
            n for n in ALL_XLIGHTS_EFFECTS
            if n.lower() not in cataloged_lower
        )
        return CoverageResult(
            cataloged=cataloged,
            uncatalogued=uncatalogued,
            total_xlights=len(ALL_XLIGHTS_EFFECTS),
        )


def load_effect_library(
    builtin_path: str | Path | None = None,
    custom_dir: str | Path | None = None,
) -> EffectLibrary:
    """Load the effect library from built-in JSON + optional custom overrides.

    Args:
        builtin_path: Path to the built-in JSON catalog. Defaults to the
            bundled builtin_effects.json.
        custom_dir: Path to the custom overrides directory. Defaults to
            ~/.xlight/custom_effects/. If the directory doesn't exist,
            only built-in definitions are returned.

    Raises:
        FileNotFoundError: If the built-in JSON file is missing.
    """
    builtin_path = Path(builtin_path) if builtin_path else _BUILTIN_PATH
    custom_dir = Path(custom_dir) if custom_dir else _DEFAULT_CUSTOM_DIR

    # Load built-in catalog
    if not builtin_path.exists():
        raise FileNotFoundError(f"Built-in effect library not found: {builtin_path}")

    with open(builtin_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    schema_version = raw.get("schema_version", "0.0.0")
    target_version = raw.get("target_xlights_version", "unknown")

    effects: dict[str, EffectDefinition] = {}
    for name, data in raw.get("effects", {}).items():
        errors = validate_effect_definition(data)
        if errors:
            logger.warning("Built-in effect '%s' has validation errors: %s", name, errors)
            continue
        effects[name] = EffectDefinition.from_dict(data)

    # Load custom overrides
    if custom_dir.is_dir():
        for custom_file in sorted(custom_dir.glob("*.json")):
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    custom_data = json.load(f)
                errors = validate_effect_definition(custom_data)
                if errors:
                    logger.warning(
                        "Skipping invalid custom effect '%s': %s",
                        custom_file.name, errors,
                    )
                    continue
                custom_defn = EffectDefinition.from_dict(custom_data)
                effects[custom_defn.name] = custom_defn
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning("Skipping malformed custom file '%s': %s", custom_file.name, exc)

    return EffectLibrary(
        schema_version=schema_version,
        target_xlights_version=target_version,
        effects=effects,
    )
