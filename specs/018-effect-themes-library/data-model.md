# Data Model: xLights Effect Library

**Date**: 2026-03-26
**Branch**: `018-effect-themes-library`

---

## Core Entities

### `EffectDefinition`

A single xLights effect described for use in sequencing.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | xLights effect name (e.g., "Fire", "Bars", "Meteors") — must match the `name` attribute in `.xsq` effect elements |
| `xlights_id` | `str` | Internal xLights enum name (e.g., "eff_FIRE") — for reference only |
| `category` | `str` | Organizational label: `color_wash`, `pattern`, `nature`, `movement`, `audio_reactive`, `media`, `utility` |
| `description` | `str` | One-line description of what the effect does |
| `intent` | `str` | When/why to use this effect (e.g., "Simulates rising flames — use for aggressive, high-energy sections") |
| `parameters` | `list[EffectParameter]` | All configurable parameters for this effect |
| `prop_suitability` | `dict[str, str]` | Mapping of prop type → suitability rating |
| `analysis_mappings` | `list[AnalysisMapping]` | How analysis data can drive this effect's parameters |

---

### `EffectParameter`

A configurable property of an effect, matching xLights internal naming.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Base parameter name (e.g., "Fire_Height") — combined with prefix for storage |
| `storage_name` | `str` | Full xLights storage name (e.g., "E_SLIDER_Fire_Height") |
| `widget_type` | `str` | One of: `slider`, `checkbox`, `choice`, `textctrl` |
| `value_type` | `str` | One of: `int`, `float`, `bool`, `choice` |
| `default` | `int | float | bool | str` | Default value |
| `min` | `int | float | None` | Minimum value (null for bool/choice) |
| `max` | `int | float | None` | Maximum value (null for bool/choice) |
| `choices` | `list[str] | None` | Valid choices (only for `choice` type) |
| `description` | `str` | What this parameter controls |
| `supports_value_curve` | `bool` | Whether this parameter can be driven by a value curve (most sliders can) |

---

### `AnalysisMapping`

A structured rule linking an effect parameter to an analysis level.

| Field | Type | Description |
|-------|------|-------------|
| `parameter` | `str` | Base parameter name (matches `EffectParameter.name`) |
| `analysis_level` | `str` | One of: `L0`, `L1`, `L2`, `L3`, `L4`, `L5`, `L6` |
| `analysis_field` | `str` | Specific field path in the analysis output (e.g., "energy_curves.bass", "onsets.drums") |
| `mapping_type` | `str` | One of: `direct`, `inverted`, `threshold_trigger` |
| `description` | `str` | Human-readable description of how this mapping works |

**Mapping types**:
- `direct` — analysis value maps proportionally to parameter value
- `inverted` — higher analysis value → lower parameter value
- `threshold_trigger` — analysis value crossing a threshold triggers a discrete parameter change

---

### `PropSuitability`

Stored as a dictionary on each `EffectDefinition`.

| Prop Type Key | Description |
|---------------|-------------|
| `matrix` | Matrix / High-density (pixel panels, P5/P10) |
| `outline` | Outline / Low-density (rooflines, window frames) |
| `arch` | Arch / Curved props (arches, candy canes) |
| `vertical` | Vertical / Straight props (verticals, door frames) |
| `tree` | Tree / Wrapped props (mega trees, mini trees) |

| Rating Value | Meaning |
|-------------|---------|
| `ideal` | Designed for this prop type |
| `good` | Works well with parameter tuning |
| `possible` | Can be used but limited |
| `not_recommended` | Doesn't translate to this prop type |

---

### `EffectLibrary`

The runtime container combining built-in + custom definitions.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `str` | JSON schema version (semver) |
| `target_xlights_version` | `str` | xLights version the catalog was extracted from |
| `effects` | `dict[str, EffectDefinition]` | Effect name → definition (built-in, overridden by custom) |

---

## JSON Schema Structure

```json
{
  "schema_version": "1.0.0",
  "target_xlights_version": "2024.x",
  "effects": {
    "Fire": {
      "name": "Fire",
      "xlights_id": "eff_FIRE",
      "category": "nature",
      "description": "Simulates rising flame animation with heat mapping",
      "intent": "Use for aggressive, high-energy sections — hot colors rising from bottom",
      "parameters": [
        {
          "name": "Fire_Height",
          "storage_name": "E_SLIDER_Fire_Height",
          "widget_type": "slider",
          "value_type": "int",
          "default": 50,
          "min": 1,
          "max": 100,
          "choices": null,
          "description": "Height of the flames as percentage of model height",
          "supports_value_curve": true
        }
      ],
      "prop_suitability": {
        "matrix": "ideal",
        "outline": "good",
        "arch": "possible",
        "vertical": "good",
        "tree": "good"
      },
      "analysis_mappings": [
        {
          "parameter": "Fire_Height",
          "analysis_level": "L5",
          "analysis_field": "energy_curves.bass",
          "mapping_type": "direct",
          "description": "Bass energy drives flame height — louder bass = taller flames"
        }
      ]
    }
  }
}
```

---

## Custom Override Directory

- Path: `~/.xlight/custom_effects/`
- Each file: `{effect_name}.json` containing a single `EffectDefinition`
- On load: scan directory, validate each file, merge into library (custom overrides built-in by name)
- Invalid files: log warning, skip, fall back to built-in

---

## Coverage Tracking

The library maintains a constant list of all 56 known xLights effect names. The coverage query returns:
- `cataloged`: effects present in the library (built-in + custom)
- `uncatalogued`: known xLights effects with no definition in the library
