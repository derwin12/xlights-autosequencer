# Tasks: Theme and Effect Variant Separation

**Input**: Design documents from `/specs/033-theme-variant-separation/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included per constitution Principle IV (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Capture pre-migration state for regression validation

- [X] T001 Capture pre-migration parameter snapshot by extracting all 87 theme layer resolved parameters (effect name + parameter_overrides) from src/themes/builtin_themes.json into a test fixture file at tests/fixtures/themes/pre_migration_params.json
- [X] T002 [P] Run existing test suite and record baseline pass/fail state to confirm no pre-existing failures

---

## Phase 2: User Story 1 — Theme Layers Reference Variants Only (Priority: P1) 🎯 MVP

**Goal**: EffectLayer references variants by name only. ThemeVariant renamed to ThemeAlternate. Variant library becomes required. _apply_variation removed.

**Independent Test**: Create a minimal theme with variant-only layers, load it with the variant library, and verify the effect placer resolves correct effects and parameters from variants.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T003 [P] [US1] Write unit tests for new EffectLayer model (variant required, no effect/parameter_overrides/variant_ref fields) in tests/unit/test_themes_models.py
- [X] T004 [P] [US1] Write unit tests for ThemeAlternate rename (class name, from_dict with "alternates" key, to_dict) in tests/unit/test_themes_models.py
- [X] T005 [P] [US1] Write unit tests for validator requiring variant_library and rejecting missing variants as errors in tests/unit/test_themes_validator.py
- [X] T006 [P] [US1] Write unit tests for load_theme_library requiring variant_library parameter in tests/unit/test_themes_library.py
- [X] T007 [P] [US1] Write unit tests for effect_placer resolving variant params from library (no layer.parameter_overrides, no _apply_variation) in tests/unit/test_generator/test_effect_placer.py
- [X] T008 [P] [US1] Write integration test verifying a theme with variant-only layers produces correct effect placements end-to-end in tests/integration/test_variant_theme_integration.py

### Implementation for User Story 1

- [X] T009 [US1] Simplify EffectLayer dataclass in src/themes/models.py: remove effect, parameter_overrides, variant_ref fields; add required variant field; update from_dict() and to_dict()
- [X] T010 [US1] Rename ThemeVariant to ThemeAlternate in src/themes/models.py: rename class, rename Theme.variants field to Theme.alternates, update Theme.from_dict() and Theme.to_dict()
- [X] T011 [US1] Update validator in src/themes/validator.py: make variant_library required parameter, validate layer.variant exists in library (error not warning), derive effect from variant.base_effect for modifier/blend checks, remove parameter_overrides validation, rename ThemeVariant references to ThemeAlternate
- [X] T012 [US1] Update library loader in src/themes/library.py: make variant_library a required parameter in load_theme_library(), raise error if variant_library not provided, update save_custom_theme() to serialize new format
- [X] T013 [US1] Update effect_placer parameter resolution in src/generator/effect_placer.py: modify _place_effect_on_group() to resolve variant from variant_library to get effect_def and params, add variant_library parameter where needed, remove the 3-level resolution chain (lines 437-452)
- [X] T014 [US1] Remove _apply_variation function and its call site in src/generator/effect_placer.py (lines 779-787 and line 456)
- [X] T015 [US1] Update _flat_model_fallback() in src/generator/effect_placer.py to resolve variant from library instead of reading layer.effect and layer.parameter_overrides (lines 810-822)
- [X] T016 [US1] Update _place_chase_across_groups() in src/generator/effect_placer.py to resolve variant params from library instead of reading layer.parameter_overrides (line 519)
- [X] T017 [US1] Update theme.variants → theme.alternates references in src/generator/effect_placer.py (lines 158-162, 801-805)
- [X] T018 [US1] Make variant library loading required in src/generator/plan.py: remove try/except around variant_library loading (lines 148-161), pass variant_library to load_theme_library()
- [X] T019 [US1] Update theme routes API serialization in src/review/theme_routes.py: return new EffectLayer format (variant + blend_mode), update effect-pools endpoint to use variant field
- [X] T020 [US1] Update existing test fixtures and assertions across test files to use new EffectLayer format (variant field, no parameter_overrides): tests/unit/test_variant_theme_models.py, tests/unit/test_theme_routes.py, tests/unit/test_theme_writer.py, tests/unit/test_rotation.py, tests/integration/test_theme_variant_picker.py, tests/integration/test_themes_integration.py, tests/integration/test_rotation_integration.py

**Checkpoint**: New EffectLayer model works end-to-end. A test theme with variant-only layers loads, validates, and produces correct effect placements. Existing themes will NOT load yet (they still use old format — that's Phase 3).

---

## Phase 3: User Story 2 — Builtin Themes Migrated to Variant References (Priority: P2)

**Goal**: Create ~60-70 new variants for all 87 theme layers. Rewrite builtin_themes.json. Zero visual regression.

**Independent Test**: Load migrated builtin_themes.json, verify all 21 themes pass validation, and compare resolved parameters against pre-migration snapshot.

### Tests for User Story 2

- [X] T021 [US2] Write regression test comparing post-migration resolved parameters against pre-migration snapshot in tests/fixtures/themes/pre_migration_params.json in tests/integration/test_themes_integration.py

### Implementation for User Story 2

- [X] T022 [US2] Analyze and deduplicate the 87 theme layer parameter sets — group identical (same base_effect + same params) to determine unique variant count
- [X] T023 [US2] Create new Plasma variants (~12 unique) with effect-descriptive names and tags in src/variants/builtins/Plasma.json per research.md R7 tag strategy
- [X] T024 [P] [US2] Create new Color Wash variants (~7 unique) with effect-descriptive names and tags in src/variants/builtins/Color Wash.json
- [X] T025 [P] [US2] Create new Ripple variants (~6 unique) with effect-descriptive names and tags in src/variants/builtins/Ripple.json
- [X] T026 [P] [US2] Create new Liquid variants (~6 unique) with effect-descriptive names and tags in src/variants/builtins/Liquid.json
- [X] T027 [P] [US2] Create new Shockwave variants (~5 unique) with effect-descriptive names and tags in src/variants/builtins/Shockwave.json
- [X] T028 [P] [US2] Create new Wave variants (~5 unique) with effect-descriptive names and tags in src/variants/builtins/Wave.json
- [X] T029 [P] [US2] Create new Spirals variants (~5 unique) with effect-descriptive names and tags in src/variants/builtins/Spirals.json
- [X] T030 [P] [US2] Create new Fire variants (~5 unique) with effect-descriptive names and tags in src/variants/builtins/Fire.json
- [X] T031 [P] [US2] Create new Strobe variants (~5 unique) with effect-descriptive names and tags in src/variants/builtins/Strobe.json
- [X] T032 [P] [US2] Create new Bars variants (~5 unique) with effect-descriptive names and tags in src/variants/builtins/Bars.json
- [X] T033 [P] [US2] Create new Single Strand variants (~5 unique) with effect-descriptive names and tags in src/variants/builtins/Single Strand.json
- [X] T034 [P] [US2] Create new Butterfly variants (~4 unique) with effect-descriptive names and tags in src/variants/builtins/Butterfly.json
- [X] T035 [P] [US2] Create new Pinwheel variants (~4 unique) with effect-descriptive names and tags in src/variants/builtins/Pinwheel.json
- [X] T036 [P] [US2] Create new Meteors variants (~4 unique) with effect-descriptive names and tags in src/variants/builtins/Meteors.json
- [X] T037 [P] [US2] Create new Fan variants (~4 unique) with effect-descriptive names and tags in src/variants/builtins/Fan.json
- [X] T038 [P] [US2] Create remaining new variants (Marquee ~2, Tendril ~1, Fill ~1, Fireworks ~1) in their respective files under src/variants/builtins/
- [X] T039 [US2] Rewrite src/themes/builtin_themes.json: replace all layer effect + parameter_overrides with variant references, rename "variants" key to "alternates" for all 21 themes
- [X] T040 [US2] Run validation pass: load migrated themes + variant library, verify zero errors, compare resolved params against pre-migration snapshot from T001

**Checkpoint**: All 21 builtin themes load with variant-only layers. Resolved parameters exactly match pre-migration values. Regression test passes.

---

## Phase 4: User Story 3 — Theme Editor UI Supports Variant Selection (Priority: P2)

**Goal**: Replace parameter editing with variant picker in theme editor. Authors select variants, not raw parameters.

**Independent Test**: Open theme editor, create a new theme by selecting variants for layers, save and reload — layers reference variants with no inline parameters.

### Tests for User Story 3

- [X] T041 [US3] Write test for theme save/load round-trip with new format (variant-only layers) via theme routes in tests/unit/test_theme_routes.py

### Implementation for User Story 3

- [X] T042 [US3] Add GET /variants/api/list-grouped endpoint returning variants grouped by base_effect in src/review/theme_routes.py or src/review/variant_routes.py
- [X] T043 [US3] Replace effect selector + parameter controls with variant picker dropdown in src/review/static/theme-editor.js: loadVariantsForEffect → loadGroupedVariants, layer creation produces { variant: '', blend_mode: 'Normal' }
- [X] T044 [US3] Update layer serialization (getLayerData, getLayerDataFromContainer) to output { variant, blend_mode, effect_pool } with no effect or parameter_overrides in src/review/static/theme-editor.js
- [X] T045 [US3] Update alternates editor section in src/review/static/theme-editor.js: rename "variants" to "alternates" in UI labels and data access, use same variant picker for alternate layers
- [X] T046 [US3] Update read-only theme detail view in src/review/static/theme-editor.js to display variant names per layer instead of effect + parameter count

**Checkpoint**: Theme editor creates, saves, and loads themes using variant-only format. No parameter editing UI on theme layers.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup across all stories

- [X] T047 [P] Remove dead code: delete EffectLayer.variant_ref references from any remaining files (src/cli_old.py, src/variants/importer.py if they reference theme parameter_overrides)
- [X] T048 [P] Update test fixtures that still use old EffectLayer format in tests/fixtures/themes/ and tests/fixtures/variants/
- [X] T049 Run full test suite and fix any remaining failures across all test files
- [X] T050 Run quickstart.md validation: verify the documented dependency chain (EffectLibrary → VariantLibrary → ThemeLibrary) works as described

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **US1 (Phase 2)**: Depends on Setup (T001 provides regression fixture)
- **US2 (Phase 3)**: Depends on US1 completion (new model must be in place before migrating data)
- **US3 (Phase 4)**: Depends on US1 completion (UI must use new model). Can run in parallel with US2.
- **Polish (Phase 5)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Setup — foundational model change
- **User Story 2 (P2)**: DEPENDS on US1 — needs new EffectLayer model to write migrated themes
- **User Story 3 (P2)**: DEPENDS on US1 — needs new EffectLayer model for UI. Can run in parallel with US2.

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Model changes before generator/placer changes
- Core implementation before API/UI updates
- Story complete before moving to next priority

### Parallel Opportunities

- T003-T008 (US1 tests) can all run in parallel
- T009-T010 (model changes) are sequential — T009 before T010
- T013-T017 (effect_placer changes) are sequential within the file
- T023-T038 (variant creation) can ALL run in parallel — different JSON files
- T042-T046 (UI changes) are mostly sequential within theme-editor.js
- US2 and US3 can run in parallel after US1 completes

---

## Parallel Example: User Story 2 (Variant Creation)

```bash
# All variant creation tasks can run simultaneously (different files):
T023: Create Plasma variants in src/variants/builtins/Plasma.json
T024: Create Color Wash variants in src/variants/builtins/Color Wash.json
T025: Create Ripple variants in src/variants/builtins/Ripple.json
T026: Create Liquid variants in src/variants/builtins/Liquid.json
T027: Create Shockwave variants in src/variants/builtins/Shockwave.json
T028: Create Wave variants in src/variants/builtins/Wave.json
T029: Create Spirals variants in src/variants/builtins/Spirals.json
T030: Create Fire variants in src/variants/builtins/Fire.json
# ... (all 16 variant tasks in parallel)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (capture snapshot)
2. Complete Phase 2: US1 (core model changes + tests)
3. **STOP and VALIDATE**: Verify new model works with a test theme
4. At this point the model is proven — themes must use variants

### Incremental Delivery

1. Setup → Snapshot captured
2. US1 → Core model proven with test themes → MVP
3. US2 → All 21 builtin themes migrated → Regression-free
4. US3 → Theme editor uses variant picker → Full feature
5. Polish → Dead code removed, all tests green

### Parallel Team Strategy

With multiple developers after US1 completes:
- Developer A: US2 (variant creation + theme migration)
- Developer B: US3 (theme editor UI)
- Both merge independently, then Polish phase

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- The ~60-70 new variant files in US2 are the bulk of the work but highly parallelizable
- Pre-migration snapshot (T001) is critical for regression validation — do not skip
