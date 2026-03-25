# Tasks: Hierarchy Orchestrator

**Input**: Design documents from `/specs/016-hierarchy-orchestrator/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new project setup needed — extending existing codebase.

- [X] T001 Create `src/analyzer/capabilities.py` with stub `detect_capabilities()` returning `dict[str, bool]`
- [X] T002 [P] Create `src/analyzer/selector.py` with stub `select_best_track()` returning `TimingTrack | None`
- [X] T003 [P] Create `src/analyzer/derived.py` with stubs for `derive_energy_impacts()`, `derive_gaps()`

---

## Phase 2: Foundational (Data Model Updates)

**Purpose**: Update the data model so all downstream code has the right types. MUST complete before user stories.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Add `label: str | None = None` and `duration_ms: int | None = None` fields to `TimingMark` in `src/analyzer/result.py`. Update `to_dict()` and `from_dict()` to serialize both fields (omit from dict when None).
- [X] T005 Add `ValueCurve` dataclass to `src/analyzer/result.py` with fields: `name`, `stem_source`, `fps`, `values: list[int]`. Implement `to_dict()`, `from_dict()`, and `duration_ms` property.
- [X] T006 Add `HierarchyResult` dataclass to `src/analyzer/result.py` with all fields per data-model.md (energy_impacts, energy_drops, gaps, sections, bars, beats, events, energy_curves, spectral_flux, chords, key_changes, interactions, stems_available, capabilities, algorithms_run, warnings). Set `schema_version = "2.0.0"`. Implement `to_dict()` and `from_dict()`.
- [X] T007 Update `BBCEnergyAlgorithm._run()` in `src/analyzer/algorithms/vamp_bbc.py` to return a `ValueCurve` object (attached to the track) instead of empty timing marks. Store the 0-100 normalized values in `track.value_curve`. Update `BBCSpectralFluxAlgorithm` and `BBCPeaksAlgorithm` similarly.
- [X] T008 [P] Update `SegmentinoAlgorithm._run()` in `src/analyzer/algorithms/vamp_segmentation.py` to populate `TimingMark.label` (A, B, N1, etc.) and `TimingMark.duration_ms` from the Vamp output.
- [X] T009 [P] Update `ChordinoAlgorithm._run()` in `src/analyzer/algorithms/vamp_harmony.py` to populate `TimingMark.label` with the chord name (Am, G, D, etc.) from the Vamp output.

**Checkpoint**: Data model supports value curves, labeled marks, and hierarchy result. All existing tests still pass.

---

## Phase 3: User Story 1 — Single-File Analysis (Priority: P1) 🎯 MVP

**Goal**: `xlight-analyze song.mp3` produces a complete `HierarchyResult` JSON with all 7 levels populated.

**Independent Test**: Run on any MP3 and verify the output JSON has non-empty fields for each available hierarchy level.

### Implementation for User Story 1

- [X] T010 [US1] Implement `detect_capabilities()` in `src/analyzer/capabilities.py` — try-import vamp, madmom, demucs, whisperx. For vamp, also check plugin files exist. Return `dict[str, bool]`.
- [X] T011 [US1] Implement `select_best_bar_track()` and `select_best_beat_track()` in `src/analyzer/selector.py` — compute coefficient of variation of inter-mark intervals for each candidate track, return the one with lowest CV. Tiebreak by cross-correlation with onset density.
- [X] T012 [US1] Implement `derive_energy_impacts()` and `derive_energy_drops()` in `src/analyzer/derived.py` — given a ValueCurve, compute 1-second windowed averages, find ratio changes >1.8x (impacts) and <0.55x (drops). Return list of TimingMark with label="impact"/"drop".
- [X] T013 [P] [US1] Implement `derive_gaps()` in `src/analyzer/derived.py` — given a ValueCurve, find runs where value < 5 for >300ms. Return list of TimingMark with label="gap" and duration_ms.
- [X] T014 [US1] Create `src/analyzer/orchestrator.py` with `run_orchestrator(audio_path: str) -> HierarchyResult`. Implement the 6-stage pipeline:
  1. Detect capabilities
  2. Load audio + stem separation (if demucs available)
  3. Run algorithms grouped by hierarchy level (use existing AnalysisRunner for algorithm execution, but only request the ~15 algorithms needed per the level mapping in research.md)
  4. Select best per level (call selector functions)
  5. Derive L0 features (call derived functions)
  6. Run interaction analysis (if stems available, reuse existing `analyze_interactions()`)
  Assemble and return HierarchyResult.
- [X] T015 [US1] Add cache integration to `run_orchestrator()` — compute MD5 hash of source file, check for existing `_hierarchy.json` with matching hash and schema_version "2.0.0". If found, load and return. If not, run analysis, write result, return.
- [X] T016 [US1] Replace the existing `analyze` CLI command in `src/cli.py` with a new entry point that calls `run_orchestrator()`. Accept a single file path argument. Add `--fresh` flag to skip cache. Add `--dry-run` flag to show what would run without executing. Print progress output per the CLI contract.
- [X] T017 [US1] Write `_hierarchy.json` and `.xtiming` files to a song-named output folder. Update `src/analyzer/xtiming.py` to handle TimingMarks with labels (include label as mark name/layer in the xtiming XML).

**Checkpoint**: `xlight-analyze song.mp3` produces a valid `_hierarchy.json` with all available levels populated and a `.xtiming` file.

---

## Phase 4: User Story 2 — Graceful Degradation (Priority: P1)

**Goal**: System produces useful output even when Vamp, madmom, or demucs are missing.

**Independent Test**: Run with Vamp plugins removed — verify librosa-only levels (L2, L3, L4) are populated and missing levels have clear warnings.

### Implementation for User Story 2

- [X] T018 [US2] Update `run_orchestrator()` in `src/analyzer/orchestrator.py` to handle missing capabilities per level. For each level, check required capabilities before running algorithms. If capability missing, set field to None/empty and add a warning to warnings list.
- [X] T019 [US2] Implement librosa-only fallback paths in the orchestrator: when Vamp is unavailable, L2 uses `librosa_bars` only, L3 uses `librosa_beats` only, L4 uses `librosa_onsets` only. L0, L1, L5, L6 are skipped with warnings.
- [X] T020 [US2] Verify the capabilities map and warnings are correctly serialized in the output JSON metadata section. Ensure human-readable warning messages (e.g., "L1 Structure: skipped — Vamp plugin 'segmentino' not available").

**Checkpoint**: System produces valid output with only librosa installed. At least 4 of 7 levels populated (SC-003).

---

## Phase 5: User Story 3 — Structured Output (Priority: P1)

**Goal**: Output JSON is organized by hierarchy level with typed fields, not a flat list.

**Independent Test**: Load the JSON programmatically and access `result["sections"]`, `result["beats"]`, `result["energy_curves"]["drums"]` — verify each is the correct type.

### Implementation for User Story 3

- [X] T021 [US3] Verify `HierarchyResult.to_dict()` produces the expected JSON structure per data-model.md — energy_impacts/drops/gaps as lists of marks, sections with labels+durations, bars/beats as track objects, events keyed by stem name, energy_curves keyed by stem name with fps+values arrays, chords/key_changes with labels.
- [X] T022 [US3] Write a validation script or test that loads a produced `_hierarchy.json` and asserts: (a) top-level keys match the schema, (b) value curves contain integer arrays, (c) timing marks contain time_ms integers, (d) sections have label and duration_ms, (e) events dict is keyed by stem name.
- [X] T023 [US3] Verify derived features (energy_impacts, energy_drops, gaps) are pre-computed in the JSON — downstream consumers should not need to re-derive from raw energy curves.

**Checkpoint**: Output JSON is structured, typed, and directly consumable by the downstream grouping/theme pipeline.

---

## Phase 6: User Story 4 — Batch Directory Processing (Priority: P2)

**Goal**: `xlight-analyze /path/to/mp3s/` processes all MP3s in a directory.

**Independent Test**: Point at a directory of 3 MP3s and verify 3 output folders are created.

### Implementation for User Story 4

- [X] T024 [US4] Update the CLI entry point in `src/cli.py` to detect whether the path argument is a file or directory. If directory, glob for `*.mp3` files.
- [X] T025 [US4] Implement batch loop: iterate over MP3s, call `run_orchestrator()` for each, print per-song progress (`[1/22] song name... done`). Catch exceptions per-song so one failure doesn't stop the batch. Print summary at end (N succeeded, M failed).
- [X] T026 [US4] Respect cache in batch mode — skip songs that already have a valid cached `_hierarchy.json`.

**Checkpoint**: `xlight-analyze /path/to/mp3s/` processes a directory of 20+ songs, skips cached results, and reports a summary.

---

## Phase 7: User Story 5 — Timing Export (Priority: P2)

**Goal**: `.xtiming` file is generated alongside the JSON with timing marks for beats, bars, sections, and events.

**Independent Test**: Import generated `.xtiming` into xLights and verify marks appear.

### Implementation for User Story 5

- [X] T027 [US5] Update `src/analyzer/xtiming.py` to accept `HierarchyResult` and write a multi-layer `.xtiming` file with separate timing layers for: beats, bars, sections (with labels), drum events, bass events, vocal events.
- [X] T028 [US5] Ensure the `.xtiming` is written automatically as part of `run_orchestrator()` output — no separate export step needed.

**Checkpoint**: Every analysis run produces a `.xtiming` file that imports cleanly into xLights.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup and validation across all stories.

- [X] T029 Update `src/review/server.py` to read `HierarchyResult` (schema_version "2.0.0") instead of the old `AnalysisResult` format. Display hierarchy levels in the review UI.
- [X] T030 Remove or deprecate old CLI flags (--algorithms, --no-vamp, --no-madmom, --stems, --phonemes, --phoneme-model, --structure, --genius, --scoring-config, --scoring-profile, --top) from `src/cli.py`. Keep `--fresh` and `--dry-run` only.
- [X] T031 Update `docs/orchestrator-design.md` to reflect final implementation decisions.
- [ ] T032 Run the full 22-song batch from `/Users/rob/mp3` through the new orchestrator and verify all songs produce valid `_hierarchy.json` output. Command: `xlight-analyze analyze /Users/rob/mp3/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — create stub files
- **Phase 2 (Foundational)**: Depends on Phase 1 — data model must be updated before orchestrator
- **Phase 3 (US1)**: Depends on Phase 2 — needs ValueCurve, labeled TimingMark, HierarchyResult
- **Phase 4 (US2)**: Depends on Phase 3 — extends orchestrator with degradation paths
- **Phase 5 (US3)**: Depends on Phase 3 — validates output structure from US1
- **Phase 6 (US4)**: Depends on Phase 3 — adds batch wrapper around single-file orchestrator
- **Phase 7 (US5)**: Depends on Phase 3 — adds .xtiming export to orchestrator output
- **Phase 8 (Polish)**: Depends on all stories

### User Story Dependencies

- **US1 (Single-File)**: Blocks all other stories — core pipeline
- **US2 (Degradation)**: Depends on US1
- **US3 (Structured Output)**: Depends on US1 (validates its output)
- **US4 (Batch)**: Depends on US1 only (wraps it)
- **US5 (Timing Export)**: Depends on US1 only (extends its output)

### Parallel Opportunities

- T002 and T003 can run in parallel (Phase 1 stubs)
- T007, T008, T009 — T008 and T009 can run in parallel (different algorithm files)
- T012 and T013 can run in parallel (different derived features)
- US4, US5 can run in parallel after US1 is complete (independent extensions)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup stubs
2. Complete Phase 2: Data model updates (ValueCurve, TimingMark labels, HierarchyResult)
3. Complete Phase 3: Orchestrator pipeline + CLI
4. **STOP and VALIDATE**: Run on Highway to Hell and verify `_hierarchy.json` has all 7 levels
5. This is a fully functional tool at this point

### Incremental Delivery

1. Phase 1 + 2 → Data model ready
2. Phase 3 (US1) → Single file works → **MVP**
3. Phase 4 (US2) → Degradation tested
4. Phase 5 (US3) → Output validated for downstream
5. Phase 6 (US4) → Batch processing
6. Phase 7 (US5) → .xtiming export
7. Phase 8 → Polish, UI update, validation on 22 songs

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- The orchestrator (T014) is the largest single task — consider breaking into sub-steps during implementation
