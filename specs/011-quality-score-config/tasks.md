# Tasks: Configurable Quality Scoring

**Input**: Design documents from `/specs/011-quality-score-config/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Included per Constitution Principle IV (Test-First Development).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in all descriptions

---

## Phase 1: Setup

**Purpose**: Create test fixtures and shared test infrastructure for scoring

- [x] T001 Create scoring test fixtures directory and fixture tracks with known properties in tests/fixtures/scoring/
- [x] T002 [P] Add ScoreBreakdown and CriterionResult dataclasses to src/analyzer/result.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core scoring infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Create src/analyzer/scoring_config.py with ScoringCategory dataclass, built-in category definitions (beats, bars, onsets, segments, pitch, harmony, general), category-to-algorithm mapping table, and default criterion weights
- [x] T004 Implement criterion computation functions in src/analyzer/scorer.py: compute density (marks/s), regularity (1 - CV), mark_count, coverage (first-to-last / duration), and min_gap (proportion of intervals >= threshold) for a TimingTrack given duration_ms
- [x] T005 [P] Write failing unit tests for criterion computation in tests/unit/test_scorer.py: test each criterion against fixture tracks with known expected values, test edge cases (0 marks, 1 mark, all marks at same time)
- [x] T006 Implement category-aware score computation in src/analyzer/scorer.py: given a track and its category, compute per-criterion scores using target range interpolation (within range → 1.0, linear falloff outside), then weighted sum normalized to [0.0, 1.0], returning a ScoreBreakdown

**Checkpoint**: Core scoring engine works with built-in defaults. All criterion computations verified by tests.

---

## Phase 3: User Story 1 — Explainable Score Breakdowns (Priority: P1) MVP

**Goal**: Every scored track includes a per-criterion breakdown showing measured value, weight, score contribution, and plain-language description.

**Independent Test**: Run `xlight-analyze analyze song.mp3`, then `xlight-analyze summary song_analysis.json --breakdown` and verify each track shows per-criterion scores with descriptions.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T007 [P] [US1] Write failing unit tests for ScoreBreakdown serialization/deserialization in tests/unit/test_scorer.py: verify ScoreBreakdown.to_dict() and from_dict() roundtrip, verify CriterionResult includes all fields (name, label, measured_value, target_min, target_max, weight, score, contribution)
- [x] T008 [P] [US1] Write failing integration test in tests/integration/test_scoring_pipeline.py: load a fixture analysis JSON, verify each track has score_breakdown with all 5 criteria, verify breakdowns are present in serialized JSON output

### Implementation for User Story 1

- [x] T009 [US1] Add ScoreBreakdown serialization (to_dict/from_dict) to src/analyzer/result.py and wire score_breakdown field into TimingTrack.to_dict() and TimingTrack.from_dict()
- [x] T010 [US1] Update src/analyzer/scorer.py to expose a score_all_tracks(tracks, duration_ms) function that scores every track using CategoryScorer, returns list of ScoreBreakdown, and sets quality_score on each track
- [x] T011 [US1] Update src/export.py to serialize and deserialize score_breakdown in analysis JSON output (backward-compatible: missing score_breakdown loads as None)
- [x] T012 [US1] Update src/cli.py analyze_cmd to call score_all_tracks after runner.run() and include breakdowns in the saved JSON
- [x] T013 [US1] Add --breakdown flag to summary command in src/cli.py: when set, print per-track criterion details (criterion name, score, measured value, target range, weight, contribution) after the summary table
- [x] T014 [US1] Add plain-language labels to each criterion in src/analyzer/scorer.py: "Mark density — timing marks per second of audio", "Regularity — consistency of inter-mark intervals", "Mark count — total number of timing marks", "Coverage — fraction of song duration with marks", "Minimum gap compliance — proportion of intervals >= threshold"

**Checkpoint**: Analysis produces breakdowns in JSON. `summary --breakdown` shows per-criterion details. Tests pass.

---

## Phase 4: User Story 2 — Adjust Scoring Weights and Thresholds (Priority: P1)

**Goal**: Users configure criterion weights and thresholds via TOML config files. Custom configs change track rankings. Invalid configs are rejected with descriptive errors.

**Independent Test**: Create a TOML config doubling the density weight, run analysis with `--scoring-config`, verify denser tracks rank higher than with defaults.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T015 [P] [US2] Write failing unit tests for TOML config loading in tests/unit/test_scoring_config.py: test loading valid config, test default values for missing fields, test validation errors (negative weights, all-zero weights, unknown criterion, unknown category, out-of-range diversity threshold)
- [x] T016 [P] [US2] Write failing unit tests for threshold filtering in tests/unit/test_scorer.py: test tracks below min_mark_count are excluded, test tracks above max_density are excluded, test all-tracks-excluded produces warning
- [x] T017 [P] [US2] Write failing unit tests for diversity filter in tests/unit/test_diversity.py: test near-identical tracks are deduplicated, test duplicate_of field is set, test low threshold effectively disables dedup, test configurable tolerance_ms

### Implementation for User Story 2

- [x] T018 [US2] Add ScoringConfig dataclass and from_toml(path) classmethod to src/analyzer/scoring_config.py: parse TOML via tomllib, merge with defaults, validate all constraints (weights >= 0, sum > 0, known criteria/categories, diversity_threshold in (0,1])
- [x] T019 [US2] Add category target override support to src/analyzer/scoring_config.py: [categories.beats] density_min/max etc. override built-in ScoringCategory ranges
- [x] T020 [US2] Add threshold filtering to src/analyzer/scorer.py: after scoring, mark tracks that fail configured thresholds (min/max per criterion) with passed_thresholds=False and populate threshold_failures list
- [x] T021 [US2] Create src/analyzer/diversity.py with DiversityFilter class: greedy mark-alignment similarity, configurable tolerance_ms and threshold, returns selected tracks with skipped_as_duplicate and duplicate_of set on excluded ScoreBreakdowns
- [x] T022 [US2] Wire ScoringConfig into scorer: update score_all_tracks to accept optional ScoringConfig, apply custom weights and category overrides
- [x] T023 [US2] Add --scoring-config option to analyze command in src/cli.py: load and validate TOML before analysis, exit code 6 on invalid config
- [x] T024 [US2] Update --top N in src/cli.py to use DiversityFilter when selecting top tracks, show skip messages in summary output ("SKIPPED: near-identical to X (Y% match)")

**Checkpoint**: Custom TOML configs change track rankings. Invalid configs rejected. Diversity filter deduplicates --top N. Tests pass.

---

## Phase 5: User Story 3 — Save and Share Scoring Profiles (Priority: P2)

**Goal**: Users save scoring configs as named profiles, reuse by name, list/show available profiles.

**Independent Test**: Save a scoring profile, re-run analysis using the profile name, verify identical scoring results.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T025 [P] [US3] Write failing unit tests for profile management in tests/unit/test_scoring_config.py: test save profile creates TOML file, test load by name searches project-local then user-global, test list profiles returns all available, test project-local overrides user-global with same name

### Implementation for User Story 3

- [x] T026 [US3] Add profile management functions to src/analyzer/scoring_config.py: save_profile(name, config, scope), load_profile(name), list_profiles(), get_profile_path(name) with search order (.scoring/ → ~/.config/xlight/scoring/)
- [x] T027 [US3] Add scoring subcommand group to src/cli.py: `scoring list` (list all profiles with source), `scoring show <name>` (display profile config), `scoring save <name> --from <path>` (save TOML as named profile), `scoring defaults` (print default config as commented TOML to stdout)
- [x] T028 [US3] Add --scoring-profile option to analyze command in src/cli.py: load profile by name, exit code 7 if not found, error if both --scoring-config and --scoring-profile provided
- [x] T029 [US3] Implement default TOML generation in src/analyzer/scoring_config.py: generate_default_toml() returns a fully commented TOML string with all defaults, valid ranges, and descriptions for each field (FR-005 self-documenting)

**Checkpoint**: Profiles save, load, and list correctly. `--scoring-profile` applies saved settings. `scoring defaults` outputs complete documented config. Tests pass.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, review UI integration, and validation

- [x] T030 [P] Add edge case tests to tests/unit/test_scorer.py: zero marks track scores 0.0 with breakdown, all-zero weights rejected, config with thresholds eliminating all tracks warns and outputs unranked list, all 22 tracks near-identical with diversity filter
- [x] T031 [P] Update src/review/server.py to serve score_breakdown data to the review UI
- [x] T032 Run quickstart.md validation: verify all commands in quickstart.md work end-to-end
- [x] T033 Verify backward compatibility: run analysis with no config, confirm quality_score values match baseline scorer output for identical input tracks

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (fixtures + dataclasses)
- **User Story 1 (Phase 3)**: Depends on Phase 2 (scoring engine)
- **User Story 2 (Phase 4)**: Depends on Phase 2 (scoring engine); independent of US1
- **User Story 3 (Phase 5)**: Depends on Phase 4 (ScoringConfig must exist for profiles)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (Explainable Breakdowns)**: Depends on Foundational only — no cross-story dependencies
- **US2 (Adjust Weights/Thresholds)**: Depends on Foundational only — can run in parallel with US1
- **US3 (Save/Share Profiles)**: Depends on US2 (needs ScoringConfig and TOML infrastructure)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Data classes before services
- Scoring logic before CLI integration
- Core implementation before formatting/display

### Parallel Opportunities

- T001 and T002 can run in parallel (different files)
- T005 can run in parallel with T003/T004 (test-first: write failing tests alongside implementation)
- T007 and T008 can run in parallel (different test files)
- T015, T016, T017 can all run in parallel (different test files)
- US1 and US2 can proceed in parallel after Phase 2
- T030 and T031 can run in parallel (different files)

---

## Parallel Example: User Story 2

```bash
# Launch all tests for US2 together (they should all fail initially):
Task: "Tests for TOML config loading in tests/unit/test_scoring_config.py"
Task: "Tests for threshold filtering in tests/unit/test_scorer.py"
Task: "Tests for diversity filter in tests/unit/test_diversity.py"

# Then implement in dependency order:
Task: "ScoringConfig + from_toml() in src/analyzer/scoring_config.py"
Task: "Category target overrides in src/analyzer/scoring_config.py"
Task: "Threshold filtering in src/analyzer/scorer.py"
Task: "DiversityFilter in src/analyzer/diversity.py"
Task: "Wire ScoringConfig into scorer"
Task: "--scoring-config CLI option"
Task: "Diversity filter in --top N"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (fixtures + dataclasses)
2. Complete Phase 2: Foundational (scoring engine with categories)
3. Complete Phase 3: User Story 1 (breakdowns in JSON + summary --breakdown)
4. **STOP and VALIDATE**: Analysis produces explainable breakdowns, summary shows per-criterion details
5. Deliver: Users can now understand why tracks score high or low

### Incremental Delivery

1. Setup + Foundational → Scoring engine ready
2. Add US1 → Explainable breakdowns → Validate → MVP
3. Add US2 → Custom weights, thresholds, diversity filter → Validate
4. Add US3 → Saved profiles → Validate → Feature complete
5. Polish → Edge cases, review UI, backward compat verification

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Constitution requires test-first (Principle IV): write failing tests before implementation
- Backward compatibility critical: default scoring must match current baseline (SC-005)
- The existing `scorer.py` (57 lines) is fully rewritten — no incremental patching
- `tomllib` is Python 3.11+ stdlib — no new pip dependencies
- Category-to-algorithm mapping is a static lookup table, not derived from algorithm metadata
