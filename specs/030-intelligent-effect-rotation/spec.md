# Feature Specification: Intelligent Effect Rotation

**Feature Branch**: `030-intelligent-effect-rotation`
**Created**: 2026-04-01
**Status**: Draft
**Input**: User description: "I want to work on intelligent effect rotation. I want to create variety within sections. I want to intelligently select an effect to go on a prop which aligns with the song theme and tone, speed, etc. I don't want the same effect over and over again. I want there to be enough effects for a given theme and prop and layer. I want the theme to have choices of effects and then apply them in a way which is visually pleasing."

## Clarifications

### Session 2026-04-01

- Q: Should intelligent rotation apply to all tiers (1-8), or a subset? → A: Tiers 5-8 (fidelity, prop, comp, hero). Tiers 1-4 (base, geo, type, beat) remain unchanged.
- Q: How should theme effect pools be structured? → A: List of variant names with optional scorer fallback — named refs are tried first, scorer fills gaps when pool variants don't match context.
- Q: How should symmetry pairs be detected? → A: Auto-detect from naming patterns (Left/Right, 1/2, A/B) and spatial position, with manual override for edge cases.
- Q: Should prop effect suitability (feature 029) be a separate feature or merged? → A: Merged into this feature. Prop type classification, graduated scorer, and suitability-filtered pools are foundational prerequisites for intelligent rotation.

## User Scenarios & Testing

### User Story 0 — Prop Type Classification and Suitability Scoring (Priority: P0, Foundation)

Each power group must know what type of props it contains (matrix, outline, arch, vertical, tree, radial) so that downstream selection can make prop-aware decisions. The system maps xLights DisplayAs values to canonical prop suitability keys and assigns a dominant prop type to each group. The variant scorer must use graduated suitability ratings (ideal=1.0, good=0.75, possible=0.25, not_recommended=0.0) instead of binary presence checks.

**Why this priority**: This is foundational data and scoring infrastructure that all other stories depend on. Without prop type classification and graduated scoring, the rotation engine cannot make prop-aware or suitability-weighted selections.

**Independent Test**: Parse a layout with diverse prop types, generate power groups, and verify each group carries the correct prop type. Score the same variant against two prop types with different suitability ratings and verify different scores.

**Acceptance Scenarios**:

1. **Given** a group whose members all have DisplayAs="Arch", **When** the group is generated, **Then** its prop type is "arch".
2. **Given** a group with 3 "Matrix" members and 1 "Single Line" member, **When** the group is generated, **Then** its prop type is "matrix" (majority wins).
3. **Given** a group with members whose DisplayAs is not in the known mapping, **When** the group is generated, **Then** it defaults to "outline".
4. **Given** an effect rated "ideal" for matrix, **When** scored with prop_type="matrix", **Then** the prop_type dimension score is 1.0.
5. **Given** an effect rated "good" for outline, **When** scored with prop_type="outline", **Then** the prop_type dimension score is 0.75.
6. **Given** an effect rated "possible" for arch, **When** scored with prop_type="arch", **Then** the prop_type dimension score is 0.25.
7. **Given** an effect rated "not_recommended" for radial, **When** scored with prop_type="radial", **Then** the prop_type dimension score is 0.0.

---

### User Story 1 — Theme-Aware Effect Selection (Priority: P1)

When the sequence generator assigns effects to prop groups within a section, it selects from a curated pool of effect variants that match the current theme's mood, the section's energy level, and the prop type — rather than cycling through a static, hard-coded list.

**Why this priority**: This is the core problem. The current system uses a fixed `_PROP_EFFECT_POOL` for tier 6-7 rotation and each theme layer specifies exactly one effect. There is no variety within a section — every bar/beat of a layer gets the same effect. Solving selection is the foundation everything else builds on.

**Independent Test**: Generate a sequence for a high-energy chorus section with a theme tagged "energetic." Verify that the effects chosen for each prop group are drawn from high-energy variants appropriate for each prop type, and that at least 2 different effects appear across the groups in that section.

**Acceptance Scenarios**:

1. **Given** a theme with mood "energetic" and a chorus section with energy score above 70, **When** the generator places effects on 4 prop groups (arch, matrix, tree, custom), **Then** each group receives an effect variant whose `energy_level` tag matches or is adjacent to "high" and whose base effect is suitable for that prop type.
2. **Given** a verse section with energy score below 40, **When** the generator selects effects, **Then** the selected variants have `energy_level` "low" or "medium" and `tier_affinity` matching the group's tier.
3. **Given** a theme with no explicit effect pool defined, **When** the generator runs, **Then** it falls back to the variant library's scored selection and still produces a valid sequence with no empty groups.

---

### User Story 2 — Effect Variety Within Sections (Priority: P1)

Within a single section, different prop groups at the same tier should receive different effects to avoid visual monotony. Adjacent sections of the same type (e.g., two consecutive verse sections) should also vary their effect assignments.

**Why this priority**: Even with good selection, using the same effect on every arch and every tree creates a flat, repetitive look. Variety is what makes a professional sequence feel hand-crafted.

**Independent Test**: Generate a sequence with 3 consecutive verse sections and 4 prop groups. Verify that no two groups at the same tier in the same section have the same effect, and that the effect assignments differ between the repeated verse sections.

**Acceptance Scenarios**:

1. **Given** a section with 4 prop groups all at tier 6, **When** effects are placed, **Then** at least 3 distinct effect variants are used across those 4 groups.
2. **Given** two consecutive sections with the same theme, **When** effects are placed, **Then** at least 50% of the effect assignments differ between the two sections (same group gets a different effect variant the second time).
3. **Given** a section with only 1 prop group, **When** effects are placed, **Then** the system does not error — it selects the best single variant for that group.

---

### User Story 3 — Theme Effect Pool Definition (Priority: P2)

Theme authors can define a curated pool of preferred effect variants per layer or per tier, giving the generator a menu of choices rather than a single fixed effect. The generator picks from this pool based on context (prop type, energy, section role).

**Why this priority**: Enables theme designers to curate the visual aesthetic while still allowing intelligent rotation. Without this, the system makes all decisions — with it, the theme provides artistic direction and the system handles execution.

**Independent Test**: Create a theme where one layer specifies a pool of 4 effect variants instead of a single effect. Generate a sequence and verify all 4 variants appear across sections and groups, distributed according to their tag fitness.

**Acceptance Scenarios**:

1. **Given** a theme layer with an effect pool of 3 named variants, **When** the generator places effects across 6 sections and 3 groups, **Then** all 3 variants appear at least once in the output.
2. **Given** a theme layer with an effect pool AND a fallback base effect, **When** none of the pool variants match the current section's energy, **Then** the system falls back to the base effect with default parameters.
3. **Given** a theme layer with a single effect (no pool), **When** the generator runs, **Then** behavior is identical to today — backward compatible.

---

### User Story 4 — Visual Coherence Constraints (Priority: P2)

The system enforces visual coherence rules so that variety does not become chaos. Groups that are visually adjacent or paired (e.g., left arch and right arch) should receive the same effect. Effect transitions between sections should be smooth, not jarring.

**Why this priority**: Unconstrained variety can look worse than repetition. Paired props looking different is immediately noticeable. Section transitions need continuity.

**Independent Test**: Generate a sequence where "Arch Left" and "Arch Right" are in the same symmetry group. Verify they always get the same effect and direction. Generate a sequence with a verse-to-chorus transition and verify the effect change is not abrupt (shared elements or gradual shift).

**Acceptance Scenarios**:

1. **Given** two prop groups marked as a symmetry pair, **When** effects are placed, **Then** both groups receive the same effect variant with mirrored direction (if applicable).
2. **Given** a section transition from verse (low energy) to chorus (high energy), **When** effects change, **Then** at least one tier maintains its effect across the transition to provide visual continuity.
3. **Given** a drop section following a build, **When** effects are placed, **Then** the drop section uses hero-tier effects with higher energy variants than the build section.

---

### User Story 5 — Rotation Preview and Diagnostics (Priority: P3)

Users can preview what effects were assigned to each group in each section and understand why, via CLI or the web dashboard. This helps theme authors and users tune their sequences.

**Why this priority**: Visibility into the rotation decisions helps users learn the system and identify when manual overrides are needed.

**Independent Test**: Run the generator on a song, then query the rotation report. Verify it shows per-section, per-group effect assignments with the scoring rationale.

**Acceptance Scenarios**:

1. **Given** a completed sequence generation, **When** the user requests a rotation report, **Then** the output shows each section with its groups, assigned effect variants, and the top scoring factors for each assignment.
2. **Given** a completed generation viewed on the web dashboard, **When** the user views the sequence plan, **Then** each section visually shows which effects are on which groups.

---

### Edge Cases

- What happens when the variant library has fewer variants than prop groups in a section? The system reuses variants but prefers the highest-scoring ones, not errors.
- What happens when a theme's effect pool references variants that no longer exist in the library? The system warns and falls back to scored selection from the full library.
- What happens when all variants score equally (no distinguishing tags)? The system uses deterministic pseudo-random selection seeded by section index to ensure reproducibility.
- What happens with a 1-section song? Rotation across sections is not applicable — intra-section variety still applies.
- What happens when a theme has 10+ layers but only 2 prop groups? Each group gets its assigned layers; no rotation needed across groups.

## Requirements

### Functional Requirements

- **FR-000a**: System MUST maintain a mapping from xLights DisplayAs values to the six canonical prop suitability keys (matrix, outline, arch, vertical, tree, radial), covering at minimum: Matrix, Tree 360, Tree Flat, Tree, Arch, Arches, Candy Cane, Candy Canes, Circle, Spinner, Star, Wreath, Icicles, Window Frame, Single Line, Poly Line, Custom.
- **FR-000b**: System MUST assign a dominant prop type to each power group based on the DisplayAs values of its member props, using majority vote with alphabetical tiebreaking. Unrecognized or empty DisplayAs values default to "outline".
- **FR-000c**: The variant scorer MUST use graduated suitability scores: ideal=1.0, good=0.75, possible=0.25, not_recommended=0.0 (replacing the current binary 1.0/0.0 check). Return 0.5 (neutral) when no prop type context is provided.
- **FR-001**: The generator MUST select effect variants for tier 5-8 groups based on the group's prop type, the section's energy level, the section's role (verse/chorus/bridge/etc.), and the theme's mood. Tiers 1-4 remain unchanged.
- **FR-002**: The generator MUST ensure that within a single section, no two prop groups at the same tier receive the same effect variant (when sufficient variants are available).
- **FR-003**: The generator MUST vary effect assignments across repeated sections of the same type (e.g., Verse 1 and Verse 2 should differ in at least 50% of their group assignments).
- **FR-004**: Themes MUST support defining an effect pool (list of variant names) per layer, as an alternative to a single fixed effect. When pool variants don't match the current context, the variant scorer fills gaps from the full library.
- **FR-005**: When a theme layer defines an effect pool, the generator MUST select from that pool using weighted scoring dimensions (prop type, energy, tier, section role, scope, genre).
- **FR-006**: The system MUST auto-detect symmetry pairs among prop groups from naming patterns (Left/Right, 1/2, A/B) and spatial position, with support for manual override in the grouping configuration.
- **FR-006b**: Prop groups identified as symmetry pairs MUST receive the same effect variant with appropriate directional mirroring.
- **FR-007**: The generator MUST maintain at least one shared effect across section transitions on at least one tier to provide visual continuity.
- **FR-008**: When the variant library lacks sufficient variants for a selection context, the system MUST fall back gracefully — using the best available match rather than erroring.
- **FR-009**: The rotation assignments MUST be deterministic given the same input (song analysis + theme + variant library) to ensure reproducible sequences.
- **FR-010**: The system MUST produce a rotation report showing per-section, per-group effect assignments with scoring rationale, accessible via CLI and web dashboard.
- **FR-011**: Effect pool definitions in themes MUST be backward compatible — existing themes with single-effect layers continue to work identically.

### Key Entities

- **Prop Type Mapping**: A lookup table translating xLights DisplayAs strings to one of six canonical suitability keys. Entries not in the map default to "outline".
- **Power Group (extended)**: An existing grouping of props by tier, now extended with a dominant prop type derived from its members.
- **Suitability Score**: A graduated numeric score (0.0–1.0) derived from the four-level rating system (ideal/good/possible/not_recommended), used in variant ranking.
- **EffectPool**: A list of effect variant names associated with a theme layer. The generator selects from this list first using scored matching; if no pool variant fits the current context, the scorer falls back to the full variant library.
- **RotationPlan**: The per-section, per-group mapping of selected effect variants with scoring metadata. Generated during sequence planning, before output.
- **SymmetryGroup**: A pairing of prop groups that should receive mirrored effect assignments (e.g., left/right arches, paired trees). Auto-detected from naming patterns and spatial position, with manual override support. Does not exist in the codebase today — created by this feature.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Generated sequences use at least 3 distinct effect variants per section when 4+ prop groups are present (measured across 10 test songs).
- **SC-002**: Repeated sections of the same type (e.g., Verse 1 vs Verse 2) differ in at least 50% of their group-level effect assignments.
- **SC-003**: Zero prop groups are left without an effect assignment, even when the variant library has limited coverage.
- **SC-004**: Symmetry-paired groups receive identical effects in 100% of cases.
- **SC-005**: Existing themes (single-effect layers, no effect pool) produce identical output before and after the change — full backward compatibility.
- **SC-006**: The rotation report renders in under 2 seconds for a 4-minute song with 20+ sections.

## Assumptions

- The variant library (feature 028) is available with 100+ curated variants across 30 effects, including energy_level, tier_affinity, speed_feel, section_roles, and direction_cycle tags.
- The variant scorer with progressive fallback is the primary selection mechanism.
- Prop group tier assignments are available from the layout grouper. Symmetry detection will be built as part of this feature.
- Theme mood/occasion/genre fields provide sufficient context for initial selection filtering.
- The existing hard-coded effect pool and tier 6-7 rotation logic will be replaced by this feature's intelligent selection. Tiers 5 (fidelity) and 8 (hero) also gain intelligent variant selection. Tiers 1-2 (base/geo), 3 (type), and 4 (beat chase) remain unchanged.
- Direction cycling on variants continues to handle per-bar/beat alternation within a single effect — this feature handles which effect is selected, not how it alternates.

## Scope Boundaries

### In Scope

- Intelligent variant selection using the scorer for tiers 5-8 (fidelity, prop, comp, hero)
- Effect variety within sections (across groups) and across repeated sections
- Theme effect pool definition (list of variant refs per layer)
- Symmetry pair enforcement
- Section transition continuity
- Rotation diagnostics (CLI report + dashboard display)
- Backward compatibility with existing single-effect themes

### Out of Scope

- Modifying the variant library itself (that is feature 028)
- Value curve integration (brightness/speed ramps within an effect placement)
- Manual per-section effect override UI (future theme editor enhancement)
- Multi-layer stacking (placing two effects on the same group with blend modes)
- Creating new themes — this feature uses existing themes and their pool definitions

## Dependencies

- Feature 028 (Effects Variant Library) — variant models, scorer, library loading
- Feature 017 (xLights Layout Grouping) — prop group tier assignments
- Feature 019 (Effect Themes) — theme model, layers, mood/genre fields
- Feature 020 (Sequence Generator) — effect placer, section assignments, place_effects()
