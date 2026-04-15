# Tasks: Web UX Overhaul — Phase 1 Wayfinding (045)

**Input**: Design documents from `/specs/045-web-ux-wayfinding/`
**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new files or dependencies. Confirm the existing plumbing referenced by the plan is where the plan says it is.

- [X] T001 Verify `src/settings.py` exposes `get_layout_path()` returning `Path | None` — confirm by reading `src/settings.py` around line 37
- [X] T002 Verify `src/review/generate_routes.py` exposes the in-memory `_jobs` dict with `source_hash`, `status`, and `created_at` fields used by `/generate/<hash>/history` — read `src/review/generate_routes.py` around line 222
- [X] T003 Verify the current `/library` shape by reading `src/review/server.py` lines 447–570 (`library_index()` and `_enrich()`) — confirm `source_hash`, `source_file_exists`, `analysis_exists`, `has_story`, `has_phonemes` are already emitted

**Checkpoint**: Server-side prerequisites for the `/library` payload extension confirmed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the `/library` response extension before any client code that depends on it. The dashboard JS in Phases 3–7 reads these four fields from every entry.

### Tests for Foundational

- [X] T004 [P] Write integration test: GET `/library` returns entries with `layout_configured` (bool), `last_generated_at` (ISO-8601 string or null), `has_story` (bool), and `is_stale` (bool) fields present on every entry, in tests/integration/test_library_payload.py
- [X] T005 [P] Write integration test: when `src.settings.get_layout_path()` returns None, every entry in `/library` has `layout_configured: false`; when it returns an existing Path, every entry has `layout_configured: true`, in tests/integration/test_library_payload.py
- [X] T006 [P] Write integration test: when the source file's recomputed MD5 equals `source_hash`, `is_stale` is false; when the source file is missing, `is_stale` is false (skipped), in tests/integration/test_library_payload.py

### Implementation for Foundational

- [X] T007 Compute `layout_configured` once per request at the top of `library_index()` in src/review/server.py by calling `src.settings.get_layout_path()` and checking `.exists()`; store in a local bool
- [X] T008 Extend `_enrich(e)` in src/review/server.py (~lines 469–570) to set `entry["layout_configured"] = layout_configured` from the enclosing scope on every row
- [X] T009 Extend `_enrich(e)` in src/review/server.py to compute `last_generated_at` by scanning `src.review.generate_routes._jobs` for the newest job with `source_hash == e.source_hash` and `status == "complete"`; emit ISO-8601 or null
- [X] T010 Extend `_enrich(e)` in src/review/server.py to compute `is_stale` by recomputing the source file MD5 and comparing to `e.source_hash`; skip (false) when source file is missing
- [X] T011 Add an in-process cache keyed by `(source_path, mtime, size)` for the MD5 recomputation in src/review/server.py to keep `/library` under 100ms for large libraries (research.md Decision 3)
- [X] T012 Confirm `has_story` is already emitted by `_enrich()` (plan.md line 96); no code change — add an inline comment in src/review/server.py noting that spec 045 consumes this field
- [X] T013 Run tests: `python3 -m pytest tests/integration/test_library_payload.py -v`

**Checkpoint**: `/library` now serves the four fields the dashboard needs. Every user-story phase below depends on this.

---

## Phase 3: User Story 1 — Stateful Per-Song Workflow Strip (Priority: P1) MVP

**Goal**: The five-step strip becomes a four-step strip (Upload → Review → Story → Generate) that reflects the expanded row's real state with four visual states (complete / active / incomplete / blocked / neutral).

**Independent Test**: Expand an analyzed+generated row with a configured layout — steps 1–4 render `complete`. Expand an analyzed-never-generated row with layout configured — step 4 renders `active`. Clear layout — step 4 renders `blocked`.

### Tests for User Story 1

- [X] T014 [P] [US1] Write JS unit-style test fixture file tests/ui/fixtures/strip_states.json with 5 synthetic `/library` entries covering: fresh upload, analyzed-no-story, analyzed-with-story-never-generated, fully generated, layout-missing
- [X] T015 [US1] Write verification note in tests/ui/strip_states_README.md documenting the expected `data-state` attribute per step for each fixture row (serves as the acceptance oracle — no JS runner required)

### Implementation for User Story 1

- [X] T016 [US1] Rewrite the workflow strip in src/review/static/dashboard.html (lines 67–94) to four `.workflow-step` divs with `data-step` values `upload | review | story | generate` — remove the `layout` step
- [X] T017 [US1] Add new function `applyStripState(entry)` in src/review/static/dashboard.js that sets `data-state={complete|active|incomplete|blocked}` on each `.workflow-step` per the rules in plan.md Change 2
- [X] T018 [US1] Add a `resetStripState()` helper in src/review/static/dashboard.js that clears all `data-state` attributes so the strip renders neutral grey when no row is expanded
- [X] T019 [US1] Wire `applyStripState(entry)` into the row-expand handler in src/review/static/dashboard.js (~line 209); wire `resetStripState()` into the collapse path
- [X] T020 [US1] Add click handlers on `.workflow-step` in src/review/static/dashboard.js so steps in `complete` or `active` state navigate to their destination (step 2 → `openSong(hash)`, step 3 → `/story-review`, step 4 → inline generate action); `incomplete` and `blocked` steps remain non-clickable
- [X] T021 [US1] Add tooltip text (via `title` attribute or `data-tooltip`) on `incomplete` and `blocked` steps in src/review/static/dashboard.js explaining what is missing
- [X] T022 [P] [US1] Add CSS selectors `.workflow-step[data-state="complete"]`, `[data-state="active"]`, `[data-state="incomplete"]`, `[data-state="blocked"]` in src/review/static/dashboard.css with visually-distinct styling (filled/highlighted/grey/warning-tinted)
- [X] T023 [P] [US1] Add `.workflow-step[data-state="blocked"]` cursor and hover-tooltip styling in src/review/static/dashboard.css
- [X] T024 [US1] Manually walk quickstart.md section 1 "Strip is stateful" to confirm the expanded/collapsed transitions render correctly

**Checkpoint**: Strip is stateful. FR-001, FR-002, FR-003, FR-006 (strip portion) met. SC-001 met.

---

## Phase 4: User Story 2 — Layout Groups Promoted to Zone A Setup Gate (Priority: P1)

**Goal**: A setup banner appears above the library when layout is unconfigured; all Generate controls disable with a tooltip; banner disappears when layout is configured.

**Independent Test**: Clear layout settings — banner appears, Generate controls disabled. Configure layout via `/grouper` — banner gone, Generate controls enabled.

### Tests for User Story 2

- [X] T025 [P] [US2] Write integration test: POST `/open-from-library` plus GET `/library` with a cleared `layout_path` returns `layout_configured: false` on every entry, in tests/integration/test_library_payload.py
- [X] T026 [P] [US2] Extend the tests/ui/strip_states_README.md acceptance oracle to document banner visibility and Generate-disabled state per fixture row

### Implementation for User Story 2

- [X] T027 [US2] Insert `<div id="zone-a-banner" class="zone-a-banner" hidden>…</div>` between `#progress-section` and `#workflow-guide` in src/review/static/dashboard.html with copy "Set up your layout before generating sequences" and a primary button "Set Up Layout" linking to `/grouper`
- [X] T028 [US2] Add function `renderZoneABanner(entries)` in src/review/static/dashboard.js that toggles the banner's `hidden` attribute based on `entries[0]?.layout_configured`
- [X] T029 [US2] Call `renderZoneABanner(entries)` from the `fetchLibrary()` success path in src/review/static/dashboard.js (near the existing `renderTable` call)
- [X] T030 [US2] Set `document.body.dataset.layoutConfigured = entries[0]?.layout_configured ? "true" : "false"` in src/review/static/dashboard.js so CSS can drive disabled-state for Generate controls without per-button JS
- [X] T031 [P] [US2] Add `.zone-a-banner` styling (prominent panel, primary button, appropriate color) in src/review/static/dashboard.css
- [X] T032 [P] [US2] Add CSS rules `body[data-layout-configured="false"] [data-action="generate"]`, `body[data-layout-configured="false"] .workflow-step[data-step="generate"]`, etc., that visually disable Generate controls and surface a tooltip via `::after` or `title` in src/review/static/dashboard.css
- [X] T033 [US2] Ensure disabled Generate controls in src/review/static/dashboard.js short-circuit their click handler when `document.body.dataset.layoutConfigured !== "true"` (belt-and-braces — CSS hides, JS prevents)
- [X] T034 [US2] Manually walk quickstart.md section 2 "Zone A banner appears when layout is missing" including the clear/re-configure cycle

**Checkpoint**: Zone A gate enforced. FR-004, FR-005, FR-006 (banner portion) met. SC-002 met.

---

## Phase 5: User Story 3 — Single Primary "Open" Action with Overflow Menu (Priority: P1)

**Goal**: The seven-button detail panel collapses to one primary "Open" + overflow menu with the remaining six actions. All existing destinations preserved. `openSong(hash)` is the single retargeting point for spec 046.

**Independent Test**: Expand a row — one "Open" button + one kebab. Clicking Open routes to `/timeline?hash=<md5>`. Overflow menu contains the six legacy actions, dismisses on outside-click/Escape.

### Tests for User Story 3

- [X] T035 [P] [US3] Extend tests/ui/strip_states_README.md to document: detail panel must contain exactly one `data-action="open"` primary button and exactly one `.overflow-menu` with six `role="menuitem"` children
- [X] T036 [P] [US3] Write a grep-based acceptance check note in tests/ui/strip_states_README.md: `grep -c 'function openSong' src/review/static/dashboard.js` must return 1 (the canonical helper for spec 046 retargeting — SC-004, SC-008)

### Implementation for User Story 3

- [X] T037 [US3] Rewrite `<template id="detail-template">` `.detail-actions` in src/review/static/dashboard.html (lines 134–160) to the primary/overflow structure from plan.md Change 4
- [X] T038 [US3] In `renderDetail` (src/review/static/dashboard.js ~line 241) add a new `case 'open':` to the `data-action` switch that calls `openSong(entry.source_hash)`
- [X] T039 [US3] Canonicalize the existing `openSong(hash, tool, storyPath)` in src/review/static/dashboard.js (lines 434–446) to `openSong(hash)` that always routes to `/timeline?hash=<hash>` after the `/open-from-library` POST
- [X] T040 [US3] Rename the legacy three-arg variant to `openSongTool(hash, tool, storyPath)` in src/review/static/dashboard.js; update all callers currently using the old signature (row-click ~line 165, fetch-success ~line 549, overflow-menu `story`/`phonemes` actions)
- [X] T041 [US3] Wire the overflow-menu toggle in src/review/static/dashboard.js: kebab click toggles `aria-expanded` and the `hidden` attribute on `.overflow-menu`
- [X] T042 [US3] Add a document-level `click` listener in src/review/static/dashboard.js that closes any open `.overflow-menu` when the click target is outside the menu (FR-010)
- [X] T043 [US3] Add a document-level `keydown` listener in src/review/static/dashboard.js that closes any open `.overflow-menu` on `Escape` (FR-010)
- [X] T044 [P] [US3] Add `.btn-open` primary styling, `.btn-kebab`, `.overflow-wrap`, `.overflow-menu`, and menu-item hover states in src/review/static/dashboard.css
- [X] T045 [US3] Manually walk quickstart.md section 3 "Open + overflow" to confirm Open routes correctly, overflow contains the six actions, and dismiss behavior works

**Checkpoint**: Detail panel reshaped. FR-007, FR-008, FR-009, FR-010 met. SC-003, SC-004, SC-008 met.

### P1 MVP Gate

**After completing Phases 3–5**: the P1 block is shippable — stateful strip, Zone A gate, single Open action. US4 (badges) and US5 (back-to-library) are additive polish.

---

## Phase 6: User Story 4 — Status Badges on Library Rows (Priority: P2)

**Goal**: Each row displays a lifecycle badge (Analyzed / Generated / Stale) without requiring expansion. `Briefed` reserved but unused.

**Independent Test**: Library with one analyzed, one generated, one stale row displays the correct badge on each.

### Tests for User Story 4

- [X] T046 [P] [US4] Extend tests/ui/strip_states_README.md acceptance oracle to document the badge vocabulary per fixture row and the replacement rules (Generated replaces Analyzed; Stale replaces both)
- [X] T047 [P] [US4] Add a grep check note in tests/ui/strip_states_README.md: `grep 'Briefed' src/review/static/dashboard.js` must return no matches in Phase 1 (FR-011)

### Implementation for User Story 4

- [X] T048 [US4] Extend `renderBadges(e)` in src/review/static/dashboard.js (lines 229–238) to prepend lifecycle badges computed from `is_stale`, `last_generated_at`, and `analysis_exists` per plan.md Change 6
- [X] T049 [P] [US4] Add CSS classes `.badge-analyzed`, `.badge-generated`, `.badge-stale` in src/review/static/dashboard.css next to the existing `.badge-stems`/`.badge-phonemes`/`.badge-story` block
- [X] T050 [US4] Manually walk quickstart.md section 4 "Lifecycle badges" — confirm each badge appears on the correct row and `Briefed` never renders

**Checkpoint**: Lifecycle badges visible on library rows. FR-011 met. SC-006 met.

---

## Phase 7: User Story 5 — Navigation Consistency from Deep Pages Back to Library (Priority: P3)

**Goal**: `/timeline`, `/story-review`, `/phonemes-view`, `/grouper`, `/themes/`, `/variants/` all display a consistent "Back to Library" breadcrumb.

**Independent Test**: Visit each of the six deep pages — each shows a breadcrumb whose "Song Library" link routes to `/`.

### Tests for User Story 5

- [X] T051 [P] [US5] Add a quickstart-style route-reachability check to tests/ui/strip_states_README.md: the six routes (`/timeline`, `/story-review`, `/phonemes-view`, `/grouper`, `/themes/`, `/variants/`) must all return 200 OK (SC-005)

### Implementation for User Story 5

- [X] T052 [US5] Extend `SONG_TOOL_PAGES` in src/review/static/navbar.js (lines 16–21) to include `/grouper`, `/themes/`, and `/variants/`
- [X] T053 [US5] Update `buildNav()` in src/review/static/navbar.js (lines 68–100) to render the breadcrumb with an omitted song-name segment when the page has no song context (grouper/themes/variants) — collapses to `Song Library › <Tool>`
- [X] T054 [P] [US5] Verify the breadcrumb "Song Library" anchor already links to `/` in src/review/static/navbar.js (no change expected — read-only confirmation)
- [X] T055 [US5] Manually walk quickstart.md section 5 "Back to Library from deep pages" — visit all six deep pages and confirm the breadcrumb link works

**Checkpoint**: Deep pages consistently expose a return path. FR-012 met.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T056 Run full test suite: `python3 -m pytest tests/ -v` and verify no regressions (baseline: 55 failed/104 errors pre-existing on main; post-045: same 55/104 — new suite adds 10 passing tests with zero new regressions)
- [X] T057 Run quickstart.md section 6 "Route-reachability audit" — six deep routes confirmed 200 OK via Flask test client (SC-005)
- [X] T058 Run `git diff --stat` and confirm changes touch only `src/review/` paths plus `specs/045-web-ux-wayfinding/` and `tests/` (SC-007) — confirmed
- [X] T059 Confirm `grep -nE '^\s*function openSong\(' src/review/static/dashboard.js` returns exactly one canonical `openSong(hash)` definition — confirmed (line 651) (SC-008)
- [X] T060 Confirm no change to `src/generator/`, `src/analyzer/`, `src/cli.py`, analysis artifact schema, or any CLI command (FR-014, SC-007) via `git diff --stat` — confirmed
- [X] T061 Walk the full quickstart.md end-to-end to confirm every Validation Checklist bullet passes (static oracle walk; dynamic browser verification tracked in tests/ui/strip_states_README.md per US1–US5 acceptance tables)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — immediate
- **Phase 2 (Foundational — `/library` extension)**: Depends on Phase 1; BLOCKS all client-side phases
- **Phase 3 (US1 strip)**: Depends on Phase 2
- **Phase 4 (US2 Zone A gate)**: Depends on Phase 2; independent of US1 in code but shares fixture oracle (T015 / T026)
- **Phase 5 (US3 Open + overflow)**: Depends on Phase 2; independent of US1/US2 in code
- **Phase 6 (US4 badges)**: Depends on Phase 2; best landed after P1 MVP so badge/strip states stay consistent
- **Phase 7 (US5 breadcrumb)**: Fully independent of Phases 2–6 — different file (`navbar.js`)
- **Phase 8 (Polish)**: Depends on all desired user stories

### User Story Dependencies

- **US1 (Stateful strip)**: Depends on Foundational only — MVP block
- **US2 (Zone A gate)**: Depends on Foundational; shares CSS with US1 for the `blocked` strip step
- **US3 (Open + overflow)**: Depends on Foundational; independent of US1/US2
- **US4 (Badges)**: Depends on Foundational; benefits from US1 logic but does not require it
- **US5 (Breadcrumb)**: Independent — separate file, no payload dependency

### Parallel Opportunities

- T004, T005, T006 can run in parallel (same test file, different test functions)
- T022, T023 can run in parallel with T016–T021 (CSS vs HTML/JS)
- T031, T032 can run in parallel with T027–T030
- T044 can run in parallel with T037–T043
- T049 can run in parallel with T048
- Phase 7 (US5) can start at any point after Phase 1 — fully orthogonal to Phases 3–6

---

## Implementation Strategy

### MVP First (US1 + US2 + US3)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational `/library` extension (T004–T013)
3. Complete Phase 3: US1 — Stateful strip (T014–T024)
4. Complete Phase 4: US2 — Zone A gate (T025–T034)
5. Complete Phase 5: US3 — Open + overflow (T035–T045)
6. **STOP and VALIDATE**: Walk quickstart.md sections 1–3 and 6 — this is the shippable P1 block
7. If satisfactory, move to US4 (P2) and US5 (P3)

### Incremental Delivery

1. Setup + Foundational → `/library` serves the four new fields
2. US1 + US2 + US3 → P1 wayfinding MVP (stateful strip, Zone A gate, single Open action)
3. US4 → at-a-glance lifecycle badges (P2 polish)
4. US5 → consistent back-to-library affordance on deep pages (P3 polish)
5. Polish → regression test + full quickstart walkthrough

---

## Notes

- [P] tasks = different files or independent test functions
- [Story] label maps task to specific user story
- US1 + US2 + US3 form the P1 MVP — shipping them delivers the phase's headline value (stateful wayfinding)
- US4 is convenience on top of the same `/library` payload — zero marginal server cost
- US5 is a two-line navbar tweak independent of every other change
- FR-013 and FR-014 are enforced by the scope gate in T058 and T060 — the diff must stay inside `src/review/`
- Spec 046 only needs the single `openSong(hash)` helper from T039 to retarget — the rest of this plan is free to evolve without affecting 046 (SC-008)
