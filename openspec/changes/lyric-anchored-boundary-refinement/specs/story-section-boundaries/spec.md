## ADDED Requirements

### Requirement: Free-transcription step is a reusable analyzer module

A new module `src/analyzer/free_transcription.py` SHALL expose a public function `transcribe_free(audio_path: str, *, language: str = "en", device: str = "cpu") -> list[WordMark]` that runs WhisperX free transcription (no lyrics input) on the given audio path and returns the per-word timestamps as a list of `WordMark` instances. Existing callers in `src/analyzer/genius_segments.py` SHALL delegate to this function rather than maintaining their own transcription invocation.

#### Scenario: Standalone free transcription returns word-level marks

- **WHEN** `transcribe_free` is called with the path to a vocals stem
- **THEN** the function SHALL return a list of `WordMark` instances
  whose `start_ms` values are strictly non-decreasing, and whose
  `label` is the transcribed word

#### Scenario: Free transcription is reused inside Genius alignment

- **WHEN** the story builder runs the existing Genius alignment path on
  a song with a Genius match
- **THEN** Step 1 of `_run_genius_alignment` SHALL call
  `transcribe_free(...)` and use its return value, rather than
  invoking `whisperx.transcribe` directly
- **AND** the resulting `_story.json` for a known song (e.g. Cher's
  *DJ Play a Christmas Song*) SHALL be byte-identical to the pre-
  refactor output, modulo the new `boundary_refinements` field

#### Scenario: Missing audio path raises

- **WHEN** `transcribe_free` is called with a non-existent path
- **THEN** the function SHALL raise `FileNotFoundError`
- **AND** the function SHALL NOT silently return an empty list

### Requirement: Short post_chorus tails continuous with prior section are merged into the prior section

A `post_chorus` section SHALL be merged into its preceding section when ALL of the following hold:

- The preceding section has `kind` in `{verse, chorus, pre_chorus, bridge}`
- The `post_chorus` duration is `< 6000 ms`
- The `post_chorus` `agreement_score` is `<= 1`
- The temporal gap from the preceding section's last forced-aligned word's `end_ms` to the `post_chorus`'s first forced-aligned word's `start_ms` is `<= 1500 ms`

When merged, the preceding section's `end_ms` SHALL be extended to the `post_chorus`'s last forced-aligned word's `end_ms + 250 ms` tail, and the `post_chorus` section SHALL be removed from the section list. The preceding section's `boundary_refinements` SHALL gain a one-line note describing the merge (target label, gap in ms, word count).

#### Scenario: Cher's chorus 2 with mislabeled post_chorus tail is merged

- **WHEN** the story builder produces `Chorus 105.58–116.83 s (agreement=4)` followed by `Post Chorus 116.83–120.65 s (agreement=1, dur=3.82 s)` and the gap from chorus's last word end to post_chorus's first word start is `100 ms`
- **THEN** the post_chorus SHALL be merged into the chorus
- **AND** the resulting chorus SHALL span 105.58 → 121.72 s (last word end + tail)
- **AND** the chorus's `boundary_refinements` SHALL contain a note
  matching `"merged short post_chorus.*chorus tail"`

#### Scenario: Long post_chorus is not merged

- **WHEN** a post_chorus has duration `>= 6000 ms`
- **THEN** the merge SHALL NOT fire regardless of agreement_score or gap

#### Scenario: High-agreement post_chorus is not merged

- **WHEN** a post_chorus has `agreement_score >= 2`
- **THEN** the merge SHALL NOT fire even if the gap is small

#### Scenario: Post_chorus with vocal pause before it is not merged

- **WHEN** the gap from prior section's last word end to post_chorus's first word start is `> 1500 ms`
- **THEN** the merge SHALL NOT fire (the singer paused — the post_chorus is plausibly distinct)

#### Scenario: Refinement is recorded even when guards skip

- **WHEN** a post_chorus is examined but a precondition fails
- **THEN** the section list SHALL be unchanged
- **AND** no `boundary_refinements` note SHALL be added (skipped fixes are not surfaced as refinements; only fired ones are)

### Requirement: A Bridge whose sung content opens with the chorus first-line hook is relabeled or split

A section with `kind == "bridge"` SHALL be examined for chorus content using the chorus's first-line distinctive hook — defined as up to 4 words from the chorus body's first line, filtered to length `>= 3` and not in a stopword set including common contractions and high-frequency function words.

The hook is considered "matched" against a list of free-transcribed words if at least `max(2, len(targets) - 1)` of the hook's distinctive words appear in those words in order, each within 12 words of the previous match.

When the bridge is matched, its disposition is determined by the presence of an internal vocal gap of `>= 3000 ms` and which halves of the bridge match the hook:

- **No internal gap, hook matched in whole**: the bridge SHALL be relabeled with `kind = "chorus"` and its label suffixed with `" (→Chorus, full)"`. Bounds are unchanged.
- **Internal gap, hook matched in BOTH halves**: same as above — the bridge contains two chorus iterations with silence between. Relabel whole.
- **Internal gap, hook matched in PREFIX only (not in suffix)**: the bridge SHALL be split into two sections at the prefix's last word's `end_ms + 250 ms`. The prefix becomes `kind = "chorus"` with label `"Bridge→Chorus"`. The suffix remains `kind = "bridge"`.
- **Otherwise** (no hook anywhere, or hook only in suffix): the bridge SHALL be unchanged.

In every case where a relabel or split fires, the affected section's `boundary_refinements` SHALL gain a note describing what fired and why (which targets matched, where).

#### Scenario: Cher's bridge — chorus repeated entirely — is relabeled whole

- **WHEN** the story builder produces a `Bridge 120.65–150.13 s` whose free-transcribed content is `["DJ", "play", "Christmas", "song", "wanna", "dancing", ...]` and the chorus first-line hook is `["play", "christmas", "song", "wanna"]`
- **AND** the bridge has no internal vocal gap `>= 3000 ms`
- **THEN** the bridge SHALL be relabeled with `kind = "chorus"`
- **AND** the section's `boundary_refinements` SHALL contain a note matching `"chorus hook.*present.*transcribed"`

#### Scenario: Crazy Train's bridge — chorus prefix + verse-like tail — is split

- **WHEN** a `Bridge 140.31–176.89 s` has free-transcribed words showing the chorus hook in its prefix (140.49–143.71 s) followed by a 7.8-second instrumental gap, then non-chorus lyrics in the suffix (151.54 s onward)
- **THEN** the bridge SHALL be split into a `Bridge→Chorus` section ending at `prefix_last_word.end_ms + 250 ms` and a `Bridge` section from there to the original end
- **AND** the new chorus section SHALL have `kind = "chorus"`
- **AND** the bridge tail SHALL retain `kind = "bridge"`

#### Scenario: Ghostbusters' bridge — chorus repeated twice with silence — is relabeled whole

- **WHEN** a Bridge contains the chorus first-line hook in BOTH halves around an internal vocal gap `>= 3000 ms`
- **THEN** the bridge SHALL be relabeled with `kind = "chorus"`, NOT split (both halves are chorus iterations; a split would leave one half mislabeled)

#### Scenario: Believe — bridge with different lyrical content — is unchanged

- **WHEN** a Bridge's free-transcribed content does not contain the chorus first-line distinctive hook in order (a single coincidental word like "believe" appearing once is insufficient)
- **THEN** the bridge SHALL be unchanged
- **AND** no `boundary_refinements` note SHALL be added to the bridge

#### Scenario: Chorus first line too short to form a hook

- **WHEN** the chorus body's first line yields fewer than 2 distinctive words after stopword filtering
- **THEN** the bridge SHALL be unchanged regardless of its content
- **AND** a warning SHALL be appended to `HierarchyResult.warnings` of the form `"boundary refinement skipped: Fix 2 — chorus first line has insufficient distinctive words"`

#### Scenario: Genius produces no chorus body

- **WHEN** the story builder has no Genius match (or the Genius result has no `Chorus` section)
- **THEN** Fix 2 SHALL NOT fire on any section
- **AND** a warning SHALL be appended to `HierarchyResult.warnings` of the form `"boundary refinement skipped: Fix 2 — no chorus body from Genius"`

### Requirement: Vocal sections starting before the singer enters are split into Instrumental + remaining vocal

A vocal section (`kind` in `{verse, chorus, pre_chorus, post_chorus, bridge}`) SHALL be examined for a pre-vocal instrumental gap. The gap is the duration from the section's `start_ms` to its first free-transcribed word's `start_ms`. When the following hold:

- The section's label does NOT contain the strings `"instrumental"` or `"break"` (case-insensitive)
- The gap is `>= 5000 ms`
- The remaining vocal portion (from first word's start to section's `end_ms`) is `>= 3000 ms`
- The section contains at least one free-transcribed word (i.e., it is not entirely silent — different concern, out of scope)

a synthetic `Instrumental` section SHALL be inserted before the vocal section, spanning from the original `start_ms` to `first_word.start_ms - 250 ms`. The vocal section's `start_ms` SHALL be moved to that boundary. The vocal section's `boundary_refinements` SHALL gain a note describing the gap. The synthetic section's `boundary_refinements` SHALL contain a single note describing where the split came from.

#### Scenario: Cher's chorus 3 — long instrumental ramp — is split

- **WHEN** a `Chorus 150.13–174.16 s` has its first free-transcribed word at 163.75 s
- **THEN** an `Instrumental 150.13–163.50 s` section SHALL be inserted
- **AND** the chorus SHALL be moved to start at 163.50 s, ending at the original 174.16 s
- **AND** the chorus's `boundary_refinements` SHALL contain a note matching `"shifted start.*to first transcribed word"`
- **AND** the synthetic instrumental's `boundary_refinements` SHALL contain a note matching `"pre-vocal gap split off"`

#### Scenario: Section already labeled instrumental is not re-split

- **WHEN** a section's label contains the string `"Instrumental Break"`
- **THEN** the split SHALL NOT fire even if `kind` is set to a vocal kind (analyzer mislabel) — the existing label takes precedence

#### Scenario: Mislabeled chorus that is mostly instrumental is left for human review

- **WHEN** a vocal section's first free-transcribed word leaves less than 3000 ms of vocal remainder (e.g., a 7.99 s "Chorus" with first word at the very end of the section)
- **THEN** the split SHALL NOT fire
- **AND** the section's `boundary_refinements` SHALL contain a note matching `"section likely mislabeled"`

#### Scenario: Vocal section starting at the singer's entry is unchanged

- **WHEN** a vocal section's first free-transcribed word is within 5 s of the section's start
- **THEN** the section SHALL be unchanged

#### Scenario: Vocal section with no transcribed words is unchanged

- **WHEN** a vocal section contains zero free-transcribed words across its full span
- **THEN** the section SHALL be unchanged (whole-section misnaming is not addressed by this fix)

### Requirement: Boundary refinements run in fixed order 1 → 2 → 3 and accumulate notes per section

A new function `refine_section_boundaries(sections, hierarchy, forced_words, free_words, chorus_body)` SHALL invoke the three refinement passes in this exact order: (1) `merge_short_post_chorus_tail`, (2) `relabel_or_split_bridge`, (3) `split_pre_vocal_instrumental`. Each pass operates on the previous pass's output. Every section in the final result SHALL have a `boundary_refinements: list[str]` field, present even when empty.

#### Scenario: Crazy Train requires Fix 2 to run before Fix 3

- **WHEN** the story builder runs on Crazy Train's analyzer output (Bridge 140.31–176.89 s with chorus prefix + guitar solo + verse-like tail)
- **THEN** Fix 2 SHALL run first, splitting the bridge into `Bridge→Chorus` (140.31–144.82 s) and `Bridge` (144.82–176.89 s)
- **AND** Fix 3 SHALL run after, splitting the Bridge tail into `Instrumental` (144.82–151.29 s) and `Bridge` (151.29–176.89 s)
- **AND** the final section list SHALL contain those three new sections in that temporal order

#### Scenario: Section untouched by any refinement has empty boundary_refinements

- **WHEN** a section is unchanged by all three refinements
- **THEN** the section's `boundary_refinements` field SHALL be present and equal to `[]`
- **AND** the section SHALL NOT have an absent or `null` `boundary_refinements` field

#### Scenario: Section touched by multiple refinements accumulates notes

- **WHEN** a section is modified by Fix 2 (split) and the resulting suffix is then split again by Fix 3
- **THEN** the suffix section's `boundary_refinements` SHALL contain notes from both fixes in the order they were applied

### Requirement: `_story.json` carries `boundary_refinements` per section

The `_story.json` schema SHALL be bumped from version `1.0.0` to `1.1.0` to reflect an additive, backward-compatible change: each section dict gains an optional `boundary_refinements: list[str]` field. Code that reads `_story.json` SHALL default the field to `[]` when absent. The schema bump SHALL NOT require a manual file regeneration of legacy stories; missing fields SHALL be tolerated read-side per the `pattern_story_schema_migration` memory.

#### Scenario: Story with refinement notes round-trips through write / read

- **WHEN** the story builder writes a `_story.json` with one section carrying `boundary_refinements: ["merged short post_chorus..."]`
- **AND** the file is read back by `src/cli/library.py` or `src/review/api/v1/analysis.py`
- **THEN** the `boundary_refinements` field SHALL be preserved verbatim

#### Scenario: Legacy story without refinements field reads cleanly

- **WHEN** an analyzer reads a `_story.json` written before this change (no `boundary_refinements` field on any section)
- **THEN** the read SHALL succeed
- **AND** every section's effective `boundary_refinements` SHALL be `[]`

### Requirement: Analyze-step API propagates `boundary_refinements` and exposes a `low_refined` flag

The analyze-step API in `src/review/api/v1/analysis.py` SHALL include `boundary_refinements: list[str]` for every section in its payload (default `[]`) and SHALL include a derived boolean `low_refined: bool` equal to `len(boundary_refinements) > 0`.

#### Scenario: Refined section reports refinements in API payload

- **WHEN** the analyze-step API serializes a section whose source `_story.json` has `boundary_refinements: ["merged short post_chorus 'Post Chorus' as chorus tail"]`
- **THEN** the API payload's section dict SHALL have `boundary_refinements` equal to that list
- **AND** the API payload's section dict SHALL have `low_refined: true`

#### Scenario: Unrefined section reports empty list and false

- **WHEN** a section has empty `boundary_refinements`
- **THEN** the API payload SHALL emit `boundary_refinements: []` and `low_refined: false`

### Requirement: Analyze frontend renders a refinement indicator on refined sections

The frontend `Section` interface in `src/review/frontend/src/screens/Analyze.tsx` SHALL declare `boundary_refinements: string[]` and `low_refined: boolean`. The Analyze screen SHALL render a visual indicator (icon, badge, or color marker — implementation choice) on section rows where `low_refined` is true, with a tooltip listing the refinement notes.

#### Scenario: Refined section row is visually distinguished

- **WHEN** the Analyze screen receives a section with `low_refined: true`
- **THEN** the rendered section row SHALL include a visual marker not present on rows with `low_refined: false`
- **AND** the rendered marker SHALL expose a tooltip / popover that displays the strings in `boundary_refinements`

#### Scenario: Unrefined section row has no indicator

- **WHEN** every section in the list has `low_refined: false`
- **THEN** no row SHALL render the refinement indicator

### Requirement: Web upload flow confirms ID3 metadata before Genius lookup

The Web upload flow in `src/review/server.py` SHALL prompt the user to confirm or correct the song's title and artist *before* attempting any Genius lookup. The prompt SHALL be prefilled from the uploaded MP3's existing ID3 tags (read via `mutagen`) and SHALL accept three responses:

- **Confirm**: proceed with the prefilled metadata.
- **Correct**: the user supplies a replacement title and/or artist; proceeds with that metadata. The user MAY opt to write the corrected tags back to the MP3.
- **Skip**: the analyzer SHALL skip Genius lookup entirely for this run; downstream Genius-dependent refinements (Fix 2) SHALL emit their standard skip warnings.

When write-back is requested, the server SHALL write the corrected ID3 tags via an atomic write-with-backup pattern: a sibling `.bak` is written first, then the file is atomically replaced. On any write failure, the in-memory metadata SHALL still be used for the analyzer run, and the failure SHALL be surfaced to the UI.

This Requirement applies only to the interactive Web flow. Non-interactive callers (CLI batch, acceptance gate, library refresh) cannot prompt and follow the title-only fallback Requirement below.

#### Scenario: User confirms accurate ID3 tags

- **WHEN** the user uploads an MP3 whose ID3 tags read `title="DJ Play a Christmas Song", artist="Cher"`
- **AND** the user clicks Confirm
- **THEN** the analyzer SHALL invoke `g.search_song("DJ Play a Christmas Song", "Cher")` with no fallback attempt

#### Scenario: User corrects wrong artist and writes back to MP3

- **WHEN** the user uploads `holiday_road.mp3` whose ID3 tags read `title="Holiday Road", artist="Lindsey Buckingham"` and the user clicks Correct, replaces artist with `"Kesha"`, and checks "Save corrected tags back to MP3"
- **THEN** the server SHALL write `holiday_road.mp3.bak` containing the original bytes
- **AND** SHALL atomically replace `holiday_road.mp3` with the file carrying corrected ID3 tags
- **AND** SHALL invoke `g.search_song("Holiday Road", "Kesha")` for the Genius lookup
- **AND** the library record SHALL reflect the corrected artist on subsequent reads

#### Scenario: User corrects metadata without writing back

- **WHEN** the user clicks Correct and provides a replacement title or artist but leaves "Save corrected tags back to MP3" unchecked
- **THEN** the file on disk SHALL be unchanged
- **AND** the analyzer SHALL still use the corrected metadata in-memory for this run
- **AND** the next upload of the same file SHALL re-prompt with the original (unchanged) ID3 tags

#### Scenario: User skips Genius lookup entirely

- **WHEN** the user clicks Skip
- **THEN** the analyzer SHALL NOT invoke `g.search_song(...)` for this song
- **AND** Fix 2 (chorus-hook bridge relabel) SHALL emit a `"boundary refinement skipped: Fix 2 — no chorus body from Genius"` warning to `HierarchyResult.warnings`

#### Scenario: MP3 has no ID3 tags

- **WHEN** the uploaded file has no readable ID3 tags
- **THEN** the prompt SHALL appear with empty title and artist fields
- **AND** the user SHALL be required to fill them in (or Skip) before the analyzer proceeds

#### Scenario: Atomic write-back fails

- **WHEN** the user requests write-back but the OS-level rename fails (permission error, disk full)
- **THEN** the analyzer SHALL still proceed using the corrected in-memory metadata
- **AND** the UI SHALL display an error noting the file on disk was not updated
- **AND** the `.bak` SHALL be cleaned up if it was created

### Requirement: Non-interactive callers fall back to title-only Genius lookup

Non-interactive callers (CLI batch via `xlight-analyze analyze`, acceptance gate, library refresh) cannot present a confirmation prompt. When `g.search_song(title, artist)` returns `None` and the caller has opted in via `allow_title_only_fallback=True`, the lookup SHALL retry with `g.search_song(title)` (no artist). The fallback SHALL fire only on a `None` response — it SHALL NOT overwrite a successful title+artist match. The match metadata SHALL gain a `fallback_used: bool` field indicating which path produced the match.

The Web flow SHALL pass `allow_title_only_fallback=False` because §6a's pre-prompt is the preferred preventive fix. Non-interactive callers SHALL pass `allow_title_only_fallback=True`.

#### Scenario: Title+artist hits — no fallback

- **WHEN** `g.search_song("DJ Play a Christmas Song", "Cher")` returns a match directly
- **THEN** the fallback SHALL NOT fire
- **AND** the match metadata SHALL have `fallback_used: false`

#### Scenario: CLI batch caller — title+artist misses, title-only succeeds

- **WHEN** the CLI batch invokes `g.search_song("Holiday Road", "Lindsey Buckingham")` with `allow_title_only_fallback=True` and that returns None, and `g.search_song("Holiday Road")` returns a match (Kesha's cover)
- **THEN** the fallback SHALL fire
- **AND** the match metadata SHALL have `fallback_used: true`
- **AND** an INFO-level log entry SHALL be emitted noting the fallback was used

#### Scenario: Web caller never falls back

- **WHEN** the Web flow invokes `g.search_song("Holiday Road", "Lindsey Buckingham")` with `allow_title_only_fallback=False` and that returns None
- **THEN** the fallback SHALL NOT fire
- **AND** the lookup SHALL be reported as no-match (the Web flow's pre-prompt is the intended preventive path)

#### Scenario: Both fail — genuinely no match

- **WHEN** both calls return None (or only the title+artist call ran with fallback disabled)
- **THEN** the function SHALL return its existing not-found indication (None or equivalent)
- **AND** SHALL NOT raise

#### Scenario: `fallback_used` surfaces in API and UI

- **WHEN** a section's source song was matched via title-only fallback (`fallback_used=true`)
- **THEN** the analyze-step API payload SHALL include `fallback_used: true` at the song level
- **AND** the Analyze screen SHALL render a small "title-only match" badge near the section list

### Requirement: Refinement skips emit warnings to `HierarchyResult.warnings`

When a refinement pass is skipped because a precondition cannot be evaluated (chorus body unavailable, chorus first-line hook too short, vocals stem missing), the analyzer SHALL append a single warning to `HierarchyResult.warnings` describing which fix was skipped and why. One warning per skipped fix per song; per-section skips (e.g., a particular section that simply does not match a fix's preconditions) SHALL NOT produce warnings.

#### Scenario: Fix 2 skipped due to no Genius chorus

- **WHEN** the story builder has no Genius match for a song
- **THEN** `HierarchyResult.warnings` SHALL contain exactly one entry matching `"boundary refinement skipped: Fix 2.*no chorus body from Genius"`
- **AND** SHALL NOT contain a per-section repetition of that warning

#### Scenario: All refinements run — no skip warnings

- **WHEN** Genius matched, vocals stem present, and all preconditions are evaluable
- **THEN** no `"boundary refinement skipped"` warnings SHALL be appended
- **AND** sections may individually have their preconditions fail without producing warnings (per-section non-fires are silent)
