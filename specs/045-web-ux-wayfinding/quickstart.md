# Quickstart: Web UX Phase 1 Wayfinding (045)

## What It Does

The dashboard's five-step decorative strip becomes a stateful four-step strip
(Upload → Review → Story → Generate). Layout Groups is surfaced as a one-time
Zone A banner above the library — visible only when unconfigured. Each song
row's detail panel collapses from seven equally-weighted buttons to one primary
"Open" button plus a kebab overflow menu. Rows show lifecycle badges
(Analyzed / Generated / Stale). Deep pages get a consistent "Back to Library"
breadcrumb.

## Key Files

| File | Change |
|------|--------|
| `src/review/server.py` | Extend `/library` `_enrich()` with 4 new fields (~line 570) |
| `src/review/static/dashboard.html` | Rewrite strip (lines 67–94) to 4 steps; rewrite detail-template (lines 134–164); add `#zone-a-banner` |
| `src/review/static/dashboard.js` | New `applyStripState()`, `renderZoneABanner()`, `openSong(hash)` canonicalization; extend `renderBadges()` and `renderDetail()` |
| `src/review/static/dashboard.css` | New states `.workflow-step[data-state=…]`, `.zone-a-banner`, `.btn-open`, `.overflow-menu`, `.badge-analyzed`, `.badge-generated`, `.badge-stale` |
| `src/review/static/navbar.js` | Extend `SONG_TOOL_PAGES` to include `/grouper`, `/themes/`, `/variants/` |

## How to Verify Locally

Start the review server:

```bash
python3 -m src.cli review
# opens http://localhost:5173
```

### 1. Strip is stateful

- With a library containing at least one analyzed song and a configured layout,
  expand a row. Verify step 1 and step 2 show the `complete` visual, step 3
  shows `complete` (has_story=true) or `active` (no story yet), step 4 shows
  `active` (layout configured, never generated) or `complete` (generated).
- Collapse all rows. Strip reverts to all grey (neutral).

### 2. Zone A banner appears when layout is missing

```bash
# Remove the layout setting
python3 -c "from src.settings import save_settings; save_settings({'layout_path': None})"
# Reload the dashboard — banner must appear, Set Up Layout button links to /grouper
```

- Every row's Generate action (strip step 4, overflow menu entry, row-level
  button if any) must be disabled with a tooltip referencing the banner.
- Re-configure layout via `/grouper`, reload — banner gone, Generate enabled.

### 3. Open + overflow

- Expand a row. Exactly one primary "Open" button is visible. Clicking it
  routes to `/timeline?hash=<md5>` (same destination as today's Review Timeline).
- Click the kebab (or "More" control). Menu shows exactly: Preview Generation,
  Story Review, Phonemes, Generate Sequence, Re-analyze, Delete. Each routes to
  today's destination.
- Click outside the menu or press Escape — menu dismisses without navigating.

### 4. Lifecycle badges

- A freshly-analyzed, never-generated song shows an `Analyzed` badge.
- A song with a completed generation in the current server session shows
  `Generated` (replaces `Analyzed`).
- Touch the source MP3 with new content (or rename an existing MP3 so its MD5
  no longer matches the library index entry) and reload — row shows `Stale`.
- No row ever shows `Briefed` in Phase 1.

### 5. Back to Library from deep pages

- Visit `/timeline`, `/story-review`, `/phonemes-view`, `/grouper`, `/themes/`,
  `/variants/`. Each must render a breadcrumb with a "Song Library" link that
  routes to `/`.

### 6. Route-reachability audit (SC-005)

Every existing route must still resolve:

```bash
for path in /timeline /story-review /phonemes-view /grouper /themes/ /variants/; do
  curl -sI "http://localhost:5173$path" | head -1
done
# All must return 200 OK
```

## Validation Checklist

- [ ] Expanding an analyzed row on a configured-layout library shows complete/active/incomplete/blocked states distinctly (SC-001).
- [ ] Clearing layout configuration surfaces the banner and disables every Generate control (SC-002).
- [ ] "Which button should I click first?" reads as "Open" without hesitation (SC-003).
- [ ] `grep -n 'openSong' src/review/static/dashboard.js` shows the single canonical `openSong(hash)` helper that spec 046 will retarget (SC-004, SC-008).
- [ ] All seven existing routes return 200 OK (SC-005).
- [ ] Library rows with ≥1 analyzed, ≥1 generated, ≥1 stale song display the correct badge on each (SC-006).
- [ ] `git diff --stat` touches only `src/review/` paths (SC-007).
