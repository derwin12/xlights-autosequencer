# Feature Specification: Song Library Sequence Generation

**Feature Branch**: `034-library-sequence-gen`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: "Can we add a sequence generation option to the details in the song library?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Generate a Sequence from the Song Library (Priority: P1)

A user has an analyzed song in the library and wants to produce an xLights sequence file (.xsq) without leaving the browser. They open the song's detail panel, configure basic generation options (genre, occasion, transition style), and trigger generation. The system uses the already-configured layout groups (set up once in the grouper) and the sequence file downloads automatically when complete.

**Why this priority**: This is the core value — moving sequence generation from a CLI-only workflow into the review UI so users never have to open a terminal. Layout groups are configured once per installation in the grouper; generation just uses them.

**Independent Test**: A user with an analyzed song and configured layout groups can open the song's detail panel, click Generate, and receive a downloadable .xsq file with no CLI involvement.

**Acceptance Scenarios**:

1. **Given** a song with a completed analysis and configured layout groups, **When** the user opens its detail panel, **Then** a "Generate Sequence" section is visible with a Generate button and generation option controls.
2. **Given** the user clicks Generate, **When** generation completes successfully, **Then** the .xsq file is offered as a download.
3. **Given** generation is in progress, **When** the user views the detail panel, **Then** a progress indicator is shown and the Generate button is disabled to prevent duplicate submissions.
4. **Given** generation fails (e.g., no layout groups have been configured), **When** the error occurs, **Then** the user sees a human-readable error message and a link to the grouper to set up layout groups.
5. **Given** a song has never been analyzed, **When** the user views its detail panel, **Then** the Generate section is shown as disabled with an explanation that analysis must run first.

---

### User Story 2 — Configure Generation Options (Priority: P2)

Before generating, a user wants to control the key options that shape the sequence: genre, occasion (general / christmas / halloween), and transition style. These should be pre-populated from any available song metadata, with sensible defaults for anything unknown.

**Why this priority**: Genre and occasion are the most impactful choices for theme selection — without them, all sequences use the same defaults regardless of the song.

**Independent Test**: The generation form shows genre, occasion, and transition mode controls pre-populated from song metadata where available. Changing them and generating produces a sequence that reflects those choices.

**Acceptance Scenarios**:

1. **Given** a song has genre metadata, **When** the detail panel opens, **Then** the genre field is pre-populated with the detected value.
2. **Given** the user changes the occasion to "christmas" and generates, **When** the sequence is produced, **Then** the downloaded .xsq uses christmas-appropriate themes.
3. **Given** no options are changed, **When** the user clicks Generate, **Then** generation uses sensible defaults (genre: auto-detected or "any", occasion: "general", transitions: "subtle").

---

### User Story 3 — View and Re-download Past Generations (Priority: P3)

A user has generated sequences for the same song with different options and wants to re-download a prior result without regenerating.

**Why this priority**: Useful for repeat users but not required for the core workflow. Can be added once P1 and P2 are stable.

**Independent Test**: After generating a sequence, the detail panel shows a history entry with a timestamp and re-download link that remains valid for the duration of the server session.

**Acceptance Scenarios**:

1. **Given** a sequence has been generated for a song, **When** the user revisits the detail panel in the same session, **Then** the result is listed with a timestamp and a re-download link.
2. **Given** multiple sequences exist for a song, **When** the user views the history, **Then** entries are sorted newest-first and show the options used (genre, occasion).

---

### Edge Cases

- What if no layout groups have been configured? The Generate section shows a clear message directing the user to set up groups in the grouper first.
- What if the song analysis is incomplete or corrupted? Generation fails early with a message directing the user to re-analyze.
- What if the user navigates away mid-generation? Generation continues server-side; the user can return to the library to find the result and download it.
- What if no themes match the selected genre/occasion combination? Generation falls back to general themes and shows a notice that defaults were used.
- What if a song has never been analyzed? The Generate section is disabled with an explanation that analysis must be run first.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The song library detail panel MUST include a "Generate Sequence" section for every song.
- **FR-002**: The Generate section MUST be disabled with an explanatory message for songs that have not yet been analyzed.
- **FR-003**: If no layout groups have been configured, the Generate section MUST show a message explaining the prerequisite and link to the grouper setup.
- **FR-004**: The generation form MUST provide controls for genre, occasion, and transition style, pre-populated with detected values from song metadata where available.
- **FR-005**: The system MUST use the existing configured layout groups for generation — no layout file upload is required per song or per generation.
- **FR-006**: The system MUST show a progress indicator while generation is running and prevent duplicate submissions.
- **FR-007**: On successful completion, the system MUST deliver the generated .xsq file as a browser download.
- **FR-008**: The system MUST display a human-readable error message if generation fails, without exposing raw internal error details.
- **FR-009**: The system MUST keep the generated file available for download if the user navigates away and returns within the same server session.
- **FR-010** *(P3)*: The detail panel SHOULD display a list of previously generated sequences for the song with timestamps and re-download links.

### Key Entities

- **GenerationRequest**: A single sequence generation run — linked to a song (by analysis hash), the configured layout groups, genre, occasion, transition mode, and status (pending / running / complete / failed).
- **GeneratedSequence**: The output artifact — an .xsq file associated with a completed GenerationRequest, available for download.
- **LayoutGroups**: The installation-wide power group configuration set up once in the grouper, shared across all song generations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with configured layout groups can go from clicking "Generate Sequence" to downloading a valid .xsq file without opening a terminal.
- **SC-002**: Generation completes and the download begins within 60 seconds for a typical 3-minute song.
- **SC-003**: 100% of generation errors surface a user-readable message — no raw error output is shown to users.
- **SC-004**: Users with no layout groups configured are clearly directed to the grouper setup before they can generate — zero silent failures.
- **SC-005**: A previously generated sequence remains downloadable for the duration of the server session without requiring regeneration.

## Assumptions

- Layout groups are configured once per installation using the existing grouper UI and persisted server-side; generation reads them directly without any per-song or per-generation upload.
- The existing generation pipeline (`build_plan` / `write_xsq`) is reused server-side without modification; this feature adds a web front-end to it.
- Generation runs as a synchronous or simple background server-side process; no external queue infrastructure is required.
- Generated .xsq files are held in temporary server-side storage long enough to be downloaded but are not permanently archived.
- The song must have a completed hierarchy analysis to generate.

## Clarifications

### Session 2026-04-09

- Q: Should layout files be uploaded per-generation? → A: No. Layout group configuration is a one-time per-installation setup done in the grouper. Generation uses the already-configured groups with no per-song or per-generation layout upload.
