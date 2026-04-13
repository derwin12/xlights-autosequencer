# Feature Specification: Dynamic Model Activation

**Feature Branch**: `039-dynamic-model-activation`
**Created**: 2026-04-09
**Status**: Draft
**Parent**: `035-sequence-quality-refinement` (Phase 4 of 5)
**Input**: Reference sequence analysis showing that skilled sequencers vary the number of active models by section energy, using model count as an intensity control rather than keeping all models active throughout.

## User Scenarios & Testing

### User Story 1 - Verse/Chorus Model Count Contrast (Priority: P1)

As a user generating a sequence for a song with clear verse/chorus structure, I want
the generator to activate fewer models during low-energy sections (verses, bridges) and
more models during high-energy sections (choruses, drops), so that choruses feel
genuinely bigger and verses feel appropriately intimate -- matching how skilled hand-
sequencers create visual dynamic range by turning props on and off rather than just
changing effects on always-on models.

**Why this priority**: This is the core value proposition of the feature. The reference
analysis shows "Shut Up and Dance" going from 13 active models in verses to 57 in
choruses -- the most impactful visual technique observed. Without this, all sections
feel equally "full" regardless of musical intensity.

**Independent Test**: Generate a sequence for a song with distinct verse and chorus
sections. Run the density-over-time analyzer on the output. Compare active model counts
in verse windows vs chorus windows.

**Acceptance Scenarios**:

1. **Given** a song with sections labeled as verse (energy < 50) and chorus (energy > 70),
   **When** a sequence is generated, **Then** the chorus sections have at least 30% more
   active models than the verse sections.
2. **Given** a song with sections labeled as verse and chorus, **When** the density-over-
   time analyzer is run on the generated output, **Then** the density curve shows a
   visible step-up at each verse-to-chorus transition and a step-down at each chorus-to-
   verse transition.
3. **Given** two songs -- one high-energy throughout and one with clear verse/chorus
   contrast -- **When** sequences are generated for both, **Then** the high-energy song
   shows relatively flat density while the contrasting song shows dynamic density
   variation.

---

### User Story 2 - Tier-Based Activation Order (Priority: P1)

As a user, I want the generator to activate model tiers in a predictable order based on
section energy -- base tiers always on, mid tiers added at moderate energy, high tiers
(hero and compound) reserved for peak energy -- so that the visual build-up follows a
logical progression from foundation to full display.

**Why this priority**: Without a defined activation order, models would turn on and off
randomly, creating an inconsistent visual experience. The tier system already groups
models by visual importance; activation order should follow that hierarchy.

**Independent Test**: Generate a sequence and inspect which tiers have effects in each
section. Verify that low-energy sections only populate base tiers, moderate sections add
mid tiers, and high-energy sections activate all tiers.

**Acceptance Scenarios**:

1. **Given** a section with energy below 40, **When** effects are placed, **Then** only
   base-tier (tiers 1-2) and select mid-tier models (tier 4 beat, tier 6 prop) receive
   effects. Hero and compound tiers are empty for that section.
2. **Given** a section with energy between 40 and 70, **When** effects are placed,
   **Then** base tiers and most mid tiers are active. Hero tier may have sparse accents
   but compound tier remains inactive.
3. **Given** a section with energy above 70, **When** effects are placed, **Then** all
   tiers including hero (tier 7) and compound (tier 8) are fully active.
4. **Given** a section transition from low energy to high energy, **When** the new
   section begins, **Then** the newly activated tiers start with effects at the section
   boundary -- models do not fade in gradually within a section.

---

### User Story 3 - Always-On Visual Backbone (Priority: P1)

As a user, I want a core set of models to remain active throughout the entire song
regardless of section energy, so that the display never goes completely dark and
maintains a visual foundation that other models layer on top of.

**Why this priority**: Every reference sequence has "always on" models (7-18 models at
90%+ coverage) that form the visual backbone. Without this, low-energy sections could
leave the display looking empty or broken.

**Independent Test**: Generate a sequence and identify which models have effects in
every section. Verify that base-tier models maintain continuous coverage.

**Acceptance Scenarios**:

1. **Given** any generated sequence, **When** the coverage per model is analyzed,
   **Then** at least the base-tier models (tiers 1-2) have effects in every section of
   the song, achieving 90%+ time coverage.
2. **Given** the lowest-energy section in any song, **When** effects are placed,
   **Then** the number of active models never drops below 30% of the total available
   models.
3. **Given** a song where all sections have energy below 40, **When** a sequence is
   generated, **Then** the base-tier models still receive full coverage and the display
   does not appear sparse or broken.

---

### User Story 4 - Graduated Density Curve for Building Songs (Priority: P2)

As a user generating a sequence for a song that builds in intensity over its duration
(like Baby Shark building from 9 to 24 models), I want the generator to progressively
activate more models as the song builds, so that the visual intensity tracks the musical
arc rather than jumping between two fixed states.

**Why this priority**: Not all songs have binary verse/chorus structure. Some build
continuously, some have multiple intensity plateaus. The activation system should
respond to the actual energy curve, not just a two-state toggle.

**Independent Test**: Generate a sequence for a song with a gradual build. Verify that
the density-over-time curve increases progressively rather than stepping between two
fixed levels.

**Acceptance Scenarios**:

1. **Given** a song with three or more distinct energy levels across its sections,
   **When** a sequence is generated, **Then** the active model count shows at least
   three distinct density levels (not just "low" and "high").
2. **Given** a song that builds from quiet intro to peak finale, **When** the density-
   over-time is analyzed, **Then** the trend line of active model count increases
   monotonically across the first half of the song.
3. **Given** a song with a quiet bridge between two choruses, **When** a sequence is
   generated, **Then** the bridge section shows a density dip below the chorus level
   but above the verse level (proportional to its intermediate energy).

---

### User Story 5 - Sub-Model and Parent Group Deduplication (Priority: P2)

As a user, I want the generator to avoid placing effects on both a parent group and its
sub-models simultaneously, so that visual elements are not double-covered and deactivated
sub-models are truly "off" rather than inheriting from their parent.

**Why this priority**: Reference sequences show 6-70% of models intentionally empty,
typically because effects are placed on parent groups and sub-models inherit. The
current generator places effects on all levels, creating visual clutter and making
activation/deactivation meaningless if sub-models inherit parent effects anyway.

**Independent Test**: Generate a sequence and inspect the output for models that are
children of groups that also have effects. Verify that when a group has effects, its
sub-models are either empty or have intentionally distinct effects.

**Acceptance Scenarios**:

1. **Given** a layout where a parent group contains sub-models, **When** the parent
   group receives an effect in a section, **Then** the sub-models in that group do not
   receive duplicate effects for that same section.
2. **Given** a low-energy section where the generator deactivates certain models,
   **When** the parent group of those models is active, **Then** the deactivated sub-
   models are truly empty (no effect placements) for that section.
3. **Given** the density-over-time analysis of a generated sequence, **When** only
   models with direct effect placements are counted (excluding inheritance), **Then**
   the count matches the intended activation level for that section's energy.

---

### User Story 6 - Activation Feature Toggle (Priority: P2)

As a user, I want to be able to enable or disable the dynamic model activation behavior
independently of other quality refinement features, so that I can evaluate its impact
in isolation or revert to the previous "all models always active" behavior if preferred.

**Why this priority**: Each phase of the quality refinement must be independently
toggleable (FR-008 and FR-010 from the parent spec). This is essential for A/B testing
and incremental validation.

**Independent Test**: Generate two sequences for the same song -- one with activation
enabled and one with it disabled. Verify that the disabled version matches the previous
behavior (all models active in all sections).

**Acceptance Scenarios**:

1. **Given** dynamic model activation is disabled, **When** a sequence is generated,
   **Then** all tiers receive effects in every section, matching the pre-feature behavior
   exactly.
2. **Given** dynamic model activation is enabled, **When** a sequence is generated,
   **Then** the density-over-time varies by section energy as described in User Story 1.
3. **Given** dynamic model activation is toggled from enabled to disabled, **When** the
   same song is regenerated, **Then** no other quality refinement behaviors (focused
   effects, duration scaling, palette restraint) are affected.

---

### Edge Cases

- What happens when a song has no section boundaries (e.g., ambient music or a single
  continuous section)? The system should treat the entire song as one section and
  activate models based on its average energy, resulting in stable density throughout.
- What happens when all sections have the same energy level? The system should produce
  flat density (similar to "Away In A Manger" with 24-28 models throughout), which is
  the correct behavior for songs without dynamic contrast.
- What happens when a layout has only one group (all models in a single tier)? Tier-
  based activation cannot create contrast. The system should fall back to activating
  all models, since there is no meaningful hierarchy to modulate.
- What happens when a section is very short (under 3 seconds)? The system should still
  apply the activation level for that section's energy rather than blending with
  neighbors, to avoid smearing section boundaries.
- What happens when the layout has very few models (under 10 total)? The activation
  range becomes too narrow for meaningful contrast. The system should widen the
  minimum active percentage to avoid looking sparse (e.g., minimum 60% instead of 30%).
- What happens when energy values are missing or unreliable for some sections? The
  system should default to full activation (all tiers active) for sections without
  energy data, matching the pre-feature behavior.

## Requirements

### Functional Requirements

- **FR-001**: The generator MUST determine an activation level for each section based on
  that section's energy value, mapping energy to the number of active tiers and models.
- **FR-002**: The activation level MUST follow a tiered progression: base tiers (1-2)
  always active, mid tiers (3-6) activated at moderate energy, high tiers (7-8) activated
  at high energy.
- **FR-003**: The generator MUST maintain a minimum set of always-on models (base tier)
  in every section so that the display never goes dark. The minimum active model count
  MUST be at least 30% of total available models.
- **FR-004**: The generator MUST produce at least 30% more active models in sections with
  energy above 70 compared to sections with energy below 40, for songs that contain both
  energy levels.
- **FR-005**: The generator MUST NOT place effects on both a parent group and its sub-
  models for the same section when the intent is for the parent effect to cascade. When a
  model is deactivated for a section, it MUST have zero effect placements for that
  section's time range.
- **FR-006**: The activation system MUST support songs with more than two distinct energy
  levels, producing graduated density rather than a binary on/off toggle.
- **FR-007**: The activation behavior MUST be independently toggleable. When disabled, the
  generator MUST produce the same output as the pre-feature baseline (all tiers active in
  all sections).
- **FR-008**: The activation system MUST NOT alter effect selection, duration, palette, or
  any other aspect of placement on models that ARE active. It only controls WHICH models
  receive effects, not WHAT effects they receive.
- **FR-009**: For layouts with very few models (under 10), the minimum active percentage
  MUST increase to at least 60% to avoid the display appearing broken.
- **FR-010**: Sections without energy data MUST default to full activation (all tiers
  active).

### Key Entities

- **ActivationCurve**: A per-section specification of which tiers are active, derived
  from the section's energy value. Maps energy ranges to tier sets. Each section in the
  song plan has an associated activation level that determines which model groups receive
  effect placements.
- **TierActivationOrder**: The ordered progression of tier activation as energy increases.
  Defines which tiers are "always on" (base), which are "moderate energy" (mid), and
  which are "high energy only" (hero/compound). This ordering is fixed and follows the
  existing tier hierarchy.
- **AlwaysOnSet**: The set of models that maintain effects in every section regardless
  of energy. Corresponds to base-tier models and forms the visual backbone of the
  display. Analogous to the 7-18 "always on" models observed in reference sequences.

## Success Criteria

### Measurable Outcomes

- **SC-001**: For songs with clear verse/chorus contrast (energy difference > 30 between
  lowest and highest sections), the generated sequence shows at least 30% more active
  models in the highest-energy sections compared to the lowest-energy sections.
- **SC-002**: The density-over-time analysis of generated sequences correlates with the
  section energy curve -- Pearson correlation coefficient of at least 0.6 between section
  energy and active model count.
- **SC-003**: Base-tier models achieve 90%+ time coverage across the full song duration in
  every generated sequence.
- **SC-004**: No section in any generated sequence has fewer than 30% of available models
  active (or 60% for layouts with under 10 models).
- **SC-005**: The dynamic range (max active models minus min active models) of generated
  sequences for dynamic songs is within 50% of the dynamic range observed in reference
  sequences of similar style.
- **SC-006**: When the activation feature is disabled, generated sequences are identical
  to pre-feature baseline output (zero diff in effect placements).
- **SC-007**: No regression in the existing test suite when the feature is enabled or
  disabled.

## Assumptions

- Section energy values (0-100 scale) are available from the existing analysis pipeline
  and are sufficiently accurate to drive activation decisions. No new audio analysis is
  required.
- The existing tier system (tiers 1-8) provides a meaningful visual hierarchy where
  lower tiers are foundational and higher tiers are accent/hero elements. This hierarchy
  is well-suited for progressive activation.
- The layout parser correctly identifies parent-child relationships between groups and
  sub-models, enabling the deduplication logic in FR-005.
- Phases 1-2 (focused effects and duration scaling) are complete or in progress. Dynamic
  model activation is most impactful when combined with focused effects and proper
  duration -- without those, turning models on/off still results in visual incoherence
  on the active models.
- The reference analyzer tool (`analyze_reference_xsq.py`) supports density-over-time
  analysis and can be run on generated output for comparison.

## Relationship to Other Phases

This is **Phase 4 of 5** in the Sequence Quality Refinement plan
(`035-sequence-quality-refinement`).

| Phase | Feature | Status | Dependency |
|-------|---------|--------|------------|
| Phase 1 | Focused Effects + Repetition (036) | Prerequisite | Provides coherent effects on active models |
| Phase 2 | Duration Scaling (037) | Prerequisite | Ensures proper timing on active models |
| Phase 3 | Palette Restraint (038) | Independent | No direct interaction |
| **Phase 4** | **Dynamic Model Activation (039)** | **This spec** | Best results with Phases 1-2 complete |
| Phase 5 | MusicSparkles + Value Curves (040) | Dependent | Additive polish on top of activation |

**Why Phases 1-2 should be complete first**: Dynamic model activation controls WHICH
models are active. Phases 1-2 control WHAT those active models look like (focused
effects, proper duration, embraced repetition). If the active models still have
incoherent effects and wrong durations, turning other models off just makes the
incoherence more visible on fewer models. The activation contrast is most impactful
when the active models already look good.

**Interaction with Phase 3 (Palette Restraint)**: No direct dependency. Palette restraint
affects color slot usage on active models. Model activation affects which models are
active. These are orthogonal concerns.

**Interaction with Phase 5 (MusicSparkles + Value Curves)**: Phase 5 adds polish to
effects on active models. The two features compose naturally -- fewer active models in
verses means the sparkle and curve enhancements are concentrated on the visible models.
