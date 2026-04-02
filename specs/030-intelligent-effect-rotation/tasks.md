# Tasks: Intelligent Effect Rotation

**Input**: Design documents from `/specs/030-intelligent-effect-rotation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Constitution**: v1.0.0 — Test-First Development (Principle IV) requires tests before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create new modules and test fixtures

- [x] T001 Create src/generator/rotation.py module with RotationEngine, RotationPlan, and RotationEntry dataclasses per data-model.md
- [x] T002 [P] Create src/grouper/symmetry.py module with SymmetryGroup dataclass and detect_symmetry_pairs() stub per data-model.md
- [x] T003 [P] Create tests/fixtures/themes/theme_with_effect_pool.json — minimal theme with 2 layers, one having effect_pool of 3-4 variant names per quickstart.md

---

## Phase 2: Foundational — Prop Type Classification & Graduated Scoring (Blocking)

**Purpose**: Prop type infrastructure (merged from 029) + core data model changes. All user stories depend on this.

**CRITICAL**: No user story work can begin until this phase is complete.

**Note**: DISPLAY_AS_TO_PROP_TYPE mapping, dominant_prop_type(), and PowerGroup.prop_type are partially implemented in uncommitted changes on src/grouper/layout.py and src/grouper/grouper.py. Tasks below cover completing and testing that work.

### Tests for Foundation

- [x] T004 [P] Write unit tests for DISPLAY_AS_TO_PROP_TYPE mapping and prop_type_for_display_as() in tests/unit/test_grouper/test_layout.py — test all known DisplayAs values map to correct keys, unknown values default to "outline", empty string defaults to "outline"
- [x] T005 [P] Write unit tests for dominant_prop_type() in tests/unit/test_grouper/test_layout.py — test majority vote, alphabetical tiebreaking, empty list returns "outline"
- [x] T006 [P] Write unit tests for PowerGroup.prop_type population in tests/unit/test_grouper/test_grouper.py — test that generate_groups() populates prop_type on all non-empty groups from member DisplayAs values
- [x] T007 [P] Write unit tests for graduated _score_prop_type() in tests/unit/test_variant_scorer.py — test ideal=1.0, good=0.75, possible=0.25, not_recommended=0.0, unknown=0.0, no context=0.5
- [x] T008 [P] Write unit tests for RotationEntry and RotationPlan dataclasses in tests/unit/test_rotation.py — test construction, field defaults, serialization to dict
- [x] T009 [P] Write unit tests for ScoringContext mapping from SectionEnergy + PowerGroup + Theme in tests/unit/test_rotation.py — test energy_score→energy_level, tier→tier_affinity, label→section_role mappings per research.md R2
- [x] T010 [P] Write unit tests for EffectLayer.effect_pool field in tests/unit/test_variant_theme_models.py — test from_dict()/to_dict() with effect_pool present and absent, backward compatibility

### Implementation for Foundation

- [x] T011 Finalize DISPLAY_AS_TO_PROP_TYPE mapping, prop_type_for_display_as(), and dominant_prop_type() in src/grouper/layout.py — verify existing implementation covers all FR-000a DisplayAs values, add any missing entries
- [x] T012 Finalize PowerGroup.prop_type field and population in src/grouper/grouper.py — verify existing implementation correctly populates prop_type via dominant_prop_type() for all groups in generate_groups()
- [x] T013 Update _score_prop_type() in src/variants/scorer.py — replace binary check (1.0 if present, 0.0 if absent) with graduated scoring: ideal=1.0, good=0.75, possible=0.25, not_recommended=0.0 per FR-000c
- [x] T014 Add effect_pool field to EffectLayer in src/themes/models.py — optional list[str], default empty list, include in from_dict()/to_dict(), backward compatible
- [x] T015 Implement build_scoring_context() in src/generator/rotation.py — maps SectionEnergy + PowerGroup + Theme to ScoringContext per research.md R2 mapping table
- [x] T016 Update theme validator in src/themes/validator.py — when effect_pool is set, validate each variant name exists in VariantLibrary (warn, don't error on missing)

**Checkpoint**: Foundation ready — prop_type on every PowerGroup, graduated scorer, EffectLayer has effect_pool, ScoringContext mapping works, RotationPlan model exists. All foundational tests pass.

---

## Phase 3: User Story 1 — Theme-Aware Effect Selection (Priority: P1) MVP

**Goal**: Replace hardcoded tier 5-8 rotation with intelligent variant selection using the scorer

**Independent Test**: Generate a sequence for a high-energy section and verify effects are drawn from high-energy variants appropriate for each prop type, with at least 2 different effects across groups.

### Tests for User Story 1

- [x] T017 [P] [US1] Write unit tests for RotationEngine.select_variant_for_group() in tests/unit/test_rotation.py — test that it calls rank_variants with correct ScoringContext, returns top-scoring variant, handles empty results via fallback
- [x] T018 [P] [US1] Write integration test in tests/integration/test_rotation_integration.py — build a section with 4 groups (different prop types), run rotation, verify each group gets a variant whose energy_level matches section energy and whose base_effect is suitable for the group's prop type

### Implementation for User Story 1

- [x] T019 [US1] Implement RotationEngine.select_variant_for_group() in src/generator/rotation.py — build ScoringContext from section/group/theme, call rank_variants_with_fallback(), return top result from full variant library. Effect pool filtering is added later in US3 (T029)
- [x] T020 [US1] Implement RotationEngine.build_rotation_plan() in src/generator/rotation.py — iterate sections × tier 5-8 groups, call select_variant_for_group() per group, populate RotationPlan with RotationEntry objects including score and breakdown
- [x] T021 [US1] Update place_effects() in src/generator/effect_placer.py — accept rotation_plan parameter; for tier 5-8 groups, look up the RotationEntry and use the selected variant's base_effect + parameter_overrides instead of hardcoded pool rotation. Remove _PROP_EFFECT_POOL and _build_effect_pool()
- [x] T022 [US1] Update build_plan() in src/generator/plan.py — load variant_library, construct RotationEngine, call build_rotation_plan(), pass rotation_plan to place_effects() for each section assignment

**Checkpoint**: Tier 5-8 groups now get scored variant selection instead of round-robin. Existing themes (no effect_pool) work via full-library fallback. US1 is independently functional.

---

## Phase 4: User Story 2 — Effect Variety Within Sections (Priority: P1)

**Goal**: Ensure different groups at the same tier get different variants, and repeated sections vary their assignments

**Independent Test**: Generate a sequence with 3 consecutive verse sections and 4 prop groups. Verify at least 3 distinct variants per section, and 50%+ differences between repeated verses.

### Tests for User Story 2

- [x] T023 [P] [US2] Write unit tests for intra-section variety in tests/unit/test_rotation.py — given 4 groups at tier 6 and sufficient variants, verify at least 3 distinct variants are selected; given 2 groups and only 1 variant available, verify graceful reuse
- [x] T024 [P] [US2] Write unit tests for cross-section repeat penalty in tests/unit/test_rotation.py — given two consecutive "verse" sections, verify at least 50% of group assignments differ; given a non-repeating section type, verify no penalty applied

### Implementation for User Story 2

- [x] T025 [US2] Implement intra-section deduplication in RotationEngine.build_rotation_plan() in src/generator/rotation.py — after selecting a variant for a group, add it to an exclusion set for subsequent groups at the same tier in that section. If exclusion leaves no candidates, allow reuse of the highest-scoring already-used variant
- [x] T026 [US2] Implement cross-section repeat penalty in RotationEngine.build_rotation_plan() in src/generator/rotation.py — track previous_assignments per group; when scoring for a new section of the same type (same label), apply 0.5× penalty multiplier to variants used in the previous instance of that section type. Seed penalty deterministically by section index per FR-009

**Checkpoint**: Within-section variety and across-section variation are enforced. US2 is independently functional.

---

## Phase 5: User Story 3 — Theme Effect Pool Definition (Priority: P2)

**Goal**: Theme layers can define effect_pool lists; the rotation engine selects from the pool with scorer fallback

**Independent Test**: Create a theme with a 4-variant effect_pool on one layer. Generate a sequence with 6 sections and 3 groups. Verify all 4 pool variants appear at least once.

### Tests for User Story 3

- [x] T027 [P] [US3] Write unit tests for pool-based selection in tests/unit/test_rotation.py — given a layer with effect_pool of 3 variants, verify selection is restricted to pool entries when they score above threshold; verify fallback to full library when pool variants score below threshold
- [x] T028 [P] [US3] Write integration test in tests/integration/test_rotation_integration.py — load theme_with_effect_pool.json fixture, generate rotation plan across multiple sections, verify all pool variants appear at least once

### Implementation for User Story 3

- [x] T029 [US3] Update RotationEngine.select_variant_for_group() in src/generator/rotation.py — when layer.effect_pool is non-empty, build candidate list from pool variant names looked up in variant_library; score these candidates; if best score < 0.3 threshold, fall back to full library scoring
- [x] T030 [US3] Update builtin_themes.json in src/themes/builtin_themes.json — add effect_pool entries to 3-5 themes for variety (e.g., the top layer of "Ethereal Frost", "Neon Pulse", "Inferno")
- [x] T031 [US3] Add GET /themes/<name>/effect-pools endpoint in src/review/server.py — returns the effect_pool configuration per layer for a theme per contracts/api-endpoints.md

**Checkpoint**: Theme effect pools work. Pool selection → scorer fallback → full library fallback chain is functional. US3 is independently functional.

---

## Phase 6: User Story 4 — Visual Coherence Constraints (Priority: P2)

**Goal**: Symmetry pair detection and enforcement; section transition continuity

**Independent Test**: Generate a sequence with "Arch Left"/"Arch Right" groups and verify they always get the same effect. Verify adjacent sections share at least one effect on a tier 5-8 group.

### Tests for User Story 4

- [x] T032 [P] [US4] Write unit tests for symmetry detection in tests/unit/test_symmetry.py — test name-based pairing (Left/Right, 1/2, A/B), spatial pairing (mirrored norm_x), manual override, no false positives on unrelated groups
- [x] T033 [P] [US4] Write unit tests for symmetry enforcement in tests/unit/test_rotation.py — given a symmetry pair, verify both groups get the same variant; verify direction parameters are mirrored for group_b
- [x] T034 [P] [US4] Write unit tests for section transition continuity in tests/unit/test_rotation.py — given two adjacent sections, verify at least one tier 5-8 group retains the same variant across the boundary

### Implementation for User Story 4

- [x] T035 [US4] Implement detect_symmetry_pairs() in src/grouper/symmetry.py — name-based matching (strip Left/Right/L/R/1/2/A/B suffixes, match remaining), spatial matching (groups at same tier with mirrored norm_x > 0.65 / < 0.35 and similar norm_y within 0.15), manual override via optional overrides parameter. Returns list[SymmetryGroup]
- [x] T036 [US4] Integrate symmetry into RotationEngine.build_rotation_plan() in src/generator/rotation.py — after selecting variant for group_a of a symmetry pair, assign the same variant to group_b with mirrored direction_cycle values. Skip scoring for group_b
- [x] T037 [US4] Implement section transition continuity in RotationEngine.build_rotation_plan() in src/generator/rotation.py — after assigning all groups in a section, check if at least one tier 5-8 group retained its variant from the previous section. If not, force the lowest-tier group (tier 5 if present, else 6) to keep its previous variant per research.md R7

**Checkpoint**: Symmetry pairs are detected and enforced. Section transitions maintain continuity. US4 is independently functional.

---

## Phase 7: User Story 5 — Rotation Preview and Diagnostics (Priority: P3)

**Goal**: Users can view effect assignments per section/group with scoring rationale via CLI and web dashboard

**Independent Test**: Generate a sequence, run rotation-report CLI command, verify output shows per-section/per-group assignments with scores.

### Tests for User Story 5

- [x] T038 [P] [US5] Write unit tests for rotation report CLI command in tests/unit/test_cli.py — test table output format, JSON output format, section/group filtering, empty plan handling
- [x] T039 [P] [US5] Write integration test for GET /rotation-report endpoint in tests/integration/test_rotation_integration.py — test response shape, filtering, 404 for unknown hash

### Implementation for User Story 5

- [x] T040 [US5] Add rotation-report CLI subcommand in src/cli.py — loads plan JSON, extracts rotation_plan, displays table per contracts/cli-commands.md. Options: --section, --group, --format (table/json)
- [x] T041 [US5] Add GET /rotation-report/<plan_hash> endpoint in src/review/server.py — returns rotation plan JSON with entries, symmetry_pairs, and summary per contracts/api-endpoints.md
- [x] T042 [US5] Persist RotationPlan in sequence plan JSON output in src/generator/plan.py — add rotation_plan dict to the plan JSON written by build_plan(), keyed by source audio hash for retrieval

**Checkpoint**: Rotation diagnostics available via CLI and API. US5 is independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Validate end-to-end quality and backward compatibility

- [x] T043 Validate backward compatibility — run existing test suite, confirm all themes without effect_pool produce identical output to pre-feature behavior (SC-005)
- [x] T044 Run quickstart.md validation — verify all documented CLI commands and API endpoints work as described
- [x] T045 Verify variety metrics across 3+ test songs — confirm SC-001 (3+ variants per section), SC-002 (50% cross-section variety), SC-003 (no empty groups)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phases 3-7)**: All depend on Foundational phase completion
  - US1 (Phase 3): No dependencies on other stories — **MVP**
  - US2 (Phase 4): Depends on US1 (extends RotationEngine.build_rotation_plan)
  - US3 (Phase 5): Depends on US1 (extends select_variant_for_group with pool logic)
  - US4 (Phase 6): Depends on US1 (extends build_rotation_plan with symmetry + continuity)
  - US5 (Phase 7): Depends on US1 (reads RotationPlan produced by US1)
- **Polish (Phase 8)**: Depends on US1 + US2 at minimum

### User Story Dependencies

- **US1 (P1)**: Foundation only — core scorer integration
- **US2 (P1)**: US1 — extends rotation plan with variety constraints
- **US3 (P2)**: US1 — extends selection with pool filtering
- **US4 (P2)**: US1 — extends rotation plan with symmetry and continuity
- **US5 (P3)**: US1 — reads rotation plan for diagnostics

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Constitution Principle IV)
- Models → Engine logic → Integration with effect_placer
- Core implementation before integration
- Commit after each task or logical group

### Parallel Opportunities

- T002 + T003 can run in parallel (different files)
- T004-T010 can all run in parallel (different test files/areas)
- T017 + T018 can run in parallel (unit vs integration tests)
- T023 + T024 can run in parallel (different test scenarios)
- T027 + T028 can run in parallel (unit vs integration)
- T032 + T033 + T034 can run in parallel (symmetry vs rotation vs continuity tests)
- T038 + T039 can run in parallel (CLI vs API tests)
- US3, US4, and US5 can all start in parallel after US1 (they extend different aspects of the rotation engine)

---

## Parallel Example: User Story 1

```bash
# Launch tests in parallel:
Task T017: "Unit tests for select_variant_for_group() in tests/unit/test_rotation.py"
Task T018: "Integration test for rotation in tests/integration/test_rotation_integration.py"

# After tests written, implement sequentially (same module, dependencies):
Task T019: "Implement select_variant_for_group() in src/generator/rotation.py"
Task T020: "Implement build_rotation_plan() in src/generator/rotation.py" (depends on T019)
Task T021: "Update place_effects() in src/generator/effect_placer.py" (depends on T020)
Task T022: "Update build_plan() in src/generator/plan.py" (depends on T021)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (model + context mapping)
3. Complete Phase 3: User Story 1 (scorer-based selection)
4. **STOP and VALIDATE**: Generate a sequence, verify tier 5-8 effects are scored, not round-robin
5. Deliver: Intelligent effect selection replaces hardcoded pool

### Incremental Delivery

1. Setup + Foundational → Core models and context mapping
2. Add US1 → Scored variant selection (MVP!)
3. Add US2 → Intra/cross-section variety
4. Add US3 → Theme effect pool support
5. Add US4 → Symmetry + transition continuity
6. Add US5 → Rotation diagnostics
7. Polish → Validate metrics and backward compatibility

### Parallel Team Strategy

With multiple developers after US1:
- Developer A: US2 (variety constraints) + US5 (diagnostics)
- Developer B: US3 (theme pools) + US4 (symmetry + continuity)
- Developer C: Polish (validation + metrics)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Constitution requires test-first: write tests, confirm they fail, then implement
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
