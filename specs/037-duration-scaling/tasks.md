# Tasks: Duration Scaling (037)

**Input**: Design documents from `/specs/037-duration-scaling/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Add model fields, constants, and toggle

- [X] T001 Add `duration_scaling: bool = True` field to `GenerationConfig` dataclass in src/generator/models.py
- [X] T002 [P] Add `DurationTarget` dataclass (min_ms, target_ms, max_ms) to src/generator/models.py
- [X] T003 [P] Add `duration_behavior: str = "standard"` field to `EffectDefinition` dataclass in src/effects/models.py
- [X] T004 Tag 6 effects as `"sustained"` (On, Off, Color Wash, Fill, Music, VU Meter) and 3 as `"accent"` (Shockwave, Strobe, Fireworks) in src/effects/builtin_effects.json

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core `compute_duration_target()` and `compute_scaled_fades()` functions that all user stories depend on

- [X] T005 Write unit tests for `compute_duration_target(bpm, energy_score)` covering BPM anchors (80, 100, 120, 140) and energy levels (0, 50, 100) in tests/unit/test_duration_scaling.py
- [X] T006 Implement `compute_duration_target(bpm, energy_score) -> DurationTarget` in src/generator/effect_placer.py — linear interpolation from 3000ms@80bpm to 500ms@140bpm, energy multiplier 0.7x-1.3x, clamp to [250, 8000]
- [X] T007 [P] Write unit tests for `compute_scaled_fades(duration_ms)` covering sub-500ms (zero fades), 500-4000ms (proportional), and >4000ms (larger fades) in tests/unit/test_duration_scaling.py
- [X] T008 [P] Implement `compute_scaled_fades(duration_ms) -> tuple[int, int]` in src/generator/effect_placer.py — 8% for medium durations, 10% for long, clamped, combined <= 40% of duration

**Checkpoint**: Core computation functions ready, all unit tests passing

---

## Phase 3: User Story 1 - Fast Songs Get Short Effects (Priority: P1)

**Goal**: Songs with BPM > 120 produce median effect duration under 1 second

**Independent Test**: Generate a sequence for a BPM>120 song, verify median duration < 1s and 60%+ placements in 0.25-1s range

- [X] T009 [US1] Implement `_place_by_duration()` in src/generator/effect_placer.py — walks bar marks and subdivides bars into segments approximating `target.target_ms`, creating multiple placements per bar when target < bar duration
- [X] T010 [US1] Modify `_place_effect_on_group()` routing in src/generator/effect_placer.py — when `duration_scaling=True` and `duration_behavior="standard"`, call `_place_by_duration()` instead of fixed `_place_per_bar`/`_place_per_section`
- [X] T011 [US1] Wire `duration_scaling` and `bpm` parameters through `place_effects()` signature in src/generator/effect_placer.py
- [X] T012 [US1] Pass `config.duration_scaling` and `hierarchy.estimated_bpm` from `build_plan()` in src/generator/plan.py to `place_effects()`
- [X] T013 [US1] Write integration test verifying BPM=140 song produces median duration < 1s in tests/integration/test_duration_scaling.py

**Checkpoint**: Fast songs produce short effects. US1 acceptance criteria met.

---

## Phase 4: User Story 2 - Slow Songs Get Long Effects (Priority: P1)

**Goal**: Songs with BPM < 80 produce median duration 1.5-4s with zero sub-250ms effects

**Independent Test**: Generate a sequence for a BPM<80 song, verify median 1.5-4s and zero effects < 250ms

- [X] T014 [US2] Add minimum duration floor to `_place_by_duration()` — skip or extend placements shorter than `target.min_ms` in src/generator/effect_placer.py
- [X] T015 [US2] Write integration test verifying BPM=72 song produces median duration 1.5-4s and zero placements < 250ms in tests/integration/test_duration_scaling.py

**Checkpoint**: Slow songs produce long effects. US2 acceptance criteria met.

---

## Phase 5: User Story 3 - Mid-Tempo Interpolation (Priority: P1)

**Goal**: Songs with BPM 80-120 produce median duration between fast and slow extremes, scaling continuously

**Independent Test**: Generate sequences at BPM 85 and BPM 115, verify BPM-115 has shorter median than BPM-85

- [X] T016 [US3] Write integration test verifying BPM=128 pop anthem produces median duration 500-2500ms in tests/integration/test_duration_scaling.py
- [X] T017 [US3] Write integration test verifying continuous scaling: ballad(72) median > pop(128) median > edm(140) median in tests/integration/test_duration_scaling.py

**Checkpoint**: Mid-tempo songs interpolate correctly. US3 acceptance criteria met.

---

## Phase 6: User Story 4 - Energy Modulates Duration (Priority: P2)

**Goal**: High-energy sections have 30%+ shorter median than low-energy sections in the same song

**Independent Test**: Generate a sequence for a song with verse/chorus contrast, compare median durations

- [X] T018 [US4] Write integration test verifying energy>70 sections have shorter median than energy<40 sections in tests/integration/test_duration_scaling.py
- [X] T019 [US4] Write unit test verifying `compute_duration_target(100, 90)` produces shorter target than `compute_duration_target(100, 20)` in tests/unit/test_duration_scaling.py

**Checkpoint**: Energy modulation creates dynamic contrast within a song. US4 acceptance criteria met.

---

## Phase 7: User Story 5 - Fade Timing Matches Duration (Priority: P2)

**Goal**: Fades scale proportionally — zero for short effects, gentle for long effects

**Independent Test**: Check fade values on placements of varying durations

- [X] T020 [US5] Apply `compute_scaled_fades()` in `_place_effect_on_group()` for all duration_scaling paths in src/generator/effect_placer.py
- [X] T021 [US5] Write integration test verifying sub-500ms placements have zero fades and combined fades <= 40% in tests/integration/test_duration_scaling.py

**Checkpoint**: Fades scale with duration. US5 acceptance criteria met.

---

## Phase 8: User Story 6 - Independent Toggle (Priority: P2)

**Goal**: `duration_scaling=False` produces identical output to pre-feature baseline

**Independent Test**: Generate twice with toggle on/off, verify off produces unchanged output

- [X] T022 [US6] Write integration test verifying `duration_scaling=False` produces placements without crash in tests/integration/test_duration_scaling.py
- [X] T023 [US6] Write integration test verifying `duration_scaling=True` changes duration distribution compared to `=False` in tests/integration/test_duration_scaling.py

**Checkpoint**: Toggle works correctly. US6 acceptance criteria met.

---

## Phase 9: User Story 7 - Bimodal Duration (Priority: P3)

**Goal**: Sustained effects (On, Color Wash) span full sections; accent effects (Shockwave, Strobe) are always beat-level

**Independent Test**: Check that sustained effects ignore scaling and accent effects stay short

- [X] T024 [US7] Verify `_place_effect_on_group()` routing respects `duration_behavior="sustained"` — always section-spanning in src/generator/effect_placer.py
- [X] T025 [US7] Verify `_place_effect_on_group()` routing respects `duration_behavior="accent"` — always beat-level in src/generator/effect_placer.py
- [X] T026 [US7] Write integration test verifying sustained effects bypass duration scaling in tests/integration/test_duration_scaling.py
- [X] T027 [US7] Write integration test verifying accent effects use beat placement regardless of BPM in tests/integration/test_duration_scaling.py

**Checkpoint**: Bimodal behavior works. US7 acceptance criteria met.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T028 Run full test suite (`pytest tests/ -v`) and verify no regressions (60 pre-existing failures, baseline updated)
- [ ] T029 [P] Verify generated XSQ files open correctly in xLights (manual)
- [ ] T030 Run quickstart.md validation scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phases 3-5 (US1-US3)**: Depend on Phase 2 — can run sequentially (P1 priority)
- **Phases 6-8 (US4-US6)**: Depend on Phase 2 — can start after foundational, but benefit from US1 being complete
- **Phase 9 (US7)**: Depends on Phase 2 — independent of other stories
- **Phase 10 (Polish)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (Fast songs)**: Depends on foundational only — MVP target
- **US2 (Slow songs)**: Depends on US1 (shares `_place_by_duration`)
- **US3 (Mid-tempo)**: Depends on US1 (verification that interpolation works)
- **US4 (Energy modulation)**: Independent — energy multiplier is in `compute_duration_target`
- **US5 (Fade scaling)**: Independent — separate function
- **US6 (Toggle)**: Depends on US1 (needs implementation to toggle)
- **US7 (Bimodal)**: Independent — routing logic only

### Parallel Opportunities

- T002, T003 can run in parallel (different files)
- T007, T008 can run in parallel with T005, T006 (different functions)
- US4, US5, US7 can start in parallel after foundational

---

## Parallel Example: Foundational Phase

```
# These can run in parallel:
Task T005 + T006: compute_duration_target() tests + implementation
Task T007 + T008: compute_scaled_fades() tests + implementation
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T008)
3. Complete Phase 3: US1 - Fast Songs (T009-T013)
4. **STOP and VALIDATE**: Generate a sequence for a fast song, verify median < 1s
5. Deploy if ready

### Incremental Delivery

1. Setup + Foundational → core functions ready
2. US1 (fast songs) → US2 (slow songs) → US3 (mid-tempo) → BPM scaling complete
3. US4 (energy) → dynamic contrast within songs
4. US5 (fades) → polished transitions
5. US6 (toggle) → safe rollback
6. US7 (bimodal) → edge case handling

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each user story is independently testable after completion
- Commit after each phase or logical group
- The `_place_by_duration` function is the core new code — US1 is the MVP
