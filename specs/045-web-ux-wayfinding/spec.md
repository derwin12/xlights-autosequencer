# Feature Specification: Web UX Overhaul — Phase 1 Wayfinding

**Feature Branch**: `045-web-ux-wayfinding`
**Created**: 2026-04-14
**Status**: Draft
**Input**: Strategy doc `greedy-splashing-chipmunk.md` identifies the dashboard as "thrown together" — decorative progress strip, one-time setup (Layout Groups) buried as step 4 of the per-song flow, and a per-song detail panel with seven equally-weighted action buttons. Phase 1 is the cheap-wins wayfinding pass: no pipeline changes, no new creative surfaces, just reordering what the user sees so the happy path becomes obvious.

## Background

The dashboard (`src/review/static/dashboard.html`) currently presents:

- A five-step workflow strip (Upload → Review Timeline → Story & Themes → Layout Groups → Generate) rendered as static markup with no `active` or `complete` state bindings — it is purely decorative.
- **Layout Groups** framed as step 4 of the per-song workflow, despite being a one-time layout-XML setup that must exist before *any* song can be generated. The `/grouper` page is reachable only by manual navigation.
- A per-song detail panel (`detail-template`, lines 134–160) with seven buttons of equal weight: Review Timeline, Preview Generation, Story Review, Phonemes, Generate Sequence, Re-analyze, Delete. A first-time user has no visible hierarchy to indicate which is the primary action.

The strategy document proposes a four-zone model (Zone A setup, Zone B library, Zone C per-song workspace, Zone D library admin). Phase 1 implements the wayfinding subset only — Zones A and B's visible boundaries — without building the Zone C workspace itself. Spec **046 (song workspace shell)** is the follow-up that makes "Open" meaningful; this spec must leave a clean attachment point for it.

Pipeline code, generator flags, analysis artifacts, and any existing routes (`/timeline`, `/story-review`, `/phonemes`, `/themes`, `/variants`, `/grouper`) are out of scope. Every route stays reachable — only the default entry path changes.

---

## Clarifications

### Session 2026-04-14

- Q: When layout setup is complete, what persistent UI signals "Zone A is healthy"? → A: Nothing persistent — the absence of the setup banner is the only cue. No pill, badge, or navbar indicator when layout is configured.
- Q: How does the dashboard get the per-song data the stateful strip and badges need (layout configured, last generated, story present, stale)? → A: Extend the existing `/library` response to include `layout_configured` (global, same on every row), `last_generated_at`, `has_story`, and `is_stale` fields. No new per-song endpoint; the dashboard drives the strip and badges from a single library fetch.

---

## User Scenarios & Testing

### User Story 1 — Stateful Per-Song Workflow Strip (Priority: P1)

As a user viewing the song library, I want the five-step workflow strip at the top of the dashboard to reflect the real state of the currently-selected song, so that I can see at a glance which steps are done, which is next, and which are blocked.

**Why this priority**: The strip already exists in the DOM and is the most visible UI element above the song list. Today it is pure decoration — every step renders identically regardless of song state. Making it stateful is a small CSS/JS change that turns a misleading affordance into an accurate one. Without this, the rest of Phase 1 (Layout gate, single "Open" action) lacks the visual anchor that explains *why* something is disabled.

**Independent Test**: Load the dashboard with a library containing one song that has been analyzed but never generated, and a layout file configured. Expand that song's row. The strip must show step 1 (Upload) complete, step 2 (Review Timeline) complete, step 3 (Story & Themes) complete, step 4 (Layout Groups) complete, step 5 (Generate) active. Delete the layout configuration and reload. Step 4 must now show the blocked state.

**Acceptance Scenarios**:

1. **Given** no song row is expanded, **When** the dashboard loads, **Then** the workflow strip renders in a neutral/default state (all steps grey) with no song-specific affordances.
2. **Given** a song row is expanded in the library, **When** that song has a completed analysis on disk, **Then** steps 1 and 2 render in the "complete" state (filled, checkmark or equivalent visual).
3. **Given** a song row is expanded, **When** the layout file (Zone A setup) has not been configured, **Then** step 4 (Layout Groups) renders in a "blocked" state visually distinct from "incomplete" — e.g. warning-tinted rather than grey.
4. **Given** a song row is expanded and all prerequisites are satisfied, **When** the song has never been generated, **Then** step 5 (Generate) renders in the "active" state (highlighted as the next recommended action).
5. **Given** a song row is expanded and the song has a recorded generation timestamp, **When** the strip renders, **Then** step 5 also renders in the "complete" state.
6. **Given** any step is in the "complete" or "active" state, **When** the user clicks the step, **Then** the dashboard routes to the corresponding page (step 2 → `/timeline`, step 3 → `/story-review`, step 4 → `/grouper`, step 5 → Generate action for that song). Steps in the "blocked" or "incomplete" state are non-clickable and show a tooltip explaining what is missing.

---

### User Story 2 — Layout Groups Promoted to Zone A Setup Gate (Priority: P1)

As a user opening the dashboard for the first time, I want Layout Groups presented as a one-time setup prerequisite — not as step 4 of every song's workflow — so that I understand it must be configured once before any sequence can be generated.

**Why this priority**: Layout Groups is the single most misplaced element in today's flow. It is conceptually a property of the user's physical light installation, not a property of a song, yet the strip frames it as per-song work. A user with 20 songs today must mentally ignore step 4 on all 20 rows. Surfacing it as a prerequisite gate removes repeated confusion and lets the per-song strip (User Story 1) shrink to the steps that are genuinely per-song. This is the change that unlocks the strategy document's Zone A/B separation.

**Independent Test**: Clear any saved layout configuration. Load the dashboard. A setup banner must appear above the song library stating that layout configuration is required before generation. Every song row's Generate action (both in the row itself and in the detail panel) must be disabled with a tooltip that references the banner. Configure a layout via `/grouper` and return to the dashboard. The banner must disappear and Generate actions must become enabled.

**Acceptance Scenarios**:

1. **Given** no layout file has been configured, **When** the dashboard loads, **Then** a prominent banner appears above the song library with copy along the lines of "Set up your layout before generating sequences" and a primary button labelled "Set Up Layout" that routes to `/grouper`.
2. **Given** a layout file has been configured, **When** the dashboard loads, **Then** the banner is not rendered at all (no collapsed/dismissed state — it is simply absent when setup is complete).
3. **Given** the layout-setup banner is visible, **When** the user hovers or focuses any Generate control (row button, detail-panel button, or the step 5 strip entry), **Then** a tooltip appears explaining that layout setup must be completed first and Generate is disabled until then.
4. **Given** the layout file has been configured and at least one song is analyzed, **When** the dashboard renders, **Then** Generate controls are enabled for all songs whose analysis is complete.
5. **Given** layout setup is complete but a song is missing analysis, **When** the user hovers its Generate control, **Then** the tooltip explains the per-song blocker (missing analysis) rather than the Zone A blocker.
6. **Given** the strategy doc's Zone A model, **When** this spec ships, **Then** the workflow strip on the dashboard no longer depicts Layout Groups as step 4 — it is either removed from the strip or visually separated (e.g. rendered as a prerequisite pill above the strip, or collapsed into the banner). Per-song steps become Upload → Review → Story → Generate.

---

### User Story 3 — Single Primary "Open" Action with Overflow Menu (Priority: P1)

As a user scanning the song library, I want each expanded row to show one clearly primary action ("Open") with a secondary overflow menu for the rest, so that I am not forced to choose among seven equally-weighted buttons before I know what I want to do.

**Why this priority**: The seven-button detail panel is the single most common complaint in the audit ("no idea which is the main action"). Collapsing it into one primary + overflow is a layout change only — no routes are retired, no pipeline touched. This is the half of Phase 1 that most directly answers "everything is kind of thrown together."

**Independent Test**: Expand a song row. The detail panel must show exactly one primary button labelled "Open" and one overflow control (kebab menu, "More" dropdown, or equivalent). Clicking "Open" must route to the existing `/timeline` page for that song (temporary Phase 1 destination — spec 046 will retarget this to the song workspace). The overflow menu must contain the other six actions (Preview Generation, Story Review, Phonemes, Generate Sequence, Re-analyze, Delete), each routing to the same destination as today.

**Acceptance Scenarios**:

1. **Given** a song row is expanded, **When** the detail panel renders, **Then** exactly one button is styled as the primary action, labelled "Open".
2. **Given** the detail panel is rendered, **When** the user clicks "Open", **Then** the dashboard routes to `/timeline?file=<analysis-path>` for that song — the same destination as today's "Review Timeline" button. (Spec 046 retargets this to `/song/<hash>` once the workspace shell lands.)
3. **Given** the detail panel is rendered, **When** the user opens the overflow menu, **Then** it presents: Preview Generation, Story Review, Phonemes, Generate Sequence, Re-analyze, Delete — each routing to today's destination.
4. **Given** layout setup is incomplete, **When** the overflow menu is opened, **Then** the Generate Sequence entry is disabled with the same tooltip wording as the User Story 2 banner.
5. **Given** the Delete entry is invoked, **When** the confirmation dialog resolves, **Then** today's delete flow runs unchanged (this spec does not modify the dialog).
6. **Given** the overflow menu is open, **When** the user clicks outside it or presses Escape, **Then** the menu dismisses without navigating.

---

### User Story 4 — Status Badges on Library Rows (Priority: P2)

As a user with a large library, I want each song row to show a short lifecycle badge (Analyzed / Briefed / Generated / Stale) so that I can see each song's progress without expanding every row to read its workflow strip.

**Why this priority**: P2 because the workflow strip (User Story 1) already carries this information once a row is expanded, so this is a convenience rather than a blocker. It becomes more valuable as the library grows. "Briefed" is reserved for Phase 3 when the Brief tab ships — for Phase 1 it never appears, but the badge vocabulary should accommodate it so the UI doesn't need re-designing later.

**Independent Test**: Load a dashboard with four songs: one analyzed only, one analyzed with a stale hash (source file modified since analysis), one analyzed and generated. Each row must display its correct badge in the library table without requiring expansion.

**Acceptance Scenarios**:

1. **Given** a song has a valid `_analysis.json` on disk, **When** the library row renders, **Then** an "Analyzed" badge appears in the row.
2. **Given** a song has been generated (a recorded generation timestamp exists in song metadata), **When** the row renders, **Then** a "Generated" badge replaces or supplements the "Analyzed" badge.
3. **Given** a song's source file hash differs from the hash recorded in its analysis, **When** the row renders, **Then** a "Stale" badge appears indicating re-analysis is recommended.
4. **Given** Phase 3 has not yet shipped, **When** any row renders in Phase 1, **Then** no row displays a "Briefed" badge — the vocabulary is reserved but unused.

---

### User Story 5 — Navigation Consistency from Deep Pages Back to Library (Priority: P3)

As a user on a deep page (`/timeline`, `/story-review`, `/grouper`), I want a consistent "back to library" affordance so that I can always return to the song list without using the browser back button.

**Why this priority**: P3 because the browser back button works today and users are not blocked. However, the strategy doc explicitly calls out that "seven pages exist with no breadcrumbs, no shared chrome beyond the navbar, and no 'what should I do next' affordance." Adding a back-to-library link on deep pages is trivial and paves the way for the richer breadcrumb structure that Phase 2's song workspace will need.

**Independent Test**: Open any of `/timeline`, `/story-review`, `/grouper`, `/phonemes`. A consistent "Back to Library" link or breadcrumb must be visible in shared chrome. Clicking it routes to `/` (the dashboard).

**Acceptance Scenarios**:

1. **Given** the user is on `/timeline`, `/story-review`, `/phonemes`, or `/grouper`, **When** the page renders, **Then** a "Back to Library" affordance is visible in the page chrome.
2. **Given** the affordance is visible, **When** the user clicks it, **Then** the browser navigates to `/` (the dashboard).
3. **Given** `/themes` and `/variants` are Zone D library-admin pages, **When** they render, **Then** they also show the same "Back to Library" affordance for consistency (no Zone D-specific chrome is introduced in Phase 1).

---

### Edge Cases

- **Layout configured but file missing on disk**: If `~/.xlight/settings.json` references a layout path that no longer exists, Zone A MUST treat setup as incomplete and surface the banner, with wording that distinguishes "file moved/deleted" from "never configured" if feasible.
- **Song analyzed before layout exists**: User Story 2 only gates Generate, not Upload/Review/Story. A user must still be able to upload, analyze, and review a song before configuring a layout. The strip reflects partial completion without blocking upstream steps.
- **No songs in library + no layout**: The empty state (today's `#empty-state`) must coexist with the Zone A setup banner. Both can render simultaneously — the banner is always above the library region, the empty state inside it.
- **Multiple rows expanded**: Today the dashboard expands one row at a time. If that changes, the strip must still reflect a deterministic song (the most-recently-expanded). If no row is expanded, the strip shows the neutral state (User Story 1 scenario 1).
- **Overflow menu on narrow viewports**: On mobile/narrow viewports the overflow menu must remain reachable. If the dashboard is not responsive today, this spec does not require adding responsiveness — but the overflow must not be worse than today's button row on the same viewport.
- **Phase 2 handoff**: Once spec 046 ships the song workspace at `/song/<hash>`, the "Open" button's destination changes. That retargeting happens in spec 046, not here. This spec must not hard-code the `/timeline` destination in a way that makes retargeting costly (e.g. a single `openSong(songMd5)` JS helper, not inline `<a href>` scattered across templates).
- **Existing direct-link URLs**: Deep pages remain at today's URLs. Any bookmark or CLI that links directly to `/timeline`, `/grouper`, `/story-review`, `/phonemes`, `/themes`, or `/variants` continues to work unchanged.

---

## Requirements

### Functional Requirements

- **FR-001**: The workflow strip on the dashboard MUST render per-song state. When a song row is expanded, each of the five steps MUST render in one of four visual states: `complete`, `active`, `incomplete`, `blocked`.
- **FR-002**: Step-state computation MUST derive from observable data on the song and system state: analysis artifacts on disk (steps 1–2), story/theme artifacts (step 3), Zone A layout configuration (step 4), generation timestamp in song metadata (step 5). The client MUST read these facts from the existing `/library` response — which MUST be extended with the following additional fields: `layout_configured: bool` (global, same on every row), `last_generated_at: iso8601 | null`, `has_story: bool`, `is_stale: bool`. No per-song status endpoint is introduced.
- **FR-003**: When no song row is expanded, the workflow strip MUST render in a neutral all-grey state with no step marked `active`.
- **FR-004**: The dashboard MUST display a Zone A setup banner above the song library whenever layout configuration is incomplete. When configuration is complete, the banner MUST NOT render at all (no collapsed/dismissed state).
- **FR-005**: All Generate controls (row-level, detail-panel overflow entry, and workflow strip step 5) MUST be disabled when layout configuration is incomplete, with a tooltip referencing the banner's instruction.
- **FR-006**: Layout Groups MUST NOT be rendered as step 4 of the per-song workflow strip. The strip MUST depict per-song steps only: Upload → Review → Story → Generate (4 steps). Zone A status is surfaced **exclusively via the setup banner from FR-004** — when layout is configured, no persistent pill, badge, or navbar indicator is rendered. The absence of the banner is the user's only signal that Zone A is healthy.
- **FR-007**: The per-song detail panel MUST present exactly one primary action button labelled "Open".
- **FR-008**: The "Open" action MUST route to `/timeline?file=<analysis-path>` for the selected song as a temporary Phase 1 destination. The routing MUST be centralized (single JS helper) to allow spec 046 to retarget it in one place.
- **FR-009**: The detail panel MUST present a single overflow control (menu, dropdown, or equivalent) containing: Preview Generation, Story Review, Phonemes, Generate Sequence, Re-analyze, Delete. Each entry MUST route to today's destination without change.
- **FR-010**: The overflow menu MUST dismiss on outside-click and on Escape key.
- **FR-011**: The library table MUST display per-song status badges in a dedicated column (or within the existing `col-badges` column). Phase 1 vocabulary: `Analyzed`, `Generated`, `Stale`. The `Briefed` value MUST be reserved but unused.
- **FR-012**: Deep pages (`/timeline`, `/story-review`, `/phonemes`, `/grouper`, `/themes`, `/variants`) MUST display a consistent "Back to Library" affordance in shared chrome that routes to `/`.
- **FR-013**: No existing route (`/timeline`, `/story-review`, `/phonemes`, `/grouper`, `/themes`, `/variants`) MUST be removed, renamed, or have its response contract changed by this spec.
- **FR-014**: No field on `GenerationConfig`, no analysis artifact schema, no generator module, and no CLI command MUST be modified by this spec. Phase 1 is UI-only.

### Key Entities

- **WorkflowStepState**: A per-step visual state — one of `complete`, `active`, `incomplete`, `blocked`. Computed client-side from song artifacts and system settings. Not persisted.
- **ZoneAStatus**: A boolean-plus-reason derived from whether a layout file is configured and reachable. Drives banner visibility and Generate-control disabled state. Not persisted beyond today's `~/.xlight/settings.json` layout-path entry.
- **SongLifecycleBadge**: A short label shown in the library row — `Analyzed`, `Generated`, or `Stale` in Phase 1. `Briefed` is reserved for Phase 3.

---

## Success Criteria

- **SC-001**: On a dashboard with at least one analyzed song and a configured layout, expanding the song row renders the workflow strip with every step's state visibly distinct (complete/active/incomplete/blocked), and the states match the song's real artifacts on disk.
- **SC-002**: When the layout configuration is cleared, the Zone A banner appears on the next dashboard load, every Generate control is disabled, and hovering a Generate control reveals the explanatory tooltip. Re-configuring the layout removes the banner and re-enables the controls without requiring any per-song action.
- **SC-003**: The per-song detail panel presents one visibly-primary "Open" button. A user-testing walk-through ("which button should I click first?") yields the "Open" answer without hesitation in a way the seven-button layout did not.
- **SC-004**: Clicking "Open" routes to `/timeline` for that song. Changing the destination for all songs in Phase 2 requires editing one JS helper, not multiple templates.
- **SC-005**: Every route reachable today remains reachable. A click-path audit ("from `/`, can I still reach every one of `/timeline`, `/story-review`, `/phonemes`, `/grouper`, `/themes`, `/variants`?") passes.
- **SC-006**: Library rows display badges that correctly identify Analyzed, Generated, and Stale songs in a library fixture that includes at least one of each.
- **SC-007**: No change to `GenerationConfig`, analysis artifacts, generator pipeline code, or CLI commands. Phase 1 diff is scoped to `src/review/static/` and `src/review/server.py` (for layout-status exposure only, if a new endpoint is needed).
- **SC-008**: Spec 046 (song workspace shell) can land without any further changes to this spec's routing scaffold — the "Open" helper is its single attachment point.

## Key Files

- `src/review/static/dashboard.html` — workflow strip (lines ~67–94) and detail-template (lines ~134–160) rewritten for stateful rendering, single "Open" + overflow.
- `src/review/static/dashboard.js` — step-state computation, Zone A banner rendering, `openSong()` helper (single point of retargeting for spec 046).
- `src/review/static/dashboard.css` — new visual states (`complete`/`active`/`incomplete`/`blocked`), banner, primary/overflow button styles.
- `src/review/static/navbar.html` / `navbar.js` / `navbar.css` — "Back to Library" affordance rendered on deep pages.
- `src/review/server.py` — extend the existing `/library` response with `layout_configured`, `last_generated_at`, `has_story`, and `is_stale` fields. No new per-song status endpoint; no writes; no other behavior change.
- Follow-up: spec **046-song-workspace-shell** retargets the `openSong()` helper to `/song/<hash>` once the workspace lands.
