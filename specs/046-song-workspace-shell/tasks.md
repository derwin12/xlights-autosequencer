# Tasks: Song Workspace Shell (046)

**Input**: Design documents from `/specs/046-song-workspace-shell/`
**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new dependencies. Confirm existing infrastructure the workspace will consume.

- [X] T001 Verify the `/generate/<hash>/history` endpoint exists in `src/review/generate_routes.py` — locate the current `status == "complete"` filter and note line numbers for the Phase 3 extension
- [X] T002 Verify `/analysis?hash=<source_hash>` resolves hash-based analysis lookups in `src/review/server.py` (around line 951 per plan.md) — no changes needed, just confirm the contract the Analysis tab relies on
- [X] T003 Verify `Library().find_by_hash()` exists in `src/library.py` — the `/song/<source_hash>` route's 404 gate depends on it
- [X] T004 Verify spec 045's centralized `openSong()` helper exists in `src/review/static/dashboard.js` (around lines 434–446 per plan.md) — this is the sole edit point for Change 5

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Inventory `app.js` globals and DOM lookups before the factory refactor; seed the workspace static files so later tasks have files to edit.

- [X] T005 Grep `src/review/static/app.js` for every `document.getElementById` and `document.querySelector` call — produce an inventory comment block or scratch list identifying which ones move to `rootEl.querySelector` and which stay on `window`/`document` (keyboard shortcut bindings)
- [X] T006 Catalog module-level state in `src/review/static/app.js` (lines 5–11, 36–80 per research.md §1) — list `tracks`, `durationMs`, `focusIndex`, `pxPerSec`, DOM handles, etc. that must move into the factory closure
- [X] T007 Create empty stub files `src/review/static/song-workspace.html`, `src/review/static/song-workspace.js`, `src/review/static/song-workspace.css` so subsequent tasks can edit in place

**Checkpoint**: Refactor surface area understood; new static files exist as empty shells.

---

## Phase 3: User Story 1 — One Home Per Song (Priority: P1) MVP

**Goal**: `/song/<source_hash>` loads a four-tab shell (Analysis / Brief / Preview / Generate & Download) with the Analysis tab active by default, URL-fragment tab routing, and state preservation across tab switches.

**Independent Test**: Navigate to `/song/<source_hash>` on an analyzed song. Confirm four tabs render in order, Analysis is active by default, clicking tabs updates the URL fragment, and a deep link to `#generate` activates Generate on first paint.

### Tests for User Story 1

- [X] T008 [P] [US1] Write route test: GET `/song/<known_hash>` returns 200 with the `song-workspace.html` body in `tests/unit/test_song_workspace_route.py`
- [X] T009 [P] [US1] Write route test: GET `/song/bogus-hash-1234` returns 404 with a message pointing back to the library view in `tests/unit/test_song_workspace_route.py`
- [X] T010 [P] [US1] Write route test: existing `/timeline` route still serves `index.html` unchanged (no regression) in `tests/unit/test_song_workspace_route.py`
- [X] T011 [P] [US1] Write route test: existing `/phonemes-view` and `/story-review` routes still return their original static files unchanged in `tests/unit/test_song_workspace_route.py`

### Implementation for User Story 1

- [X] T012 [US1] Add the `/song/<source_hash>` route to `src/review/server.py` beside `/library-view` / `/timeline` — resolve via `Library().find_by_hash(source_hash)`, `abort(404, description="Song not found in library")` on miss, else `send_from_directory(app.static_folder, "song-workspace.html")`
- [X] T013 [US1] Build the workspace HTML shell in `src/review/static/song-workspace.html` — navbar include, header region (title, duration, analysis status, layout-ready banner slot), `<nav role="tablist">` with four tab buttons, and four `<section role="tabpanel">` panels with stable ids `#panel-analysis`, `#panel-brief`, `#panel-preview`, `#panel-generate`
- [X] T014 [US1] Link `/navbar.js`, `/song-workspace.css`, `/song-workspace.js` from `song-workspace.html` — do NOT include `/app.js` in the initial HTML (the timeline factory script loads separately on Analysis-tab first activation)
- [X] T015 [US1] Add tab-strip + panel layout styles to `src/review/static/song-workspace.css` — tab buttons, active-tab indicator, hidden panels (use `[hidden]` attribute), reuse navbar/theme tokens from existing stylesheets
- [X] T016 [US1] In `src/review/static/song-workspace.js`, on `DOMContentLoaded` parse `source_hash` from `location.pathname.split('/').pop()` and stash it for later consumers
- [X] T017 [US1] In `src/review/static/song-workspace.js`, implement tab switching: click handler toggles `hidden` on panels, updates ARIA `aria-selected`, and updates the URL fragment via `history.replaceState(null, '', '#' + tabId)` (NOT `pushState` — browser Back must exit the workspace, edge case in spec)
- [X] T018 [US1] On page load, in `src/review/static/song-workspace.js`, honor `location.hash` — activate the matching tab on first paint (`#analysis`, `#brief`, `#preview`, `#generate`); fallback to Analysis for unknown fragments (per edge case: `#bogus` falls back to default)
- [X] T019 [US1] In `src/review/static/song-workspace.js`, fetch the library entry (e.g. `GET /library` and find the matching `source_hash`, or reuse existing helper) and populate the header: title, duration, analysis status
- [X] T020 [US1] Ensure tab state preservation in `src/review/static/song-workspace.js` — panels use `hidden` attribute only (no innerHTML swap, no detach/reattach), so scroll position and DOM state persist across switches for the lifetime of the page load
- [X] T021 [US1] Run route tests: `python3 -m pytest tests/unit/test_song_workspace_route.py -v`

**Checkpoint**: Workspace shell loads, four tabs switch cleanly, URL fragment syncs, deep links work. SC-001 and SC-006 met.

---

## Phase 4: User Story 2 — Analysis Tab Wraps the Existing Timeline (Priority: P1)

**Goal**: The Analysis tab mounts the existing timeline UI (waveform, per-track lanes, synchronized playback) via a factory-wrapped `app.js`. `/timeline` continues to work standalone mounted at full-page scale.

**Independent Test**: On `/song/<hash>` the Analysis tab shows the same waveform, track lanes, playback controls, and focus behavior as `/timeline?hash=<hash>`. Playback works. Switching tabs and returning does not re-fetch analysis JSON or re-decode audio.

### Tests for User Story 2

- [X] T022 [P] [US2] Write integration test: after GET `/song/<hash>`, assert the HTML body contains a `#panel-analysis` element and references `/app.js` is loadable (smoke test only — DOM mount is exercised manually in quickstart) in `tests/integration/test_song_workspace_flow.py`
- [X] T023 [P] [US2] Write route test: `/timeline?hash=<hash>` still returns `index.html` body containing `#timeline-root` mount point in `tests/unit/test_song_workspace_route.py`

### Implementation for User Story 2

- [X] T024 [US2] Wrap the body of `src/review/static/app.js` in `function createTimeline({ rootEl, hashParam = null }) { ... }` and expose `window.createTimeline = createTimeline` — per research.md §3 chosen design
- [X] T025 [US2] Move every module-level state variable catalogued in T006 (`tracks`, `durationMs`, `focusIndex`, `pxPerSec`, `dragSrcIndex`, `phonemeLayers`, `songSegments`, `activeStemFilter`, etc.) into the factory closure in `src/review/static/app.js`
- [X] T026 [US2] Replace every `document.getElementById('foo')` / `document.querySelector(...)` inventoried in T005 with `rootEl.querySelector('#foo')` inside the factory in `src/review/static/app.js`
- [X] T027 [US2] Move creation/lookup of `<audio id="player">` into the factory so the element lives under `rootEl` in `src/review/static/app.js` — ensure `player.src` still targets `/audio`
- [X] T028 [US2] Change the module-level `init()` call at the bottom of `src/review/static/app.js` to an auto-mount guard: `if (document.getElementById('timeline-root')) { createTimeline({ rootEl: ..., hashParam: new URLSearchParams(location.search).get('hash') }); }`
- [X] T029 [US2] Update `init()` inside the factory in `src/review/static/app.js` to use `hashParam ? `/analysis?hash=${hashParam}` : '/analysis'` for the analysis fetch
- [X] T030 [US2] Refactor `src/review/static/index.html` into a thin full-page wrapper: keep the navbar + toolbar, replace the old per-id body with a single `<div id="timeline-root">` that owns the toolbar, `#main`, `<audio>`, `#legend-panel`, `#status` as children — the factory populates this element
- [X] T031 [US2] Add a small "Open in workspace" link in `src/review/static/index.html` pointing to `/song/<source_hash>#analysis` when a `hash` URL param is resolvable (FR-012 affordance)
- [X] T032 [US2] In `src/review/static/song-workspace.js`, lazy-load `/app.js` on first Analysis-tab activation (insert a `<script src="/app.js">` tag into the document head if not already present) and call `createTimeline({ rootEl: document.getElementById('panel-analysis'), hashParam: sourceHash })` exactly once — subsequent activations are no-ops
- [X] T033 [US2] In `src/review/static/song-workspace.js`, render the Analysis empty-state ("No analysis available — re-run analysis to populate this tab") into `#panel-analysis` when the library entry indicates analysis is missing or errored (US2 acceptance scenario 5)
- [X] T034 [US2] Leave keyboard shortcut bindings (`Space`, `Ctrl+-`, `Ctrl+0`, `ArrowUp/Down`) on `window` inside the factory in `src/review/static/app.js` — Phase 2 only mounts one timeline; per research.md §3 this is intentional
- [X] T035 [US2] Run route tests: `python3 -m pytest tests/unit/test_song_workspace_route.py -v`

**Checkpoint**: Analysis tab renders full timeline UI; `/timeline` still works standalone; no regression. SC-002, SC-005, SC-009 met.

---

## Phase 5: User Story 3 — Generate & Download Moves Into the Workspace (Priority: P1)

**Goal**: The Generate tab posts to `/generate/<hash>`, polls status, renders a download link on completion, shows a "Previous renders" list, and re-attaches to an in-flight job on mount by extending `/generate/<hash>/history` to include `running`/`queued` jobs.

**Independent Test**: On an analyzed song, open the Generate tab, click Generate, watch progress, download the `.xsq`, reload — the completed render appears in "Previous renders". Start another generation, reload mid-run — the tab immediately shows progress UI and resumes polling the same `job_id`.

### Tests for User Story 3

- [X] T036 [P] [US3] Write unit test: seed `_jobs` with one `complete`, one `running`, one `failed` for the same `source_hash`; assert `/generate/<hash>/history` returns all three sorted newest-first in `tests/unit/test_generate_routes.py` (or the existing equivalent test file)
- [X] T037 [P] [US3] Write unit test: the `running` entry in the history payload has NO `download_url` field; the `complete` entry has a `download_url` pointing to `/generate/<hash>/download/<job_id>`; the `failed` entry has an `error` field in `tests/unit/test_generate_routes.py`
- [X] T038 [P] [US3] Write integration test: full flow — GET `/song/<hash>`, POST `/generate/<hash>`, poll `/generate/<hash>/status?job_id=...` until `complete`, GET `/generate/<hash>/download/<job_id>` returns an `.xsq` artifact in `tests/integration/test_song_workspace_flow.py`
- [X] T039 [P] [US3] Write integration test: seed a `running` job for `<hash>`; assert the initial `/generate/<hash>/history` payload on a fresh workspace mount contains the running entry with `status: "running"` in `tests/integration/test_song_workspace_flow.py`

### Implementation for User Story 3

- [X] T040 [US3] Extend `generation_history` in `src/review/generate_routes.py` — remove the `status == "complete"` filter, select all jobs for the `source_hash`, sort by `created_at` descending (per plan.md Change 2 diff)
- [X] T041 [US3] In the serialized dict in `src/review/generate_routes.py`, emit every status value (`pending`, `running`, `complete`, `failed`) and add conditional fields: `download_url` only when `status == "complete"`, `error` only when `status == "failed"`
- [X] T042 [US3] In `src/review/static/song-workspace.js`, on Generate-tab first activation, GET `/generate/<source_hash>/history` once and render the "Previous renders" list from entries with `status == "complete"` (timestamp, config summary, re-download link) — sorted newest-first
- [X] T043 [US3] In `src/review/static/song-workspace.js`, inspect the history payload for any entry with `status in {"pending", "running"}` — if found, adopt that `job_id` and enter the polling state immediately (progress UI visible, Generate button hidden/disabled)
- [X] T044 [US3] In `src/review/static/song-workspace.js`, render the primary Generate button, progress region (spinner + stage label), download region, and history list inside `#panel-generate`
- [X] T045 [US3] Wire the Generate button click handler in `src/review/static/song-workspace.js` — POST to `/generate/<source_hash>`, capture the `job_id`, disable the button, show the progress region
- [X] T046 [US3] Implement polling in `src/review/static/song-workspace.js` — `setInterval(1500)` calling `/generate/<source_hash>/status?job_id=...`; on `status == "complete"`, clear the interval, render the Download link (prominent, visually dominant) pointing to `/generate/<source_hash>/download/<job_id>`; on `status == "failed"`, surface the `error` message and re-enable Generate
- [X] T047 [US3] In `src/review/static/song-workspace.js`, fetch `/generate/settings` (or the existing layout-status endpoint) and render the layout-gate banner / disable the Generate button with a tooltip linking to the Zone A setup page when layout is not configured (FR-008)
- [X] T048 [US3] Ensure the history/settings/analysis fetches each fire at most once per page load in `src/review/static/song-workspace.js` (SC-005) — guard with per-tab `_mounted` flags
- [X] T049 [US3] Run unit and integration tests: `python3 -m pytest tests/unit/test_generate_routes.py tests/integration/test_song_workspace_flow.py -v`

**Checkpoint**: Full generate flow works inside the workspace with no external page navigation; history + in-flight re-attach working. SC-003, SC-004 met.

---

## Phase 6: User Story 4 — Brief Tab Placeholder (Priority: P2)

**Goal**: The Brief tab exists as a stable stub referencing feature 047 as the follow-up. No form submits, no `GenerationConfig` mutation.

**Independent Test**: Click the Brief tab on any analyzed song's workspace — a "Coming soon — feature 047" placeholder appears, no network activity, no form fields.

### Implementation for User Story 4

- [X] T050 [US4] Add the Brief panel placeholder markup inside `#panel-brief` in `src/review/static/song-workspace.html` — copy: "Coming soon — the Brief tab will be filled in by feature 047 (creative brief form)." Reference the strategy doc if useful
- [X] T051 [US4] Confirm no JS in `src/review/static/song-workspace.js` touches `#panel-brief` beyond tab-switch visibility toggling — the panel is pure static HTML per FR-004 and SC-007

**Checkpoint**: Brief tab renders a clean placeholder. SC-007 structural contract preserved.

---

## Phase 7: User Story 5 — Preview Tab Placeholder (Priority: P3)

**Goal**: The Preview tab exists as a stable stub referencing feature 049 as the follow-up. No audio loads, no background polling, no render calls.

**Independent Test**: Click the Preview tab on any analyzed song's workspace — a "Coming soon — feature 049" placeholder appears, no network activity, no audio.

### Implementation for User Story 5

- [X] T052 [US5] Add the Preview panel placeholder markup inside `#panel-preview` in `src/review/static/song-workspace.html` — copy: "Coming soon — feature 049 will render short-section previews here." Name the intended capability briefly
- [X] T053 [US5] Confirm no JS in `src/review/static/song-workspace.js` touches `#panel-preview` beyond tab-switch visibility toggling — no audio element, no polling, per FR-005 and SC-008

**Checkpoint**: Preview tab renders a clean placeholder. SC-008 structural contract preserved.

---

## Phase 8: Dashboard Redirect (Cross-Cutting for US1)

**Goal**: The Phase 1 "Open" button always lands users on `/song/<source_hash>`.

- [X] T054 Update `openSong()` in `src/review/static/dashboard.js` (around lines 434–446 per plan.md Change 5) — replace the three-branch switch with unconditional `window.location.href = '/song/' + encodeURIComponent(hash)`
- [X] T055 Leave the `openSong()` signature intact (keep `tool` and `storyPath` parameters) so existing call sites in `src/review/static/dashboard.js` (around lines 165, 273–276, 549) keep working — parameter cleanup is a documented follow-up, not Phase 2 scope

---

## Phase 9: Legacy Route Affordances (FR-012)

**Goal**: `/timeline`, `/phonemes-view`, `/story-review` continue to work; when the source_hash is resolvable, a small "Open in workspace" link points back to `/song/<hash>#analysis`.

- [X] T056 [P] Confirm/add the "Open in workspace" link in `src/review/static/index.html` (done in T031 — verify)
- [X] T057 [P] Add the "Open in workspace" link to the phonemes view HTML (`src/review/static/phonemes.html` or equivalent) when the `hash` URL param resolves via `/library` — link targets `/song/<hash>#analysis`
- [X] T058 [P] Add the "Open in workspace" link to the story-review view HTML when the story's `source_hash` resolves — link targets `/song/<hash>#analysis`

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T059 Run the full test suite: `python3 -m pytest tests/ -v` and verify no regressions in analysis, generation, or existing review routes (SC-009)
- [X] T060 Execute `specs/046-song-workspace-shell/quickstart.md` steps 1–12 manually against a dev server with an analyzed song — confirm all twelve steps produce the expected result
- [X] T061 Smoke-check the browser console on `/song/<hash>` and `/timeline?hash=<hash>` — no errors from the `app.js` factory refactor (verifies research.md §6 risk mitigation: no lingering `document.`-rooted lookups)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — immediate
- **Phase 2 (Foundational)**: Depends on Phase 1 — inventory + stub files
- **Phase 3 (US1 Shell)**: Depends on Phase 2 — delivers the 4-tab shell + route
- **Phase 4 (US2 Analysis)**: Depends on Phase 3 — Analysis tab mounts into the shell; also depends on the `app.js` factory refactor
- **Phase 5 (US3 Generate)**: Depends on Phase 3 — Generate tab mounts into the shell; history route change is independent
- **Phase 6 (US4 Brief)**: Depends on Phase 3 — markup swap only
- **Phase 7 (US5 Preview)**: Depends on Phase 3 — markup swap only
- **Phase 8 (Dashboard redirect)**: Depends on Phase 3 — the target route must exist
- **Phase 9 (Legacy affordances)**: Depends on Phase 3 — the target route must exist
- **Phase 10 (Polish)**: Depends on all desired user stories

### User Story Dependencies

- **US1 (Shell)**: Foundational only — MVP target
- **US2 (Analysis mount)**: Depends on US1; independent of US3
- **US3 (Generate tab + history)**: Depends on US1; can run in parallel with US2 (different files: `generate_routes.py` + `#panel-generate` code paths vs. `app.js` refactor)
- **US4 (Brief stub)**: Depends on US1; independent
- **US5 (Preview stub)**: Depends on US1; independent

### Parallel Opportunities

- T008, T009, T010, T011 can all run in parallel (same test file, different test functions)
- T022, T023 can run in parallel
- T036, T037, T038, T039 can run in parallel (different test functions / files)
- After Phase 3 completes, Phases 4, 5, 6, 7, 8 can proceed in parallel (different files or different regions of `song-workspace.js`/`song-workspace.html`)
- T056, T057, T058 can run in parallel (different HTML files)

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — all P1)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T007)
3. Complete Phase 3: US1 — Shell + route + tabs + fragment routing (T008–T021)
4. **STOP and VALIDATE**: `/song/<hash>` loads, four tabs switch, URL fragment syncs, 404 works
5. Complete Phase 4: US2 — `app.js` factory refactor + Analysis-tab mount (T022–T035) — in parallel with Phase 5 if a second engineer is available
6. Complete Phase 5: US3 — history extension + Generate-tab wiring + polling (T036–T049)
7. **STOP and VALIDATE**: Full workspace usable end-to-end — open song → see timeline → start generation → download `.xsq`

### Incremental Delivery

1. Setup + Foundational → infrastructure understood
2. US1 (shell) → the structural container Phase 3/5 depend on (spec 047, 049 future)
3. US2 (Analysis) + US3 (Generate) in parallel → the two P1 functional tabs
4. US4 (Brief stub) + US5 (Preview stub) → quick markup adds, lock in tab order
5. Dashboard redirect + legacy affordances → route users into the workspace as the default path
6. Polish → full regression + quickstart validation

---

## Notes

- [P] tasks = different files or independent test functions
- [Story] label maps task to a specific user story
- US1 is the structural MVP — without it the other stories have nowhere to mount
- US2 and US3 together deliver the user-visible Phase 2 value; ship them together if possible
- US4 and US5 are deliberate stubs that lock in tab order for specs 047 and 049 (SC-007, SC-008 are the contract)
- The `app.js` factory refactor (T024–T029) is the single largest risk area — verify no lingering `document.`-rooted DOM lookups via the T005 inventory and the T061 smoke check
- No generator pipeline changes (FR-014); no new `GenerationConfig` flags; Phase 2 is organizational
