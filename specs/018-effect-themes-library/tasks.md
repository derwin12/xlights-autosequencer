# Tasks: xLights Effect Library

**Input**: Design documents from `specs/018-effect-themes-library/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contract.md

**Tests**: Included per constitution (Test-First Development — Red-Green-Refactor is mandated).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2…)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the module skeleton, JSON schema, and test fixtures.

- [x] T001 Create `src/effects/` package with stub files: `__init__.py`, `models.py`, `library.py`, `validator.py`
- [x] T002 [P] Create `src/effects/effect_schema.json` — JSON schema defining the structure of an effect definition (EffectDefinition, EffectParameter, AnalysisMapping, PropSuitability) per data-model.md
- [x] T003 [P] Create test fixture files: `tests/fixtures/effects/minimal_library.json` (3 effects for unit tests), `tests/fixtures/effects/valid_custom_effect.json`, `tests/fixtures/effects/invalid_custom_effect.json`
- [x] T004 [P] Create empty test module files: `tests/unit/test_effects_models.py`, `tests/unit/test_effects_library.py`, `tests/unit/test_effects_validator.py`, `tests/integration/test_effects_integration.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data model classes and schema validation — everything else depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T005 Write failing tests for `EffectParameter`, `AnalysisMapping`, and `EffectDefinition` dataclasses in `tests/unit/test_effects_models.py` — verify construction, field types, and defaults
- [x] T006 Implement `EffectParameter`, `AnalysisMapping`, `PropSuitability` constants, `ALL_XLIGHTS_EFFECTS` constant (list of all 56 known effect names), and `EffectDefinition` dataclasses in `src/effects/models.py` — fields per data-model.md, including `from_dict()` class methods for JSON deserialization
- [x] T007 [P] Write failing tests for `validate_effect_definition()` in `tests/unit/test_effects_validator.py` — verify valid definitions pass, missing required fields fail, invalid parameter types fail, min > max fails, invalid mapping_type fails, invalid analysis_level fails
- [x] T008 Implement `validate_effect_definition(data: dict) -> list[str]` in `src/effects/validator.py` — validate against schema, return list of error messages

**Checkpoint**: Dataclasses and validation working — can construct and validate effect definitions from dicts.

---

## Phase 3: User Story 1 — Built-in Effect Catalog Exists (Priority: P1) 🎯 MVP

**Goal**: Ship a `builtin_effects.json` with 35+ effect definitions, loadable and validatable.

**Independent Test**: Load `builtin_effects.json`, validate every entry, confirm 35+ effects present with complete definitions (parameters, suitability, mappings).

- [x] T009 [US1] Create `scripts/scrape_xlights_effects.py` — one-time dev tool that fetches `*Effect.cpp` and `*Effect.h` from xLights GitHub repo for the 35 target effects, parses `GetValueCurveInt()`, `SettingsMap.GetBool()`, `SettingsMap.Get()` calls and `#define *_MIN/*_MAX` constants, outputs raw JSON with extracted parameter names, types, defaults, and ranges
- [x] T010 [US1] Run the scraper and hand-review output — add `description`, `intent`, `category`, `prop_suitability`, and `analysis_mappings` for each effect; also cross-reference parameter values against real sequences in `/Users/rob/sequences/` (Believer, Danger Zone, etc.) for sensible defaults; save as `src/effects/builtin_effects.json`
- [x] T011 [US1] Write failing tests in `tests/unit/test_effects_library.py` — verify `builtin_effects.json` loads without errors, contains at least 35 effects, every effect has ≥3 parameters, every effect has suitability ratings for all 5 prop types, at least 20 effects have ≥1 analysis mapping
- [x] T012 [US1] Implement `load_effect_library(custom_dir=None)` in `src/effects/library.py` — parse `builtin_effects.json`, deserialize each entry to `EffectDefinition` via `from_dict()`, validate all entries, return `EffectLibrary` dataclass (custom_dir support added in T021)
- [x] T013 [US1] Write integration test in `tests/integration/test_effects_integration.py` — full load of `builtin_effects.json`, validate every definition, confirm SC-001 (35+ effects), SC-002 (≥3 params each), SC-003 (20+ with mappings), SC-004 (all 5 suitability ratings), SC-005 (loads in <1s)

**Checkpoint**: US1 complete — built-in catalog exists, loads, validates, and meets all success criteria.

---

## Phase 4: User Story 2 — Programmatic Loading and Querying (Priority: P2)

**Goal**: Downstream code can load the library, look up by name, query by prop type, and get coverage stats.

**Independent Test**: Load library, look up "Fire" by name, query effects suitable for "matrix", request coverage stats — all return structured data.

- [x] T014 [P] [US2] Write failing tests for `EffectLibrary.get()` in `tests/unit/test_effects_library.py` — verify lookup by name (case-insensitive), not-found returns None
- [x] T015 [US2] Implement `EffectLibrary.get(name: str) -> EffectDefinition | None` in `src/effects/library.py` — case-insensitive name lookup
- [x] T016 [P] [US2] Write failing tests for `EffectLibrary.for_prop_type()` in `tests/unit/test_effects_library.py` — verify returns only effects rated Ideal or Good for the given prop type
- [x] T017 [US2] Implement `EffectLibrary.for_prop_type(prop_type: str) -> list[EffectDefinition]` in `src/effects/library.py`
- [x] T018 [P] [US2] Write failing tests for `EffectLibrary.coverage()` in `tests/unit/test_effects_library.py` — verify returns cataloged names, uncatalogued names, and total count (56)
- [x] T019 [US2] Implement `EffectLibrary.coverage() -> CoverageResult` in `src/effects/library.py` — compare cataloged effect names against the known set of 56 xLights effects (constant list in `models.py`)

**Checkpoint**: US2 complete — full query API working, tested against both fixture and real library.

---

## Phase 5: User Story 3 — Custom Overrides via JSON (Priority: P3)

**Goal**: Custom effect JSON files in `~/.xlight/custom_effects/` override built-in definitions at load time.

**Independent Test**: Place a custom Fire.json in a temp custom dir, load library, confirm custom version is returned.

- [x] T020 [P] [US3] Write failing tests for custom override loading in `tests/unit/test_effects_library.py` — verify: custom overrides built-in by name; invalid custom files are skipped with warning; missing custom dir is silently ignored; custom-only effects (not in built-in) are added to library
- [x] T021 [US3] Implement `load_effect_library(custom_dir: Path | None = None) -> EffectLibrary` in `src/effects/library.py` — load built-in first, then scan custom dir, validate each custom file, merge (custom overrides built-in by name), log warnings for invalid files
- [x] T022 [US3] Extend integration test in `tests/integration/test_effects_integration.py` — test full round-trip: place custom effect in temp dir, load library with custom_dir, verify override works, verify invalid custom is skipped

**Checkpoint**: US3 complete — custom overrides work, invalid files handled gracefully.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Known xLights effect list, edge cases, and documentation.

- [x] T023 [P] Add edge-case tests in `tests/unit/test_effects_validator.py` — parameter with min > max, analysis mapping referencing nonexistent parameter, unknown mapping_type, unknown analysis_level
- [x] T024 [P] Verify `builtin_effects.json` parameter names against real `.xsq` files in `/Users/rob/sequences/` — spot-check that the `storage_name` values (e.g., `E_SLIDER_Fire_Height`) match what real sequences actually use
- [x] T025 Run full test suite: `pytest tests/unit/test_effects_*.py tests/integration/test_effects_integration.py -v`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — the scraper and JSON must exist before query API
- **US2 (Phase 4)**: Depends on US1 (needs the loaded library to query against)
- **US3 (Phase 5)**: Depends on US1 (custom overrides layer on top of built-in loading)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — builds the catalog
- **US2 (P2)**: Depends on T012 (library loading must exist before query methods)
- **US3 (P3)**: Depends on T012 (extends loading with custom directory scanning)

### Within Each User Story

- Failing tests MUST be written and confirmed failing before implementation (Constitution IV)
- Models before library logic
- Library loading before query methods
- Story complete before next priority

### Parallel Opportunities

- T002, T003, T004 can all run in parallel with T001 (different files)
- T007 can run in parallel with T005 (different test files)
- Within US2: T014, T016, T018 are independent test tasks (different test methods) that can run in parallel
- T023 and T024 can run in parallel in Polish phase

---

## Parallel Example: User Story 2

```bash
# These test tasks can be written in parallel (different test methods):
Task: T014 — get() tests in tests/unit/test_effects_library.py
Task: T016 — for_prop_type() tests in tests/unit/test_effects_library.py
Task: T018 — coverage() tests in tests/unit/test_effects_library.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (dataclasses + validation)
3. Run scraper (T009), hand-review output (T010)
4. Complete Phase 3: Load and validate the catalog
5. **STOP and VALIDATE**: Confirm 35+ effects with complete definitions

### Incremental Delivery

1. Phase 1 + 2 → models and validation working
2. Phase 3 (US1) → catalog exists and loads → MVP
3. Phase 4 (US2) → query API for downstream consumers
4. Phase 5 (US3) → custom overrides
5. Phase 6 → polish, edge cases, .xsq cross-validation

---

## Notes

- [P] tasks = different files, no dependencies between them
- [Story] label maps task to specific user story
- Constitution IV (Test-First): Write failing test → implement → make it pass
- T009 (scraper) is a dev tool in `scripts/`, not part of the shipped product
- T010 (hand-review) is a manual/semi-automated task — the biggest effort in this feature
- T025 (cross-validation against real .xsq files) is a verification task, not a test — documents findings
- The `builtin_effects.json` file is the primary deliverable — everything else serves it
