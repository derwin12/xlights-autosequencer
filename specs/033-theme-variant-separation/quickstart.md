# Quickstart: Theme and Effect Variant Separation

**Feature**: 033-theme-variant-separation

## What Changed

Theme layers no longer contain effect parameters inline. Instead, each layer references a named **effect variant** from the variant library. The variant owns all parameter configuration; the theme just composes variants with palettes and blend modes.

**ThemeVariant** has been renamed to **ThemeAlternate** to avoid confusion with **EffectVariant**.

## New Theme Layer Format

**Before** (theme layer configured its own parameters):
```json
{
  "effect": "Butterfly",
  "blend_mode": "Normal",
  "parameter_overrides": {
    "E_SLIDER_Butterfly_Speed": 15,
    "E_SLIDER_Butterfly_Chunks": 3
  }
}
```

**After** (theme layer references a variant by name):
```json
{
  "variant": "Butterfly Slow 3-Chunk",
  "blend_mode": "Normal"
}
```

## Creating a New Theme

1. Open the theme editor in the review UI
2. Set name, mood, occasion, genre, intent, and palette
3. Add layers — each layer is a variant picker (grouped by effect name)
4. Select a variant for each layer and set the blend mode
5. Optionally add alternates (for repeated section variety)
6. Save

If no existing variant fits your needs, create a new variant in the variant editor first, then reference it in your theme.

## Key Concepts

- **Variants own parameters** — all effect configuration lives in named variants
- **Themes compose variants** — themes select which variants to use and pair them with palettes
- **Alternates** (formerly "variants" on Theme) — alternate layer stacks for repeated sections
- **effect_pool** — optional list of variant names for rotation engine alternatives
- **Final tweaks happen in xLights** — the generated sequence gets you to ~95%, fine-tuning is done in xLights

## Dependency Chain

```
EffectLibrary (must load first)
    ↓
VariantLibrary (must load second — required, not optional)
    ↓
ThemeLibrary (loads third — resolves variant references)
    ↓
Generator pipeline (uses resolved themes)
```
