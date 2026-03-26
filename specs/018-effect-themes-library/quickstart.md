# Quickstart: xLights Effect Library

**Date**: 2026-03-26
**Branch**: `018-effect-themes-library`

---

## What This Is

A JSON catalog of 35+ xLights effects with their parameters, prop-type suitability ratings, and analysis-to-parameter mappings. It's the data layer that the Themes engine and sequence generator will consume.

---

## Using the Library in Code

```python
from src.effects.library import load_effect_library

# Load built-in + any custom overrides
library = load_effect_library()

# Look up an effect
fire = library.get("Fire")
print(fire.description)         # "Simulates rising flame animation..."
print(fire.parameters[0].name)  # "Fire_Height"
print(fire.parameters[0].min)   # 1
print(fire.parameters[0].max)   # 100

# Find effects good for matrices
matrix_effects = library.for_prop_type("matrix")
for e in matrix_effects:
    print(f"{e.name}: {e.prop_suitability['matrix']}")

# Check coverage
coverage = library.coverage()
print(f"{len(coverage.cataloged)}/{coverage.total_xlights} effects cataloged")
```

---

## Customizing an Effect

1. Find the built-in definition in `src/effects/builtin_effects.json`
2. Copy the effect's JSON block to `~/.xlight/custom_effects/Fire.json`
3. Edit parameters, suitability, or mappings as needed
4. Next time the library loads, your custom version overrides the built-in

---

## Understanding Analysis Mappings

Each mapping tells the sequence generator how to connect audio analysis to an effect parameter:

```json
{
  "parameter": "Fire_Height",
  "analysis_level": "L5",
  "analysis_field": "energy_curves.bass",
  "mapping_type": "direct",
  "description": "Bass energy drives flame height"
}
```

**Mapping types**:
- `direct` — analysis value scales the parameter proportionally
- `inverted` — higher analysis value → lower parameter value
- `threshold_trigger` — crossing a threshold triggers a discrete change
