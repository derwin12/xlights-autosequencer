# Quickstart: Intelligent Effect Rotation

## Prerequisites

- Feature 028 (Effects Variant Library) must be complete — variant library with 100+ curated variants
- Feature 029 (Prop Effect Suitability) must be complete — prop_type on PowerGroup, graduated scorer
- Existing themes in `src/themes/builtin_themes.json`
- A song with completed analysis (hierarchy JSON)

## Basic Usage

### 1. Generate a sequence (rotation happens automatically)

```bash
xlight-analyze generate song.mp3 --layout xlights_rgbeffects.xml
```

The generator now uses intelligent variant selection for tiers 5-8 instead of the hardcoded effect pool. No flags needed — it's the new default.

### 2. View the rotation report

```bash
# Table format (default)
xlight-analyze rotation-report song_plan.json

# Filter to a section
xlight-analyze rotation-report song_plan.json --section chorus

# JSON format for programmatic use
xlight-analyze rotation-report song_plan.json --format json
```

### 3. Add effect pools to a theme

Edit a theme JSON to add `effect_pool` to any layer:

```json
{
  "name": "Ethereal Frost",
  "mood": "ethereal",
  "layers": [
    {
      "effect": "Color Wash",
      "blend_mode": "Normal"
    },
    {
      "effect": "Butterfly",
      "effect_pool": [
        "butterfly-gentle-blue",
        "butterfly-sparkle-frost",
        "shimmer-ice-crystal",
        "ripple-slow-pulse"
      ]
    }
  ]
}
```

When `effect_pool` is set, the generator picks from the pool based on section energy, prop type, and tier. If no pool variant fits, it falls back to the full variant library.

### 4. View effect pools via API

```bash
curl http://localhost:5173/themes/Ethereal%20Frost/effect-pools
```

### 5. View rotation report via API

```bash
curl http://localhost:5173/rotation-report/<plan_hash>
```

## Backward Compatibility

- Existing themes with no `effect_pool` work identically to before
- The `variant_ref` field on layers still works — `effect_pool` takes priority when both are set
- Tiers 1-4 are completely unchanged
- The `_PROP_EFFECT_POOL` hardcoded list is removed; its behavior is replaced by variant library scoring

## Verifying Rotation Quality

After generating a sequence, check:

1. **Variety**: The rotation report should show 3+ distinct variants per section (when 4+ groups exist)
2. **Symmetry**: Paired groups (Left/Right) should show the same variant name
3. **Continuity**: Adjacent sections should share at least 1 variant on a tier 5-8 group
4. **Energy match**: Chorus sections should show high-energy variants; verse sections should show low/medium
