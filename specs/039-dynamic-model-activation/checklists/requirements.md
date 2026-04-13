# Requirements Checklist: Dynamic Model Activation (039)

Phase 4 of 5 — Sequence Quality Refinement

## User Stories

- [x] US1 (P1): Verse/chorus model count contrast -- choruses have 30%+ more active models than verses
- [x] US2 (P1): Tier-based activation order -- base always on, mid at moderate energy, high at peak
- [x] US3 (P1): Always-on visual backbone -- base-tier models active in every section, display never dark
- [x] US4 (P2): Graduated density curve -- supports 3+ density levels, not just binary on/off
- [x] US5 (P2): Sub-model and parent group deduplication -- no double-coverage
- [x] US6 (P2): Activation feature toggle -- independently enable/disable without affecting other phases

## Acceptance Scenarios

### US1 - Verse/Chorus Contrast
- [x] Chorus sections (energy > 70) have at least 30% more active models than verse sections (energy < 50)
- [x] Density-over-time shows visible step-up at verse-to-chorus transitions
- [x] High-energy-throughout songs produce flat density; contrasting songs produce dynamic density

### US2 - Tier-Based Activation Order
- [x] Energy below 40: only base tiers (1-2) and select mid tiers (4, 6) active
- [x] Energy 40-70: base tiers and most mid tiers active; hero sparse, compound inactive
- [x] Energy above 70: all tiers fully active including hero (7) and compound (8)
- [x] Newly activated tiers start at section boundary, not gradual fade-in

### US3 - Always-On Backbone
- [x] Base-tier models have 90%+ time coverage in every generated sequence
- [x] Active model count never drops below 30% of total available models
- [x] Low-energy-only songs still have full base-tier coverage

### US4 - Graduated Density
- [x] Songs with 3+ distinct energy levels produce 3+ distinct density levels
- [x] Building songs show monotonically increasing density trend
- [x] Bridge sections show intermediate density between verse and chorus levels

### US5 - Sub-Model Deduplication
- [x] Parent group with effects does not also have duplicate effects on its sub-models
- [x] Deactivated sub-models have zero effect placements for that section
- [x] Density-over-time counts only models with direct placements (not inherited)

### US6 - Feature Toggle
- [x] Disabled: all tiers receive effects in every section (matches pre-feature behavior)
- [x] Enabled: density varies by section energy
- [x] Toggle does not affect other quality refinement behaviors

## Functional Requirements

- [x] FR-001: Activation level determined per section from section energy value
- [x] FR-002: Tiered progression -- base always on, mid at moderate, high at peak energy
- [x] FR-003: Minimum always-on set (base tier); never fewer than 30% of models active
- [x] FR-004: High-energy sections (>70) have at least 30% more models than low-energy (<40)
- [x] FR-005: No duplicate effects on parent group AND sub-models; deactivated models truly empty
- [x] FR-006: Graduated density with 3+ levels, not binary toggle
- [x] FR-007: Independently toggleable; disabled produces identical pre-feature output
- [x] FR-008: Activation controls WHICH models are active, not WHAT effects they receive
- [x] FR-009: Small layouts (under 10 models) use 60% minimum active percentage
- [x] FR-010: Sections without energy data default to full activation

## Edge Cases

- [x] No section boundaries (single section): stable density based on average energy
- [x] All sections same energy: flat density (appropriate, not a bug)
- [x] Single-group layout (one tier): fall back to all models active
- [x] Very short sections (under 3s): apply activation level, no blending
- [x] Very few models (under 10): widen minimum active percentage to 60%
- [x] Missing energy data: default to full activation

## Success Criteria

- [x] SC-001: 30%+ more active models in highest vs lowest energy sections (for dynamic songs)
- [x] SC-002: Pearson correlation >= 0.6 between section energy and active model count
- [x] SC-003: Base-tier models at 90%+ time coverage in every sequence
- [x] SC-004: No section below 30% active models (60% for small layouts)
- [x] SC-005: Dynamic range within 50% of reference sequences for similar style
- [x] SC-006: Disabled toggle produces zero diff vs pre-feature baseline
- [x] SC-007: No regression in existing test suite

## Key Entities

- [x] ActivationCurve: per-section tier activation derived from energy
- [x] TierActivationOrder: ordered progression of tier activation by energy
- [x] AlwaysOnSet: models with effects in every section regardless of energy

## Phase Dependencies

- [x] Relationship to Phase 1 (Focused Effects) documented as prerequisite
- [x] Relationship to Phase 2 (Duration Scaling) documented as prerequisite
- [x] Relationship to Phase 3 (Palette Restraint) documented as independent
- [x] Relationship to Phase 5 (MusicSparkles + Value Curves) documented as dependent
- [x] Rationale for Phase 1-2 prerequisite explained (activation most impactful with coherent effects)
