# Tasks: Effect Themes

**Input**: Design documents from `specs/019-effect-themes/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contract.md

**Tests**: Included per constitution (Test-First Development).

**Organization**: Tasks grouped by user story.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create module skeleton, schema, fixtures.

- [x] T001 Create `src/themes/` package with stub files: `__init__.py`, `models.py`, `library.py`, `validator.py`
- [x] T002 [P] Create test fixtures: `tests/fixtures/themes/minimal_themes.json` (3 themes across 3 moods, referencing effects from the effects minimal fixture), `tests/fixtures/themes/valid_custom_theme.json`, `tests/fixtures/themes/invalid_custom_theme.json`
- [x] T003 [P] Create empty test files: `tests/unit/test_themes_models.py`, `tests/unit/test_themes_library.py`, `tests/unit/test_themes_validator.py`, `tests/integration/test_themes_integration.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data model classes and validation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Write failing tests for `Theme`, `EffectLayer` dataclasses in `tests/unit/test_themes_models.py` — verify construction, field types, defaults, `from_dict()` deserialization
- [x] T005 Implement `Theme`, `EffectLayer` dataclasses and constants (`VALID_MOODS`, `VALID_OCCASIONS`, `VALID_GENRES`, `VALID_BLEND_MODES` — all 24) in `src/themes/models.py` — fields per data-model.md, including `from_dict()` class methods
- [x] T006 [P] Write failing tests for `validate_theme()` in `tests/unit/test_themes_validator.py` — verify: valid theme passes; missing fields fail; invalid mood/occasion/genre fail; invalid blend mode fails; bottom layer not Normal fails; modifier effect on bottom layer fails; palette with fewer than 2 colors warns; effect not in effect library warns
- [x] T007 Implement `validate_theme(data: dict, effect_library: EffectLibrary) -> list[str]` in `src/themes/validator.py` — validate all fields, check effect references against loaded effect library, check layer_role constraints

**Checkpoint**: Dataclasses and validation working.

---

## Phase 3: User Story 1 — Built-in Theme Catalog Exists (Priority: P1) 🎯 MVP

**Goal**: Ship `builtin_themes.json` with 21+ themes, loadable and validatable.

**Independent Test**: Load the JSON, validate every entry, confirm 21+ themes across 4 moods + holiday themes with valid effect references.

- [x] T008 [US1] Author `src/themes/builtin_themes.json` — all 21+ themes with complete definitions: 12 from design doc (Stellar Wind, Aurora, Bio-Lume, Inferno, Molten Metal, Tracer Fire, The Void, Glitch City, The Kraken, Cyber Grid, Scanning Beam, The Zipper), 6 Christmas (Winter Wonderland, Candy Cane Chase, Warm Glow, North Star, Festive Flash, Silent Night), 3 Halloween (Haunted Pulse, Jack-o-Lantern, Graveyard Fog). Each with layers, blend modes, parameter overrides, palette, and mood/occasion/genre tags.
- [x] T009 [US1] Write failing tests in `tests/unit/test_themes_library.py` — verify `builtin_themes.json` loads, contains 21+ themes, 4+ mood collections with 3+ each, 4+ Christmas themes, 2+ Halloween themes, all effect references valid
- [x] T010 [US1] Implement `load_theme_library()` in `src/themes/library.py` — parse JSON, deserialize to `Theme` via `from_dict()`, validate against effect library, return `ThemeLibrary` dataclass
- [x] T011 [US1] Write integration test in `tests/integration/test_themes_integration.py` — full load of `builtin_themes.json` with real effect library, verify SC-001 through SC-003, include `time.monotonic()` assertion for SC-003 (loads in under 1 second)

**Checkpoint**: US1 complete — catalog exists, loads, validates.

---

## Phase 4: User Story 2 — Programmatic Loading and Querying (Priority: P2)

**Goal**: Query themes by mood, occasion, genre, or any combination.

**Independent Test**: Load library, query by mood="aggressive", by occasion="christmas", combined query mood+genre.

- [x] T012 [P] [US2] Write failing tests for `ThemeLibrary.get()`, `by_mood()`, `by_occasion()`, `by_genre()`, `query()` in `tests/unit/test_themes_library.py` — verify case-insensitive get, correct filtering, by_genre includes "any"-tagged themes, combined query uses AND logic
- [x] T013 [US2] Implement `ThemeLibrary` with `get()`, `by_mood()`, `by_occasion()`, `by_genre()`, `query()` in `src/themes/library.py`

**Checkpoint**: US2 complete — full query API working.

---

## Phase 5: User Story 3 — Custom Theme Overrides (Priority: P3)

**Goal**: Custom themes in `~/.xlight/custom_themes/` override built-in by name.

**Independent Test**: Place custom theme in temp dir, load, verify override.

- [x] T014 [P] [US3] Write failing tests for custom override loading in `tests/unit/test_themes_library.py` — custom overrides built-in by name; invalid skipped with warning; missing dir silently ignored; new custom themes added
- [x] T015 [US3] Extend `load_theme_library()` in `src/themes/library.py` to scan custom dir, validate, merge
- [x] T016 [US3] Extend integration test in `tests/integration/test_themes_integration.py` — custom override round-trip

**Checkpoint**: US3 complete — custom overrides work.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T017 [P] Add edge-case tests in `tests/unit/test_themes_validator.py` — theme with only 1 palette color, theme with modifier on bottom layer, theme referencing nonexistent effect
- [x] T018 Run full test suite: `pytest tests/unit/test_themes_*.py tests/integration/test_themes_integration.py -v`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all stories
- **US1 (Phase 3)**: Depends on Phase 2 — the JSON must exist before queries
- **US2 (Phase 4)**: Depends on T010 (library loading)
- **US3 (Phase 5)**: Depends on T010 (extends loading)
- **Polish (Phase 6)**: Depends on all stories

### Key External Dependency

- `src/effects/library.py` must be available — theme validation loads the effect library to check effect references. Tests use the effects fixtures.

### Parallel Opportunities

- T002, T003 parallel with T001
- T006 parallel with T004
- T012, T014 are independent test tasks

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + 2 → models and validation
2. Phase 3 → author 21 themes, load and validate
3. **STOP and VALIDATE**: Confirm themes load with valid effect references

### Incremental Delivery

1. Phase 1 + 2 → foundation
2. Phase 3 (US1) → catalog exists → MVP
3. Phase 4 (US2) → query API
4. Phase 5 (US3) → custom overrides
5. Phase 6 → polish

---

## Notes

- T008 (authoring 21 themes) is the heaviest task — translate design doc prose + create holiday themes
- Same patterns as effect library (018): models.py, library.py, validator.py, builtin JSON, custom overrides
- Effect library must be loadable for validation — integration tests need real `builtin_effects.json`
