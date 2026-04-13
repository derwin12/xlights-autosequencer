# Requirements Checklist: MusicSparkles + Rotation Value Curves (040)

Phase 5 of 5 -- Sequence Quality Refinement (035)

## Functional Requirements

- [x] **FR-001**: MusicSparkles support on pattern-based effect palettes with configurable eligible effect set
- [x] **FR-002**: MusicSparkles exclusion on audio-reactive effects (VU Meter)
- [x] **FR-003**: MusicSparkles probability influenced by section energy level
- [x] **FR-004**: SparkleFrequency varies with section energy (denser for high energy, sparser for low)
- [x] **FR-005**: Rotation value curves on effects lasting >2 seconds that support rotation (Ramp default)
- [x] **FR-006**: No rotation value curves on effects lasting <1 second
- [x] **FR-007**: Parameter-specific value curves for eligible effect parameters (Wave height, Pinwheel twist, Bars blur)
- [x] **FR-008**: Independent toggles for MusicSparkles and value curves with no cross-feature side effects
- [x] **FR-009**: Rotation curves coexist with existing analysis-mapped value curves without conflict
- [x] **FR-010**: Overall MusicSparkles rate within 10-30% of total palettes

## User Stories

- [x] **US-1 (P1)**: MusicSparkles on pattern effects -- 10-30% of palettes, never on audio-reactive effects
- [x] **US-2 (P1)**: SparkleFrequency customization -- varies by section energy, at least 2 distinct values per sequence
- [x] **US-3 (P1)**: Rotation value curves on sustained effects -- Ramp curves on >2s effects, skip <1s effects
- [x] **US-4 (P2)**: Parameter value curves for advanced animation -- Wave, Bars, Pinwheel parameter curves
- [x] **US-5 (P2)**: Feature toggle for independent control -- each feature independently enable/disable

## Acceptance Scenarios

### MusicSparkles

- [x] Pattern-based effects (SingleStrand, Bars, Pinwheel, Spirals, Curtain, Ripple) eligible for MusicSparkles
- [x] Audio-reactive effects (VU Meter) never receive MusicSparkles
- [x] Generated sequence has 10-30% MusicSparkles palettes for pattern-heavy songs
- [x] Gentle/low-energy songs produce MusicSparkles toward lower end (8-15%)
- [x] VU Meter-dominant songs produce 0% MusicSparkles (correct behavior)

### SparkleFrequency

- [x] High-energy sections (>70) produce higher SparkleFrequency values
- [x] Low-energy sections (<40) produce lower SparkleFrequency values
- [x] At least 2 distinct SparkleFrequency values used across a sequence

### Rotation Value Curves

- [x] Effects >2 seconds with rotation support receive Ramp rotation curve
- [x] Effects <1 second never receive rotation curves
- [x] Effects 1-2 seconds may optionally receive rotation curves
- [x] At least 40% of >2s effects have rotation value curves
- [x] Rotation curves coexist with existing analysis-mapped curves

### Parameter Value Curves

- [x] Wave effects >2s may receive height/thickness value curves
- [x] Bars effects in high-energy sections may receive blur value curves
- [x] Pinwheel effects >3s may receive twist value curves

### Feature Toggles

- [x] MusicSparkles disabled + value curves enabled: zero sparkle palettes, curves still present
- [x] MusicSparkles enabled + value curves disabled: sparkle palettes present, zero curves
- [x] Both disabled: output identical to pre-phase baseline

## Edge Cases

- [x] All-audio-reactive sequence (VU Meter dominant): 0% MusicSparkles is correct
- [x] All effects <1 second (very fast song): 0 rotation curves is correct
- [x] Effect does not support rotation: skipped without error
- [x] Section energy data unavailable: falls back to moderate defaults
- [x] Rotation curves and analysis-mapped curves on same effect: no conflict

## Success Criteria

- [x] **SC-001**: MusicSparkles 10-30% for pattern songs, 0% for audio-reactive songs
- [x] **SC-002**: At least 2 distinct SparkleFrequency values per sequence
- [x] **SC-003**: At least 40% of >2s effects have rotation value curves
- [x] **SC-004**: Zero <1s effects have rotation value curves
- [x] **SC-005**: Independent toggle verification (no cross-feature impact)
- [x] **SC-006**: Reference analyzer metrics within reference sequence ranges
- [x] **SC-007**: No test regression when both features disabled

## Phase Relationship

- [x] Spec identifies this as Phase 5 of 5 in the refinement plan
- [x] Dependencies on Phase 1 (effect pool), Phase 2 (duration), Phase 3 (palettes) documented
- [x] Independence confirmed: works without prior phases implemented
- [x] Parent spec (035) user stories US6 and US7 fully covered
