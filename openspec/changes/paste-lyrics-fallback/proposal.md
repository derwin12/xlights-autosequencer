# Proposal: paste-lyrics fallback

## Why

`src/analyzer/synced_lyrics.py` looks up lyrics via `syncedlyrics` against a
fixed provider allowlist (lrclib, Musixmatch, NetEase, Deezer, Megalobiz,
Lyricsify — Genius is deliberately excluded, see
`docs/segment-classification-changelog.md` 2026-07-11 "no genius.com access
in any form"). Brand-new or niche releases genuinely have no match anywhere
in that allowlist — verified directly against "Shake the Snowglobe" (Gwen
Stefani, a just-released Christmas single): every provider returned nothing,
while a known song (Bohemian Rhapsody) succeeded through the same code path,
confirming the lookup mechanism itself works and this is a coverage gap, not
a bug.

When this happens today, the user has no recourse — `chorus_body` and word
timing for boundary refinement stay empty for that song, and the Timeline's
lyrics track is blank. The user can find lyrics themselves (e.g. Genius,
which this project won't scrape automatically) and wants to paste them in
by hand.

## What Changes

- Add `parse_pasted_lyrics(text: str) -> dict` to `src/analyzer/synced_lyrics.py`,
  reusing the existing `parse_lrc` / plain-line / `_is_credit_line` logic so
  pasted text is validated and previewed the same way a provider result is.
  Returns the same `{found, reason, line_count, preview}` shape as
  `check_synced_lyrics_with_text`, plus `source: "pasted"`.
- Add `POST /api/v1/lyrics/paste` to `src/review/api/v1/analysis.py`. Accepts
  `{title, artist, lyrics_text}`, rejects blank text, stores the raw text in
  the existing `_lyrics_cache` dict (same cache `check_lyrics` already writes
  to and `start_analyze` already reads from), and returns the same JSON shape
  as `/lyrics/check`.
- Add a "Paste Lyrics" button next to "Check Lyrics" on the Analyze screen's
  pre-analysis metadata panel, opening a new `PasteLyricsDialog` modal
  (textarea + Save/Cancel, following the existing `ReanalysisDialog`
  overlay/dialog CSS-module convention). On save, calls the new endpoint and
  feeds the response into the same `lyricsCheckResult` state and ✓/✗ display
  `handleCheckLyrics` already populates.

## What Does NOT Change

- The provider allowlist, `syncedlyrics` search logic, or the Genius
  exclusion — pasting is a manual, user-driven action, not an automated
  fetch, so it doesn't reopen that decision.
- `build_song_story`, `get_boundary_refinement_inputs`, or any section
  detection/merging/classification logic. Pasted text lands in the exact
  same `lyrics_text_override` → `_lyrics_cache` path an automatically-found
  result already uses; consumers can't tell the difference and don't need
  to. No changelog entry under
  `docs/segment-classification-changelog.md`'s mandatory rule is needed —
  that rule covers changes to detection/merging/classification behavior,
  and this changes only where the input text comes from.
- The `/lyrics/check` endpoint's contract or its existing tests
  (`tests/review/test_api_analysis.py:260-306`) — it keeps doing exactly one
  job (search providers), and paste gets its own endpoint rather than an
  `if lyrics_text provided, skip search` branch bolted onto it.

## Alternative Considered

Add an optional `lyrics_text` field to the existing `/lyrics/check` body:
when present, skip the provider search and just validate/cache the given
text. Rejected — it would blur a single-purpose route into two behaviors
(search vs. accept-as-given) behind one conditional, muddying what "check
lyrics" means for logging/telemetry and for the three existing tests that
assert the route always calls `check_synced_lyrics_with_text`. A dedicated
`/lyrics/paste` route matches the project's existing one-route-one-job
pattern (metadata `PATCH`, analyze `POST`, lyrics `check` `POST` are all
already separate single-purpose routes).

## Historical Echoes

- **2026-07-11, Genius removal** (`docs/segment-classification-changelog.md`):
  this project does not access genius.com in any form. Pasting keeps that
  boundary intact — the user, not the app, visits whatever page they choose
  and copies text out of their browser.
- **bug-414** (`.wolf/buglog.json`, 2026-07-20): a provider (NetEase)
  injected credit lines (`作词 : ...`) as ordinary timed lines, which
  contaminated the lyrics timeline and forced word timing before
  `_is_credit_line` was added. Pasted text — especially copy-pasted from a
  lyrics site with an attribution block — is at least as likely to include
  these. Reusing `parse_lrc`/the plain-line path (both already run through
  `_is_credit_line`) for pasted text avoids reintroducing this, rather than
  writing new parsing logic that would need its own filter.
- **bug-406** (`.wolf/buglog.json`, 2026-07-19): lyrics lookups silently
  failed when run against filename-derived title + "Unknown" artist because
  the search fired before the user had a chance to correct metadata. The
  fix added the title/artist review step before "Check Lyrics"/"Start
  Analysis". "Paste Lyrics" sits in that same reviewed panel and is keyed
  into `_lyrics_cache` by the same `(title, artist)` pair the user has
  already confirmed there — no new metadata-timing issue introduced.

## Files Touched

- `src/analyzer/synced_lyrics.py` — modified (add `parse_pasted_lyrics`)
- `src/review/api/v1/analysis.py` — modified (add `POST /api/v1/lyrics/paste`)
- `src/review/frontend/src/screens/Analyze.tsx` — modified (Paste Lyrics
  button + dialog wiring)
- `src/review/frontend/src/components/PasteLyricsDialog/PasteLyricsDialog.tsx` — added
- `src/review/frontend/src/components/PasteLyricsDialog/PasteLyricsDialog.module.css` — added
- `tests/unit/test_synced_lyrics.py` — modified (add `parse_pasted_lyrics` tests)
- `tests/review/test_api_analysis.py` — modified (add `/lyrics/paste` tests)
- `src/review/frontend/tests/screens/Analyze.test.tsx` — modified (button/dialog wiring)
- new `src/review/frontend/tests/components/PasteLyricsDialog.test.tsx`

## Regression Surface

- `_lyrics_cache` (`src/review/api/v1/analysis.py:36`) — currently written
  only by `check_lyrics`; will also be written by the new paste route. Sole
  reader is `start_analyze`'s lookup by `(lib_title, lib_artist)`
  (`analysis.py:422-428`), which is provenance-agnostic — no change needed
  there.
- `check_synced_lyrics_with_text` / `check_synced_lyrics_available` /
  `get_boundary_refinement_inputs` — signatures unchanged, no new callers.
- No public JSON/XML schema field changes; `/lyrics/paste`'s response reuses
  the existing `{found, reason, line_count, preview}` shape plus one
  additive `source` field the frontend can ignore safely if absent.
