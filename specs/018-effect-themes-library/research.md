# Research: xLights Effect Library

**Date**: 2026-03-26
**Branch**: `018-effect-themes-library`

---

## Parameter Data Source

### Decision: Scrape xLights C++ source code from GitHub, then hand-review

**Rationale**: The xLights manual (manual.xlights.org) uses only friendly display names ("Height", "Hue Shift") with no mapping to internal parameter names and no min/max ranges. The xLights source code on GitHub has 100% consistent naming and is the definitive source.

**Alternatives considered**:
- Manual only (from xLights docs) — rejected: no internal names, no ranges
- Pure hand-authoring — rejected: error-prone for 35+ effects × 5-20 params each

### xLights Parameter Naming Convention

Every parameter follows: `{PREFIX}_{WIDGET_TYPE}_{EffectName}_{ParameterName}`

**Prefixes**: `E_` (effect), `B_` (buffer/layer), `C_` (color), `T_` (transition)

**Widget types**:
- `SLIDER_` — integer slider (has min/max)
- `CHECKBOX_` — boolean ("0" or "1")
- `CHOICE_` — dropdown (string value)
- `TEXTCTRL_` — text/numeric input (often float)
- `VALUECURVE_` — value curve serialization (can drive any slider/textctrl)

**Extraction sources per effect**:
- `.h` file: `#define` constants for `*_MIN`, `*_MAX`, `*_DIVISOR`
- `.cpp` `Render()`: `GetValueCurveInt()`, `GetValueCurveDouble()`, `SettingsMap.GetBool()`, `SettingsMap.Get()` calls
- `.cpp` `adjustSettings()`: `E_`-prefixed storage names

### Example: Fire Effect Parameters

| Stored Name | Type | Default | Min | Max |
|---|---|---|---|---|
| `E_SLIDER_Fire_Height` | int | 50 | 1 | 100 |
| `E_SLIDER_Fire_HueShift` | int | 0 | 0 | 100 |
| `E_VALUECURVE_Fire_GrowthCycles` | float | 0.0 | 0 | 20.0 |
| `E_CHECKBOX_Fire_GrowWithMusic` | bool | false | — | — |
| `E_CHOICE_Fire_Location` | choice | "Bottom" | — | Bottom/Top/Left/Right |

---

## xLights .xsq XML Format for Effects

### Decision: Use the EffectDB + ref-index pattern

**Rationale**: This is how xLights natively stores effects. Understanding this format is needed for the downstream sequence generator but also validates our parameter catalog — if our JSON uses the same `E_SLIDER_*` names, the sequence generator can emit them directly.

**Format**:
```xml
<EffectDB>
  <Effect>E_SLIDER_Fire_Height=50,E_CHOICE_Fire_Location=Bottom</Effect>
</EffectDB>
```

Effects reference the DB by index and include timing:
```xml
<Effect ref="0" name="Fire" startTime="1000" endTime="5000" palette="0"/>
```

---

## Analysis Mapping Types

### Decision: Three mapping types — direct, inverted, threshold-trigger

**Rationale**: These cover the three fundamental ways analysis data drives effect parameters:
- **direct**: Analysis value maps proportionally to parameter value (e.g., energy 0-100 → brightness 0-100)
- **inverted**: Higher analysis value → lower parameter value (e.g., energy → slower speed for ethereal moods)
- **threshold-trigger**: Analysis value crossing a threshold triggers a discrete change (e.g., drum onset → shockwave fire)

**Alternatives considered**: Full formula language — rejected per clarification session (over-engineered for v1).

---

## Scraping Strategy

### Decision: One-time scrape + commit as static JSON

**Rationale**: The xLights effect parameter set is stable. A one-time extraction from the GitHub source code, hand-reviewed, and committed as a static JSON file is the simplest approach (Constitution V: Simplicity First). No runtime scraping, no dependency on the xLights repo.

**Process**:
1. Clone/download the xLights repo (or fetch specific files)
2. Parse each `*Effect.cpp` and `*Effect.h` for the 35 target effects
3. Extract parameter names, types, defaults, min/max
4. Hand-review and annotate with intent, prop suitability, analysis mappings
5. Commit as `src/effects/builtin_effects.json`

**Alternatives considered**: Runtime scraping at install time — rejected: brittle, requires network, violates offline constraint.

---

## Real-World Effect Usage (from /Users/rob/sequences/)

Analyzed 4 professional sequences (Believer, Danger Zone, Light of Christmas, Shut Up and Dance) totaling 15,943 effect instances across 33 unique effect types.

### Top effects by usage

| Effect | Instances | In N/4 sequences | Notes |
|--------|-----------|-------------------|-------|
| SingleStrand | 4,786 | 4/4 | The workhorse — uses FX sub-modes like "Fireworks 1D" |
| Shockwave | 3,045 | 3/4 | Beat-sync staple |
| On | 2,996 | 4/4 | Basic solid color blocks |
| Spirals | 784 | 4/4 | Heavy value curve usage |
| Pinwheel | 731 | 4/4 | Heavy value curve usage |
| Shape | 527 | 2/4 | — |
| Shader | 524 | 3/4 | More common than expected — NOT in our v1 catalog |
| Bars | 412 | 3/4 | — |
| Ripple | 399 | 3/4 | — |
| VU Meter | 360 | 2/4 | References timing tracks directly (`"Drum Beats"`) |

### Key findings for analysis mappings

- **Value curves** are heavily used on Spirals (Rotation, Thickness), Pinwheel (ArmSize, Speed), Fan (Revolutions) — these parameters are ideal candidates for analysis-driven automation
- **VU Meter** has `E_CHOICE_VUMeter_TimingTrack` that references timing tracks by name — this creates a direct bridge to our analysis pipeline
- **Fire** has `GrowWithMusic=1` checkbox — built-in music reactivity we should document
- **SingleStrand FX mode** wraps WLED-style sub-effects (e.g., "Fireworks 1D") — the `E_CHOICE_SingleStrand_FX` parameter selects from dozens of presets

### Effects used in real sequences but NOT in our v1 catalog

- **Shader** (524 instances) — worth reconsidering for inclusion
- **Garlands** (11 instances) — low usage but present
- **Video** (8 instances) — requires external media
- **Galaxy** (1 instance) — very rare

---

## Prop Suitability Ratings

### Decision: Hand-curated based on community knowledge and effect characteristics

**Rationale**: No automated way to determine "Fire looks great on matrices but not on single arches." This is domain knowledge from the xLights community. We'll curate initial ratings and users can override via custom definitions.

| Rating | Meaning |
|--------|---------|
| Ideal | Effect was designed for this prop type; looks great with minimal tuning |
| Good | Works well with some parameter adjustment |
| Possible | Can be used but may not look as intended |
| Not Recommended | Effect doesn't translate to this prop type (e.g., matrix-only effects on single-strand outlines) |
