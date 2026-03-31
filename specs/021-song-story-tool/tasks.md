# Tasks: Song Story Tool

**Input**: Design documents from `/specs/021-song-story-tool/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included per constitution principle IV (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create the song story module structure and shared data classes.

- [X] T001 Create song story module directory and __init__.py at src/story/__init__.py
- [X] T002 Create data classes (SongStory, Section, SectionCharacter, SectionStems, SectionLighting, SectionOverrides, Moment, StemCurves, ReviewState, GlobalProperties, SongIdentity, Preferences, DrumPattern, SoloRegion, LeaderTransition, HandoffEvent, ChordChange, BandEnergy) in src/story/models.py per data-model.md
- [X] T003 [P] Create test fixture: a minimal HierarchyResult dict with sections, energy_curves, energy_impacts, energy_drops, stems_available, beats, and essentia_features for use across all unit tests in tests/fixtures/story_fixture.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core computation modules that ALL user stories depend on. Each module is a pure function with no side effects.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Write failing tests for section merger (minimum duration enforcement, same-role merge, vocal continuity merge, target count 8-15) in tests/unit/test_section_merger.py
- [X] T005 [P] Write failing tests for section classifier (vocal-based role assignment, energy-based chorus/verse distinction, MFCC repetition detection, climax override; include a test case with zero vocal activity for instrumental music fallback) in tests/unit/test_section_classifier.py
- [X] T006 [P] Write failing tests for section profiler (energy_level thresholds, energy_peak, energy_variance, energy_trajectory detection, texture classification, spectral_brightness + centroid_hz + flatness, local_tempo_bpm, dominant_note, frequency_bands breakdown, dominant stem, active stems, stem_levels normalization, per-stem onset counts, drum pattern extraction with kick/snare/hihat breakdown and style classification, solo region filtering, leader stem computation, leader transitions, kick-bass tightness, handoffs, chord changes) in tests/unit/test_section_profiler.py
- [X] T007 [P] Write failing tests for moment classifier (type detection for energy_surge/drop/vocal_entry/vocal_exit/texture_shift, temporal pattern classification: isolated/double_tap/plateau/cascade/scattered, ranking formula) in tests/unit/test_moment_classifier.py
- [X] T008 [P] Write failing tests for energy arc detector (ramp/arch/flat/valley/sawtooth/bookend classification from 10-point energy sampling) in tests/unit/test_energy_arc.py
- [X] T009 [P] Write failing tests for lighting mapper (role → active_tiers, brightness_ceiling, theme_layer_mode, transition_in mapping; verify energy_level modulates beat_effect_density) in tests/unit/test_lighting_mapper.py
- [X] T010 [P] Write failing tests for stem curve extractor (downsample ValueCurve from 10fps to 2Hz, verify array lengths match ceil(duration * 2), full_mix includes spectral/harmonic/percussive) in tests/unit/test_stem_curves.py
- [X] T011 [P] Implement section merger in src/story/section_merger.py — merge micro-segments into 8-15 sections using min duration (4s), same-role adjacency, vocal continuity rules per research.md R1; make T004 tests pass
- [X] T012 [P] Implement section classifier in src/story/section_classifier.py — three-signal approach (vocal activity primary, energy rank secondary, MFCC repetition tertiary) with climax override per research.md R2; make T005 tests pass
- [X] T013 [P] Implement section profiler in src/story/section_profiler.py — compute SectionCharacter (energy score/peak/variance/trajectory, texture + hp_ratio, spectral brightness/centroid/flatness, local_tempo_bpm from beats, dominant_note from chroma, frequency_bands from band_energies) and SectionStems (stem_levels, onset_counts, drum_pattern with kick/snare/hihat + style, leader_stem + transitions from interaction.leader_track, solos, tightness from interaction.tightness, handoffs from interaction.handoffs, chords from L6, other_stem_class) from HierarchyResult data for a given time range per data-model.md; make T006 tests pass
- [X] T014 [P] Implement moment classifier in src/story/moment_classifier.py — detect moments from L0 data + vocal/texture events, classify temporal patterns, rank by weighted formula per data-model.md; make T007 tests pass
- [X] T015 [P] Implement energy arc detector in src/story/energy_arc.py — sample energy at 10 points, classify shape per spec section classification logic; make T008 tests pass
- [X] T016 [P] Implement lighting mapper in src/story/lighting_mapper.py — pure function mapping (role, energy_level) → SectionLighting per stem-lighting-framework.md tier rules; make T009 tests pass
- [X] T017 [P] Implement stem curve extractor in src/story/stem_curves.py — downsample existing ValueCurve data to 2Hz StemCurves dict; make T010 tests pass

**Checkpoint**: All foundational modules pass their unit tests independently. Ready for integration.

---

## Phase 3: User Story 1 + 5 — Automatic Song Interpretation & Export (Priority: P1) 🎯 MVP

**Goal**: Run a single CLI command on an MP3 and produce a complete song story JSON file that the generator can consume.

**Independent Test**: Run `xlight-analyze story song.mp3` and verify the output JSON contains schema_version, global properties, 8-15 sections with roles and lighting guidance, ranked moments, and 2Hz stem curves.

### Tests for US1+US5

- [X] T018 [P] [US1] Write failing integration test: MP3 → build_song_story() → valid song story dict with all required top-level keys, non-empty sections, non-empty moments, valid stem curves in tests/integration/test_story_pipeline.py
- [X] T019 [P] [US1] Write failing test for builder orchestration: verify build_song_story calls merger → classifier → profiler → moment classifier → energy arc → lighting mapper → stem curves in correct order, with correct data flow in tests/unit/test_builder.py
- [X] T020 [P] [US5] Write failing test for song story JSON serialization: verify output matches contracts/song-story-schema.md validation rules (contiguous sections, sorted moments, matching curve lengths, valid review state) in tests/unit/test_story_serialization.py

### Implementation for US1+US5

- [X] T021 [US1] Implement story builder in src/story/builder.py — top-level build_song_story(hierarchy: HierarchyResult, audio_path: str) → dict that orchestrates all foundational modules: load hierarchy, merge sections, classify roles, profile sections, detect moments, compute energy arc, map lighting, extract stem curves, assemble SongStory dict; handle stems_available=[] by falling back to full-mix-only profiling; make T018 and T019 tests pass
- [X] T022 [US5] Implement song story JSON serialization and validation in src/story/builder.py — add write_song_story(story: dict, output_path: str), load_song_story(path: str) → dict, write_edits(edits: dict, path: str), load_edits(path: str) → dict, and merge_story_with_edits(base: dict, edits: dict) → dict with schema version check and validation per contracts/song-story-schema.md; make T020 tests pass
- [X] T023 [US1] Add overwrite protection to write_song_story: check if story file exists, warn if reviewed, require force flag per FR-020 in src/story/builder.py
- [X] T024 [US1] Add `story` CLI command in src/cli.py — click command accepting audio_path, --output, --force flags; calls run_orchestrator() then build_song_story() then write_song_story(); displays step-by-step progress per FR-021
- [X] T025 [US5] Modify generator to consume song story in src/generator/plan.py — add optional --story parameter to generate_sequence(); when provided, look for `_story_reviewed.json` first, fall back to `_story.json`; extract section roles, energy scores, lighting guidance, preferences, and moments instead of calling derive_section_energies(); fall back to existing pipeline when no story given per research.md R7 and FR-029
- [X] T026 [US5] Update theme selector to use song story roles in src/generator/theme_selector.py — when song story sections are provided, use section.role and section.lighting.theme_layer_mode instead of mood_tier mapping
- [X] T027 [US5] Add --story flag to `generate` CLI command in src/cli.py — pass song story JSON path through to generate_sequence()

**Checkpoint**: `xlight-analyze story song.mp3` produces valid JSON. `xlight-analyze generate song.mp3 --story song_story.json --layout layout.xml --output show.xsq` uses the story. MVP complete.

---

## Phase 4: User Story 2 — Interactive Song Story Review (Priority: P2)

**Goal**: Open a browser-based review interface that displays the song story with synchronized audio playback, section timeline, stem visualizations, and section detail panel.

**Independent Test**: Run `xlight-analyze story-review song_story.json`, open browser, verify waveform timeline with section blocks, audio playback with synced playhead, section detail panel updates on section change.

### Implementation for US2

- [X] T028 [P] [US2] Create Flask blueprint with routes: GET /story (load story JSON), GET /story/audio (stream audio file), GET /story/stems (stem curve data) in src/review/story_routes.py
- [X] T029 [P] [US2] Create story review HTML shell with layout regions (toolbar, timeline, section detail, stems panel, moments panel) in src/review/static/story-review.html
- [X] T030 [US2] Implement Canvas waveform timeline with labeled section blocks, playhead, click-to-seek in src/review/static/story-review.js — load audio via Web Audio API, render waveform + section overlays, sync playhead to audio currentTime
- [X] T031 [US2] Implement section detail panel in src/review/static/story-review.js — display current section's role, energy, texture, stem levels, drum pattern summary (kick/snare/hihat counts + style), solo regions (stem + time range + prominence), leader stem, leader transitions, kick-bass tightness, chord changes, handoffs, and lighting guidance; auto-update when playhead crosses section boundary or user clicks a section
- [X] T032 [US2] Implement stem visualization panel in src/review/static/story-review.js — render mini RMS waveforms per stem for the current section, highlight dominant stem
- [X] T033 [US2] Implement moments list panel in src/review/static/story-review.js — list moments in current section with timestamp, type, stem, intensity, pattern
- [X] T034 [US2] Register story blueprint in src/review/server.py and add `story-review` CLI command in src/cli.py — command accepts story JSON path, optional --port, serves review SPA
- [X] T035 [P] [US2] Add story review CSS styling in src/review/static/story-review.css — layout grid, section block colors by role, stem level bars, moment badges

**Checkpoint**: Browser-based review displays all song data with synchronized playback. Read-only at this point.

---

## Phase 5: User Story 3 — Section Editing in Review (Priority: P2)

**Goal**: Users can rename section roles, adjust boundaries, merge/split sections, and override energy — with automatic re-profiling of affected sections.

**Independent Test**: In review UI, rename a section role → verify lighting guidance updates. Split a section → verify two new sections with independent profiles. Merge two sections → verify single section with combined profile. Drag boundary → verify both sections re-profiled.

### Tests for US3

- [X] T036 [P] [US3] Write failing tests for re-profiling API: POST /story/reprofile with modified section bounds returns updated character, stems, and lighting for affected sections in tests/unit/test_story_routes.py

### Implementation for US3

- [X] T037 [US3] Add audio + stem array loading at session start in src/review/story_routes.py — on first request, load audio file and stem arrays into server memory for fast re-profiling per research.md R4
- [X] T038 [US3] Add section editing API endpoints in src/review/story_routes.py — POST /story/rename (change role, re-map lighting), POST /story/split (split at timestamp, re-profile both), POST /story/merge (merge adjacent, re-profile combined), POST /story/boundary (adjust boundary, re-profile both adjacent)
- [X] T039 [US3] Implement re-profiling logic in API handlers: call section_profiler and lighting_mapper on affected time ranges using in-memory audio/stems, re-bucket moments by new section bounds; make T036 tests pass
- [X] T040 [US3] Add section editing UI controls in src/review/static/story-review.js — role rename dropdown, "Split Here" button (at playhead), "Merge →" button, boundary drag handles on timeline, energy override dropdown
- [X] T041 [US3] Wire UI controls to API endpoints in src/review/static/story-review.js — on edit action, POST to server, receive updated sections, re-render timeline and detail panel

**Checkpoint**: All section editing operations work with automatic re-profiling. Edits are reflected in the UI immediately.

---

## Phase 6: User Story 4 — Dramatic Moment Curation (Priority: P3)

**Goal**: Users can dismiss moments and flag highlight sections in the review UI.

**Independent Test**: Dismiss a moment in the UI → export → verify moment has dismissed=true. Flag a section as highlight → export → verify is_highlight=true.

### Implementation for US4

- [X] T042 [P] [US4] Add moment dismiss and section highlight API endpoints in src/review/story_routes.py — POST /story/moment/dismiss (toggle dismissed flag), POST /story/section/highlight (toggle is_highlight flag)
- [X] T043 [US4] Add dismiss toggle (checkbox) on each moment row and highlight toggle (star button) on section detail panel in src/review/static/story-review.js; wire to API endpoints
- [X] T044 [US4] Add Save button API endpoint POST /story/save in src/review/story_routes.py — persist user edits to a separate `_story_edits.json` file per FR-019/FR-027; track all section edits (renames, splits, merges, boundary moves, overrides), moment dismissals, and preferences as structured edit records; keep base `_story.json` unmodified
- [X] T045 [US4] Add Export button API endpoint POST /story/export in src/review/story_routes.py — merge base story + edits file into final `_story_reviewed.json` with review.status="reviewed", reviewed_at timestamp, and reviewer_notes per FR-013/FR-029
- [X] T046 [US4] Add Save and Export buttons to toolbar in src/review/static/story-review.js — Save persists draft, Export finalizes review; add reviewer notes text field

**Checkpoint**: Full review workflow: view → edit sections → curate moments → save progress → export final story.

---

## Phase 7: User Story 7 — Creative Preferences (Priority: P2)

**Goal**: Users can set song-wide creative direction and per-section overrides (mood, theme, focus stem, intensity, occasion, genre) that guide downstream generation.

**Independent Test**: Set focus_stem="guitar" on a section with a guitar solo, set occasion="christmas" globally, export → verify preferences are in the JSON. Feed into generator → verify guitar zone is boosted and Christmas themes are selected.

### Implementation for US7

- [X] T047 [US7] Initialize Preferences with defaults in builder.py (mood=null, theme=null, focus_stem=null, intensity=1.0, occasion="general", genre=null from ID3 tags); Preferences data class already exists in models.py from T002
- [X] T048 [US7] Add song-wide preferences panel to review UI in src/review/static/story-review.js — mood dropdown (ethereal/structural/aggressive/dark/auto), theme dropdown (21 built-in + auto), focus stem dropdown (6 stems + auto), intensity slider (0-200%), occasion selector, genre text field
- [X] T049 [US7] Add per-section override controls to section detail panel in src/review/static/story-review.js — theme dropdown, focus stem dropdown, mood dropdown, intensity slider; each with "auto" option that clears the override
- [X] T050 [US7] Add preferences API endpoints in src/review/story_routes.py — POST /story/preferences (update song-wide prefs), POST /story/section/overrides (update per-section overrides including new mood/theme/focus_stem/intensity fields)
- [X] T051 [US7] Update generator in src/generator/plan.py to implement three-level precedence: per-section override > song-wide preference > auto-derived; apply focus_stem zone boosting per contracts/song-story-schema.md section 6
- [X] T052 [US7] Update theme selector in src/generator/theme_selector.py to respect mood override (filter to matching pool), theme lock (skip selection, use forced theme), and occasion/genre preferences

**Checkpoint**: User can express creative intent via preferences and overrides. Generator respects the three-level precedence chain.

---

## Phase 8: User Story 6 — Quick Pipeline Mode (Priority: P3)

**Goal**: Single command generates story and opens review UI.

**Independent Test**: Run `xlight-analyze story song.mp3 --review` → verify story generates, then browser opens to review UI.

### Implementation for US6

- [X] T053 [US6] Add --review flag to `story` CLI command in src/cli.py — after story generation completes, automatically launch Flask review server and open browser to the story-review page

**Checkpoint**: One-command workflow from MP3 to interactive review.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories.

- [X] T054 [P] Add stale-edits detection in src/review/story_routes.py — on review session load, compare `_story_edits.json` base_story_hash against current `_story.json` MD5; if mismatch, return a warning flag to the UI per FR-028; add UI banner in src/review/static/story-review.js offering to re-apply or discard previous edits
- [X] T055 [P] Add prev/next section navigation keyboard shortcuts (arrow keys) in src/review/static/story-review.js
- [X] T056 [P] Add low-confidence warning indicators (role_confidence < 0.5) on sections in the review timeline in src/review/static/story-review.js
- [ ] T057 Run full integration test: MP3 → story → review edits → export → generate sequence with story → verify XSQ uses story roles, lighting, and preferences; validate section classifier achieves >=70% role accuracy against hand-labeled fixture (SC-002) in tests/integration/test_story_pipeline.py
- [ ] T058 Validate quickstart.md commands work end-to-end per specs/021-song-story-tool/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (models.py and fixtures) — BLOCKS all user stories
- **US1+US5 (Phase 3)**: Depends on Phase 2 — MVP delivery
- **US2 (Phase 4)**: Depends on Phase 3 (needs a story JSON to display)
- **US3 (Phase 5)**: Depends on Phase 4 (needs the review UI to add editing to)
- **US4 (Phase 6)**: Depends on Phase 4 (needs the review UI); depends on US3 completing first (both modify story_routes.py and story-review.js)
- **US7 (Phase 7)**: Depends on Phase 4 (needs review UI) and Phase 6 (needs save/export); adds preferences panel
- **US6 (Phase 8)**: Depends on Phase 3 (story command) and Phase 4 (review server)
- **Polish (Phase 9)**: Depends on all previous phases

### User Story Dependencies

- **US1+US5 (P1)**: Can start after Foundational — no dependencies on other stories
- **US2 (P2)**: Depends on US1 output (needs a song story JSON file to display)
- **US3 (P2)**: Depends on US2 (adds editing to the review UI)
- **US4 (P3)**: Depends on US3 (both modify story_routes.py and story-review.js)
- **US7 (P2)**: Depends on US4 (needs save/export workflow); adds preferences to review
- **US6 (P3)**: Depends on US1 (story command) + US2 (review server); independent of US3/US4/US7

### Within Each Phase

- Tests marked [P] can run in parallel
- Implementation modules marked [P] can run in parallel (different files)
- Tests MUST be written and FAIL before implementation (TDD per constitution)

### Parallel Opportunities

- **Phase 2**: All 7 test tasks (T004-T010) can run in parallel. All 7 implementation tasks (T011-T017) can run in parallel (each in its own file).
- **Phase 3**: T018-T020 (tests) can run in parallel. T021-T022 depend on foundational modules.
- **Phase 4**: T028-T029 and T035 can run in parallel (Flask routes, HTML shell, CSS). T030-T033 are sequential (build on each other within the same JS file).
- **Phase 5→6→7**: US3, US4, and US7 must run sequentially — all modify story_routes.py and story-review.js.

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch ALL test tasks in parallel (7 different test files):
T004: tests/unit/test_section_merger.py
T005: tests/unit/test_section_classifier.py
T006: tests/unit/test_section_profiler.py
T007: tests/unit/test_moment_classifier.py
T008: tests/unit/test_energy_arc.py
T009: tests/unit/test_lighting_mapper.py
T010: tests/unit/test_stem_curves.py

# Then launch ALL implementation tasks in parallel (7 different source files):
T011: src/story/section_merger.py
T012: src/story/section_classifier.py
T013: src/story/section_profiler.py
T014: src/story/moment_classifier.py
T015: src/story/energy_arc.py
T016: src/story/lighting_mapper.py
T017: src/story/stem_curves.py
```

---

## Implementation Strategy

### MVP First (US1 + US5 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T017)
3. Complete Phase 3: US1+US5 (T018-T027)
4. **STOP and VALIDATE**: Run `xlight-analyze story song.mp3` → valid JSON. Run `xlight-analyze generate --story` → XSQ uses story data.
5. MVP delivers the core value: automatic interpretation + generator integration.

### Incremental Delivery

1. Setup + Foundational → Core modules ready
2. Add US1+US5 → CLI story generation + generator consumption (MVP!)
3. Add US2 → Browser review UI (read-only)
4. Add US3 → Section editing in review
5. Add US4 → Moment curation + save/export workflow (two-file architecture)
6. Add US7 → Creative preferences (mood, theme, focus stem, intensity)
7. Add US6 → Quick pipeline mode (convenience)
8. Each phase adds value without breaking previous phases.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Constitution requires TDD: write failing tests, then implement
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- The detailed design doc at docs/song-story-spec.md contains JSON schemas, classification algorithms, and UI wireframes to reference during implementation
