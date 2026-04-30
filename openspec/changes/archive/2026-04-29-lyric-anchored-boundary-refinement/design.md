## Context

The story builder's boundary-derivation algorithm in
`src/analyzer/genius_segments.py:640-704` runs after WhisperX has
forced-aligned the full song's lyrics to audio:

```python
# pseudocode of current behavior
for section in genius_sections:
    first_word = find_word_starting_with(section.first_word_prefix, cursor)
    section.start_ms = first_word.start_ms
    cursor = position_after(first_word)
# Then:
for i, sec in enumerate(sections):
    sec.end_ms = sections[i+1].start_ms if i+1 < len(sections) else duration_ms
```

Two ground-truth signals are used inside that file but not consumed by
the boundary-derivation pass:

1. **Step 1 free transcription** at `genius_segments.py:526` — runs
   `whisperx.transcribe(audio)` *without* lyrics input to discover
   "vocal regions" (continuous spans of audible singing). The result is
   used only for the local task of filtering forced-alignment words
   inside instrumental sections. The transcribed words themselves —
   which are the gold-standard answer to "is anyone singing here" — are
   discarded after that filter.

2. **`HierarchyResult.energy_curves["vocals"]`** — the per-stem energy
   curve from the BBC Vamp plugin, computed at fps=47 over the demucs
   vocals stem. Available on every analyzed song. Not consulted by the
   story builder.

The four-song deep dive plus 16-song corpus check
(`/tmp/corpus_run_v4b.out` artefacts, summarized in this conversation's
exchange) demonstrated:

- Free transcription reliably reports zero words during instrumental
  breaks, even when the vocals stem has 30-50 % residual energy from
  instrument bleed, ad-libs, or breath.
- Forced alignment will spread known lyrics across silence to satisfy
  its constraint that every input word must be placed somewhere — its
  per-word `score` field reaches 0.5-0.7 even for ghost-placed words
  because wav2vec2 fits phoneme transitions to the audio waveform
  shape, not to actual lexical content. Score is not a usable
  "is this real" signal.
- Vocals-stem energy alone is not sufficient: dynamically quiet but
  continuous singing (Down with the Sickness pre-choruses, Holiday
  Road's second chorus) sustains energy below the natural threshold
  while the singer is clearly performing. Free transcription
  correctly captures these as continuous vocals.

Three concrete boundary errors recur across songs:

| Pattern | Example | Required signal |
|---|---|---|
| Short post_chorus that is actually the prior chorus's last line | Cher post_chorus 116.83→120.65 s, 3.82 s, agreement=1 | forced-alignment word continuity across boundary |
| Bridge labeled by Genius but content is a chorus repeat | Cher bridge 120.65→150.13 s, agreement=1 (Genius "Bridge"); Crazy Train bridge 140.31→176.89 s (chorus prefix + verse-like content) | free-transcribed words match chorus first-line hook |
| Vocal section whose start precedes the singer's actual entry by a long instrumental ramp | Cher chorus 3 150.13→174.16 s, vocals enter 163.75 s; Hoist the Colours verse 43.65→70.83 s, vocals enter 52.26 s | free-transcribed first word vs. section start |

The required code changes touch shared modules (`src/analyzer/`,
`src/story/`) so this design pre-clears the design-first gate per
`CLAUDE.md`. The `src/review/` touch (analyze-step API, frontend) is
small and additive.

## Goals / Non-Goals

**Goals:**

- Eliminate the three concrete boundary errors observed in Cher
  without introducing false positives. The 16-song corpus check
  already shipped 0 FPs across 8 fires after iteration; the spec
  preserves those guards.
- Use existing in-pipeline data (forced-alignment words +
  vocals-energy curve) plus one new signal (free transcription as a
  reusable analyzer step). No new dependencies.
- Make refinement decisions explainable — every boundary change a
  refinement makes is recorded as a one-line note on the section,
  visible to the reviewer. No silent "we moved the boundary 5
  seconds" surprises.
- Generalize: 4 songs validated up close, 12 more validated by
  corpus run with no fires (correct quiet behavior on songs the
  analyzer already gets right).

**Non-Goals:**

- Re-segmenting the audio. Sections are still seeded by Genius (where
  available) or the heuristic role classifier; refinements adjust
  boundaries, never invent or merge across distant sections.
- SSM-driven role inference. Refinement consults the SSM-supplied
  `chorus_ssm_supported` flag (already shipped in PR #84) but does
  not promote roles based on SSM. A Verse cannot become a Chorus
  through this change.
- Solving the broader silent-failure surface. The audit identified 7
  swallow points across `capabilities.py`, `orchestrator.py`,
  `builder.py`, and `analysis.py`. This change adds explicit
  refinement-skip warnings (one specific case) but the larger
  hardening — surfacing capability false-states with reasons,
  cache-vs-fresh badge in UI, full warnings panel — is a separate
  proposal.
- Auto-fixing songs with no Genius match. Fix 3 already works without
  Genius (it uses free transcription only); Fixes 1 and 2 require
  Genius and remain inert when absent.
- Refining anything outside the WhisperX-pipeline path. Songs with no
  vocals stem, songs where WhisperX fails, songs longer than the
  WhisperX runtime budget — all fall back to the existing,
  unrefined behavior.

## Decisions

### D1. Free transcription as the "is anyone singing" ground truth

**Decision:** Free-transcription word marks (no lyrics input) are the
authoritative signal for whether a section's prefix is silent or
continues sung content. Forced-alignment words and vocals-energy
curves are useful but secondary.

**Why:** Iterative testing on the 4-song probe ruled out alternatives:

- *Forced-alignment confidence score* — fails because WhisperX scores
  phoneme-fit, not lexical presence. Ghost placements in silence
  reach 0.5-0.7 confidence.
- *Vocals-stem energy threshold* — fails on dynamic vocals. Down with
  the Sickness pre-chorus has continuous singing at energy 28-65; my
  early threshold of 50 sustained classified it as silence.
- *Vocals-energy + word density combo* — too brittle to tune.

Free transcription's failure mode is undertranscription (rare
mishears, e.g. "DJ play a Christmas song" → "You can clap Christmas
song" on Cher's chorus 3). For the boundary-refinement task, this
mode is benign: a missing word means we'd skip an intervention we
might have made; we don't make a wrong intervention.

### D2. Refinements run after existing boundary derivation, not in place of it

**Decision:** The current boundary derivation in `genius_segments.py`
stays unchanged. Refinements operate on its output. Each refinement
is a pure function `sections, signals → sections'`.

**Why:** This is the smallest blast-radius approach. The existing
boundary-derivation algorithm is correct on the majority of sections
(verified by the 16-song corpus's 12 zero-fire songs); replacing it
risks regressing those. Post-hoc refinement scopes the change to
exactly the patterns we identified.

The trade-off is that we can't fix everything (e.g., a section
mid-mislabeled by the segmenter that the refinements can't reach
without re-segmenting). But (a) the 16-song corpus shows the three
patterns we *can* fix capture the visible errors, and (b) deeper
fixes would require re-running segmentino + qm_segments with
different parameters, which is a separate spec.

### D3. Targeted preconditions over universal heuristics

**Decision:** Each refinement fires only under narrow, named
preconditions — not "whenever you see something suspicious."

- Fix 1 (merge short post_chorus): kind == post_chorus, dur < 6 s,
  agreement_score ≤ 1, gap-to-prior-last-word ≤ 1.5 s. Four
  conditions, all required.
- Fix 2 (relabel/split bridge): kind == bridge, free-transcribed
  content opens with chorus first-line distinctive hook (N-1 of N
  match in order). Hook is computed from the chorus's first line
  only, not the whole chorus body, so a single coincidental word
  cannot trigger.
- Fix 3 (split pre-vocal instrumental): kind ∈ {verse, chorus,
  pre_chorus, post_chorus, bridge}; label does not contain
  "instrumental" or "break"; gap from section start to first
  free-transcribed word ≥ 5 s; remaining vocal portion ≥ 3 s.

**Why:** Universal "sounds quieter than expected → must be silence"
heuristics produced false positives during iteration (Down with the
Sickness, Holiday Road's continuous-but-quiet chorus). Each
precondition above was added because the corpus check exposed a
specific false-positive class. They are stable in v7+ across all 16
songs.

### D4. Fix 2's hook-match threshold: N-1 of N, in order, within window

**Decision:** A bridge's free-transcribed words "open with the chorus
hook" iff at least `max(2, len(targets)-1)` of the chorus first line's
distinctive words appear in order within a 12-word window of the
bridge content (or its prefix / suffix around the largest internal
vocal gap).

**Why:** Strict "all targets must match in order" failed on Crazy
Train because forced/free transcription dropped "I'm" (contraction at
chorus start). Loose "any target appears anywhere" produced the
Believe false positive (single word "believe" overlap with bridge
that has different lyrical content).

The N-1 threshold tolerates one ASR drop per hook (most common
failure mode is contractions and weak short words) but a single-word
match cannot meet the minimum of 2.

The 12-word window is empirically derived: chorus first lines run
3-7 distinctive words long, allowing some filler between them
without requiring contiguity.

### D5. Free transcription extraction is a refactor, not a re-implementation

**Decision:** `src/analyzer/free_transcription.py` lifts the existing
Step 1 transcription call from `genius_segments.py:526-538` verbatim,
exposing it as `transcribe_free(audio_path: str, *, language="en")
-> list[WordMark]`. The existing call site in `genius_segments.py`
delegates to the new module and uses the result as before. No
parameters change.

**Why:** Avoid duplicating the WhisperX setup (model load, language
specification, alignment-pass invocation). The function is already
working in production; the refactor just gives the rest of the
analyzer access to it. Lower regression surface than writing a
parallel implementation.

### D6. Refinement notes are persisted in `_story.json`

**Decision:** Each section dict gains an optional
`boundary_refinements: list[str]` field. Each entry is a one-line
human-readable note: e.g.,
`"merged 3.82 s post_chorus 'Post Chorus' as chorus tail (gap=100 ms, +8 words)"`.

The analyze-step API copies the field; the Analyze screen renders a
small icon next to the section label when the list is non-empty,
with the notes shown on hover/click.

**Why:** The user's silent-failure complaint that started this work
explicitly named opaque boundary changes ("we moved the boundary 5
seconds and you have no idea why"). Notes make every refinement
auditable. Costs a few hundred bytes per song in `_story.json`.

The alternative — log-only — was rejected: log files don't reach the
reviewer, and "if you want to know why a boundary moved, go run the
CLI again with `--debug`" is exactly the kind of friction this work
is trying to eliminate.

### D7. Ordering is fixed: 1 → 2 → 3

**Decision:** Refinements run in fixed order:
1. `merge_short_post_chorus_tail` — operates on the original
   sections; can change the count by merging.
2. `relabel_or_split_bridge` — operates on Fix 1's output; can split
   one section into two.
3. `split_pre_vocal_instrumental` — operates on Fix 2's output;
   needed because Fix 2's split (Crazy Train) creates a Bridge tail
   that itself has a pre-vocal gap.

**Why:** Reordering creates issues. If 3 ran before 2: the
Crazy Train bridge wouldn't yet be split, so 3 would split off the
guitar solo at the start of the whole 36 s bridge — leaving the
chorus prefix inside an Instrumental section. If 1 ran after 2: a
post_chorus that gets merged into a chorus prefix that 2 produced
would either merge into the wrong place or fail the tail-gap check.

The order is documented in `boundary_refinement.refine(...)` and
asserted by a unit test that runs each pair out of order on a
synthetic input and asserts the output diverges.

## Risks / Trade-offs

### Risk 1: A song with a real bridge that quotes the chorus's first line gets mislabeled

The Fix 2 hook threshold (N-1 in order) makes single-word coincidence
impossible but cannot distinguish:
- A bridge whose first 4 lines ARE a chorus repeat (Cher,
  Ghostbusters — true positives, want to fire) from
- A bridge whose first 4 lines QUOTE the chorus opening before going
  elsewhere (e.g., "♫ DJ play a Christmas song… ♫ but tonight is
  different…")

The 16-song corpus had no clear example of the latter. The literature
on pop song structure suggests it is rare but possible. If it occurs,
Fix 2 will incorrectly relabel the whole bridge or split too aggressively.

**Mitigation:** Refinement notes (D6) make this case visible to the
reviewer. The Analyze screen's existing manual section-edit affordance
lets a human override.

**Detection:** if a future corpus run shows Fix 2 relabeling a bridge
where the *Genius bridge body itself* contains substantial non-chorus
lyrics, that's the failure mode. Add a guard: skip Fix 2 when
`genius_bridge_body` does NOT itself open with the chorus first line.
(Cher's Genius bridge does. Crazy Train's Genius bridge ("DJ, play a
Christmas song / I wanna be dancing, dancing all night long") does
too. A song where Genius's bridge text differs from the chorus text
should not fire — and current Fix 2 already wouldn't fire on it
because the *audio* would not match the hook either, since Genius
bridge text and audio agree.) Confirm with corpus.

### Risk 2: Free transcription latency on long songs blocks story building

Free transcription on a 5-minute song takes ~30-60 s on CPU. The
analyzer pipeline already runs forced alignment on the same audio
inside `_run_genius_alignment`, so adding free transcription as a
parallel ground-truth signal doubles WhisperX time on that song.

**Mitigation:** D5's refactor reuses the Step 1 transcription that
genius_segments.py already runs — net cost on songs with Genius
match is **zero additional invocations**. The cost surfaces only on
songs without Genius match where the story builder currently skips
WhisperX; those songs gain Fix 3 in exchange.

Budget: orchestrator already has a 600 s timeout per
`_run_genius_alignment` call. The free-transcription refactor stays
within that.

### Risk 3: `_story.json` schema bump breaks downstream consumers

The new `boundary_refinements` field is optional and additive. But
schema-bump pain is real (pattern_story_schema_migration memory:
"on-disk `_story.json` files don't auto-migrate; surface a 'regenerate'
path").

**Mitigation:** Read sites default to `[]`. Bump
`_story.json.schema_version` from 1.0.0 to 1.1.0 (minor — backward
compatible) and document the field in
`docs/story-schema.md` (or wherever the schema is documented; verify
location during implementation).

### Risk 4: Refinement diff in baselines

Running refinements changes section boundaries on at least 6 of 16
corpus songs. The acceptance gate's analyzer baseline + section
fidelity baseline must be re-snapshotted.

**Mitigation:** Tasks include explicit re-snapshot steps. The
`agreement_score` baseline is unaffected (refinements don't alter
agreement scores; they only adjust boundaries and labels of sections
the agreement_score was already computed for).

### Trade-off: Spec vs. corpus rerun

The current 4-song deep dive + 16-song corpus run produced 8 fires,
0 FPs, 0 missed regressions on songs the analyzer already got right.
This is strong but not exhaustive — songs not in the local library
(future imports) might exhibit Fix 2 false positives of the form
described in Risk 1. The decision to spec now (rather than wait for
a 50-song corpus) is justified by:

- The spec's preconditions are specific enough that a Risk 1 case
  would require the song's Genius bridge to also open with chorus
  text (rare), AND the audio to match (which would mean the bridge
  IS chorus-content, which is the case Fix 2 should fire on).
- Refinement notes (D6) make every fire reviewable.
- The refinements are reversible: `boundary_refinements` field
  records what was done, so a "revert" path is straightforward to
  add later if needed.

## Migration Plan

1. Land `src/analyzer/free_transcription.py` first (refactor only).
   Verify existing `_run_genius_alignment` still produces identical
   output by running the analyzer on Cher's audio before / after and
   diffing the resulting `_story.json` (should be byte-identical
   modulo the new `boundary_refinements` field — 0 entries because
   refinement isn't wired yet).

2. Land `src/story/boundary_refinement.py` with all three functions
   plus unit tests. No call site yet — the module is dead code in
   this commit, with full test coverage.

3. Wire `refine_section_boundaries(...)` into `src/story/builder.py`
   behind a feature flag `XLIGHT_REFINE_BOUNDARIES=1` defaulting to
   off. Run the corpus through with the flag on and the flag off;
   diff the section-by-section output to confirm only the expected
   8 fires across the 16 songs.

4. Flip the default to on. Re-snapshot baselines.

5. Land the analyze-step API + frontend pieces (
   `boundary_refinements` propagation and rendering).

The feature flag in step 3 is unusual for this codebase (CLAUDE.md
discourages flags) but justified here by the high-blast-radius nature
of changing section boundaries — the flag exists only for the
duration of step 3's verification and is removed in step 4. A
`# remove with PR XXX` comment on the flag commits its short life.

### D8. ID3 confirmation prompt before Genius lookup (Web flow); title-only fallback for non-interactive callers

**Decision:** The Web upload flow SHALL surface the title and artist
read from the MP3's ID3 tags to the user *before* attempting Genius
lookup, with three responses available — Confirm, Correct, Skip.
On Correct, the user's input replaces the ID3 values for the rest
of this analysis run; the user is also offered a separate opt-in
to write the corrected tags back to the MP3 file (atomic write with
sibling `.bak`). The Genius lookup proceeds with whatever the user
confirmed or corrected.

Non-interactive callers (CLI `xlight-analyze analyze`, acceptance
gate, batch refresh) cannot prompt. They SHALL retry
`g.search_song(title, artist)` with `g.search_song(title)` when the
first call returns `None`, log the fallback at INFO, and tag the
match metadata with `fallback_used = True`.

**Why:** The Holiday Road failure was a real instance of the
systemic silent-failure complaint that started this work — the user
saw "no Genius match" but didn't know whether the song was
genuinely missing from Genius or whether the title/artist we sent
was wrong. Prompting the user *before* Genius runs:

- Surfaces the source of truth (the user) at the right moment, not
  after a failure when context is lost.
- Lets the user correct genuinely wrong ID3 tags (cover artist,
  remix attribution, typo) once, with the fix persisted on disk.
- Sidesteps the false-match risk of permanent silent title-only
  retry: Cher's "Believe" matched against "Believe" by some other
  artist could attach wrong lyrics; the prompt forces the user to
  acknowledge or correct.

The non-interactive title-only fallback exists so the acceptance
gate and CLI batch keep working without prompts. The fallback's
risk (wrong-version match) is mitigated by `fallback_used` being
visible in the match metadata and surfaceable in the UI for
post-hoc review.

**Why not permanent silent fallback alone:** Risk 1 of the
permanent-fallback option (wrong-cover lyrics get attached) is
real and silent. Even with logging, the user wouldn't see the
mismatch until they noticed weird section labels mid-song. The
prompt makes the moment of decision explicit.

**Why not add a "genius bridge body must match chorus" guard
(formerly Open Q2):** Tested against the 16-song corpus. Crazy
Train would fail the guard incorrectly: Genius's bridge body for
Crazy Train (`"All aboard! / Hahaha! / Ay, ay, ay, ay, ay, ay"`)
does NOT match the chorus first line, but the *audio* at the
start of Crazy Train's bridge IS chorus content (the famous
"going off the rails" line). The guard would block a correct fire.
Adding the guard creates a known false-negative class to defend
against a hypothetical false-positive class with no corpus
evidence. Decision: don't add the guard. If the FP appears in
production, refinement notes (D6) make it visible for manual
override; we add the guard then with a real test case.

### D9. Refinement indicator rendering on the Analyze screen (formerly Open Q3)

**Decision:** Sections with `low_refined: true` SHALL render a
small icon (e.g., "↻") next to the section role label. The icon
SHALL expose a tooltip on hover/focus that lists the strings in
`boundary_refinements`. The icon's specific glyph, color, and
animation behavior are implementation detail for whoever lands the
frontend slice.

**Why:** Icon + tooltip is the minimum-disruption pattern: small
real-estate cost, glanceable signal, multi-line note content fits
naturally in a tooltip. Alternatives considered: a colored dot
(accessibility risk if color is the only signal), a text suffix
on the section role (eats horizontal space, repeats verbosely on
songs with many refinements), or a row-level border treatment
(too heavy for a per-section signal). The spec mandates "visual
marker that exposes the notes" — implementation chooses the
specific glyph and styling consistent with the existing Analyze
screen's visual language (e.g., the `low_confidence` indicator
shipped in PR #84, which uses a small marker pattern).
