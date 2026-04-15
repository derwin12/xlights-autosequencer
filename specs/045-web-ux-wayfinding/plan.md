# Implementation Plan: Web UX Overhaul — Phase 1 Wayfinding

**Branch**: `045-web-ux-wayfinding` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/045-web-ux-wayfinding/spec.md`

## Summary

The dashboard's workflow strip is decorative, Layout Groups is miscategorized as a
per-song step, and the detail panel gives seven equally-weighted buttons with no
primary action. Phase 1 fixes the wayfinding: make the strip stateful, promote
Layout Groups to a one-time Zone A setup banner, collapse the detail panel to a
single "Open" primary + overflow menu, add lifecycle badges on rows, and render a
"Back to Library" affordance on deep pages.

This is a UI-only change. The only server touch is extending the existing
`/library` response with four fields (`layout_configured`, `last_generated_at`,
`has_story`, `is_stale`). No generator, analyzer, or CLI code is modified.

Spec 046 (song workspace shell) is the follow-up. This plan exposes a single JS
helper `openSong(hash)` that 046 retargets from `/timeline?hash=…` to
`/song/<hash>` without touching templates.

## Technical Context

**Language/Version**: Python 3.11+ (Flask route), Vanilla JS ES2020+ (frontend)
**Primary Dependencies**: No new dependencies — Flask, `src.settings`, `src.library` already present
**Storage**: None new — reads `~/.xlight/settings.json` (existing) for layout_configured
**Testing**: Manual click-path audit per quickstart.md; no unit tests required for template/CSS
**Target Platform**: Chromium-based browsers served by the local Flask review app
**Project Type**: Web UI (single-page dashboard + deep tool pages)
**Performance Goals**: `/library` response stays <100ms for ≤500-song libraries (the four new fields are cheap)
**Constraints**: Every existing route (`/timeline`, `/story-review`, `/phonemes-view`, `/grouper`, `/themes`, `/variants`) remains reachable and unchanged
**Scale/Scope**: ~5 files touched, estimated ~300 lines of diff concentrated in `dashboard.*`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | No change to analysis pipeline; no timing data touched |
| II. xLights Compatibility | PASS | No sequence output touched; `.xsq` generation untouched |
| III. Modular Pipeline | PASS | Changes confined to `src/review/` UI layer; no stage boundaries crossed |
| IV. Test-First Development | PASS (N/A) | UI template/CSS change — covered by manual click-path audit in quickstart.md. No new pipeline logic to unit-test |
| V. Simplicity First | PASS | One JS helper (`openSong`), one banner element, one overflow menu. No new abstractions. |

No violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/045-web-ux-wayfinding/
├── plan.md              # This file
├── research.md          # Current DOM + /library shape reference
├── quickstart.md        # Manual verification steps
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

No `data-model.md` — the only new "data" is four JSON fields added to an existing
response, fully described in FR-002. No new entities.

### Source Code (affected files)

```text
src/
├── review/
│   ├── server.py                        # Extend /library response (4 new fields)
│   └── static/
│       ├── dashboard.html               # Strip rewrite (4 steps), detail-template rewrite
│       ├── dashboard.js                 # stepState(), banner render, openSong() canonicalization, badge render, overflow menu
│       ├── dashboard.css                # .workflow-step states, .zone-a-banner, .btn-open, .overflow-menu, .row-badge
│       └── navbar.js                    # Extend SONG_TOOL_PAGES + breadcrumb to cover /grouper, /themes/, /variants/
```

No new files. No new routes. No schema or settings changes.

**Structure Decision**: UI-only diff with a single server-side payload extension.
All new JS logic lives in `dashboard.js`; navbar changes are additive.

## Implementation Approach

### Change 1: `/library` response extension (`src/review/server.py`, `_enrich()` ~lines 469–570)

Add four fields to the dict returned by `_enrich(e)` — three per-song, one global
repeated on every row:

- `layout_configured: bool` — computed once per request outside the loop via
  `src.settings.get_layout_path()`: `True` iff the returned Path is not None and
  `.exists()`. Same value set on every entry (simplest; dashboard reads `[0]`).
- `last_generated_at: str | None` — ISO-8601 string from the newest job in
  `src.review.generate_routes._jobs` with `source_hash == e.source_hash` and
  `status == "complete"`. Returns `None` when no completed job exists.
- `has_story: bool` — already populated at line 569; no change, documented here
  for completeness.
- `is_stale: bool` — `True` iff `source_file_exists` and the recomputed MD5 of
  the source file differs from `e.source_hash`. Skipped (False) when source is
  missing. MD5 can be gated behind file size check to keep <100ms budget
  (see research.md decision 3).

No other changes to `library_index()`. The existing `entries` list shape is
preserved.

### Change 2: Workflow strip becomes stateful (`dashboard.html` lines 67–94, `dashboard.js`)

Rewrite the strip to four steps (Upload, Review, Story, Generate) — Layout Groups
is removed per FR-006. Each `.workflow-step` gets a `data-state` attribute set by
a new `applyStripState(entry)` function in `dashboard.js` called from the
existing row-expand handler (dashboard.js ~line 209).

Step-state rules (computed client-side from the enriched `/library` entry):

| Step | complete | active | incomplete | blocked |
|------|----------|--------|------------|---------|
| 1 Upload | `source_file_exists && analysis_exists` | never | `!analysis_exists` | — |
| 2 Review | step 1 complete | never | step 1 not complete | — |
| 3 Story | `has_story` | steps 1–2 complete && !has_story | earlier step incomplete | — |
| 4 Generate | `last_generated_at != null` | steps 1–3 complete && !last_generated_at && layout_configured | earlier step incomplete | `!layout_configured` |

When `_expandedHash` is null, strip renders neutral grey (no `data-state` or
`data-state="neutral"`). Click handler routes complete/active steps to their
existing destinations via `openSong()` for step 2, `/story-review` for step 3,
inline generate panel for step 4.

### Change 3: Zone A setup banner (`dashboard.html`, `dashboard.js`, `dashboard.css`)

Insert `<div id="zone-a-banner" class="zone-a-banner" style="display:none">`
between `#progress-section` (line 64) and `#workflow-guide` (line 67) in
`dashboard.html`. Populated by a new `renderZoneABanner(entries)` in
`dashboard.js` called from `fetchLibrary()`'s `.then` (around line 50-ish where
`renderTable` is called today). When `entries[0].layout_configured === false`
the banner shows with copy "Set up your layout before generating sequences" and a
"Set Up Layout" button linking to `/grouper`. Otherwise `display:none`.

The banner also drives the disabled-state for all Generate controls via the
`data-layout-configured` attribute on `<body>`. CSS uses attribute selectors to
disable buttons and show tooltips without JS per-button wiring.

### Change 4: Single "Open" + overflow (`dashboard.html` lines 134–160, `dashboard.js` `renderDetail` ~line 241)

Rewrite `<template id="detail-template">` `.detail-actions` to a primary button
and an overflow menu:

```html
<button class="btn btn-open" data-action="open">Open</button>
<div class="overflow-wrap">
  <button class="btn-kebab" aria-haspopup="menu" aria-expanded="false">&#8942;</button>
  <div class="overflow-menu" role="menu" hidden>
    <button role="menuitem" data-action="preview">Preview Generation</button>
    <button role="menuitem" data-action="story">Story Review</button>
    <button role="menuitem" data-action="phonemes">Phonemes</button>
    <button role="menuitem" data-action="generate">Generate Sequence</button>
    <button role="menuitem" data-action="reanalyze">Re-analyze</button>
    <button role="menuitem" data-action="delete" class="btn-danger">Delete</button>
  </div>
</div>
```

In `renderDetail` (dashboard.js line 241), the existing `data-action` switch
(line 270–281) gains one new case `'open'` that calls
`openSong(entry.source_hash)` (now defaulting to the timeline tool — see
Change 5). The remaining six cases are unchanged, they just live inside the
menu. Add outside-click and Escape handlers that close any open menu (FR-010).

### Change 5: Centralize `openSong()` (`dashboard.js` lines 434–446)

Collapse the existing `openSong(hash, tool, storyPath)` to `openSong(hash)` as
the canonical Phase 1 entry point: it always routes to
`/timeline?hash=<hash>` after the `/open-from-library` POST. The old signature
is kept as `openSongTool(hash, tool, storyPath)` for the overflow-menu actions
that still need explicit tool targeting (`story`, `phonemes`, row-click at
line 165, fetch-success at line 549). Only `openSong(hash)` is the one spec 046
will retarget.

### Change 6: Row lifecycle badges (`dashboard.js` `renderBadges` ~line 229)

Extend the existing `renderBadges(e)` (line 229–238) to prepend lifecycle badges
computed from the same fields feeding Change 2:

- `Analyzed` — shown when `analysis_exists` and not Generated/Stale.
- `Generated` — shown when `last_generated_at != null`, replaces `Analyzed`.
- `Stale` — shown when `is_stale`, replaces both others (source changed since
  analysis).
- `Briefed` — reserved label; never emitted in Phase 1 (FR-011).

CSS classes `.badge-analyzed`, `.badge-generated`, `.badge-stale` added to
`dashboard.css` next to existing `.badge-stems`/`.badge-phonemes`/`.badge-story`.

### Change 7: "Back to Library" on deep pages (`navbar.js` lines 16–21)

Extend `SONG_TOOL_PAGES` to cover `/grouper`, `/themes/`, `/variants/` so the
existing breadcrumb (`Song Library › …`) renders on those pages too (FR-012).
The navbar already emits the `Song Library` anchor linking to `/`; no new DOM
needed. For `/grouper`, `/themes/`, `/variants/` the breadcrumb omits the song
name (no song context) and collapses to `Song Library › <Tool>`. A small
conditional in `buildNav()` (navbar.js line 68–100) handles the no-song case.

### Sequencing notes

- Change 1 lands first — the dashboard JS depends on the new fields.
- Changes 2–6 are orthogonal within `dashboard.*` and can ship in any order
  inside a single commit.
- Change 7 is independent of everything else.
- Spec 046 only needs Change 5's single `openSong(hash)` entry point; the
  rest of this plan is free to change without affecting 046.
