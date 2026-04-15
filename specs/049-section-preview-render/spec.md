# Feature Specification: Short-Section Preview Render

**Feature Branch**: `049-section-preview-render`
**Created**: 2026-04-14
**Status**: Draft
**Input**: Phase 5 of the web-UI UX overhaul (`~/.claude/plans/greedy-splashing-chipmunk.md`).
Corresponds to strategy principle #5 — "Preview before commit" — and to the Preview tab
of the per-song workspace introduced in spec 046. Full sequence generation takes minutes
of wall-clock time, and the output is a `.xsq` file the user has to open in xLights to
evaluate. This loop is too slow to iterate on the Brief (spec 047). A short per-section
preview closes the gap between "tweak a slider" and "see what it does."

## Background

Today there is no functional preview of what generation will produce for a given song
and Brief. The routes `/generation-preview` and `/api/generation-preview/<hash>` exist
in `src/review/server.py` but return only a static summary — section labels, durations,
stems-available, and a track count. They do **not** run the generator, do **not**
produce any effect placements, and cannot answer "does the Brief I just edited look
right?"

The full generator pipeline lives in `src/generator/plan.py::build_plan()` →
`place_effects()` → `write_xsq()`. It operates on the entire song and writes a
`.xsq` file. It is deterministic given a `GenerationConfig`, a `HierarchyResult`,
and a layout, but the cost scales with song length, section count, and per-group
rotation bookkeeping. A 3-minute song currently takes 30-90 seconds to plan + serialize
and longer once value curves are enabled. That cost dominates the Brief-iteration
feedback loop.

This spec defines a **short-section preview**: render exactly one section (10–20
seconds of music) through the real generator and surface the result inside the
Brief tab. The goal is fidelity + speed — the preview must represent what the full
render would produce for that section, but complete in a few seconds so the user
can tweak the Brief and re-run without breaking flow.

**Sequencing and dependencies:**

- **Depends on spec 046** (Song workspace shell + Preview tab shell). This spec
  fills the Preview tab with real content; the tab itself is created by 046.
- **Benefits from spec 048** (Precomputed section assignments). When section-level
  tier/palette/duration decisions are materialized on `SectionAssignment` before
  placement begins, rendering a single section becomes a clean slice of the pipeline
  rather than a fragile reach into per-tier loops. This spec works without 048 —
  it falls back to running the full `build_plan` and throwing away non-target
  sections — but 048 makes the implementation substantially cleaner and faster.
- **Highest-impact, highest-effort phase** per the strategy document. Every earlier
  phase (wayfinding, workspace shell, Brief, decision-ordering refactor) is primarily
  a UI or plumbing reshuffle. Phase 5 adds new rendering behavior and a new
  long-lived async job surface to the server. Call this out explicitly so scope is
  not underestimated.

**Non-goals** (reiterated from the task prompt):

- Does NOT replace full generation. The Generate tab still produces the
  authoritative full-song `.xsq`.
- Does NOT require any xLights integration beyond what a user already has. If the
  preview output is a `.xsq`, the user opens it in their own xLights install
  exactly as they would a full render.

---

## Clarifications

### Session 2026-04-14

- Q: When a user clicks Preview while a preview job is already in-flight for the same song, what happens? → A: **Supersede.** The new request cancels the in-flight job and starts fresh against the latest Brief. The UI shows "Previewing…" for the newest request. The cancelled job's artifact, if any was partially written, is discarded and never surfaced.
- Q: How is audio delivered with the preview `.xsq` — reference the original MP3 with an offset, or bundle a clipped audio file? → A: **Reference the original MP3 with an offset.** The preview `.xsq` points at the song's existing MP3 path with `start_offset_ms` = section start and `duration_ms` = previewed window length. No audio re-encoding, no bundled media clip. Assumes the user's xLights install can resolve the original MP3 path; this matches how full renders already work.

---

## User Scenarios & Testing

### User Story 1 — One-click section preview from the Brief tab (Priority: P1)

As a user editing my Brief on the Preview tab, I want to click a single **Preview**
button and receive a short preview of one representative section within a few seconds,
so I can evaluate whether my current Brief is producing the right feel without
committing to a full-song render.

**Why this priority**: This is the core value of Phase 5. Without this, every Brief
tweak requires a full render, which is the problem the phase exists to fix. The
default flow (pick a representative section automatically, render, surface the
output) is the 80% case and must work before anything else.

**Independent Test**: Open the Preview tab for a song that has a completed analysis
and a saved Brief. Click **Preview**. Within the target time budget the tab displays
a downloadable `.xsq` (P1) or an in-browser animation (P2) scoped to one section.
Opening the `.xsq` in xLights shows effects on the same prop groups, with the same
effect vocabulary and palette, that a full render would produce for that section.

**Acceptance Scenarios**:

1. **Given** a song with a saved Brief on the Preview tab, **When** the user clicks
   **Preview**, **Then** the server runs a scoped generation against the currently
   saved Brief and returns a single-section `.xsq` artifact within the configured
   time budget (target: ≤ 10 seconds wall-clock for a typical 3-minute song).
2. **Given** the preview job succeeds, **When** the tab renders the result,
   **Then** a download link for the preview `.xsq` appears along with metadata:
   selected section label, section start/end in the song, section energy, theme
   name, and number of effect placements produced.
3. **Given** the preview `.xsq` is opened in xLights, **When** it is played back,
   **Then** the effects on each prop group match (in effect name, variant, and
   palette) the effects that a full-song render of the same Brief would produce
   for that section.
4. **Given** the user has **not** saved the Brief, **When** they click **Preview**,
   **Then** the preview uses the in-memory (unsaved) Brief values from the form,
   so they can preview a change before persisting it.
5. **Given** the preview job fails (no analysis, no layout, no drum track,
   pipeline exception), **When** the result returns, **Then** the tab shows a
   human-readable error and does not leave stale data from a prior preview on
   screen.

---

### User Story 2 — Choose which section to preview (Priority: P1)

As a user iterating on the Brief, I want to explicitly choose which section to
preview from a dropdown (verse, chorus, bridge, drop, …), so I can evaluate Brief
decisions in the context that matters — e.g. a palette-restraint change is most
meaningful on a chorus, not on an intro.

**Why this priority**: Auto-selecting "highest-energy section" is correct as the
default but wrong for many evaluation scenarios. Users frequently tweak the Brief
to fix a specific moment ("the bridge felt flat last time"). Forcing them through
auto-selection to preview an unrelated section is the same UX failure the strategy
doc is trying to fix elsewhere — hiding creative choices.

**Independent Test**: Open the Preview tab. Verify a section dropdown is present,
populated from the song's analyzed sections (label + timestamp range + energy
score). Pick a specific section (not the default). Click **Preview**. The returned
preview's metadata reports the chosen section, not the auto-selected one.

**Acceptance Scenarios**:

1. **Given** a song with N sections, **When** the Preview tab loads, **Then** a
   dropdown lists all N sections as `"{label} — {start}–{end} — energy {score}"`,
   with the auto-selected representative section pre-selected.
2. **Given** the user changes the dropdown selection and clicks **Preview**,
   **Then** the preview renders the chosen section (not the auto-default), and
   the returned metadata names that section.
3. **Given** a song has no analyzed sections (unlikely but possible for corrupt
   analysis), **When** the tab loads, **Then** the dropdown is disabled with an
   inline message ("No sections available") and the Preview button is disabled.
4. **Given** the user previews section A, changes the dropdown to section B, and
   clicks **Preview** again, **Then** the result pane replaces the section-A
   output with the section-B output; section-A's download link is not silently
   left dangling.

---

### User Story 3 — Automatic representative-section selection (Priority: P1)

As a user who has not manually picked a section, I want the system to auto-select
a **representative** section — one that exercises the full Brief — so the default
preview is useful rather than arbitrary.

**Why this priority**: The zero-config preview must be good enough that most users
never touch the dropdown. A bad default ("always preview section 0") turns the
feature into a novelty.

**Independent Test**: For 5 songs of varied structure (verse-heavy, chorus-heavy,
EDM with drops, ballad, instrumental), call the auto-selection logic. Verify the
chosen section is the highest-energy non-outro section ≥ 4 seconds long. A user
manually inspecting the analysis for each song would agree "yes, that's the
representative one."

**Acceptance Scenarios**:

1. **Given** a song with at least one high-energy section (chorus, drop, climax),
   **When** auto-selection runs, **Then** it returns the section with the highest
   `energy_score` among sections ≥ 4 seconds long and not of role `outro` / `intro`.
2. **Given** ties in energy score, **When** auto-selection runs, **Then** it
   prefers `chorus` / `drop` / `climax` over other roles, then prefers the first
   occurrence (earlier sections tend to be structurally cleaner than final-chorus
   variants with tags).
3. **Given** a song with no high-energy section (all energy < 50), **When**
   auto-selection runs, **Then** it returns the longest non-intro / non-outro
   section, so at least something substantive is previewed.
4. **Given** a song with only an intro and an outro analyzed, **When**
   auto-selection runs, **Then** it falls back to the first section that is
   ≥ 4 seconds long, even if it is tagged `intro` / `outro`.

---

### User Story 4 — Re-preview on Brief change (Priority: P2)

As a user who just changed a Brief slider, I want the preview to refresh — either
automatically (debounced) or with a visible **Re-preview** button — so the new
Brief value is reflected without me needing to remember the manual step.

**Why this priority**: The strategy principle is "preview before commit," which
means preview should feel tethered to the Brief, not a separate one-shot. P2 rather
than P1 because the manual "Preview" button from Story 1 is already sufficient for
the core loop; auto-refresh is a smoothness improvement.

**Independent Test**: Open the Preview tab with a completed preview visible. Change
one Brief control. Confirm the preview result is visibly marked as stale (greyed
out, "Brief changed — click Re-preview"), or a debounced auto-refresh fires within
a small time window. Re-previewing produces a new `.xsq` that reflects the changed
value.

**Acceptance Scenarios**:

1. **Given** a completed preview is displayed, **When** the user changes any
   Brief field, **Then** the preview result is marked stale with a visible
   indicator and a **Re-preview** call-to-action.
2. **Given** the user clicks **Re-preview**, **Then** a new job runs against the
   current (possibly unsaved) Brief values and replaces the stale result.
3. **Given** the user changes the Brief and then reverts the change (same values
   as the last preview), **Then** the stale indicator clears without forcing a
   re-render. *(Nice-to-have; acceptable to always re-render on any edit.)*
4. **Given** auto-refresh is enabled (optional setting), **When** the user stops
   editing for longer than the debounce window (e.g. 1500ms), **Then** a preview
   job fires automatically. **While** a preview is already running, a new
   debounced fire MUST supersede it per FR-009 (cancel in-flight, start fresh
   against the latest Brief) — never run in parallel, never queue.

---

### User Story 5 — In-browser visual preview (Priority: P3 / stretch)

As a user who does not want to switch to xLights to evaluate a preview, I want a
visual approximation rendered directly in the browser (a canvas animation showing
a rough pixel grid of the prop layout with the section's effect placements
playing in real time), so a quick yes/no judgment can happen entirely on the
Preview tab.

**Why this priority**: The highest-fidelity preview is always the `.xsq` opened in
xLights. Browser approximations are lossy (they will never render exactly what
xLights does for complex effects like Plasma, Fire, or Butterfly). But the user's
dominant question — "is this the right vibe?" — can often be answered from a
low-fidelity canvas without leaving the browser. This is explicitly stretch: it can
ship later or never without blocking P1 value.

**Independent Test**: With in-browser preview enabled, run a preview. The canvas
shows prop groups as rectangles/dots arranged by their normalized layout positions,
and effect placements animate their active groups through approximated colors and
motion synced to the audio. Audio playback is driven by the same WebAudio pipeline
used by the existing timeline view.

**Acceptance Scenarios**:

1. **Given** in-browser preview is enabled, **When** a preview completes, **Then**
   the canvas plays the section in sync with the section's audio slice.
2. **Given** the user plays the in-browser preview, **When** an effect placement
   is active, **Then** its assigned prop group(s) animate with at least a
   palette-correct color and a motion hint (pulse / wash / sweep / strobe)
   appropriate to the effect family.
3. **Given** an effect with no browser approximation exists, **When** that effect
   is active, **Then** the prop group shows a flat palette-colored fill (fallback)
   rather than going dark, and an inline legend notes "approximated."
4. **Given** the user still wants the real xLights result, **When** they click
   **Download .xsq**, **Then** the same preview is also available as a downloadable
   `.xsq` file. Browser visualization and `.xsq` download coexist.

---

### Edge Cases

- **No analysis yet**: Preview tab shows an inline prompt ("Run analysis first")
  and links to the Analysis tab. The Preview button is disabled.
- **No layout configured**: Preview tab shows "Complete Setup → Layout" with a link
  to Zone A. Preview button disabled. (Same gate as full generation.)
- **Brief incomplete**: Minimum Brief fields are needed (genre, occasion, mood
  intent). If any are missing, the preview still runs using config defaults, but
  the result banner warns "Preview used default values for: …" so the user knows
  what is being rendered.
- **Concurrent previews**: A second Preview click while a job is in-flight cancels the in-flight job and starts fresh (supersede semantics — see FR-009). The cancelled job's output is discarded and never surfaced to the user.
- **Very short sections**: If the representative section is shorter than the
  minimum preview length (target 10s), extend the preview window to 10s by
  including the next section's opening. Label the result clearly
  ("chorus + start of bridge") so the user knows the preview crosses a boundary.
- **Very long sections**: If the selected section is longer than the max preview
  length (target 20s), use the first 20s of the section. This captures the
  intro-of-section shape which is what most effect decisions key off.
- **Preview disabled by flag**: A server-side feature flag `preview_enabled`
  (default True) can disable the Preview tab contents, e.g. in hosted environments
  where background CPU is constrained. The tab still appears (per 046) but shows
  "Preview is disabled in this environment."
- **Stem-dependent Briefs**: If the Brief references stems that were not
  separated for this song (e.g. `beat_accent_effects=True` but `drums` stem
  missing), the preview behaves exactly as full generation does — the accent
  placements are silently skipped. The result banner surfaces the skip so the
  user is not confused by the missing accents.
- **Cache hits**: If the user clicks **Preview** with identical Brief + section
  selection as a prior run that is still in memory, the server may return the
  cached artifact instead of re-running. Cache key = `(song_hash,
  section_index, brief_hash)`. TTL is at server discretion; a bounded in-memory
  LRU is sufficient.

---

## Requirements

### Functional Requirements

- **FR-001**: A new POST endpoint `/api/song/<hash>/preview` MUST accept a Brief
  payload (or reference to the saved Brief) plus an optional `section_index`.
  It MUST launch a scoped generation job and return a job id for polling, matching
  the async-job convention already used by full generation in spec 034.
- **FR-002**: A new GET endpoint `/api/song/<hash>/preview/<job_id>` MUST return
  the job's status (`queued` / `running` / `done` / `failed`), result metadata
  (section label, start/end, theme, effect placement count), and either a
  downloadable artifact path or an error message.
- **FR-003**: When no `section_index` is supplied, the server MUST auto-select the
  representative section per the rules in User Story 3 (highest-energy non-intro,
  non-outro section ≥ 4 seconds; role-based tiebreaker; longest-section fallback).
- **FR-004**: Preview MUST run through the real generator pipeline
  (`build_plan` → `place_effects` → `write_xsq`), scoped to a single section's
  time range. A scoped pipeline is preferred over a simplified parallel path so
  the preview has full fidelity with the eventual full render. **Trade-off**:
  scoping requires either (a) filtering `assignments` to a single index after
  `build_plan` runs, discarding work for other sections, or (b) a targeted
  refactor (cleaner post-spec 048) that lets `build_plan` accept a
  `section_filter`. Option (a) is acceptable for the first implementation;
  option (b) is a follow-up once 048 lands.
- **FR-005**: The preview artifact MUST be a valid `.xsq` file whose media
  duration equals the section's duration (clamped to 10–20s per the edge case
  rules). All non-target sections MUST be absent from the output — the timeline
  must start at 0 and cover only the previewed window, so xLights does not need
  the full song media file.
- **FR-006**: The preview MUST reuse the song's existing audio by **referencing the original MP3 path** with a start offset equal to the previewed section's start time and a duration equal to the previewed window length. No clipped audio file is produced; no re-encoding occurs. The preview `.xsq` is audio-dependent on the user's original MP3 remaining accessible at the same path in their xLights install (the same assumption full renders already make). Bundling a clipped WAV/MP3 is explicitly out of scope.
- **FR-007**: Preview wall-clock time from POST to `done` MUST be ≤ 10 seconds
  for a typical 3-minute song on the reference hardware (same as full-render
  reference hardware). This is a target, not a hard cap — the success criterion
  for "fast enough to iterate."
- **FR-008**: The Preview tab in the Brief workspace MUST display: the current
  section dropdown, a primary **Preview** button, a stale-marker when the Brief
  has changed since the last preview (User Story 4), a result area with a
  download link plus metadata, and an error area for failures.
- **FR-009**: Concurrent previews for the same song MUST use **supersede** semantics. A new Preview request while one is in-flight MUST cancel the in-flight job and start fresh against the latest Brief. The UI MUST reflect the newest request ("Previewing…") and MUST NOT surface the cancelled job's partial artifact. Queueing and coalescing of intermediate requests is out of scope.
- **FR-010**: Preview jobs MUST NOT write to the permanent output directory used
  by full generation. Artifacts MUST live in a `preview/` subdirectory (or
  `tempfile.mkdtemp()`) so preview `.xsq` files can be cleaned up without
  touching the user's real renders.
- **FR-011**: The preview endpoint MUST honor every Brief field that full
  generation honors, including (at minimum) `focused_vocabulary`,
  `embrace_repetition`, `palette_restraint`, `duration_scaling`,
  `beat_accent_effects`, `tier_selection`, `curves_mode`, and any per-section
  theme overrides that intersect the previewed section.
- **FR-012**: In-browser visual preview (User Story 5) is stretch / P3. When
  implemented, it MUST coexist with the `.xsq` download — never replace it.
- **FR-013**: If the preview job fails, the failure MUST NOT leave a stale
  artifact from a previous run as the "current" preview. The UI MUST clearly
  distinguish "error" from "previous preview still valid."
- **FR-014**: Existing `/api/generation-preview/<hash>` (the static summary
  endpoint in `src/review/server.py`) is unrelated to this feature and MUST
  remain working. This spec introduces a separate endpoint family
  (`/api/song/<hash>/preview`) and does not change or rely on
  `generation-preview`.

### Key Entities

- **PreviewJob**: Server-side async job representing one preview render. Carries
  `job_id`, `song_hash`, `section_index`, `brief_snapshot`, `status`,
  `started_at`, `completed_at`, `artifact_path`, `error_message`. Stored
  in-process (dict) like the spec-034 generation jobs.
- **PreviewRequest**: The POST body — `{ section_index: int | null, brief: {...}
  | "saved" }`. When `brief` is `"saved"`, the server reads the persisted Brief
  for the song; otherwise the inline Brief object is used (supports the
  "preview unsaved changes" case from User Story 1 acceptance #4).
- **PreviewResult**: The response shape — `{ section: {label, start_ms, end_ms,
  energy}, theme_name, placement_count, artifact_url, warnings: [...] }`.
  `warnings` surfaces soft failures like "drums stem missing — accents skipped"
  (FR-011 interaction with missing-stem edge case).
- **RepresentativeSectionPicker**: Pure function over the section list and role
  labels. Implements User Story 3's ranking. No side effects; unit-testable.

---

## Success Criteria

- **SC-001**: For 5 reference songs (varied length, structure, and energy
  profile), preview completes in ≤ 10 seconds wall-clock on the reference
  hardware from POST to `done`.
- **SC-002**: For each of those 5 songs, the effects placed on each prop group
  in the preview `.xsq` match (by effect name, variant, and palette) the effects
  placed by a full-song render of the same Brief when restricted to the
  previewed section's time range.
- **SC-003**: The auto-selected representative section matches the section a
  human reviewer would pick in ≥ 4 of the 5 reference songs. (A single
  disagreement is acceptable; systematic failure is not.)
- **SC-004**: Opening a preview `.xsq` in xLights plays audio in sync with
  effects for the previewed 10–20s window, with no gap or drift.
- **SC-005**: Changing a Brief field after a successful preview visibly marks
  the preview stale within 500ms of the edit.
- **SC-006**: A preview failure (simulated — e.g. missing analysis) surfaces a
  human-readable error in the Preview tab without crashing the tab or leaving a
  stale artifact marked as current.
- **SC-007**: The existing `/api/generation-preview/<hash>` summary endpoint
  continues to return its existing payload unchanged (regression guard).
- **SC-008**: Existing test suite passes with no regressions.

---

## Open Design Questions — Spec Answers

These are the open questions called out in the task prompt. The spec takes a
position on each so downstream planning has a clear starting point; any of them
may be revisited during implementation with justification.

1. **Scoped-full-path vs simplified pipeline?** Answer: **scoped-full-path**
   (FR-004). Preview runs `build_plan` end-to-end and filters to the target
   section post-hoc for the first implementation; a cleaner `section_filter`
   parameter is a follow-up after spec 048 lands. The tradeoff is that first-cut
   preview does more work than strictly necessary (derives all sections, then
   throws most away). This is acceptable because (a) the cost dominates at
   `place_effects`, which is per-section and the outer loop simply skips the
   non-target ones once we add a guard, and (b) a simplified parallel path would
   drift from full generation over time and defeat the fidelity goal.
2. **Output format — `.xsq`, in-browser, both?** Answer: **`.xsq` is P1.
   In-browser animation is P3/stretch** (FR-005, User Story 5). Reasoning:
   `.xsq` is the authoritative output format; a download link that the user
   opens in xLights gives the truest preview and requires the least new
   rendering code. In-browser animation is strictly value-add and lossy; it is
   worth doing once the `.xsq` path is solid, never before.
3. **How is the representative section picked?** Answer: **highest-energy
   non-intro, non-outro section ≥ 4 seconds, with role-based tiebreaker
   (chorus / drop / climax preferred), falling back to longest non-intro /
   non-outro if no high-energy section exists** (User Story 3, FR-003).

---

## Key Files

- `src/review/server.py` — add `/api/song/<hash>/preview` POST + status GET
  endpoints; wire in `PreviewJob` tracking analogous to spec-034's generation
  jobs.
- `src/generator/plan.py` — introduce an optional `section_filter: int | None`
  parameter on `build_plan` so single-section preview can short-circuit
  per-section work (follow-up after spec 048; first implementation may filter
  post-hoc).
- `src/generator/xsq_writer.py` — support a scoped duration and time-offset so
  the output `.xsq` covers only the previewed window.
- `src/generator/preview.py` *(new)* — `pick_representative_section()`,
  `run_section_preview()`, `PreviewJob` dataclass. Isolated from full-generation
  code so preview behavior changes do not bleed into full renders.
- `src/review/static/song-workspace.js` *(from spec 046)* — extend the Preview
  tab handler with the dropdown, Preview button, re-preview / stale logic, and
  download link rendering.
- `src/review/static/song-workspace.html` *(from spec 046)* — add Preview-tab
  DOM structure (dropdown, button, result pane, error pane, stale marker).
- `tests/unit/test_preview_section_picker.py` *(new)* — representative-section
  auto-selection rules (User Story 3).
- `tests/unit/test_preview_job.py` *(new)* — job lifecycle, concurrent-request
  handling, cache-key behavior.
- `tests/integration/test_section_preview.py` *(new)* — end-to-end: POST
  preview → poll → download `.xsq` → validate it contains only the target
  section's effects over the expected time range.
