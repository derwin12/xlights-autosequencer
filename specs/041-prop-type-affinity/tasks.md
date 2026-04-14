# Tasks: Prop-Type Effect Affinity (041)

**Input**: Design documents from `/specs/041-prop-type-affinity/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new files or dependencies required. Verify existing infrastructure.

- [X] T001 Verify `PowerGroup.prop_type` is populated for all groups by inspecting `src/grouper/grouper.py` — confirm `dominant_prop_type()` call and field assignment exist

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Understand the current `build_rotation_plan()` assignment loop before modifying it.

- [X] T002 Read and document the current variant-assignment loop in `src/generator/rotation.py` `build_rotation_plan()` — identify the exact insertion point for within-tier base-effect tracking (locate the line where `results[0]` or `unused[0]` is selected)

**Checkpoint**: Assignment loop understood; insertion point identified.

---

## Phase 3: User Story 1 — Within-Tier Base-Effect Diversity (Priority: P1) MVP

**Goal**: No two groups in the same tier 5–8 receive the same base effect in the same section (best-effort, 0.3 score floor for fallback to duplication).

**Independent Test**: Generate a sequence, inspect `group_effects` for a section with ≥3 tier-6 groups. At least 2 distinct base effects should be present.

### Tests for User Story 1

- [X] T003 [P] [US1] Write unit test: given 5 mock arch groups in tier 6 with identical scoring, verify `build_rotation_plan()` assigns ≥3 distinct base effects across the 5 groups in tests/unit/test_rotation_diversity.py
- [X] T004 [P] [US1] Write unit test: given 1 group in tier 6, verify it receives its top-scored variant unchanged (no regression) in tests/unit/test_rotation_diversity.py
- [X] T005 [P] [US1] Write unit test: given 10 arch groups but only 4 distinct suitable effects, verify all 4 effects are used before any reuse occurs in tests/unit/test_rotation_diversity.py
- [X] T006 [P] [US1] Write unit test: verify the 0.3 score floor — when the only unclaimed effect scores 0.2 for a group's prop type, the group falls back to its own top-scored effect (allowing duplication) in tests/unit/test_rotation_diversity.py

### Implementation for User Story 1

- [X] T007 [US1] Add `used_effects_per_tier: dict[int, set[str]]` tracking to `build_rotation_plan()` in src/generator/rotation.py — initialize as `defaultdict(set)`, reset per section
- [X] T008 [US1] Modify the variant-selection logic in `build_rotation_plan()` in src/generator/rotation.py — after scoring, iterate ranked results and pick the first variant whose `base_effect` is not in `used_effects_per_tier[tier]` AND whose score ≥ 0.3; if none qualifies, fall back to `results[0]`
- [X] T009 [US1] After selecting a variant, add `variant.base_effect` to `used_effects_per_tier[tier]` in src/generator/rotation.py
- [X] T010 [US1] Ensure the dedup only applies to tiers 5–8 by gating the new logic with `if tier >= 5:` in src/generator/rotation.py
- [X] T011 [US1] Run tests: `python3 -m pytest tests/unit/test_rotation_diversity.py -v`

**Checkpoint**: Within-tier diversity working for tier 5–8. SC-001 met.

---

## Phase 4: User Story 2 — Tree/Radial Props Show Rotational Effects (Priority: P1)

**Goal**: Tree-typed groups receive tree-ideal effects (Pinwheel, Spirals, Fan, Ripple, Shockwave) in ≥70% of assignments.

**Independent Test**: Generate a sequence with identifiable tree groups. Inspect assigned base effects. At least 70% should be tree-ideal.

### Tests for User Story 2

- [X] T012 [P] [US2] Write unit test: given a tree-typed group scored against the full variant library, verify the top-ranked variant's base effect has `prop_suitability["tree"] == "ideal"` in tests/unit/test_rotation_diversity.py
- [X] T013 [P] [US2] Write unit test: given a tree group and an arch group in the same tier, verify they receive different base effects in tests/unit/test_rotation_diversity.py

### Implementation for User Story 2

- [X] T014 [US2] Verify that the existing RotationEngine scoring with `prop_type` weight 0.30 in src/variants/scorer.py already produces tree-ideal effects as top picks for tree groups — this is a read-and-confirm task, not a code change
- [X] T015 [US2] If T014 reveals that tree-ideal effects are NOT consistently top-scored for tree groups, investigate whether the theme's variant pool is constraining selection and document the finding
- [X] T016 [US2] Run combined tests: `python3 -m pytest tests/unit/test_rotation_diversity.py -v`

**Checkpoint**: Tree/radial groups consistently get appropriate effects. SC-002 met.

---

## Phase 5: User Story 3 — Fallback Pool Respects Prop Suitability (Priority: P2)

**Goal**: `_build_effect_pool()` excludes `not_recommended` effects for the group's prop type.

**Independent Test**: Call `_build_effect_pool()` with `prop_type="arch"` and verify no `not_recommended` effects for arch are in the returned pool.

### Tests for User Story 3

- [X] T017 [P] [US3] Write unit test: `_build_effect_pool(effect_library, prop_type="arch")` excludes effects rated `not_recommended` for arch in tests/unit/test_effect_placer.py
- [X] T018 [P] [US3] Write unit test: `_build_effect_pool(effect_library, prop_type=None)` returns the full pool (backward compatibility) in tests/unit/test_effect_placer.py
- [X] T019 [P] [US3] Write unit test: when all `_PROP_EFFECT_POOL` effects are `not_recommended` for a hypothetical prop type, verify the pool relaxes to include `possible`-rated effects in tests/unit/test_effect_placer.py

### Implementation for User Story 3

- [X] T020 [US3] Add `prop_type: str | None = None` parameter to `_build_effect_pool()` in src/generator/effect_placer.py
- [X] T021 [US3] Add filtering logic: when `prop_type` is provided, skip effects where `edef.prop_suitability.get(prop_type, "possible") == "not_recommended"` in src/generator/effect_placer.py
- [X] T022 [US3] Add empty-pool fallback: if filtering empties the pool, re-call without prop_type filtering in src/generator/effect_placer.py
- [X] T023 [US3] Wire `group.prop_type` to the `_build_effect_pool()` call site at the tier 6–7 fallback path in `place_effects()` in src/generator/effect_placer.py (pass `prop_type=group.prop_type`)
- [X] T024 [US3] Run tests: `python3 -m pytest tests/unit/test_effect_placer.py -v -k "build_effect_pool"`

**Checkpoint**: Fallback pool is prop-type-aware. SC-003 met.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T025 Run full test suite: `python3 -m pytest tests/ -v` and verify no regressions (SC-004)
- [X] T026 Run quickstart.md validation: generate a sequence and inspect tier-6 group effects for diversity

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — immediate
- **Phase 2 (Foundational)**: Depends on Phase 1 — read-only investigation
- **Phase 3 (US1)**: Depends on Phase 2 — core implementation
- **Phase 4 (US2)**: Depends on Phase 3 — US1's within-tier dedup enables tree/radial variety
- **Phase 5 (US3)**: Can start after Phase 2 — independent of US1/US2 (different file)
- **Phase 6 (Polish)**: Depends on all desired user stories

### User Story Dependencies

- **US1 (Within-tier diversity)**: Foundational only — MVP target
- **US2 (Tree/radial routing)**: Depends on US1 (within-tier dedup is what allows tree effects to surface when arch effects no longer monopolize)
- **US3 (Fallback pool filtering)**: Independent — different file (`effect_placer.py`), different code path

### Parallel Opportunities

- T003, T004, T005, T006 can all run in parallel (same test file, different test functions)
- T012, T013 can run in parallel
- T017, T018, T019 can run in parallel
- US3 (Phase 5) can run in parallel with US1/US2 (different files)

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002)
3. Complete Phase 3: US1 — Within-Tier Diversity (T003–T011)
4. **STOP and VALIDATE**: Generate a sequence, verify ≥2 distinct effects in tier-6 groups
5. If satisfactory, move to US2 and US3

### Incremental Delivery

1. Setup + Foundational → understand current code
2. US1 (within-tier diversity) → visible variety across the house (MVP)
3. US2 (tree/radial routing) → confirm tree groups get rotational effects
4. US3 (fallback pool) → close edge-case gap in `_build_effect_pool()`
5. Polish → full regression test + quickstart validation

---

## Notes

- [P] tasks = different files or independent test functions
- [Story] label maps task to specific user story
- US1 is the MVP — delivers the visible "no more all-Bars" fix
- US2 is largely a verification pass — the RotationEngine's existing scoring should already prefer tree-ideal effects once US1's dedup prevents arch-effect pile-up
- US3 is a separate code path fix that can proceed in parallel
