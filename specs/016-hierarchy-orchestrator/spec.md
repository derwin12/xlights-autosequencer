# Feature Specification: Hierarchy Orchestrator

**Feature Branch**: `016-hierarchy-orchestrator`
**Created**: 2026-03-25
**Status**: Draft
**Input**: User description: "Zero-flag orchestrator pipeline that replaces the current 14-flag analyze command. Drop an MP3, get a complete hierarchical analysis organized by 7 levels. Auto-detects capabilities, runs only needed algorithms, picks one best per level, outputs structured HierarchyResult."

## Clarifications

### Session 2026-03-25

- Q: Should the new orchestrator replace the existing `analyze` command or coexist alongside it? → A: Replace — new orchestrator becomes the `analyze` command. Old AnalysisResult format is retired. Review UI updated to read HierarchyResult.
- Q: Should stem separation auto-run when demucs is available, or be opt-in with a flag? → A: Always auto-run stems if demucs is installed. True zero-flag — no opt-in flag needed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Single-File Analysis (Priority: P1)

A user has an MP3 file they want to sequence lights for. They run a single command with no configuration and receive a complete, organized analysis of the song's musical structure — sections, beats, energy dynamics, and instrument events — ready to feed into the lighting pipeline.

**Why this priority**: This is the core value proposition. If this doesn't work, nothing else matters. Every downstream feature (grouping, theme selection, .xsq generation) depends on this output.

**Independent Test**: Can be fully tested by running the command on any MP3 and verifying that the output JSON contains all 7 hierarchy levels with valid data. Delivers immediate value — a complete song analysis with zero setup.

**Acceptance Scenarios**:

1. **Given** an MP3 file on disk, **When** the user runs `xlight-analyze song.mp3`, **Then** the system produces a structured analysis file organized by hierarchy level (L0–L6) in a song-named output folder.
2. **Given** an MP3 file and no additional flags, **When** the analysis runs, **Then** the system auto-detects which analysis tools are installed and runs every available algorithm relevant to each hierarchy level.
3. **Given** an MP3 file, **When** the analysis completes, **Then** each hierarchy level that requires a "best" selection (beats, bars) contains exactly one result, chosen automatically.
4. **Given** an MP3 file that was previously analyzed, **When** the user runs the command again, **Then** the cached result is returned immediately without re-running analysis.
5. **Given** an MP3 file that was previously analyzed but has since been modified, **When** the user runs the command again, **Then** the analysis is re-run automatically.

---

### User Story 2 — Graceful Degradation (Priority: P1)

A user has a minimal installation — perhaps only librosa is available, without Vamp plugins, madmom, or demucs. The system still produces useful output for every hierarchy level it can, and clearly reports what was skipped and why.

**Why this priority**: Co-equal with Story 1. Users should never hit an error because a dependency is missing. The system must always produce something useful.

**Independent Test**: Can be tested by temporarily renaming or uninstalling Vamp plugin files and verifying the system still produces beats, bars, and onsets from librosa alone, with warnings noting what was unavailable.

**Acceptance Scenarios**:

1. **Given** a system with only librosa installed (no Vamp, no madmom, no demucs), **When** analysis runs, **Then** the output includes L2 (bars), L3 (beats), and L4 (onsets) from librosa, and L0/L1/L5/L6 are marked as unavailable with a clear reason.
2. **Given** a system with Vamp but no demucs, **When** analysis runs, **Then** all hierarchy levels are populated using full-mix analysis, and L4 events contain a single full-mix onset track instead of per-stem tracks.
3. **Given** any missing capability, **When** analysis completes, **Then** the output metadata includes a capabilities map showing what was available and what was skipped, plus human-readable warnings.

---

### User Story 3 — Structured Output for Downstream Pipeline (Priority: P1)

The lighting pipeline (grouping, theme selection, .xsq generation) needs analysis output organized by purpose, not as a flat list of scored tracks. The output must clearly separate timing events (beats, onsets) from continuous value curves (energy, spectral flux) and labeled segments (sections, chords).

**Why this priority**: Co-equal with Stories 1 and 2. The entire reason for this feature is to produce output that maps directly to the grouping tiers and effect themes. A flat list is what we have today and it doesn't work.

**Independent Test**: Can be tested by loading the output JSON and verifying that beats, sections, energy curves, and chord changes are in separate, typed fields — not mixed in a single array.

**Acceptance Scenarios**:

1. **Given** a completed analysis, **When** the output is read, **Then** timing events (beats, bars, onsets) are stored as lists of timestamped marks, value curves (energy, spectral flux) are stored as frame-rate-aligned value arrays (0–100), and labeled segments (sections, chords) include their labels and durations.
2. **Given** a completed analysis with stems, **When** the output is read, **Then** energy curves and onset events are keyed by stem name (drums, bass, vocals, other), not by algorithm name.
3. **Given** a completed analysis, **When** the output is read, **Then** derived features (energy impacts, gaps/silence) are present as pre-computed lists — the downstream pipeline does not need to re-derive them from raw curves.

---

### User Story 4 — Batch Directory Processing (Priority: P2)

A user has a folder of 20+ MP3s for a holiday show. They point the tool at the directory and all songs are analyzed sequentially, each producing its own output folder.

**Why this priority**: Important for real-world usage but not architecturally different from single-file analysis. Built on top of Story 1.

**Independent Test**: Can be tested by pointing the command at a directory of 3+ MP3s and verifying each gets its own output folder with a complete hierarchy result.

**Acceptance Scenarios**:

1. **Given** a directory containing MP3 files, **When** the user runs `xlight-analyze /path/to/mp3s/`, **Then** each MP3 is analyzed and results are written to per-song subfolders.
2. **Given** a directory where some songs have cached results, **When** batch analysis runs, **Then** cached songs are skipped and only new/modified songs are analyzed.
3. **Given** a batch run where one song fails, **When** processing continues, **Then** remaining songs are still analyzed and the failure is reported in a summary.

---

### User Story 5 — Timing Export for xLights (Priority: P2)

The analysis produces an xLights-compatible .xtiming file alongside the JSON, so users can import timing marks (beats, bars, sections) directly into xLights.

**Why this priority**: High user value but depends on Stories 1 and 3 being complete. The JSON is the primary output; the .xtiming is a convenience for immediate xLights use.

**Independent Test**: Can be tested by importing the generated .xtiming file into xLights and verifying timing marks load correctly.

**Acceptance Scenarios**:

1. **Given** a completed analysis, **When** the output folder is examined, **Then** it contains an .xtiming file with timing marks for beats, bars, sections, and onset events.
2. **Given** a generated .xtiming file, **When** imported into xLights, **Then** timing marks appear correctly aligned with the audio.

---

### Edge Cases

- What happens when the MP3 is very short (<30 seconds)? System should still produce beats/bars/onsets but warn that structural analysis (L1) may be unreliable.
- What happens when the MP3 is corrupt or unreadable? System should report a clear error and exit cleanly.
- What happens when no analysis tools are installed at all? System should report which tools are needed and how to install them.
- What happens when the output directory is read-only? System should fail with a clear error before starting analysis.
- What happens when a song has no detectable beat (ambient music)? System should produce whatever levels it can and mark beat/bar levels as low-confidence.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a single MP3 file path as its only required input and produce a complete hierarchical analysis with no additional configuration. This replaces the existing `analyze` command — the old command and its AnalysisResult format are retired.
- **FR-002**: System MUST auto-detect installed analysis capabilities (Vamp plugins, madmom, demucs, whisperx) at startup and adapt its algorithm selection accordingly.
- **FR-003**: System MUST organize analysis output into 7 hierarchy levels: L0 Special Moments, L1 Structure, L2 Bars, L3 Beats, L4 Instrument Events, L5 Energy Curves, L6 Harmony.
- **FR-004**: System MUST select one best result per hierarchy level for levels that run multiple competing algorithms (L2 Bars, L3 Beats), rather than outputting all candidates.
- **FR-005**: System MUST distinguish between timing events (discrete timestamps), value curves (continuous frame-rate data), and labeled segments (timestamps with labels and durations) in its data model.
- **FR-006**: System MUST preserve segment labels (A, B, N1) from structural analysis and chord names (Am, G) from harmonic analysis in the output.
- **FR-007**: System MUST derive energy impacts (sudden loudness changes) and gaps (silence) from the energy curve and include them as pre-computed features in L0.
- **FR-008**: System MUST automatically run stem separation when demucs is installed, and run per-stem analysis on the resulting stems, producing per-stem onset events (L4) and per-stem energy curves (L5). No flag is required — stems are always used when available.
- **FR-009**: System MUST cache analysis results keyed by file content hash and return cached results when the source file has not changed.
- **FR-010**: System MUST produce an xLights-compatible .xtiming file for timing marks (beats, bars, sections, events) alongside the structured JSON output. Value curve export (.xvc) is deferred to a separate feature where per-section slicing and xLights size limits can be handled properly.
- **FR-011**: System MUST accept a directory path and batch-process all MP3 files within it, producing per-song output folders.
- **FR-012**: System MUST degrade gracefully when capabilities are missing — producing partial results from available tools rather than failing entirely.
- **FR-013**: System MUST report capabilities detected, algorithms run, and any warnings in the output metadata.
- **FR-014**: System MUST run stem interaction analysis (leader election, tightness, sidechaining, handoffs) when multiple stems are available and include results in the output.

### Key Entities

- **HierarchyResult**: The structured output of a complete analysis — contains one field per hierarchy level plus metadata, interactions, and warnings.
- **ValueCurve**: A continuous, frame-rate-aligned sequence of 0–100 integer values representing an audio feature over time (e.g., energy, spectral flux). Distinguished from timing marks.
- **TimingMark**: A discrete timestamp with optional label (for segments, chords) and optional duration (for segments). The atomic unit of timing event data.
- **TimingTrack**: A named, ordered sequence of TimingMarks produced by one algorithm for one purpose. Carries its stem source.
- **Capabilities**: A map of which analysis tools are available on this system, used to determine algorithm selection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can analyze any MP3 by providing only the file path — no flags, no configuration files, no environment variables required.
- **SC-002**: Analysis of a 3-minute MP3 completes in under 5 minutes on a modern laptop (including automatic stem separation when demucs is available). Without demucs, completes in under 60 seconds.
- **SC-003**: Output contains valid data for at least 4 of 7 hierarchy levels on any system with at least librosa installed.
- **SC-004**: The output JSON can be loaded and every hierarchy level accessed by field name without parsing or filtering a flat list.
- **SC-005**: Repeated analysis of the same unmodified file returns cached results in under 2 seconds.
- **SC-006**: Batch processing of 20 MP3 files completes without manual intervention, even if individual songs fail.
- **SC-007**: Generated .xtiming files import successfully into xLights without modification.
- **SC-008**: The system produces correct output when run with only librosa (no Vamp, no madmom, no demucs) — graceful degradation verified.

## Assumptions

- The existing 36 algorithm implementations are correct and do not need modification beyond preserving data that is currently dropped on serialization (energy values, segment labels, chord names).
- Stem separation via demucs is the most time-consuming step; when unavailable, the pipeline is significantly faster.
- The "best-of" selection for beats and bars can be determined algorithmically (interval regularity, onset correlation) without user input.
- The output folder structure (song_name/ with subfolders) is acceptable for all users.
- The existing conditioning pipeline (downsample, smooth, normalize) is correct and reusable.
- The existing .xtiming export code is correct and reusable.

## Scope Boundaries

**In scope**:
- New orchestrator pipeline with capability detection and hierarchy-aware output, replacing the existing `analyze` command
- Data model updates (ValueCurve type, TimingMark label/duration fields, HierarchyResult replacing AnalysisResult)
- Fixes to algorithms that currently drop data (bbc_energy values, segmentino labels, chordino chord names)
- New CLI entry point (single-argument, zero required flags, automatic stem separation)
- Update review UI to read HierarchyResult format
- Batch directory processing
- Cache integration

**Out of scope**:
- Value curve export (.xvc files) — deferred to a separate feature where per-section slicing and xLights size limits can be addressed
- xLights layout parsing or power group generation (separate feature)
- Effect theme selection or .xsq sequence generation (separate feature)
- Vocal-based segmentation (documented as future enhancement)
- Parameter sweep tooling (research tool, remains available but not part of this pipeline)
- Review UI changes
