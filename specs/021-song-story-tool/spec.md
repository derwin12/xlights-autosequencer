# Feature Specification: Song Story Tool

**Feature Branch**: `021-song-story-tool`
**Created**: 2026-03-30
**Status**: Draft
**Input**: User description: "Song Story Tool — unified song interpretation layer between analysis and sequence generation"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Song Interpretation (Priority: P1)

A user has an MP3 file and wants to understand its musical structure before generating a light show. They run a single command pointing at the audio file, and the system automatically produces a structured interpretation of the song: its sections (intro, verse, chorus, bridge, etc.), the energy and character of each section, which instruments are prominent where, and the dramatic moments that should drive visual events.

**Why this priority**: This is the core value of the feature — replacing scattered, opaque analysis data with a single, coherent narrative of the song. Without automatic interpretation, the user has no starting point.

**Independent Test**: Can be tested by running the tool on any MP3 and verifying the output contains labeled sections, energy profiles, stem activity, and dramatic moments in a structured format.

**Acceptance Scenarios**:

1. **Given** an MP3 file, **When** the user runs the song story command, **Then** the system produces a structured interpretation containing labeled sections (8-15 for a typical 3-5 minute song), global song properties (tempo, key, energy arc), per-section character profiles, and ranked dramatic moments.
2. **Given** an MP3 file that has not been previously analyzed, **When** the user runs the song story command, **Then** the system performs stem separation, per-stem feature extraction, full-mix analysis, section detection, and moment classification — all automatically with no additional user input.
3. **Given** an MP3 file that has already been stem-separated, **When** the user runs the song story command, **Then** the system reuses cached stems and completes faster without re-separating.
4. **Given** the generated interpretation, **When** the user inspects the output, **Then** each section has a role (intro, verse, pre_chorus, chorus, post_chorus, bridge, instrumental_break, climax, ambient_bridge, outro, interlude), an energy level (low/medium/high), energy trajectory (rising/falling/stable/oscillating), texture classification, onset density, and a list of active stems with relative levels.

---

### User Story 2 - Interactive Song Story Review (Priority: P2)

After the automatic interpretation is generated, the user wants to review and correct it before it drives sequence generation. They open a browser-based review interface that shows the song's waveform, section blocks on a timeline, stem activity visualizations, and dramatic moments. They can play the audio and see section details update as the playhead moves. For each section, the user sees not just the role label but the full musical picture: which stems are active and at what levels, drum patterns (kick/snare/hihat breakdown), any solo regions, which stem is leading, kick-bass tightness, chord changes, and leader transitions within the section.

**Why this priority**: The automatic classification will sometimes be wrong. Users need the ability to override decisions before they cascade into a full light show. This is the "human in the loop" that prevents bad interpretations from producing bad sequences. Seeing the rich per-stem detail helps users understand WHY the system classified a section the way it did.

**Independent Test**: Can be tested by loading a song story file and verifying the review interface displays all sections, allows audio playback with synchronized timeline, renders stem activity curves, and shows per-stem detail (drum patterns, solos, leader stem, tightness, chords) for each section.

**Acceptance Scenarios**:

1. **Given** a song story file, **When** the user opens the review interface, **Then** they see a waveform timeline with labeled section blocks, audio playback controls, and a detail panel for the current section.
2. **Given** the review interface is open and audio is playing, **When** the playhead enters a new section, **Then** the current section panel updates to show that section's role, energy, texture, stem activity levels, drum pattern summary, solo regions, leader stem, kick-bass tightness, chord changes, and lighting recommendations.
3. **Given** the review interface, **When** the user clicks a section on the timeline, **Then** playback jumps to that section and the detail panel updates.
4. **Given** a section with a guitar solo, **When** the user views the section detail, **Then** the solo region is highlighted with its stem name, time range, and prominence score.

---

### User Story 3 - Section Editing in Review (Priority: P2)

During review, the user realizes the classifier labeled a pre-chorus as a verse, or that two sections should really be one. They want to rename section roles, adjust section boundaries, merge adjacent sections, split sections at a specific timestamp, and override energy classifications — all from the review interface.

**Why this priority**: Section roles directly determine which visual tiers activate, brightness ceilings, and theme layer modes downstream. Incorrect classifications produce visually wrong light shows. Editing is essential for quality.

**Independent Test**: Can be tested by modifying sections in the review UI and verifying the changes persist in the exported file with correct re-profiling of affected sections.

**Acceptance Scenarios**:

1. **Given** a section labeled "verse", **When** the user changes its role to "pre_chorus", **Then** the lighting recommendations for that section update automatically (active tiers, brightness ceiling, theme layer mode) and the override is recorded.
2. **Given** two adjacent sections, **When** the user merges them, **Then** a single section is created with re-profiled energy, texture, and stem data spanning the combined time range, and moments are re-bucketed.
3. **Given** a section, **When** the user splits it at the current playhead position, **Then** two new sections are created, each independently profiled, with moments assigned to the appropriate new section.
4. **Given** a section boundary, **When** the user drags it to adjust timing, **Then** both adjacent sections are re-profiled and moments near the boundary are re-assigned as needed.

---

### User Story 4 - Dramatic Moment Curation (Priority: P3)

The user wants to see which moments the system identified as dramatically significant (energy surges, drops, percussive impacts, vocal entries, silences, etc.) and dismiss any they don't want to trigger visual events. They also want to flag specific sections as "the moment" of the song.

**Why this priority**: Dramatic moments drive event-triggered effects in the light show. Too many false positives create visual noise; missed moments leave the show feeling flat. User curation is the quality filter.

**Independent Test**: Can be tested by dismissing moments in the review UI and verifying dismissed moments are excluded from the exported file's active moment list.

**Acceptance Scenarios**:

1. **Given** the review interface showing a section, **When** the user views the moments panel, **Then** they see each moment's timestamp, type, source stem, intensity, and temporal pattern (isolated, double_tap, plateau, cascade, scattered).
2. **Given** a dramatic moment, **When** the user dismisses it, **Then** that moment is marked as dismissed and will not trigger effects in downstream generation.
3. **Given** a section, **When** the user toggles the "Highlight" flag, **Then** that section is marked as the user-designated peak moment of the song.

---

### User Story 5 - Export and Downstream Consumption (Priority: P1)

The user finishes reviewing (or accepts the draft as-is) and exports the song story. The exported file becomes the single source of truth for the sequence generator. The generator reads section roles, lighting guidance, dramatic moments, and stem curves directly from this file — it never re-derives energy scores or section classifications.

**Why this priority**: The entire point of the song story is to provide a clean contract between interpretation and generation. If the output isn't consumable downstream, the feature has no value.

**Independent Test**: Can be tested by feeding an exported song story into the sequence generator and verifying it uses the story's section roles, energy scores, lighting guidance, and moment data without re-analysis.

**Acceptance Scenarios**:

1. **Given** a reviewed song story, **When** it is exported, **Then** the output file contains the review status as "reviewed", a timestamp, and any reviewer notes.
2. **Given** the review interface with unsaved edits, **When** the user clicks Save, **Then** in-progress changes are persisted to a separate edits file (`_story_edits.json`), keeping the base story file unmodified. Review status remains "draft" until Export merges base + edits into `_story_reviewed.json`.
3. **Given** a song story (reviewed or draft), **When** the sequence generator reads it, **Then** it uses section roles, lighting tier recommendations, brightness ceilings, theme layer modes, moment patterns, and stem curves directly from the file.
4. **Given** a section with user overrides, **When** the generator processes it, **Then** the overrides take precedence over the computed values.
5. **Given** a song story with stem curves, **When** the generator builds value curves, **Then** it can bind per-stem continuous data (e.g., bass energy to fire height, vocal energy to wash brightness) directly from the story.

---

### User Story 7 - Creative Preferences (Priority: P2)

During review, the user wants to express creative direction — not just correct what the system got wrong, but steer what the light show should feel like. They can set song-wide preferences (global mood, theme lock, focus stem, visual intensity, occasion) and per-section overrides (theme, focus stem, mood, intensity) that guide downstream generation.

**Why this priority**: The automatic pipeline produces a technically correct interpretation, but it can't know the user's creative intent. A user staging a Christmas show wants different themes than someone doing a Halloween display. A user who knows the guitar solo is the highlight wants to focus visual emphasis there. These preferences are the bridge between analysis and artistic vision.

**Independent Test**: Can be tested by setting a focus stem on a section, exporting, and verifying the exported story contains the preference. Then feeding into the generator and verifying the focus stem's house zone gets boosted brightness/tier priority.

**Acceptance Scenarios**:

1. **Given** the review interface, **When** the user sets a song-wide mood to "ethereal", **Then** all sections without a per-section mood override use ethereal theme selection.
2. **Given** the review interface, **When** the user sets a per-section theme override to "Inferno" on the chorus, **Then** the chorus uses the Inferno theme regardless of its auto-derived mood.
3. **Given** a section where guitar is soloing, **When** the user sets focus_stem to "guitar", **Then** the generator boosts the house zone associated with guitar (arches/sides) with higher brightness and tier priority.
4. **Given** the review interface, **When** the user adjusts visual intensity to 0.5 on a section, **Then** the exported brightness_ceiling for that section is halved.
5. **Given** song-wide preferences set to occasion="christmas", **When** the generator selects themes, **Then** it filters to Christmas-appropriate themes (Winter Wonderland, Candy Cane Chase, etc.).
6. **Given** a per-section focus_stem override and a song-wide focus_stem preference, **When** the generator processes that section, **Then** the per-section override takes precedence.

---

### User Story 6 - Quick Pipeline Mode (Priority: P3)

The user wants a streamlined workflow where a single command generates the song story and immediately opens the review interface, so they don't have to run two separate commands.

**Why this priority**: Convenience feature that improves workflow. The core functionality works without it.

**Independent Test**: Can be tested by running the combined command and verifying both generation and review launch occur in sequence.

**Acceptance Scenarios**:

1. **Given** an MP3 file, **When** the user runs the story command with a review flag, **Then** the system generates the story and automatically opens the review interface in the browser.

---

### Edge Cases

- What happens when the audio file is very short (<30 seconds) and produces fewer than 8 sections? The system should produce as many sections as are musically meaningful, without forcing artificial splits to meet a minimum count.
- What happens when stems cannot be separated (e.g., corrupted audio, unsupported format)? The system should fall back to full-mix-only analysis and indicate that per-stem data is unavailable.
- What happens when no vocals are detected in the entire song (instrumental music)? Section classification should rely on energy, texture, and repetition signals rather than vocal activity.
- What happens when the user edits sections such that they overlap or leave gaps? The interface should prevent overlaps and gaps — section boundaries must be contiguous.
- What happens when a song has a very unstable tempo (live recording, rubato)? The system should report tempo stability as "free" and adapt beat-sync recommendations accordingly.
- What happens when the user dismisses all moments in a section? The section should still be valid for generation but will produce no event-triggered effects.
- What happens when the user re-runs story generation on a file that already has a song story? The system warns and requires explicit confirmation before overwriting, particularly if the existing story has been reviewed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically produce a structured song interpretation from a single audio file input, with no additional user configuration required.
- **FR-002**: System MUST identify and label 8-15 musically meaningful sections for a typical 3-5 minute song, with roles (intro, verse, pre_chorus, chorus, post_chorus, bridge, instrumental_break, climax, ambient_bridge, outro, interlude).
- **FR-003**: System MUST detect and classify dramatic moments by type (energy_surge, energy_drop, percussive_impact, brightness_spike, tempo_change, silence, vocal_entry, vocal_exit, texture_shift, handoff) and temporal pattern (isolated, plateau, cascade, double_tap, scattered).
- **FR-004**: System MUST rank dramatic moments by importance, retaining the top 20-30 for a typical song.
- **FR-005**: System MUST produce per-section character profiles including energy level, energy trajectory, texture, onset density, spectral brightness, dominant stem, per-stem activity levels, per-stem onset counts, drum pattern breakdown (kick/snare/hihat counts and style), solo regions, leader stem and leader transitions, kick-bass tightness, melodic handoffs, and chord changes — all derived from the existing analysis pipeline's per-stem data.
- **FR-006**: System MUST produce per-section lighting guidance including recommended active tiers, brightness ceiling, theme layer mode, transition style, and beat effect density.
- **FR-007**: System MUST detect global song properties: tempo (with stability classification), key, energy arc shape, vocal coverage, harmonic/percussive ratio, and available stems.
- **FR-008**: System MUST provide continuous per-stem data curves at a fixed 2Hz sample rate (0.5-second intervals) for downstream value curve binding.
- **FR-009**: System MUST provide a browser-based review interface for viewing and editing the song interpretation with synchronized audio playback.
- **FR-010**: The review interface MUST allow users to: rename section roles, adjust section boundaries, merge adjacent sections, split sections at a timestamp, override energy classifications, dismiss dramatic moments, add free-text notes, and flag highlight sections.
- **FR-019**: The review interface MUST provide a Save button that persists user edits to a separate edits file (`_story_edits.json`), keeping the base auto-generated story file (`_story.json`) unmodified. Export merges base + edits into a final reviewed file (`_story_reviewed.json`) with review status "reviewed".
- **FR-011**: When a user edits sections (rename, split, merge, boundary adjust), the system MUST automatically re-profile affected sections (energy, texture, stems) and re-assign moments.
- **FR-012**: System MUST export the interpretation as a structured file that serves as the single source of truth for downstream sequence generation.
- **FR-013**: The exported file MUST include a review status indicating whether a human reviewed it or it is an unreviewed draft.
- **FR-014**: User overrides from the review phase MUST take precedence over computed values in downstream consumption.
- **FR-015**: System MUST reuse previously cached stem separations to avoid redundant processing.
- **FR-020**: If a song story already exists for the given audio file, the system MUST warn the user and require explicit confirmation (e.g., a force flag) before overwriting — especially if the existing story has been reviewed.
- **FR-021**: During story generation, the system MUST display step-by-step progress indicating the current pipeline stage (stem separation, feature extraction, section detection, moment classification, etc.).
- **FR-016**: System MUST classify the overall energy arc shape (ramp, arch, flat, valley, sawtooth, bookend) based on energy sampling across the song duration.
- **FR-017**: Section merging MUST enforce a minimum section duration of 4 seconds, merging shorter sections with the most similar neighbor.
- **FR-018**: Section classification MUST use a multi-signal approach: vocal activity (primary), relative energy (secondary), and melodic repetition (tertiary).
- **FR-022**: The review interface MUST allow users to set song-wide creative preferences: mood override, theme lock, focus stem, visual intensity scaler, occasion, and genre.
- **FR-023**: The review interface MUST allow users to set per-section creative overrides: theme, focus stem, mood, and visual intensity — each overriding the song-wide preference for that section.
- **FR-024**: Per-section overrides MUST take precedence over song-wide preferences, which MUST take precedence over auto-derived values (three-level precedence chain).
- **FR-025**: The generator MUST respect the focus_stem preference by boosting the visual weight (brightness, tier priority) of the house zone associated with the focused stem.
- **FR-026**: The generator MUST respect mood and theme overrides by selecting themes from the appropriate pool or using the forced theme directly.
- **FR-027**: The system MUST store user edits in a separate file (`_story_edits.json`) from the auto-generated base story (`_story.json`), so the diff between auto-generated and user-corrected data is preserved for algorithm feedback.
- **FR-028**: When the base story is re-generated (e.g., after algorithm updates), the edits file MUST be preserved. The review UI SHOULD offer to re-apply previous edits to the new base.
- **FR-029**: The generator MUST consume the merged reviewed file (`_story_reviewed.json`) when available, falling back to the base story file when no reviewed version exists.

### Key Entities

- **Song Story**: The complete interpretation of a song, identified by the MD5 hash of the audio file content (consistent with existing stem and analysis caches). Contains global properties, user creative preferences, an ordered list of sections, a ranked list of dramatic moments, continuous stem curves, and review state. One song story per audio file.
- **Preferences**: Song-wide creative direction set by the user: mood override, theme lock, focus stem, visual intensity, occasion, genre. These are defaults that per-section overrides can supersede.
- **Section**: A musically meaningful segment of the song with a role, time boundaries, character profile (energy, texture, stem activity), lighting guidance, and optional user overrides. Sections are contiguous and non-overlapping.
- **Dramatic Moment**: A point in time where something musically significant occurs, classified by type, source stem, temporal pattern, and ranked by importance. Moments belong to sections and can be dismissed by the user.
- **Stem Curves**: Continuous per-stem signal data sampled at a fixed 2Hz rate (0.5-second intervals), used for binding to effect parameters downstream. Covers all separated stems plus the full mix.
- **Review State**: Tracks whether the song story has been reviewed by a human, including timestamp and optional reviewer notes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from an MP3 file to a complete song interpretation in a single command, with no intermediate manual steps.
- **SC-002**: The automatic section classifier correctly identifies at least 70% of section roles (matching human judgment) across a diverse set of songs.
- **SC-003**: Users can complete a full review session (inspecting all sections, making edits, exporting) in under 10 minutes for a typical 3-5 minute song.
- **SC-004**: The song story replaces all existing interpretation logic in the generator — the generator reads section roles, energy scores, lighting guidance, and moments exclusively from the song story, with zero re-derivation of these values.
- **SC-005**: For at least 2 out of 3 test songs, the reviewed song story corrects at least one section role or dismisses at least one false-positive moment, producing a different (corrected) sequence output compared to the unreviewed draft.
- **SC-006**: The review interface displays all song data (sections, stems, moments) synchronized to audio playback with no perceptible lag between the playhead and visual updates.
- **SC-007**: Section edits (rename, split, merge, boundary adjust) complete within 2 seconds, including re-profiling of affected sections.
- **SC-008**: The system reuses cached stems, reducing repeat analysis time by at least 50% compared to a fresh run.

## Clarifications

### Session 2026-03-30

- Q: How is a song story identified/keyed for caching and re-generation? → A: MD5 hash of audio file content (matches existing stem/analysis cache pattern).
- Q: How are in-progress review edits persisted? → A: Two-file architecture. Save writes user edits to a separate `_story_edits.json` file, keeping the base `_story.json` unmodified. Export merges base + edits into `_story_reviewed.json`. This preserves the diff for algorithm feedback.
- Q: What happens when re-running story generation for an audio file that already has a song story? → A: Warn and require confirmation; if an existing story is found (especially if reviewed), warn the user and require an explicit flag to overwrite.
- Q: What feedback does the user see during story generation? → A: Step-by-step progress showing the current pipeline stage (e.g., "Separating stems... Extracting features... Detecting sections...").
- Q: What sample rate should stem curves use? → A: Fixed at 2Hz (0.5s intervals) — sufficient for lighting effect parameter binding, keeps file sizes small.

## Assumptions

- Stem separation via the existing demucs integration is available and produces 6 stems (drums, bass, vocals, guitar, piano, other).
- The existing analysis cache and stem cache infrastructure can be reused.
- The existing Flask-based review server pattern (from the timing track review UI) can be extended for the song story review interface.
- Users have a modern web browser capable of Web Audio and Canvas 2D rendering.
- The sequence generator will be updated to consume song story files as its primary input, replacing the current direct-from-analysis pipeline.

## Dependencies

- Existing stem separation pipeline (feature 008)
- Existing per-stem and full-mix feature extraction algorithms
- Existing analysis cache infrastructure (feature 010)
- Theme and effect libraries (features 018, 019) for lighting guidance mapping
- Sequence generator (feature 020) must be updated to consume the song story format

## Scope Boundaries

**In Scope**:
- Automatic song interpretation (sections, moments, energy, stems, lighting guidance)
- Browser-based interactive review interface
- Export as structured file for downstream consumption
- Stem curve data for value curve binding

**Out of Scope**:
- Changes to the theme system or effect catalog
- XSQ file generation (handled by the sequence generator)
- Beat/bar grid data (the generator accesses beat times separately from the analysis cache)
- Multi-song batch processing
- Collaborative review (single user at a time)
