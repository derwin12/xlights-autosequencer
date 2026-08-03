# Proposal: scope Unmap/Shadow to a single lyric occurrence

## Why

User report (2026-08-02, real song in progress — "Dream On"): the Pictures
screen already lists every lyric occurrence of a word individually, each
with its own timestamp (the screenshot shows 9 separate "DREAM" rows at
3:02, 3:03, 3:05, 3:06, 3:07, 3:14, 3:15, 3:16, 3:18, all matched to
`dream2.png`). But clicking **Unmap** or **Shadow** on any single row acts
on the *word text*, not that occurrence — it unmaps/shadow-tags **every**
occurrence of "DREAM" in the whole song at once. The user wants to unmap
(or shadow-tag) just the one time slot they clicked.

Root cause: `ignored_image_words` and `shadow_text_words`
(`GenerationConfig`, session JSON, and the matching logic in
`image_catalog.suggest_images_for_words` / `effect_placer.
_place_shadow_text_effects`) have always been flat `list[str]` word tokens.
The UI data (`image_topics`, `imageSuggestions`) was already per-occurrence
(each entry carries its own `start_ms`) — only the *action* collapsed
occurrences into one word-level toggle.

## What Changes

Rename and reshape both fields from word-level to occurrence-level. This is
a genuine shape change, not additive — renaming (rather than keeping the
old name with a new meaning) makes every caller update explicitly instead
of silently misinterpreting the new shape.

- `ignored_image_words: list[str]` → `ignored_image_occurrences: list[dict]`
  (each `{"word": str, "start_ms": int}`)
- `shadow_text_words: list[str]` → `shadow_text_occurrences: list[dict]`
  (same shape)

### Backend: storage + API (`src/review/api/v1/images.py`, `shadow_words.py`)

Both routes' request/response bodies gain `start_ms` alongside `word`:

- `POST /songs/<id>/ignored-images` body: `{"word": ..., "start_ms": ...}`
- `DELETE /songs/<id>/ignored-images/<word>/<start_ms>` (path gains a
  segment — a compound key needs both parts, and path params keep this
  RESTful rather than routing state through a body on DELETE)
- Same two changes mirrored for `/shadow-words`.

Session JSON key renamed to match (`ignored_image_occurrences`,
`shadow_text_occurrences`).

### Generator: occurrence-aware matching

- `src/generator/image_catalog.py::suggest_images_for_words` — parameter
  renamed `ignored_words` → `ignored_occurrences: list[dict] | None`;
  builds a `{(token, start_ms)}` tuple set instead of a token-only set;
  filter becomes `(token, word.get("start_ms")) in ignored_pairs`.
- `src/generator/effect_placer.py::_place_shadow_text_effects` — parameter
  renamed `shadow_words` → `shadow_occurrences: list[dict] | None`; same
  tuple-set change; the `spans` filter checks `(text_token, word_start) in
  shadow_occurrence_set` instead of text-only membership.
- `src/generator/models.py::GenerationConfig` — fields renamed as above.
- `src/generator/plan.py` — both call sites updated to the renamed
  params/fields (mechanical, same call shape).
- `src/evaluation/generator_runner.py` (`run()` and `_run_pipeline()`) and
  `src/review/api/v1/export.py` — parameter/kwarg renames, mechanical.

### Frontend (`Pictures.tsx`)

- `ignored`/`shadowWords` state: `Set<string>` keyed by a composite
  `` `${word.toLowerCase()}|${start_ms}` `` instead of plain word — every
  `.has(...)`/`.add(...)` call across the file updated to build/check that
  composite key (there are 6 call sites: the "Already matched",
  "Suggested topics", and "uploaded" sections each render a Shadow button;
  "Already matched" also renders Unmap).
- `ignoreMatch(word)` → `ignoreMatch(word, start_ms)`; `toggleShadowWord(word)`
  → `toggleShadowWord(word, start_ms)`; both now send `start_ms` in the
  POST body and in the DELETE URL.
- `activeSuggestions` filter (which suggestions currently show as "Already
  matched" vs. moved back to "Suggested topics") keys off the composite
  identifier, not `s.word.toLowerCase()` alone — so unmapping one
  occurrence only moves *that* row back, leaving the other 8 "DREAM" rows
  mapped.
- GET responses for `/ignored-images` and `/shadow-words` now return
  `[{"word", "start_ms"}, ...]` instead of `["word", ...]` — the two
  `useEffect` hooks that populate `ignored`/`shadowWords` on mount build
  the composite key from each object instead of using the string directly.

## What does NOT change

- `lyricWordCandidates`'s word-level dedup (used for the "Suggested
  topics" empty-state list before any match exists) — unrelated to
  Unmap/Shadow, stays as-is.
- "Choose image" / upload-per-word behavior — the user didn't ask for this
  to become per-occurrence, and uploading a NEW image for one occurrence
  of a word while the word's library tag stays shared for the whole
  library is a materially different, unrequested feature. Out of scope.
- Any change to how `image_topics`/`imageSuggestions` are computed — they
  were already per-occurrence; only the action layer changes.

## Alternatives considered

- **Keep the old field names, just change their contents' shape** —
  rejected: a `list[str]` silently becoming a `list[dict]` under the same
  name is exactly the kind of change that produces confusing runtime
  errors far from the actual mistake (e.g. `"word" in old_ignored_words`
  silently becomes always-False instead of erroring). Renaming forces
  every caller to be touched deliberately.
- **Migrate old word-level ignore lists into per-occurrence entries at
  load time** (expand every existing ignored word into one entry per
  occurrence found in that song's `vocal_words`) — considered, but this
  session's actual old data was itself a symptom of the bug being fixed
  (the user never wanted "ignore everywhere," they wanted "ignore this
  once" and the tool only offered the wrong granularity) — auto-expanding
  it forward would just reproduce today's incorrect scope one more time.
  Simpler and more honest: ship the rename, per-song ignore/shadow state
  resets once, the user re-picks with the new (correct) granularity going
  forward. Flagged explicitly rather than silently decided.
- **Add a NEW parallel per-occurrence field, keep the old word-level one
  for backward compat** — rejected: two overlapping mechanisms doing
  almost the same thing is exactly the kind of complexity CLAUDE.md's
  engineering principles warn against ("don't over-engineer... no
  backwards-compatibility shims when you can just change the code").

## Files touched

| File | Change |
|---|---|
| `src/generator/models.py` | `GenerationConfig.ignored_image_words`→`ignored_image_occurrences`, `.shadow_text_words`→`.shadow_text_occurrences` |
| `src/generator/image_catalog.py` | `suggest_images_for_words`'s `ignored_words`→`ignored_occurrences`, tuple-set matching |
| `src/generator/effect_placer.py` | `_place_shadow_text_effects`'s `shadow_words`→`shadow_occurrences`, tuple-set matching |
| `src/generator/plan.py` | both call sites renamed |
| `src/evaluation/generator_runner.py` | `run()`/`_run_pipeline()` param renames |
| `src/review/api/v1/export.py` | kwarg renames |
| `src/review/api/v1/images.py` | POST body/DELETE route gain `start_ms`; session key renamed |
| `src/review/api/v1/shadow_words.py` | same as images.py |
| `src/review/frontend/src/screens/Pictures.tsx` | composite-key state, updated handlers, updated GET parsing |
| `tests/unit/test_image_catalog.py` (or equivalent) | updated for renamed param + occurrence-scoped filtering |
| `tests/unit/test_generator/test_shadow_text*.py` | same |
| `tests/review/test_api_images.py`, `test_api_shadow_words.py` | updated for `start_ms` in request/response |
| `src/review/frontend/tests/screens/Pictures.test.tsx` | new/updated: unmapping one occurrence leaves siblings mapped |

## Regression surface

- **`GenerationConfig`** — two fields renamed (not added). Grep confirms
  the only writers are `export.py`/`generator_runner.py`'s kwarg passing
  and the only reader is `plan.py`'s two call sites — all in the table
  above, all updated together. No test constructs `GenerationConfig` with
  the old field names outside files already listed for update (verified
  via grep in the investigation above).
- **`suggest_images_for_words`** — also called from the analyze phase (per
  its own docstring: "used both by the analyze phase... and by
  `_place_picture_effects`") — grep for other callers beyond `plan.py`
  before implementing, to make sure the analyze-phase call site (likely
  computing `image_topics` for the Pictures screen's *display*, which
  should NOT be occurrence-filtered — it needs to show ALL occurrences so
  the user has something to unmap in the first place) is either unaffected
  or intentionally passes `None`/no ignore list.
- **`_place_shadow_text_effects`** — private, single call site
  (`plan.py`), already covered above.

## Validation

1. Unit: updated tests per the files-touched table; full
   `pytest tests/unit/test_generator tests/review -v`.
2. Frontend: new Pictures.tsx test — unmap one "DREAM" occurrence, assert
   the other 8 rows are unaffected (still show "Already matched", still
   render Unmap/Shadow) and the unmapped one moves to "Suggested topics".
3. Manual: reproduce the exact screenshot scenario against a real song,
   confirm one Unmap only removes that timestamp's mapping.
