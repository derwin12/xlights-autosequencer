# Data Model: Theme Editor

**Feature**: 026-theme-editor | **Date**: 2026-04-01

## Existing Entities (No Changes)

These entities already exist in `src/themes/models.py` and `src/effects/models.py`. The theme editor consumes them as-is.

### Theme (`src/themes/models.py`)

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| name | str | Yes | Unique across all themes (built-in + custom) |
| mood | str | Yes | One of: `ethereal`, `aggressive`, `dark`, `structural` |
| occasion | str | No | One of: `general`, `christmas`, `halloween`. Default: `general` |
| genre | str | No | One of: `rock`, `pop`, `classical`, `any`. Default: `any` |
| intent | str | Yes | Free text describing the visual intent |
| layers | list[EffectLayer] | Yes | Min 1. Bottom layer (index 0) must have blend_mode=`Normal` |
| palette | list[str] | Yes | Min 2 hex color strings (e.g., `#FF4400`) |
| accent_palette | list[str] | No | Min 2 hex color strings if provided. Default: empty list |
| variants | list[ThemeVariant] | No | Alternative layer configurations. Default: empty list |

**Identity**: Theme name (case-insensitive lookup via `ThemeLibrary.get()`)

**Lifecycle**:
- Built-in themes: read-only, loaded from `builtin_themes.json`
- Custom themes: full CRUD, stored as individual JSON files in `~/.xlight/custom_themes/`
- Override: a custom theme with the same name as a built-in replaces it in the library

### EffectLayer (`src/themes/models.py`)

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| effect | str | Yes | Must exist in EffectLibrary (case-insensitive) |
| blend_mode | str | No | One of 22 valid blend modes. Default: `Normal` |
| parameter_overrides | dict[str, int\|float\|bool\|str] | No | Keys are xLights storage names (e.g., `E_SLIDER_Fire_Height`) |

**Constraints**: Bottom layer of a theme must use `Normal` blend mode. Bottom layer cannot be a modifier effect (`layer_role != "modifier"`).

### ThemeVariant (`src/themes/models.py`)

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| layers | list[EffectLayer] | Yes | Same constraints as Theme.layers |

### EffectDefinition (`src/effects/models.py`) — Read-Only Reference

| Field | Type | Used By Editor |
|-------|------|---------------|
| name | str | Effect dropdown in layer editor |
| category | str | Potential grouping in effect dropdown |
| parameters | list[EffectParameter] | Auto-populate parameter overrides UI |
| layer_role | str | Validate bottom layer (cannot be "modifier") |

### EffectParameter (`src/effects/models.py`) — Read-Only Reference

| Field | Type | Used By Editor |
|-------|------|---------------|
| name | str | Display name in parameter UI |
| storage_name | str | Key for parameter_overrides dict |
| widget_type | str | Determines input widget: slider, checkbox, choice, textctrl |
| value_type | str | Input validation: int, float, bool, choice, string |
| default | varies | Pre-filled value when effect is selected |
| min / max | number\|None | Slider/input bounds |
| choices | list[str]\|None | Dropdown options for choice type |

## New Entities

### ThemeWriteResult (returned by writer operations)

| Field | Type | Description |
|-------|------|-------------|
| success | bool | Whether the operation succeeded |
| theme_name | str | Name of the theme affected |
| file_path | str | Absolute path to the written/deleted file |
| error | str\|None | Error message if success=False |

This is a simple return type for the `writer.py` module, not a persisted entity.

## Storage Layout

```text
~/.xlight/
└── custom_themes/
    ├── my-cool-theme.json      # Slugified from "My Cool Theme"
    ├── winter-wonderland.json   # Slugified from "Winter Wonderland"
    └── inferno.json             # Override of built-in "Inferno" (created via Edit flow)
```

Each file contains a single Theme object (not wrapped in a container):

```json
{
  "name": "My Cool Theme",
  "mood": "ethereal",
  "occasion": "general",
  "genre": "any",
  "intent": "Gentle flowing lights for ambient tracks",
  "layers": [
    {
      "effect": "Color Wash",
      "blend_mode": "Normal",
      "parameter_overrides": {}
    },
    {
      "effect": "Twinkle",
      "blend_mode": "Additive",
      "parameter_overrides": {"E_SLIDER_Twinkle_Count": 30}
    }
  ],
  "palette": ["#4488FF", "#88CCFF", "#FFFFFF"],
  "accent_palette": ["#AADDFF", "#FFFFFF"],
  "variants": []
}
```

## Relationships

```text
ThemeLibrary (in-memory)
  └── Theme (many, keyed by name)
        ├── EffectLayer (ordered list, 1+)
        │     └── references EffectDefinition (by name)
        │           └── EffectParameter (list, for auto-populate)
        ├── ThemeVariant (optional list)
        │     └── EffectLayer (ordered list, same constraints)
        ├── palette (list of hex colors)
        └── accent_palette (optional list of hex colors)
```

## Validation Rules Summary

| Rule | Enforced At | Source |
|------|------------|--------|
| Name unique across all themes | API (server-side) + UI (client-side) | FR-005 |
| Mood in valid set | Theme validator | Existing |
| Occasion in valid set | Theme validator | Existing |
| Genre in valid set | Theme validator | Existing |
| Palette >= 2 colors | Theme validator | Existing |
| Accent palette >= 2 colors (if provided) | Theme validator | Existing |
| At least 1 layer | Theme validator | Existing |
| Bottom layer blend_mode = Normal | Theme validator | Existing |
| Bottom layer not modifier effect | Theme validator | Existing |
| All effects exist in EffectLibrary | Theme validator | Existing |
| All blend modes valid | Theme validator | Existing |
