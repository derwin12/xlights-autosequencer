# Data Model: Song Library Sequence Generation

**Feature**: 034-library-sequence-gen
**Date**: 2026-04-09

---

## Entities

### GenerationJob (in-memory, server-side)

Represents a single sequence generation run.

| Field | Type | Notes |
|-------|------|-------|
| `job_id` | `str` | UUID4, unique per run |
| `source_hash` | `str` | Links to LibraryEntry (song identity) |
| `status` | `str` | `"pending"` / `"running"` / `"complete"` / `"failed"` |
| `output_path` | `Path \| None` | Path to the generated `.xsq` file once complete |
| `error_message` | `str \| None` | Human-readable error if status is `"failed"` |
| `genre` | `str` | User-selected genre (e.g. `"pop"`, `"rock"`, `"any"`) |
| `occasion` | `str` | `"general"` / `"christmas"` / `"halloween"` |
| `transition_mode` | `str` | `"none"` / `"subtle"` / `"dramatic"` |
| `created_at` | `float` | `time.time()` epoch seconds |

**Storage**: Module-level dict `_jobs: dict[str, GenerationJob]` in `generate_routes.py`, keyed by `job_id`. Persists for the server process lifetime.

**State transitions**:
```
pending → running → complete
              ↓
           failed
```

---

### GenerationSettings (persisted, installation-wide)

Installation-wide configuration stored in `~/.xlight/settings.json`.

| Field | Type | Notes |
|-------|------|-------|
| `layout_path` | `str \| null` | Absolute path to the xLights layout XML (`xlights_rgbeffects.xml`) |

**Storage**: `~/.xlight/settings.json` — written when the user saves their grouper configuration. Read by the generate endpoint to find layout groups.

**Example**:
```json
{
  "layout_path": "/Users/alice/xLights/xlights_rgbeffects.xml"
}
```

---

### LibraryEntry (existing, referenced)

Existing entity from `src/library.py`. Relevant fields:

| Field | Type | Notes |
|-------|------|-------|
| `source_hash` | `str` | MD5 of the source audio file |
| `source_file` | `str` | Absolute path to the MP3 |
| `analysis_path` | `str` | Absolute path to the `*_hierarchy.json` |
| `title` | `str \| None` | Song title (for UI display) |
| `artist` | `str \| None` | Artist name (for UI display) |

---

## Relationships

```
LibraryEntry (1) ──── (many) GenerationJob
  source_hash                source_hash

GenerationSettings (1, global) ──── (all) GenerationJob
  layout_path                         layout_path (read at job start)
```

---

## API Response Shapes

### Job Status Response
```json
{
  "job_id": "abc123",
  "status": "complete",
  "source_hash": "deadbeef",
  "genre": "pop",
  "occasion": "general",
  "transition_mode": "subtle",
  "created_at": 1712700000.0,
  "error": null
}
```

### Generation History Response
```json
{
  "jobs": [
    {
      "job_id": "abc123",
      "status": "complete",
      "genre": "pop",
      "occasion": "general",
      "transition_mode": "subtle",
      "created_at": 1712700000.0
    }
  ]
}
```

### Start Generation Request Body
```json
{
  "genre": "rock",
  "occasion": "general",
  "transition_mode": "subtle"
}
```

### Settings Response
```json
{
  "layout_path": "/Users/alice/xLights/xlights_rgbeffects.xml",
  "layout_configured": true
}
```
