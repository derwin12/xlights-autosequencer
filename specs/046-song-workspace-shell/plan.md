# Implementation Plan: Song Workspace Shell

**Branch**: `046-song-workspace-shell` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/046-song-workspace-shell/spec.md`

## Summary

Add `/song/<source_hash>` — a single tabbed per-song page (Analysis / Brief / Preview
/ Generate & Download) that becomes the one landing destination for the "Open" button
from spec 045. Phase 2 is organizational: no new `GenerationConfig` flags, no generator
pipeline touch.

Two concrete architectural moves are required and together they are the whole feature:

1. **Refactor `index.html` + `app.js` into a mountable timeline component** that accepts
   a root element plus a `hashParam` and owns its own DOM. `/timeline` becomes a thin
   full-page wrapper that mounts the component at document body scale; the workspace's
   Analysis tab mounts the same component inside a tab panel. No iframe. The existing
   module-level singletons in `app.js` (`tracks`, `durationMs`, `player`, etc.) move
   into a per-instance closure so two mounts on one page would not collide — even
   though Phase 2 never mounts it twice.

2. **Extend `/generate/<hash>/history` to include in-flight jobs** with status
   `queued`/`running` alongside `complete`/`failed`. The workspace fetches history
   once on mount; any `running` entry identifies the job to re-attach to. No
   `/active` endpoint, no `localStorage`.

Brief and Preview tabs ship as placeholder panels with stable DOM mount points so
specs 047 and 049 are pure drop-in replacements.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend)
**Primary Dependencies**: Flask 3+ (existing), `src.library` (existing). No new deps.
**Storage**: In-memory `_jobs` dict in `generate_routes.py` (existing); no new storage.
**Testing**: pytest (route + integration)
**Target Platform**: Linux devcontainer / macOS host, served via Flask review server
**Project Type**: Web UI (Flask + vanilla JS single-page tabs)
**Performance Goals**: Tab switch is synchronous DOM show/hide (<16 ms). Initial
paint under 1 s on warm server for analyzed songs (SC-001). Analysis / audio /
history fetched at most once per page load (SC-005).
**Constraints**: `/timeline`, `/phonemes`, `/story-review` MUST remain reachable at
their current URLs (FR-012). No generator pipeline change (FR-014).
**Scale/Scope**: One new Flask route; two new static files (HTML + JS, small CSS);
refactor of `app.js` into a factory function; ~30 lines added to `generate_routes.py`
for in-flight job reporting.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | ✅ PASS | No change to analysis or timing pipeline; workspace is a view over existing analysis JSON. |
| II. xLights Compatibility | ✅ PASS | No change to `.xsq` output. Generate tab posts to the unchanged `/generate/<hash>` endpoint. |
| III. Modular Pipeline | ✅ PASS | Timeline UI becomes a clean component boundary with explicit inputs (`rootEl`, `hashParam`); tab panels are independent subtrees. |
| IV. Test-First Development | ✅ PASS | Route tests (404, default fragment, in-flight history) and an integration test (open workspace → switch tabs → start generation → download) are written before implementation. |
| V. Simplicity First | ✅ PASS | No new abstractions beyond what the component refactor strictly requires. Brief/Preview tabs are literal placeholder `<div>`s. |

No violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/046-song-workspace-shell/
├── plan.md              # This file
├── research.md          # Component-refactor strategy for index.html / app.js
└── quickstart.md        # Manual verification walkthrough
```

No `data-model.md`: the only data shape change is the history payload's `status`
field gaining two additional enumerated values (`queued`, `running`) alongside
`complete`/`failed`, plus two new fields (`error`, `download_url`) that already
exist elsewhere in the response. Documented inline in the route change below.

### Source Code (affected files)

```text
src/
└── review/
    ├── server.py                          # + /song/<source_hash> route
    ├── generate_routes.py                 # extend /history with in-flight jobs
    └── static/
        ├── song-workspace.html            # NEW — tab shell
        ├── song-workspace.js              # NEW — tab strip, URL fragment sync,
        │                                  #       mounts timeline component,
        │                                  #       generate-tab polling, history
        ├── song-workspace.css             # NEW — tab strip + panel layout
        ├── index.html                     # thin wrapper around #timeline-root
        ├── app.js                         # exports createTimeline({rootEl, hashParam})
        │                                  # auto-mounts when loaded on /timeline
        └── dashboard.js                   # openSong() points to /song/<hash>

tests/
├── unit/
│   └── test_song_workspace_route.py       # 404 on unknown hash, 200 on known,
│                                          # default-tab server-side selection,
│                                          # /timeline still returns index.html
└── integration/
    └── test_song_workspace_flow.py        # open workspace → generate → download
                                           # + in-flight history re-attach
```

No schema changes. No new directories.

**Structure Decision**: The timeline component extraction is confined to `app.js` +
`index.html` and leaves every other caller untouched. The workspace page is a new
peer of `dashboard.html` / `story-review.html` in `static/` — the same patterns
those pages already use. The `/song/<hash>` route is the sole backend addition.

## Implementation Approach

### Change 1: Timeline Component Refactor (`static/app.js`, `static/index.html`)

Wrap the entire body of `app.js` in a factory:

```js
function createTimeline({ rootEl, hashParam = null }) { /* existing code, scoped */ }
window.createTimeline = createTimeline;
```

Every `document.getElementById(...)` at module scope becomes `rootEl.querySelector(...)`.
The `<audio id="player">` element is created by the factory and appended to `rootEl`
instead of being looked up. Module-level `tracks`, `durationMs`, `focusIndex` etc.
move inside the factory closure (no more globals). The `init()` call at the bottom
is replaced with an auto-mount block guarded by the presence of a `#timeline-root`
element:

```js
if (document.getElementById('timeline-root')) {
  createTimeline({ rootEl: document.getElementById('timeline-root'),
                   hashParam: new URLSearchParams(location.search).get('hash') });
}
```

`index.html` becomes a minimal wrapper that provides `<div id="timeline-root">` plus
the existing toolbar. `/timeline?hash=...` continues to serve `index.html` unchanged
from the server's perspective — the wrapper simply hosts the same component at full
page scale and adds the "Open in workspace" link required by FR-012.

When mounted inside the workspace, `song-workspace.js` fetches `/analysis?hash=...`
indirectly by loading `app.js` and calling `createTimeline({ rootEl: analysisPanel,
hashParam })`. The existing `/analysis` endpoint already supports `?hash=<source_hash>`
(server.py:951) so no backend change is needed for the Analysis tab to work per-song.

Keyboard shortcut scoping (Space / Ctrl-+ / arrows) stays on `window` for Phase 2 —
the workspace only ever has one mounted timeline. A follow-up is noted in research.md
if Preview (spec 049) ends up needing a second instance.

### Change 2: In-Flight History (`src/review/generate_routes.py`)

Replace the `status == "complete"` filter in `generation_history` with "all jobs for
this source_hash", sort by `created_at` descending, and emit every status value
(`pending`, `running`, `complete`, `failed`). Add a `download_url` field populated
only when `status == "complete"` and an `error` field populated only when
`status == "failed"`. No new endpoint, no change to the status/start/download
endpoints.

Client contract for the Generate tab on mount:

1. GET `/generate/<hash>/history` once.
2. If any entry has `status` in `{"pending", "running"}`, adopt its `job_id` and
   start polling `/generate/<hash>/status?job_id=...` at 1.5 s intervals (satisfies
   the 2-second FR-006 requirement with margin).
3. Otherwise render the "Previous renders" list from the completed entries and wait
   for the user to click Generate.

### Change 3: Workspace Page (`static/song-workspace.html` + `.js` + `.css`)

`song-workspace.html`: navbar, header (`<h1>` title, duration, analysis status,
layout-ready banner slot), tab strip (`<nav role="tablist">`), four panels
(`<section role="tabpanel">`) with stable ids `#panel-analysis`, `#panel-brief`,
`#panel-preview`, `#panel-generate`. Brief and Preview panels are static placeholder
markup referencing specs 047 and 049 respectively — no JS touches them in Phase 2.

`song-workspace.js`:

- On `DOMContentLoaded`: parse `source_hash` from the URL path, fetch `/library`
  entry to populate header; fetch `/generate/settings` to decide whether to show
  the Zone A layout banner / disable the Generate button (FR-008).
- Tab strip: click handler toggles `hidden` on panels and updates the URL fragment
  via `history.replaceState` (not `pushState`, per edge case: back button exits).
- On first activation of the Analysis tab, `import`-style load `app.js` (a plain
  `<script src="/app.js">` in the HTML head is sufficient) and call
  `createTimeline({ rootEl: panelAnalysis, hashParam: sourceHash })`. Subsequent
  activations are no-ops.
- Generate tab: render the primary Generate button, progress region, download
  region, and history list. Implements the 3-step mount contract above. Polling
  uses `setInterval(1500)` cleared on job completion/failure.
- Brief / Preview tabs: no JS. Panels render pre-baked "Coming soon — feature 047 /
  049" markup.

### Change 4: Route Registration (`src/review/server.py`)

Add beside the existing `/library-view` / `/timeline` / `/phonemes-view` routes:

```python
@app.route("/song/<source_hash>")
def song_workspace(source_hash):
    from src.library import Library
    if Library().find_by_hash(source_hash) is None:
        abort(404, description="Song not found in library")
    return send_from_directory(app.static_folder, "song-workspace.html")
```

The source_hash is re-read client-side from `location.pathname`; the route's job is
purely to gate the 404 and serve the HTML shell.

### Change 5: `openSong()` Redirect (`static/dashboard.js`)

Replace the three-branch switch at lines 434–446 with an unconditional
`window.location.href = '/song/' + encodeURIComponent(hash)`. The `tool` and
`storyPath` parameters become unused — leave the signature intact so call sites
at lines 165, 273–276, 549 keep working, then drop the arguments in a follow-up
cleanup. Spec 045's centralized helper is the sole edit point.

## Testing Strategy

- **Route test** (`test_song_workspace_route.py`): assert 404 for bogus hash; 200
  and HTML body for a Library fixture hash; `/timeline` and `/phonemes-view` still
  return their original static files unchanged.
- **History test** (extend `tests/unit/test_generate_routes.py` or equivalent):
  seed `_jobs` with one `complete`, one `running`, one `failed`; assert all three
  appear in `/generate/<hash>/history`, running entry has no `download_url`, failed
  entry has `error`.
- **Integration test** (`test_song_workspace_flow.py`): Flask test client walks the
  full flow — GET `/song/<hash>`, POST `/generate/<hash>`, poll status, GET
  download. A second scenario seeds a `running` job and asserts the workspace's
  initial history payload contains it (backend guarantee; client re-attach behavior
  is exercised in manual quickstart.md).
- No new Vamp / librosa / analysis runs — Phase 2 is presentation.

## Sequencing Notes

- **Depends on 045**: the centralized `openSong()` helper must exist and be the
  single point updated (this plan's Change 5).
- **Does not remove legacy routes**: `/timeline`, `/phonemes`, `/story-review`
  stay. Future consolidation is out of scope (FR-012).
- **Phase 3 (spec 047) and Phase 5 (spec 049)** replace the Brief and Preview
  panel innerHTML respectively. No other file in this plan needs to be touched
  by those specs — SC-007 and SC-008 are the structural contract.

## Open Questions Resolved by Clarifications

Both clarifications in spec.md (component-vs-iframe, in-flight job detection) are
honored as described in Changes 1 and 2. No further open questions for Phase 2.
