# Feature Specification: MusicSparkles + Rotation Value Curves

**Feature Branch**: `040-sparkles-value-curves`
**Created**: 2026-04-09
**Status**: Draft
**Input**: Phase 5 of the Sequence Quality Refinement (035). Adds audio-reactive sparkle overlays and animated value curves to sustained effects, matching techniques observed across all 5 reference sequences.

## User Scenarios & Testing

### User Story 1 - MusicSparkles on Pattern Effects (Priority: P1)

As a user generating a sequence, I want pattern-based effects (SingleStrand, Bars, Pinwheel, Spirals, Curtain, Ripple) to have an audio-reactive sparkle overlay enabled on a percentage of their palettes, so that the sequence has the same visual liveliness seen in hand-sequenced community files where 8-30% of palettes use MusicSparkles.

**Why this priority**: MusicSparkles is the most widely used audio-reactive palette feature in the reference sequences, appearing in 3 of 5 analyzed files. Our generator never enables it, which is the single biggest missing "polish" feature. Pattern effects without sparkles look flat compared to reference sequences.

**Independent Test**: Generate a sequence for any song. Analyze the output with the reference analyzer tool. Count the percentage of palettes that have MusicSparkles enabled, and verify it falls within the 10-30% range. Verify that MusicSparkles never appears on audio-reactive effects (VU Meter).

**Acceptance Scenarios**:

1. **Given** a placement using a pattern-based effect (SingleStrand, Bars, Pinwheel, Spirals, Curtain, Ripple), **When** the palette is generated, **Then** MusicSparkles has a probability of being enabled based on section energy level.
2. **Given** a placement using an audio-reactive effect (VU Meter), **When** the palette is generated, **Then** MusicSparkles is NOT enabled, because the effect itself already responds to audio.
3. **Given** a generated sequence for any song, **When** analyzed with the reference tool, **Then** between 10% and 30% of palettes have MusicSparkles enabled.
4. **Given** a song classified as gentle or low-energy overall, **When** a sequence is generated, **Then** the MusicSparkles percentage is toward the lower end of the range (closer to 8-15%), matching the restraint seen in "Away In A Manger."

---

### User Story 2 - SparkleFrequency Customization (Priority: P1)

As a user, I want MusicSparkles to have a tuned SparkleFrequency value rather than always using the default, so that the sparkle density matches the song's character -- denser sparkles for high-energy sections, sparser for calm sections.

**Why this priority**: Reference sequences customize SparkleFrequency extensively (6-57 palettes per sequence with custom values). Using only the default frequency produces a one-size-fits-all sparkle that does not respond to the song's energy dynamics.

**Independent Test**: Generate a sequence. Inspect the output for palettes with MusicSparkles enabled. Verify that SparkleFrequency values vary across sections and correlate with section energy.

**Acceptance Scenarios**:

1. **Given** a palette with MusicSparkles enabled in a high-energy section (energy > 70), **When** SparkleFrequency is set, **Then** it uses a higher frequency value to produce denser sparkles.
2. **Given** a palette with MusicSparkles enabled in a low-energy section (energy < 40), **When** SparkleFrequency is set, **Then** it uses a lower frequency value to produce sparser, subtler sparkles.
3. **Given** a generated sequence, **When** palettes with MusicSparkles are analyzed, **Then** at least two distinct SparkleFrequency values are used across the sequence (not all identical).

---

### User Story 3 - Rotation Value Curves on Sustained Effects (Priority: P1)

As a user, I want effects lasting longer than 2 seconds to have rotation value curves applied when the effect supports rotation, so that sustained effects have internal animation (gradual sweep, oscillation) rather than appearing static for their entire duration.

**Why this priority**: All 5 reference sequences use rotation value curves. They are the primary technique for adding visual movement to sustained effects without changing the effect itself. "Light of Christmas" applies Ramp rotation curves on Curtain, Pictures, Ripple, Spirals, and Warp. Without rotation curves, our sustained effects look frozen compared to reference sequences.

**Independent Test**: Generate a sequence for a song with moderate-to-slow tempo. Count the number of effects lasting >2 seconds that have rotation value curves. The percentage should be comparable to reference sequences.

**Acceptance Scenarios**:

1. **Given** an effect placement lasting more than 2 seconds on an effect that supports rotation, **When** the effect is written to the output, **Then** a rotation value curve is applied (typically a Ramp-type curve producing a gradual sweep).
2. **Given** an effect placement lasting less than 1 second, **When** the effect is written, **Then** no rotation value curve is applied, because the effect is too short for the animation to be perceptible.
3. **Given** an effect placement lasting between 1 and 2 seconds, **When** the effect is written, **Then** a rotation value curve MAY be applied but is not required.
4. **Given** a generated sequence, **When** analyzed, **Then** the percentage of sustained effects (>2s) with rotation value curves is at least 40%.

---

### User Story 4 - Parameter Value Curves for Advanced Animation (Priority: P2)

As a user, I want selected effect parameters (beyond rotation) to use value curves tied to section energy or beat patterns, so that effects exhibit dynamic parameter changes over time -- such as Wave height pulsing with beats, or Blur intensity following energy.

**Why this priority**: This is a more advanced enhancement beyond basic rotation curves. "Shut Up and Dance" uses Saw Tooth curves on Wave Thickness and Height tied to drum timing. "Away In A Manger" uses Blur value curves on Bars. These techniques add sophisticated animation but are less universally applied than rotation curves.

**Independent Test**: Generate a sequence containing Wave or Bars effects. Verify that at least some of these effects have parameter-specific value curves (e.g., height, thickness, or blur parameters with curve data).

**Acceptance Scenarios**:

1. **Given** a Wave effect placement lasting more than 2 seconds, **When** written to output, **Then** parameter-specific value curves (such as height or thickness) MAY be applied based on section energy.
2. **Given** a Bars effect placement in a section with energy > 60, **When** written, **Then** a Blur or speed value curve MAY be applied to add visual dynamics.
3. **Given** a Pinwheel effect lasting more than 3 seconds, **When** written, **Then** a Twist value curve MAY be applied to create oscillating twist animation.

---

### User Story 5 - Feature Toggle for Independent Control (Priority: P2)

As a user or developer, I want MusicSparkles and value curves to be independently toggleable, so that each enhancement can be enabled, disabled, or tested in isolation without affecting other generator behaviors or prior phase improvements.

**Why this priority**: Consistent with the phasing strategy from the parent specification. Each improvement must be independently verifiable and revertable. This is critical for validation and debugging.

**Independent Test**: Generate a sequence with MusicSparkles enabled but value curves disabled, and vice versa. Verify that each toggle controls only its own feature with no side effects on other generation behaviors.

**Acceptance Scenarios**:

1. **Given** MusicSparkles is disabled and value curves are enabled, **When** a sequence is generated, **Then** zero palettes have MusicSparkles but sustained effects still have rotation curves.
2. **Given** MusicSparkles is enabled and value curves are disabled, **When** a sequence is generated, **Then** palettes on pattern effects have MusicSparkles but no effects have rotation or parameter value curves.
3. **Given** both features are disabled, **When** a sequence is generated, **Then** the output is identical to the output produced before this phase was implemented.

---

### Edge Cases

- What happens when a song's effects are ALL audio-reactive (e.g., VU Meter dominant like "Shut Up and Dance")? MusicSparkles should not be applied to any palettes, resulting in 0% MusicSparkles -- this is correct and expected behavior.
- What happens when all effects in a sequence are shorter than 1 second (very fast tempo song)? No rotation value curves should be applied. This is correct -- short effects do not benefit from curves.
- What happens when an effect definition does not support rotation? The system should skip rotation curve generation for that effect without error.
- What happens when energy data is unavailable for a section? SparkleFrequency and curve parameters should fall back to moderate default values rather than failing.
- What happens when the existing value curve framework produces analysis-mapped curves AND this phase adds rotation curves? Both should coexist without conflict -- rotation curves and analysis-mapped parameter curves operate on different parameters.

## Requirements

### Functional Requirements

- **FR-001**: The generator MUST support enabling MusicSparkles on palettes associated with pattern-based effects. The set of pattern-based effects eligible for MusicSparkles MUST be configurable.
- **FR-002**: The generator MUST NOT enable MusicSparkles on palettes associated with audio-reactive effects (such as VU Meter), because the sparkle overlay is redundant with the effect's built-in audio reactivity.
- **FR-003**: The probability of enabling MusicSparkles on an eligible palette MUST be influenced by section energy level, producing higher rates in energetic sections and lower rates in calm sections.
- **FR-004**: When MusicSparkles is enabled, the generator MUST set a SparkleFrequency value that varies with section energy. Higher energy sections MUST produce denser sparkle frequencies; lower energy sections MUST produce sparser frequencies.
- **FR-005**: Effects lasting more than 2 seconds that support rotation MUST have a rotation value curve applied. The default curve type MUST be a gradual ramp (linear sweep over the effect duration).
- **FR-006**: Effects lasting less than 1 second MUST NOT have rotation value curves applied.
- **FR-007**: The generator SHOULD support parameter-specific value curves (beyond rotation) for effects that define curve-eligible parameters, such as Wave height, Pinwheel twist, and Bars blur.
- **FR-008**: MusicSparkles and value curves MUST be independently toggleable. Disabling one MUST NOT affect the other. Disabling both MUST produce output identical to the pre-phase baseline.
- **FR-009**: The rotation curve behavior MUST coexist with any existing value curve generation (such as analysis-mapped energy curves) without conflict or overwriting.
- **FR-010**: The overall MusicSparkles rate across a generated sequence MUST fall within the 10-30% range of total palettes, consistent with the reference sequence observations.

### Key Entities

- **SparklePolicy**: Determines whether a given effect placement is eligible for MusicSparkles, the probability of enabling it, and the SparkleFrequency value. Driven by effect type and section energy.
- **RotationCurve**: A value curve specification applied to an effect's rotation parameter. Defined by curve type (Ramp, Saw Tooth, Custom), direction, and speed relative to effect duration.
- **ParameterCurve**: A value curve specification applied to an effect-specific parameter (e.g., Wave height, Pinwheel twist, Bars blur). Defined by curve type, target parameter name, and amplitude.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Generated sequences have MusicSparkles enabled on 10-30% of palettes when the song uses pattern-based effects. Sequences dominated by audio-reactive effects (VU Meter) correctly produce 0% MusicSparkles.
- **SC-002**: SparkleFrequency values in generated sequences use at least 2 distinct values, correlating with section energy differences.
- **SC-003**: At least 40% of effects lasting >2 seconds in a generated sequence have rotation value curves applied.
- **SC-004**: No effects lasting <1 second have rotation value curves applied.
- **SC-005**: Toggling MusicSparkles off produces zero MusicSparkles palettes with no other output changes. Toggling value curves off produces zero value curves with no other output changes.
- **SC-006**: The reference analyzer tool, when run on generated output, shows MusicSparkles and value curve metrics within the ranges observed in the 5 reference sequences.
- **SC-007**: No regression in the existing test suite when both features are disabled.

## Assumptions

- The 5 reference sequences analyzed in `docs/reference-sequence-analysis.md` are representative of good MusicSparkles and value curve practices. The 8-30% MusicSparkles range and universal presence of rotation curves across all references provides a reliable target.
- The existing value curve framework (`value_curves.py` and `_encode_value_curve()` in the XSQ writer) provides sufficient infrastructure for writing rotation and parameter curves. No new output format is needed.
- Effect definitions include sufficient metadata to determine whether an effect supports rotation and which parameters are curve-eligible. If this metadata is incomplete, it can be extended without affecting other phases.
- Section energy data from the analysis hierarchy is available and reliable for driving MusicSparkles probability and SparkleFrequency values. No new audio analysis is required.
- MusicSparkles is a palette-level feature (not an effect-level feature) and applies a sparkle overlay regardless of which layer the effect is on. This matches xLights behavior.

## Relationship to Other Phases

This is **Phase 5 of 5** in the Sequence Quality Refinement plan (035-sequence-quality-refinement), and the final polish layer.

| Phase | Spec | Focus | Status |
|-------|------|-------|--------|
| Phase 1 | 036-focused-effects-repetition | Focused vocabulary + embrace repetition | Sibling |
| Phase 2 | 037-duration-scaling | Duration matches song energy | Sibling |
| Phase 3 | 038-palette-restraint | Palette color restraint (2-4 active colors) | Sibling |
| Phase 4 | 039-dynamic-model-activation | Dynamic model activation by section | Sibling |
| **Phase 5** | **040-sparkles-value-curves** | **MusicSparkles + rotation value curves** | **This spec** |

**Dependencies**: This phase benefits from all prior phases but can be implemented independently. Specifically:
- Phase 3 (Palette Restraint) affects how palettes are structured. MusicSparkles is additive to the palette and does not conflict with reduced active color counts.
- Phase 1 (Focused Vocabulary) determines which effects are placed. MusicSparkles eligibility depends on effect type, so the effect pool composition affects sparkle rates.
- Phase 2 (Duration Scaling) determines effect durations. Value curve application depends on duration thresholds, so duration strategy affects how many effects receive curves.

**Independence**: Despite these relationships, this phase requires no changes from prior phases to function. It reads effect type and duration from whatever the generator produces and applies sparkles/curves accordingly. If prior phases are not implemented, this phase still works -- it just operates on the existing effect pool and duration distribution.
