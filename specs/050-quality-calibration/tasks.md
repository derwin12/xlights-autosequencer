---

description: "Task list for xLights Sequence Quality Calibration Harness"
---

# Tasks: xLights Sequence Quality Calibration Harness

**Input**: Design documents from `/workspace/specs/050-quality-calibration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Tests**: REQUIRED — constitution Principle IV (Test-First Development) mandates failing tests before implementation.

**Organization**: Tasks grouped by user story per spec.md priorities (P1 → P4). Within each story: tests before implementation; models before services; services before CLI.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1, US2, US3, US4)
- File paths are absolute project-relative (`src/…`, `tests/…`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding for the new evaluation module and golden-corpus tree.

- [X] T001 Create directory skeleton with `__init__.py` files: `src/evaluation/`, `src/evaluation/metrics/`, `tests/evaluation/`, `tests/evaluation/fixtures/degenerate/`, `tests/evaluation/fixtures/minimal_xsq/`, `tests/golden/pro_reference/notes/`, `tests/golden/reports/`
- [X] T002 [P] Add `xlight-evaluate` console script entry to `pyproject.toml` pointing at `src.cli.evaluate:main`
- [X] T003 [P] Create `tests/golden/reports/.gitignore` that ignores `*.json` and keeps `.gitkeep`, plus `tests/golden/reports/.gitkeep`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Entity types, parser, corpus loader, and deterministic generator wrapper — all required before any user story can compute metrics.

**⚠️ CRITICAL**: No user story work begins until every task in this phase is complete.

- [X] T004 [P] Hand-author minimal valid `.xsq` fixture at `tests/evaluation/fixtures/minimal_xsq/tiny.xsq` with 2–3 placements on 2 models and 2 palettes (for parser unit tests)
- [X] T005 [P] Create 4 degenerate `SequenceSummary` JSON fixtures in `tests/evaluation/fixtures/degenerate/`: `monochrome.json`, `single_effect.json`, `random_alignment.json`, `empty.json` (per research.md §9)
- [X] T006 Implement `src/evaluation/models.py` with frozen dataclasses `Placement` and `SequenceSummary` plus JSON load helpers for the degenerate fixtures (per data-model.md §Placement, §SequenceSummary)
- [X] T007 [P] Implement `src/evaluation/metrics/__init__.py` with `MetricKind` enum, `MetricTolerance` dataclass, `MetricDefinition` dataclass, `MetricValue` dataclass, empty metric registry, and default-tolerance constant (per data-model.md §MetricDefinition)
- [X] T008 Write failing tests in `tests/evaluation/test_xsq_reader.py`: parse `tiny.xsq`, parse a `.xsqz` (zip the tiny fixture at test time), extract placements with correct start/end/model/effect_type/palette_colors/layer_index, reject malformed XML with a clean error
- [X] T009 Implement `src/evaluation/xsq_reader.py`: parse `.xsq` via `xml.etree.ElementTree` and `.xsqz` via `zipfile`, build `SequenceSummary`, derive `effect_type` via the `E_NOTEBOOK_<Name>` pattern, apply name-heuristic prop-type inference (per research.md §1, §2); T008 passes
- [X] T010 [P] Write failing tests in `tests/evaluation/test_corpus.py` covering: manifest load from JSON, audio-hash match/mismatch warning, skip categorization (missing mp3 → corpus-side, missing xsq → corpus-side, master_may_differ propagation), unique `(song_id, pro_id)` enforcement
- [X] T011 Implement `src/evaluation/corpus.py`: load `manifest.json`, compute MD5 of on-disk mp3, compare with manifest, classify entries, expose `measurable_songs()` and `skips()` accessors; T010 passes
- [X] T012 [P] Write failing test in `tests/evaluation/test_generator_runner.py` that invokes the runner on a short fixture MP3 twice with the same audio hash and asserts byte-identical `.xsq` bytes returned
- [X] T013 Implement `src/evaluation/generator_runner.py`: thin wrapper calling existing `src.generator` pipeline with deterministic seed derived from audio hash, returning `.xsq` bytes in memory (per research.md §4); T012 passes

**Checkpoint**: Foundational phase complete — entities, parser, corpus, and deterministic generator are ready for user-story work.

---

## Phase 3: User Story 1 — Detect Unintended Generator Regressions (Priority: P1) 🎯 MVP

**Goal**: A maintainer can run `xlight-evaluate check` and either see the code pass or see exactly which gated metric regressed, without any pro references present.

**Independent Test**: Run `xlight-evaluate snapshot` to create a baseline, make a deliberate generator tweak, run `xlight-evaluate check` — expect a failing exit code with the regressed metric named. Reverting the tweak restores exit 0.

### Tests for User Story 1 (write first — must fail before implementation)

- [X] T014 [P] [US1] Write failing tests in `tests/evaluation/test_metrics_pacing.py` for `placements_per_minute` and `density_energy_correlation` (expected values on `tiny.xsq`; assert empty fixture → 0, monochrome fixture handled cleanly)
- [X] T015 [P] [US1] Write failing tests in `tests/evaluation/test_metrics_palette.py` for `palette_top5_colors` and `per_section_palette_diversity`
- [X] T016 [P] [US1] Write failing tests in `tests/evaluation/test_metrics_effects.py` for `effect_type_histogram` (including Jensen-Shannon divergence math against known hand-computed values) and `unknown_effect_fraction`
- [X] T017 [P] [US1] Write failing tests in `tests/evaluation/test_metrics_alignment.py` for `beat_alignment_pct` with ±80 ms tolerance (per FR-007)
- [X] T018 [P] [US1] Write failing tests in `tests/evaluation/test_metrics_sections.py` for `section_transition_delta`
- [X] T019 [P] [US1] Write failing tests in `tests/evaluation/test_metrics_internal.py` for `tier_utilization` and `theme_assignment_consistency` (both ours-only per data-model.md registry table)
- [X] T020 [P] [US1] Write failing tests in `tests/evaluation/test_baseline.py` covering: read/write baseline JSON, schema-version mismatch detection, song-set mismatch detection, per-metric tolerance comparison (both default and overridden), detection of same-commit baseline update via git diff
- [X] T021 [P] [US1] Write failing tests in `tests/evaluation/test_cli_check.py` covering every documented exit code from `contracts/evaluate-check.md` (0 pass, 3 generator error, 4 missing baseline, 5 schema mismatch, 6 regression, 7 song-count mismatch)
- [X] T022 [P] [US1] Write failing tests in `tests/evaluation/test_cli_snapshot.py` covering exit codes 0, 3, 8 and the `--force` flag behavior from `contracts/evaluate-snapshot.md`

### Implementation for User Story 1

- [X] T023 [P] [US1] Implement `src/evaluation/metrics/pacing.py`; register `placements_per_minute` (15% rel tolerance) and `density_energy_correlation` (default 10%); T014 passes
- [X] T024 [P] [US1] Implement `src/evaluation/metrics/palette.py`; register `palette_top5_colors` (default) and `per_section_palette_diversity` (default); T015 passes
- [X] T025 [P] [US1] Implement `src/evaluation/metrics/effects.py` including inline Jensen-Shannon divergence (research.md §8); register `effect_type_histogram` (default); T016 passes
- [X] T026 [P] [US1] Implement `src/evaluation/metrics/alignment.py`; register `beat_alignment_pct` (±3 pp absolute tolerance); T017 passes
- [X] T027 [P] [US1] Implement `src/evaluation/metrics/sections.py`; register `section_transition_delta` (default); T018 passes
- [X] T028 [P] [US1] Implement `src/evaluation/metrics/internal.py`; register `tier_utilization` (±0.05 absolute) and `theme_assignment_consistency` (default); T019 passes
- [X] T029 [US1] Implement `src/evaluation/baseline.py`: read/write `tests/golden/baseline.json`, schema version check, tolerance-based comparison, git-diff detection of same-commit baseline updates (research.md §5); T020 passes
- [X] T030 [US1] Implement `src/cli/evaluate.py` with `check` and `snapshot` subcommands per `contracts/evaluate-check.md` and `contracts/evaluate-snapshot.md`; wire the click entry point registered in T002; T021 and T022 pass
- [X] T031 [US1] Write `tests/evaluation/test_pathological_floor.py` asserting each of the 9 registered metrics scores every degenerate fixture worse than the minimum observed on the minimal-real fixture (spec FR-020 / SC-003). If any metric fails this, fix the metric or remove it from the gated set before proceeding.
- [X] T032 [US1] Write `tests/evaluation/test_regression_detection.py` — inject 10 synthetic generator regressions via stub runners (one per gated metric regression direction) and assert ≥ 9 are caught by `check` (SC-002: ≥ 90% detection)

**Checkpoint**: US1 MVP shippable — `xlight-evaluate snapshot` + `check` form a closed CI-gated loop with zero pro references required. Pathological-floor and regression-detection SCs verified.

---

## Phase 4: User Story 2 — Compare Against Professional References (Priority: P2)

**Goal**: A maintainer can run `xlight-evaluate compare` and receive a per-song table plus cross-song trend summary that flags metrics where ours-vs-pro moves in the same direction on ≥ 80% of songs.

**Independent Test**: With the committed corpus manifest, run `xlight-evaluate compare` and verify the JSON report contains per-song `metric | pro | ours | delta | direction` rows and a `cross_song_trends` block with `consistent_gap` flags.

### Tests for User Story 2

- [X] T033 [P] [US2] Write failing tests in `tests/evaluation/test_compare.py` covering per-song comparison assembly (pro-side, ours-side, delta, direction) and cross-song consistent-gap detection at the 80% threshold (research.md §10)
- [X] T034 [P] [US2] Write failing tests in `tests/evaluation/test_cli_compare.py` for the `compare` subcommand: full-corpus run, `--json` flag suppresses terminal output, `--song` filter limits to named songs, report JSON persisted to `tests/golden/reports/<iso>.json`, exit codes 0/2/3 per `contracts/evaluate-compare.md`
- [X] T035 [P] [US2] Write `tests/evaluation/test_integration_smoke.py` — 1-song corpus end-to-end: minimal manifest → `compare` → parse report JSON → validate schema version, per-song block, and summary fields

### Implementation for User Story 2

- [X] T036 [US2] Implement `src/evaluation/compare.py` — per-song comparison assembly and cross-song trend detection (no intra-pro variance yet; that's US4); T033 passes
- [X] T037 [US2] Extend `src/cli/evaluate.py` with the `compare` subcommand per `contracts/evaluate-compare.md`, including `--json`, `--song`, and `--corpus` flags; T034 passes
- [X] T038 [US2] Add terminal-summary renderer in `src/evaluation/compare.py` that produces the formatted output shown in the compare contract; T035 integration test passes

**Checkpoint**: US2 complete — pro-vs-ours comparison works end-to-end on real corpus; reports persisted.

---

## Phase 5: User Story 3 — Handle Partial Corpus Gracefully (Priority: P2)

**Goal**: Missing MP3s, unparseable pro files, and `master_may_differ` flags produce clear skip entries and reliability annotations rather than failing the whole run.

**Independent Test**: Remove one MP3 from disk, add a `master_may_differ=true` entry, and delete a pro `.xsq`; run `compare`; verify the report measures the remaining entries, lists the three skips with categories, and tags reduced-reliability metrics on the flagged song.

Most plumbing exists already from Phase 2 (T011 categorization) and Phase 4 (report assembly). This phase adds the integration-level coverage and surfaces gaps.

### Tests for User Story 3

- [X] T039 [P] [US3] Extend `tests/evaluation/test_integration_smoke.py` with scenarios: (a) all entries skipped → exit 2, (b) one of three entries skipped → exit 0 with report listing the skip, (c) `master_may_differ=true` → audio-dependent metrics for that song carry `reliability: "reduced"` in JSON output, (d) unparseable pro `.xsq` is skipped with `category: "corpus-side"` and reason `"pro_unparseable"`

### Implementation for User Story 3

- [X] T040 [US3] Verify and, if needed, patch `reliability` field propagation from manifest `master_may_differ` through metric computation in the pro-ours pipeline so it reaches the `MetricValue` objects in the report; T039 passes
- [X] T041 [US3] Add a `skips` summary line to the terminal report renderer in `src/evaluation/compare.py` showing counts by category; validated by T039

**Checkpoint**: US3 complete — harness robust to partial corpus and master-mismatch scenarios.

---

## Phase 6: User Story 4 — Measure Intra-Pro Noise Floor (Priority: P3)

**Goal**: For songs with ≥ 2 pro sequences, the report shows min/max/range per metric across pros and annotates ours-vs-pro deltas as "within pro variance" or "exceeds pro variance".

**Independent Test**: On the real corpus (Light of Christmas has 3 pros, Danger Zone has 2), run `compare` and verify the report entries for those two songs carry an `intra_pro_variance` block and per-metric within/exceeds annotations on deltas.

### Tests for User Story 4

- [X] T042 [P] [US4] Write failing tests in `tests/evaluation/test_compare_variance.py` for: intra-pro min/max/range computation per metric when a song has 2+ pros, annotation logic (delta within `[min, max]` → "within-variance"; outside → "exceeds pro variance")

### Implementation for User Story 4

- [X] T043 [US4] Extend `src/evaluation/compare.py` to populate the `intra_pro_variance` block and to annotate deltas; T042 passes
- [X] T044 [US4] Update terminal renderer to show `within-variance` / `⚠ exceeds pro variance` markers next to each delta when intra-pro variance exists

**Checkpoint**: US4 complete — noise floor reported; team can distinguish real gaps from artistic variation.

---

## Phase 7: Polish & Corpus Bootstrap

**Purpose**: Real-corpus validation, documentation, and commit of the initial baseline.

- [X] T045 [P] Bootstrap `tests/golden/pro_reference/manifest.json` with the 9 known `(song, pro)` entries from `/home/node/xlights/baseline-sequences/` (Baby Shark, Candy Cane Lane, 2× Danger Zone, 3× Light of Christmas, Kid On Christmas, Shut Up and Dance) with computed audio hashes
- [X] T046 [P] Write short `tests/golden/pro_reference/notes/<song-id>.md` stubs for each of the 6 unique songs (genre, why selected, what the pro did well)
- [X] T047 Write `tests/golden/pro_reference/README.md` documenting manifest format, local-path conventions, and how to acquire missing MP3s (Save Your Tears, Uptown Funk, Christmas Just Ain't Christmas)
- [X] T048 Run `xlight-evaluate compare` against the real corpus; record wall time; verify ≤ 5 minutes (SC-001). If over, profile and optimize; if still over, document the deviation and revisit SC-001.
- [X] T049 Run `xlight-evaluate snapshot` to create the initial `tests/golden/baseline.json`; review metric values for sanity; commit the baseline in the same PR as the rest of the feature
- [X] T050 Execute the `quickstart.md` walkthrough end-to-end (bootstrap → compare → snapshot → simulated regression → check) to validate docs match the shipped CLI; fix any drift
- [X] T051 [P] Add CI workflow entry (or TODO comment in existing CI config) that runs `xlight-evaluate check` on every PR; fail the build on non-zero exit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no prerequisites
- **Foundational (Phase 2)**: depends on Setup; BLOCKS every user story
- **US1 (Phase 3)**: depends on Foundational; independent of US2/US3/US4
- **US2 (Phase 4)**: depends on Foundational; independent of US1 functionally, but practically built after US1 lands so the shared CLI module exists
- **US3 (Phase 5)**: depends on US2 (extends its tests and terminal output)
- **US4 (Phase 6)**: depends on US2 (extends compare report with variance block)
- **Polish (Phase 7)**: depends on US1 + US2 at minimum; corpus bootstrap can start earlier but the baseline commit (T049) requires all gated metrics to be passing floor tests

### Within Each User Story

Tests (constitution IV) MUST be written and confirmed failing before the matching implementation task. Task IDs are ordered so a top-down execution satisfies this naturally.

### Parallel Opportunities

- **Phase 1**: T002 and T003 are [P] — `pyproject.toml` vs `.gitignore` are independent files
- **Phase 2**: T004, T005, T007 are [P]. T006 must run before T011 and US1 work (models.py). T008/T010/T012 write test files in parallel; corresponding implementations (T009/T011/T013) must come after their own tests
- **US1**: All 6 metric-test tasks (T014–T019) are [P]; all 6 metric-impl tasks (T023–T028) are [P] after their tests exist. Baseline tests (T020) and CLI tests (T021, T022) are independent [P]. Implementation of baseline (T029) and CLI (T030) must run sequentially because both edit `src/cli/evaluate.py` implicitly (T030) or depend on registry being populated.
- **US2**: T033, T034, T035 [P]. T036 must run before T037. T038 must run after T037.
- **US3/US4**: small phases, limited parallelism; see task [P] markers.
- **Polish**: T045, T046, T047, T051 are [P]; T048 → T049 → T050 are sequential.

---

## Parallel Example: User Story 1 metric implementation

```bash
# After T014–T019 tests are written and failing, kick off all 6 metric impls in parallel:
Task: "Implement src/evaluation/metrics/pacing.py — register placements_per_minute, density_energy_correlation"
Task: "Implement src/evaluation/metrics/palette.py — register palette_top5_colors, per_section_palette_diversity"
Task: "Implement src/evaluation/metrics/effects.py — register effect_type_histogram with JS divergence"
Task: "Implement src/evaluation/metrics/alignment.py — register beat_alignment_pct"
Task: "Implement src/evaluation/metrics/sections.py — register section_transition_delta"
Task: "Implement src/evaluation/metrics/internal.py — register tier_utilization, theme_assignment_consistency"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Setup (T001–T003)
2. Foundational (T004–T013) — critical, blocks everything
3. US1 (T014–T032) — ship with no pro references required; the CI regression gate is live
4. **Stop, validate, consider shipping.** Everything downstream is strictly additive.

### Incremental delivery

Each phase checkpoint is a coherent increment:
- After US1 → regression gate live; no pro comparison yet
- After US2 → pro comparison report live; noise floor not yet surfaced
- After US3 → partial-corpus resilient; reliability flags honored
- After US4 → intra-pro variance annotations complete
- After Polish → real corpus bootstrapped, initial baseline committed, CI wired

### Parallel team strategy

After Foundational completes:
- **Developer A** → US1 (deepest, MVP)
- **Developer B** → starts US2 once the metric registry (T007) and xsq_reader (T009) are in place
- US3 and US4 are small enough for either developer to pick up once US2 stabilizes

---

## Notes

- Every test task must be run and observed failing before the matching implementation task begins (constitution IV).
- `xlight-evaluate render` or any xLights-render invocation is **out of scope**; if a test requires rendered output, stop and ask — user memory says renders run only on explicit request.
- Pathological-floor validation (T031) is a **gate for the metric set** — any metric that fails must be removed from `gated=True` before the feature ships.
- Baseline (`tests/golden/baseline.json`) must be committed with the feature; PRs that intentionally change metrics must update `baseline.json` in the same commit (research.md §5).
- Commit after each task or coherent task group; never batch unrelated changes (constitution).
