## 1. Refactor: extract free transcription into a reusable module

- [ ] 1.1 Create `src/analyzer/free_transcription.py`. Move the Step 1 transcription block from `src/analyzer/genius_segments.py:521-538` into a public function `transcribe_free(audio_path: str, *, language: str = "en", device: str = "cpu") -> list[WordMark]`. Reuse the existing `WordMark` dataclass from `src/analyzer/phonemes.py` (verify the import path during implementation; the dataclass is currently defined there per `genius_segments.py:574`).
- [ ] 1.2 In `_run_genius_alignment` in `genius_segments.py`, delegate to `transcribe_free(...)` and use its return value where Step 1's `transcribed["segments"]` was previously consumed. Verify by diffing the resulting `_story.json` for a known song (Cher's *DJ Play a Christmas Song*) before and after the refactor — must be byte-identical.
- [ ] 1.3 Add `tests/unit/test_free_transcription.py` covering: (a) the function returns a list of `WordMark`, (b) audio path validation (raises on missing file), (c) language pass-through. Mock WhisperX rather than loading real audio in unit tests; integration test in §4 covers real audio.
- [ ] 1.4 Run `xlight-evaluate gate --skip-ui --quick` after the refactor and confirm exit code 0. The refactor must not change any analyzer baseline.

## 2. Implement boundary-refinement module (no call site yet)

- [ ] 2.1 Create `src/story/boundary_refinement.py` with module docstring referencing this OpenSpec change.
- [ ] 2.2 Implement `merge_short_post_chorus_tail(sections: list[dict], forced_words: list[WordMark]) -> tuple[list[dict], list[str]]`. Returns refined sections plus a list of human-readable notes describing what changed. Preconditions: prior section kind in `{verse, chorus, pre_chorus, bridge}`, next section `kind == "post_chorus"`, next duration `< 6000 ms`, next `agreement_score <= 1`, and the gap from prior section's last forced-aligned word's `end_ms` to next section's first forced-aligned word's `start_ms` is `<= 1500 ms`. When all hold, merge: extend prior's `end_ms` to the next section's last word + 250 ms tail; drop the next section.
- [ ] 2.3 Implement `_chorus_first_line_distinctives(chorus_body: str, n: int = 4) -> list[str]` returning up to N distinctive (length ≥ 3, not in stopword set) words from the chorus body's first line, in order. Stopword set per design D4 — include common contractions (`i'm`, `you're`, `we're`, `it's`, `we'll`, `i'll`) and high-frequency function words (`going`, `off`, etc., as established in `/tmp/corpus_run.py` corpus iteration).
- [ ] 2.4 Implement `_consecutive_in_order_count(targets: list[str], words: list[WordMark], window: int = 12) -> int` returning the count of targets that appear in `words` in order, each within `window` words after the previous match. Targets that aren't found are skipped (cursor stays put), so a single ASR drop doesn't abort the count.
- [ ] 2.5 Implement `_hook_matches(targets: list[str], words: list[WordMark]) -> bool` returning `True` iff `_consecutive_in_order_count(targets, words) >= max(2, len(targets) - 1)`.
- [ ] 2.6 Implement `relabel_or_split_bridge(sections: list[dict], free_words: list[WordMark], chorus_body: str | None) -> tuple[list[dict], list[str]]`. Operates on sections with `kind == "bridge"`. Compute `targets = _chorus_first_line_distinctives(chorus_body)`; require `len(targets) >= 2` (else skip). Find the bridge's free-transcribed words; identify the largest internal vocal gap `>= 3000 ms`. Then four branches per design (no-gap + hook → full relabel; gap + both halves match → full relabel; gap + prefix-only matches → split; otherwise → skipped with note).
- [ ] 2.7 Implement `split_pre_vocal_instrumental(sections: list[dict], free_words: list[WordMark]) -> tuple[list[dict], list[str]]`. Operates on sections with `kind` in the vocal kinds set (per design D3). Skip sections whose label contains `"instrumental"` or `"break"` (case-insensitive). Skip sections with no free-transcribed words. Compute gap from `section.start_ms` to first transcribed word's `start_ms`; if `>= 5000 ms` AND `(section.end_ms - first_word.start_ms) >= 3000 ms`, split: insert a synthetic `instrumental` section from `section.start_ms` to `first_word.start_ms - 250 ms`; shift section's start to that boundary.
- [ ] 2.8 Implement `refine_section_boundaries(sections: list[dict], hierarchy: HierarchyResult, forced_words: list[WordMark], free_words: list[WordMark], chorus_body: str | None) -> list[dict]`. Runs the three refinements in fixed order 1 → 2 → 3 (per design D7). Each section gains a `boundary_refinements: list[str]` field that accumulates notes from each pass; sections that no refinement touched have `boundary_refinements = []` (NOT absent — the field is always present after this function runs).
- [ ] 2.9 Add `tests/unit/test_boundary_refinement.py` with at least these cases. Each test constructs synthetic `sections + words` inputs (no audio loading); the v7-final corpus output in this conversation provides ground-truth examples to encode:
  - Fix 1: short post_chorus continuous with prior chorus → merged.
  - Fix 1: post_chorus 6+ s → not merged.
  - Fix 1: post_chorus with agreement_score=2 → not merged.
  - Fix 1: gap > 1500 ms → not merged.
  - Fix 2: bridge with hook in whole, no gap → full relabel.
  - Fix 2: bridge with hook in prefix only, gap ≥ 3 s → split.
  - Fix 2: bridge with hook in both halves around gap → full relabel.
  - Fix 2: bridge with no hook match → unchanged.
  - Fix 2: chorus first line is too short / all stopwords (`len(targets) < 2`) → unchanged.
  - Fix 3: vocal section with first word > 5 s after start → split.
  - Fix 3: vocal section with first word at start → unchanged.
  - Fix 3: vocal section labeled "Instrumental Break" → unchanged (label guard).
  - Fix 3: vocal section with first word leaving < 3 s remainder → unchanged (mislabeled-section guard).
  - Ordering: assert running 3-then-2-then-1 vs 1-then-2-then-3 produces different output on a synthetic Crazy-Train-like input.
- [ ] 2.10 Add type hints and a module-level docstring describing the v7 corpus result (16 songs, 8 fires, 0 FPs) and the three preconditions per fix. The corpus run script `/tmp/corpus_run.py` is the empirical record; do not check it into the repo, but reference the OpenSpec change ID in the module docstring.

## 3. Wire boundary refinement into the story builder

- [ ] 3.1 In `src/story/builder.py`, locate the section-construction code (around `genius_segments.py:_derive_section_boundaries_from_words` call site, plus the post-processing that builds `_story.json` section dicts). Determine where to invoke `refine_section_boundaries(...)` — must be after section dicts have `kind`, `start_ms`, `end_ms`, `agreement_score`, but before the file is written.
- [ ] 3.2 Pass `forced_words` and `free_words` through. `forced_words` is already computed inside `_run_genius_alignment`. `free_words` is what §1 extracted. Verify both reach the call site without needing new orchestrator-level plumbing; if they don't, surface them through the existing `phoneme_result` or as a sibling return value from `genius_segments`.
- [ ] 3.3 Add a feature flag `XLIGHT_REFINE_BOUNDARIES` per design migration step 3. Default off. When off, `refine_section_boundaries` is not called and `boundary_refinements` field is not populated.
- [ ] 3.4 With the flag ON, run the analyzer on the 16 library songs and capture before/after `_story.json` files. Compare to the corpus result already validated in this conversation; expected fires:
  - Cher: Fix 1 + Fix 2 (full relabel) + Fix 3.
  - Crazy Train: Fix 2 (split) + Fix 3.
  - Ghostbusters: Fix 2 (full relabel).
  - Down with the Sickness: Fix 3.
  - Hoist the Colours: Fix 3.
  - 11 others: zero fires.
  Any deviation from this list aborts the rollout — investigate before flipping the default.
- [ ] 3.5 Flip the flag default to ON. Document the flag's removal in a comment with the PR number that lands this change; remove the flag in step 3.7 below.
- [ ] 3.6 Re-snapshot `tests/golden/analyzer/baseline.json` and `tests/golden/section_fidelity/baseline.json`. Run `xlight-evaluate gate --skip-ui` three times and confirm baselines are stable (per `pattern_per_fixture_snapshot` memory: never `--baseline` the whole corpus in one process).
- [ ] 3.7 Remove `XLIGHT_REFINE_BOUNDARIES` flag. The `# remove with PR XXX` comment serves as the marker; delete the flag dispatch block.

## 4. `_story.json` schema + integration tests

- [ ] 4.1 Bump `_story.json.schema_version` from `1.0.0` to `1.1.0` and document `boundary_refinements: list[str]` (optional; default `[]`) in the schema doc (locate the doc during implementation; if absent create `docs/story-schema.md`). Per design D6 this is a backward-compatible additive change.
- [ ] 4.2 In any code that reads `_story.json` (find via grep: `read_story`, `load_story`, paths in `src/story/`, `src/review/api/v1/`, `src/cli/library.py`), add `sec.get("boundary_refinements", [])` defaulting to `[]`. Per `pattern_story_schema_migration` memory: catch missing fields gracefully; do not require manual file regeneration.
- [ ] 4.3 Add `tests/integration/test_story_builder_refinement.py`. Use the smallest tests fixture audio that exercises one of the refinements; if no fixture suffices, add a tiny synthetic mp3 to `tests/fixtures/`. Assert that running the full story builder produces the expected refinement note on the expected section.

## 5. Surface `boundary_refinements` to the API and frontend

- [ ] 5.1 In `src/review/api/v1/analysis.py` (around the section payload construction at line 320 — verify exact line during implementation), copy `boundary_refinements` from the story-source section dict to the API payload. Default to `[]` for legacy stories. Add `low_refined: bool` derived as `len(boundary_refinements) > 0` for convenient frontend rendering.
- [ ] 5.2 Update the frontend `Section` interface in `src/review/frontend/src/screens/Analyze.tsx` (locate at line 39 region per existing convention from PR #84): add `boundary_refinements: string[]` and `low_refined: boolean`.
- [ ] 5.3 Render a refinement indicator on the section row when `low_refined` is true. Visual treatment per design Open Question 3: small "↻" icon, tooltip lists the notes from `boundary_refinements`. Keep accessible (color is not the only signal).
- [ ] 5.4 Add a Playwright e2e test (or extend an existing one in `src/review/frontend/tests/`) asserting that a section with `boundary_refinements` non-empty renders the indicator, and a section with empty `boundary_refinements` does not.
- [ ] 5.5 Audit any UI snapshot tests for whole-payload equality and update to assert against a subset (per the project test-isolation conventions: re-exported symbol patches, module-state resets, etc., from `pattern_per_fixture_snapshot` and CLAUDE.md's Test Isolation Conventions).

## 6. Genius lookup metadata reliability

Two paths, per design D8: interactive Web flow gets a confirm-or-correct prompt
*before* attempting Genius (the preventive fix); non-interactive callers get a
title-only fallback after a failed `(title, artist)` search (the safety net).

### 6a. Web flow: ID3 confirmation prompt before Genius lookup

- [ ] 6a.1 In `src/review/server.py`, locate the existing `prompt_genius` / `wait_for_genius_response` machinery (around `src/review/server.py:230-234`) and add a sibling `prompt_id3_confirm` that fires on every Web upload *before* the analyzer kicks off Genius. The job state machine gains an "awaiting_id3_confirm" phase between upload-finished and analyzer-start.
- [ ] 6a.2 Read existing ID3 tags from the uploaded MP3 via `mutagen` (already a dependency — confirm via `python -c "import mutagen"`). Read at minimum `TIT2` (title) and `TPE1` (artist); fall back to `EasyID3` view if standard ID3 frames are missing. If the file has no tags at all, fields are empty strings and the UI prompts the user to fill them in (same UI affordance as Correct).
- [ ] 6a.3 Surface the confirmation request to the frontend via the existing prompt mechanism. Three responses: `confirm` (use as-is), `correct` (replacement title + artist plus optional `write_back: bool`), `skip` (don't try Genius this run). On `correct + write_back=true`, server writes the corrected ID3 tags back to the MP3: write to a sibling `.bak` first, then atomic rename (per `pattern_atomic_write` discipline). On any write failure, surface error to UI but proceed with corrected metadata in-memory for the analyzer.
- [ ] 6a.4 Frontend: extend the existing Genius-retry modal/panel (don't add a brand-new screen) with an ID3 confirmation step that fires earlier in the flow. Three buttons: Confirm, Correct, Skip. The Correct branch reveals editable title + artist text fields and a "Save corrected tags back to MP3" checkbox (default off; user opts in). Update `src/review/frontend/src/screens/...` (locate exact file during implementation).
- [ ] 6a.5 Add Playwright e2e test for the full ID3 confirmation flow: upload, see prompt with prefilled fields, choose each branch, verify (a) Confirm proceeds with original metadata, (b) Correct + write-back produces a `.bak` file alongside an updated MP3, (c) Skip causes the analyzer to skip Genius lookup entirely (Fix 2 then surfaces a "no chorus body" warning per §7).
- [ ] 6a.6 Unit test: `tests/unit/test_id3_confirm.py` covering tag-read with all three responses, the atomic-write-with-backup path, and the no-tags-present case. Mock `mutagen` only for the no-tags edge case; use a real fixture MP3 for the read/write paths.

### 6b. Non-interactive callers: title-only fallback

- [ ] 6b.1 In the lyricsgenius lookup path in `src/analyzer/genius_segments.py` (find via grep: `g.search_song`), wrap the existing `g.search_song(title, artist)` in a fallback: if the result is `None` AND the caller is non-interactive (CLI batch, acceptance gate, library refresh), retry with `g.search_song(title)` (no artist). Log the fallback at `INFO` level. Do not silently fall back at `DEBUG` — the user should see this attempted. The Web flow does NOT trigger this fallback; it relies on §6a's pre-prompt instead.
- [ ] 6b.2 Add a `fallback_used: bool` field to the `GeniusMatch` dataclass (or equivalent metadata bag) so downstream code (and the UI) can know the match was found via title-only. Default `False`.
- [ ] 6b.3 Surface `fallback_used` in the analyze-step API payload and on the Analyze screen as a small badge ("title-only match") near the song's section list, so reviewers can see the lookup wasn't exact.
- [ ] 6b.4 Add a unit test in `tests/unit/test_genius_segments.py` covering: title+artist returns None → title-only retry → `fallback_used=True`; title+artist matches directly → `fallback_used=False`; both return None → existing not-found result (no exception).
- [ ] 6b.5 The interactive/non-interactive distinction is plumbed through `g.search_song(...)`'s caller via an explicit `allow_title_only_fallback: bool = False` parameter (default off — opt-in by callers that have no UI). The Web pipeline passes `False`; CLI batch / gate / library-refresh callers pass `True`.

## 7. Capability surfacing for refinement skips

- [ ] 7.1 In `refine_section_boundaries`, when a fix is skipped due to a missing capability (e.g., `chorus_body is None` for Fix 2 because no Genius match), append a corresponding warning to `HierarchyResult.warnings` of the form `"boundary refinement skipped: Fix 2 (relabel/split bridge) — no chorus body from Genius"`. One warning per skipped fix per song, not per section.
- [ ] 7.2 Surface these warnings in the analyze-step API payload (`HierarchyResult.warnings` already flows through; verify). Render them in the existing warnings panel on the Analyze screen if one exists; if not, surfacing is deferred but the data is in `_hierarchy.json` for diagnosis.
- [ ] 7.3 Add a unit test asserting that running `refine_section_boundaries(...)` with `chorus_body=None` skips Fix 2 and emits the expected warning string.

## 8. Documentation

- [ ] 8.1 Update `docs/segment-classification-changelog.md` per CLAUDE.md's Mandatory Changelog Rule. Append (do not modify) an entry for this change describing each of the three refinements and their preconditions, with the reasoning.
- [ ] 8.2 Add a paragraph to the Analyzer section of CLAUDE.md (or the project-level README) describing the boundary-refinement step's role in the pipeline. Cross-link to this OpenSpec change. Keep under 200 words.
- [ ] 8.3 Confirm `.wolf/anatomy.md` gets updated entries for the new files (`src/analyzer/free_transcription.py`, `src/story/boundary_refinement.py`, plus the new tests) per `.wolf/OPENWOLF.md` instructions.

## 9. Acceptance gate baseline + sign-off

- [ ] 9.1 Run `xlight-evaluate gate --skip-ui` locally before merging. All four suites (analyzer, generator, ui, section_fidelity) must return exit code 0. Capture the output in the PR description.
- [ ] 9.2 Verify the analyzer baseline that includes `boundary_refinements` is reproducible (re-run the snapshot twice; diff must be empty).
- [ ] 9.3 Manual UI verification: run `xlight-analyze review` against Cher, Crazy Train, Ghostbusters and confirm the analyze screen renders the refinement indicator on the expected sections, with tooltips showing the refinement notes.
- [ ] 9.4 Open the PR with the body cross-referencing this OpenSpec change directory; do NOT amend the proposal/design after PR open without a corresponding follow-up OpenSpec change (per project convention from existing OpenSpec changes).
