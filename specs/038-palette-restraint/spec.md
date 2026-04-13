# Feature Specification: Palette Restraint

**Feature Branch**: `038-palette-restraint`
**Created**: 2026-04-09
**Status**: Draft
**Input**: Phase 3 of the Sequence Quality Refinement plan (035). Reduce active palette colors from all 8 slots to 2-4, matching the 2.8 average observed in reference sequences. Add MusicSparkles and SparkleFrequency support as optional palette enhancements.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Restrained Color Count (Priority: P1)

As a user generating a sequence, I want palettes to use only 2-4 active colors
rather than filling all 8 slots, so that color schemes look clean and intentional --
like the focused palettes seen in hand-sequenced community files.

**Why this priority**: This is the core of the feature. Reference analysis shows an
average of 2.7-3.1 active colors per palette across 4 of 5 sequences. Our generator
currently activates every color the theme defines (up to 8), creating muddy, unfocused
color schemes. Reducing active colors is the single most impactful palette change.

**Independent Test**: Generate a sequence for any song, run the reference analyzer on
the output. The average active colors per palette should be between 2 and 4.

**Acceptance Scenarios**:

1. **Given** a theme that defines 4 colors, **When** a palette is serialized to the
   sequence file, **Then** only those 4 color slots have active checkboxes; the
   remaining 4 slots are populated with default colors but marked inactive.
2. **Given** a theme that defines 6 or more colors, **When** a palette is serialized,
   **Then** the generator selects 2-4 of those colors as active for each placement
   based on the section context, rather than activating all 6+.
3. **Given** a generated sequence for any song, **When** all palettes are analyzed,
   **Then** the average active colors per palette is between 2.0 and 4.0.
4. **Given** a theme that defines only 1-2 colors, **When** a palette is serialized,
   **Then** all defined colors are active (never fewer than the theme provides, minimum 1).

---

### User Story 2 - Hero Props Get More Palette Variety (Priority: P2)

As a user, I want hero props (matrices, mega trees) to receive more palette variety
than simple props (arches, candy canes), so that visually prominent models have
richer color treatment while background props stay restrained -- matching the layered
approach seen in reference sequences.

**Why this priority**: Reference analysis shows hero props have more layers and more
palette variation than simple props. This adds visual depth without making the overall
palette count excessive. It depends on the base restraint from Story 1 being in place.

**Independent Test**: Generate a sequence with a layout containing both hero and simple
prop groups. Analyze palette diversity per model tier. Hero-tier models should show
more unique palettes than base-tier models.

**Acceptance Scenarios**:

1. **Given** a hero-tier model (matrix, mega tree), **When** palettes are assigned
   across sections, **Then** the model receives a wider selection of palette variations
   (up to 5-6 active colors in high-energy sections).
2. **Given** a base-tier model (arch, candy cane, icicle), **When** palettes are
   assigned, **Then** the model uses 2-3 active colors consistently.
3. **Given** a generated sequence, **When** palette diversity is compared across tiers,
   **Then** hero-tier models have at least 30% more unique palette assignments than
   base-tier models.

---

### User Story 3 - MusicSparkles on Pattern Effects (Priority: P3)

As a user, I want the generator to enable MusicSparkles on appropriate palettes, so
that pattern-based effects gain an audio-reactive sparkle overlay -- a technique used
in up to 30% of palettes in pattern-heavy reference sequences.

**Why this priority**: MusicSparkles is an additive enhancement that increases visual
interest on pattern effects. It is used meaningfully in reference sequences (8-30%
of palettes) but our generator ignores it entirely. Lower priority because it is polish
on top of the structural palette changes.

**Independent Test**: Generate a sequence, inspect palettes for MusicSparkles presence.
Verify it appears on 10-30% of palettes and only on pattern-based effect types.

**Acceptance Scenarios**:

1. **Given** a placement using a pattern-based effect (e.g., SingleStrand, Bars,
   Pinwheel), **When** the palette is generated, **Then** MusicSparkles may be enabled
   based on section energy and effect type.
2. **Given** a placement using an audio-reactive effect (e.g., VU Meter), **When** the
   palette is generated, **Then** MusicSparkles is NOT enabled (it would be redundant).
3. **Given** a generated sequence, **When** all palettes are analyzed, **Then** between
   10% and 30% of palettes have MusicSparkles enabled.
4. **Given** a low-energy section (e.g., a gentle verse), **When** palettes are generated,
   **Then** MusicSparkles is used less frequently than in high-energy sections.

---

### User Story 4 - Custom SparkleFrequency (Priority: P3)

As a user, I want palettes that have MusicSparkles enabled to use a customized sparkle
frequency rather than the default, so that the sparkle intensity matches the song energy
and section mood -- as seen in reference sequences where 6-57 palettes per sequence have
custom SparkleFrequency values.

**Why this priority**: This is a refinement on top of MusicSparkles support. Custom
SparkleFrequency values allow the sparkle intensity to scale with section energy --
brighter/denser sparkles in high-energy choruses, subtle in verses.

**Independent Test**: Generate a sequence, inspect palettes with MusicSparkles enabled.
Verify that SparkleFrequency varies by section energy rather than using a single default.

**Acceptance Scenarios**:

1. **Given** a palette with MusicSparkles enabled in a high-energy section, **When** the
   palette is serialized, **Then** SparkleFrequency is set to a higher value (more
   frequent sparkles).
2. **Given** a palette with MusicSparkles enabled in a low-energy section, **When** the
   palette is serialized, **Then** SparkleFrequency is set to a lower value (subtler
   sparkles).
3. **Given** a generated sequence, **When** SparkleFrequency values are analyzed across
   all MusicSparkles palettes, **Then** there is measurable correlation between section
   energy and sparkle frequency.

---

### User Story 5 - Accent Colors for High-Energy Sections (Priority: P2)

As a user, I want high-energy sections (choruses, drops) to gain additional accent
colors beyond the base palette, so that energy peaks feel visually richer without
making the base palette muddy -- matching the reference pattern where some palettes
use up to 5-6 active colors for impact moments.

**Why this priority**: This provides dynamic range in palette complexity across the
song. Verses stay clean at 2-3 colors; choruses expand to 4-5 for visual richness.
The Shut Up and Dance reference (5.5 average) shows that high-energy songs justify
more colors.

**Independent Test**: Generate a sequence for a song with clear verse/chorus structure.
Compare average active colors in low-energy vs high-energy sections. High-energy
sections should average 1-2 more active colors.

**Acceptance Scenarios**:

1. **Given** a high-energy section (energy > 70), **When** palettes are generated,
   **Then** accent colors may be added as additional active slots, raising the active
   count to 4-6 (but never exceeding 6).
2. **Given** a low-energy section (energy < 40), **When** palettes are generated,
   **Then** the active color count stays at 2-3, with no accent color additions.
3. **Given** a generated sequence, **When** active color counts are compared between
   low-energy and high-energy sections, **Then** high-energy sections average at
   least 1 more active color than low-energy sections.

---

### Edge Cases

- What happens when a theme defines only 1 color? The palette uses that single color
  as active. The minimum active count is 1 (never zero).
- What happens when MusicSparkles is enabled on an effect that already has built-in
  audio reactivity (VU Meter)? MusicSparkles is suppressed for that placement to
  avoid redundant reactivity.
- What happens when all sections in a song have similar energy (no verse/chorus
  contrast)? Accent color logic degrades gracefully to the base 2-4 color count
  for all sections. No forced variation.
- What happens when the feature toggle is disabled? The generator reverts to its
  previous behavior of activating all theme-defined colors. No other Phase 3 behavior
  is active.
- What happens when a palette has MusicSparkles enabled but the effect duration is
  very short (under 500ms)? MusicSparkles should still be serialized -- the xLights
  renderer handles the short duration appropriately.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The palette serializer MUST activate only 2-4 color slots per palette
  by default, regardless of how many colors the theme defines (up to 8 may be
  populated in slots, but only 2-4 marked active via checkboxes).
- **FR-002**: When a theme defines fewer than 2 colors, the serializer MUST activate
  all defined colors (minimum active count equals the number of theme-defined colors,
  minimum 1).
- **FR-003**: The generator MUST support scaling the active color count by section
  energy: low-energy sections use 2-3 active colors; high-energy sections may use
  up to 5-6 active colors via accent additions.
- **FR-004**: Hero-tier models (matrices, mega trees, large display props) MUST
  receive more palette variety than base-tier models (simple linear props).
- **FR-005**: The palette serializer MUST support emitting MusicSparkles as a palette
  attribute on pattern-based effects.
- **FR-006**: MusicSparkles MUST NOT be enabled on audio-reactive effects (e.g.,
  VU Meter) where it would be redundant.
- **FR-007**: When MusicSparkles is enabled, the palette MUST support a custom
  SparkleFrequency value that scales with section energy.
- **FR-008**: The overall percentage of palettes with MusicSparkles in a generated
  sequence MUST fall between 10% and 30%.
- **FR-009**: All palette restraint behaviors MUST be independently toggleable via a
  feature flag, allowing reversion to the previous "all slots active" behavior.
- **FR-010**: Palette restraint MUST NOT alter any behavior outside of palette
  serialization and color selection. Effect choice, duration, model activation,
  and all other generation behaviors remain unchanged.

### Key Entities

- **ActivePalette**: A palette with a designated subset of its color slots marked
  as active. Carries the count of active colors (2-4 base, up to 6 with accents),
  the MusicSparkles flag, and the SparkleFrequency value.
- **PaletteEnergyProfile**: A mapping from section energy levels to target active
  color counts and MusicSparkles probability. Drives the dynamic scaling of palette
  complexity across the song.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Average active colors per palette in generated sequences is between
  2.0 and 4.0 (reference average: 2.8).
- **SC-002**: No palette in a generated sequence has more than 6 active color slots
  (hard ceiling).
- **SC-003**: High-energy sections average at least 1 more active color per palette
  than low-energy sections in the same sequence.
- **SC-004**: Between 10% and 30% of palettes in a generated sequence have
  MusicSparkles enabled, when the song uses pattern-based effects.
- **SC-005**: SparkleFrequency values in a generated sequence show measurable
  variation (not all identical) correlated with section energy.
- **SC-006**: Hero-tier models show at least 30% more unique palette assignments
  than base-tier models.
- **SC-007**: When the feature toggle is disabled, generated sequences are
  byte-identical to sequences generated without the feature present (no regression).
- **SC-008**: Existing test suite passes with no failures when the feature toggle
  is both enabled and disabled.

## Assumptions

- Reference sequences from 5 community .xsq files are representative of good
  palette practices. The 2.7-3.1 average active colors (4 of 5 sequences) is the
  target range; the Shut Up and Dance outlier (5.5) represents VU Meter-heavy
  sequences where more colors serve the spectrogram visualization.
- The existing theme color definitions provide sufficient color data to select
  2-4 active colors from. No new color generation or color theory logic is needed.
- Section energy values from the analysis hierarchy are available and reliable
  enough to drive palette energy scaling. No new audio analysis is required.
- MusicSparkles and SparkleFrequency are standard xLights palette attributes
  that the xLights renderer handles natively. No custom rendering is needed.
- The `analyze_reference_xsq.py` tool already reports active color counts and
  MusicSparkles percentages, providing the comparison mechanism for validation.

## Relationship to Other Phases

This is **Phase 3 of 5** in the Sequence Quality Refinement plan (spec 035).

| Phase | Feature | Status | Dependency on Phase 3 |
|-------|---------|--------|-----------------------|
| Phase 1 | Focused Effects + Repetition (036) | Separate | None -- independent |
| Phase 2 | Duration Scaling (037) | Separate | None -- independent |
| **Phase 3** | **Palette Restraint (038)** | **This spec** | -- |
| Phase 4 | Dynamic Model Activation (039) | Separate | None -- independent |
| Phase 5 | MusicSparkles + Value Curves (040) | Separate | Phase 5 US6 (MusicSparkles) overlaps with this spec's US3/US4; if Phase 3 ships first, Phase 5 inherits the MusicSparkles foundation |

Phase 3 is fully independent of all other phases. It modifies only palette
serialization and color selection logic. It does not change effect vocabulary,
duration, repetition behavior, or model activation -- those are handled by
their respective phases.

The MusicSparkles stories (US3, US4) in this spec overlap with Phase 5 User
Story 6 from the parent spec. If Phase 3 delivers MusicSparkles support, Phase 5
can build on it for additional refinements (e.g., tying MusicSparkles to timing
tracks). If Phase 5 ships first, Phase 3 can skip US3/US4.

Each phase can be individually enabled/disabled via feature flags, and the
reference analyzer validates each phase's metrics independently.
