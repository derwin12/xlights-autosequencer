# Feature Specification: Prop-Type Effect Affinity

**Feature Branch**: `041-prop-type-affinity`
**Created**: 2026-04-13
**Status**: Draft
**Input**: Observation that generated sequences show the same linear effect (Bars, Wave) across all prop groups simultaneously, regardless of prop shape. Trees should show rotational effects (Pinwheel, Spirals), arches show linear effects (Bars, Wave), radials show expanding effects (Shockwave, Ripple) — all simultaneously at the same moment.

## Clarifications

### Session 2026-04-13

- Q: Which tiers should within-tier base-effect diversity apply to? → A: Tiers 5–8 only (prop, compound, hero). Tiers 1–4 (base wash, geometry, architecture, beat) are intentionally uniform and excluded.
- Q: What score floor applies when falling back to a duplicate effect? → A: 0.3 — if no unclaimed effect scores ≥ 0.3 for a group, assign that group's own top-scored effect even if it duplicates another group's assignment.

## Background

The infrastructure for prop-type routing already exists from specs 028/030:
- `PowerGroup.prop_type` is populated from the xLights `DisplayAs` field (`src/grouper/grouper.py`)
- `prop_suitability` ratings exist on every effect (`src/effects/builtin_effects.json`)
- The RotationEngine scores variants by `prop_type` with 0.30 weight (`src/variants/scorer.py`)

**The gap**: With `embrace_repetition=True` (default since spec 036), the existing dedup that forced cross-group variety is disabled. When 5 arch groups all score "Bars" as their top variant, all 5 pick Bars simultaneously — the house looks uniform. Additionally, the `_build_effect_pool()` fallback ignores prop type entirely.

---

## User Scenarios & Testing

### User Story 1 — Within-Tier Base-Effect Diversity (Priority: P1)

As a user, I want different prop groups within the same tier to use different base
effects simultaneously, so that the house has visual variety at any given moment
rather than every arch doing Bars and every tree doing Spirals at the same time as
every other tree.

**Why this priority**: This is the root cause of the "bars everywhere" complaint. Even
if the RotationEngine correctly picks the best effect for each prop type, multiple groups
of the same type (e.g., five arch groups) all converge on the same top-scored effect.
Within-tier diversity is the biggest visual improvement possible without changing themes.

**Independent Test**: Generate a sequence, inspect `group_effects` for a section with
multiple tier-6 groups. No two groups in the same tier should share the same base
effect name in the same section.

**Acceptance Scenarios**:

1. **Given** five arch groups in tier 6, **When** a section is generated, **Then**
   those five groups receive at least 3 distinct base effects (e.g., Bars, Wave, Chase,
   Single Strand, Curtain) rather than all receiving Bars.
2. **Given** two tree groups and three arch groups in tier 6, **When** a section is
   generated, **Then** the two tree groups may share the same effect (Spirals) but the
   three arch groups each receive a different base effect.
3. **Given** a single group in a tier, **When** a section is generated, **Then** it
   receives its highest-scoring variant as before — no change for solo-group tiers.
4. **Given** fewer distinct suitable effects than groups in a tier, **When** assignment
   runs out of unique options, **Then** effects are reused gracefully (diversity is
   best-effort, not a hard guarantee).

---

### User Story 2 — Tree and Radial Props Show Rotational Effects (Priority: P1)

As a user, I want trees and radial props (spinners, stars, wreaths) to consistently
receive rotational or expanding effects (Pinwheel, Spirals, Fan, Ripple, Shockwave)
rather than linear effects (Bars, Wave, Single Strand), so that each prop type
contributes its visually optimal appearance to the sequence.

**Why this priority**: A tree doing Bars looks flat. A tree doing Spirals looks
dimensional and appropriate for the prop shape. The suitability data already marks
these effects as `ideal` for tree/radial props; the fix ensures this preference is
actually realized in output.

**Independent Test**: Generate a sequence for a layout with identifiable tree and arch
groups. Inspect base effects assigned to tree-typed groups. At least 70% of tree-group
effect assignments should be tree-ideal effects (Pinwheel, Spirals, Fan, Ripple,
Shockwave, Fireworks, Meteors, Tree).

**Acceptance Scenarios**:

1. **Given** a tree-typed group in tier 6, **When** the RotationEngine assigns a
   variant, **Then** the assigned base effect is rated `ideal` for tree props in
   `prop_suitability` (unless no ideal options remain, in which case `good` is
   acceptable).
2. **Given** an arch-typed group in tier 6, **When** the RotationEngine assigns a
   variant, **Then** the assigned base effect is NOT `not_recommended` for arch props.
3. **Given** a layout with both tree and arch groups, **When** a sequence is generated,
   **Then** tree groups show different base effects than arch groups in the same section
   (prop-type cross-diversity in addition to within-type diversity from US1).

---

### User Story 3 — Fallback Pool Respects Prop Suitability (Priority: P2)

As a user, I want the fallback effect pool (used when the focused rotation plan is
unavailable) to filter out effects that are `not_recommended` for the group's prop
type, so that unsuitable effects never appear on incompatible props even in edge cases.

**Why this priority**: The RotationEngine handles the normal path correctly. This story
closes the edge-case gap where `_build_effect_pool()` is called without prop-type
awareness. Lower priority because `focused_vocabulary=True` (the default) rarely hits
this path.

**Independent Test**: Disable the rotation plan and trigger the fallback path. Verify
that `not_recommended` effects for each group's prop type are absent from the assigned
effects.

**Acceptance Scenarios**:

1. **Given** a radial-typed group and `_build_effect_pool()` called with its prop type,
   **Then** effects rated `not_recommended` for radial (e.g., Plasma for radial if
   applicable) are excluded from the pool.
2. **Given** a prop type where the entire `_PROP_EFFECT_POOL` would be excluded by
   `not_recommended` filtering, **Then** the filter is relaxed to include `possible`
   effects rather than returning an empty pool.

---

### Edge Cases

- **All effects exhausted in a tier**: When the number of groups exceeds distinct
  suitable effects, reuse is allowed starting from the highest-scored effect. Diversity
  is best-effort.
- **Unknown prop type**: Groups with `prop_type=None` or unrecognized types skip the
  suitability filter entirely — current behavior preserved.
- **Single-group tiers**: No change — first-choice variant selected as before.
- **`embrace_repetition=True` vs `False`**: The within-tier base-effect dedup applies
  regardless of this flag. The flag controls section-level variant dedup; this adds
  tier-level effect dedup as a separate mechanism.

---

## Requirements

### Functional Requirements

- **FR-001**: Within any single **tier 5–8** and section, no two groups shall be assigned
  the same base effect unless no unclaimed effect scores ≥ 0.3 for that group's prop type,
  in which case the group's own top-scored effect is assigned even if it duplicates. Tiers 1–4
  are excluded — uniform effects on base/architecture/beat layers are intentional.
- **FR-002**: The RotationEngine's within-tier dedup MUST operate on base effect names
  (not variant names), so that "Spirals 3D Fast" and "Spirals Dense Slow" are treated
  as the same base effect for diversity purposes.
- **FR-003**: `_build_effect_pool()` MUST accept an optional `prop_type` parameter and
  exclude effects rated `not_recommended` for that prop type when provided.
- **FR-004**: If filtering by `not_recommended` leaves an empty pool, the filter MUST
  relax to include `possible`-rated effects before returning.
- **FR-005**: All existing behavior for single-group tiers MUST be preserved unchanged.
- **FR-006**: The within-tier dedup MUST be independent of the `embrace_repetition`
  flag — it applies in both modes.

---

## Success Criteria

- **SC-001**: In any generated section with ≥3 tier-6 groups, at least 2 distinct base
  effects are present across those groups.
- **SC-002**: Tree-typed groups receive tree-ideal effects in ≥70% of assignments.
- **SC-003**: No group receives a `not_recommended` effect for its prop type via the
  fallback pool path.
- **SC-004**: Existing test suite passes with no regressions.

## Key Files

- `src/generator/rotation.py` — add within-tier base-effect tracking in `build_rotation_plan()`
- `src/generator/effect_placer.py` — add `prop_type` param to `_build_effect_pool()`, wire through
- `tests/unit/test_rotation.py` — verify within-tier diversity and prop-type routing
