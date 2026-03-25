# Tasks: Comprehensive Stem×Parameter Sweep Matrix

**Input**: Design documents from `/specs/015-sweep-matrix/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/cli-sweep-matrix.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story. TDD order enforced (constitution §IV): tests before implementation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US6)
- Exact file paths included in all descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new modules, extract stem affinity table, set up data model stubs.

- [x] T001 Create module stubs with empty `__all__` for: `src/analyzer/sweep_matrix.py`, `src/analyzer/segment_selector.py`, `src/analyzer/value_curve_scorer.py`, `src/analyzer/stem_affinity.py`
- [x] T002 [P] Create `src/analyzer/algorithms/vamp_aubio.py` module stub (aubio_onset, aubio_tempo, aubio_notes algorithm classes)
- [x] T003 [P] Create `src/analyzer/algorithms/vamp_bbc.py` module stub (bbc_energy, bbc_spectral_flux, bbc_peaks, bbc_rhythm algorithm classes)
- [x] T004 [P] Create `src/analyzer/algorithms/vamp_segmentation.py` module stub (segmentino algorithm class)
- [x] T005 [P] Create `src/analyzer/algorithms/vamp_extra.py` module stub (qm_key, qm_transcription, silvet_notes, percussion_onsets, amplitude_follower, tempogram algorithm classes)
- [x] T006 Write stem affinity rationale document at `docs/stem-affinity-rationale.md` with a table of all ~35 algorithms, their preferred stems, audio engineering rationale, output type (timing/value_curve), and tunable parameters

**Checkpoint**: All module stubs exist. Stem affinity documented. Algorithm wrapper files ready for implementation.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and utilities that all user stories depend on.

**⚠️ CRITICAL**: US1–US6 all depend on these.

- [x] T007 Write failing tests for `StemAffinity.get_stems(algorithm, available_stems)` in `tests/unit/test_stem_affinity.py`: verify affinity returns all matching stems (no cap), includes full_mix, respects keep/review filter
- [x] T008 Implement `StemAffinity` class in `src/analyzer/stem_affinity.py` with full affinity table for all ~35 algorithms (extracted from current `_STEM_AFFINITY` + new algorithms); run T007 tests — MUST pass
- [x] T009 [P] Write failing tests for `select_representative_segment(audio_path, duration_s)` in `tests/unit/test_sweep_matrix.py`: verify it selects a high-energy segment, avoids first/last 10%, returns start_ms/end_ms
- [x] T010 [P] Implement `select_representative_segment()` in `src/analyzer/segment_selector.py` using librosa RMS energy rolling window; run T009 tests — MUST pass
- [x] T011 [P] Write failing tests for `score_value_curve(curve)` in `tests/unit/test_value_curve_scorer.py`: verify dynamic range scoring, temporal autocorrelation scoring, combined score in 0-1 range
- [x] T012 [P] Implement `score_value_curve()` in `src/analyzer/value_curve_scorer.py`; run T011 tests — MUST pass
- [x] T013 Write failing tests for `SweepMatrixConfig.from_toml(path)` and `SweepMatrixConfig.build_matrix()` in `tests/unit/test_sweep_matrix.py`: verify TOML parsing, permutation cross-product, deduplication, safety cap warning
- [x] T014 Implement `SweepMatrixConfig` and `SweepMatrix` dataclasses with `build_matrix()` in `src/analyzer/sweep_matrix.py`; run T013 tests — MUST pass

**Checkpoint**: Affinity table, segment selector, value curve scorer, and matrix config all testable. Ready for user stories.

---

## Phase 3: User Story 1 — Run a Full Sweep Matrix (Priority: P1) 🎯 MVP

**Goal**: `xlight-analyze sweep-matrix song.mp3` runs every algorithm against all affinity stems on a 30s sample segment, writes unified report + per-algorithm files.

**Independent Test**: Run `sweep-matrix` on a fixture audio with `--dry-run` — verify permutation count is N_stems × Y_params. Then run without `--dry-run` — verify result files are written with correct structure.

- [x] T015 [US1] Write failing tests for new algorithm wrappers in `tests/unit/test_vamp_new_algorithms.py`: verify each produces timing marks or value curves from fixture audio; verify plugin_key is correct; verify preferred_stem is set; run tests now — MUST fail (classes not yet implemented)
- [x] T016 [P] [US1] Implement all 3 aubio algorithm classes in `src/analyzer/algorithms/vamp_aubio.py` (AubioOnsetAlgorithm, AubioTempoAlgorithm, AubioNotesAlgorithm) inheriting from Algorithm base; set name, plugin_key, preferred_stem, depends_on, element_type; implement `_run()`
- [x] T017 [P] [US1] Implement all 4 BBC algorithm classes in `src/analyzer/algorithms/vamp_bbc.py` (BBCEnergyAlgorithm, BBCSpectralFluxAlgorithm, BBCPeaksAlgorithm, BBCRhythmAlgorithm); BBC energy/flux/peaks return value curves (vector output), rhythm returns timing marks
- [x] T018 [P] [US1] Implement SegmentinoAlgorithm in `src/analyzer/algorithms/vamp_segmentation.py`
- [x] T019 [P] [US1] Implement 6 algorithm classes in `src/analyzer/algorithms/vamp_extra.py` (QMKeyAlgorithm, QMTranscriptionAlgorithm, SilvetNotesAlgorithm, PercussionOnsetsAlgorithm, AmplitudeFollowerAlgorithm, TempogramAlgorithm)
- [x] T020 [US1] Run T015 tests against T016–T019 implementations — fix until all pass
- [x] T021 [US1] Register all new algorithms in `src/analyzer/runner.py` `default_algorithms()` function so they appear in the full algorithm list
- [x] T022 [US1] Implement `MatrixSweepRunner` in `src/analyzer/sweep_matrix.py`: accepts `SweepMatrix`, loads audio segment via `segment_selector`, runs each permutation (dispatching to existing `SweepRunner` or subprocess for vamp), collects `PermutationResult` objects, writes unified report JSON + per-algorithm JSONs
- [x] T023 [US1] Write failing integration test in `tests/integration/test_sweep_matrix_e2e.py`: run `MatrixSweepRunner` on fixture audio with 2 algorithms; verify result count = stems × params; verify unified report has metadata only; verify per-algorithm files have full marks
- [x] T024 [US1] Run T023 integration test — fix until passing
- [x] T025 [US1] Add `sweep-matrix` CLI command to `src/cli.py` per contract: accept audio file, `--algorithms`, `--stems`, `--max-permutations`, `--dry-run`, `--config`, `--output-dir`, `--sample-start`, `--sample-duration`, `--yes`; wire to `MatrixSweepRunner`
- [x] T026 [US1] Implement `--dry-run` mode in `sweep-matrix` CLI: compute and display full matrix table (algorithm × stem × params × total count) without executing

**Checkpoint**: `xlight-analyze sweep-matrix song.mp3` runs full matrix sweep. `--dry-run` shows the matrix. Results stored in unified + per-algorithm files.

---

## Phase 4: User Story 2 — View and Rank Sweep Results via CLI (Priority: P1)

**Goal**: `xlight-analyze sweep-results report.json` shows a ranked table with filtering.

**Independent Test**: Run `sweep-results` on a sweep report file and verify ranked table output with correct columns; verify `--algorithm`, `--stem`, `--best`, `--top` filters.

- [x] T027 [US2] Add `sweep-results` CLI command to `src/cli.py` per contract: accept sweep report path, `--algorithm`, `--stem`, `--best`, `--top`, `--type`, `--export`; load report JSON; display ranked table with columns: rank, score, type, algorithm, stem, marks, avg interval, parameters
- [x] T028 [US2] Implement `--best` flag: group results by algorithm, show only the top-scoring result per algorithm
- [x] T029 [US2] Implement `--export` flag: export displayed results as `.xtiming` (timing tracks) or `.xvc` (value curves) to `winners/` directory

**Checkpoint**: `sweep-results` displays ranked, filterable table. `--best --export` auto-exports winners.

---

## Phase 5: User Story 3 — Browse and Compare Results in the Review UI (Priority: P2)

**Goal**: Review UI gets a "Sweep Results" view with a sortable/filterable table and two-result comparison on the timeline.

**Independent Test**: Open review UI, navigate to Sweep Results, verify table loads with sorting and filtering; select two results and compare on timeline.

- [x] T030 [P] [US3] Create `src/review/static/sweep.html` with toolbar (back to timeline, filter box, sort dropdowns), results table, and comparison area with two canvases + shared audio player
- [x] T031 [P] [US3] Create `src/review/static/sweep.js` with: fetch sweep report from `/sweep-report` endpoint; render sortable table; filter by text input; checkbox selection for compare mode; timeline comparison view with two color-coded timing tracks and shared playhead
- [x] T032 [US3] Add server endpoints to `src/review/server.py` in review mode: `/sweep-view` (serves sweep.html), `/sweep-report` (returns sweep_report.json), `/sweep-detail?algorithm=X` (returns per-algorithm full data for comparison)
- [x] T033 [US3] Add "Sweep Results" button to `src/review/static/index.html` toolbar linking to `/sweep-view`

**Checkpoint**: Review UI Sweep Results view loads, sorts, filters, and compares two results on the timeline.

---

## Phase 6: User Story 4 — Configure Sweep via TOML (Priority: P2)

**Goal**: Users can pass `--config sweep.toml` to customize algorithms, stems, parameter ranges, and limits.

**Independent Test**: Create a TOML config with 2 algorithms and custom param ranges; run `sweep-matrix --config`; verify only specified algorithms/params run.

- [x] T034 [US4] Write failing test in `tests/unit/test_sweep_matrix.py` for TOML override/merge behavior: verify per-algorithm param overrides replace auto-derived ranges; verify TOML stems merge with CLI `--stems` flag (CLI wins); verify missing TOML fields fall back to defaults
- [x] T035 [US4] Implement TOML parsing in `SweepMatrixConfig.from_toml()` in `src/analyzer/sweep_matrix.py` using `tomllib`; run T034 test — MUST pass
- [x] T036 [US4] Wire `--config` flag in `sweep-matrix` CLI to load TOML and merge with CLI flags (CLI flags override TOML)

**Checkpoint**: `sweep-matrix --config sweep.toml` applies custom algorithm/stem/param configuration.

---

## Phase 7: User Story 5 — Auto-Select Best Results and Export (Priority: P2)

**Goal**: After sweep completes, auto-identify best result per algorithm and export winners as `.xtiming`/`.xvc` files.

**Independent Test**: After a sweep, verify best-per-algorithm selection is displayed and export produces correctly named files.

- [x] T037 [US5] Implement `auto_select_best(report)` in `src/analyzer/sweep_matrix.py`: group results by algorithm, pick highest quality_score (tie-break: fewer marks), return dict of winners
- [x] T038 [US5] After sweep completes in `MatrixSweepRunner`, call `auto_select_best()`, display winners table, prompt user to confirm export
- [x] T039 [US5] Re-run winning parameter sets on the full song (not sample segment) via `MatrixSweepRunner` to produce final timing tracks and value curves with complete song coverage (FR-007c)
- [x] T040 [US5] Implement winner export: load full-song results from T039, export timing tracks as `.xtiming` via existing `XTimingWriter`, export value curves as `.xvc` via existing `xvc_export`, write to `winners/` subdirectory with names like `qm_beats_drums.xtiming`

**Checkpoint**: Sweep auto-selects, re-runs winners on full song, and exports best results per algorithm.

---

## Phase 8: User Story 6 — Parallel Execution with Progress Display (Priority: P3)

**Goal**: Independent permutations run concurrently with a live progress display.

**Independent Test**: Run a sweep with ≥20 permutations; verify wall clock < sequential time; verify progress display shows completion count and ETA.

- [x] T041 [US6] Implement parallel execution in `MatrixSweepRunner`: use `ThreadPoolExecutor` for local algorithms, separate subprocesses for vamp/madmom; max workers = `min(cpu_count, 4)`
- [x] T042 [US6] Implement progress display using `rich.live.Live` + `rich.table.Table` in `MatrixSweepRunner`: show current algorithm, stem, params, N/M completed, estimated time remaining; fall back to `click.echo` line-per-event when stdout is not a TTY
- [x] T043 [US6] Handle Ctrl-C gracefully in `MatrixSweepRunner`: on `KeyboardInterrupt`, cancel pending futures, wait for in-progress to complete, save all completed results to disk before exiting with code 130
- [x] T044 [US6] Handle failed permutations: catch exceptions per permutation, log error, mark result as `status="failed"`, continue with remaining permutations

**Checkpoint**: Sweep runs in parallel with live progress. Interrupts preserve results. Failures don't abort the sweep.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, integration tests, backward compatibility.

- [x] T045 [P] Write end-to-end integration test in `tests/integration/test_sweep_matrix_e2e.py`: run full `sweep-matrix` CLI on fixture audio with `--dry-run` and without; verify file outputs; verify `sweep-results --best` works on the output
- [x] T046 [P] Update `src/analyzer/stem_inspector.py`: remove `_STEM_AFFINITY` dict and `_preferred_stems_for()` function; import from `src/analyzer/stem_affinity.py` instead; update `generate_sweep_configs()` to use new affinity module
- [x] T047 [P] Add `sweep-matrix` and `sweep-results` to `xlight-analyze --help` documentation; verify they appear in the command list
- [x] T048 Validate quickstart.md commands work end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — blocks all user story phases
- **US1 (Phase 3)**: Depends on Phase 2 — the core engine; all other stories depend on sweep results existing
- **US2 (Phase 4)**: Depends on US1 (needs sweep report files to display)
- **US3 (Phase 5)**: Depends on US1 (needs sweep report for UI); can parallelize with US2
- **US4 (Phase 6)**: Depends on Phase 2 only (TOML config feeds into matrix builder); can parallelize with US1
- **US5 (Phase 7)**: Depends on US1 (needs completed sweep to auto-select from)
- **US6 (Phase 8)**: Depends on US1 (enhances the runner); can be developed alongside US1
- **Polish (Phase 9)**: Depends on all desired stories being complete

### Within Each User Story

- Tests MUST be written and FAIL before implementation (constitution §IV)
- Data models before services
- Services before CLI/UI
- Core implementation before integration

### Parallel Opportunities

- T002–T005: all algorithm stub files can be created in parallel
- T007+T009+T011: foundational tests can be written in parallel (different files)
- T015–T018: all algorithm implementations can run in parallel (different files)
- T030+T031: UI HTML and JS can be built in parallel
- US2 and US3 can proceed in parallel once US1 is complete
- US4 can proceed in parallel with US1 (only needs Phase 2)

---

## Implementation Strategy

### MVP First (User Story 1 + 2 Only)

1. Complete Phase 1: Setup (stubs + affinity doc)
2. Complete Phase 2: Foundational (affinity, segment selector, scorer, matrix config)
3. Complete Phase 3: US1 — sweep-matrix command works end-to-end
4. Complete Phase 4: US2 — sweep-results displays ranked table
5. **STOP and VALIDATE**: Run sweep on Highway to Hell, verify results

### Incremental Delivery

6. Add US4: TOML config
7. Add US5: Auto-select + export winners
8. Add US3: Review UI sweep view
9. Add US6: Parallel execution + progress
10. Polish: migrate old affinity code, docs, integration tests
