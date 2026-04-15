# Phase 1 Data Model — Section Preview Render

All types live in `src/generator/preview.py` unless otherwise noted. They are
Python `@dataclass` types, stored in process memory (no persistence).

## `CancelToken`

Cooperative cancellation primitive used by the preview dispatcher and polled
inside `run_section_preview`.

```python
class CancelToken:
    _event: threading.Event

    def cancel(self) -> None: ...
    def is_cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None:
        """Raise PreviewCancelled if the token has been cancelled."""
```

`PreviewCancelled(Exception)` is a module-local sentinel, caught only by the
`_run_preview` thread target.

## `PreviewJob`

One in-memory record of a preview render. Lives in `_preview_jobs` keyed by
`job_id`.

| Field | Type | Notes |
|-------|------|-------|
| `job_id` | `str` (uuid4) | Primary key in `_preview_jobs`. |
| `song_hash` | `str` | Source-file hash from the Library entry. |
| `section_index` | `int` | Which section is being previewed. |
| `brief_snapshot` | `dict[str, Any]` | Snapshot of the Brief used for this job. Never a live reference. |
| `brief_hash` | `str` | 16-char sha256 hex of canonical-JSON(brief_snapshot). Used for cache key. |
| `status` | `str` | `"pending" \| "running" \| "done" \| "failed" \| "cancelled"` |
| `started_at` | `float` | `time.time()` — set when the thread starts. |
| `completed_at` | `float \| None` | Set on terminal statuses. |
| `artifact_path` | `Path \| None` | Path to the `.xsq` under `_preview_dir`. `None` until `done`. |
| `error_message` | `str \| None` | User-facing error (no raw traceback). |
| `cancel_token` | `CancelToken` | Signalled by the dispatcher on supersede. |
| `result` | `PreviewResult \| None` | Cached result payload returned by status GET. |
| `warnings` | `list[str]` | Soft failures surfaced to the UI (e.g. missing drum stem). |

### Status transitions

```
pending ──► running ──► done
                   \──► failed          (exception in pipeline)
                   \──► cancelled       (CancelToken fired)
```

A cancelled job is removed from `_active_by_song` immediately at supersede
time; its `status` may still be `running` briefly until the thread's next
poll. Cancelled jobs are retained in `_preview_jobs` for a short grace
period (10 min) for diagnostic polling from a stale browser tab; download
endpoints refuse cancelled jobs with 410 Gone.

## `PreviewRequest`

Shape of the POST body to `/api/song/<hash>/preview`. Not a dataclass on the
server — the Flask handler reads it directly from `request.get_json()` — but
documented here so the frontend knows the contract.

```json
{
  "section_index": 3,          // or null for auto-select
  "brief": {                   // or the literal string "saved"
    "focused_vocabulary": true,
    "embrace_repetition": true,
    "palette_restraint": true,
    "duration_scaling": true,
    "beat_accent_effects": true,
    "tier_selection": true,
    "curves_mode": "none",
    "genre": "pop",
    "occasion": "general",
    "transition_mode": "subtle"
  }
}
```

When `brief == "saved"`, the server reads the persisted Brief (from spec 047)
and uses it as the snapshot. When `brief` is an object, the server uses it
verbatim — this supports User Story 1 acceptance #4 ("preview unsaved
changes").

## `PreviewResult`

Shape returned by the status GET when `status == "done"`.

```python
@dataclass
class PreviewResult:
    section: dict      # {"label": "chorus", "start_ms": 45000, "end_ms": 60000,
                       #  "energy_score": 82, "role": "chorus"}
    window_ms: int     # Previewed window length (10000–20000).
    theme_name: str    # Theme selected for this section.
    placement_count: int  # Total EffectPlacement objects in the artifact.
    artifact_url: str  # "/api/song/<hash>/preview/<job_id>/download"
    warnings: list[str]
```

Serialized to JSON inside the status-GET response.

## LRU Cache: `_PreviewCache`

Bounded in-memory LRU. Keys are triples, values are `PreviewResult` (plus the
absolute `artifact_path` for the actual file).

```python
CacheKey = tuple[str, int, str]    # (song_hash, section_index, brief_hash)
```

Size: **16 entries** (~16 recent previews kept in memory; older artifacts
evicted and their `.xsq` files deleted from `_preview_dir`). A cache hit
short-circuits the entire pipeline — the dispatcher returns the cached
`PreviewResult` without launching a thread.

Cache correctness invariants:

- `brief_hash` uses canonical-JSON serialization so logically-equal Briefs
  hash identically regardless of key ordering.
- A cache entry is inserted **only on `status == "done"`**. Failed and
  cancelled jobs do not populate the cache.
- Eviction of an entry deletes its `.xsq` file from disk.

## Dispatcher State (module-level in `preview_routes.py`)

| Name | Type | Purpose |
|------|------|---------|
| `_preview_jobs` | `dict[str, PreviewJob]` | All jobs, keyed by `job_id`. |
| `_active_by_song` | `dict[str, str]` | Maps `song_hash` → currently active `job_id`. |
| `_dispatch_lock` | `threading.Lock` | Guards both dicts during POST handling. |
| `_preview_cache` | `_PreviewCache` | LRU from `preview.py`. |
| `_preview_dir` | `Path` | `tempfile.mkdtemp(prefix="xlight_preview_")`. |

The lock is held only for the fast bookkeeping steps inside POST handling
(cache check, job creation, supersede). It is released before the thread
starts so concurrent requests for **different** songs never block each
other.
