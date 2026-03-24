# Tasks: Interactive CLI Wizard & Pipeline Optimization

**Input**: Design documents from `/specs/014-cli-wizard-pipeline/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/cli-wizard.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story. TDD order enforced throughout (tests precede implementation per constitution §IV).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths included in all descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install new dependencies and create module stubs so all user stories can start from a clean structure.

- [x] T001 Add `questionary>=2.0` and `rich>=13.0` to project dependencies (pyproject.toml or requirements.txt, wherever existing deps are declared)
- [x] T002 [P] Create `src/wizard.py` module stub with module docstring and empty `__all__`
- [x] T003 [P] Create `src/analyzer/parallel.py` module stub (pipeline.py already exists from 012; using parallel.py for new DAG/ParallelRunner code)
- [x] T004 [P] Create `src/analyzer/progress.py` module stub with module docstring and empty `__all__`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures shared by all user stories. TDD order: tests first (they will fail to import), then implementation to make them pass.

**⚠️ CRITICAL**: US1–US5 all depend on WizardConfig and/or PipelineStep.

- [x] T005 [P] Write unit tests for `WizardConfig.to_analyze_kwargs()` in `tests/unit/test_wizard_config.py`: test every wizard field maps to a correct `analyze_cmd` kwarg, and defaults match `analyze_cmd` defaults (validates FR-014 flag parity); run tests now — they MUST fail (WizardConfig not yet defined)
- [x] T006 [P] Write unit tests for `PipelineStep.is_ready()` in `tests/unit/test_parallel.py` (named parallel.py to avoid conflict with existing pipeline.py from 012): test pending→waiting→running→done transitions, test unsatisfied `depends_on` returns False, test empty `depends_on` returns True; run tests now — they MUST fail (PipelineStep not yet defined)
- [x] T007 [P] Implement `WizardConfig` dataclass in `src/wizard.py` with fields: `audio_path`, `cache_strategy` (literal "use_existing" | "regenerate" | "skip_write"), `algorithm_groups` (set[str]), `use_stems`, `use_phonemes`, `whisper_model`, `use_structure`, `use_genius`; add `to_analyze_kwargs()` method mapping each field to existing `analyze_cmd` CLI kwargs; run T005 tests — they MUST now pass
- [x] T008 [P] Implement `PipelineStepStatus` enum, `PipelineStep`, and `DependencyGraph` in `src/analyzer/parallel.py` with fields: `name`, `phase`, `depends_on` (list[str]), `status` (PipelineStepStatus), `started_at`, `completed_at`, `mark_count`, `error`; add `is_ready(completed: set[str]) -> bool` method; run T006 tests — they MUST now pass

**Checkpoint**: T005–T008 all green. WizardConfig and PipelineStep are importable before moving to user story phases.

---

## Phase 3: User Story 1 — Guided Interactive Analysis Setup (Priority: P1) 🎯 MVP

**Goal**: `xlight-analyze wizard song.mp3` launches an interactive multi-step menu with arrow-key navigation, a confirmation screen, clean Ctrl-C exit, audio file validation, and non-interactive fallback.

**Independent Test**: Run `xlight-analyze wizard tests/fixtures/short.mp3` — all menu screens appear, arrow keys change selection, Enter starts analysis and produces a valid JSON result file. Run with a non-existent file path — wizard exits immediately with a clear error before any prompts.

- [x] T009 [US1] Implement `WizardRunner(flags: dict)` class in `src/wizard.py` with `run(audio_path: Path) -> WizardConfig | None` method; constructor takes all wizard CLI flags as a `flags` dict; add `_detect_tty() -> bool` helper via `sys.stdin.isatty()`; handle `KeyboardInterrupt` from questionary to return `None` (exit code 130); print non-interactive notice when TTY not detected (FR-011)
- [x] T010 [US1] Add audio file existence check at `wizard` subcommand entry point in `src/cli.py`: before constructing `WizardRunner`, verify `audio_path.exists()` and `audio_path.is_file()`; if not, print a clear error ("File not found: {path}") and exit with code 1; this prevents the wizard completing all steps only to fail deep in analysis (edge case: file not found)
- [x] T011 [US1] Implement `_step_scope(config: WizardConfig)` in `src/wizard.py` using `questionary.select` to offer "Full analysis", "Quick analysis (no stems)", and "Custom"; set `config.algorithm_groups`, `config.use_stems`, `config.use_phonemes`, `config.use_structure` based on selection; in non-interactive mode skip and apply defaults from `self._flags`
- [x] T012 [US1] Implement `_step_confirm(config: WizardConfig) -> bool` in `src/wizard.py` using `questionary.confirm` to display a one-line summary of all selections and ask "Start analysis?"; return False on Esc/Ctrl-C
- [x] T013 [US1] Implement non-interactive fallback in `WizardRunner.run()` in `src/wizard.py`: when `_detect_tty()` is False or `self._flags.get("non_interactive")` is True, skip all questionary steps, apply values from `self._flags` (falling back to defaults for unset flags), print "Non-interactive mode: using defaults. Use --help for flag options.", and return a `WizardConfig`
- [x] T014 [US1] Add `wizard` subcommand to `src/cli.py` as a Click command accepting `audio_file` argument and all flags from `contracts/cli-wizard.md` (including `--non-interactive`, `--use-cache`, `--skip-cache-write`); call T010 file-existence check first; construct `WizardRunner(flags=ctx.params)`, call `runner.run(audio_path)`, exit with code 130 if result is None, otherwise call `_run_analysis_from_config(config, audio_path)`
- [x] T015 [US1] Implement `_run_analysis_from_config(config: WizardConfig, audio_path: Path)` in `src/cli.py` that calls `config.to_analyze_kwargs()` and invokes the existing analyze pipeline (reusing the body of `analyze_cmd`); this ensures the wizard and the `analyze` command share exactly one code path

**Checkpoint**: `xlight-analyze wizard tests/fixtures/short.mp3` fully navigable and produces a valid JSON. `xlight-analyze wizard /nonexistent.mp3` exits with code 1 and a clear message. `xlight-analyze wizard tests/fixtures/short.mp3 --non-interactive` completes without interactive prompts.

---

## Phase 4: User Story 2 — Cache Awareness and Control (Priority: P1)

**Goal**: The wizard's cache step shows cache age and validity, offering use/regenerate/bypass. TDD order: test first.

**Independent Test**: Run wizard on a song with a valid cache — step says "Cache found (N minutes ago, valid)". Run on a song with no cache — says "No cache found". "Use existing cache" skips analysis and loads the cached result.

- [x] T016 [US2] Write unit tests for `CacheStatus.from_audio_path()` in `tests/unit/test_cache_status.py`: test no cache file (exists=False), valid cache (exists=True, is_valid=True), stale cache (source MD5 changed, is_valid=False); use fixture audio and fixture JSON; run now — MUST fail (CacheStatus not yet defined)
- [x] T017 [US2] Implement `CacheStatus` dataclass in `src/cache.py` with fields: `exists`, `is_valid`, `age_seconds`, `cache_path`, `track_count`, `has_phonemes`, `has_structure`; add `CacheStatus.from_audio_path(audio_path: Path, output_path: Path | None = None) -> CacheStatus` factory reusing existing `AnalysisCache` logic; run T016 tests — MUST now pass
- [x] T018 [US2] Implement `_step_cache(config: WizardConfig, audio_path: Path)` in `src/wizard.py` using `questionary.select`; call `CacheStatus.from_audio_path()` and display status line ("Cache found — 2 hours ago, valid" / "No cache found"); offer 3 choices: "Use existing cache" → `"use_existing"`, "Regenerate cache" → `"regenerate"`, "Skip cache (one-time run)" → `"skip_write"`; hide "Use existing cache" when no cache exists; in non-interactive mode respect `--use-cache`/`--no-cache`/`--skip-cache-write` flags
- [x] T019 [US2] Insert `_step_cache` as the first step in `WizardRunner.run()` in `src/wizard.py` (before scope step); if user selects `"use_existing"` and cache is valid, set `config.cache_strategy = "use_existing"` and return config immediately (short-circuit — no further steps needed)
- [x] T020 [US2] Update `_run_analysis_from_config()` in `src/cli.py` to honour `config.cache_strategy`: `"use_existing"` → load and return cached result directly; `"regenerate"` → pass `no_cache=True` to existing analyze path; `"skip_write"` → run fresh analysis but skip the final JSON write and library upsert

**Checkpoint**: Cache step displays correct status. "Use existing cache" skips analysis entirely. All three strategies produce the correct output.

---

## Phase 5: User Story 3 — Whisper Model Selection (Priority: P2)

**Goal**: When phonemes are enabled, wizard shows Whisper models with descriptions, local status, and offline guard. TDD order: tests first.

**Independent Test**: Run wizard with phonemes enabled — Whisper step appears, all 5 models listed with descriptions and cached badges. Select a model; it appears in result metadata. Select an uncached model with no network — clear error before analysis begins.

- [x] T021 [P] [US3] Write unit tests for `whisper_model_list()` in `tests/unit/test_wizard_config.py`: verify all 5 models returned, descriptions non-empty, `is_cached` is boolean (mock filesystem); run now — MUST fail (function not yet defined)
- [x] T022 [P] [US3] Implement `WhisperModelInfo` dataclass in `src/wizard.py` with fields: `name`, `description`, `approximate_size_mb`, `is_cached`; implement `whisper_model_list() -> list[WhisperModelInfo]` returning all 5 entries (tiny, base, small, medium, large-v2) with trade-off descriptions; detect `is_cached` by checking `~/.cache/huggingface/hub/` and `~/.cache/whisper/`; run T021 tests — MUST now pass
- [x] T023 [US3] Implement `_step_whisper_model(config: WizardConfig)` in `src/wizard.py` using `questionary.select`; build choices from `whisper_model_list()` with label `"{name} — {description}{cached_badge}"`; only present when `config.use_phonemes is True`; set `config.whisper_model`; in non-interactive mode apply `--phoneme-model` flag or default `"base"`
- [x] T024 [US3] Insert `_step_whisper_model` into `WizardRunner.run()` in `src/wizard.py` after scope step and before confirmation
- [x] T025 [US3] Add offline guard in `_run_analysis_from_config()` in `src/cli.py`: when `config.use_phonemes` is True and the selected Whisper model's `is_cached` is False, attempt a lightweight network reachability check (socket connect to huggingface.co:443, 3s timeout); if unreachable, print "Model '{model}' not cached locally and no network available — select a cached model or connect to the internet" and exit with code 1 (edge case: Whisper model unavailable + no network)

**Checkpoint**: Whisper step skipped when phonemes disabled. Model selection recorded in result metadata. Offline guard fires with a clear message when an uncached model is chosen without network.

---

## Phase 6: User Story 4 — Parallelized Analysis Execution (Priority: P2)

**Goal**: Independent algorithms run concurrently. Live multi-track progress. Stem separation cascade failure handled gracefully. TDD order: tests first.

**Independent Test**: Time a full run before and after this phase on the same fixture file; assert `elapsed_parallel <= 0.70 * elapsed_sequential`. Verify `pipeline_stats.parallelism_ratio > 1.0` in output JSON.

- [x] T020 [P] [US4] Write unit tests for `DependencyGraph.topological_sort()` in `tests/unit/test_pipeline.py`: test no deps → single layer; chain A→B→C → 3 layers; diamond A→B,C→D → 3 layers with B,C parallel; failed step removes all transitively-dependent steps from remaining layers (G4: stem_separation cascade); run now — MUST fail
- [x] T020 [P] [US4] Write integration test in `tests/integration/test_parallel_runner.py`: run `ParallelRunner` on a fixture audio file; assert `elapsed_parallel <= 0.70 * elapsed_sequential` (directly validates SC-002 30% speedup); assert result tracks are identical to a sequential run; run now — MUST fail
- [x] T020 [US4] Implement `DependencyGraph` class in `src/analyzer/pipeline.py`: constructor takes `steps: list[PipelineStep]`; implement `topological_sort() -> list[list[PipelineStep]]` returning concurrent execution layers; when a step has `status == FAILED`, mark all transitively-dependent steps as `SKIPPED` with `error = "dependency failed: {step.name}"`; raise `ValueError` on cycles; run T026 tests — MUST now pass
- [x] T020 [US4] Implement `build_pipeline_steps(algorithms: list[Algorithm], use_stems: bool, use_phonemes: bool) -> list[PipelineStep]` in `src/analyzer/pipeline.py`: for each algorithm, read `algo.preferred_stem` to infer `depends_on` (full-mix → `["audio_load"]`, stem → `["stem_separation"]`); add fixed steps "audio_load", "stem_separation" (if use_stems), "phoneme_analysis" (if use_phonemes) with correct dependencies
- [x] T030 [US4] Implement `ParallelRunner` class in `src/analyzer/pipeline.py`: `run(audio_path: str, steps: list[PipelineStep], stems: StemSet | None, progress_callback) -> AnalysisResult`; use `concurrent.futures.ThreadPoolExecutor` for local librosa steps; for subprocess algorithms group by stem group (full-mix, drums, vocals, piano) and launch each as a separate `subprocess.Popen` via existing `_run_subprocess_batch`; fire `progress_callback(step_name, status, detail)` on each state change; run T027 integration test — MUST now pass
- [x] T031 [US4] Implement live multi-track progress display in `src/analyzer/progress.py` using `rich.live.Live` + `rich.table.Table`; rows per step: name, status (color-coded), elapsed time, mark count; fall back to `click.echo` line-per-event when stdout is not a TTY (FR-010, FR-011)
- [x] T032 [US4] Wire `ParallelRunner` into `_run_analysis_from_config()` in `src/cli.py`: replace `AnalysisRunner.run()` call with `ParallelRunner.run()`; build steps via `build_pipeline_steps()`; pass `ProgressDisplay` instance as progress_callback

**Checkpoint**: Full run shows live multi-algorithm progress. `pipeline_stats.parallelism_ratio > 1.0` in output JSON. T027 integration test passes (`elapsed_parallel <= 0.70 * elapsed_sequential`).

---

## Phase 7: User Story 5 — Optimized Pipeline Dependency Ordering (Priority: P3)

**Goal**: All 22 algorithms declare explicit `depends_on`. `build_pipeline_steps()` reads declarations directly. Audio loading and stem separation each occur exactly once. TDD order: tests first.

**Independent Test**: Assert `pipeline_stats.step_timings` contains "audio_load" exactly once and "stem_separation" at most once. Assert all 22 algorithms' `depends_on` match their `preferred_stem`.

- [x] T033 [US5] Write unit tests for `depends_on` declarations in `tests/unit/test_pipeline.py`: for every algorithm in `default_algorithms()`, assert `preferred_stem != "full_mix"` implies `depends_on == ["stem_separation"]`, and `preferred_stem == "full_mix"` implies `depends_on == ["audio_load"]`; assert `depends_on` is never empty; also assert audio_load and stem_separation each appear exactly once in `pipeline_stats.step_timings` for a fixture run; run now — MUST fail (declarations not yet added)
- [x] T034 [US5] Add `depends_on: ClassVar[list[str]] = []` to `Algorithm` base class in `src/analyzer/algorithms/base.py`; document the convention in a class-level comment
- [x] T035 [P] [US5] Declare `depends_on = ["stem_separation"]` on all stem-dependent algorithm classes: `LibrosaBeatAlgorithm`, `LibrosaBarAlgorithm` in `src/analyzer/algorithms/librosa_beats.py`; `LibrosaDrumsAlgorithm` in `src/analyzer/algorithms/librosa_hpss.py`; all 3 classes in `src/analyzer/algorithms/vamp_beats.py`; all 3 classes in `src/analyzer/algorithms/vamp_onsets.py`; both classes in `src/analyzer/algorithms/vamp_pitch.py`; both classes in `src/analyzer/algorithms/vamp_harmony.py`; both classes in `src/analyzer/algorithms/madmom_beat.py`
- [x] T036 [P] [US5] Declare `depends_on = ["audio_load"]` on full-mix algorithm classes: `LibrosaOnsetAlgorithm` in `src/analyzer/algorithms/librosa_onset.py`; all 3 band classes in `src/analyzer/algorithms/librosa_bands.py`; `LibrosaHarmonicAlgorithm` in `src/analyzer/algorithms/librosa_hpss.py`; both classes in `src/analyzer/algorithms/vamp_structure.py`; run T033 tests — MUST now pass
- [x] T037 [US5] Update `build_pipeline_steps()` in `src/analyzer/pipeline.py` to read `algo.depends_on` directly instead of inferring from `algo.preferred_stem`; add an assertion (`assert algo.depends_on`, f"Algorithm {algo.name} has empty depends_on — add a declaration") so any future algorithm missing the declaration fails loudly rather than silently
- [x] T038 [US5] Add `pipeline_stats` field to `AnalysisResult` in `src/analyzer/result.py` (optional dict: `total_wall_clock_ms`, `total_cpu_ms`, `parallelism_ratio`, `step_timings`); update JSON serialization and deserialization in `src/export.py` to include `pipeline_stats` when present
- [x] T039 [US5] Populate `pipeline_stats` in `ParallelRunner.run()` in `src/analyzer/pipeline.py`: record wall-clock start/end; sum per-step durations for `total_cpu_ms`; compute `parallelism_ratio = total_cpu_ms / total_wall_clock_ms`; attach to returned `AnalysisResult`

**Checkpoint**: T033 tests pass. `pipeline_stats` present in output JSON with correct counts. `build_pipeline_steps()` uses explicit declarations. Any algorithm missing `depends_on` causes a loud assertion failure.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Backward compatibility, integration tests, and documentation.

- [x] T040 [P] Update `src/analyzer/runner.py` to preserve backward-compatible `progress_callback(index, total, name, mark_count)` signature as a thin wrapper over the new `progress_callback(step_name, status, detail)` contract; verify the Flask review server SSE path continues to work
- [x] T041 [P] Write integration test in `tests/integration/test_wizard_noninteractive.py`: assert `--non-interactive` flag suppresses all questionary prompts (no TTY interaction occurs) and produces a valid JSON result; this replaces the duplicate "add --non-interactive" task that was already handled in T014
- [x] T042 [P] Write integration test for FR-011 non-TTY fallback in `tests/integration/test_wizard_noninteractive.py`: pipe wizard through a non-TTY shell (`echo "" | xlight-analyze wizard tests/fixtures/short.mp3`) and assert it completes without error and produces a valid JSON result
- [x] T043 Add `wizard` subcommand documentation to the README (or wherever existing commands are documented) so it appears in `xlight-analyze --help`
- [x] T044 Update `specs/014-cli-wizard-pipeline/quickstart.md` with: install commands for questionary and rich, how to run the wizard interactively and non-interactively, how to read `pipeline_stats` from the JSON output, and a note on SC-004 (manually verify wizard reaches first prompt in <2s) and SC-002 (T027 integration test is the automated check for the 30% target)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — blocks all user story phases; TDD order within: T005+T006 (write tests) → T007+T008 (implement)
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on other user story phases
- **US2 (Phase 4)**: Depends on Phase 3 (wizard shell must exist to insert cache step)
- **US3 (Phase 5)**: Depends on Phase 3 (wizard shell must exist to insert Whisper step)
- **US4 (Phase 6)**: Depends on Phase 2 (PipelineStep) — fully independent of US1/US2/US3; can run in parallel with Phases 3–5
- **US5 (Phase 7)**: Depends on Phase 6 (ParallelRunner and build_pipeline_steps must exist)
- **Polish (Phase 8)**: Depends on all desired stories being complete

### TDD Order Within Each Phase

> Constitution §IV mandates: write the test, confirm it fails, then implement, then confirm it passes.

| Phase | Test task(s) | Implementation task(s) |
|-------|-------------|----------------------|
| 2 | T005, T006 | T007, T008 |
| 4 (US2) | T016 | T017 |
| 5 (US3) | T021 | T022 |
| 6 (US4) | T026, T027 | T028–T032 |
| 7 (US5) | T033 | T034–T039 |

### Parallel Opportunities Within Phases

- T002, T003, T004: fully parallel (different files)
- T005, T006: fully parallel (different files)
- T007, T008: fully parallel after T005/T006 (different files)
- T021, T022: fully parallel (different aspects of same module)
- T026, T027: fully parallel (different test files, no shared dependency)
- T035, T036: fully parallel (different algorithm files)
- T040, T041, T042: fully parallel (different files)
- US4 (T026–T032) and US1–US3 can be developed simultaneously by separate workstreams

---

## Parallel Example: US4 (Parallelized Analysis Execution)

```
# Phase 6 starts after Phase 2. Write tests first:
Task T026 (write): DependencyGraph tests in tests/unit/test_pipeline.py  ← [P] can start together
Task T027 (write): ParallelRunner integration test in tests/integration/  ←

# Confirm T026 and T027 FAIL, then implement:
Task T028: Implement DependencyGraph in src/analyzer/pipeline.py  (makes T026 pass)
Task T029: Implement build_pipeline_steps() in src/analyzer/pipeline.py
Task T031: Implement ProgressDisplay in src/analyzer/progress.py  ← [P] independent

# Once T028 + T029 done:
Task T030: Implement ParallelRunner in src/analyzer/pipeline.py  (makes T027 pass)

# Once T030 done:
Task T032: Wire ParallelRunner into src/cli.py
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Phase 1: Setup (T001–T004)
2. Phase 2: Foundational — T005+T006 (tests, confirm fail) → T007+T008 (implement, confirm pass)
3. Phase 3: US1 wizard shell (T009–T015)
4. Phase 4: US2 cache awareness (T016–T020, TDD order)
5. **STOP and VALIDATE**: `xlight-analyze wizard song.mp3` fully navigable with cache control
6. Ship if ready

### Incremental Delivery

1. Setup + Foundational → shared scaffolding
2. US1 → wizard navigable and wired to analysis
3. US2 → cache step added (both P1 stories done)
4. US3 → Whisper step + offline guard
5. US4 → parallel execution + live progress (30% speedup)
6. US5 → explicit dependency declarations + pipeline_stats
7. Polish → backward compat, integration tests, docs

### Parallel Team Strategy

With two workstreams after Phase 2:
- **Stream A**: US1 → US2 → US3 (wizard UX)
- **Stream B**: US4 → US5 (pipeline engine)
- Streams integrate in Phase 8 (Polish)

---

## Notes

- [P] tasks use different files or have no shared dependencies — safe to parallelize
- TDD is enforced: test tasks appear before their implementation targets in every phase
- Each phase ends with a Checkpoint that is independently verifiable
- US4 (T026–T032) and US1–US3 are fully parallel — no file conflicts
- The existing `analyze` command MUST NOT be modified or broken by any task
- `_run_analysis_from_config()` (T015) is the key integration point shared by wizard and analyze
- Commit after each task or logical group (e.g., after each Checkpoint)
