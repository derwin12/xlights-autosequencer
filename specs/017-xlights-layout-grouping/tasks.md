# Tasks: xLights Layout Grouping

**Input**: Design documents from `specs/017-xlights-layout-grouping/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-contract.md

**Tests**: Included per constitution (Test-First Development — Red-Green-Refactor is mandated).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2…)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the module skeleton, fixture files, and stubs so all phases can begin cleanly.

- [x] T001 Create `src/grouper/` package with stub files: `__init__.py`, `layout.py`, `classifier.py`, `grouper.py`, `writer.py`
- [x] T002 [P] Create test fixture XML files: `tests/fixtures/grouper/simple_layout.xml` (8 props, varied positions), `tests/fixtures/grouper/hero_layout.xml` (includes SingingFace with subModel children), `tests/fixtures/grouper/minimal_layout.xml` (1 prop edge case)
- [x] T003 [P] Create empty test module files: `tests/unit/test_grouper_layout.py`, `tests/unit/test_grouper_classifier.py`, `tests/unit/test_grouper_groups.py`, `tests/unit/test_grouper_writer.py`, `tests/integration/test_grouper_integration.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Layout parsing, coordinate normalization, and XML round-trip write — these underpin every user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Write failing tests for `parse_layout()` in `tests/unit/test_grouper_layout.py` — verify Prop fields (name, world_x/y/z, parm1/parm2, sub_models, pixel_count) parsed from `simple_layout.xml`
- [x] T005 Implement `parse_layout(path) -> Layout` in `src/grouper/layout.py` — parse `<model>` elements, extract `WorldPosX/Y/Z`, `ScaleX/Y`, `parm1`, `parm2`, `<subModel>` children; preserve raw `ET.ElementTree` on `Layout`
- [x] T006 [P] Write failing tests for `SpatialBounds` and `normalize_coords()` in `tests/unit/test_grouper_classifier.py` — verify 0.0–1.0 range, midpoint fallback when all props share same coordinate
- [x] T007 Implement `SpatialBounds`, `normalize_coords(props) -> None` (mutates `Prop.norm_x/norm_y`) in `src/grouper/classifier.py`; handle zero-range edge case by defaulting to 0.5
- [x] T008 [P] Write failing tests for XML round-trip in `tests/unit/test_grouper_writer.py` — verify `inject_groups()` removes old auto-prefixed `<ModelGroup>` elements and appends new ones; verify `write_layout()` produces valid XML
- [x] T009 Implement `inject_groups(raw_tree, groups) -> ET.ElementTree` (removes `01_BASE_`…`06_HERO_` prefixed groups, appends new `<ModelGroup name=... models=... />`) and `write_layout(layout, path)` in `src/grouper/writer.py`

**Checkpoint**: Foundation ready — `parse → normalize → write` round-trip works on all three fixture files.

---

## Phase 3: User Story 1 — Generate Power Groups from Layout (Priority: P1) 🎯 MVP

**Goal**: Given any valid layout file, generate Canvas (01), Spatial (02), Architecture (03), and Fidelity (05) groups and write them back to the XML.

**Independent Test**: Run `xlight-analyze group-layout tests/fixtures/grouper/simple_layout.xml --dry-run` and confirm output contains `01_BASE_All`, `02_GEO_Top/Mid/Bot/Left/Center/Right`, `03_TYPE_Vertical`, `03_TYPE_Horizontal`, `05_TEX_HiDens`, `05_TEX_LoDens`.

- [x] T010 [US1] Write failing tests for `classify_props()` in `tests/unit/test_grouper_classifier.py` — verify `aspect_ratio` (ScaleY/ScaleX), `pixel_count` (parm1*parm2), `is_vertical` flag set correctly
- [x] T011 [P] [US1] Implement `classify_props(props) -> None` (mutates `Prop.aspect_ratio`, `pixel_count`) in `src/grouper/classifier.py`
- [x] T012 [US1] Write failing tests for tier 1 and tier 2 group generation in `tests/unit/test_grouper_groups.py` — verify `01_BASE_All` contains all props; verify each `02_GEO_` bin uses correct Y/X threshold (>0.66, 0.33–0.66, <0.33)
- [x] T013 [US1] Implement `generate_groups(props, profile=None) -> list[PowerGroup]` in `src/grouper/grouper.py` — start with tiers 1 (Canvas: one group, all props) and 2 (Spatial: 6 coordinate-bin groups, skip empty bins)
- [x] T014 [US1] Extend `generate_groups()` in `src/grouper/grouper.py` to add tier 3 (Architecture: `03_TYPE_Vertical` for aspect_ratio ≥ 1.5, `03_TYPE_Horizontal` otherwise) and tier 5 (Fidelity: `05_TEX_HiDens` for pixel_count > 500, `05_TEX_LoDens` otherwise)
- [x] T015 [US1] Add `group_layout_cmd` Click command to `src/cli.py` — accepts `LAYOUT_FILE` path argument, calls `parse_layout → normalize_coords → classify_props → generate_groups → inject_groups → write_layout`; print summary line (props count, groups generated, output path)
- [x] T016 [US1] Write integration test for full round-trip in `tests/integration/test_grouper_integration.py` — parse `simple_layout.xml`, run full pipeline, assert output XML contains expected `<ModelGroup>` elements with correct `models=` attribute; assert idempotency (run twice → same output); assert all generated `<ModelGroup name>` values match regex `^\d{2}_[A-Z]+_\w+$` (SC-002 naming convention)

**Checkpoint**: US1 complete — `group-layout` command produces Canvas, Spatial, Architecture, and Fidelity groups and writes valid XML.

---

## Phase 4: User Story 2 — Select a Show Profile (Priority: P2)

**Goal**: `--profile energetic/cinematic/technical` filters which tiers are generated.

**Independent Test**: Run the command three times with different `--profile` values against the same layout; verify each output contains only the tiers defined for that profile and no others.

- [x] T017 [P] [US2] Write failing tests for `ShowProfile` filtering in `tests/unit/test_grouper_groups.py` — verify energetic generates tiers {3,4,6}, cinematic generates {1,2,6}, technical generates {1,5}; no-profile generates all tiers; assert no-profile group set is a superset of every individual profile's group set (SC-006)
- [x] T018 [US2] Add `ShowProfile` dataclass/enum and `PROFILE_TIERS` mapping to `src/grouper/grouper.py`; filter `generate_groups()` output by active tiers when `profile` is provided
- [x] T019 [US2] Wire `--profile` Click option to `group_layout_cmd` in `src/cli.py` — pass profile value to `generate_groups()`; display active profile name in summary output

**Checkpoint**: US2 complete — profile flag selects correct tier subsets; no-profile still generates everything.

---

## Phase 5: User Story 3 — Rhythmic Beat Groups (Priority: P3)

**Goal**: Add tier 4 beat groups: left-to-right (`04_BEAT_LR_*`) and center-out (`04_BEAT_CO_*`) in sets of 4.

**Independent Test**: Run on `simple_layout.xml` (8 props); verify `04_BEAT_LR_1`, `04_BEAT_LR_2`, `04_BEAT_CO_1`, `04_BEAT_CO_2` each contain exactly 4 props; LR groups sorted by `norm_x`, CO groups sorted by `|norm_x - 0.5|`.

- [x] T020 [P] [US3] Write failing tests for beat group generation in `tests/unit/test_grouper_groups.py` — verify LR partitions by ascending `norm_x`; CO partitions by ascending distance from 0.5; remainder group (1–3 props) not discarded; both algorithms run independently over same prop list
- [x] T021 [US3] Implement tier 4 beat group generation in `src/grouper/grouper.py` — Method A: sort props by `norm_x`, chunk into groups of 4, name `04_BEAT_LR_N`; Method B: sort props by `abs(norm_x - 0.5)`, chunk into groups of 4, name `04_BEAT_CO_N`

**Checkpoint**: US3 complete — beat groups present in output when profile includes tier 4 (or no profile).

---

## Phase 6: User Story 4 — Hero and Sub-Model Detection (Priority: P4)

**Goal**: Detect face and tree props by name; bundle their sub-models into `06_HERO_*` groups.

**Independent Test**: Run on `hero_layout.xml` (contains `SingingFace` with `<subModel>` children); verify `06_HERO_SingingFace` group contains the sub-model names.

- [x] T022 [P] [US4] Write failing tests for `detect_heroes()` in `tests/unit/test_grouper_classifier.py` — verify props with "face", "megatree", "tree" (case-insensitive) in name are detected; verify sub-models collected from `Prop.sub_models`; verify props with no keyword match produce no hero group
- [x] T023 [US4] Implement `detect_heroes(props) -> list[PowerGroup]` in `src/grouper/classifier.py` — keyword search (case-insensitive: "face", "megatree", "mega_tree", "tree") on `Prop.name`; create one `06_HERO_{PropName}` group per match containing `prop.sub_models` (or the prop itself if no sub-models)
- [x] T024 [US4] Integrate `detect_heroes()` into tier 6 generation in `src/grouper/grouper.py` — call `detect_heroes()` when tier 6 is active; extend integration test in `tests/integration/test_grouper_integration.py` to cover `hero_layout.xml`

**Checkpoint**: US4 complete — hero groups auto-detected and included in output; non-hero layouts produce no spurious hero groups.

---

## Phase 7: User Story 5 — CLI Dry-Run and Preview (Priority: P5)

**Goal**: `--dry-run` prints a group summary table to stdout without modifying any files.

**Independent Test**: Run `group-layout simple_layout.xml --dry-run`; assert source file is byte-for-byte unchanged; assert stdout contains group name, tier, and member count for each group.

- [x] T025 [P] [US5] Write failing tests for dry-run mode in `tests/unit/test_grouper_groups.py` — mock file write; verify it is NOT called when dry_run=True; verify stdout output contains tier column, group name column, member count column
- [x] T026 [US5] Add `--dry-run` flag to `group_layout_cmd` in `src/cli.py`; when set, skip `write_layout()` and instead print formatted summary table (using `click.echo`) matching the format in `contracts/cli-contract.md`; add `--output` option for writing to alternate path

**Checkpoint**: US5 complete — dry-run prints correct preview table; source file unchanged; `--output` writes to specified path.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, error handling, exit codes, and validation.

- [x] T027 [P] Add edge-case tests in `tests/unit/test_grouper_classifier.py` — 1-prop layout produces only `01_BASE_All`; all-same-X props → beat groups still created; missing `WorldPosX` defaults to 0.0; no `<model>` elements → clear error message
- [x] T028 [P] Implement CLI error handling in `src/cli.py` — exit code 1 for missing/unreadable file, exit code 2 for XML parse error, exit code 3 for no `<model>` elements found (per contracts/cli-contract.md)
- [x] T029 [P] Add backup file write to `src/grouper/writer.py` — before in-place overwrite, copy source to `<source>.bak` (skip silently if `.bak` already exists)
- [ ] T030 Validate generated XML against a real xLights install — load output from `simple_layout.xml` run in xLights and confirm all `01_BASE_`…`06_HERO_` groups appear in the Groups panel (manual verification step — document result in `specs/017-xlights-layout-grouping/validation-notes.md`)
- [x] T031 [P] Run full integration test suite and confirm all tests pass: `pytest tests/unit/test_grouper_*.py tests/integration/test_grouper_integration.py -v`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **User Stories (Phases 3–7)**: All depend on Phase 2 completion
  - US1 (Phase 3) must complete before US2 (Phase 4) — profile filtering requires all tiers to exist
  - US3, US4, US5 can proceed after Phase 2 in parallel (different files/methods)
- **Polish (Phase 8)**: Depends on all desired user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — foundational work
- **US2 (P2)**: Depends on US1 (adds filtering on top of group generation)
- **US3 (P3)**: Depends on T013 (US1 introduces `generate_groups()`) — extends it with tier 4 beat logic
- **US4 (P4)**: Depends on T013 (US1 introduces `generate_groups()`) — extends it with tier 6 via `detect_heroes()`
- **US5 (P5)**: Independent — CLI flag only; adds `--dry-run` and `--output` to existing command

### Within Each User Story

- Failing tests MUST be written and confirmed failing before implementation (Constitution IV)
- Classifier changes before grouper changes (grouper depends on Prop fields set by classifier)
- `generate_groups()` changes before CLI wiring
- Story complete before next priority

### Parallel Opportunities

- T002 and T003 can run in parallel with T001 (different files)
- T006 and T008 can run in parallel with T004 (different test files)
- T007 and T009 can run in parallel after T005 completes
- Within US1: T010/T011 parallel with T012 (different test/impl targets)
- US3, US4, and US5 can run in parallel after T013 completes (all extend `generate_groups()` or the CLI in different methods)

---

## Parallel Example: User Story 1

```bash
# These tests can be written in parallel (different test files):
Task: T010 — classify_props() tests in tests/unit/test_grouper_classifier.py
Task: T012 — tier 1/2 group generation tests in tests/unit/test_grouper_groups.py

# These implementations can run in parallel after T010 passes:
Task: T011 — classify_props() in src/grouper/classifier.py
Task: T013 — generate_groups() tiers 1+2 in src/grouper/grouper.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: `xlight-analyze group-layout <your-layout.xml> --dry-run` should show Canvas, Spatial, Architecture, Fidelity groups
5. Load output in xLights to confirm groups appear

### Incremental Delivery

1. Phase 1 + 2 → parsing and write pipeline working
2. Phase 3 (US1) → baseline groups + CLI command → MVP demo
3. Phase 4 (US2) → profile filtering → ready for song-type selection
4. Phase 5 (US3) → beat groups → beat-sync ready
5. Phase 6 (US4) → hero detection → face/tree groups ready
6. Phase 7 (US5) → dry-run preview → safe workflow
7. Phase 8 → polish, edge cases, xLights validation

---

## Notes

- [P] tasks = different files, no dependencies between them
- [Story] label maps task to specific user story for traceability
- Constitution IV (Test-First): Write failing test → implement → make it pass — never skip
- US1 acceptance minimum: `01_BASE_All` group containing all props, populated `02_GEO_` bins
- Commit after each task or logical group of tasks
- T030 is a manual validation task — must be done with an actual xLights installation
