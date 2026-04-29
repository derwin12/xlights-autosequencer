## Why

A user-driven sanity check on Cher's *DJ Play a Christmas Song* surfaced
that section boundaries were systematically misaligned with the actual
sung lyrics, producing visibly wrong analyses that propagated all the
way to the React review UI:

- **Chorus 2** ran 105.58 → 116.83 s (11.25 s) — cut mid-line at "And
  that's…" while the singer continued "the only thing I want this year"
  through 120.20 s. The trailing 3.82 s was relabeled `post_chorus`.
- **The "Bridge"** at 120.65 → 150.13 s contained no bridge content
  whatsoever — it was a verbatim chorus repeat, lyrics
  identical to chorus 1. Genius's lyric labels were correct; the *audio
  segmenter's boundary at 120.65 s* and the story builder's
  label-mapping never reconciled the two.
- **Chorus 3** at 150.13 → 174.16 s started 13.6 s before the singer
  re-entered. The actual first sung word ("You") lands at 163.75 s; the
  preceding 13.37 s is a pure instrumental break.

These are not Cher-specific. The boundary-derivation code in
`src/analyzer/genius_segments.py:640-704` sets each section's *start* to
its first matched WhisperX word and its *end* to the *next section's
first matched word* — there is no concept of "did this section's lyrics
actually finish" or "is the singer audibly singing in the section's
prefix." So any time:

1. The next labeled section is short (<6 s) and its lyrics are a
   continuation of the prior section, the prior section gets cut off
   mid-thought (the chorus-2 case).
2. Genius labels a section "Bridge" when the audio is a chorus repeat
   (extremely common in pop songwriting: a "bridge" that quotes the
   chorus before going elsewhere), the analyzer keeps the wrong label
   and a wrong agreement_score=1 follows it through the pipeline.
3. The labeled section starts before the singer audibly enters (an
   instrumental ramp-up snapped to a bar line by the spectral
   segmenter), the section is reported as longer than it actually is
   and themes assigned to its leading instrumental portion render
   confusingly.

A 16-song corpus check confirmed all three patterns recur (Cher,
Crazy Train, Ghostbusters, Down with the Sickness, Hoist the Colours,
Holiday Road's chorus, plus several others where the existing analyzer
output was already correct and the fixes were correctly inert).

The fix is to add three lyric-anchored refinements that consume the
existing forced-alignment word marks (already produced inside the story
builder, currently used only for section-start anchoring), plus a new
free-transcription pass that gives ground truth for "is anyone audibly
singing here." The refinements run after the existing boundary derivation
so they refine, not replace, the current behavior.

A second motivation surfaced during the same investigation: tool
failures (WhisperX not running, Genius lookup mismatched on
Holiday Road by guessing the wrong artist) are silently absorbed by the
pipeline and produce degraded output with no UI signal. This proposal
includes a small piece of that surfacing — explicit warnings whenever
the new boundary-refinement code skips for known reasons — but the
broader silent-failure audit is out of scope here and tracked separately.

## What Changes

- **Add `src/analyzer/free_transcription.py`** — a thin wrapper around the
  WhisperX free-transcription pass already invoked inside `_run_genius_alignment`
  (`src/analyzer/genius_segments.py:526`). Extract the transcription
  step into a standalone, reusable function so it is callable both as
  Step 1 of Genius alignment and as an independent ground-truth signal
  for boundary refinement. Returns a list of `WordMark` instances — same
  shape as the existing forced-alignment output. No behavior change to
  the genius alignment path; only refactored extraction.
- **Add `src/story/boundary_refinement.py`** — three pure functions
  applied after the existing boundary-derivation code in
  `genius_segments.py:_derive_section_boundaries_from_words` (or a sibling
  call site) finishes:
  - `merge_short_post_chorus_tail(sections, forced_words)` — when a
    `post_chorus` is <6 s, has `agreement_score ≤ 1`, and its first
    word is within 1.5 s of the previous section's last word, the
    `post_chorus` is merged into the previous section.
  - `relabel_or_split_bridge(sections, free_words, chorus_body)` —
    when a `bridge` section's free-transcribed content opens with the
    chorus's first-line distinctive hook (≥ N-1 of N hook words appear
    in order within a 12-word window), either relabel the whole
    bridge as Chorus, split it into Chorus prefix + Bridge tail, or
    leave it alone — three branches based on hook presence in the
    halves of the bridge around its largest internal vocal gap.
  - `split_pre_vocal_instrumental(sections, free_words)` — when a
    vocal section's first free-transcribed word is ≥ 5 s after the
    section start, split off the silent prefix as an `instrumental`
    section. Skips already-instrumental sections (kind or label).
    Skips when the resulting vocal portion would be < 3 s (signals a
    whole-section mislabel, not a prefix issue — out of scope here).
- **Wire the three functions into `src/story/builder.py`** — add a
  single call to a new `refine_section_boundaries(sections, hierarchy,
  forced_words, free_words)` function that runs the three refinements
  in order: 1 → 2 → 3 (Fix 2's split can create new sections that
  Fix 3 then operates on, observed on Crazy Train).
- **Surface refinement events in `_story.json`** — each refined section
  carries a `boundary_refinements: [...]` list of one-line strings
  describing what changed and why. Read by the analyze-step API and
  shown in a tooltip on the Analyze screen so reviewers can see *why*
  a section moved without inspecting JSON.
- **ID3 confirmation in the Web upload flow + title-only fallback in
  non-interactive paths.** Holiday Road's lookup failed because of an
  artist mismatch between the library entry and what Genius indexed.
  ID3 tags on the user's MP3s are not always correct; the existing
  Web upload flow already has prompt-then-retry infrastructure
  (`job.prompt_genius` / `job.wait_for_genius_response` —
  `src/review/server.py:230-234`) but it only fires *after* Genius
  has failed. This change extends the Web flow to:
  1. Read existing ID3 tags via `mutagen` (already a dependency).
  2. Prompt the user to confirm or correct title + artist *before*
     attempting Genius. Three responses: Confirm (use as-is), Correct
     (provide replacement), Skip (don't try Genius this run).
  3. On Correct, optionally write the corrected ID3 tags back to the
     MP3 (atomic write, with a sibling `.bak` written first), so the
     library record stays in sync with the file and future runs
     don't repeat the mismatch.
  Non-interactive callers — CLI batch (`xlight-analyze analyze`),
  acceptance gate, library refresh — cannot prompt, so when
  `g.search_song(title, artist)` returns `None` they SHALL retry
  with `search_song(title)` and log the fallback at INFO. The
  fallback's match metadata gains a `fallback_used: bool` field so
  downstream consumers (and the UI) can see the lookup wasn't
  exact. This keeps non-interactive runs working without producing
  silent quality regressions.
- **Capability surfacing for refinement availability** — the three
  refinements are guarded by capability requirements (WhisperX present,
  vocals stem available, Genius match optional for Fix 1/3 / required
  for Fix 2). When unavailable, a per-fix warning is appended to
  `HierarchyResult.warnings` so the UI can render "boundary refinement
  N skipped because X." Mirrors the pattern PR #84 used for SSM.

## Impact

- **Affected specs:** `story-section-boundaries` (new capability)
- **Affected code:**
  - `src/analyzer/free_transcription.py` (new)
  - `src/story/boundary_refinement.py` (new)
  - `src/analyzer/genius_segments.py` — refactor only: extract Step 1
    transcribe into the new module; existing genius-align flow keeps
    same observable behavior
  - `src/story/builder.py` — add single call to
    `refine_section_boundaries(...)` after existing boundary derivation
  - `src/review/api/v1/analysis.py` — propagate
    `boundary_refinements` and any new fields on `Section`
  - `src/review/frontend/src/screens/Analyze.tsx` (or sibling) — render
    refinement notes (tooltip / icon) on refined sections
  - `src/review/server.py` — extend the existing prompt-then-retry
    flow (`prompt_genius` / `wait_for_genius_response`) to include
    a confirm-or-correct step that fires *before* Genius lookup, plus
    a write-back-to-ID3 hook gated on user opt-in
  - Frontend Web upload flow — new modal / panel for ID3 confirmation
    (extends the existing Genius retry UI; not a brand-new screen)
  - `src/analyzer/genius_segments.py` — title-only retry for
    non-interactive callers when `search_song(title, artist)` returns None
- **Affected tests:**
  - `tests/unit/test_boundary_refinement.py` (new)
  - `tests/unit/test_free_transcription.py` (new)
  - `tests/integration/test_story_builder_refinement.py` (new)
  - `tests/golden/analyzer/baseline.json` — re-snapshot after the
    refinement step lands; fields that participate are deterministic
- **Backward compatibility:** `_story.json` schema gains an optional
  `boundary_refinements: list[str]` field on each section. Legacy
  files without the field are read with default `[]` (no refinement
  notes). No breaking change to API consumers.
- **Performance:** adds one WhisperX free-transcription pass per song
  in the story-builder path. WhisperX is already loaded in that path
  (Step 1 of `_run_genius_alignment` already runs the same call). The
  refactor reuses the result rather than running it twice. Net cost:
  zero additional WhisperX invocations on the success path; the
  free-transcription is now also available on the no-Genius-match
  path where it currently isn't computed (small added cost there;
  budget +30 s on a 4-minute song, well within existing analyzer
  runtime).
