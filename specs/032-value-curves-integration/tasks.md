# Tasks: Value Curves Integration

**Input**: Design documents from `/specs/032-value-curves-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — constitution requires test-first development.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Add the `curves_mode` config field and CLI flag that all user stories depend on.

- [X] T001 Add `curves_mode: str = "all"` field to `GenerationConfig` dataclass in src/generator/models.py
- [X] T002 Add `--curves` flag (click.Choice: all, brightness, speed, color, none) to the `generate` command in src/cli.py and pass it through to `GenerationConfig.curves_mode`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement the category classification helper and minimum duration check that all curve generation depends on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Implement `classify_param_category(parameter_name: str) -> str` helper in src/generator/value_curves.py that returns "brightness", "speed", "color", or "other" based on keyword matching (transparency/brightness/intensity/opacity → brightness; speed/velocity/rate/cycles/rotation → speed; color/hue/saturation/palette → color; else → other)
- [X] T004 Add minimum duration guard at the top of `generate_value_curves()` in src/generator/value_curves.py: if `placement.end_ms - placement.start_ms < 1000`, return empty dict immediately
- [X] T005 [P] Write tests for `classify_param_category` and minimum duration guard in tests/unit/test_generator/test_value_curves.py: test all keyword categories return correct label, test "other" fallback, test placements <1s return empty curves, test placements >=1s proceed normally

**Checkpoint**: Category classification and duration guard tested and ready.

---

## Phase 3: User Story 1 — Effects Breathe with Music Energy (Priority: P1) MVP

**Goal**: Activate value curve generation in `build_plan()` for brightness parameters. Effects dim and brighten with the music energy.

**Independent Test**: Generate a sequence for a song with dynamic range. Open in xLights and verify brightness varies over time within effect placements.

### Tests for User Story 1

- [X] T006 [P] [US1] Write test in tests/unit/test_generator/test_value_curves.py: test that `generate_value_curves` produces brightness curves (On_Transparency) when given an effect with brightness analysis_mappings and valid hierarchy energy data
- [X] T007 [P] [US1] Write test in tests/unit/test_generator/test_value_curves.py: test that `generate_value_curves` returns empty dict when `curves_mode="none"`, and returns only brightness params when `curves_mode="brightness"`
- [X] T008 [P] [US1] Write integration test in tests/integration/test_generate_with_curves.py: generate a SequencePlan using `build_plan()` with curves enabled, verify at least one EffectPlacement has non-empty `value_curves` dict, verify the curves contain valid (x, y) points in [0.0-1.0] x [0.0-100.0] range

### Implementation for User Story 1

- [X] T009 [US1] Add `curves_mode` parameter to `generate_value_curves()` function signature in src/generator/value_curves.py; filter output dict to only include parameters whose category matches the mode ("all" includes everything, specific mode includes only that category + "other")
- [X] T010 [US1] Activate value curve generation in `build_plan()` in src/generator/plan.py: replace the Phase 1 disable comment (lines 151-152) with a loop that calls `generate_value_curves(placement, effect_def, hierarchy, config.curves_mode)` for each placement when `config.curves_mode != "none"`, matching the existing pattern in `regenerate_sections()` (lines 296-298)
- [X] T011 [US1] Update `regenerate_sections()` in src/generator/plan.py to also pass `curves_mode` from config to `generate_value_curves()`, using "all" as the default if config is not available
- [X] T012 [US1] Verify the existing xSQ writer encoding works end-to-end: generate a plan with curves, call xsq_writer, inspect the output XML string for `Active=TRUE|Id=` inline value curve encoding on at least one parameter

**Checkpoint**: User Story 1 fully functional — brightness curves generated and encoded in xSQ output.

---

## Phase 4: User Story 2 — Speed Ramps on Builds and Drops (Priority: P2)

**Goal**: Speed parameters also get value curves. Build sections show increasing speed values.

**Independent Test**: Generate a sequence for a song with a build section. Verify speed parameters contain value curves that trend upward during the build.

### Tests for User Story 2

- [X] T013 [P] [US2] Write test in tests/unit/test_generator/test_value_curves.py: test that `generate_value_curves` produces speed curves (e.g., Bars_Speed, Meteors_Speed) when `curves_mode` is "all" or "speed", and omits them when mode is "brightness"

### Implementation for User Story 2

- [X] T014 [US2] Review and verify speed-related analysis_mappings in src/effects/builtin_effects.json: confirm at least 5 effects (Bars, Meteors, Spirals, Wave, Marquee) have speed-category parameters with `supports_value_curve: true` and valid `analysis_mappings` entries. Add or fix mappings where missing.
- [X] T015 [US2] No code changes needed beyond T009's category filtering — speed curves flow through the same `generate_value_curves` pipeline. Run the integration test from T008 with a speed-mapped effect to confirm speed curves appear in the output.

**Checkpoint**: User Stories 1 AND 2 both work — brightness and speed curves generated.

---

## Phase 5: User Story 3 — Color Breathes with Energy, Accents on Chords (Priority: P2)

**Goal**: Color-mix parameters get energy-driven curves on all songs. Songs with good chord data additionally get chord-triggered accent shifts.

**Independent Test**: Generate sequences for two songs — one with good chord data (>20 events/min, quality >0.4) and one with poor chord data. Verify the first has chord accents overlaid on energy color curves; the second has energy-only color curves.

### Tests for User Story 3

- [X] T016 [P] [US3] Write test in tests/unit/test_generator/test_value_curves.py: test `apply_chord_accents()` overlays accent shifts at chord change positions onto a base energy curve; test it returns the base curve unchanged when chord density is below threshold or quality is below threshold
- [X] T017 [P] [US3] Write test in tests/unit/test_generator/test_value_curves.py: test that chord accent function handles missing chord data gracefully (returns base curve), and test that accent shifts stay within parameter bounds

### Implementation for User Story 3

- [X] T018 [US3] Implement `_get_chord_density_and_quality(hierarchy, start_ms, end_ms) -> tuple[float, float]` in src/generator/value_curves.py: find the chordino track in hierarchy, count chord events in the time range, compute events/min density and extract quality_score
- [X] T019 [US3] Implement `apply_chord_accents(base_curve, hierarchy, start_ms, end_ms, output_min, output_max) -> list[tuple[float, float]]` in src/generator/value_curves.py: if chord density >20/min and quality >0.4, iterate chord events in range dissolving a +10-20% accent at each chord boundary that decays over ~500ms; merge into base curve control points; downsample result to ≤100 points
- [X] T020 [US3] Wire chord accents into the main `generate_value_curves()` flow in src/generator/value_curves.py: after generating energy-based color curves, call `apply_chord_accents()` for color-category parameters when `curves_mode` is "all" or "color"
- [X] T021 [US3] Review and verify color-related analysis_mappings in src/effects/builtin_effects.json: confirm at least 3 effects have color-category parameters (hue, saturation, palette) with valid `analysis_mappings`. Add mappings where missing.

**Checkpoint**: All 3 curve categories work — brightness, speed, and color (with conditional chord accents).

---

## Phase 6: User Story 4 — Disable or Adjust Value Curves per Generation (Priority: P3)

**Goal**: Users can control curves via CLI `--curves` flag and config file. CLI overrides config.

**Independent Test**: Generate with `--curves none` and verify no curves in output. Generate with `--curves brightness` and verify only brightness curves appear.

### Tests for User Story 4

- [X] T022 [P] [US4] Write test in tests/integration/test_generate_with_curves.py: test that GenerationConfig with `curves_mode="none"` produces a SequencePlan with all empty `value_curves` dicts; test `curves_mode="brightness"` only produces brightness-category curves

### Implementation for User Story 4

- [X] T023 [US4] Add curves_mode to the generation wizard interactive prompts in src/cli.py or src/wizard.py (if the wizard flow exists): present a choice "Value curves: all / brightness / speed / color / none" with default "all"
- [X] T024 [US4] Add `curves_mode` to TOML generation profile loading in src/cli.py: read `[generation].curves_mode` from config file if present, use as default for the `--curves` CLI flag (CLI overrides config)

**Checkpoint**: Full user control — CLI, config, and wizard all respect curves_mode.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validation, performance check, and documentation.

- [X] T025 Run all existing generator tests to verify no regressions: `pytest tests/unit/test_generator/ -v`
- [X] T026 Run full integration test suite: `pytest tests/integration/ -v` — verify no regressions from plan.py changes
- [X] T027 Performance check: time `build_plan()` with and without curves on a real song hierarchy, verify <20% overhead (SC-005)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (needs curves_mode field)
- **User Story 1 (Phase 3)**: Depends on Phase 2 (needs classify + duration guard)
- **User Story 2 (Phase 4)**: Depends on Phase 3 (same pipeline, just verifying speed mappings)
- **User Story 3 (Phase 5)**: Depends on Phase 3 (needs the activation in build_plan; chord accents are additive)
- **User Story 4 (Phase 6)**: Depends on Phase 1 (needs curves_mode field; can run in parallel with US1-US3)
- **Polish (Phase 7)**: Depends on all stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational — core MVP, activates the pipeline
- **User Story 2 (P2)**: Depends on User Story 1 — uses same pipeline, primarily a mapping verification
- **User Story 3 (P2)**: Depends on User Story 1 — adds chord accent overlay to color curves
- **User Story 4 (P3)**: Depends on Setup only — CLI/config wiring, can overlap with US1-US3

### Parallel Opportunities

- T005, T006, T007, T008 (foundational + US1 tests) can all run in parallel
- T013, T016, T017 (US2 + US3 tests) can run in parallel
- US2 and US3 can run in parallel after US1 completes (different parameter categories, different files for chord logic)
- US4 (CLI/config) can run in parallel with US2/US3 after Phase 1

---

## Parallel Example: After Phase 2

```text
# US1 implementation (sequential — same files):
T009 → T010 → T011 → T012

# After US1, these can run in parallel:
Developer A (US2): T013 → T014 → T015
Developer B (US3): T016 → T017 → T018 → T019 → T020 → T021
Developer C (US4): T022 → T023 → T024
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Add curves_mode to config + CLI (T001-T002)
2. Complete Phase 2: Category classification + duration guard (T003-T005)
3. Complete Phase 3: Activate brightness curves in build_plan (T006-T012)
4. **STOP and VALIDATE**: Generate a sequence, open in xLights, verify brightness breathes with music
5. This alone delivers the core value — effects are no longer static

### Incremental Delivery

1. Setup + Foundational → Config ready, helpers tested
2. Add User Story 1 → Brightness curves live (MVP!)
3. Add User Story 2 → Speed ramps on builds (verify mappings)
4. Add User Story 3 → Color modulation + chord accents
5. Add User Story 4 → Full user control via CLI/config/wizard
6. Each story adds value without breaking previous stories

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- This feature is ~70% activation of existing code, ~20% chord accent logic (new), ~10% CLI/config wiring
- The existing `test_value_curves.py` (307 lines) covers core algorithm; new tests focus on activation, filtering, and chord accents
- Commit after each task or logical group
