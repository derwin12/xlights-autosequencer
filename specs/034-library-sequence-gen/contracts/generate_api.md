# API Contract: Sequence Generation Endpoints

**Blueprint prefix**: `/generate`
**Blueprint file**: `src/review/generate_routes.py`

---

## POST /generate/<source_hash>

Start a new sequence generation job for the song identified by `source_hash`.

**Request**
```
Content-Type: application/json
```
```json
{
  "genre": "pop",
  "occasion": "general",
  "transition_mode": "subtle"
}
```

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `genre` | string | No | `"pop"` | `"rock"` / `"pop"` / `"classical"` / `"any"` |
| `occasion` | string | No | `"general"` | `"general"` / `"christmas"` / `"halloween"` |
| `transition_mode` | string | No | `"subtle"` | `"none"` / `"subtle"` / `"dramatic"` |

**Success Response** — `202 Accepted`
```json
{
  "job_id": "abc123",
  "status": "pending"
}
```

**Error Responses**

- `404` — song not found in library
  ```json
  {"error": "Song not found"}
  ```
- `400` — song has not been analyzed
  ```json
  {"error": "Song has not been analyzed. Run analysis first."}
  ```
- `409` — layout not configured
  ```json
  {"error": "No layout configured. Set up layout groups in the grouper first.", "setup_required": true}
  ```

---

## GET /generate/<source_hash>/status?job_id=<job_id>

Poll the status of a generation job.

**Success Response** — `200 OK`
```json
{
  "job_id": "abc123",
  "status": "running",
  "source_hash": "deadbeef",
  "genre": "pop",
  "occasion": "general",
  "transition_mode": "subtle",
  "created_at": 1712700000.0,
  "error": null
}
```

| `status` | Meaning |
|----------|---------|
| `"pending"` | Job queued, not started |
| `"running"` | Generation in progress |
| `"complete"` | `.xsq` ready to download |
| `"failed"` | Error; see `error` field |

**Error Responses**
- `404` — job_id not found
  ```json
  {"error": "Job not found"}
  ```

---

## GET /generate/<source_hash>/download/<job_id>

Download the generated `.xsq` file.

**Success Response** — `200 OK`
```
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="<song_title>.xsq"
```
Binary `.xsq` file.

**Error Responses**
- `404` — job not found or not complete
  ```json
  {"error": "No completed sequence found for this job"}
  ```

---

## GET /generate/<source_hash>/history

List all completed generation jobs for a song in the current session.

**Success Response** — `200 OK`
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

Jobs are returned newest-first. Failed jobs are excluded.

---

## GET /generate/settings

Get the current installation-wide generation settings (layout path).

**Success Response** — `200 OK`
```json
{
  "layout_path": "/Users/alice/xLights/xlights_rgbeffects.xml",
  "layout_configured": true
}
```

If no layout has been configured:
```json
{
  "layout_path": null,
  "layout_configured": false
}
```
