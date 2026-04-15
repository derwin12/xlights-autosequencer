# Phase 0 Research: Creative Brief

**Feature**: 047-creative-brief | **Date**: 2026-04-14

This document records the design research needed before implementation. Three topics:
the Preset → raw-config mapping table (the heart of the UI), the Mood Intent
smart-default ruleset (Phase 3's only new axis), and a concrete comparison of the
existing vs. extended `/generate/<source_hash>` endpoint behavior.

---

## 1. Preset → Raw Config Mapping

Every axis on the Brief tab is a named preset selector first and an Advanced
disclosure over raw `GenerationConfig` fields second. The mapping below is
authoritative — it lives in `brief-presets.js` as `BRIEF_PRESETS` and is the input
to `brief-tab.js`'s submit handler when converting the Brief to a POST body.

| Axis (UI label) | Preset options | Raw field(s) (`GenerationConfig`) | Preset → raw value |
|-----------------|----------------|-----------------------------------|---------------------|
| **Genre** | `Auto`, `Pop`, `Rock`, `Classical`, `Any` | `genre: str` | Auto → omit (defaults to `"pop"`); others → lowercased preset id |
| **Occasion** | `Auto`, `General`, `Christmas`, `Halloween` | `occasion: str` | Auto → omit (defaults to `"general"`); others → lowercased preset id |
| **Mood intent** | `Auto`, `Party`, `Emotional`, `Dramatic`, `Playful` | `mood_intent: str` (new nominal field) | Auto → `"auto"`; others → lowercased preset id. See §2 for client-side sibling effects. |
| **Variation style** | `Auto`, `Focused`, `Balanced`, `Varied` | `focused_vocabulary: bool`, `embrace_repetition: bool`, `tier_selection: bool` (Advanced) | Auto → omit all (library defaults); Focused → `(True, True, True)`; Balanced → `(True, False, True)`; Varied → `(False, False, True)` |
| **Color palette** | `Auto`, `Restrained`, `Balanced`, `Full` | `palette_restraint: bool` | Auto → omit; Restrained → `True`; Balanced → Auto-equivalent (Phase 3); Full → `False` |
| **Effect duration** | `Auto`, `Snappy`, `Balanced`, `Flowing` | `duration_scaling: bool`, `duration_feel: str` (new nominal) | Auto → omit; Snappy → `(True, "snappy")`; Balanced → `(True, "balanced")`; Flowing → `(True, "flowing")` |
| **Accent intensity** | `Auto`, `None`, `Subtle`, `Strong` | `beat_accent_effects: bool`, `accent_strength: str` (new nominal) | Auto → omit; None → `(False, "auto")`; Subtle → `(True, "subtle")`; Strong → `(True, "strong")` |
| **Transitions** | `Auto`, `None`, `Subtle`, `Dramatic` | `transition_mode: str` | Auto → omit (default `"subtle"`); others → lowercased preset id |
| **Value curves** | `Auto`, `On`, `Off` | `curves_mode: str` (Advanced = 5-way) | Auto → omit; On → `"all"`; Off → `"none"` |
| **Per-section overrides** | One row per detected section | `theme_overrides: dict[int, str]` | Auto rows omitted; non-Auto rows → `{section_index: theme_slug}` |

**Fields never surfaced**: `audio_path`, `layout_path`, `output_dir`, `story_path`,
`force_reanalyze`, `target_sections`, `tiers`. These are CLI/infrastructure concerns
(FR-021).

**Advanced disclosures** show the raw field(s) as checkboxes / enum selectors with
the preset-derived values prefilled. If the user edits a raw value away from every
named preset's mapping, the preset selector switches to a "Custom" label (FR
US2 AC-5).

### One-line hints per axis (FR-003, US6)

- Genre — "Shapes which palettes and effect families get selected."
- Occasion — "Seasonal palette bias (Christmas reds/greens, Halloween oranges, etc.)."
- Mood intent — "The overall feeling you want — recommends defaults for other controls."
- Variation style — "Whether every section cycles through similar effects (Focused) or new ones (Varied)."
- Color palette — "How many colors are on-screen at once. Restrained reads as cleaner; Full reads as busier."
- Effect duration — "How long each effect lingers — Snappy cuts on beats, Flowing crossfades over bars."
- Accent intensity — "Beat-synchronized bursts on drum hits. None disables them; Strong turns them up."
- Transitions — "How sections blend at boundaries. None is abrupt; Dramatic uses strobes and flashes."
- Value curves — "Let effect parameters (brightness, speed) animate over time instead of staying constant."

---

## 2. Mood Intent Smart-Default Ruleset (client-side, Phase 3)

Per the 2026-04-14 clarification, Mood Intent is persisted in Phase 3 and drives
smart Auto-defaults on sibling controls that are **still** on "Auto". Explicit
non-Auto picks are never overridden. The ruleset lives in `brief-tab.js` as
`MOOD_DEFAULTS` so Phase 4 can delete it when the generator reads mood directly.

| Mood      | Transitions (if Auto) | Accent intensity (if Auto) | Variation (if Auto) | Palette (if Auto) | Duration (if Auto) |
|-----------|-----------------------|-----------------------------|---------------------|-------------------|--------------------|
| Party     | Dramatic              | Strong                      | Varied              | Full              | Snappy             |
| Emotional | Subtle                | Subtle                      | Focused             | Restrained        | Flowing            |
| Dramatic  | Dramatic              | Strong                      | Focused             | Restrained        | Flowing            |
| Playful   | Subtle                | Subtle                      | Varied              | Full              | Snappy             |
| Auto      | (no effect)           | (no effect)                 | (no effect)         | (no effect)       | (no effect)        |

Behavior when mood changes:
1. For each sibling axis, check if its current value is `"Auto"`.
2. If yes, apply the recommended default from the row above and mark it as
   "implicitly set by mood" (visual hint: small "via Mood" chip).
3. If the user later changes mood back to Auto, sibling axes that were implicitly
   set revert to Auto as well. Siblings the user explicitly touched stay put.
4. Changing mood from one non-Auto value to another re-applies the new row's
   defaults to siblings still on "Auto" or "via Mood"; explicit picks are untouched.

This is entirely client-side state. The POST body sent to the server contains the
final resolved values, not the "via Mood" provenance — Phase 4 will make the
server mood-aware and replace this whole mechanism.

---

## 3. `/generate/<source_hash>` — Existing vs. Extended Behavior

### Existing (pre-047)

```
POST /generate/<source_hash>
  body: (ignored — dashboard sends {})
  server:
    1. look up song in Library
    2. check analysis exists, layout configured
    3. compute _story_reviewed.json path from audio filename
    4. call _load_prefs_from_story(story_path) → (genre, occasion, transition_mode)
    5. validate those three fields against hardcoded enums
    6. build GenerationConfig with defaults for every other field
    7. spawn background thread, return 202 {job_id}
```

Notable properties:
- POST body is ignored. No way for a caller to request `palette_restraint=True`.
- `genre`, `occasion`, `transition_mode` come from `/story-review`'s prefs file.
- Every other creative field uses its `GenerationConfig` default.

### Extended (post-047)

```
POST /generate/<source_hash>
  body: {genre, occasion, transition_mode, curves_mode, focused_vocabulary,
         embrace_repetition, palette_restraint, duration_scaling,
         beat_accent_effects, tier_selection, theme_overrides,
         mood_intent, duration_feel, accent_strength}  — ALL optional
  server:
    1. look up song, check analysis + layout as before
    2. parse body = request.get_json(silent=True) or {}
    3. for each known Brief field:
         value = body.get(field)
         if value is None:
             value = persisted Brief JSON on disk (if exists)
         if value is None and field in {genre, occasion, transition_mode}:
             value = _load_prefs_from_story(story_path)  # legacy last-resort
         if value is None:
             value = GenerationConfig default
    4. validate via existing _VALID_* sets + GenerationConfig.__post_init__
       — on failure, return 400 {field, error}
    5. build GenerationConfig with all resolved values
    6. record brief_snapshot on the GenerationJob
    7. spawn background thread, return 202 {job_id}
```

Notable changes:
- Body is parsed and takes precedence over everything else.
- On-disk Brief JSON (written by the new `brief_routes.py`) is the second
  source; this covers the case where a CLI user seeded a Brief but is POSTing
  without a body.
- `_load_prefs_from_story` is still called, but only as a last-resort fallback
  for the three legacy fields when neither the body nor the on-disk Brief has
  them. This preserves behavior for songs that predate the Brief tab.
- `GenerationJob` gains `brief_snapshot: Optional[dict]` (FR-044).
- All-absent body produces the same `GenerationConfig` as today's flow (SC-002,
  SC-007).

### Why not just replace story-prefs entirely?

Several songs in the library already have `_story_reviewed.json` files written by
the existing story-review UI. Deleting the fallback would silently change the
generator's output for any song that was briefed in the old way but has not yet
been briefed in the new Brief tab. Keeping the fallback as a last-resort
(value-is-still-None) check preserves determinism through the transition. Phase 4
removes the fallback entirely once all songs have been migrated to Brief JSON.

---

## 4. Brief Persistence Location

Decision: per-song JSON file at `<audio_path.parent>/<audio_path.stem>_brief.json`.

Alternatives considered:
- **Inside `~/.xlight/library.json`**: rejected — library index is a catalog, not a
  per-song store; colocating transient creative choices with catalog metadata
  bloats the index and complicates concurrent writes.
- **In a new `~/.xlight/briefs/<hash>.json`**: rejected — separates the Brief from
  the audio file, making it easy to lose when a song is moved or re-imported.
  `_analysis.json`, `_story.json`, `_story_reviewed.json` are all keyed to the
  audio file's directory; Brief follows the same pattern for consistency.
- **Inside the job record**: rejected — job records are transient (`_jobs` dict)
  and don't survive server restart. Persistence is mandatory (FR-030).

The audio-adjacent JSON file is consistent with every other per-song artifact and
survives server restarts without extra bookkeeping.

---

## 5. Schema Versioning Strategy

`brief_schema_version: int = 1`. On load:
- Version matches → parse.
- Version is older → attempt forward migration in `brief_routes.py`; if no
  migration is registered, return defaults and log a warning. Don't delete the
  file automatically.
- Version is newer → refuse to load (return defaults), surface a warning in the
  UI, let the user decide whether to overwrite by submitting the current form.

This is the minimum viable migration story — we do not implement an actual
migration registry in Phase 3, we just leave the hook.
