# Data Model: Theme and Effect Variant Separation

**Feature**: 033-theme-variant-separation
**Date**: 2026-04-09

## Entity Changes

### EffectLayer (MODIFIED)

**Before**:
```
EffectLayer:
  effect: str                    # effect name from library
  blend_mode: str                # xLights blend mode
  parameter_overrides: dict      # inline parameter values
  variant_ref: str | None        # optional variant reference
  effect_pool: list[str]         # rotation alternative variant names
```

**After**:
```
EffectLayer:
  variant: str                   # REQUIRED — variant name from VariantLibrary
  blend_mode: str                # xLights blend mode (default: "Normal")
  effect_pool: list[str]         # rotation alternative variant names (optional)
```

**Removed fields**:
- `effect` — derived from variant's `base_effect`
- `parameter_overrides` — lives in the variant
- `variant_ref` — replaced by `variant` as the primary required field

**Derived properties**:
- Effect name: resolved via `variant_library.get(layer.variant).base_effect`
- Parameters: resolved via `variant_library.get(layer.variant).parameter_overrides`

### ThemeAlternate (RENAMED from ThemeVariant)

**Before**:
```
ThemeVariant:
  layers: list[EffectLayer]
```

**After**:
```
ThemeAlternate:
  layers: list[EffectLayer]     # same structure, same variant-only model
```

No structural change — only the class name and JSON key change.

### Theme (MODIFIED)

**Before**:
```
Theme:
  name: str
  mood: str
  occasion: str
  genre: str
  intent: str
  layers: list[EffectLayer]
  palette: list[str]
  accent_palette: list[str]
  variants: list[ThemeVariant]   # ← old name, old key
  transition_mode: str | None
```

**After**:
```
Theme:
  name: str
  mood: str
  occasion: str
  genre: str
  intent: str
  layers: list[EffectLayer]      # layers now use variant-only model
  palette: list[str]
  accent_palette: list[str]
  alternates: list[ThemeAlternate]  # ← renamed from variants
  transition_mode: str | None
```

### EffectVariant (UNCHANGED)

No changes to the EffectVariant entity. It gains ~60-70 new instances from theme migration but the schema is unchanged.

```
EffectVariant:
  name: str
  base_effect: str
  description: str
  parameter_overrides: dict
  tags: VariantTags
  direction_cycle: dict | None
```

## JSON Format Changes

### builtin_themes.json

**Before**:
```json
{
  "layers": [
    {
      "effect": "Butterfly",
      "blend_mode": "Normal",
      "parameter_overrides": {
        "E_SLIDER_Butterfly_Speed": 15,
        "E_SLIDER_Butterfly_Chunks": 3
      }
    }
  ],
  "variants": [
    {
      "layers": [
        {
          "effect": "Wave",
          "blend_mode": "Normal",
          "parameter_overrides": { ... }
        }
      ]
    }
  ]
}
```

**After**:
```json
{
  "layers": [
    {
      "variant": "Butterfly Slow 3-Chunk",
      "blend_mode": "Normal"
    }
  ],
  "alternates": [
    {
      "layers": [
        {
          "variant": "Wave Sine Slow",
          "blend_mode": "Normal"
        }
      ]
    }
  ]
}
```

## Relationship Map

```
Theme
  ├── layers: list[EffectLayer]
  │     └── variant ──references──→ EffectVariant (in VariantLibrary)
  │           └── base_effect ──references──→ EffectDefinition (in EffectLibrary)
  ├── alternates: list[ThemeAlternate]
  │     └── layers: list[EffectLayer]  (same structure as above)
  ├── palette: list[str]
  └── accent_palette: list[str]

VariantLibrary (REQUIRED for theme loading)
  └── variants: dict[name → EffectVariant]

EffectLibrary (REQUIRED for variant validation)
  └── effects: dict[name → EffectDefinition]
```

## Validation Rules

1. Every `EffectLayer.variant` must resolve to an existing `EffectVariant` in the library
2. The resolved variant's `base_effect` must exist in the `EffectLibrary`
3. Bottom layer's blend_mode must be "Normal" (unchanged)
4. Bottom layer's resolved effect must not be a "modifier" type (unchanged)
5. `effect_pool` entries must resolve to existing variants (warning if not found)
6. `VariantLibrary` must load successfully before any theme loading begins
