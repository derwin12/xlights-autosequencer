# Feature Specification: Theme and Effect Variant Separation

**Feature Branch**: `033-theme-variant-separation`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: "Separate theme layer configuration from effect variant parameter ownership so that themes compose variants rather than duplicating their responsibilities"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Theme Layers Reference Variants Only (Priority: P1)

A theme author defines a theme by selecting pre-existing effect variants for each layer rather than configuring raw effect parameters inline. When creating or editing a theme, the author picks from the variant library (e.g., "Butterfly Classic 2-Chunk", "Wave Sine Mirror") and assigns each to a layer with a blend mode. The theme contains no parameter overrides — all parameter knowledge lives exclusively in variants. If a theme needs a slightly different configuration, a new variant is created rather than tweaking parameters inline. Final fine-tuning of the generated sequence happens in xLights itself.

**Why this priority**: This is the core of the feature. Without this, themes and variants continue to blend responsibilities. Every other story depends on this structural change.

**Independent Test**: A theme can be created with layers that reference only variant names. Loading that theme resolves each layer to the correct effect and parameters by looking up the variant. No parameter_overrides exist on any layer.

**Acceptance Scenarios**:

1. **Given** a theme with a layer referencing variant "Butterfly Classic 2-Chunk", **When** the theme is loaded, **Then** the layer resolves to effect "Butterfly" with the parameters defined in that variant.
2. **Given** a theme with a layer referencing a variant that does not exist in the library, **When** the theme is validated, **Then** a validation error is reported and the theme fails to load.
3. **Given** a theme with multiple layers each referencing different variants, **When** effects are placed for a section, **Then** each layer uses the parameters from its referenced variant with no additional overrides.
4. **Given** the variant library fails to load, **When** the system attempts to load themes, **Then** the system raises an unrecoverable error rather than silently degrading.

---

### User Story 2 - Builtin Themes Migrated to Variant References (Priority: P2)

All 21 built-in themes are migrated so that each layer references a variant from the variant library. Where an existing variant matches the theme's current inline parameters, that variant is reused. Where no match exists, a new variant is created in the variant library with appropriate tags. After migration, no built-in theme layer contains inline parameter overrides.

**Why this priority**: The migration demonstrates the new model works end-to-end and ensures all built-in themes conform to the new convention. It must happen after Story 1 establishes the model.

**Independent Test**: Load the migrated builtin themes and verify every layer has a variant field pointing to an existing variant and no parameter_overrides. The generated sequences from the migrated themes should produce identical visual output to the pre-migration themes.

**Acceptance Scenarios**:

1. **Given** the migrated built-in themes, **When** the theme library is loaded with validation, **Then** all 21 themes pass validation with zero errors.
2. **Given** a theme layer that previously had inline parameters matching existing variant "Ripple Circle", **When** the migration runs, **Then** that layer references "Ripple Circle" instead of duplicating its parameters.
3. **Given** a theme layer with inline parameters that match no existing variant, **When** the migration runs, **Then** a new variant is created in the variant library with those parameters and appropriate tags, and the layer references it.
4. **Given** any built-in theme layer after migration, **When** its data is inspected, **Then** it contains no parameter_overrides field.

---

### User Story 3 - Theme Editor UI Supports Variant Selection (Priority: P2)

The theme editor in the review UI allows authors to build themes by selecting variants from the library for each layer. The variant picker shows available variants grouped by effect, with descriptions. The editor no longer exposes raw parameter configuration for theme layers — parameter editing is the domain of the variant editor.

**Why this priority**: The UI must reflect the new data model for authors to work with it. Without this, the structural change is invisible to users.

**Independent Test**: Open the theme editor, create a new theme, add a layer by selecting a variant from a picker, save the theme, and reload it — the layer references the chosen variant with no inline parameters.

**Acceptance Scenarios**:

1. **Given** a user editing a theme layer, **When** they open the variant picker, **Then** they see variants grouped by base effect with names and descriptions.
2. **Given** a user has selected a variant for a layer, **When** they save the theme, **Then** the saved theme includes the variant reference on that layer.
3. **Given** a user wants to tweak a parameter for a theme layer, **When** they look at the layer editor, **Then** they are directed to edit the variant (or create a new one) rather than adding inline overrides.

---

### Edge Cases

- What happens when a variant referenced by a theme is deleted from the variant library? The theme fails validation and will not load — this is an error, not a warning. Variants referenced by themes should not be deleted without updating the theme.
- What happens when two themes reference the same variant and a user edits that variant? Both themes are affected — this is expected behavior since variants are shared resources. The variant picker should indicate which themes reference a variant.
- What happens when a theme layer's variant has a different base_effect than the variants in its effect_pool? This is allowed — the rotation engine already handles mixed-effect pools.
- What happens when the rotation engine selects a different variant for tiers 5-8 than the one specified on the theme layer? The rotation variant takes precedence for those tiers, same as today. The layer's variant serves as the default for tiers 1-4.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Theme layers MUST have a required `variant` field that references an effect variant by name from the variant library.
- **FR-002**: The effect for a layer MUST be derived from the referenced variant's `base_effect`. Theme layers MUST NOT have a separate `effect` field.
- **FR-003**: Theme layers MUST NOT have a `parameter_overrides` field. All parameter configuration MUST live in variants.
- **FR-004**: If the variant library fails to load, theme loading MUST fail with a clear error rather than silently degrading.
- **FR-005**: If a theme layer references a variant that does not exist in the library, the theme MUST fail validation with a clear error identifying the missing variant.
- **FR-006**: All 21 built-in themes MUST be migrated so that every layer (including alternate layers) references a variant with no inline parameter overrides.
- **FR-007**: New variants MUST be created for any theme layer parameter sets that do not match an existing variant. Each new variant MUST be named using effect-descriptive conventions based on key parameters (e.g., "Plasma Slow Pattern6"), and MUST have appropriate tags (tier_affinity, energy_level, section_roles, etc.).
- **FR-008**: The theme editor UI MUST provide a variant picker for selecting variants per layer, grouped by base effect. The editor MUST NOT expose raw parameter editing on theme layers.
- **FR-009**: The `effect_pool` field on layers MUST continue to function as a list of variant names for the rotation engine.
- **FR-010**: Theme-specific variants created during migration MUST have complete, meaningful tags to avoid polluting the rotation engine's scoring for unrelated contexts.
- **FR-011**: All code paths that resolve layer parameters (primary placement, flat model fallback, chase placement) MUST resolve the variant to obtain effect definition and parameters.
- **FR-012**: The variant library MUST be a required dependency for theme loading — not optional.
- **FR-013**: The runtime parameter variation tweak for repeated sections (`_apply_variation`) MUST be removed. Repeated sections MUST use theme alternates for visual variety; variant parameters MUST be applied consistently without runtime modification.

### Key Entities

- **EffectLayer**: A layer within a theme that references a variant by name, with a blend mode and optional effect pool. Contains no effect parameters — all parameter knowledge is delegated to the variant.
- **EffectVariant**: An existing entity — a named parameter preset for a base effect with scoring tags. Now serves as the sole parameter source for theme layers.
- **Theme**: An existing entity — composes variants into visual styles with palettes and mood metadata. After this feature, themes are purely compositional and contain no effect parameter configuration.
- **ThemeAlternate** (formerly ThemeVariant): An existing entity — alternate layer stacks for repeated sections. Its layers follow the same variant-only model as primary theme layers. Renamed from "ThemeVariant" to "Alternate" to avoid terminology collision with EffectVariant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 21 built-in themes load and validate successfully with every layer referencing a variant and containing no inline parameter overrides.
- **SC-002**: Generated sequences from migrated themes produce identical visual output compared to the pre-migration themes (same effects, same parameters on the same groups).
- **SC-003**: Theme authors can create a new theme using only variant selection (no manual parameter entry) in under 5 minutes via the editor UI.
- **SC-004**: The variant library grows by no more than 60 new variants from the migration, with each new variant having complete tags (no empty/null tag fields on tier_affinity, energy_level, or section_roles).
- **SC-005**: No EffectLayer in any built-in theme or ThemeVariant contains a parameter_overrides field after migration.
- **SC-006**: When a theme references a nonexistent variant, loading produces a clear, actionable error message identifying the theme name, layer index, and missing variant name.

## Clarifications

### Session 2026-04-09

- Q: ThemeVariant naming conflicts with EffectVariant after refactor — rename? → A: Rename ThemeVariant to "Alternate" (e.g., `theme.alternates` in JSON/code).
- Q: Naming convention for new variants created during migration? → A: Effect-descriptive names based on key parameters (e.g., "Plasma Slow Pattern6", "Wave Fast 4-Wave"), matching the existing variant library convention.
- Q: Keep the +/-5% runtime parameter tweak for repeated sections? → A: Remove it. Alternates handle repetition variety; variants should produce consistent, predictable output.

## Assumptions

- The project is in initial testing — no deployed custom themes exist that require backward-compatible migration.
- A variant library that fails to load is an unrecoverable error, not a degraded-mode scenario.
- Variant names are globally unique within the variant library (enforced by existing loading logic).
- The 3 existing effect_pool usages in builtin_themes.json already reference valid variant names and will continue to work unchanged.
- Theme-specific variants created during migration are equally valid for use by other themes or by the rotation engine — they are not scoped to a single theme.
- The theme editor UI currently exists and renders theme layers with parameter controls. It will be modified to use variant selection instead.
- Final parameter fine-tuning happens in xLights after sequence generation, not within the theme system.

## Dependencies

- The variant library and its loading infrastructure must be stable and functional before migration begins.
- The variant scoring system must correctly handle newly tagged variants without regression to existing rotation behavior.
