# Tasks: Section Preview Render (049)

**Input**: Design documents from `/specs/049-section-preview-render/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Confirm the prerequisites from earlier phases (046 workspace shell, 047 Brief) are present. No new dependencies required — Python stdlib only (threading, uuid, tempfile, hashlib, json).

- [ ] T001 Verify the Preview-tab shell exists in `src/review/static/song-workspace.html` (from spec 046) — confirm there is an empty tab container we can populate with the dropdown, Preview button, result pane, and error pane
- [ ] T002 Verify the saved-Brief read path exists in `src/review/` (from spec 047) — confirm a helper returns the persisted Brief dict for a song hash so the POST handler can resolve `brief: "saved"`
- [ ] T003 Verify `/api/generation-preview/<hash>` still exists and returns its static-summary payload in `src/review/server.py` — this endpoint MUST remain untouched (FR-014, SC-007)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Audit the existing generator pipeline to identify the four cancellation poll-point boundaries and the `write_xsq` serialization surface that will gain the `scoped_duration_ms` / `audio_offset_ms` parameters. Read-only investigation before any code changes.

- [ ] T004 Read `src/generator/plan.py::build_plan()` end-to-end — document the stage order (`select_themes` → section assignment → `place_effects` → `apply_transitions`) so poll points can be inserted at the four boundaries identified in plan.md Change 2
- [ ] T005 Read `src/generator/xsq_writer.py::write_xsq()` — locate (a) where `sequenceDuration` is emitted from `plan.song_profile.duration_ms`, (b) where `<mediaFile>` is written to the `<head>` block, and (c) the placement serialization loop where `startTime`/`endTime` attributes are emitted
- [ ] T006 Read `src/review/generate_routes.py` (from spec 034) — document the async-job dispatcher pattern (`_jobs` dict, daemon thread, status/polling convention) that `preview_routes.py` will mirror
- [ ] T007 Read `src/analyzer/result.py` (or the hierarchy output module) — confirm the `SectionEnergy`-like data type that carries `label`, `role`, `start_ms`, `end_ms`, `energy_score` for the picker's input, and note the exact field names so the picker fixtures match production shape

**Checkpoint**: All pipeline stage boundaries identified; `write_xsq` modification points located; dispatcher pattern understood.

---

## Phase 3: User Story 1 — One-Click Section Preview (Priority: P1) MVP

**Goal**: POST → scoped generator run → downloadable `.xsq` artifact for one auto-selected section, returned within the 10s wall-clock budget. This is the core MVP and must work end-to-end before any other story ships.

**Independent Test**: POST to `/api/song/<hash>/preview` with `{"section_index": null, "brief": "saved"}` → poll the returned job → download the `.xsq` → open in xLights and confirm effects play against the referenced MP3 at the section's offset.

### Tests for User Story 1

- [ ] T008 [P] [US1] Write unit test: `PreviewJob` lifecycle — `pending → running → done` transitions set `started_at` / `completed_at` / `artifact_path` correctly in tests/unit/test_preview_job.py
- [ ] T009 [P] [US1] Write unit test: `CancelToken.cancel()` followed by `raise_if_cancelled()` raises `PreviewCancelled`; untouched token does not in tests/unit/test_preview_job.py
- [ ] T010 [P] [US1] Write unit test: canonical-JSON `brief_hash` — two logically-equal briefs with different key ordering produce identical `brief_hash` in tests/unit/test_preview_job.py
- [ ] T011 [P] [US1] Write unit test: `_PreviewCache` LRU — 16-entry bound, oldest entry evicted on 17th insert, evicted entry's `.xsq` file deleted from disk in tests/unit/test_preview_job.py
- [ ] T012 [P] [US1] Write unit test: `_PreviewCache` only admits `status == "done"` results — failed and cancelled jobs do not populate the cache in tests/unit/test_preview_job.py
- [ ] T013 [P] [US1] Write integration test: POST `/api/song/<hash>/preview` → poll GET `/api/song/<hash>/preview/<job_id>` → GET `/download` → verify the returned file is a valid `.xsq` with `sequenceDuration` in 10–20s range and `mediaOffset` equal to the picker's chosen section start in tests/integration/test_section_preview.py
- [ ] T014 [P] [US1] Write integration test: POST with `brief: "saved"` uses the persisted Brief; POST with an inline `brief: {...}` object uses that object verbatim (User Story 1 acceptance #4) in tests/integration/test_section_preview.py
- [ ] T015 [P] [US1] Write integration test: preview job that fails (simulated missing analysis) returns `status: "failed"` with a human-readable `error_message`; no `artifact_path` is exposed (FR-013) in tests/integration/test_section_preview.py

### Implementation for User Story 1

- [ ] T016 [US1] Create `src/generator/preview.py` with module skeleton: imports, `PreviewCancelled` exception, and the `CancelToken` class (threading.Event wrapper with `cancel` / `is_cancelled` / `raise_if_cancelled`) per data-model.md
- [ ] T017 [US1] Add the `PreviewJob` dataclass to src/generator/preview.py with the fields from data-model.md (`job_id`, `song_hash`, `section_index`, `brief_snapshot`, `brief_hash`, `status`, `started_at`, `completed_at`, `artifact_path`, `error_message`, `cancel_token`, `result`, `warnings`)
- [ ] T018 [US1] Add the `PreviewResult` dataclass to src/generator/preview.py with the fields from data-model.md (`section`, `window_ms`, `theme_name`, `placement_count`, `artifact_url`, `warnings`) and a `to_json()` helper
- [ ] T019 [US1] Add `_canonical_brief_hash(brief: dict) -> str` helper in src/generator/preview.py — canonical-JSON serialize then sha256, return first 16 hex chars
- [ ] T020 [US1] Add the `_PreviewCache` class (LRU, `max_entries=16`) to src/generator/preview.py — `get(key)`, `put(key, result, artifact_path)`, eviction deletes the evicted artifact file, `__len__`
- [ ] T021 [US1] Add `_clamp_window_ms(section_start, section_end)` helper in src/generator/preview.py — returns `(window_end_ms, window_duration_ms)` clamped to the 10–20s range per the edge-case rules; when the section is < 10s, extends into the next section and records a boundary-crossing flag
- [ ] T022 [US1] Add `scoped_duration_ms: int | None = None` kwarg to `write_xsq()` in src/generator/xsq_writer.py — when set, emit `<sequenceDuration>` using this value instead of `plan.song_profile.duration_ms`; default `None` preserves full-render behavior
- [ ] T023 [US1] Add `audio_offset_ms: int | None = None` kwarg to `write_xsq()` in src/generator/xsq_writer.py — when set, (a) emit a `<mediaOffset>` element in `<head>` with the millisecond value, (b) subtract `audio_offset_ms` from every placement's `start_ms` / `end_ms` during serialization so the output timeline starts at 0; do NOT mutate `EffectPlacement` objects
- [ ] T024 [US1] Add a unit test in tests/unit/test_xsq_writer.py asserting that `write_xsq(..., scoped_duration_ms=15000, audio_offset_ms=45000)` produces a `.xsq` with `sequenceDuration=15.000`, `<mediaOffset>45000</mediaOffset>`, and all `startTime` attributes shifted by −45000 relative to the input placements
- [ ] T025 [US1] Implement `run_section_preview(config, section_index, output_path, cancel_token)` in src/generator/preview.py — calls `build_plan(config, ...)`, polls `cancel_token.raise_if_cancelled()` immediately after, picks `target = assignments[section_index]`, constructs a single-section `SequencePlan`, polls again before `apply_transitions`, polls again before `write_xsq`, invokes `write_xsq` with scoped duration + audio offset, returns a `PreviewResult`
- [ ] T026 [US1] Create `src/review/preview_routes.py` — Flask blueprint `preview_bp`; module-level state `_preview_jobs: dict[str, PreviewJob]`, `_active_by_song: dict[str, str]`, `_dispatch_lock: threading.Lock`, `_preview_cache: _PreviewCache`, `_preview_dir: Path = Path(tempfile.mkdtemp(prefix="xlight_preview_"))`
- [ ] T027 [US1] Implement POST `/api/song/<hash>/preview` in src/review/preview_routes.py — parse `PreviewRequest` body; resolve `brief: "saved"` via the spec-047 helper; if `section_index` is null, defer to the picker (wired in Phase 5, US3); acquire `_dispatch_lock`; compute `brief_hash`; check `_preview_cache` → if hit, return 200 with the cached `PreviewResult`; otherwise create a `PreviewJob`, register it, launch a daemon thread, release lock, return 202 with `{"job_id": ...}`
- [ ] T028 [US1] Implement the thread target `_run_preview(job)` in src/review/preview_routes.py — sets `job.status = "running"` and `job.started_at`; calls `run_section_preview(...)` inside a try/except; on success sets `status = "done"`, `completed_at`, `artifact_path`, `result`, and inserts into `_preview_cache`; on `PreviewCancelled` sets `status = "cancelled"`; on any other exception sets `status = "failed"` and a sanitized `error_message` (no raw traceback)
- [ ] T029 [US1] Implement GET `/api/song/<hash>/preview/<job_id>` in src/review/preview_routes.py — returns JSON with `status`, and when `done` the full `PreviewResult` including `artifact_url`; 404 when `job_id` not found; 400 when `hash` does not match the job's `song_hash`
- [ ] T030 [US1] Implement GET `/api/song/<hash>/preview/<job_id>/download` in src/review/preview_routes.py — streams the `.xsq` via `send_file`; returns 410 Gone when `job.status == "cancelled"`, 404 when artifact missing, 409 when `status != "done"`
- [ ] T031 [US1] Register `preview_bp` in src/review/server.py next to the existing `generate_bp` registration from spec 034
- [ ] T032 [US1] Add the Preview-tab Preview button, Previewing indicator, result pane (section label, window duration, theme name, placement count, Download .xsq link), and error pane in src/review/static/song-workspace.html
- [ ] T033 [US1] Implement the Preview button handler in src/review/static/song-workspace.js — POSTs to `/api/song/<hash>/preview` with `{section_index: null, brief: <live_brief_or_saved>}`, polls the job every 500ms, renders the result pane on `done`, renders the error pane on `failed`, removes any prior Download link on error (FR-013)
- [ ] T034 [US1] Run US1 tests: `pytest tests/unit/test_preview_job.py tests/unit/test_xsq_writer.py tests/integration/test_section_preview.py -v`

**Checkpoint**: One-click preview end-to-end works. Artifact downloads; xLights plays audio at section offset. SC-001, SC-002, SC-004 achievable once US3 picker lands.

---

## Phase 4: User Story 3 — Automatic Representative-Section Selection (Priority: P1) MVP Completion

**Goal**: Pure-function picker that returns the representative section index per the ranking rules in research.md R3. Required to make US1's "null section_index" path produce a useful default.

**Independent Test**: Feed 5 reference-song section fixtures (verse-heavy, chorus-heavy, EDM, ballad, instrumental) into `pick_representative_section()`. At least 4 of 5 match a human reviewer's pick (SC-003).

### Tests for User Story 3

- [ ] T035 [P] [US3] Write unit test: chorus-heavy fixture — picker returns the first-chorus index (highest energy, role `chorus`) in tests/unit/test_preview_section_picker.py
- [ ] T036 [P] [US3] Write unit test: EDM-with-drops fixture — picker returns the first-drop index, not the pre-drop build in tests/unit/test_preview_section_picker.py
- [ ] T037 [P] [US3] Write unit test: ballad fixture — picker returns the first-chorus index even when verses are longer in tests/unit/test_preview_section_picker.py
- [ ] T038 [P] [US3] Write unit test: instrumental-climax fixture — picker returns the highest-energy non-intro section in tests/unit/test_preview_section_picker.py
- [ ] T039 [P] [US3] Write unit test: low-dynamic-range (all energy < 50) fixture — picker returns the longest non-intro / non-outro section (Fallback A) in tests/unit/test_preview_section_picker.py
- [ ] T040 [P] [US3] Write unit test: role-tiebreaker — two sections with equal energy, one `chorus` and one `verse`, picker prefers `chorus` in tests/unit/test_preview_section_picker.py
- [ ] T041 [P] [US3] Write unit test: start-time tiebreaker — two `chorus` sections with equal energy, picker prefers the earlier one in tests/unit/test_preview_section_picker.py
- [ ] T042 [P] [US3] Write unit test: intro/outro-only fixture — picker falls back to the first section with `duration >= 4000ms` regardless of role (Fallback B) in tests/unit/test_preview_section_picker.py
- [ ] T043 [P] [US3] Write unit test: empty section list — picker returns 0 (Fallback C) in tests/unit/test_preview_section_picker.py

### Implementation for User Story 3

- [ ] T044 [US3] Implement `pick_representative_section(sections: list[SectionEnergy]) -> int` in src/generator/preview.py per research.md R3 — filter (`duration >= 4000ms` AND `role not in {intro, outro}`), rank by energy, role tiebreaker, start-time tiebreaker, longest fallback, degenerate fallback, ultimate fallback to 0
- [ ] T045 [US3] Wire `pick_representative_section()` into the POST handler in src/review/preview_routes.py — when `section_index` is null, call the picker against the song's sections before creating the `PreviewJob`
- [ ] T046 [US3] Run US3 tests: `pytest tests/unit/test_preview_section_picker.py -v`

**Checkpoint**: Zero-config preview produces a useful section for the 5 reference song shapes. SC-003 met. **MVP (US1 + US3) complete.**

---

## Phase 5: User Story 2 — Choose Which Section to Preview (Priority: P1)

**Goal**: Section dropdown in the Preview tab, populated from the song's analyzed sections, auto-selected to the picker's default, and overrides the null-`section_index` path when the user picks a different section.

**Independent Test**: Open Preview tab; confirm dropdown lists all N sections with `"{label} — {start}–{end} — energy {score}"`; pick a non-default section; click Preview; verify the returned `PreviewResult.section.label` matches the dropdown choice.

### Tests for User Story 2

- [ ] T047 [P] [US2] Write integration test: POST with explicit `section_index: 2` renders section 2 (not the picker's default); returned metadata names section 2 in tests/integration/test_section_preview.py
- [ ] T048 [P] [US2] Write integration test: POST with `section_index` out of range (e.g. 999) returns 400 with a clear error in tests/integration/test_section_preview.py
- [ ] T049 [P] [US2] Write integration test: POST for a song with zero sections returns 400 with an inline "no sections available" message in tests/integration/test_section_preview.py

### Implementation for User Story 2

- [ ] T050 [US2] Add the section `<select>` element to the Preview tab in src/review/static/song-workspace.html with an `id` the JS handler can target
- [ ] T051 [US2] Populate the dropdown in src/review/static/song-workspace.js on tab load — fetch the song's sections, render each as `"{label} — {start_mmss}–{end_mmss} — energy {score}"`, call the picker (client-side mirror or a tiny server endpoint) to set the auto-selected default
- [ ] T052 [US2] Update the Preview button handler in src/review/static/song-workspace.js to send `section_index: <dropdown value>` (explicit int), not null, when the user has made a selection
- [ ] T053 [US2] When a preview completes, ensure the result pane is scoped to the **current** dropdown selection — on subsequent clicks with a different dropdown value, the previous result's Download link is removed (User Story 2 acceptance #4) in src/review/static/song-workspace.js
- [ ] T054 [US2] Disable the dropdown and the Preview button with an inline "No sections available" message when the song has zero sections (User Story 2 acceptance #3) in src/review/static/song-workspace.js
- [ ] T055 [US2] Run US2 tests: `pytest tests/integration/test_section_preview.py -v -k "section_index"`

**Checkpoint**: User can explicitly pick any section. SC-003 unaffected (picker still drives the default). US1 + US2 + US3 together satisfy Priority-P1 scope.

---

## Phase 6: User Story 4 — Re-Preview on Brief Change (Priority: P2)

**Goal**: When the user edits any Brief field after a successful preview, the result pane is marked stale within 500ms. A **Re-preview** button re-runs against the current (possibly unsaved) Brief values and replaces the stale result. Debounced auto-re-preview is deferred (plan.md explicitly defers User Story 4 acceptance #4).

**Independent Test**: Preview succeeds → edit a Brief field → within 500ms the result pane shows a stale indicator and a **Re-preview** CTA → click it → new job runs → stale indicator clears on success.

### Tests for User Story 4

- [ ] T056 [P] [US4] Write integration test: back-to-back POSTs for the same song — the first job's `status` transitions to `cancelled` within 3s of the second POST; the first job's download endpoint returns 410 Gone; the second job completes normally (FR-009 supersede) in tests/integration/test_section_preview.py
- [ ] T057 [P] [US4] Write unit test: `_dispatch_lock` is held only during the supersede bookkeeping — concurrent POSTs for **different** songs do not block each other in tests/unit/test_preview_job.py
- [ ] T058 [P] [US4] Write unit test: cancelled job remains in `_preview_jobs` long enough for a stale browser tab to poll it and see `status: "cancelled"` (grace period ≥ 10 min; validate via injected clock or retention policy) in tests/unit/test_preview_job.py

### Implementation for User Story 4

- [ ] T059 [US4] Implement the supersede path in the POST handler in src/review/preview_routes.py — under `_dispatch_lock`, if `_active_by_song[hash]` exists, call `prior.cancel_token.cancel()`, remove from `_active_by_song`, leave in `_preview_jobs` for diagnostic polling
- [ ] T060 [US4] Add the four cancellation poll points inside `run_section_preview` in src/generator/preview.py — (a) immediately after `build_plan` returns, (b) between sections in the placement loop (no-op today; useful once spec 048's `section_filter` lands), (c) before `apply_transitions`, (d) before `write_xsq`
- [ ] T061 [US4] Add a Brief-change listener in src/review/static/song-workspace.js that toggles a `.stale` class on the result pane within 500ms of any Brief-field edit (SC-005); render a **Re-preview** CTA in the stale pane
- [ ] T062 [US4] Implement the **Re-preview** CTA handler in src/review/static/song-workspace.js — re-POST against the current in-memory Brief values and the current dropdown selection; on success the stale class is cleared
- [ ] T063 [US4] Add a placeholder hook for debounced auto-re-preview in src/review/static/song-workspace.js with an inline comment referencing User Story 4 acceptance #4 as deferred scope — do NOT enable it in first cut
- [ ] T064 [US4] Run US4 tests: `pytest tests/unit/test_preview_job.py tests/integration/test_section_preview.py -v -k "supersede or stale or cancel"`

**Checkpoint**: Brief edits mark preview stale; Re-preview works; supersede is clean end-to-end. SC-005 met. FR-009 fully satisfied.

---

## Phase 7: User Story 5 — In-Browser Visual Preview (Priority: P3 / Stretch) — DEFERRED

**Goal**: Canvas-based in-browser rendering of effect placements on a normalized prop-layout grid, synchronized with the audio slice.

**Status**: **Out of scope for this phase.** Per plan.md "Out-of-Scope (deferred)" and spec FR-012, in-browser visualization is P3 stretch and does not ship in the first implementation. The `.xsq` download path (US1) covers the fidelity-critical use case; a browser approximation is strictly additive and lossy.

- [ ] T065 [US5] Placeholder: add an inline comment in src/review/static/song-workspace.js noting that in-browser canvas preview (US5) is out of scope for spec 049 and will be picked up in a follow-up spec — do NOT implement the canvas rendering in this phase

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T066 Run the quickstart.md walkthrough end-to-end against a reference song — POST, poll, download, open in xLights, verify audio+effect sync at the section offset
- [ ] T067 Run the supersede section of quickstart.md — fire two back-to-back POSTs for the same song; confirm the first job ends `cancelled` and its download returns 410 Gone
- [ ] T068 Regression guard: `curl -s http://localhost:5173/api/generation-preview/<hash>` still returns its original static-summary payload (SC-007, FR-014)
- [ ] T069 Run full test suite: `pytest tests/ -v` — confirm no regressions (SC-008)
- [ ] T070 Soak test: run preview on the 5 reference songs from research.md R3 — confirm wall-clock POST-to-`done` ≤ 10s on each (SC-001) and that the picker's choice matches a human reviewer in ≥ 4 of 5 (SC-003)
- [ ] T071 Cache-eviction smoke: run 17 distinct previews back-to-back, confirm the 17th evicts the oldest `.xsq` from `_preview_dir` and the LRU size stays at 16
- [ ] T072 Verify cleanup: restart the review server and confirm `_preview_dir` is a fresh `tempfile.mkdtemp()` (no stale artifacts carried across restarts)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — verify spec-046 / spec-047 prerequisites
- **Phase 2 (Foundational)**: Depends on Phase 1 — read-only investigation of plan/xsq_writer/dispatcher
- **Phase 3 (US1)**: Depends on Phase 2 — builds the core preview machinery; picker is stubbed (not yet called)
- **Phase 4 (US3)**: Depends on Phase 3 (picker is wired into the POST handler written in Phase 3) — completes the MVP
- **Phase 5 (US2)**: Depends on Phases 3 + 4 — adds the dropdown UI on top of the working backend
- **Phase 6 (US4)**: Depends on Phase 3 (supersede touches the dispatcher and cancellation poll points) — can start after US1 backend stabilizes
- **Phase 7 (US5)**: **Deferred** — placeholder only
- **Phase 8 (Polish)**: Depends on Phases 3, 4, 5, 6

### User Story Dependencies

- **US1 (One-click preview)**: Foundational — all other stories build on it
- **US3 (Auto-pick)**: Depends on US1 — picker is called from the POST handler US1 creates. US1 + US3 form the MVP.
- **US2 (Dropdown)**: Depends on US1 + US3 — the dropdown's default value is the picker's choice
- **US4 (Re-preview on Brief change)**: Depends on US1 — supersede is bookkeeping around the US1 dispatcher; stale marker is frontend-only but needs the result pane from US1
- **US5 (In-browser canvas)**: Explicitly deferred — placeholder task T065 only

### Parallel Opportunities

- T008–T012 (US1 unit tests) can all run in parallel (same file, different test functions)
- T013–T015 (US1 integration tests) can all run in parallel
- T035–T043 (US3 picker tests) can all run in parallel (same file, different fixtures)
- T047–T049 (US2 integration tests) can all run in parallel
- T056–T058 (US4 concurrency tests) can all run in parallel
- Implementation of `xsq_writer.py` kwargs (T022, T023) can run in parallel with `preview.py` dataclasses (T017, T018) — different files
- Frontend tasks in Phases 3, 5, 6 (song-workspace.html / song-workspace.js edits) must be sequenced per phase but are independent of backend test runs

---

## Implementation Strategy

### MVP First (US1 + US3)

1. Complete Phase 1: Setup (T001–T003) — confirm prerequisites
2. Complete Phase 2: Foundational (T004–T007) — read-only audit
3. Complete Phase 3: US1 — One-click preview end-to-end (T008–T034)
4. Complete Phase 4: US3 — Representative-section picker (T035–T046)
5. **STOP and VALIDATE**: Run the quickstart.md walkthrough. Preview a reference song → download `.xsq` → open in xLights → confirm audio+effect sync at the section offset. This is the MVP.

### Incremental Delivery

1. Setup + Foundational → understand spec-046/047 surface and pipeline boundaries
2. US1 (one-click, null section_index) → backend + basic UI (MVP backend)
3. US3 (picker) → MVP zero-config default works (MVP complete)
4. US2 (dropdown) → user-driven section choice
5. US4 (stale marker + supersede + Re-preview) → Brief-iteration loop closes
6. Polish → full regression + soak on 5 reference songs
7. US5 → **deferred**; placeholder comment only

### Risk Areas (from plan.md Technical Context)

1. **Cancellation correctness**: The four poll points in T060 must match the stages in research.md R1. If a stage is added or renamed later, add a poll point in the same commit.
2. **XSQ offset compat**: T023 writes `<mediaOffset>` which is an xLights 2024+ attribute. Pre-2024 xLights silently ignores it — this is a documented limitation, not a bug (research.md R2).
3. **Picker quality**: SC-003 requires 4-of-5 human agreement. The fixtures in T035–T043 must reflect the five reference-song shapes from research.md R3. Failing any of these indicates the ranking rules need tuning before shipping.

---

## Notes

- [P] tasks = different files OR independent test functions in the same file
- [Story] label maps task to specific user story (US1, US2, US3, US4, US5)
- US1 + US3 form the MVP — zero-config one-click preview with a useful default section
- US2 and US4 extend the MVP but do not block it
- US5 (in-browser canvas) is explicitly deferred to a follow-up spec per plan.md "Out-of-Scope"
- The `build_plan(section_filter=...)` parameter is also deferred — first-cut post-hoc filter in `run_section_preview` is acceptable (plan.md Change 5)
- Cancellation is cooperative only — no hard thread-kill. Orphan-work window between poll points is ≤ 3s and acceptable given the 10s overall budget
- LRU cache is bounded at 16 entries; eviction deletes the evicted `.xsq` from `_preview_dir`
- `_preview_dir` is a fresh `tempfile.mkdtemp()` per server start — no persistence across restarts (FR-010)
