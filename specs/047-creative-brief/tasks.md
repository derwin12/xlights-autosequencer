# Tasks: Creative Brief (Per-Song Workspace, Phase 3) (047)

**Input**: Design documents from `/specs/047-creative-brief/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md
**Hard dependency**: spec 046 (per-song workspace shell) must be shipped.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Verify prerequisites, scout existing code touch-points, and create skeleton files so later tasks can diverge in parallel.

- [ ] T001 Verify spec 046 has landed: `src/review/static/song-workspace/` exists with tab shell (Analysis / Brief / Generate). Confirm a Brief-tab stub is reachable from the tab bar and that the shell exposes a hook for mounting tab-local markup.
- [ ] T002 Read and document the current `/generate/<source_hash>` handler in `src/review/generate_routes.py` — locate `_load_prefs_from_story` call site, the `GenerationJob` dataclass, the `_VALID_*` frozensets, and the exact spot where the POST body would be parsed.
- [ ] T003 Read and document `GenerationConfig` in `src/generator/models.py` — note existing `_VALID_CURVES_MODES` and `__post_init__` validation pattern so Phase C additions match.
- [ ] T004 Read and document `Library().find_by_hash(source_hash)` in `src/library.py` — confirm the returned record exposes `source_file` path so `brief_routes.py` can derive `<audio_stem>_brief.json`.
- [ ] T005 [P] Create empty module `src/review/brief_routes.py` with a TODO stub and module docstring referencing this spec.
- [ ] T006 [P] Create empty `src/review/static/song-workspace/brief-tab.html` with a root `<section id="brief-tab" hidden>` placeholder.
- [ ] T007 [P] Create empty `src/review/static/song-workspace/brief-tab.js` with a module-level export stub `export function mountBriefTab(root, sourceHash) {}`.
- [ ] T008 [P] Create empty `src/review/static/song-workspace/brief-presets.js` with an export stub `export const BRIEF_PRESETS = {};`.
- [ ] T009 [P] Create empty `src/review/static/song-workspace/brief-tab.css` with a top-of-file comment header.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define the Brief JSON schema, the preset map, and the nominal `GenerationConfig` fields. These land first so every subsequent task has something to import.

- [ ] T010 [P] Write unit test stubs for schema defaults in `tests/unit/test_brief_persistence.py`: assert an all-omitted Brief parses to all-`"auto"` strings, `per_section_overrides == []`, `advanced == {}`, `brief_schema_version == 1`.
- [ ] T011 [P] Write unit test for `GenerationConfig` accepting three new nominal fields (`mood_intent`, `duration_feel`, `accent_strength`) in `tests/unit/test_generation_config.py` (or extend the existing file) — verify default `"auto"` and rejection of unknown values.
- [ ] T012 Add `mood_intent: str = "auto"` to `GenerationConfig` dataclass in `src/generator/models.py` with `_VALID_MOOD_INTENTS = frozenset({"auto","party","emotional","dramatic","playful"})` and `__post_init__` validation mirroring `curves_mode`.
- [ ] T013 Add `duration_feel: str = "auto"` to `GenerationConfig` with `_VALID_DURATION_FEELS = frozenset({"auto","snappy","balanced","flowing"})` and matching validation.
- [ ] T014 Add `accent_strength: str = "auto"` to `GenerationConfig` with `_VALID_ACCENT_STRENGTHS = frozenset({"auto","subtle","strong"})` and matching validation.
- [ ] T015 Run `python3 -m pytest tests/unit/test_generation_config.py tests/unit/test_brief_persistence.py -v` to confirm nominal-field tests pass and schema stub compiles.
- [ ] T016 [P] Populate `src/review/static/song-workspace/brief-presets.js` with the full `BRIEF_PRESETS` map from `research.md` §1 (9 axes × preset id / label / hint / raw mapping). Export a helper `resolveBriefToPost(brief)` that converts a Brief JSON into a sparse POST body (omit Auto fields, spread Advanced overrides last).
- [ ] T017 [P] Write a unit test in `tests/unit/test_brief_persistence.py` that round-trips every preset combination from `BRIEF_PRESETS` through `GenerationConfig(**resolved)` without raising (SC-008). Tests run via a small Python transcription of `BRIEF_PRESETS` or by loading the JS file as JSON-like text.

**Checkpoint**: `GenerationConfig` accepts the three nominal fields; `BRIEF_PRESETS` and schema defaults are defined; tests pass.

---

## Phase 3: User Story 1 — Single Brief Form Is the Source of Truth (Priority: P1) MVP

**Goal**: The Brief tab renders one scrollable form exposing every creative knob, with named-preset selectors and Auto-by-default, for any song in the library.

**Independent Test**: Open `/song/<hash>`, click Brief, confirm all nine axis controls plus Per-Section table render, every default is Auto or ID3-derived, and each control has a visible hint.

### Tests for User Story 1

- [ ] T018 [P] [US1] Write a DOM/integration test (JSDOM or Playwright-style) in `tests/integration/test_brief_tab_render.py` (or the project's existing web-test harness) that loads `brief-tab.html` + `brief-tab.js`, mounts against a fake `sourceHash`, stubs `GET /brief/<hash>` → 404, and asserts that exactly 9 axis controls and the per-section table render with Auto-default values.
- [ ] T019 [P] [US1] Write a test asserting every axis control has a visible `<p class="hint">` sibling with non-empty text and that hints are in the rendered DOM, not behind `title=` tooltips (FR-051, US6 AC-1).
- [ ] T020 [P] [US1] Write a test asserting every axis exposes an `<details class="advanced">` that is closed by default and, when opened, shows raw controls prefilled from the preset (FR-005, US2 AC-3 / AC-4).
- [ ] T021 [P] [US1] Write a test that toggling a raw Advanced control to a value that does not match any named preset flips the preset selector label to "Custom" (US2 AC-5).

### Implementation for User Story 1

- [ ] T022 [US1] Populate `src/review/static/song-workspace/brief-tab.html` with the full form markup: one `<fieldset>` per axis (Genre, Occasion, Mood, Variation, Palette, Duration, Accents, Transitions, Curves), each with label / radio-group preset selector / hint paragraph / Advanced disclosure; plus a `<section id="per-section-overrides">` table placeholder; plus `Reset to Auto` and primary `Generate` buttons at the bottom.
- [ ] T023 [US1] Add CSS in `src/review/static/song-workspace/brief-tab.css` for preset radio groups (segmented control style), hint text (muted, one-line), Advanced disclosures (subtle border), per-section table (compact, 5 columns), and the Generate primary button. Ensure keyboard focus rings are visible (FR-050).
- [ ] T024 [US1] In `brief-tab.js`, implement `renderAxis(axisId, briefValue)` that reads from `BRIEF_PRESETS[axisId]` and produces a preset radio group with hint and Advanced details, binding change handlers to an in-memory brief state object.
- [ ] T025 [US1] In `brief-tab.js`, implement `mountBriefTab(root, sourceHash)` to fetch `GET /brief/<hash>`, synthesize all-Auto defaults on 404, render every axis via `renderAxis`, render the per-section overrides table (initially empty — will be populated by US5 task T054), and wire the Generate / Reset buttons as no-ops (actual submit lands in US4).
- [ ] T026 [US1] Implement the Advanced → Custom detection: when a raw-control change diverges from the current preset's `raw` map, switch the preset selector's active label to "Custom" and stop highlighting any preset button.
- [ ] T027 [US1] Implement the Custom → preset re-sync: changing the preset selector explicitly restores the preset's raw values into the Advanced controls and clears the Custom indicator.
- [ ] T028 [US1] Run tests: `python3 -m pytest tests/integration/test_brief_tab_render.py -v`.

**Checkpoint**: Brief tab renders, every axis is visible with preset selectors, Advanced disclosures toggle correctly, hints are inline. US1 deliverable complete.

---

## Phase 4: User Story 2 — Presets Before Sliders, Auto Is Always Valid (Priority: P1)

**Goal**: Every axis has 3–5 named presets including Auto; Auto is submittable everywhere; Mood selection applies smart defaults to sibling Auto axes.

**Independent Test**: Confirm every axis has exactly one "Auto" preset; selecting a non-Auto Mood updates sibling Auto axes per the ruleset while explicit picks remain.

### Tests for User Story 2

- [ ] T029 [P] [US2] Write a test iterating every axis in `BRIEF_PRESETS` and asserting 3 ≤ len(presets) ≤ 5 and exactly one preset has id `"auto"` (FR-004, US2 AC-1).
- [ ] T030 [P] [US2] Write a test: set every axis to Auto, call `resolveBriefToPost(brief)`, assert the resulting POST body is empty (or contains only `mood_intent: "auto"`) — matches US2 AC-2 and SC-002.
- [ ] T031 [P] [US2] Write a test for `MOOD_DEFAULTS`: mood=Dramatic with all siblings Auto → Transitions="dramatic", Accents="strong", Variation="focused", Palette="restrained", Duration="flowing". Matches `research.md` §2.
- [ ] T032 [P] [US2] Write a test: explicit sibling pick (e.g. Variation="varied") is preserved across Mood changes (US2 AC-5 spirit, research §2 rule #3).
- [ ] T033 [P] [US2] Write a test: Mood → Auto reverts implicitly-set siblings ("via Mood") back to Auto, but keeps explicitly-set siblings.

### Implementation for User Story 2

- [ ] T034 [US2] Add `MOOD_DEFAULTS` constant to `src/review/static/song-workspace/brief-tab.js` containing the five-row table from `research.md` §2. Include a clear comment that this dict is Phase 3 scaffolding and is deletable in Phase 4 (spec 048).
- [ ] T035 [US2] Add per-axis provenance state (`axis.origin = "default" | "user" | "via-mood"`) to the in-memory brief state in `brief-tab.js`.
- [ ] T036 [US2] Implement `applyMoodDefaults(mood, briefState)`: for each sibling axis, if `origin !== "user"`, set the axis value from `MOOD_DEFAULTS[mood]` and mark `origin = "via-mood"`. Auto mood clears all "via-mood" entries back to "default"/"auto".
- [ ] T037 [US2] Add a small "via Mood" chip to any axis whose provenance is `"via-mood"` (CSS + DOM helper).
- [ ] T038 [US2] Wire the Mood axis change handler to call `applyMoodDefaults` and re-render affected siblings.
- [ ] T039 [US2] Ensure explicit user interaction on any non-Mood axis flips `origin = "user"` so subsequent Mood changes do not overwrite it.
- [ ] T040 [US2] Run tests: `python3 -m pytest tests/integration/test_brief_tab_render.py -v -k "mood or preset"`.

**Checkpoint**: Presets + Auto behavior is correct; Mood smart-defaults work client-side; explicit picks are never clobbered. US2 deliverable complete.

---

## Phase 5: User Story 3 — Brief Persists Per Song (Priority: P1)

**Goal**: Submitting the Brief persists it to `<audio>_brief.json`; reopening loads it; Reset clears UI without rewriting disk until next submit.

**Independent Test**: Submit a non-default Brief, restart the server, reopen, confirm every control restores the submitted value.

### Tests for User Story 3

- [ ] T041 [P] [US3] Write `tests/unit/test_brief_routes.py` test: `GET /brief/<hash>` on a song with no brief file returns 404.
- [ ] T042 [P] [US3] Write a test: `PUT /brief/<hash>` with a valid Brief body writes `<audio_stem>_brief.json` atomically, returns 200 with the stored JSON, and a subsequent `GET` returns the same document (minus `updated_at` drift).
- [ ] T043 [P] [US3] Write a test: `PUT` with unknown genre / occasion / curves_mode returns 400 with `{field, error}` shape (FR-042).
- [ ] T044 [P] [US3] Write a test: `PUT` with `brief_schema_version != 1` returns 409 with a migration hint message.
- [ ] T045 [P] [US3] Write a test: `PUT` with a `theme_slug` in `per_section_overrides` that is not in the catalog returns 400 (or the field is stripped — matching FR-033 edge case; pick one and assert).
- [ ] T046 [P] [US3] Write a test: round-trip a fully populated Brief JSON through `PUT` → `GET` and assert deep equality on every field (SC-008).

### Implementation for User Story 3

- [ ] T047 [US3] Implement `brief_bp = Blueprint("brief", __name__, url_prefix="/brief")` in `src/review/brief_routes.py`.
- [ ] T048 [US3] Implement a helper `_brief_path(source_hash: str) -> Path` that resolves the audio file via `Library().find_by_hash(source_hash).source_file` and returns `audio_path.parent / f"{audio_path.stem}_brief.json"`. Raises a 404 if the song is unknown.
- [ ] T049 [US3] Implement `GET /brief/<source_hash>`: return `(json, 200)` if the file exists, `(jsonify(error="no brief"), 404)` otherwise.
- [ ] T050 [US3] Implement `PUT /brief/<source_hash>`: parse JSON body, validate schema version = 1 (409 otherwise), validate every axis value against the corresponding `_VALID_*` set from `GenerationConfig` / local enums, validate `advanced.curves_mode` against `_VALID_CURVES_MODES`, verify each `per_section_overrides[*].theme_slug` exists in the theme/variant catalog (use existing catalog loader). On any failure return 400 with `{field, error}`.
- [ ] T051 [US3] On successful validation, set `updated_at = datetime.utcnow().isoformat() + "Z"`, serialize to a temp file in the same directory, and `os.replace` onto the final path (atomic write). Return the stored JSON with status 200.
- [ ] T052 [US3] Register `brief_bp` in `src/review/server.py` next to the existing blueprints.
- [ ] T053 [US3] In `brief-tab.js`, wire the Reset button to reset every in-memory axis to `"auto"` and clear `per_section_overrides` in state. Reset does NOT call `PUT` — it only rewrites state; the next Generate click will persist (FR-033).
- [ ] T054 [US3] In `brief-tab.js`, extend `mountBriefTab` to populate UI from the fetched brief (if present) — every axis selector reflects the persisted preset id, Advanced values hydrate if set, per-section table rows show overrides. First paint must complete without a flash-of-defaults (SC-009).
- [ ] T055 [US3] In `brief-tab.js`, detect stale `theme_slug` in `per_section_overrides` (not in the catalog GET response) — render that row as Auto with a warning chip, and drop the stale override from the in-memory state so the next submit clears it (FR-033 edge case).
- [ ] T056 [US3] Run tests: `python3 -m pytest tests/unit/test_brief_routes.py -v`.

**Checkpoint**: Brief persists and restores across server restart; Reset behaves correctly; stale slugs are handled. US3 deliverable complete.

---

## Phase 6: User Story 4 — Submitting the Brief Triggers Generation (Priority: P1)

**Goal**: Generate button persists the Brief, POSTs every Brief field to `/generate/<hash>`, switches to Generate tab, surfaces validation errors inline, and records a Brief snapshot on the job.

**Independent Test**: Fill non-default Brief, click Generate, verify `PUT /brief` + `POST /generate` fire in order, tab switches, and resulting plan JSON reflects submitted choices.

### Tests for User Story 4

- [ ] T057 [P] [US4] Write contract test in `tests/unit/test_generate_routes.py` (extend existing) asserting that `POST /generate/<hash>` with an empty body still produces the same `GenerationConfig` as today's dashboard flow (SC-002, SC-007).
- [ ] T058 [P] [US4] Write a contract test asserting `POST /generate/<hash>` accepts `{genre, occasion, transition_mode, curves_mode, focused_vocabulary, embrace_repetition, palette_restraint, duration_scaling, beat_accent_effects, tier_selection, theme_overrides, mood_intent, duration_feel, accent_strength}` and that each value reaches `GenerationConfig` unchanged.
- [ ] T059 [P] [US4] Write a test asserting that when the POST body supplies `genre`/`occasion`/`transition_mode`, the server does NOT call `_load_prefs_from_story` for those fields (FR-041).
- [ ] T060 [P] [US4] Write a test asserting that when the POST body omits all three, the server still falls back to `_load_prefs_from_story` as a last resort (legacy safety net for un-briefed songs).
- [ ] T061 [P] [US4] Write a test asserting an invalid POST body value (e.g. `transition_mode: "explosive"`) returns 400 with `{field: "transition_mode", error: ...}` (FR-042).
- [ ] T062 [P] [US4] Write a test asserting the on-disk Brief JSON is consulted as the second-tier fallback when the POST body is empty but `<audio>_brief.json` exists.
- [ ] T063 [P] [US4] Write an integration test in `tests/integration/test_brief_generation.py` that seeds analysis for a fixture song, `PUT`s a Brief with mood=dramatic / palette=restrained / variation=varied / one per-section override, POSTs `/generate/<hash>`, and asserts the resulting plan JSON has the expected config fields and theme override on the named section (SC-003).
- [ ] T064 [P] [US4] Write a test asserting that after successful generation, the `GenerationJob` record has `brief_snapshot` populated with the exact Brief body (FR-044).

### Implementation for User Story 4

- [ ] T065 [US4] Extend `GenerationJob` dataclass in `src/review/generate_routes.py` with `brief_snapshot: Optional[dict] = None`.
- [ ] T066 [US4] Add a helper `_resolve_brief_field(body, on_disk_brief, story_prefs, field_name, default)` in `generate_routes.py` that returns the first non-Auto source in priority order: POST body → on-disk Brief → story-prefs (legacy, only for genre/occasion/transition_mode) → `GenerationConfig` default.
- [ ] T067 [US4] At the top of `start_generation`, parse `body = request.get_json(silent=True) or {}` and load the on-disk Brief via `_brief_path(source_hash)` if present.
- [ ] T068 [US4] Rebuild the `GenerationConfig(...)` construction in `start_generation` to resolve every Brief-capable field via `_resolve_brief_field`, dropping the unconditional call to `_load_prefs_from_story` — call it only when all three legacy fields are still unresolved.
- [ ] T069 [US4] Validate every incoming POST-body value against the same `_VALID_*` sets / `GenerationConfig.__post_init__` rules; on failure return `400 {"field": <name>, "error": <msg>}` without creating a job (FR-042).
- [ ] T070 [US4] Record the full submitted body as `job.brief_snapshot` after successful validation.
- [ ] T071 [US4] In `brief-tab.js`, implement the Generate click handler: (a) `PUT /brief/<hash>` with the full Brief JSON, (b) `POST /generate/<hash>` with the sparse body produced by `resolveBriefToPost`, (c) on 202, dispatch a workspace-shell event to activate the Generate tab.
- [ ] T072 [US4] In `brief-tab.js`, handle 400 from either endpoint: parse `{field, error}`, attach an `.inline-error` element next to the offending control, scroll into view. Do not top-banner.
- [ ] T073 [US4] In `brief-tab.js`, handle concurrent-job responses: if a job is already running for this song, show a non-blocking "Generation in progress" message next to the Generate button and do not resubmit (US4 AC-4).
- [ ] T074 [US4] Run tests: `python3 -m pytest tests/unit/test_generate_routes.py tests/integration/test_brief_generation.py -v`.

**Checkpoint**: Generate submits Brief + fires generation + switches tabs + shows inline errors. MVP (P1 block US1+US2+US3+US4) complete.

---

## Phase 7: User Story 5 — Per-Section Theme Overrides in the Brief (Priority: P2)

**Goal**: A compact per-section table inside the Brief lets users override the theme for individual sections; overrides serialize to `theme_overrides` on submit.

**Independent Test**: For a song with ≥ 8 sections, override two rows to specific theme slugs, submit, confirm those sections get the overridden theme in the generated plan.

### Tests for User Story 5

- [ ] T075 [P] [US5] Write a test asserting the table renders exactly N rows for a song with N detected sections, each row showing index / label / time range (mm:ss – mm:ss) / energy / theme selector defaulting to Auto (US5 AC-1, FR-020).
- [ ] T076 [P] [US5] Write a test asserting non-Auto rows serialize into `theme_overrides: {int: str}` and Auto rows are omitted entirely from the POST body (US5 AC-3).
- [ ] T077 [P] [US5] Write a test asserting a "Clear all overrides" click empties the dict and submits an absent/empty `theme_overrides` (US5 AC-5).
- [ ] T078 [P] [US5] Write a test asserting that reloading after submit restores the overridden rows exactly (US5 AC-4).

### Implementation for User Story 5

- [ ] T079 [US5] Add a `GET /song/<source_hash>/sections` helper (or reuse the existing analysis-fetch endpoint) to return the section list (index, label, start_ms, end_ms, energy). If a suitable endpoint exists, skip; otherwise add it alongside existing analysis routes.
- [ ] T080 [US5] In `brief-tab.js`, fetch the section list on mount, fetch the theme catalog via `GET /themes` (+ `GET /variants`), and render the per-section override table rows into the placeholder from T022.
- [ ] T081 [US5] Wire each row's `<select>` to update in-memory `per_section_overrides` state. Auto rows are removed from state (not stored as null).
- [ ] T082 [US5] Add a "Clear all overrides" button that empties the overrides list and re-renders all rows to Auto.
- [ ] T083 [US5] Extend `resolveBriefToPost` to translate `per_section_overrides` into the `theme_overrides: {int: slug}` shape expected by the POST endpoint.
- [ ] T084 [US5] Run tests: `python3 -m pytest tests/integration/test_brief_generation.py -v -k "override"`.

**Checkpoint**: Per-section overrides work end-to-end via the Brief.

---

## Phase 8: User Story 6 — Hints Explain Why Each Control Matters (Priority: P2)

**Goal**: Every axis control has a static, visible, meaningful hint string.

**Independent Test**: Inspect the rendered page; every axis has a hint ≤ 120 chars that describes the observable effect, not the implementation.

### Tests for User Story 6

- [ ] T085 [P] [US6] Write a test iterating `BRIEF_PRESETS` and asserting every axis has a non-empty top-level hint ≤ 120 chars (FR-003, US6 AC-2).
- [ ] T086 [P] [US6] Write a test asserting hints are rendered as visible DOM text (not `title=` tooltips) by querying the mounted Brief tab (FR-051, US6 AC-1).
- [ ] T087 [P] [US6] Write a test asserting each Advanced raw control has its own hint (US6 AC-4) — Advanced hints are allowed to use technical terminology.

### Implementation for User Story 6

- [ ] T088 [US6] Confirm each of the 9 axis hints in `BRIEF_PRESETS` matches `research.md` §1 exactly and does not mention config flag names (observable-effect phrasing only).
- [ ] T089 [US6] Add per-raw-control hint strings to the Advanced disclosure markup (brief technical description, flag name allowed). Source from `research.md` where available; invent where not and append them to `research.md`'s hint table comment in-file.
- [ ] T090 [US6] Run tests: `python3 -m pytest tests/integration/test_brief_tab_render.py -v -k "hint"`.

**Checkpoint**: Hints are visible, meaningful, and cover both preset and Advanced controls.

---

## Phase 9: User Story 7 — Brief Tab Composes Cleanly into Workspace Shell (Priority: P3)

**Goal**: Brief tab sits between Analysis and Generate in tab order, shows Unsaved / Submitted status badge, preserves focus across tab switches, and displays a last-submitted timestamp.

**Independent Test**: Navigate Analysis → Brief → Generate → Analysis; verify tab activation, focus restoration, badge state, and timestamp visibility.

### Tests for User Story 7

- [ ] T091 [P] [US7] Write a test asserting the tab bar order is Analysis → Brief → Generate (US7 AC-1).
- [ ] T092 [P] [US7] Write a test asserting the Brief tab badge shows "Unsaved" (or dot) when edits are pending and clears after successful submit (US7 AC-2).
- [ ] T093 [P] [US7] Write a test asserting a "Last submitted: ..." timestamp is visible at the top of the Brief form when a persisted brief exists (US7 AC-4).

### Implementation for User Story 7

- [ ] T094 [US7] In `brief-tab.js`, dispatch a `brief:dirty` CustomEvent on any control change and a `brief:clean` on successful submit; have the shell (spec 046) subscribe to toggle the tab badge.
- [ ] T095 [US7] Render a small timestamp line at the top of the Brief form pulled from the loaded Brief's `updated_at`.
- [ ] T096 [US7] Ensure keyboard focus returns to the last-focused control when switching away from and back to the Brief tab (store `document.activeElement.id` on hide, restore on show).

**Checkpoint**: Workspace navigation polish meets US7 scenarios.

---

## Phase 10: Edge Cases & Polish

- [ ] T097 Handle the "song has no analysis yet" edge case: the Brief tab is rendered disabled with a tooltip pointing to the Analysis tab; editing and submitting are blocked (spec Edge Cases §1).
- [ ] T098 Handle "analysis exists but no sections detected": per-section overrides panel shows a single "whole song" pseudo-row labelled "(no sections detected)".
- [ ] T099 Handle "layout not configured": Generate button inside the Brief is disabled with the existing "configure layout first" affordance; editing/persisting still works.
- [ ] T100 Handle ID3 parse failure: Genre preset shows Auto; any raw ID3 string visible as a ghost hint.
- [ ] T101 Handle "generation in progress" click on Generate: message + no duplicate job (US4 AC-4) — confirm wiring from T073 is hit by an integration test.
- [ ] T102 Run the full quickstart walkthrough (`specs/047-creative-brief/quickstart.md` steps 1–9) end-to-end on a fixture song.
- [ ] T103 Run the complete test suite: `python3 -m pytest tests/ -v` and confirm no regressions (SC-007 on the existing `/generate/<hash>` contract).
- [ ] T104 Confirm SC-002: an all-Auto Brief submit produces an effective `GenerationConfig` identical to a dashboard Generate on the same song (diff the two plan JSONs).
- [ ] T105 Confirm SC-009: time the Brief tab first paint on a 30-section song and verify it is under 300ms on the developer laptop.
- [ ] T106 Final sanity pass — no `console.log` / `print` debug statements left behind; no dead code; every new file has a short module docstring/header.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — immediate.
- **Phase 2 (Foundational)**: Depends on Phase 1. Must complete before any UI or route work.
- **Phase 3 (US1)**: Depends on Phase 2 — needs `BRIEF_PRESETS` and skeleton files.
- **Phase 4 (US2)**: Depends on Phase 3 — Mood smart-defaults mutate the US1 state object.
- **Phase 5 (US3)**: Depends on Phase 2 for schema; can start in parallel with Phase 3 since the Flask blueprint is file-isolated. UI wiring (T053–T055) depends on Phase 3.
- **Phase 6 (US4)**: Depends on Phase 5 (needs `PUT /brief`) and Phase 2 (needs `GenerationConfig` nominal fields) and Phase 3 (needs UI scaffold).
- **Phase 7 (US5)**: Depends on Phase 3 (table placeholder) and Phase 6 (POST plumbing carries `theme_overrides`). Tests can be written in parallel earlier.
- **Phase 8 (US6)**: Depends on Phase 3 (DOM exists to assert against). Hint content itself can land in Phase 2 (T016).
- **Phase 9 (US7)**: Depends on Phase 3 + Phase 6. Pure polish; no generation logic.
- **Phase 10 (Polish)**: Depends on every preceding user story phase it validates.

### User Story Dependencies (MVP = P1 block)

- **US1 (single form is source of truth)**: Foundational UI — everything else builds on it.
- **US2 (presets + Auto + Mood defaults)**: Depends on US1 state object.
- **US3 (persistence)**: Independent of US1/US2 server-side; UI wiring depends on US1.
- **US4 (submit triggers generation)**: Depends on US3 (to `PUT` Brief before `POST` generate) + US1/US2 (to have a form to submit).
- **US5 (per-section overrides in Brief)**: Depends on US4 for full end-to-end submission; the table UI depends on US1.
- **US6 (hints)**: Depends on US1 (DOM) + preset map (Phase 2). Content is already part of `BRIEF_PRESETS`.
- **US7 (workspace composition polish)**: Depends on US1 + US4; nothing blocks it after those.

### Parallel Opportunities

- T005–T009 (skeleton file creation) all parallel.
- T010, T011 (test stubs) parallel.
- T016, T017 (preset map + round-trip test) parallel with `GenerationConfig` edits.
- T018–T021 (US1 tests) parallel.
- T029–T033 (US2 tests) parallel.
- T041–T046 (US3 route tests) parallel.
- T057–T064 (US4 contract + integration tests) parallel.
- T075–T078 (US5 tests) parallel.
- T085–T087 (US6 tests) parallel.
- T091–T093 (US7 tests) parallel.
- US3 Flask blueprint (T047–T052) can proceed fully parallel to Phase 3 UI work.
- `GenerationConfig` nominal field additions (T012–T014) can be split across three contributors (different subkeys, same file — coordinate merge).

---

## Implementation Strategy

### MVP First (P1 block: US1 + US2 + US3 + US4)

1. Phase 1 (Setup) — T001–T009.
2. Phase 2 (Foundational) — T010–T017. Schema + `BRIEF_PRESETS` + nominal config fields land.
3. Phase 3 (US1) — T018–T028. Form renders with defaults.
4. Phase 4 (US2) — T029–T040. Presets + Auto + Mood smart-defaults.
5. Phase 5 (US3) — T041–T056. Brief persists to disk.
6. Phase 6 (US4) — T057–T074. Generate button wires through.
7. **STOP and VALIDATE**: Run quickstart steps 1–7, confirm an all-Auto Brief and a non-default Brief both produce correct sequences.
8. If MVP satisfactory, ship or continue to P2 / P3.

### Incremental Delivery

1. Setup + Foundational → schema + preset map + nominal fields live.
2. US1 → form renders.
3. US2 → presets and Auto behavior feel right.
4. US3 → persistence closes the loop for repeat users.
5. US4 → Generate button actually works (MVP ready).
6. US5 → per-section overrides removed from `/story-review` happy path.
7. US6 → hint coverage audited; no bare knobs.
8. US7 → navigation polish.
9. Polish phase → edge cases + regression guard.

---

## Notes

- [P] tasks = different files or independent test functions.
- [Story] label maps task to a specific user story.
- P1 block (US1–US4) is the MVP — everything else is additive polish.
- Mood smart-defaults live in a single JS object (`MOOD_DEFAULTS` in `brief-tab.js`) with a comment marking it Phase-4-deletable — do not leak mood logic into Python yet.
- The three nominal `GenerationConfig` fields (`mood_intent`, `duration_feel`, `accent_strength`) are stored-but-unread in Phase 3 so Phase 4 has zero schema migration.
- `/story-review` is explicitly NOT touched in this phase. Its preferences file stays on disk; the generator just stops reading it when the Brief supplies the value.
- Every new or modified field must route through the existing `_VALID_*` frozensets — do not add ad-hoc validation.
- No per-keystroke autosave (FR-052). Only three network calls per tab session: one GET on mount, one GET for themes, one POST on Generate (plus the PUT immediately before).
