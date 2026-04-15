# Implementation Plan: Creative Brief (Per-Song Workspace, Phase 3)

**Branch**: `047-creative-brief` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/047-creative-brief/spec.md`

## Summary

Today every creative knob on `GenerationConfig` has a default and no UI. Thirteen fields
exist (`genre`, `occasion`, `transition_mode`, `curves_mode`, `focused_vocabulary`,
`embrace_repetition`, `palette_restraint`, `duration_scaling`, `beat_accent_effects`,
`tier_selection`, `theme_overrides`, `target_sections`, `tiers`); three of them
(`genre`, `occasion`, `transition_mode`) are surfaced only on `/story-review`, and the
rest are invisible. The Generate action on the dashboard submits an empty POST body and
the server recovers `genre`/`occasion`/`transition_mode` by reading
`<audio_stem>_story_reviewed.json` from disk.

Phase 3 replaces that scatter with a single Brief tab in the per-song workspace from
spec 046. The tab is one scrollable form where every creative decision has a named
home, "Auto" is always valid, Advanced disclosures expose the raw flags, a per-section
theme override table is embedded, and a single Generate button persists the brief and
kicks off generation with every choice on the wire.

Mood Intent is introduced as a new axis. In Phase 3 it is persisted on the Brief JSON
and (client-side only) drives smart "Auto" defaults on sibling controls — the
generator itself does not read it yet. Direct generator wiring lands in Phase 4 (spec
048); the Phase 3 client-side ruleset is deliberately easy to delete when that happens.

The POST-body plumbing is the most invasive backend change. `/generate/<source_hash>`
is extended to accept every Brief field in the request body and MUST stop consulting
`_story_reviewed.json` for `genre`, `occasion`, or `transition_mode` when the body
carries them. `/story-review` continues to write its own preferences file for its own
UI, but generation no longer depends on it. A new `brief_routes.py` blueprint handles
per-song GET/PUT of the Brief JSON.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend)
**Primary Dependencies**: Flask 3+ (existing), existing `src/generator/plan.py`; no new deps
**Storage**: Per-song `<audio_stem>_brief.json` keyed by `source_hash`, alongside the existing `_analysis.json` artifacts
**Testing**: pytest (Python), manual smoke of the Brief tab via `quickstart.md`
**Target Platform**: Linux devcontainer / macOS host, served by the existing review server
**Project Type**: Web UI (per-song workspace tab) + Flask blueprint + POST endpoint extension
**Performance Goals**: Brief tab first paint < 300ms on a 30-section song; persistence GET/PUT < 50ms local
**Constraints**: An all-"Auto" Brief submit must produce the same effective `GenerationConfig` as today's dashboard Generate flow (no new implicit defaults)
**Scale/Scope**: Single new blueprint (~120 lines), ~350 lines of new JS in the workspace shell, one POST-endpoint extension (~80 lines); ≈9 axis controls + per-section table

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | No change to analysis; Brief only reshapes how creative choices reach the generator |
| II. xLights Compatibility | PASS | Output format unchanged; Brief drives the same `GenerationConfig` that already produces valid `.xsq` |
| III. Modular Pipeline | PASS | New blueprint is a sibling of existing ones; POST-body extension is additive and optional |
| IV. Test-First Development | PASS | Schema round-trip and per-section override serialization tests written before implementation; POST body contract test extended first |
| V. Simplicity First | PASS | No new abstractions server-side; preset → raw-config mapping table is declarative JSON; mood smart-defaults live in JS only so Phase 4 can replace them cleanly |

No violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/047-creative-brief/
├── plan.md              # This file
├── research.md          # Phase 0 output — preset mappings, mood ruleset, endpoint comparison
├── data-model.md        # Phase 1 output — Brief JSON schema, PerSectionOverride shape
├── quickstart.md        # Phase 1 output — manual verification walkthrough
└── tasks.md             # Phase 2 output (created later by /speckit.tasks)
```

### Source Code (affected files)

```text
src/
├── generator/
│   └── models.py                          # Add nominal mood_intent/duration_feel/accent_strength fields (optional, per FR-012)
├── review/
│   ├── brief_routes.py                    # NEW — Flask blueprint: GET/PUT /brief/<source_hash>
│   ├── generate_routes.py                 # Extend POST /generate/<hash> to accept Brief body; stop reading genre/occasion/transition_mode from _story_reviewed.json when body has them
│   ├── server.py                          # Register brief_bp
│   └── static/
│       ├── song-workspace/                # (from spec 046)
│       │   ├── brief-tab.html             # NEW — Brief form fragment (loaded by the workspace shell)
│       │   ├── brief-tab.js               # NEW — load/persist/submit; preset → raw mapping; mood smart-defaults
│       │   ├── brief-presets.js           # NEW — BriefPresetMap (preset id → raw config values)
│       │   └── brief-tab.css              # NEW — form styling, hint layout, override table
│       └── story-review.html / .js        # UNCHANGED — continues to write its own prefs file

tests/
├── unit/
│   ├── test_brief_persistence.py          # NEW — schema round-trip, version, preset mapping
│   └── test_brief_routes.py               # NEW — GET/PUT contract
└── integration/
    └── test_brief_generation.py           # NEW — edit Brief, submit, verify plan reflects choices
```

**Structure Decision**: New `brief_routes.py` blueprint for persistence; existing
`generate_routes.py` extended (not replaced); new JS modules slot into the spec-046
workspace shell without touching the other tabs.

## Implementation Approach

### Phase A — Brief JSON shape and persistence (server)

1. Create `src/review/brief_routes.py` with a single `brief_bp` blueprint:
   - `GET /brief/<source_hash>` → 200 with the persisted JSON, or 404 if absent.
   - `PUT /brief/<source_hash>` → validates schema version + field enums, writes
     `<audio_stem>_brief.json` atomically (temp file + rename). Returns the stored JSON.
2. File location: resolve via `Library().find_by_hash(source_hash).source_file`, then
   `audio_path.parent / f"{audio_path.stem}_brief.json"`. Matches the sibling
   `_analysis.json` / `_story_reviewed.json` pattern.
3. Schema: `brief_schema_version: int = 1`, `source_hash: str`, `updated_at: iso8601`,
   one key per control. See `data-model.md` for the full schema.
4. Validation on PUT: reject unknown genre/occasion/transition/curves values using
   existing `_VALID_*` sets from `generate_routes.py` and `GenerationConfig`. Schema
   version mismatches return 409 with an explicit migration message.
5. Register the blueprint in `src/review/server.py` at url prefix `/brief`.

### Phase B — Extend `/generate/<hash>` to read Brief from POST body

1. Parse `request.get_json(silent=True) or {}` at the top of `start_generation`.
2. Build `GenerationConfig` from the POST body first, falling back to Brief-JSON on disk,
   falling back to library defaults. Explicitly **stop** calling
   `_load_prefs_from_story` for `genre` / `occasion` / `transition_mode` when the body
   (or on-disk Brief) carries them. Keep the story-prefs fallback only as a last resort
   so songs that have never been briefed still generate.
3. New accepted POST keys (all optional): `genre`, `occasion`, `transition_mode`,
   `curves_mode`, `focused_vocabulary`, `embrace_repetition`, `palette_restraint`,
   `duration_scaling`, `beat_accent_effects`, `tier_selection`, `theme_overrides`,
   `mood_intent` (stored but not acted on in Phase 3). `target_sections` and `tiers`
   remain CLI-only (FR-021).
4. Validate each field against the existing enums / `GenerationConfig._VALID_CURVES_MODES`.
   Return 400 with `{field: <name>, error: <msg>}` for failures so the Brief tab can
   highlight the offending control (FR-042).
5. Record the full Brief snapshot on the `GenerationJob` dataclass (add
   `brief_snapshot: Optional[dict]` field) per FR-044. Status and download endpoints
   unchanged.

### Phase C — Optional nominal `GenerationConfig` fields (forward-compat)

Per FR-012 and the spec, add three nominal string fields to `GenerationConfig` so the
Brief can persist future-facing choices through the existing config path without losing
them on round-trip:

- `mood_intent: str = "auto"` (values: `auto`, `party`, `emotional`, `dramatic`, `playful`)
- `duration_feel: str = "auto"` (values: `auto`, `snappy`, `balanced`, `flowing`)
- `accent_strength: str = "auto"` (values: `auto`, `subtle`, `strong`)

These are stored but not read in Phase 3; Phase 4 wires them. Added to
`__post_init__` validation and to `_VALID_*` frozensets. This keeps the Brief JSON and
`GenerationConfig` symmetrical and round-trippable (SC-008).

### Phase D — Brief tab UI

1. **HTML** (`brief-tab.html`): one form, sections for each axis, each with:
   - `<label>` with human-readable name
   - `<div class="preset-group">` of radio buttons (3–5 options, one always "Auto")
   - `<p class="hint">` one-line effect description (FR-003, FR-051)
   - `<details class="advanced">` exposing raw flags (FR-005)
   The per-section override table is its own `<section>` with one `<tr>` per
   detected section (index / label / mm:ss–mm:ss / energy / theme selector).
   Bottom: "Reset to Auto" button + primary "Generate" button.

2. **Preset map** (`brief-presets.js`): exported const `BRIEF_PRESETS` — an object
   keyed by axis name, each axis having `{presets: [{id, label, hint, raw: {field: value, ...}}]}`.
   See `research.md` for the full table. Single JSON-like source of truth, easy for
   Phase 4 to import.

3. **Load/persist flow** (`brief-tab.js`):
   - On tab activation: `GET /brief/<hash>` — on 404, synthesize defaults from
     `GenerationConfig` library values + ID3-derived genre/occasion.
   - On any control change: mark the tab "Unsaved" (FR-052 — no autosave).
   - On Generate click:
     a. Resolve every preset to its raw config values via `BRIEF_PRESETS`.
     b. `PUT /brief/<hash>` with the full Brief JSON.
     c. `POST /generate/<hash>` with the raw config values as JSON body.
     d. On 202 response: switch the workspace to the Generate tab.
     e. On 400 validation error: highlight the offending control inline.

4. **Mood smart-default ruleset (client-only, Phase 3 scaffold)**:
   When the user picks a non-Auto mood, iterate sibling controls; for each
   one still on "Auto", apply the recommended default from the ruleset. An
   explicit non-Auto pick is never overridden. The ruleset lives in
   `brief-tab.js` in a single `MOOD_DEFAULTS` object — roughly:
   - `party` → accents=Strong, transitions=Dramatic, variation=Varied
   - `emotional` → accents=Subtle, transitions=Subtle, variation=Focused, palette=Restrained
   - `dramatic` → accents=Strong, transitions=Dramatic, palette=Restrained, duration=Flowing
   - `playful` → variation=Varied, accents=Subtle, palette=Full
   See `research.md` for the full table. Phase 4 (spec 048) replaces this ruleset with
   server-side mood-aware defaulting inside `build_plan`; the JS dict is designed to
   be deletable.

5. **Per-section override table**: populated from the song's `_analysis.json`
   section list. Each row's theme `<select>` is populated from
   `GET /themes` + `GET /variants`. Auto rows are omitted from the submitted
   `theme_overrides` dict (FR-020). Deleted / missing theme slugs show a warning
   chip; the override is cleared on the next submit (FR-033 edge case).

6. **Hints**: every axis has a static hint string (`hints` table in `research.md`).
   Preset-specific hints are deliberately out of scope for Phase 3 (FR-006 AC-3).

### Phase E — Deprecate story-prefs generation path (scoped)

Only the *generation* path changes:
- `generate_routes.py` stops calling `_load_prefs_from_story` for songs where the
  POST body or on-disk Brief supplies the values.
- `_load_prefs_from_story` remains in the file as a last-resort fallback for songs
  that have never been briefed AND did not send any POST body (preserving SC-007).
- `/story-review` is **not** touched. It continues to read/write its own
  `_story_reviewed.json` file for its own timeline UI. De-duping the two persistence
  surfaces is explicitly a Phase 4 concern.

### Phase F — Tests

- `test_brief_persistence.py`: create Brief dict → PUT → GET → assert equality; schema
  version 0 rejected; unknown genre rejected; preset-to-raw mapping round-trips through
  `GenerationConfig` without data loss (SC-008).
- `test_brief_routes.py`: 404 when no brief, 200 after PUT, 400 on invalid payload,
  validation error shape matches `{field, error}`.
- `test_brief_generation.py`: integration — seed a fixture analysis, PUT a brief with
  non-default mood/variation/palette/one override, POST /generate, assert the
  resulting plan JSON reflects `palette_restraint=True`, `focused_vocabulary=False`,
  and `theme_overrides[2] == <slug>`. All-Auto Brief vs no Brief produces identical
  effective config (SC-002).
- Extend the existing `/generate/<hash>` contract test to cover the new POST-body
  fields (SC-007).

## Dependency and Phase Ordering

- **Hard prerequisite**: spec 046 (per-song workspace shell). The Brief tab is a
  drop-in for the 046 Brief-tab stub; this spec does not create the shell.
- **Parallel / unblocked**: none — Phases A/B/C/D can be developed concurrently;
  D depends on A for the GET/PUT endpoints, B depends on C if the nominal fields
  ship together but can skip them entirely.
- **Follow-up (not a prerequisite)**: spec 048 (Phase 4 pipeline decision-ordering).
  After 048 ships:
  - Per-section overrides naturally simplify because they read off
    `SectionAssignment` rather than a raw `{int: str}` dict.
  - The client-side mood smart-default ruleset in `brief-tab.js` is deleted; the
    server's `build_plan` consumes `mood_intent` directly and applies defaults
    during plan construction.
  - The Brief tab UI itself does not change — this is the promise of Phase 3.

## Risks and Mitigations

- **Risk**: Extending `/generate` POST body breaks existing callers (dashboard). All
  new fields are optional and default to today's behavior (SC-007). Contract test
  covers the old shape.
- **Risk**: Mood smart-defaults feel magical when the user didn't ask for them.
  Mitigation: only apply to controls still on "Auto"; never override explicit picks;
  show a one-time "Defaults applied from Mood" toast the first time per session.
- **Risk**: Brief JSON and `_story_reviewed.json` diverge after user edits both.
  Mitigation: Brief is the authoritative surface for generation; `/story-review`'s
  writes no longer affect generation output. Phase 4 removes the redundancy.
- **Risk**: Custom theme slug in a persisted override is later deleted. Handled by
  FR-033 edge case — warning chip, cleared on next submit.
- **Risk**: Preset → raw mapping drifts from server validation. Mitigation: the
  `BRIEF_PRESETS` map produces only values already in the existing `_VALID_*` sets;
  the unit test round-trips the full map through `GenerationConfig.__init__`.

## Open Questions (deferred to Phase 4 unless noted)

- Should mood-intent also influence *theme family selection* in Phase 3? **No** —
  theme selection already runs through `theme_selector.py`; wiring mood there is a
  Phase 4 change. Phase 3's smart-defaults affect only sibling Auto controls.
- Should the Brief surface the four tier toggles? **No** — per FR-021, `tiers` and
  `target_sections` remain CLI-only.
- Should the Brief support draft autosave on blur? **No** (FR-052) — per-keystroke
  autosave is explicitly out of scope for Phase 3.
