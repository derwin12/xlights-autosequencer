# Segment Classification Changelog

Any change to segment detection, section merging, or section role classification
**must** be logged here with a date, rationale, and description of what changed.
Do not remove old entries — append only. This log exists to prevent going in circles.

---

## 2026-03-31 — Genius quality gate (fallback to heuristics)

**Files:** `src/story/builder.py`

**Problem:** Genius returns poor section data for classical, instrumental, or non-English
songs. Carmina Burana matched TSO's version with Latin section headers (`[Introductio]`,
`[Versum I]`, etc.) — only 4 sections, with Versum II+III merging into a 60-second
"verse" that covers 37% of the song. The heuristic path (segmentino A×3 + N×3 + QM
boundaries) would have produced better results.

**Quality checks added (`_genius_quality_ok()`):**
- Reject if <3 sections for songs >60s
- Reject if any single section covers >60% of song duration
- Reject if fewer than 2 distinct roles (all mapped to same role)
- Reject if >50% of sections are <3s (bad WhisperX alignment)

When Genius data fails the quality gate, `section_source` is set to `"heuristic"` and
the segmentino+energy classifier runs instead.

---

## 2026-03-31 — Implicit intro/outro detection for Genius sections

**Files:** `src/story/builder.py`

**Problem:** Genius sections don't include `[Intro]` or `[Outro]` tags for most songs.
The first Genius section starts at the first lyric (e.g. 10s into the song), leaving
the instrumental intro unaccounted for. The last section runs all the way to the song
duration, even when the song clearly fades out — e.g. Santa Tell Me's last "chorus"
was 52 seconds because Genius had no `[Outro]` after the final `[Chorus]`.

**Energy analysis (Santa Tell Me tail):**
```
02:30 → energy=36.3
02:50 → energy=38.7
03:00 → energy=26.1  ← drop starts here
03:10 → energy=23.6
03:20 → energy=5.6   ← clearly an outro
```

**Changes:**
1. **Implicit intro**: If the first Genius section starts >3s into the song, insert an
   `intro` section from 0 to that start time.
2. **Implicit outro**: If the last section is >15s long and the energy in its tail (last
   15s) drops below 60% of its first-half energy, scan backwards to find the crossover
   point and split off an `outro` section.

**Note:** This only applies to Genius-sourced sections. The heuristic fallback already
handles intro/outro via positional rules.

---

## 2026-03-31 — Genius user prompt on lookup failure

**Files:** `src/review/server.py`, `src/review/static/upload.js`, `src/review/static/upload.html`,
`src/analyzer/genius_segments.py`

**Problem:** When a song had no ID3 tags and the filename-derived title didn't match
Genius, the Genius lookup silently failed and fell back to heuristics. The user had
no opportunity to correct the search.

**Changes:**
1. `genius_segments.py` — Falls back to filename when ID3 tags are missing. Supports
   `_GENIUS_OVERRIDE_ARTIST` / `_GENIUS_OVERRIDE_TITLE` env vars for user-provided values.
2. `server.py` — After story build, if `section_source != "genius"`, emits a
   `genius_prompt` SSE event with the guessed artist/title. Background thread blocks
   on `threading.Event` waiting for user response. New `/genius-retry` endpoint
   receives the user's artist/title and unblocks the thread.
3. `upload.js` — Handles `genius_prompt` event: shows a purple form with artist/title
   fields and Search/Skip buttons. Search posts to `/genius-retry`; Skip sends
   `__skip__` sentinel.
4. `upload.html` — CSS for the Genius prompt form.

---

## 2026-03-31 — Genius lyrics as primary section source

**Files:** `src/story/builder.py`, `src/story/section_classifier.py`, `scripts/compare_genius_sections.py`

**Problem:** Genius comparison on Ghostbusters revealed energy+segmentino heuristics
produce structurally wrong results when a song's energy profile doesn't match
conventional verse/chorus expectations.

**Comparison output (Ghostbusters):**

```
Genius sequence (12 sections):
  intro → verse → chorus → verse → chorus → verse → bridge → verse → interlude → chorus → verse → outro

Our sequence (11 sections):
  intro → chorus → verse → pre_chorus → chorus → verse → pre_chorus → chorus → verse → pre_chorus → outro
```

**Specific failures:**
1. **Our "pre_chorus" = Genius "chorus"** — "I ain't afraid of no ghost" IS the chorus.
   Energy heuristics classified it as pre_chorus because it's lower energy than the
   "Ghostbusters!" call-and-response verses.
2. **Our "chorus" at s02 = Genius "verse"** — The high-energy "Ghostbusters!" hook is
   part of the verses, not a standalone chorus. Energy-based classifier inverted this.
3. **93-second s09 "verse"** — One merged section swallowed 6 Genius sections: verse 3,
   bridge, verse 4, interlude, chorus, and verse 5. The consecutive-same-role merger
   from the earlier change collapsed too aggressively when the heuristic got the base
   labels wrong.
4. **Missing bridge and interlude** — Genius has both; we produced neither. The segmentino
   boundaries for that range were merged into one giant section.
5. **3 phantom "pre_chorus" sections** — Genius has zero pre-choruses. Our label-aware
   classifier invented them by assuming sections before the (wrongly labeled) "chorus"
   must be pre-choruses.

**Root causes:**
- Energy heuristics assume chorus = high energy. Ghostbusters has high-energy verses
  ("Ghostbusters!") and lower-energy choruses ("I ain't afraid of no ghost").
- Segmentino labels (A, B, C) indicate musical repetition but not lyric function.
  The most-repeated high-energy label being "chorus" is an assumption that fails here.
- Without lyric text, there's no way to know what the section actually IS — energy
  and repetition patterns are insufficient.

**Fix:** When Genius API data is available, use it as the primary source for section
labels (chorus, verse, bridge, etc.) instead of guessing from energy+segmentino.
Fall back to heuristics only when Genius isn't available.

**Changes:**
1. `builder.py` — When `GENIUS_API_TOKEN` is set, fetch Genius lyrics, parse section
   headers, and use WhisperX forced alignment to map each lyric section to a time
   range. These become the primary section boundaries and roles.
2. `section_classifier.py` — Energy heuristics remain as fallback when Genius is
   unavailable.
3. Added `scripts/compare_genius_sections.py` — diagnostic tool to compare Genius
   sections against our classifier output for any song.

---

## 2026-03-31 — Energy scale fix (0–100 not 0–1)

**Files:** `src/story/section_profiler.py`, `src/story/section_classifier.py`

**Problem:** Every section had `energy_score=100`. The profiler multiplied 0–100 curve
values by 100 (treating them as 0.0–1.0 floats), clamping everything to 100.
The classifier's thresholds (0.05, 0.3, 0.65) were also calibrated for 0–1 but received
0–100 values, making every section appear high-energy and vocal.

**Changes:**
1. `section_profiler.py` — Removed `* 100` from `energy_score` and `energy_peak`.
   Normalized variance to 0–1 by dividing by 2500 (max possible for 0–100 range).
2. `section_classifier.py` — `_avg_curve()` now normalizes values >1.0 to 0.0–1.0
   by dividing by 100, so thresholds work correctly.

---

## 2026-03-31 — Label-aware classifier + consecutive merge

**Files:** `src/story/section_classifier.py`, `src/story/builder.py`

**Problem:** Too many sections labeled "verse". For Ghostbusters, nearly every vocal
section was classified as verse because the classifier only had two paths for vocal
sections: chorus (top 40% energy) or verse (everything else). Songs with uniform
high energy had almost no sections clear the chorus threshold.

**Root cause:**
- Binary vocal classification — `pre_chorus`, `bridge`, `post_chorus` were defined
  in `VALID_ROLES` but never assigned by any code path.
- Chorus threshold `vocal_median + 0.6 × (vocal_max − vocal_median)` was too strict
  (required top 40% of energy range). Uniform-energy songs produced few choruses.
- Segmentino's own repetition labels (A, B, C…) were extracted and stored but never
  used by the classifier.
- No post-processing to collapse consecutive same-role sections.

**Changes:**
1. `section_classifier.py` — New `_classify_by_labels()` path (used when segmentino
   labels are available):
   - Groups sections by segmentino label; computes per-label average energy and count.
   - Most-repeated high-energy vocal label → `chorus`.
   - Section immediately before a chorus-label section → `pre_chorus`.
   - Vocal label that appears only once and follows a chorus → `bridge`.
   - Fallback heuristic chorus threshold loosened from top-40% to top-25% of energy range.
2. `builder.py` — Extracts segmentino labels per boundary and maps dominant label to
   each merged section. Passes `section_labels` to `classify_section_roles()`.
3. `builder.py` — Post-classification step merges consecutive sections with the same
   role into one (collapses segmentino over-splits within a single musical section).

**Note:** Multiple distinct verses are still correct and expected when there are genuine
musical differences between them (different lyrics, energy trajectory, etc.). The merge
only collapses *adjacent* same-role sections with no different role between them.

---

## 2026-03-26 — Initial section classification (baseline)

**Files:** `src/story/section_classifier.py`, `src/story/section_merger.py`, `src/story/builder.py`

**Approach:**
- `section_merger.py`: Merges raw segmentino boundaries into 8–15 sections
  (`min_duration_ms=4000`, `target_max=15`). Short sections (<4s) are absorbed
  into their shorter neighbour. Excess sections merged by shortest-combined-duration.
- `section_classifier.py`: Energy + vocal heuristics only.
  - No vocals anywhere → instrumental fallback (intro / instrumental_break / interlude / outro).
  - Vocal sections: top 40% of vocal-energy range → `chorus`; remainder → `verse`.
  - Non-vocal sections mid-song: `instrumental_break` if surrounded by vocal sections,
    else `interlude`. First section → `intro`. Last section → `outro`.
- `builder.py`: Extracted raw boundaries from `hierarchy["sections"]` (segmentino marks),
  passed timestamps only (labels discarded) to `merge_sections()` then `classify_section_roles()`.

**Known limitations at time of writing:**
- `pre_chorus`, `bridge`, `post_chorus` never assigned.
- Segmentino labels ignored.
- Uniform-energy songs produce too many verses.
- No consecutive same-role merging.
