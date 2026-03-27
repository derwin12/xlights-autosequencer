# Data Model: Effect Themes

**Date**: 2026-03-26
**Branch**: `019-effect-themes`

---

## Core Entities

### `Theme`

A named composite "look" that stacks multiple effects with a color palette.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Unique theme name (e.g., "Inferno", "Winter Wonderland") |
| `mood` | `str` | Mood collection: `ethereal`, `aggressive`, `dark`, `structural` |
| `occasion` | `str` | Occasion tag: `christmas`, `halloween`, `general` |
| `genre` | `str` | Genre affinity: `rock`, `pop`, `classical`, `any` |
| `intent` | `str` | When/why to use this theme |
| `layers` | `list[EffectLayer]` | Ordered effect stack (bottom to top) |
| `palette` | `list[str]` | Hex RGB colors (e.g., `["#FF4400", "#FF8800"]`), 2-8 entries |

---

### `EffectLayer`

One layer in a theme's effect stack.

| Field | Type | Description |
|-------|------|-------------|
| `effect` | `str` | Effect name from the effect library (e.g., "Fire") |
| `blend_mode` | `str` | xLights blend mode (default: "Normal") |
| `parameter_overrides` | `dict[str, any]` | Key-value pairs using xLights storage names (e.g., `{"E_SLIDER_Fire_Height": 80}`) |

**Constraints**:
- The bottom layer (index 0) MUST use "Normal" blend mode
- Effects with `layer_role=modifier` in the effect library MUST NOT be on the bottom layer

---

### `ThemeLibrary`

The runtime container combining built-in + custom themes.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `str` | JSON schema version (semver) |
| `themes` | `dict[str, Theme]` | Theme name → definition |

**Query methods**:
- `get(name)` → `Theme | None` — case-insensitive lookup
- `by_mood(mood)` → `list[Theme]`
- `by_occasion(occasion)` → `list[Theme]`
- `by_genre(genre)` → `list[Theme]` (includes themes tagged "any")
- `query(mood=, occasion=, genre=)` → `list[Theme]` — combined filter

---

## Valid Values

### Moods
`ethereal`, `aggressive`, `dark`, `structural`

### Occasions
`christmas`, `halloween`, `general`

### Genres
`rock`, `pop`, `classical`, `any`

### Blend Modes (24)
`Normal`, `Effect 1`, `Effect 2`, `1 is Mask`, `2 is Mask`, `1 is Unmask`, `2 is Unmask`, `1 is True Unmask`, `2 is True Unmask`, `1 reveals 2`, `2 reveals 1`, `Layered`, `Average`, `Bottom-Top`, `Left-Right`, `Shadow 1 on 2`, `Shadow 2 on 1`, `Additive`, `Subtractive`, `Brightness`, `Max`, `Min`, `Highlight`, `Highlight Vibrant`

---

## JSON Structure

```json
{
  "schema_version": "1.0.0",
  "themes": {
    "Inferno": {
      "name": "Inferno",
      "mood": "aggressive",
      "occasion": "general",
      "genre": "rock",
      "intent": "Raw power — house looks like it is on fire and exploding",
      "layers": [
        {
          "effect": "Fire",
          "blend_mode": "Normal",
          "parameter_overrides": {
            "E_SLIDER_Fire_Height": 80,
            "E_CHOICE_Fire_Location": "Bottom"
          }
        },
        {
          "effect": "Morph",
          "blend_mode": "Additive",
          "parameter_overrides": {
            "E_SLIDER_Morph_Stagger": 50
          }
        },
        {
          "effect": "Shockwave",
          "blend_mode": "Additive",
          "parameter_overrides": {
            "E_SLIDER_Shockwave_Start_Width": 5,
            "E_SLIDER_Shockwave_End_Radius": 100
          }
        }
      ],
      "palette": ["#FF4400", "#FF8800", "#FFCC00", "#FFFFFF"]
    }
  }
}
```

---

## Custom Override Directory

- Path: `~/.xlight/custom_themes/`
- Each file: `{theme_name}.json` containing a single Theme definition
- On load: scan directory, validate, merge (custom overrides built-in by name)
- Invalid files: log warning, skip
