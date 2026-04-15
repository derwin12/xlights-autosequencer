# Phase 1 Data Model: Creative Brief

**Feature**: 047-creative-brief | **Date**: 2026-04-14

This document defines the Brief JSON schema (persisted per song), the
per-section override row shape, and the `GenerationJob` snapshot extension.

---

## Brief JSON (schema version 1)

**File**: `<audio_path.parent>/<audio_path.stem>_brief.json`
**Keyed by**: `source_hash` (also duplicated into the file for integrity checks).

```jsonc
{
  "brief_schema_version": 1,
  "source_hash": "a1b2c3…",               // MD5 of source audio; must match library entry
  "updated_at": "2026-04-14T12:34:56Z",   // ISO8601 UTC, set by the server on PUT

  // Axis selections. Every field is a preset id (lowercased) OR "auto".
  // A value of "auto" means "omit from POST body / use library default".
  "genre":           "auto" | "pop" | "rock" | "classical" | "any",
  "occasion":        "auto" | "general" | "christmas" | "halloween",
  "mood_intent":     "auto" | "party" | "emotional" | "dramatic" | "playful",
  "variation":       "auto" | "focused" | "balanced" | "varied",
  "palette":         "auto" | "restrained" | "balanced" | "full",
  "duration":        "auto" | "snappy" | "balanced" | "flowing",
  "accents":         "auto" | "none" | "subtle" | "strong",
  "transitions":     "auto" | "none" | "subtle" | "dramatic",
  "curves":          "auto" | "on" | "off",

  // Advanced raw-field overrides. Present only when the user has opened an
  // Advanced disclosure and diverged from the preset mapping. When present,
  // these take precedence over the axis preset on submit and the preset
  // selector shows "Custom".
  "advanced": {
    "focused_vocabulary": true | false,
    "embrace_repetition": true | false,
    "tier_selection":     true | false,
    "palette_restraint":  true | false,
    "duration_scaling":   true | false,
    "beat_accent_effects": true | false,
    "curves_mode":        "all" | "brightness" | "speed" | "color" | "none"
  },

  // Per-section overrides. One entry per section the user has changed away
  // from Auto. Auto sections are OMITTED, not sent as null.
  "per_section_overrides": [
    { "section_index": 2, "theme_slug": "witching-hour" },
    { "section_index": 5, "theme_slug": "arctic-sunrise" }
  ]
}
```

### Field contracts

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `brief_schema_version` | `int` | `1` | Must equal current schema version on load; mismatches handled per §5 of research.md |
| `source_hash` | `str` | required | Must match URL hash and library entry |
| `updated_at` | `str` (ISO8601) | server-set | Not user-editable; set on PUT |
| `genre` | `str` | `"auto"` | Must be in `{"auto","any","pop","rock","classical"}` |
| `occasion` | `str` | `"auto"` | Must be in `{"auto","general","christmas","halloween"}` |
| `mood_intent` | `str` | `"auto"` | Must be in `{"auto","party","emotional","dramatic","playful"}` |
| `variation` | `str` | `"auto"` | Must be in `{"auto","focused","balanced","varied"}` |
| `palette` | `str` | `"auto"` | Must be in `{"auto","restrained","balanced","full"}` |
| `duration` | `str` | `"auto"` | Must be in `{"auto","snappy","balanced","flowing"}` |
| `accents` | `str` | `"auto"` | Must be in `{"auto","none","subtle","strong"}` |
| `transitions` | `str` | `"auto"` | Must be in `{"auto","none","subtle","dramatic"}` |
| `curves` | `str` | `"auto"` | Must be in `{"auto","on","off"}` |
| `advanced` | `object` | `{}` | Each subkey optional; values validated against `GenerationConfig._VALID_*` and types |
| `per_section_overrides` | `list[PerSectionOverride]` | `[]` | Deduped by `section_index`; theme slug must exist in catalog at submit time |

Every field is **optional** for JSON parse purposes — missing fields are
interpreted as `"auto"` (or `{}` / `[]`). This makes the schema additive and
makes forward migration trivial: a Brief JSON written before a new axis existed
simply loads with that axis set to Auto.

---

## PerSectionOverride row shape

```jsonc
{
  "section_index": 2,            // 0-based index into the song's section list
  "theme_slug": "witching-hour"  // must exist in the theme catalog at submit;
                                 // a stale slug renders as "Auto" with a warning
}
```

Serialized to `GenerationConfig.theme_overrides` on submit as:

```python
{ row.section_index: row.theme_slug for row in per_section_overrides }
```

Auto rows are never written — they are represented by their absence from the
list. This matches the existing `theme_overrides: Optional[dict[int, str]]`
contract in `GenerationConfig` (an omitted section means "use the auto-assigned
theme").

---

## `GenerationJob` extension (in `generate_routes.py`)

Existing dataclass gains one field:

```python
@dataclass
class GenerationJob:
    job_id: str
    source_hash: str
    status: str
    output_path: Optional[Path]
    error_message: Optional[str]
    genre: str
    occasion: str
    transition_mode: str
    created_at: float
    brief_snapshot: Optional[dict] = None   # NEW — full Brief JSON at submit time
```

The snapshot is the exact JSON body submitted to `PUT /brief/<hash>` just before
the POST to `/generate/<hash>`. It is not rendered in Phase 3 (FR-044 explicitly
defers UI rendering), but is available on `GET /generate/<hash>/history` for
future "compare renders" functionality.

---

## Nominal `GenerationConfig` field additions (Phase C)

Three new dataclass fields, all defaulting to `"auto"`, all validated in
`__post_init__`:

```python
mood_intent: str = "auto"       # "auto", "party", "emotional", "dramatic", "playful"
duration_feel: str = "auto"     # "auto", "snappy", "balanced", "flowing"
accent_strength: str = "auto"   # "auto", "subtle", "strong"
```

Validation added alongside existing `_VALID_CURVES_MODES`:

```python
_VALID_MOOD_INTENTS   = frozenset({"auto", "party", "emotional", "dramatic", "playful"})
_VALID_DURATION_FEELS = frozenset({"auto", "snappy", "balanced", "flowing"})
_VALID_ACCENT_STRENGTHS = frozenset({"auto", "subtle", "strong"})
```

These fields are **stored but not read** by the generator in Phase 3 — they
exist so the Brief round-trips through `GenerationConfig` without loss (SC-008)
and so Phase 4 can switch to reading them without a schema migration.

---

## Auto representation — why strings, not nulls

Every axis uses the literal string `"auto"` rather than `null` / missing. Reasons:
1. The UI needs to show "Auto" as a first-class preset selection, not a "value
   absent" state. Serializing it as a real string makes the round-trip trivial.
2. The POST-to-generate resolver can check `value == "auto"` consistently and
   fall through to the next source (on-disk Brief, story-prefs, default). `null`
   would require a tri-state (missing vs. null vs. present) that adds no value.
3. Schema evolution is additive — adding a new axis means defaulting its string
   to `"auto"` in old files, which falls through to Auto behavior without code
   changes.

The **submitted POST body** on Generate, however, **omits** fields that resolve
to Auto (matching US2 AC-2 which says "omit or send default" is acceptable). The
Brief JSON is the full self-describing document; the POST body is a sparse
override envelope.
