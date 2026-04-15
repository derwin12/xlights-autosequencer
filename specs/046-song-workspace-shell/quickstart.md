# Quickstart: Song Workspace Shell

**Feature**: 046-song-workspace-shell | **Date**: 2026-04-14

A manual verification walkthrough for the `/song/<source_hash>` page. Run this
against a dev Flask server after implementation to confirm the four-tab shell,
the timeline component refactor, and the in-flight history extension all work.

## Prerequisites

- A Flask review server running (`xlight-analyze review <hash>` or the upload-mode
  default).
- A song already in the library with a completed hierarchy analysis. Note its
  `source_hash`. Use `curl http://localhost:5173/library | jq '.entries[0]'` to
  grab one.
- A layout configured via the grouper (otherwise the Generate button is gated —
  that case is verified in step 6).

## Steps

### 1. Landing on the workspace

Navigate to `http://localhost:5173/song/<source_hash>`.

**Expect**:
- Page renders within 1 second.
- Header shows the song's title, duration, and analysis status.
- Four tabs in the order **Analysis / Brief / Preview / Generate & Download**.
- Analysis tab is active. URL bar shows `.../song/<hash>` (no fragment, or
  `#analysis`).

### 2. Analysis tab parity with `/timeline`

Confirm the Analysis tab is a full timeline UI.

**Expect**:
- Waveform, per-track lanes, Play / Prev / Next / Focus / Zoom controls visible.
- Click Play — audio plays, cursor advances, beat indicator flashes.
- Open a second browser tab to `/timeline?hash=<source_hash>`. The same UI
  renders full-page (toolbar at top, tracks below).
- Both pages should load the same analysis JSON without errors in the browser
  console.

### 3. Tab switching preserves state

Back on `/song/<hash>`:

- Start playback in the Analysis tab.
- Scroll the track list and focus a track with the arrow keys.
- Click the **Generate & Download** tab.
- URL fragment updates to `#generate` (check the address bar).
- Click **Analysis** again.

**Expect**: the playback continued while the tab was hidden, the same track is
still focused, and the scroll position is preserved. Nothing was re-fetched
(open DevTools → Network → Fetch/XHR; no new `/analysis` or `/audio` request on
tab switch).

### 4. Deep-link fragment

Open a fresh window at `http://localhost:5173/song/<source_hash>#generate`.

**Expect**: the Generate tab is active on first paint (no Analysis-tab flash).

### 5. Brief and Preview placeholders

Click **Brief**.

**Expect**: "Coming soon — feature 047" placeholder. No form, no network activity,
no audio change.

Click **Preview**.

**Expect**: "Coming soon — feature 049" placeholder. No network activity, no audio
starts from this tab.

### 6. Layout-gate banner

Temporarily clear the layout setting (`rm ~/.xlight/settings.json` or equivalent)
and reload `/song/<source_hash>`.

**Expect**: a banner or inline tooltip on the Generate tab explaining layout
setup is required; the Generate button is disabled. Restore the layout and reload;
the banner disappears.

### 7. Start a generation

On the Generate & Download tab, click **Generate**.

**Expect**:
- Button disables; a progress region appears with a spinner and a status label.
- DevTools Network panel shows a POST to `/generate/<hash>` returning 202 with
  a `job_id`, then periodic GETs to `/generate/<hash>/status?job_id=...` at
  roughly 1.5-second intervals.
- On completion, a prominent **Download** link appears pointing to
  `/generate/<hash>/download/<job_id>`. Click it; the browser downloads an
  `.xsq` file.

### 8. History list

Reload the page (`/song/<hash>#generate`).

**Expect**: a **Previous renders** list with at least one row — the generation
just completed — showing a timestamp, a short config summary, and a working
re-download link. Rows are sorted newest-first.

### 9. In-flight re-attach (FR-013)

Start another generation. While it is running, reload the page (don't wait for
completion).

**Expect**:
- DevTools shows one GET to `/generate/<hash>/history` on mount.
- Response includes the still-running job with `status: "running"`.
- The Generate tab immediately shows the progress UI (not the idle Generate
  button) and resumes polling the same `job_id`.
- The second generation completes normally; no duplicate job was started.

### 10. 404 handling

Visit `/song/not-a-real-hash-1234`.

**Expect**: HTTP 404 with a message pointing back to the library view.

### 11. Legacy routes still work (FR-012)

Navigate to each of:

- `/timeline?hash=<source_hash>`
- `/phonemes-view?hash=<source_hash>` (if phoneme data exists for this song)
- `/story-review?path=<story_json_path>`

**Expect**: each page loads its existing content unchanged. A small "Open in
workspace" affordance links back to `/song/<source_hash>#analysis` (optional,
per FR-012 — present only when the source_hash is resolvable).

### 12. Dashboard Open button (depends on spec 045)

From `/` (dashboard), click a song's **Open** button.

**Expect**: navigation to `/song/<source_hash>` — a single destination regardless
of story/phoneme/timeline capability state.

## Pass Criteria

All twelve steps produce the expected result. If step 7 or 9 fails, inspect the
server log for generation errors; if steps 2 or 3 fail, recheck the component
refactor (see research.md §3 "Component Boundary") for lingering `document.`-rooted
DOM lookups.
