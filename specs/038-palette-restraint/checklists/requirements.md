# Requirements Checklist: 038 Palette Restraint

## User Stories

- [x] US1 (P1): Restrained Color Count -- palettes use 2-4 active colors instead of all 8
- [x] US2 (P2): Hero Props Get More Palette Variety -- hero models get richer palettes than simple props
- [x] US3 (P3): MusicSparkles on Pattern Effects -- audio-reactive sparkle overlay on pattern-based effects
- [x] US4 (P3): Custom SparkleFrequency -- sparkle intensity scales with section energy
- [x] US5 (P2): Accent Colors for High-Energy Sections -- choruses expand to 4-6 active colors

## Acceptance Scenarios

### US1 - Restrained Color Count
- [x] Theme with 4 colors: only 4 slots active, remaining 4 inactive
- [x] Theme with 6+ colors: generator selects 2-4 active per placement
- [x] Average active colors across all palettes is between 2.0 and 4.0
- [x] Theme with 1-2 colors: all defined colors active (minimum 1)

### US2 - Hero Props Get More Palette Variety
- [x] Hero-tier models receive wider palette selection (up to 5-6 active in high-energy)
- [x] Base-tier models stay at 2-3 active colors consistently
- [x] Hero-tier models have at least 30% more unique palette assignments than base-tier

### US3 - MusicSparkles on Pattern Effects
- [x] Pattern-based effects (SingleStrand, Bars, Pinwheel) may get MusicSparkles
- [x] Audio-reactive effects (VU Meter) never get MusicSparkles
- [x] 10-30% of palettes have MusicSparkles enabled in a generated sequence
- [x] Low-energy sections use MusicSparkles less frequently than high-energy sections

### US4 - Custom SparkleFrequency
- [x] High-energy sections get higher SparkleFrequency
- [x] Low-energy sections get lower SparkleFrequency
- [x] Measurable correlation between section energy and sparkle frequency

### US5 - Accent Colors for High-Energy Sections
- [x] High-energy sections (energy > 70) may expand to 4-6 active colors
- [x] Low-energy sections (energy < 40) stay at 2-3 active colors
- [x] High-energy sections average at least 1 more active color than low-energy

## Edge Cases
- [x] Theme defines only 1 color: single color active (never zero)
- [x] MusicSparkles suppressed on audio-reactive effects (VU Meter)
- [x] Uniform energy song: degrades gracefully to base 2-4 colors everywhere
- [x] Feature toggle disabled: reverts to previous all-slots-active behavior
- [x] MusicSparkles on short-duration effects (under 500ms): still serialized

## Functional Requirements
- [x] FR-001: Palette serializer activates only 2-4 color slots by default
- [x] FR-002: Minimum active count equals theme-defined colors (min 1)
- [x] FR-003: Active color count scales with section energy (2-3 low, up to 5-6 high)
- [x] FR-004: Hero-tier models get more palette variety than base-tier
- [x] FR-005: Palette serializer supports MusicSparkles attribute
- [x] FR-006: MusicSparkles suppressed on audio-reactive effects
- [x] FR-007: SparkleFrequency scales with section energy when MusicSparkles enabled
- [x] FR-008: MusicSparkles percentage between 10% and 30% of palettes
- [x] FR-009: All behaviors independently toggleable via feature flag
- [x] FR-010: No changes outside palette serialization and color selection

## Success Criteria
- [x] SC-001: Average active colors per palette between 2.0 and 4.0
- [x] SC-002: No palette exceeds 6 active color slots
- [x] SC-003: High-energy sections average 1+ more active colors than low-energy
- [x] SC-004: 10-30% of palettes have MusicSparkles (pattern-based sequences)
- [x] SC-005: SparkleFrequency values vary with section energy
- [x] SC-006: Hero-tier models show 30%+ more unique palettes than base-tier
- [x] SC-007: Feature toggle off produces byte-identical output (no regression)
- [x] SC-008: Existing test suite passes with toggle both enabled and disabled

## Structural Completeness
- [x] Spec includes User Scenarios & Testing section with prioritized stories
- [x] Spec includes Given/When/Then acceptance scenarios for all stories
- [x] Spec includes Edge Cases section
- [x] Spec includes Functional Requirements section
- [x] Spec includes Key Entities section
- [x] Spec includes Success Criteria with measurable outcomes
- [x] Spec includes Assumptions section
- [x] Spec includes Relationship to Other Phases section
- [x] All requirements are testable
- [x] All success criteria are measurable and technology-agnostic
- [x] No implementation details (no language/framework/API mentions)
- [x] Written for non-technical stakeholders
