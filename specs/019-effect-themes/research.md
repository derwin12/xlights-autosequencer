# Research: Effect Themes

**Date**: 2026-03-26
**Branch**: `019-effect-themes`

---

## xLights Blend Modes (24 total)

### Decision: Support all 24 blend modes as valid values; use Normal as default

**Rationale**: xLights supports 24 blend modes stored as `T_CHOICE_LayerMethod` in effect settings strings. Supporting all of them avoids artificial limitations. Normal is omitted from storage when it's the default.

**Complete list**: Normal, Effect 1, Effect 2, 1 is Mask, 2 is Mask, 1 is Unmask, 2 is Unmask, 1 is True Unmask, 2 is True Unmask, 1 reveals 2, 2 reveals 1, Layered, Average, Bottom-Top, Left-Right, Shadow 1 on 2, Shadow 2 on 1, Additive, Subtractive, Brightness, Max, Min, Highlight, Highlight Vibrant

**Most useful for themes**:
- `Normal` — default, alpha-based layering
- `Additive` — brightens (good for adding sparkle/twinkle on top)
- `Subtractive` — darkens (good for Dark/Horror themes — "carving holes")
- `1 is Mask` / `2 is Mask` — one effect shapes the other
- `Layered` — base + overlay
- `Average` — smooth blend between two effects

---

## Color Palette Format

### Decision: Use xLights native `#RRGGBB` hex format, up to 8 colors per palette

**Rationale**: xLights stores palettes as `C_BUTTON_Palette1=#FF0000` with `C_CHECKBOX_Palette1=1` for active slots. Matching this format means the sequence generator can emit palette strings directly.

**Format in our theme JSON**:
```json
"palette": ["#FF4400", "#FF8800", "#FFCC00"]
```

Active slots = all listed colors. Unused slots (4-8) are omitted. The sequence generator translates this to xLights `C_BUTTON_Palette` format.

---

## Layer Parameter Overrides

### Decision: Store overrides as key-value pairs using xLights storage names

**Rationale**: Each layer in a theme can override the effect's default parameter values. Using the same `E_SLIDER_*` / `E_CHECKBOX_*` storage names from the effect library means the sequence generator can emit them directly without translation.

**Example**: The Inferno theme uses Fire with Height=80 (instead of default 50):
```json
{
  "effect": "Fire",
  "blend_mode": "Normal",
  "parameter_overrides": {
    "E_SLIDER_Fire_Height": 80,
    "E_CHOICE_Fire_Location": "Bottom"
  }
}
```

---

## Structure Decision: Themes Module Alongside Effects

### Decision: New `src/themes/` module, depends on `src/effects/`

**Rationale**: Themes compose from effects but are a separate concern. Same pattern as grouper (017) and effects (018) — independent module, shared data via imports.

Custom themes directory: `~/.xlight/custom_themes/` (parallels `~/.xlight/custom_effects/`).
