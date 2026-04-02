# Research: Value Curves Integration

**Feature**: 032-value-curves-integration
**Date**: 2026-04-02

## R1: Activation Strategy

**Decision**: Activate value curves by calling `generate_value_curves()` for each placement inside `build_plan()` at the existing disabled location (line 151 of `plan.py`), filtered by the new `curves_mode` config setting.

**Rationale**: The function, data model, xSQ encoding, and tests all exist and pass. The disable was a Phase 1 gate to validate static rendering first. Rather than modifying `effect_placer.py`, apply curves post-placement in `build_plan()` — matching the existing pattern in `regenerate_sections()` (lines 296-298).

**Alternatives considered**:
- Integrate into `effect_placer._make_placement()`: Rejected — would couple placement logic with curve generation and require passing hierarchy into the placer's inner functions.
- Generate curves in `xsq_writer.py` at write time: Rejected — writer should serialize, not compute. Curves should be on the model before write.

## R2: Category Filtering Architecture

**Decision**: Add a `curves_mode` field to `GenerationConfig` accepting values: `"all"` (default), `"brightness"`, `"speed"`, `"color"`, `"none"`. The curve generation loop in `build_plan()` checks this mode and only generates curves for matching analysis mapping categories.

**Rationale**: Filtering at the `build_plan` level is simple — iterate mappings, check if the mapping's parameter category matches the mode, skip if not. No changes needed to `generate_value_curves()` itself; instead, filter its output before assigning to `placement.value_curves`.

**Alternatives considered**:
- Filter inside `generate_value_curves()` by adding a `categories` param: Works but changes the tested function signature. Filtering at the call site is less invasive.
- Separate functions per category (`generate_brightness_curves`, etc.): Over-engineered — the single function with post-filtering achieves the same result.

## R3: Parameter Category Classification

**Decision**: Classify parameters into categories based on the analysis mapping's `parameter` name using keyword matching:
- **brightness**: parameters containing "transparency", "brightness", "intensity", "opacity"
- **speed**: parameters containing "speed", "velocity", "rate", "cycles", "rotation"
- **color**: parameters containing "color", "hue", "saturation", "palette"
- All other mapped parameters: included in `"all"` mode only

**Rationale**: The existing `analysis_mappings` in `builtin_effects.json` use descriptive parameter names (e.g., `On_Transparency`, `Bars_Speed`, `Fire_HueShift`). Simple keyword matching on the parameter name is sufficient and doesn't require adding a new `category` field to the AnalysisMapping model.

**Alternatives considered**:
- Add `category` field to AnalysisMapping in the JSON: Cleaner but requires updating 33 effect definitions. Can be done as a follow-up if keyword matching proves insufficient.
- Map by analysis_field instead of parameter name: Energy mappings could be brightness or speed, so the analysis field doesn't cleanly determine category.

## R4: Chord-Triggered Color Accents

**Decision**: Add a new function `apply_chord_accents()` in `value_curves.py` that overlays chord-change-triggered value shifts onto an existing energy-driven color curve. Activation requires: (1) chord data present in hierarchy, (2) chord density >20 events/min, (3) chord quality score >0.4.

**Rationale**: The chord data analysis across 4 songs showed density ranges from 13-41 events/min and quality 0.30-0.60. The thresholds exclude unreliable data (Carmina Burana at 13/min, 0.30) while including viable data (Santa Tell Me at 25/min, 0.60; Mad Russian at 41/min, 0.53).

**Implementation approach**:
1. Generate the base color curve from energy data (existing `generate_value_curves` flow)
2. If chord thresholds are met, iterate chord events within the effect's time range
3. At each chord change, insert a small value shift (+10-20% of range) that decays back over ~500ms
4. This creates "accent pulses" at harmonic boundaries without replacing the energy-driven base curve

**Alternatives considered**:
- Replace energy curve with chord-driven step function: Rejected — creates abrupt jumps and fails on sparse chord data.
- Use chord root note to map to specific palette positions: Interesting but requires a chord-to-color mapping theory. Deferred to future feature.

## R5: CLI and Config Integration

**Decision**: Add `--curves` flag to the `generate` CLI command as a `click.Choice` with options `all`, `brightness`, `speed`, `color`, `none`. Default: `all`. Also add `curves_mode` field to `GenerationConfig` dataclass. The CLI flag populates this field; the generation wizard also presents it as a choice.

**Rationale**: Follows the existing pattern of CLI flags mapping to `GenerationConfig` fields (e.g., `--genre`, `--occasion`, `--tiers`). Config file support via TOML profiles already exists for scoring; extending it for curves_mode is straightforward.

**Alternatives considered**:
- Multiple boolean flags (`--no-brightness-curves`, `--no-speed-curves`): More flexible but verbose. A single mode flag covers the common use cases (all, none, one category).

## R6: Minimum Duration Threshold

**Decision**: Effect placements shorter than 1000ms skip value curve generation and use static parameters. This is checked at the top of the `generate_value_curves()` function.

**Rationale**: A value curve needs meaningful time variation to be useful. At 43fps energy resolution, a 1-second placement has ~43 samples — enough for a curve. Below 1 second, the curve would have too few points to show meaningful variation, and the visual impact is negligible on such short effects.

**Alternatives considered**:
- 500ms threshold: Would allow very short curves with 20+ samples. Possible but the visual benefit is marginal.
- No threshold: Would generate single-point or near-flat curves for beat-length effects, wasting xSQ file size without visual benefit.
