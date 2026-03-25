# Feature Specification: Comprehensive Stem×Parameter Sweep Matrix

**Feature Branch**: `015-sweep-matrix`
**Created**: 2026-03-24
**Status**: Draft
**Input**: Replace the current limited sweep system (capped at 3 stems per algorithm, minimal permutations) with a comprehensive matrix that runs every algorithm against every applicable stem with full parameter permutations, stores structured results, and provides CLI + UI views for browsing, comparing, and selecting the best timing tracks.

## Clarifications

### Session 2026-03-24

- Q: Which algorithms should the sweep include — only the current 22, or also the ~10 additional high-value installed Vamp plugins? Should stem assignments be documented? → A: Include all ~32 algorithms (current 22 + new high-value installed plugins: aubio onset, aubio tempo, percussiononsets, bbc-energy, bbc-peaks, bbc-spectral-flux, bbc-rhythm, qm-keydetector, qm-transcription, silvet, segmentino, tempogram, amplitudefollower) and require a stem affinity rationale document explaining why each algorithm is assigned to specific stems.
- Q: Should the sweep run ALL stems for every algorithm, or use affinity to determine default stems? → A: Use affinity to determine default stems per algorithm (no artificial cap), but allow user override via `--stems` or TOML config to include any stem.
- Q: New plugins produce continuous value curves (energy, spectral flux, amplitude) not just timing marks. Should the sweep handle both? → A: Yes, support both timing tracks and value curves in the sweep. Score and rank them separately since they serve different xLights purposes (timing marks → beat/onset effects, value curves → brightness/color/position effects).
- Q: Should the unified sweep report store full timing marks for every permutation, or just metadata? → A: Unified report stores metadata only (scores, params, counts); full timing marks and value curve data stored in per-algorithm files. Keeps the unified report fast to load (~1MB) while preserving all data for deep inspection.
- Q: Should sweeps run on the full song or a sample segment for speed? → A: Auto-select a representative high-energy segment (chorus-like section, not silence/intro) for the sweep. Run all permutations on that segment for speed. Then run the winning parameters on the full song for the final result.

## Overview

The existing sweep infrastructure generates a small number of parameter permutations per algorithm, limits each to at most 3 stems, and stores results in isolated per-algorithm JSON files. Users cannot easily compare results across stems, algorithms, or parameter sets. This feature replaces that with a full matrix sweep: N stems × Y permutations per algorithm, unified result storage, CLI ranking, and a review UI for visual comparison.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Run a Full Sweep Matrix (Priority: P1) 🎯 MVP

A user has a song with separated stems and wants to find the best timing track for each analysis algorithm. They run a single command that sweeps every algorithm across all applicable stems with full parameter ranges, then see the total permutation count, progress, and final results.

**Why this priority**: Without the ability to run the full matrix, no other feature in this spec delivers value. This is the core engine.

**Independent Test**: Run `xlight-analyze sweep-matrix song.mp3` on a song with 6 stems. Verify that every algorithm runs against every applicable stem (not capped at 3), that the total permutation count matches N_stems × Y_params, and that a unified results file is written.

**Acceptance Scenarios**:

1. **Given** a song with 6 stems (drums, bass, vocals, guitar, piano, other) plus full_mix, **When** the user runs `sweep-matrix`, **Then** each algorithm is tested against every stem that passed quality inspection (keep + review), plus full_mix.
2. **Given** an algorithm with 4 sensitivity values and 5 applicable stems, **When** the sweep runs, **Then** 20 permutations are executed for that algorithm (5 stems × 4 params).
3. **Given** the `--dry-run` flag, **When** the user runs `sweep-matrix --dry-run`, **Then** the system displays the full permutation matrix (algorithm × stem × params) with total count but does not execute any analysis.
4. **Given** the `--algorithms` filter, **When** the user passes `--algorithms qm_beats,qm_onsets_complex`, **Then** only those two algorithms are swept.
5. **Given** the `--stems` filter, **When** the user passes `--stems drums,vocals`, **Then** only those stems (plus full_mix) are used for all algorithms.
6. **Given** the `--max-permutations` safety cap (default 500), **When** the total matrix exceeds the cap, **Then** the system warns the user and asks for confirmation before proceeding.

---

### User Story 2 — View and Rank Sweep Results via CLI (Priority: P1)

After a sweep completes, the user wants to see a ranked table of all results sorted by quality score, filterable by algorithm, stem, or parameter values, so they can identify the best timing track for each algorithm.

**Why this priority**: Results are useless without a way to view them. This is the minimum viable output.

**Independent Test**: Run `xlight-analyze sweep-results song_sweep.json` after a completed sweep. Verify the table shows all results ranked by quality score, and filtering by `--algorithm` and `--stem` narrows the output correctly.

**Acceptance Scenarios**:

1. **Given** a completed sweep with 200 results, **When** the user runs `sweep-results`, **Then** a table is displayed showing rank, quality score, algorithm, stem, parameters, and mark count, sorted by quality score descending.
2. **Given** `--algorithm qm_beats`, **When** the user runs `sweep-results`, **Then** only results for `qm_beats` are shown.
3. **Given** `--stem drums`, **When** the user runs `sweep-results`, **Then** only results where the stem is "drums" are shown.
4. **Given** `--best`, **When** the user runs `sweep-results --best`, **Then** only the top-scoring result per algorithm is shown (one row per algorithm).
5. **Given** `--top 10`, **When** the user runs `sweep-results --top 10`, **Then** only the top 10 results globally are shown.

---

### User Story 3 — Browse and Compare Results in the Review UI (Priority: P2)

A user opens the review UI and navigates to a "Sweep Results" view where they can browse all results in a sortable, filterable table. They select two results to compare side-by-side, overlaying both on the song timeline to visually evaluate which timing track better matches the music.

**Why this priority**: Visual comparison is the most effective way to judge timing track quality against the audio. The CLI table provides ranking but not the musical context.

**Independent Test**: Open the review UI for a song with completed sweep results. Verify the Sweep Results table loads, supports sorting by quality score, filtering by algorithm/stem, and the comparison mode overlays two selected results on the timeline.

**Acceptance Scenarios**:

1. **Given** a song with sweep results, **When** the user opens the Sweep Results view, **Then** a sortable table shows all results with columns for rank, algorithm, stem, quality score, mark count, avg interval, and parameters.
2. **Given** the table is displayed, **When** the user clicks a column header, **Then** the table sorts by that column.
3. **Given** the table is displayed, **When** the user types in the filter box, **Then** results are filtered by algorithm name, stem name, or parameter values.
4. **Given** the user selects two results (via checkboxes), **When** they click "Compare", **Then** a timeline view shows both results overlaid with distinct colors, the audio waveform, and a playhead.
5. **Given** two results in comparison mode, **When** the user plays the audio, **Then** both timing track marks are shown on the timeline and the user can visually judge which aligns better with the music.

---

### User Story 4 — Configure Sweep via TOML (Priority: P2)

A user wants to customize which algorithms to sweep, which stems to include, parameter ranges, and constraints without using CLI flags every time. They create a TOML config file and pass it to the sweep command.

**Why this priority**: Power users need repeatable, shareable sweep configurations. TOML provides a readable, versionable format.

**Independent Test**: Create a TOML config that restricts the sweep to 2 algorithms with custom parameter ranges. Run `sweep-matrix --config sweep.toml` and verify only the specified algorithms run with the specified ranges.

**Acceptance Scenarios**:

1. **Given** a TOML config specifying `algorithms = ["qm_beats", "qm_onsets_complex"]`, **When** the sweep runs, **Then** only those two algorithms are swept.
2. **Given** a TOML config specifying `stems = ["drums", "bass"]`, **When** the sweep runs, **Then** only those stems plus full_mix are used.
3. **Given** a TOML config with custom parameter ranges `[params.qm_beats] inputtempo = [100, 120, 140]`, **When** the sweep runs, **Then** those exact values are used instead of the auto-derived ranges.
4. **Given** a TOML config with `max_permutations = 100`, **When** the matrix exceeds 100, **Then** the system warns before proceeding.
5. **Given** no `--config` flag, **When** the sweep runs, **Then** all algorithms, all applicable stems, and auto-derived parameter ranges are used (the default comprehensive behavior).

---

### User Story 5 — Auto-Select Best Results and Export (Priority: P2)

After the sweep completes, the system automatically identifies the best-scoring result for each algorithm and offers to export those as the final timing tracks for use in xLights.

**Why this priority**: The sweep produces hundreds of results. Automatically selecting the best saves the user from manually identifying winners.

**Independent Test**: After a completed sweep, verify the system reports the best result per algorithm and, when the user confirms, exports those as timing tracks.

**Acceptance Scenarios**:

1. **Given** a completed sweep, **When** results are displayed, **Then** the system highlights the best-scoring result for each algorithm with its stem and parameters.
2. **Given** the user confirms the auto-selection, **When** export runs, **Then** the winning timing tracks are exported as `.xtiming` files named with the algorithm, stem, and parameter signature.
3. **Given** the user disagrees with auto-selection, **When** they use `--select` to override, **Then** the specified results are exported instead of the auto-selected ones.
4. **Given** two results with identical quality scores for the same algorithm, **Then** the one with fewer marks (simpler track) is preferred.

---

### User Story 6 — Parallel Execution with Progress Display (Priority: P3)

The sweep matrix can contain hundreds of permutations. The system runs independent permutations concurrently and shows a live progress display with current algorithm, stem, parameter set, completion count, and estimated time remaining.

**Why this priority**: Parallelism reduces total sweep time proportionally to available cores. Progress display is essential for a process that may take minutes.

**Independent Test**: Run a sweep matrix with at least 20 permutations. Verify that multiple permutations run concurrently (wall clock time < sequential time) and the progress display updates in real-time.

**Acceptance Scenarios**:

1. **Given** a sweep with 100 permutations and 4 available cores, **When** the sweep runs, **Then** up to 4 permutations execute concurrently.
2. **Given** an in-progress sweep, **Then** the progress display shows: current algorithm, current stem, current parameters, N/M completed, and estimated time remaining.
3. **Given** a permutation that fails (algorithm error), **Then** the failure is logged, the result is marked as failed, and the sweep continues with remaining permutations.

---

### Edge Cases

- **No stems available**: Fall back to full_mix only for all algorithms. Warn the user that results will be limited.
- **All stems are SKIPped**: Same as no stems — use full_mix. The sweep still runs.
- **Algorithm has no tunable parameters**: Run a single pass per applicable stem (1 × N_stems permutations).
- **Total permutations exceed safety cap**: Warn and ask for confirmation. Show the breakdown (which algorithms contribute most) so the user can filter.
- **Sweep interrupted (Ctrl-C)**: Save all completed results to disk before exiting. Partial results are still valuable.
- **Vamp plugins not installed**: Skip vamp-based algorithms with a warning. Continue with librosa/madmom algorithms.
- **Duplicate parameter combinations**: Deduplicate before running. If two config sources produce the same algorithm×stem×params tuple, run it once.
- **Very long songs (>10 min)**: Each permutation takes longer. The estimated time display helps the user decide whether to filter the matrix.
- **Concurrent subprocess conflicts**: Vamp/madmom algorithms run in subprocesses. Concurrent execution must not share stdin/stdout between subprocesses.
- **Song shorter than sample duration**: If the song is shorter than the configured sample duration (default 30s), sweep the full song. No segment selection needed.
- **No high-energy segment found**: If the song has uniform energy (ambient/drone), fall back to a segment starting at 20% of the song duration.

---

## Requirements *(mandatory)*

### Functional Requirements

**Sweep Matrix Execution**

- **FR-001**: The system MUST sweep every algorithm against its affinity-determined stems (no artificial cap on stem count) plus full_mix. Affinity determines the default stem set per algorithm; the user MAY override this to include any stem via `--stems` CLI flag or TOML config. The algorithm set MUST include all ~32 algorithms: the current 22 plus new high-value installed Vamp plugins (aubio onset, aubio tempo, percussiononsets, bbc-energy, bbc-peaks, bbc-spectral-flux, bbc-rhythm, qm-keydetector, qm-transcription, silvet, segmentino, tempogram, amplitudefollower).
- **FR-001a**: The system MUST include a stem affinity rationale document that explains, for each algorithm, why specific stems are preferred and what audio engineering reasoning supports the assignment.
- **FR-002**: For each algorithm×stem combination, the system MUST run the full set of parameter permutations derived from the algorithm's tunable parameters (sensitivity ranges, tempo values, constraint toggles, etc.).
- **FR-003**: The total number of analysis runs per algorithm MUST equal N_applicable_stems × Y_parameter_permutations.
- **FR-004**: The system MUST support a `--dry-run` mode that computes and displays the full matrix without executing any analysis.
- **FR-005**: The system MUST support a configurable safety cap (`--max-permutations`, default 500) that warns and asks for confirmation when the total matrix exceeds the limit.
- **FR-006**: The system MUST support filtering by algorithm (`--algorithms`) and by stem (`--stems`) to reduce the matrix scope.
- **FR-007**: The system MUST deduplicate identical algorithm×stem×parameter combinations before execution.
- **FR-007a**: The system MUST auto-select a representative audio segment for the sweep by identifying a high-energy section of the song (e.g., chorus or verse, avoiding silence, intros, and fade-outs). The default sample duration MUST be configurable (default: 30 seconds).
- **FR-007b**: All sweep permutations MUST run against the representative segment, not the full song, to reduce execution time.
- **FR-007c**: After the sweep completes and best results are identified, the system MUST re-run the winning parameter set for each algorithm on the full song to produce the final timing tracks and value curves.
- **FR-007d**: The user MAY override the auto-selected segment via `--sample-start` and `--sample-duration` CLI flags or TOML config.

**Result Storage**

- **FR-008**: The system MUST store all sweep results in a single unified JSON file per song (the "sweep report") containing every permutation's metadata: algorithm, stem, parameters, quality score, mark count (or sample count for value curves), average interval, and result type (timing track or value curve). Full timing marks and value curve data MUST NOT be stored in the unified report.
- **FR-009**: The system MUST store per-algorithm result files for individual inspection, each containing all stem×parameter results for that algorithm including full timing marks or value curve data.
- **FR-010**: Each result entry MUST include: algorithm name, stem name, parameter values used, quality score, mark count (for timing tracks) or sample count (for value curves), average interval in milliseconds (for timing tracks), and the timing marks or value curve data.
- **FR-010a**: The system MUST distinguish between two result types: timing tracks (discrete event marks) and value curves (continuous data). Each type MUST be scored and ranked independently since they serve different xLights purposes (timing marks for beat/onset effects, value curves for brightness/color/position effects).
- **FR-010b**: Value curve results from plugins such as bbc-energy, bbc-spectral-flux, bbc-peaks, tempogram, and amplitudefollower MUST be stored as conditioned, normalized arrays (0–100 integer values at the target frame rate) ready for `.xvc` export.

**CLI Commands**

- **FR-011**: A `sweep-matrix` command MUST accept an audio file argument and the options: `--algorithms`, `--stems`, `--max-permutations`, `--dry-run`, `--config`, `--output-dir`.
- **FR-012**: A `sweep-results` command MUST accept a sweep report file and display a ranked table with options: `--algorithm`, `--stem`, `--best`, `--top N`.
- **FR-013**: The `sweep-results` command MUST display columns: rank, quality score, algorithm, stem, mark count, average interval, and key parameter values.

**TOML Configuration**

- **FR-014**: The system MUST support a TOML configuration file that defines: algorithms to sweep, stems to include, per-algorithm parameter ranges (overriding auto-derived values), and a max-permutations cap.
- **FR-015**: When no TOML config is provided, the system MUST use the comprehensive default behavior: all algorithms, all applicable stems, auto-derived parameter ranges.

**Review UI**

- **FR-016**: The review UI MUST include a "Sweep Results" view accessible from the toolbar.
- **FR-017**: The Sweep Results view MUST display a sortable, filterable table of all results with the same columns as the CLI output.
- **FR-018**: The Sweep Results view MUST support selecting two results for side-by-side comparison on the timeline with the audio waveform.
- **FR-019**: In comparison mode, the two selected timing tracks MUST be displayed in distinct colors with a shared playhead and audio playback.

**Auto-Selection and Export**

- **FR-020**: After a sweep completes, the system MUST identify the best-scoring result for each algorithm (highest quality score, tie-broken by fewer marks).
- **FR-021**: The system MUST display the auto-selected winners and offer to export them as `.xtiming` files.
- **FR-022**: The user MUST be able to override auto-selection via CLI flags or UI interaction.

**Parallel Execution**

- **FR-023**: Independent permutations (different stems or different parameter sets for the same algorithm) MUST be eligible for concurrent execution.
- **FR-024**: The progress display MUST show: current algorithm, current stem, current parameters, completed/total count, and estimated time remaining.
- **FR-025**: A failed permutation MUST be logged and skipped without aborting the remaining sweep.

### Key Entities

- **Sweep Matrix**: The full cross-product of algorithms × applicable stems × parameter permutations for a given song.
- **Sweep Report**: A unified JSON file containing all permutation results for one song, plus metadata (audio path, timestamp, total permutations, duration).
- **Permutation Result**: A single algorithm×stem×params run result containing quality score, timing marks, mark count, average interval, and the parameters used.
- **Sweep Configuration**: A TOML-defined (or auto-derived) specification of which algorithms, stems, and parameter ranges to sweep.
- **Auto-Selection**: The system's recommendation of the best-scoring result per algorithm, used as the default export set.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running a full sweep matrix on a 6-stem, 3.5-minute song completes within 5 minutes with default settings (all algorithms, affinity stems, auto-derived params, 30-second sample segment).
- **SC-002**: The total number of permutations executed equals the sum across all algorithms of (applicable stems × parameter combinations) — no stem caps, no skipped combinations.
- **SC-003**: The `sweep-results` CLI command displays results within 1 second for a report with up to 500 results.
- **SC-004**: The review UI Sweep Results view loads and renders a 500-row table within 2 seconds.
- **SC-005**: Auto-selected best results achieve quality scores at least as high as the best result found by the previous limited sweep system (no regression).
- **SC-006**: The `--dry-run` flag accurately predicts the total permutation count that the actual sweep will execute (exact match).
- **SC-007**: Parallel execution achieves at least 2× speedup over sequential execution on a machine with 4+ cores when running 20 or more permutations.
- **SC-008**: Interrupted sweeps (Ctrl-C) preserve all completed results — the partial report file is valid and loadable.

---

## Assumptions

- Stem separation has already been run before the sweep. The sweep does not perform separation.
- The full_mix is always available and always included in the sweep, regardless of stem filtering.
- Quality inspection (KEEP/REVIEW/SKIP verdicts) is run before the sweep to determine applicable stems. SKIP stems are excluded; KEEP and REVIEW stems are included.
- The existing quality scoring system (`score_track`) is used to score each permutation's results. No new scoring algorithm is introduced.
- Parameter ranges for algorithms without tunable Vamp parameters (librosa, madmom) are stem-only sweeps (one pass per stem).
- The safety cap (default 500) is a soft limit — the user can confirm to proceed beyond it.
- The TOML config format follows the project's existing TOML conventions (used by scoring configs).
- Vamp/madmom algorithms continue to run in the `.venv-vamp` subprocess for ABI isolation.
- The sweep report JSON file may be large (10-50 MB for comprehensive sweeps). This is acceptable for local filesystem storage.
