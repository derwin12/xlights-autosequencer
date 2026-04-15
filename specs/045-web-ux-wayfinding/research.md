# Research: Web UX Phase 1 Wayfinding (045)

## Decision 1: `layout_configured` derived from `src.settings.get_layout_path()`

**Decision**: Compute `layout_configured` server-side in `/library` by calling
`src.settings.get_layout_path()` and checking the returned `Path.exists()`.

**Rationale**: This mirrors how the generator wizard and `/grouper` already
treat the setting. `get_layout_path()` handles show-dir-relative resolution
(see `src/settings.py:37`). We explicitly check `.exists()` so a
stale settings entry (layout file moved/deleted — Edge Case in spec) reports
as not configured and re-surfaces the banner.

**Alternatives considered**:
- Client-side fetch of `/settings`: doubles the request count on dashboard load.
- New `/layout-status` endpoint: per clarification Q2, we avoid adding endpoints.

---

## Decision 2: `last_generated_at` sourced from in-memory `_jobs`

**Decision**: Read `src.review.generate_routes._jobs` for the newest completed
job matching each `source_hash` and emit its `created_at` as ISO-8601.

**Rationale**: `generate_routes.py:222` already exposes `/generate/<hash>/history`
which is fed by this same dict. No persisted generation history exists today,
so restarting the server wipes `last_generated_at`. That is the correct Phase 1
behavior — generations that predate the current server process shouldn't count
as "step 5 complete" because their artifacts may be gone.

**Alternatives considered**:
- Scan the filesystem for `.xsq` files adjacent to each MP3: brittle (generated
  files land in `tempfile.mkdtemp()` per spec 034), and defining what counts as
  "this song's .xsq" is out of scope for Phase 1.
- Persist generation history to `~/.xlight/generations.json`: real improvement,
  but outside Phase 1 scope.

---

## Decision 3: `is_stale` = recomputed MD5 ≠ stored `source_hash`

**Decision**: Recompute MD5 of the source file and compare against
`e.source_hash` from the library index. Skip (emit `False`) when the source is
missing. Cache results in-process by `(source_file, mtime, size)` to avoid
re-hashing on every dashboard poll.

**Rationale**: The library key IS the source MD5 (`src/library.py:16`), so a
mismatch means the file changed since analysis — the exact definition of
"stale" in FR-011. Hashing is ~50ms per 5MB MP3; with the (mtime, size) cache
only the first request pays that cost.

**Alternatives considered**:
- Compare mtimes: too lenient (touch changes mtime without real content change).
- Store a rolling MD5 in the library index: premature persistence for a
  read-only display attribute.

---

## Current DOM Reference

### Dashboard workflow strip
Lives at `src/review/static/dashboard.html` lines 67–94. Five `.workflow-step`
divs with `data-step` values `upload | review | story | layout | generate`.
No state bindings today; all steps render identically. Phase 1 removes `layout`
and adds `data-state={complete|active|incomplete|blocked|neutral}`.

### Detail template
Lives at `dashboard.html` lines 134–164. Seven action buttons in
`.detail-actions`, bound by `data-action` strings in `dashboard.js` line 270.
Phase 1 rewrites to primary `.btn-open` + `.overflow-menu` with six menuitems.

### Row badges
Rendered by `renderBadges(e)` at `dashboard.js` lines 229–238 into the
`col-badges` column. Today emits `Stems | Phonemes | Story | Missing`. Phase 1
prepends lifecycle badges `Analyzed | Generated | Stale`.

### Navbar breadcrumb
`src/review/static/navbar.js` lines 16–21 defines `SONG_TOOL_PAGES`:
`/timeline | /story-review | /phonemes-view | /sweep-view`. Breadcrumb
renders at lines 68–100. Phase 1 adds `/grouper | /themes/ | /variants/`
as no-song-context entries.

### `/library` endpoint shape
`src/review/server.py:447` — `library_index()` returns
`{version, entries: [enriched-entry, ...]}`. `_enrich()` at lines 469–570
computes per-entry dict with `source_file_exists`, `analysis_exists`,
`has_story`, `has_phonemes`, etc. Phase 1 adds `layout_configured`,
`last_generated_at`, `is_stale` (and keeps `has_story` which already exists).

### Settings
`~/.xlight/settings.json` via `src/settings.py:7`. Key `layout_path`,
stored show-dir-relative. `get_layout_path()` returns an absolute Path or None.
