# Data Model: Value Curves Integration

**Feature**: 032-value-curves-integration
**Date**: 2026-04-02

## Entities

This feature modifies one existing entity and adds one new concept. No new entity classes are needed.

### GenerationConfig (modified — src/generator/models.py)

Added field for controlling value curve generation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| curves_mode | str | "all" | Controls which value curve categories are generated: "all", "brightness", "speed", "color", "none" |

All other fields remain unchanged.

### EffectPlacement (existing — src/generator/models.py)

No changes needed. The `value_curves` field already exists:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| value_curves | dict[str, list[tuple[float, float]]] | {} | Maps parameter names to control point lists. Currently always empty (Phase 1 disable). This feature populates it. |

### AnalysisMapping (existing — src/effects/models.py)

No changes needed. Already defines how analysis data maps to parameters:

| Field | Type | Description |
|-------|------|-------------|
| parameter | str | Parameter name (used for category classification: brightness/speed/color) |
| analysis_level | str | Always "L5" currently |
| analysis_field | str | e.g., "energy_curves.overall", "beats.bpm" |
| mapping_type | str | "direct", "inverted", "threshold_trigger" |
| curve_shape | str | "linear", "logarithmic", "exponential", "step" |
| input_min/max | float | Analysis data range |
| output_min/max | float | Parameter value range |

### Parameter Category Classification (new concept — no new model)

Parameters are classified into categories by keyword matching on `AnalysisMapping.parameter`:

| Category | Keywords | Example Parameters |
|----------|----------|-------------------|
| brightness | transparency, brightness, intensity, opacity | On_Transparency, Eff_Brightness |
| speed | speed, velocity, rate, cycles, rotation | Bars_Speed, Meteors_Speed, Spirals_Rotation |
| color | color, hue, saturation, palette | Fire_HueShift, ColorWash_Saturation |
| (other) | everything else | Fire_Height, Meteors_Count — only included in "all" mode |

### Chord Accent Data (derived from hierarchy — no new model)

For chord-triggered color accents, data is extracted from existing hierarchy:

| Source | Field | Used for |
|--------|-------|----------|
| hierarchy.tracks | chordino_chords_full_mix | Chord change timestamps and labels |
| track.quality_score | float 0-1 | Threshold check (>0.4) |
| track.marks | list[TimingMark] | Chord event positions — density calculated as events/min |

## Data Flow

```
GenerationConfig.curves_mode
        │
        ▼
build_plan() iterates placements
        │
        ▼
generate_value_curves(placement, effect_def, hierarchy)
        │
        ├── For each AnalysisMapping on effect_def:
        │     ├── Check supports_value_curve flag
        │     ├── Check category matches curves_mode
        │     ├── Extract analysis data for time range
        │     ├── Apply curve shape transform
        │     └── Downsample to ≤100 points
        │
        ├── If color category + chord thresholds met:
        │     └── apply_chord_accents() overlays accent shifts
        │
        └── Returns dict[param_name, list[(x, y)]]
                │
                ▼
        placement.value_curves = result
                │
                ▼
        xsq_writer encodes inline: Active=TRUE|Id=...|Values=...
```
