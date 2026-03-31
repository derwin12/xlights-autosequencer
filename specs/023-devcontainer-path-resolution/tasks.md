# Tasks: Devcontainer Path Resolution

**Input**: Design documents from `/specs/023-devcontainer-path-resolution/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: Included per constitution principle IV (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new dependencies or project structure changes needed. This feature uses only stdlib modules (pathlib, os) and modifies existing files.

_(No setup tasks required — project structure already exists.)_

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the PathContext module that ALL user stories depend on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T001 Write failing unit tests for PathContext (env detection, to_relative, to_absolute, is_in_show_dir, suggest_path) in tests/unit/test_paths.py
- [x] T002 Implement PathContext class in src/paths.py with environment detection via XLIGHTS_HOST_SHOW_DIR env var, container_show_dir=/home/node/xlights, and all methods from data-model.md
- [x] T003 Implement suggest_path() in src/paths.py that maps cross-environment prefixes (e.g., /Users/* inside container suggests /home/node/xlights/*, and vice versa)
- [x] T004 Verify all tests/unit/test_paths.py tests pass

**Checkpoint**: PathContext module fully tested — user story implementation can now begin.

---

## Phase 3: User Story 1 - Analyze an MP3 from the Host xLights Directory (Priority: P1) MVP

**Goal**: Analysis runs correctly inside the container on mounted files, output JSON contains portable relative paths alongside absolute paths.

**Independent Test**: Run `xlight-analyze analyze /home/node/xlights/song.mp3` inside the container and verify output JSON contains both absolute and relative_source_file paths.

### Tests for User Story 1

- [x] T005 [P] [US1] Write failing test for HierarchyResult relative_source_file field serialization/deserialization in tests/unit/test_paths.py
- [x] T006 [P] [US1] Write failing test for orchestrator storing relative path in result in tests/unit/test_paths.py

### Implementation for User Story 1

- [x] T007 [P] [US1] Add optional relative_source_file field to HierarchyResult in src/analyzer/result.py — nullable, excluded from JSON when None for backward compat
- [x] T008 [US1] Update run_orchestrator() in src/analyzer/orchestrator.py to use PathContext.to_relative() when setting source_file on the result, storing both absolute and relative paths
- [x] T009 [US1] Update HierarchyResult JSON serialization in src/analyzer/result.py to include relative_source_file when present, and deserialization to read it with None fallback
- [x] T010 [US1] Verify T005 and T006 tests pass

**Checkpoint**: Analysis inside container produces JSON with portable relative paths.

---

## Phase 4: User Story 2 - Load Previously Cached Analysis Across Environments (Priority: P1)

**Goal**: Analysis cached in one environment (host or container) is found and reused in the other without re-analysis. Library index deduplicates by content hash.

**Independent Test**: Generate analysis locally, open container, request same song — system reuses cache via content hash.

### Tests for User Story 2

- [x] T011 [P] [US2] Write failing test for LibraryEntry with relative path fields and hash-based dedup in tests/unit/test_paths.py
- [x] T012 [P] [US2] Write failing test for cache fallback: absolute path missing, finds via relative path in tests/unit/test_paths.py

### Implementation for User Story 2

- [x] T013 [US2] Add relative_source_file and relative_analysis_path fields to LibraryEntry in src/library.py — nullable, backward compatible on JSON load
- [x] T014 [US2] Update Library.upsert() in src/library.py to deduplicate by source_hash (update existing entry paths instead of creating duplicate) and store relative paths via PathContext
- [x] T015 [US2] Update cache lookup in src/cache.py to fall back to relative path resolution via PathContext when absolute path does not exist
- [x] T016 [US2] Add path suggestion to cache miss error message in src/cache.py using PathContext.suggest_path()
- [x] T017 [US2] Verify T011 and T012 tests pass

**Checkpoint**: Cache reuse works across environments; library has no duplicates for same song.

---

## Phase 5: User Story 3 - Generate Sequences Referencing Correct Audio Paths (Priority: P2)

**Goal**: XSQ files reference audio using show-directory-relative paths that work on any host. Warn when audio is outside the show directory.

**Independent Test**: Generate a sequence in the container, verify the mediaFile element uses a relative reference that xLights on the host can resolve.

### Implementation for User Story 3

- [x] T018 [US3] Verify xsq_writer.py already uses basename-only mediaFile references in src/generator/xsq_writer.py — add a comment documenting this is intentional for cross-environment portability
- [x] T019 [US3] Add warning in the sequence generation flow when the audio file is outside the mounted show directory, advising the user to copy it into the show directory — in src/generator/xsq_writer.py or the calling CLI command in src/cli.py

**Checkpoint**: XSQ generation produces host-compatible audio references with clear warnings for edge cases.

---

## Phase 6: User Story 4 - Stem Cache Accessible Across Environments (Priority: P2)

**Goal**: Stem separation results persist across container/host switches. Manifest includes relative paths for portability.

**Independent Test**: Run stem separation in container, verify stems are found when accessed from host or fresh container session.

### Tests for User Story 4

- [x] T020 [US4] Write failing test for stem manifest with relative_source_path field in tests/unit/test_paths.py

### Implementation for User Story 4

- [x] T021 [US4] Add optional relative_source_path field to stem manifest write in src/analyzer/stems.py — store via PathContext.to_relative(), nullable for backward compat
- [x] T022 [US4] Update stem manifest read in src/analyzer/stems.py to use relative_source_path as fallback when absolute source_path does not exist
- [x] T023 [US4] Verify T020 test passes

**Checkpoint**: Stem cache survives environment switches.

---

## Phase 7: User Story 5 - Local-Only Workflow Remains Unaffected (Priority: P3)

**Goal**: Users who never use a dev container experience zero changes.

**Independent Test**: Run the full pipeline locally with no container env vars set — all paths behave identically to pre-023 behavior.

### Tests for User Story 5

- [x] T024 [US5] Write integration test in tests/integration/test_path_resolution.py verifying that with no container env vars set, PathContext is_in_container=False and all methods pass through paths unchanged
- [x] T025 [US5] Write integration test in tests/integration/test_path_resolution.py verifying that library, cache, orchestrator, and stem modules produce identical output to pre-023 behavior when PathContext detects local environment

**Checkpoint**: Local workflow regression-free.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Cross-environment integration tests and error handling polish.

- [x] T026 [P] Write cross-environment integration test in tests/integration/test_path_resolution.py simulating container env (mock XLIGHTS_HOST_SHOW_DIR) and verifying end-to-end: analyze → cache → library → re-resolve
- [x] T027 [P] Add helpful CLI error message in src/cli.py for file-not-found errors that calls PathContext.suggest_path() and prints the equivalent path if a mapping exists
- [x] T028 Update quickstart.md validation — run through specs/023-devcontainer-path-resolution/quickstart.md steps and verify they work

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Skipped — no setup needed
- **Foundational (Phase 2)**: No dependencies — start immediately. BLOCKS all user stories.
- **User Stories (Phase 3-7)**: All depend on Phase 2 (PathContext) completion
  - US1 and US2 are both P1 but US2 depends on US1 (needs relative paths in results before cache can use them)
  - US3 and US4 can start after Phase 2 (independent of US1/US2)
  - US5 can start after Phase 2 (independent)
- **Polish (Phase 8)**: Depends on US1 and US2 being complete

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2 only — no dependencies on other stories
- **US2 (P1)**: Depends on Phase 2 + US1 (needs relative paths written by orchestrator before cache can resolve them)
- **US3 (P2)**: Depends on Phase 2 only — can run in parallel with US1
- **US4 (P2)**: Depends on Phase 2 only — can run in parallel with US1
- **US5 (P3)**: Depends on Phase 2 only — can run in parallel with US1

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Data model changes before service logic
- Serialization before consumers
- Verify tests pass after implementation

### Parallel Opportunities

- T005 and T006 (US1 tests) can run in parallel
- T011 and T012 (US2 tests) can run in parallel
- US3, US4, US5 can all run in parallel with each other (and with US1)
- T026 and T027 (Polish) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch US1 tests together:
Task: "T005 — Write failing test for HierarchyResult relative_source_file in tests/unit/test_paths.py"
Task: "T006 — Write failing test for orchestrator storing relative path in tests/unit/test_paths.py"

# After tests written, launch model changes in parallel:
Task: "T007 — Add relative_source_file field to HierarchyResult in src/analyzer/result.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (PathContext module)
2. Complete Phase 3: User Story 1 (relative paths in analysis output)
3. **STOP and VALIDATE**: Analyze a song in container, verify JSON has relative paths
4. This alone makes analysis output portable

### Incremental Delivery

1. Phase 2 → PathContext ready
2. US1 → Analysis output has relative paths (MVP)
3. US2 → Cache reuse across environments (high value)
4. US3 → XSQ warnings for edge cases (low effort)
5. US4 → Stem cache portable (medium effort)
6. US5 → Regression validation (confidence)
7. Polish → Error messages and integration tests

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Constitution IV (Test-First) is followed: tests written before implementation in each story
- No new dependencies introduced — all stdlib
- Backward compatibility preserved: new fields are nullable, old JSON loads cleanly
- Commit after each task or logical group
