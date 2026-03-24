# Feature Specification: Interactive CLI Wizard & Pipeline Optimization

**Feature Branch**: `014-cli-wizard-pipeline`
**Created**: 2026-03-24
**Status**: Draft
**Input**: User description: "i want to create a wizard on the command line where we can run and it will guide us through the different selections giving us options for things like to use a cache not use a cache maybe also telling us if the cash exists when it's there allowing us to choose a different whisper models i'd like an interactive so we can kind of use the up and down arrows to do the selections it would be nice and also like to see if we can potentially parallelize some of the analysis and anything we can do that's going to speed up like rather than a sequential analysis for all like the audio stems and stuff or even the main way files i'd also like to rethink to the order of the pipeline that we have is this the most efficient way or are we doing work that gets redone again so let's look at the dependencies and try to relink and reorder some of the steps"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guided Interactive Analysis Setup (Priority: P1)

A user runs `xlight-analyze wizard song.mp3` and is guided step-by-step through all analysis configuration choices via an interactive terminal menu. They use arrow keys to move between options and press Enter to confirm each choice. At the end, the analysis runs with their selections applied.

**Why this priority**: This is the core deliverable of the feature — a discoverable, interactive entry point that makes configuration accessible without memorizing CLI flags. Every other story depends on the wizard existing.

**Independent Test**: Can be fully tested by running `xlight-analyze wizard song.mp3` and confirming all menu screens appear, arrow-key navigation works, selections persist into the analysis run, and a valid result file is produced.

**Acceptance Scenarios**:

1. **Given** a user runs `xlight-analyze wizard song.mp3`, **When** the wizard launches, **Then** a full-screen interactive menu appears in the terminal with the first configuration step highlighted and ready for input.
2. **Given** the wizard is open on any step, **When** the user presses the up or down arrow key, **Then** the highlighted selection changes accordingly without any flicker or redraw artifacts.
3. **Given** the user reaches the final confirmation step, **When** they press Enter, **Then** the analysis starts with all prior selections applied and progress is shown.
4. **Given** the user presses Escape or Ctrl-C at any step, **Then** the wizard exits cleanly without starting analysis and without corrupting any existing cache files.

---

### User Story 2 - Cache Awareness and Control (Priority: P1)

When the wizard reaches the cache step, it shows whether a cached result already exists for the current song (with its age and source hash status), and offers clear options: use the existing cache, regenerate it, or bypass cache entirely for this run.

**Why this priority**: Cache decisions are the most common cause of stale or unexpected results. Making cache state visible prevents confusion and reduces wasted re-analysis time. P1 because it directly affects correctness of output.

**Independent Test**: Can be fully tested by running the wizard on a song that has an existing analysis cache and confirming the cache status is displayed, and that selecting "use cache" skips re-analysis while selecting "regenerate" produces a fresh result.

**Acceptance Scenarios**:

1. **Given** a cached result exists for the input song, **When** the cache step is reached, **Then** the wizard displays "Cache found" along with the cache's age and whether it is still valid (source file unchanged).
2. **Given** no cached result exists, **When** the cache step is reached, **Then** the wizard displays "No cache found — analysis will run fresh."
3. **Given** the user selects "Use existing cache", **When** the wizard completes, **Then** the analysis phase is skipped entirely and the cached result is loaded directly.
4. **Given** the user selects "Regenerate cache", **When** the wizard completes, **Then** a full fresh analysis runs and overwrites the prior cached result.
5. **Given** the user selects "Skip cache (one-time run)", **When** the wizard completes, **Then** analysis runs fresh but the result is not persisted to cache.

---

### User Story 3 - Whisper Model Selection (Priority: P2)

During the wizard, the user is presented with a list of available Whisper model sizes (tiny, base, small, medium, large) along with a brief description of the speed/accuracy trade-off for each, and can choose which model to use for vocal transcription.

**Why this priority**: Whisper model size is the biggest single factor in phoneme analysis time. Exposing this choice without documentation-digging meaningfully improves the user's ability to tune the analysis for their hardware and time budget.

**Independent Test**: Can be fully tested by selecting a specific model in the wizard and confirming the transcription step uses that model size (observable in progress output or result metadata).

**Acceptance Scenarios**:

1. **Given** the Whisper model selection step is displayed, **When** the user navigates the list, **Then** each model entry shows its name and a one-line trade-off summary (e.g., "tiny — fastest, lower accuracy / large — slowest, highest accuracy").
2. **Given** the user selects a model, **When** analysis runs, **Then** the chosen model size is used for vocal transcription and the model name is recorded in the analysis result metadata.
3. **Given** the user's machine has already downloaded a model, **When** that model appears in the list, **Then** it is marked as "cached locally" so the user knows it will not require a download.

---

### User Story 4 - Parallelized Analysis Execution (Priority: P2)

Independent analysis algorithms run concurrently rather than sequentially, so that algorithms with no dependency on each other's output are dispatched in parallel. The user sees a multi-track progress display showing each algorithm's status simultaneously.

**Why this priority**: The current pipeline is fully sequential even for algorithms that share no data dependencies. Parallelization is the highest-impact technical improvement for wall-clock time reduction.

**Independent Test**: Can be fully tested by timing an analysis run before and after the change on the same song, and verifying that independent algorithms run concurrently as shown in the progress display.

**Acceptance Scenarios**:

1. **Given** a song is analyzed with multiple independent algorithms, **When** analysis runs, **Then** algorithms with no shared dependencies start simultaneously rather than waiting for each other.
2. **Given** an algorithm depends on stem separation output, **When** analysis runs, **Then** that algorithm only starts after stem separation completes (dependency ordering is respected).
3. **Given** analysis is running, **When** the user watches progress, **Then** multiple algorithm names are shown as "running" at the same time, with individual completion status updating as each finishes.
4. **Given** one algorithm fails during parallel execution, **When** the run completes, **Then** the failure is reported clearly without causing other in-flight independent algorithms to abort.

---

### User Story 5 - Optimized Pipeline Dependency Ordering (Priority: P3)

The analysis pipeline is restructured so that work is never redone: audio loading happens once, stem separation is done before any stem-dependent algorithm, and result scoring happens only after all tracks are collected. The ordering is made explicit as a dependency graph.

**Why this priority**: Eliminates wasted computation. Lower priority than parallelization because it is a correctness/efficiency refactor rather than a new capability, but it multiplies the benefit of parallelization by ensuring no step repeats unnecessarily.

**Independent Test**: Can be tested by adding timing instrumentation and confirming audio is loaded exactly once, stems are computed once, and no algorithm runs before its declared dependencies are met.

**Acceptance Scenarios**:

1. **Given** a full analysis run, **When** it completes, **Then** audio loading has occurred exactly once regardless of how many algorithms ran.
2. **Given** a full analysis run with stem separation enabled, **When** it completes, **Then** stem separation has run exactly once and all stem-based algorithms used its output.
3. **Given** the pipeline dependency graph is reviewed, **When** any step is inspected, **Then** its declared inputs and outputs can be traced without ambiguity.

---

### Edge Cases

- What happens when the input audio file does not exist when the wizard launches?
- How does the wizard behave on a terminal that does not support interactive mode (e.g., piped input, CI environment)?
- What happens if stem separation fails mid-run while parallel algorithms that depend on it are waiting?
- What happens if the user's selected Whisper model is not downloaded and the network is unavailable?
- How is cache validity determined if the source audio file has been modified but the path is the same?
- What happens if two parallel algorithms both attempt to write to the same output simultaneously?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a new `wizard` subcommand that launches an interactive guided setup for running analysis on a given audio file.
- **FR-002**: The wizard MUST support keyboard navigation (up/down arrows, Enter to confirm) for all selection screens without requiring the user to type values manually.
- **FR-003**: The wizard MUST display the current cache status for the input file at the cache configuration step, including whether a cache exists, its age, and whether the source file has changed since the cache was created.
- **FR-004**: The wizard MUST offer at least three cache options: use existing cache, regenerate cache, and bypass cache for this run only.
- **FR-005**: The wizard MUST present all available Whisper model sizes with a one-line speed/accuracy description for each, and indicate which models are already downloaded locally.
- **FR-006**: The analysis engine MUST dispatch independent algorithms concurrently so that algorithms with no declared data dependencies run in parallel.
- **FR-007**: The analysis engine MUST enforce dependency ordering: any algorithm that requires stem audio MUST only start after stem separation is complete.
- **FR-008**: Audio loading MUST occur exactly once per analysis run regardless of how many algorithms are executed.
- **FR-009**: Stem separation MUST occur at most once per analysis run; all stem-dependent algorithms MUST share the single stem output.
- **FR-010**: A multi-track progress display MUST be shown during analysis, with each algorithm's real-time status (waiting, running, complete, failed) visible simultaneously.
- **FR-011**: If the wizard is run in a non-interactive terminal (no TTY), it MUST fall back to non-interactive mode using default or flag-supplied values and display a clear notice that interactive mode is unavailable.
- **FR-012**: If a parallel algorithm fails, the failure MUST be reported clearly at completion without aborting other in-flight independent algorithms.
- **FR-013**: The wizard MUST be launchable with a single command (`xlight-analyze wizard <audio-file>`) and MUST require no additional flags to produce a working analysis run.
- **FR-014**: All selections made in the wizard MUST be equivalent to corresponding CLI flags, so that any wizard-configured run can be reproduced directly from the command line.

### Key Entities

- **Wizard Session**: A single guided configuration run for one audio file; holds all user selections before handing off to the analysis engine.
- **Cache Entry**: A persisted analysis result keyed by audio file hash; has an age, a validity state (source hash match or mismatch), and a path on disk.
- **Pipeline Step**: A single unit of work in the analysis pipeline with declared input dependencies and output artifacts.
- **Dependency Graph**: The directed acyclic graph of pipeline steps; determines which steps can run in parallel and which must be sequenced.
- **Whisper Model**: A named model variant with size, local availability status, and speed/accuracy characteristics.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who has never used the tool before can complete a full analysis run using only the wizard, without reading any documentation, within 5 minutes of first launch.
- **SC-002**: Total wall-clock analysis time for a typical 3-5 minute song is reduced by at least 30% compared to the pre-parallelization sequential pipeline on the same machine.
- **SC-003**: Audio loading and stem separation each occur exactly once per run, verified across 100% of runs in the automated test suite.
- **SC-004**: The wizard launches and reaches its first interactive screen in under 2 seconds on any supported machine.
- **SC-005**: 100% of wizard selections are reproducible via direct CLI flags, ensuring no capability is wizard-only.
- **SC-006**: The wizard falls back gracefully to non-interactive mode in 100% of non-TTY environments without crashing or hanging.

---

## Assumptions

- The wizard is a new `wizard` subcommand that co-exists with the existing `analyze` command; the existing command is not modified or removed.
- Whisper model selection applies only when the vocal phoneme analysis algorithm is included in the run; if phoneme analysis is excluded, the Whisper step is skipped in the wizard.
- The dependency graph for parallelization is defined statically (declared in code), not inferred dynamically at runtime.
- Parallel execution is implemented within the existing venv/subprocess architecture; the existing vamp subprocess isolation is preserved and respected as a dependency boundary.
- Cache validity is determined by comparing the MD5 hash of the source audio file, consistent with the existing `source_hash` field in `_analysis.json`.
- "Locally downloaded" Whisper model detection checks for model files in the standard Whisper model cache directory on the user's machine.
- The wizard does not support saving a named configuration profile for repeated use (that is out of scope for this feature).
