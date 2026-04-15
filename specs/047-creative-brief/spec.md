# Feature Specification: Creative Brief (Per-Song Workspace, Phase 3)

**Feature Branch**: `047-creative-brief`
**Created**: 2026-04-14
**Status**: Draft
**Input**: Phase 3 of the web UX overhaul (strategy: `greedy-splashing-chipmunk.md`). Builds on the per-song workspace shell from spec 046. Introduces the "Brief" tab — a single form that is the single source of truth for every creative decision about a song. This is the phase where the strategy doc's thesis ("decisions at the end → decisions at the beginning") is actually realized in the UI. Phase 4 (spec 048) will refactor the backend pipeline so the Brief's choices attach cleanly; this spec works against the existing generator.

## Background

Today's web UI scatters creative choices across four homes: server config (layout path), `/story-review` (theme overrides, transition mode), `/themes` and `/variants` (library admin), and a dashboard POST body that is not rendered by any form. `GenerationConfig` carries thirteen creative knobs — `genre`, `occasion`, `transition_mode`, `curves_mode`, `focused_vocabulary`, `embrace_repetition`, `palette_restraint`, `duration_scaling`, `beat_accent_effects`, `tier_selection`, `theme_overrides`, `target_sections`, `tiers` — but only `genre`, `occasion`, and `transition_mode` have *any* UI surface, and even those live three pages away from the Generate button.

The result is that the user has no single place to answer the question "what is this sequence going to feel like?" before pressing Generate. Each flag became a boolean with a sensible default, and no user has ever knowingly changed one of them.

The Brief tab fixes this. Every creative knob in `GenerationConfig` gets a named home. Each control is a small set of named presets ("Snappy / Balanced / Flowing") before it is a number. Every preset has an "Auto" option that preserves today's implicit behavior. The Brief is persisted per song, so re-opening the workspace restores the last brief. Submitting the Brief is what triggers generation.

### Relationship to neighboring specs

- **Spec 046 (Phase 2 — per-song workspace shell)** is a hard prerequisite. This spec assumes the `/song/<hash>` page exists with a tab bar. The Brief tab slots into that shell.
- **Spec 048 (Phase 4 — pipeline decision-ordering refactor)** is a follow-up, not a prerequisite. Phase 3 ships against the existing `build_plan` / `place_effects` code path and the existing `/generate/<source_hash>` POST endpoint, which already accepts all thirteen `GenerationConfig` fields. Phase 4 will clean up the backend so the Brief's choices have first-class per-section attachment points; this Brief UI does not change in Phase 4.
- **Spec 019 (effect themes), 033 (theme/variant separation), 027 (dashboard)** provide the theme catalog consumed by the per-section override table.
- **Story-review page** (`/story-review`) continues to exist as a deep-dive timeline tool, but its per-section theme override feature — the only part of that page that influences generation — is absorbed into the Brief tab. After this ships, a user never needs to visit `/story-review` to generate a sequence.

---

## Clarifications

### Session 2026-04-14

- Q: How does the new Mood Intent axis behave in Phase 3 before Phase 4 wires it to the generator? → A: Persisted AND drives smart Auto-defaults on sibling controls that are still set to "Auto" (recommended theme family, accent intensity, transition mode). Explicit non-Auto selections on siblings are never overridden by mood. Direct generator wiring lands in Phase 4; the Phase 4 upgrade is additive.
- Q: How do Brief fields reach `GenerationConfig` given that the existing `/generate/<hash>` endpoint reads some fields from `_story_reviewed.json` today? → A: Extend the POST endpoint to accept every Brief field in the request body. `/generate/<hash>` stops consulting `_story_reviewed.json` for `genre`, `occasion`, and `transition_mode` — those come from the POST body when present. The Brief JSON is the only persistence surface the Brief writes to; `/story-review` continues to write its own preferences file for its own UI, but generation no longer reads from it.

---

## User Scenarios & Testing

### User Story 1 — Single Brief Form Is the Source of Truth (Priority: P1)

As a user, I want one page where every creative decision for a song is visible and
editable, so that I don't have to guess what the generator will do and I never have
to visit three different pages to change how a sequence feels.

**Why this priority**: The entire point of Phase 3 is that every `GenerationConfig`
flag has a named home in the UI. Without this, the rest of the overhaul is cosmetic
— the user is still pressing a black-box Generate button. Every other story in
this spec assumes the Brief form exists and is authoritative.

**Independent Test**: Open `/song/<hash>` and click the Brief tab. Confirm all
eleven user-facing controls (genre, occasion, mood intent, variation, palette,
duration, accents, transitions, curves, per-section theme overrides, Auto master
toggle) are visible on one page. For each, confirm the displayed default value
matches the resolved value that `GenerationConfig.__init__` would produce for
this song today.

**Acceptance Scenarios**:

1. **Given** a song whose workspace has never been opened, **When** the user clicks
   the Brief tab, **Then** every control shows either the ID3-prefilled value (genre,
   occasion where applicable) or "Auto", and no control is empty or undefined.
2. **Given** the Brief tab is open, **When** the user scrolls through the form,
   **Then** each control displays a one-line "why this matters" hint directly
   beside or below it, explaining the visible effect of changing it.
3. **Given** a brief has been submitted for the song in a prior session, **When** the
   user re-opens the workspace and clicks Brief, **Then** every control restores the
   previously submitted values (not defaults) within 500ms of tab activation.
4. **Given** the Brief tab is the active view, **When** the user navigates to the
   Analysis or Generate tab and back, **Then** unsaved edits in the Brief are
   preserved (local to the workspace session; persisted on submit).
5. **Given** any creative decision the generator makes (a `GenerationConfig` field),
   **When** the user inspects the Brief tab, **Then** that decision is represented
   by exactly one control — no hidden flags, no duplicate controls.

---

### User Story 2 — Presets Before Sliders, Auto Is Always Valid (Priority: P1)

As a user who doesn't know what "focused_vocabulary" means, I want each control to
offer 3–5 named presets (including "Auto") instead of a raw number or technical
flag name, so that I can make a musical choice without understanding the
implementation.

**Why this priority**: The strategy doc calls this out explicitly. A user who
cannot decode `palette_restraint=True` is not going to set it. The Brief is
worthless as a decision surface if it exposes booleans and floats by default.
"Auto" must be valid for every axis so the current default behavior is always
one click away.

**Independent Test**: For each of the nine axis controls (genre, occasion, mood,
variation, palette, duration, accents, transitions, curves), confirm the primary
UI element is a named preset selector — not a slider, checkbox, or text box —
and that "Auto" is one of the presets. Confirm an "Advanced" disclosure, when
expanded, reveals the underlying numeric/flag values that back the presets.

**Acceptance Scenarios**:

1. **Given** the Brief tab, **When** the user inspects any axis control, **Then**
   the default-visible element is a named-preset selector (radio group, segmented
   control, or dropdown) with no fewer than 3 and no more than 5 options, one of
   which is labelled "Auto".
2. **Given** any axis control, **When** the user selects "Auto", **Then** the
   corresponding `GenerationConfig` field is submitted with the current library
   default (matching today's behavior for that flag), and the submitted JSON
   payload MAY either omit the field or explicitly send the default value —
   both are acceptable.
3. **Given** an axis control with an "Advanced" disclosure, **When** the user
   opens it, **Then** the raw numeric or flag-level controls that back the
   preset become visible (e.g., Variation Advanced exposes
   `focused_vocabulary` and `embrace_repetition` as separate checkboxes).
4. **Given** the user has selected a named preset, **When** they open Advanced,
   **Then** the raw controls are pre-populated to the values that preset
   corresponds to (no surprise defaults inside the disclosure).
5. **Given** the user edits a raw control inside an Advanced disclosure and
   thereby diverges from any named preset, **When** they return to the preset
   selector, **Then** the preset indicator shows "Custom" (or equivalent) and
   does not silently re-snap to a named preset.

---

### User Story 3 — Brief Persists Per Song (Priority: P1)

As a user who generated a sequence yesterday, I want to reopen the song's
workspace today and see exactly the brief I submitted, so that I can tweak one
knob and re-generate without reconstructing every choice from memory.

**Why this priority**: A non-persistent brief is worse than no brief — the user
would have to re-enter ten controls every time they want to re-generate a song.
Persistence is also what makes the "compare renders" affordance (future) possible,
since each generation is logged with its brief snapshot.

**Independent Test**: Open a song's Brief tab, change several controls away from
"Auto", submit, wait for generation to complete, close the browser, restart the
server, reopen the same song's workspace, click Brief. Confirm every changed
control displays the submitted value, not "Auto".

**Acceptance Scenarios**:

1. **Given** a user edits the Brief and submits it (triggering generation),
   **When** the server responds with job acceptance, **Then** the brief is written
   to persistent storage keyed by the song's source hash before the job ID is
   returned to the client.
2. **Given** a persisted brief exists for a song, **When** the workspace loads
   the Brief tab, **Then** the persisted values populate every control within
   a single GET request (no progressive reveal, no flash-of-defaults).
3. **Given** no persisted brief exists for a song, **When** the workspace loads
   the Brief tab, **Then** the form falls back to library defaults merged with
   ID3-derived genre/occasion, matching the current implicit behavior.
4. **Given** a persisted brief references a theme slug that no longer exists in
   the theme catalog (user deleted a custom theme), **When** the Brief loads,
   **Then** the per-section override for that section displays "Auto" and a
   non-blocking warning chip; other sections are unaffected.
5. **Given** a user opens the Brief tab and makes unsaved edits, **When** they
   close the tab/browser without submitting, **Then** the next session shows the
   last *submitted* brief, not the abandoned draft. (Draft persistence is out of
   scope for Phase 3.)
6. **Given** a persisted brief, **When** the user clicks an explicit "Reset to
   Auto" control on the Brief tab, **Then** all controls revert to library
   defaults and the persisted brief is cleared on the next submit (reset alone
   does not rewrite storage).

---

### User Story 4 — Submitting the Brief Triggers Generation (Priority: P1)

As a user, I want a single "Generate" button at the bottom of the Brief tab that
submits the brief and kicks off sequence generation with those exact choices,
so that there is no separate "save brief" vs "generate" step.

**Why this priority**: The strategy doc is explicit that the Brief tab is where
generation is *initiated*. Splitting "save brief" from "generate" would recreate
today's problem of scattered actions. One button, one intent: "generate with
these choices".

**Independent Test**: Fill the Brief with non-default values (mood=Dramatic,
variation=Varied, palette=Restrained, one section override). Click Generate.
Confirm (a) the POST body to `/generate/<source_hash>` contains the non-default
values at the correct JSON keys, (b) the Generate tab becomes active and shows
job progress, (c) the completed `.xsq` reflects the submitted choices (verified
by inspecting the plan JSON or the resulting XML).

**Acceptance Scenarios**:

1. **Given** the user has edited the Brief, **When** they click Generate, **Then**
   the Brief is persisted AND a POST is issued to the existing
   `/generate/<source_hash>` endpoint (see `src/review/generate_routes.py`) with
   every brief field serialized into the body, AND the UI switches to the
   Generate tab to show progress.
2. **Given** the Brief contains fields the existing POST endpoint does not yet
   accept in its request body (today it reads `genre`, `occasion`, and
   `transition_mode` from `_story_reviewed.json` instead of the POST), **When**
   the Brief submits, **Then** the endpoint MUST be extended to accept every
   Brief field in the body, and `/generate/<hash>` MUST stop consulting
   `_story_reviewed.json` for those three fields — the body wins
   unconditionally.
3. **Given** the server rejects a brief value (validation failure — e.g. unknown
   genre), **When** the response returns, **Then** the Brief tab displays the
   error inline beside the offending control and no job is created.
4. **Given** a generation job is already running for this song, **When** the user
   edits the Brief and clicks Generate again, **Then** the UI either queues the
   new job or explicitly blocks the click with a "Generation in progress" message
   — it does not silently discard the edit.
5. **Given** the user submits the Brief without changing anything (all "Auto"),
   **When** the request reaches the server, **Then** generation proceeds with
   the same effective config as today's "click Generate on the dashboard" flow
   — the Brief adds no new required fields.
6. **Given** a successful generation, **When** the Generate tab shows completion,
   **Then** the brief snapshot that produced the result is recorded alongside
   the job (for a future "compare renders" feature — stored on the job record,
   not required to render in Phase 3).

---

### User Story 5 — Per-Section Theme Overrides Embedded in the Brief (Priority: P2)

As a user who knows section 3 should use a different theme than the auto-assigned
one, I want a compact per-section table inside the Brief tab where I can override
the theme for individual sections, so that I don't have to open `/story-review`
just to change one section.

**Why this priority**: Per-section theme override is the *only* feature of
`/story-review` that directly influences generation output, and it's the single
most-requested creative control in practice. Embedding it in the Brief closes
the loop of "all creative decisions live here". P2 rather than P1 because the
`theme_overrides` field already works end-to-end via the POST body; this story
is about surfacing it, not plumbing it.

**Independent Test**: Open the Brief tab for a song with at least 8 detected
sections. Scroll to the Per-Section Overrides panel. Change two sections away
from "Auto" to specific theme slugs. Submit. Inspect the resulting sequence
plan and confirm those two sections use the overridden themes while every other
section uses the auto-assigned theme.

**Acceptance Scenarios**:

1. **Given** a song with N sections from the analysis, **When** the Brief tab
   loads, **Then** the Per-Section Overrides panel shows exactly N rows, each
   displaying the section index, label (verse / chorus / etc.), time range
   (mm:ss – mm:ss), energy score, and a theme selector defaulting to "Auto".
2. **Given** the user sets a per-section override to a specific theme slug,
   **When** the Brief submits, **Then** the submitted payload includes
   `theme_overrides: {<section_index>: <theme_slug>}` matching the existing
   `GenerationConfig.theme_overrides` contract (int keys → theme slug strings).
3. **Given** an override table row, **When** the theme selector is "Auto",
   **Then** that section index is omitted from the submitted `theme_overrides`
   dict (not sent as null, not sent as the default theme string).
4. **Given** a previously-submitted brief with overrides on sections 2 and 5,
   **When** the Brief reloads, **Then** rows 2 and 5 show the overridden slugs
   and all other rows show "Auto".
5. **Given** the user clicks a "Clear all overrides" control on the panel,
   **When** the next submit occurs, **Then** the `theme_overrides` field is
   absent (or empty) in the submitted payload and every row resets to "Auto".
6. **Given** the story-review page is still used elsewhere, **When** the user
   edits per-section themes in `/story-review`, **Then** those edits are NOT
   auto-synced back into the Brief in Phase 3. The Brief's per-section panel
   is authoritative; `/story-review` continues to write its own preferences
   file. Resolving this overlap belongs to Phase 4.

---

### User Story 6 — Hints Explain Why Each Control Matters (Priority: P2)

As a user who is musically literate but not a lighting designer, I want a
one-line hint beside each control that tells me what the visible effect is of
changing it, so that I can make informed choices without reading docs.

**Why this priority**: Named presets alone are not enough — "Focused" vs "Varied"
is a label, not an explanation. The hint is what converts the form from
"inscrutable knobs" to "creative decisions I understand". P2 because presets
alone are shippable, but without hints the Brief is notably less useful for a
first-time user.

**Independent Test**: For each of the nine axis controls, confirm a hint string
is rendered within 120 characters, describes the observable visual effect (not
the implementation), and does not repeat the control label. Confirm hints are
always visible (not tooltips-only) so a user scanning the page sees them
without hovering.

**Acceptance Scenarios**:

1. **Given** any axis control on the Brief tab, **When** the tab is rendered,
   **Then** a hint text element is present with a non-empty string, positioned
   directly below or beside the control (not behind a hover tooltip).
2. **Given** a hint string, **When** reviewed, **Then** it describes what the
   user will observe in the generated sequence (e.g. "How long each effect
   lingers — Snappy cuts on beats, Flowing crossfades over bars") rather than
   restating the control name or naming a config flag.
3. **Given** a user selects a specific preset, **When** the preset is active,
   **Then** the hint MAY optionally update to describe what *that preset*
   specifically does. A static hint that describes the axis is also acceptable;
   preset-specific hints are a stretch goal.
4. **Given** the user opens an Advanced disclosure, **When** raw controls
   appear, **Then** each raw control carries its own hint that is allowed to
   use technical terminology (flag names, numeric ranges) since the user has
   opted into the advanced view.

---

### User Story 7 — Brief Tab Composes Cleanly Into the Workspace Shell (Priority: P3)

As a returning user, I want the Brief tab to feel like a native part of the
per-song workspace — consistent chrome, predictable tab order, stateful badges
— so that moving between Analysis / Brief / Generate feels like a single app,
not three bolted-on pages.

**Why this priority**: Navigation polish. The workspace shell from spec 046 is
responsible for the tab bar; this story just confirms Phase 3 does not regress
the shell. P3 because functional correctness takes precedence over polish in a
Draft spec.

**Independent Test**: Navigate Analysis → Brief → Generate → Analysis. Confirm
tab activation state is correct, keyboard focus is preserved when switching,
and the Brief tab shows a status badge ("Unsaved" when edits are pending,
"Submitted" once generation has been triggered with the current values).

**Acceptance Scenarios**:

1. **Given** the workspace shell from spec 046, **When** the Brief tab is added,
   **Then** it appears in the tab order between Analysis and Generate (matching
   the strategy doc's recommended order).
2. **Given** the Brief has unsaved edits, **When** the tab bar is rendered,
   **Then** the Brief tab shows a visual indicator (dot, "•", or "Unsaved"
   chip) so the user knows they have uncommitted changes.
3. **Given** the user attempts to close the workspace with unsaved Brief edits,
   **When** they confirm the navigation, **Then** the unsaved edits are
   discarded silently (Phase 3 does not require a confirm dialog; draft
   persistence is a future enhancement).
4. **Given** a generation job has completed for the currently-loaded brief,
   **When** the Brief tab is viewed, **Then** a "Last submitted / Last
   generated" timestamp is shown at the top of the form.

---

### Edge Cases

- **Song has no `_analysis.json` yet**: The Brief tab is disabled with a
  tooltip directing the user to run analysis first (Analysis tab). The Brief
  cannot be edited or submitted until an analysis exists, because section
  overrides need a section list.
- **Song has analysis but no sections detected** (very short clip): The
  per-section overrides panel shows a single "whole song" pseudo-row labelled
  "(no sections detected)". All other controls work normally.
- **Layout not configured**: The Generate button within the Brief is disabled
  with the same "configure layout first" affordance used elsewhere in the
  workspace. Editing and persisting the Brief is still allowed — only generation
  is blocked.
- **User has never set genre via ID3**: Genre control defaults to "Auto", which
  resolves server-side to "pop" (matching today's default). No blocking.
- **Custom theme slug referenced by an override is deleted**: Section row
  displays "Auto" and a small warning chip; the persisted override for that
  section is cleared on the next submit.
- **Brief payload exceeds endpoint validation** (invalid enum values): The
  server returns a field-level error and the UI renders it inline beside the
  offending control. No partial job is created.
- **Two browser tabs editing the same song's Brief**: Last submit wins. The
  Brief does not attempt optimistic concurrency control in Phase 3. A reload
  after submit will show the winning values.
- **Per-axis `curves_mode="all"` is selected but `curves_mode` is disabled
  elsewhere**: Resolution order is Brief > story-preferences > code default.
  Brief is authoritative.
- **ID3 tag parsing fails or returns unknown genre**: Genre preset shows "Auto"
  with the raw ID3 string (if any) visible as a ghost hint. Submit sends
  genre="pop" (Auto-resolved).
- **User selects a preset that maps to a combination the generator later
  rejects at placement time**: Phase 3 treats this as an "Auto fallback at
  render" — the brief is valid at submit, but a warning appears in the
  generation log. Phase 4 will close this gap by validating presets against
  section data up-front.

---

## Requirements

### Functional Requirements

#### Brief tab surface

- **FR-001**: The per-song workspace (spec 046) MUST include a tab named
  "Brief" positioned between "Analysis" and "Generate".
- **FR-002**: The Brief tab MUST render as a single scrollable form. Multi-step
  wizards are explicitly out of scope.
- **FR-003**: Every control MUST show a human-readable label, a named-preset
  selector as its primary input, and a one-line hint explaining the observable
  effect.
- **FR-004**: Every axis control MUST offer "Auto" as a selectable preset.
  "Auto" means "use the library default for this song", matching today's
  implicit behavior when the field is left unset.
- **FR-005**: Every control backed by one or more raw config fields MUST offer
  an "Advanced" disclosure that exposes those raw fields. The disclosure is
  closed by default.

#### Controls (every `GenerationConfig` creative field has a home)

- **FR-010 — Genre**: A preset selector populated from the existing `_VALID_GENRES`
  set (`any`, `pop`, `rock`, `classical`) plus "Auto". Pre-filled from ID3 on
  first load. Maps to `GenerationConfig.genre`.
- **FR-011 — Occasion**: A preset selector with options `General`, `Christmas`,
  `Halloween`, plus "Auto". Maps to `GenerationConfig.occasion`.
- **FR-012 — Mood intent**: A preset selector with options `Party`,
  `Emotional`, `Dramatic`, `Playful`, `Auto`. This is a new creative axis that
  influences downstream defaults (theme family preference, accent intensity
  default, transition mode default). Phase 3 persists the mood choice; Phase 4
  wires it to its downstream effects. In Phase 3, mood=Auto is equivalent to
  today's behavior and mood=other presets set recommended defaults on the
  other controls if they are also on "Auto" (no override if the user has
  explicitly set them).
- **FR-013 — Variation style**: A preset selector with options `Focused`,
  `Balanced`, `Varied`, `Auto`. Advanced exposes `focused_vocabulary` and
  `embrace_repetition` as separate booleans. Preset mapping:
  Focused → `focused_vocabulary=True, embrace_repetition=True`;
  Balanced → `focused_vocabulary=True, embrace_repetition=False`;
  Varied → `focused_vocabulary=False, embrace_repetition=False`;
  Auto → library default.
- **FR-014 — Color palette**: A preset selector with options `Restrained`,
  `Balanced`, `Full`, `Auto`. Advanced exposes `palette_restraint` as a
  boolean. Preset mapping: Restrained → `palette_restraint=True`;
  Full → `palette_restraint=False`; Balanced → Auto equivalent for Phase 3.
- **FR-015 — Effect duration**: A preset selector with options `Snappy`,
  `Balanced`, `Flowing`, `Auto`. Advanced exposes `duration_scaling` as a
  boolean. Preset mapping: Snappy/Flowing → `duration_scaling=True` with a
  downstream hint passed to the plan (Phase 3 may persist a nominal
  `duration_feel` string alongside; Phase 4 wires it to the scaler);
  Balanced/Auto → `duration_scaling=True` with default scaling.
- **FR-016 — Accent intensity**: A preset selector with options `None`,
  `Subtle`, `Strong`, `Auto`. Advanced exposes `beat_accent_effects` as a
  boolean. Preset mapping: None → `beat_accent_effects=False`;
  Subtle/Strong → `beat_accent_effects=True` (strength persisted as a nominal
  field for Phase 4 to consume); Auto → library default (`True`).
- **FR-017 — Transitions**: A preset selector with options `None`, `Subtle`,
  `Dramatic`, `Auto`. Maps directly to `GenerationConfig.transition_mode`
  (`none`, `subtle`, `dramatic`).
- **FR-018 — Value curves**: A preset selector with options `On`, `Off`,
  `Auto`. Advanced exposes `curves_mode` as a 5-way selector matching the
  existing `_VALID_CURVES_MODES` (`all`, `brightness`, `speed`, `color`,
  `none`). Preset mapping: On → `all`; Off → `none`; Auto → library default.
- **FR-019 — Tier selection**: An Advanced-only control (not a top-level
  preset axis). Exposes `tier_selection` as a boolean inside the Variation
  Advanced disclosure, since tier selection interacts conceptually with
  variation. Default: Auto (library default `True`).
- **FR-020 — Per-section theme overrides**: A compact table with one row per
  detected section. Each row shows section index, label, time range, energy
  score, and a theme selector defaulting to "Auto". Non-Auto selections
  serialize to `GenerationConfig.theme_overrides` as `{int: theme_slug}`.
- **FR-021 — Target sections / tiers**: NOT surfaced in the Brief. These are
  debugging/CLI fields and remain CLI-only. The Brief form does not set them
  (they default to None in the submitted config).

#### Persistence

- **FR-030**: Submitting the Brief MUST persist it to disk, keyed by the song's
  source hash, before the generation job ID is returned to the client.
  Storage location: a per-song JSON file. Concrete path SHOULD live alongside
  the existing analysis artifacts (e.g. `<audio_stem>_brief.json`) unless
  Phase 4 dictates otherwise; the exact location is an implementation detail
  as long as it is keyed by source hash and survives server restarts.
- **FR-031**: Opening the Brief tab MUST load the persisted brief for the song
  if it exists, else fall back to library defaults merged with ID3-derived
  genre/occasion.
- **FR-032**: The persisted brief MUST be JSON-serializable and MUST include
  every control value shown in the UI, including "Auto" selections (so that
  re-opening the form shows "Auto" explicitly rather than inferring it).
- **FR-033**: An explicit "Reset to Auto" action on the Brief MUST reset every
  control to "Auto" in the UI. The persisted file is only rewritten on the
  next submit; reset alone does not delete the file.
- **FR-034**: The persisted brief MUST be schema-versioned (an integer
  `brief_schema_version` field) so future schema changes can migrate or
  discard older briefs without data corruption.

#### Generation wiring

- **FR-040**: Clicking Generate on the Brief tab MUST (a) persist the brief,
  (b) POST the brief to the existing `/generate/<source_hash>` endpoint in
  `src/review/generate_routes.py`, (c) switch the workspace to the Generate
  tab to display job progress.
- **FR-041**: Every field in the Brief MUST reach `GenerationConfig` on the
  server side via the **POST request body**. The `/generate/<hash>` endpoint
  MUST be extended to accept every Brief field (including `genre`,
  `occasion`, and `transition_mode`, which today are read from
  `_story_reviewed.json`). After this spec, generation MUST NOT fall back to
  reading these three fields from the story-preferences file when they are
  present in the body. `/story-review` continues to write its own preferences
  file for its own UI, but generation no longer depends on it. The Brief
  JSON is the single source of truth the Brief writes to.
- **FR-042**: Validation errors from the server MUST be surfaced inline in
  the Brief tab beside the offending control, not as a top-level banner.
- **FR-043**: Submitting an all-"Auto" Brief MUST produce an effective
  `GenerationConfig` identical to today's dashboard Generate flow for the
  same song (regression safety — no new defaults snuck in via the Brief).
- **FR-044**: Each successful generation job record MUST include a snapshot
  of the brief that produced it, keyed alongside the existing job metadata
  (`job_id`, `source_hash`, `status`, `created_at`). Rendering the snapshot
  in the UI is NOT required in Phase 3.

#### Accessibility and polish

- **FR-050**: All preset selectors MUST be keyboard-navigable (Tab to focus,
  arrow keys or Enter to select).
- **FR-051**: Hint text MUST be part of the rendered DOM, not a tooltip-only
  affordance, so it is visible on scan.
- **FR-052**: The Brief tab MUST not make network requests other than (a) the
  initial GET to load the persisted brief, (b) a GET for the theme catalog,
  (c) the POST on Generate. No per-keystroke autosave in Phase 3.

### Key Entities

- **Brief**: The JSON document persisted per song. Fields:
  `brief_schema_version: int`, `source_hash: str`, `updated_at: iso8601`,
  one field per Brief control. Every control value is stored as a string
  preset identifier (including the literal "auto") OR as the underlying
  raw config value when the user has used the Advanced disclosure.
- **BriefPresetMap**: A server-side or client-side mapping from preset
  identifiers (e.g. "Focused", "Snappy") to the raw `GenerationConfig`
  field values the preset expands to. Lives next to `GenerationConfig`
  so Phase 4 can consume it cleanly.
- **PerSectionOverride**: One row in the overrides table. Fields:
  `section_index: int`, `theme_slug: str | "auto"`. Serializes to the
  existing `GenerationConfig.theme_overrides` dict on submit (Auto rows
  omitted).
- **GenerationJob** (existing in `generate_routes.py`): Extended to carry
  a `brief_snapshot` field alongside the existing genre/occasion/transition
  fields. No breaking change to the status or download endpoints.

---

## Success Criteria

- **SC-001**: Every one of the twelve creative `GenerationConfig` fields
  surveyed in the strategy doc (`genre`, `occasion`, `transition_mode`,
  `curves_mode`, `focused_vocabulary`, `embrace_repetition`,
  `palette_restraint`, `duration_scaling`, `beat_accent_effects`,
  `tier_selection`, `theme_overrides`, plus the new `mood_intent` axis) has
  a named control on the Brief tab. Zero fields are invisible.
- **SC-002**: An all-"Auto" Brief submit produces a sequence byte-identical
  (modulo timestamps) to today's dashboard Generate flow on the same song.
- **SC-003**: A Brief with at least three non-Auto choices (e.g.
  mood=Dramatic, variation=Varied, palette=Restrained) produces a sequence
  whose plan JSON reflects each choice in the expected config field. Verified
  by unit/integration test on a fixture song.
- **SC-004**: Re-opening the Brief after a browser restart restores every
  previously submitted control value within 500ms of tab activation.
- **SC-005**: A first-time user can open the Brief tab, scan the form, and
  press Generate without hovering any control, because every hint and preset
  label is statically visible.
- **SC-006**: After this feature ships, zero functional paths require the
  user to visit `/story-review` in order to generate a sequence. (The page
  still exists for deep-dive timeline work; it is no longer on the happy
  path.)
- **SC-007**: Existing `/generate/<source_hash>` contract tests continue to
  pass. If the endpoint is extended to accept additional POST body fields,
  those fields are additive and optional — the old contract remains valid.
- **SC-008**: Persisted brief files on disk round-trip through
  JSON deserialize → `GenerationConfig` construct → serialize without loss.
- **SC-009**: The Brief tab loads (first paint with all controls populated)
  within 300ms on a song with 30 sections, measured on a developer laptop.

## Key Files

- `specs/046-song-workspace/spec.md` — Phase 2 workspace shell (prerequisite).
- `specs/048-pipeline-decision-ordering/spec.md` — Phase 4 backend refactor
  (follow-up, not a prerequisite).
- `src/generator/models.py` — `GenerationConfig` (no new fields strictly
  required for Phase 3; may add a nominal `mood_intent: str = "auto"` field
  and nominal strength/feel strings if preferred over stashing them in the
  persisted brief only).
- `src/review/generate_routes.py` — POST endpoint that accepts the Brief;
  may be extended to read additional Brief fields from the request body.
- `src/review/static/song-workspace/*` — Brief tab UI lives here (exact
  file layout follows spec 046's conventions).
- `src/review/brief_routes.py` — NEW Flask blueprint for the per-song
  Brief GET/PUT endpoints (load, persist).
- `src/review/static/story-review.html` — unchanged by this spec; the
  per-section theme override UI is duplicated (not migrated) into the
  Brief tab. De-duplication is a Phase 4 concern.
- `tests/unit/test_brief_persistence.py` — Brief schema round-trip,
  preset → raw config mapping, per-section override serialization.
- `tests/integration/test_brief_generation.py` — end-to-end: edit Brief,
  submit, verify resulting sequence reflects submitted choices.
