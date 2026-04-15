# Feature Specification: Song Workspace Shell

**Feature Branch**: `046-song-workspace-shell`
**Created**: 2026-04-14
**Status**: Draft
**Input**: Phase 2 of the web-UI UX overhaul described in `plans/greedy-splashing-chipmunk.md`. The strategy doc identifies Zone C — the per-song workspace — as the default entry point for everything you do with one song. Today those actions are scattered across seven separate pages (`/timeline`, `/phonemes`, `/story-review`, plus six action buttons in the dashboard detail panel). This feature consolidates the per-song surface into one tabbed page at `/song/<source_hash>` so there is exactly one home per song.

## Background

The strategy's Zone C model: "Clicking a song opens a single dedicated page with tabs for the four things you can do with that song, in recommended order: Analysis, Brief, Preview, Generate & Download." Today none of those live in one place:

- **Analysis**: rendered by `src/review/static/index.html` (the timeline app). Reached via `/timeline?path=...` or `/library-view` → Timeline button.
- **Brief**: does not exist as a UI surface. Creative decisions are set by POST body flags in `/generate/<hash>` or buried inside `/story-review`.
- **Preview**: does not exist. A `/generation-preview` route exists but produces a static plan-inspection view, not an audio/visual preview.
- **Generate & Download**: `generate_bp` is wired under `/generate` with endpoints for POST, status, download, and history (`src/review/generate_routes.py`). The UI calls it from two places (`dashboard.js` and `story-review.js`) with partially overlapping form fields.

Phase 1 (spec 045) replaces the seven-button detail panel with a single "Open" button. Phase 2 (this spec) owns what that "Open" button lands on. Phase 3 (spec 047) will fill in the Brief tab; Phase 5 (spec 049) will fill in the Preview tab. The two placeholder tabs in this spec exist specifically so those later phases have stable mount points and so the tab order is correct from day one.

Scope boundary: Phase 2 is **organizational**. No new creative decisions are exposed. No generator pipeline changes. Existing pages (`/story-review`, `/themes`, `/variants`, `/phonemes`) remain reachable by direct URL but are no longer the default entry path.

---

## Clarifications

### Session 2026-04-14

- Q: How is the existing timeline UI mounted inside the Analysis tab? → A: Refactor `index.html` into a mountable component. The Analysis tab imports and mounts the component directly (no iframe). `/timeline` continues to work as a standalone page that renders the same component at a full-page mount point. Shared audio-playback state across tabs is permitted but not required in Phase 2.
- Q: How does the Generate tab detect an already-running generation for this song on mount so it can re-attach instead of duplicating? → A: Extend `/generate/<hash>/history` to include in-flight jobs with their live status. The tab fetches history once on mount; any entry whose status is `running` triggers re-attach to that `job_id`. No new `/active` endpoint; no reliance on localStorage.

---

## User Scenarios & Testing

### User Story 1 — One Home Per Song (Priority: P1)

As a user, when I click "Open" on a song in the library, I want to land on a single page that shows me everything I can do with that song in a clear recommended order, so that I am never asking "which of seven buttons do I press next?"

**Why this priority**: This is the entire point of Phase 2. Without a single landing page, the "Open" button from Phase 1 has nowhere to go, the Brief tab from Phase 3 has nowhere to live, and the Preview tab from Phase 5 has nowhere to mount. Every other story in this spec depends on the shell existing.

**Independent Test**: With a song already analyzed in the library, navigate to `/song/<source_hash>` directly. Confirm the page loads without error, shows the song title and duration in a header, and displays four tabs in the order: Analysis, Brief, Preview, Generate & Download. Confirm the Analysis tab is active by default.

**Acceptance Scenarios**:

1. **Given** a song with a valid `source_hash` that resolves to a library entry, **When** the user navigates to `/song/<source_hash>`, **Then** the workspace page loads with the song's title, duration, and analysis status visible in a header, and four tabs are rendered in the order Analysis / Brief / Preview / Generate & Download.
2. **Given** the workspace page loads, **When** no tab is specified in the URL, **Then** the Analysis tab is active by default.
3. **Given** the user is on any tab, **When** they click a different tab, **Then** the active tab changes, the URL fragment updates to `#analysis`, `#brief`, `#preview`, or `#generate` respectively, and the previously active tab's content is hidden (not destroyed — tab state is preserved so switching back does not reset scroll/selection).
4. **Given** the user loads `/song/<source_hash>#generate` directly, **When** the page renders, **Then** the Generate & Download tab is active from the first paint.
5. **Given** a `source_hash` that does not resolve to a library entry, **When** the user navigates to `/song/<source_hash>`, **Then** the server returns 404 with a message pointing back to the library view.

---

### User Story 2 — Analysis Tab Wraps the Existing Timeline (Priority: P1)

As a user, I want the Analysis tab to show the same interactive timeline, waveform, and synchronized playback I have today on `/timeline`, so that moving to the workspace page loses no capability and I still have a single place to confirm analysis looks correct before committing to a brief or generation.

**Why this priority**: The timeline is the one existing per-song view that already works end-to-end. Reproducing it inside the workspace is non-negotiable: if the tab feels like a degraded version of `/timeline`, users will keep using `/timeline` directly and the workspace fails as the default entry path.

**Independent Test**: Open `/song/<source_hash>` on a song with a completed analysis. Confirm the Analysis tab shows the waveform, timing-track lanes, playback controls, and track solo/focus behavior identical to the standalone `/timeline` page for the same song. Start playback; confirm the audio plays in sync with the timeline cursor.

**Acceptance Scenarios**:

1. **Given** a song with a hierarchy analysis available, **When** the Analysis tab is active, **Then** the existing timeline UI (waveform, per-track lanes, play/pause, next/prev focus) is rendered and functional, sourced from the same analysis JSON the standalone `/timeline` route would serve.
2. **Given** the Analysis tab is active, **When** the user starts playback, **Then** audio plays via the same `/audio` endpoint used today and the timeline cursor tracks the playhead.
3. **Given** the user switches to another tab and returns to Analysis, **When** the Analysis tab reactivates, **Then** the timeline is still in the same scroll position and track focus it had before (tab content is not torn down on switch).
4. **Given** the standalone `/timeline?path=...` route is accessed directly, **When** the page loads, **Then** it still works (route is not removed in this phase), but a subtle "Open in workspace" link points to `/song/<source_hash>#analysis`.
5. **Given** the analysis for this song is missing or in an error state, **When** the Analysis tab loads, **Then** it shows a clear empty-state ("No analysis available — re-run analysis to populate this tab") instead of a broken timeline.

---

### User Story 3 — Generate & Download Moves Into the Workspace (Priority: P1)

As a user, I want to start a generation, watch its progress, download the resulting `.xsq`, and see a history of previous renders for this song, all inside the Generate & Download tab of the workspace, so that I don't have to leave the page or guess which of two duplicate UIs (dashboard vs. story-review) is the "real" one.

**Why this priority**: Today the generation flow is implemented twice (in `dashboard.js` and in `story-review.js`) against the same `/generate/<hash>` endpoints. Both are partial; neither has polished progress UI; the history list is hidden under story-review. Consolidating this tab is the single largest functional piece of Phase 2 and the most visible improvement for returning users.

**Independent Test**: On a song with a completed analysis, open the workspace's Generate & Download tab. Click Generate. Confirm a progress UI appears and updates until completion. Confirm a download link to the produced `.xsq` appears and works. Reload the page; confirm the completed generation appears in a "Previous renders" list with its timestamp and a re-download link.

**Acceptance Scenarios**:

1. **Given** the Generate & Download tab is active on an analyzed song, **When** the user clicks the primary Generate button, **Then** the UI POSTs to `/generate/<source_hash>` using the existing endpoint and transitions into a progress state showing a spinner, a percent or stage label, and a cancel-hint (cancel itself is not in scope).
2. **Given** a generation is in progress, **When** the browser is polling `/generate/<source_hash>/status?job_id=...`, **Then** progress updates are visible to the user at least every 2 seconds, and the Generate button is disabled while the job is running.
3. **Given** a generation completes successfully, **When** the status endpoint returns `done`, **Then** a Download button/link pointing to `/generate/<source_hash>/download/<job_id>` appears and is the visually dominant affordance on the tab.
4. **Given** a generation fails, **When** the status endpoint returns an error state, **Then** the tab shows the error message surfaced by the server and re-enables the Generate button so the user can retry.
5. **Given** one or more prior generations exist for this song, **When** the tab loads, **Then** a "Previous renders" list is populated from `/generate/<source_hash>/history` and each row shows the render timestamp, a short summary of the config/brief used, and a re-download link.
6. **Given** the user navigates away mid-generation and returns to the tab, **When** the tab re-mounts, **Then** it resumes polling the same `job_id` (tracked in page state or URL) and continues to show progress without restarting the render.

---

### User Story 4 — Brief Tab Placeholder (Priority: P2)

As a future-user of the Brief feature (Phase 3 / spec 047), I need a tab labeled "Brief" to exist in the workspace today, so that Phase 3's work is a pure fill-in and not a structural change to the shell, and so Phase 2 can ship and be used while Brief is still being designed.

**Why this priority**: The tab order is part of the strategy's recommended per-song flow (Analysis → Brief → Preview → Generate). Introducing it now — even as a stub — locks in correct ordering, avoids a disruptive re-shuffle when Phase 3 lands, and gives users a visible promise that a brief surface is coming. Lower priority than P1 because a stub has no functional payoff on its own.

**Independent Test**: Open the workspace for any analyzed song. Click the Brief tab. Confirm the tab activates without error and shows a clearly labeled "Coming soon" placeholder (or a minimal read-only snapshot of the genre/occasion pulled from the song's ID3 metadata and current `GenerationConfig` defaults).

**Acceptance Scenarios**:

1. **Given** the Brief tab is rendered, **When** the user clicks it, **Then** it becomes the active tab and displays a placeholder panel with copy that states this tab will be filled in by a future feature, with a link to the strategy doc or feature 047 tracking issue if one exists.
2. **Given** the Brief tab is a stub, **When** the user interacts with the page, **Then** no form submits from this tab and no generation config is mutated by anything inside it.
3. **Given** Phase 3 (spec 047) later replaces the placeholder with real form fields, **When** that change ships, **Then** no other tab's code, route, or URL needs to change — the swap is contained to the Brief tab's panel.

---

### User Story 5 — Preview Tab Placeholder (Priority: P3)

As a future-user of the Preview feature (Phase 5 / spec 049), I need a tab labeled "Preview" to exist in the workspace today, so that its slot in the tab order is reserved and Phase 5 can land as a pure fill-in.

**Why this priority**: Same rationale as the Brief stub but lower because Preview is further out on the roadmap (Phase 5 after the pipeline refactor in Phase 4) and has the smallest user-visible value as a stub. Still worth reserving the slot to avoid shuffling tabs later.

**Independent Test**: Open the workspace for any analyzed song. Click the Preview tab. Confirm it activates, shows a "Coming soon — short-section preview render will live here" placeholder, and does not attempt to render or fetch any audio.

**Acceptance Scenarios**:

1. **Given** the Preview tab is rendered, **When** the user clicks it, **Then** it becomes active and displays a placeholder panel that names feature 049 as the follow-up and briefly describes the intended capability (short-section preview render).
2. **Given** the Preview tab is a stub, **When** the page is idle on that tab, **Then** no background polling, audio loading, or render calls occur.
3. **Given** the workspace is loaded, **When** the tab order is inspected, **Then** Preview sits between Brief and Generate & Download as specified by the strategy, regardless of whether the Brief tab is a stub or a full form.

---

### Edge Cases

- **Song exists in library but analysis is missing**: Workspace loads, header renders, Analysis tab shows the empty state (User Story 2 scenario 5), and Generate tab is disabled with a tooltip pointing to a re-analyze action in the library view.
- **Layout not configured (Zone A gate)**: The Generate button in the Generate & Download tab is disabled with a tooltip/banner explaining that layout setup (Zone A) must be completed first, consistent with the Phase 1 banner from spec 045. Clicking the tooltip link navigates to the Zone A setup page.
- **Deep link with unknown tab fragment**: A URL like `/song/<hash>#bogus` falls back to the default tab (Analysis) rather than showing a blank state or error.
- **Concurrent generations on the same song**: If a generation is already running when the tab mounts, the tab detects the active `job_id` via the extended `/generate/<hash>/history` endpoint (which now includes in-flight jobs) and attaches to it rather than starting a duplicate.
- **Browser back/forward across tabs**: Changing tabs updates the URL fragment but not the history stack, so browser Back exits the workspace instead of cycling through tabs (avoids trapping users inside one page).
- **Direct access to legacy routes**: `/timeline`, `/phonemes`, `/story-review` continue to serve their existing content. A small "Open in workspace" affordance links back to `/song/<source_hash>#analysis` when the source_hash is resolvable. Removal of these routes is out of scope for this phase.

---

## Requirements

### Functional Requirements

- **FR-001**: A new route `/song/<source_hash>` MUST be added to `src/review/server.py` that resolves the source_hash via `Library().find_by_hash` and returns 404 if no entry exists.
- **FR-002**: The workspace page MUST render exactly four tabs in this order: Analysis, Brief, Preview, Generate & Download.
- **FR-003**: The Analysis tab MUST display the current timeline UI (waveform, per-track lanes, synchronized playback) for the song by refactoring `index.html` / `app.js` into a **mountable component** and mounting it directly in the tab panel (no iframe). The existing `/timeline` route MUST continue to render the same component at a full-page mount point so direct-URL access is unchanged. Component boundaries MUST be clean enough that Phase 5's Preview tab (spec 049) can optionally share or coordinate playback state — but sharing is not a Phase 2 requirement.
- **FR-004**: The Brief tab MUST render as a clearly labeled placeholder panel referencing feature 047 as the follow-up. No form fields that mutate `GenerationConfig` may be wired from this tab in Phase 2.
- **FR-005**: The Preview tab MUST render as a clearly labeled placeholder panel referencing feature 049 as the follow-up. No audio, preview render, or background polling may originate from this tab in Phase 2.
- **FR-006**: The Generate & Download tab MUST POST generation requests to the existing `/generate/<source_hash>` endpoint and MUST poll `/generate/<source_hash>/status?job_id=...` at least every 2 seconds while a job is running.
- **FR-007**: The Generate & Download tab MUST render a "Previous renders" list populated from `/generate/<source_hash>/history`, with each row showing timestamp, a short summary of the config used, and a link to `/generate/<source_hash>/download/<job_id>`.
- **FR-008**: The workspace MUST disable the Generate button and show an explanatory tooltip/banner when layout setup (Zone A) is not complete, consistent with the Phase 1 banner in spec 045.
- **FR-009**: The active tab MUST be reflected in the URL fragment (`#analysis`, `#brief`, `#preview`, `#generate`) and MUST be honored on page load so deep links work.
- **FR-010**: Tab switches MUST preserve the inactive tab's DOM state (scroll position, playback state, selected tracks) for the lifetime of the page load. A full page reload is the only event permitted to reset tab state.
- **FR-011**: The "Open" button introduced by Phase 1 (spec 045) MUST link to `/song/<source_hash>` as the single per-song landing page.
- **FR-012**: The existing routes `/timeline`, `/phonemes`, `/story-review` MUST continue to work unchanged. They MAY gain a small "Open in workspace" link when the song's `source_hash` can be resolved.
- **FR-013**: If a generation job is already running for the current song when the tab mounts, the Generate & Download tab MUST attach to the existing `job_id` instead of starting a new generation. Detection: the `/generate/<hash>/history` endpoint MUST be extended to include in-flight jobs with their live status (`queued`, `running`). The tab fetches history once on mount; any entry with status `running` identifies the job to re-attach to. No separate `/active` endpoint is introduced and no client-side persistence (e.g. `localStorage`) is used for this detection.
- **FR-014**: The workspace MUST NOT introduce any new `GenerationConfig` flags, generator pipeline changes, or new creative decision surfaces. Phase 2 is organizational.

### Key Entities

- **SongWorkspacePage**: The top-level per-song page served at `/song/<source_hash>`. Responsible for resolving the library entry, rendering the song header (title, duration, analysis status, layout-ready status), and hosting the tab strip.
- **WorkspaceTab**: A named panel inside the workspace. Four instances: `analysis`, `brief`, `preview`, `generate`. Each owns its own DOM subtree and persists state across tab switches until page reload. Two of the four (`brief`, `preview`) are stubs in Phase 2 and will be replaced in-place by specs 047 and 049 respectively.
- **GenerationHistoryEntry**: A row in the "Previous renders" list sourced from `/generate/<source_hash>/history`. Carries `job_id`, `timestamp`, `config_summary` (short human-readable string derived from the config/brief used), and a download URL.

---

## Success Criteria

- **SC-001**: Navigating to `/song/<source_hash>` for an analyzed song renders the four-tab workspace with the Analysis tab active in under 1 second on a warm server (excluding audio download).
- **SC-002**: The Analysis tab provides waveform display, playback, and track focus behavior functionally equivalent to the standalone `/timeline` page — no regression in timeline capability when accessed via the workspace.
- **SC-003**: A user can complete the full "click Generate → watch progress → download .xsq" flow entirely inside the Generate & Download tab without navigating to any other page.
- **SC-004**: The "Previous renders" list correctly shows all prior generations for the song, sorted newest-first, with working re-download links.
- **SC-005**: Switching between tabs does not re-request analysis JSON, re-decode audio, or re-fetch generation history — each is fetched at most once per page load (unless the user explicitly triggers a refresh).
- **SC-006**: Deep links with a tab fragment (e.g. `/song/<hash>#generate`) activate the correct tab on first paint, not after a flash of the default tab.
- **SC-007**: Phase 3 (spec 047) can replace the Brief tab's placeholder content without modifying `/song/<source_hash>` route code, any other tab, or the tab strip component.
- **SC-008**: Phase 5 (spec 049) can replace the Preview tab's placeholder content under the same constraint as SC-007.
- **SC-009**: Existing direct-access pages (`/timeline`, `/phonemes`, `/story-review`, `/themes`, `/variants`) remain functional; no existing test in the suite regresses.

## Key Files

- `src/review/server.py` — new `/song/<source_hash>` route; resolves library entry and serves the workspace HTML.
- `src/review/static/song-workspace.html` (new) — workspace page shell with tab strip and four panel mount points.
- `src/review/static/song-workspace.js` (new) — tab switching, URL-fragment sync, deferred panel mounting, generation flow wiring.
- `src/review/static/song-workspace.css` (new) — tab strip and panel layout styling; reuses navbar/theme tokens from existing stylesheets.
- `src/review/static/index.html`, `src/review/static/app.js` — refactored into a mountable timeline component. `/timeline` serves a thin wrapper that mounts the component at full-page scale; the Analysis tab mounts the same component inside the workspace. No iframe.
- `src/review/static/dashboard.js` — Phase 1's "Open" button updated (or confirmed, if already landed in spec 045) to link to `/song/<source_hash>`.
- `src/review/generate_routes.py` — unchanged API surface; the workspace consumes it. Documented here because this is the tab's backend contract.
- `tests/unit/test_song_workspace_route.py` (new) — route resolution, 404 on unknown hash, tab fragment handling via server-rendered default.
- `tests/integration/test_song_workspace_flow.py` (new) — end-to-end: open workspace, switch tabs, start generation, download artifact, confirm history entry.
