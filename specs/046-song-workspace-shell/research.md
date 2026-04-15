# Research: Song Workspace Shell

**Feature**: 046-song-workspace-shell | **Date**: 2026-04-14

This feature's only real research question is **how to make the existing timeline
UI mountable inside a tab panel without regressing the standalone `/timeline`
page or duplicating code**. Everything else — adding a Flask route, a tab strip,
a history-fetch-on-mount, a placeholder panel — is conventional.

---

## 1. Current Structure of the Timeline UI

`src/review/static/index.html` (80 lines) is a single document with:

- A top `#toolbar` div holding Play/Prev/Next/Focus/Zoom/Export/Phonemes/Legend buttons.
- A `#main` row containing `#panel` (track list + stem filter) and `#canvas-wrap`
  (two stacked `<canvas>` elements, bg + fg).
- A bare `<audio id="player" src="/audio" preload="auto">`.
- A `#legend-panel` overlay.
- A `#status` bar.
- `<script src="/navbar.js">` and `<script src="/app.js">` at the bottom.

`src/review/static/app.js` (945 lines) is written against a single-instance model:

- **Module-level globals**: `tracks`, `dragSrcIndex`, `phonemeLayers`, `songSegments`,
  `durationMs`, `focusIndex`, `activeStemFilter` (lines 5–11).
- **Module-level DOM handles**: `player`, `bgCanvas`, `fgCanvas`, `bgCtx`, `fgCtx`,
  `panel`, `stemFilterBar`, `trackList`, `canvasWrap`, `beatFlash`, `btnPlay`,
  `btnPrev`, `btnNext`, `btnClear`, `btnExport`, `timeDisplay`, `focusLabel`,
  `selectedCount`, `status`, `zoomLabel`, `btnZoomIn` (lines 36–80).
- **Module-level constants** for lane heights, colors, zoom bounds (lines 13–63).
- **Functions** for drawing, zoom, stem filter, export queue, keyboard shortcuts,
  all operating on the above globals.
- A final `init()` call at line 945 that fetches `/analysis` and kicks off rendering.

The code reads like a classic single-page Canvas app: one document, one analysis
file, one audio element. Every DOM reference is by id.

---

## 2. Options Considered

### Option A — Iframe the existing page

Wrap the Analysis tab's content in `<iframe src="/timeline?hash=...">`. Zero code
changes to `app.js`.

**Rejected** by clarification (Session 2026-04-14). Reasoning captured in spec.md:
shared audio-playback state, tab-fragment navigation, CSS consistency, and future
Preview-tab integration (spec 049) all become awkward with an iframe boundary.

### Option B — Duplicate the timeline into the workspace

Copy `app.js` into `song-workspace-timeline.js`, prefix ids, diverge over time.

**Rejected**: trivially violates Simplicity First. Two 945-line files to maintain.

### Option C — Factory function with scoped DOM (**chosen**)

Wrap the contents of `app.js` in `function createTimeline({ rootEl, hashParam })`
and replace `document.getElementById('foo')` with `rootEl.querySelector('#foo')`
inside the factory. Move module-level globals into the factory closure. Auto-mount
on `/timeline` by checking for a `#timeline-root` element at load time.

**Chosen**: smallest refactor that delivers a real component boundary, no new build
tooling, no module system change. Vanilla ES2020 in one file stays the house style
matched by `dashboard.js`, `grouper.js`, etc.

---

## 3. Component Boundary (Chosen Design)

```js
// app.js (refactored shape)
function createTimeline({ rootEl, hashParam = null }) {
  // --- scoped state (was module-level) ---
  let tracks = [];
  let durationMs = 0;
  let focusIndex = null;
  let pxPerSec = 100;
  // ...

  // --- scoped DOM handles (all via rootEl) ---
  const player = rootEl.querySelector('audio');
  const bgCanvas = rootEl.querySelector('#bg-canvas');
  // ...

  // --- existing functions, now closures ---
  function drawBackground() { /* uses bgCtx, durationMs, pxPerSec */ }
  // ...

  async function init() {
    const url = hashParam ? `/analysis?hash=${hashParam}` : '/analysis';
    const resp = await fetch(url);
    // ...
  }

  init();
  return { /* nothing public in Phase 2 */ };
}

window.createTimeline = createTimeline;

// Auto-mount when loaded on the standalone /timeline page
if (document.getElementById('timeline-root')) {
  const params = new URLSearchParams(location.search);
  createTimeline({
    rootEl: document.getElementById('timeline-root'),
    hashParam: params.get('hash'),
  });
}
```

### What moves into `rootEl`

Everything currently at the top of `<body>` in `index.html` except `<script>` tags:
the toolbar, the main layout, the `<audio>` element, the legend panel, and the
status bar. The workspace's Analysis tab panel becomes the `rootEl` and inherits
that entire DOM as its child — which is exactly right because the toolbar controls
belong to the timeline, not to the page chrome.

### What stays outside

- Navbar script: loaded once by the hosting page, not the component.
- Page-level `<title>`: set by the hosting page.
- `/audio` endpoint: unchanged; the component still fetches `src="/audio"`.
  (When hosted per-song in the workspace, the server resolves `source_hash` via
  `/open-from-library` — which `dashboard.js` already calls before navigation —
  so the current-job audio routing keeps working without a new endpoint.)

### Keyboard shortcuts

Today the shortcuts (`Space`, `Ctrl+-`, `Ctrl+0`, `ArrowUp/Down`) are bound on
`window` inside `app.js`. Keeping them on `window` inside the factory is safe for
Phase 2: the workspace only mounts one timeline. If Preview (spec 049) eventually
mounts a second timeline, the fix is to bind on `rootEl` instead. That is a
documented follow-up, not Phase 2 scope.

---

## 4. Shared State Across Tabs

Spec clarification: "Shared audio-playback state across tabs is permitted but not
required in Phase 2."

The chosen design does **not** share state. Each tab is self-contained:

- Analysis tab owns one `createTimeline()` instance, which owns its own `<audio>`.
- Brief / Preview tabs are static placeholders; they do not load audio.
- Generate tab has no audio element; it only posts/polls JSON.

This is simple and matches the FR-010 requirement ("inactive tab's DOM state is
preserved"): switching away from Analysis pauses nothing — the audio continues
playing, the timeline cursor continues advancing in the hidden panel — because
nothing in the workspace tells it to stop. That is the desired behavior for a
user flipping to Generate mid-playback; Phase 2 does not need an explicit
audio-orchestrator layer.

If Phase 5 (Preview) wants a shared-playback model, the factory return value is
the hook: it can be extended to return `{ pause, play, seek, currentTimeMs }` and
the workspace can coordinate. Nothing in Phase 2 precludes that.

---

## 5. History-Payload Extension

The existing `/generate/<hash>/history` endpoint filters to `status == "complete"`.
To support FR-013 (re-attach to running jobs without a new endpoint), remove that
filter and surface every job for the hash. The status enum already has
`pending` / `running` / `complete` / `failed` — no new states. Two optional fields
(`download_url` when complete, `error` when failed) round out the row so the
client does not need to branch on status before rendering.

No DTO / data-model file is warranted because the shape change is three lines:

```diff
- completed = [j for j in _jobs.values() if j.source_hash == source_hash and j.status == "complete"]
- completed.sort(key=lambda j: j.created_at, reverse=True)
+ jobs = [j for j in _jobs.values() if j.source_hash == source_hash]
+ jobs.sort(key=lambda j: j.created_at, reverse=True)
```

and two conditional fields in the serialized dict comprehension.

---

## 6. Risks / Unknowns

- **Risk**: `app.js` contains subtle `document.`-rooted DOM lookups inside nested
  helpers that are easy to miss during the scoping pass.
  **Mitigation**: grep for `document\.getElementById` and `document\.querySelector`
  in `app.js` during implementation; every hit must either move to `rootEl.`-rooted
  or be explicitly justified as global (the shortcut bindings on `window`).

- **Risk**: The `<audio id="player">` relies on the browser's default media-session
  behavior (play/pause hardware keys bind to whichever element plays most recently).
  Moving the element inside the factory does not change this, but verify during
  quickstart.

- **Unknown**: Whether any existing test asserts on id uniqueness across the
  timeline page (e.g., "only one `#player` in the DOM"). If so, the workspace —
  which has only one timeline mount in Phase 2 — passes trivially.

No other unknowns. The refactor is mechanical; the route addition is boilerplate;
the history change is three lines.
