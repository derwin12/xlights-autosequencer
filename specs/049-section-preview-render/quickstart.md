# Quickstart — Section Preview Render

Verification walkthrough for the preview endpoint + tab. Assumes you already
have a song in the library with completed analysis and a configured layout
(same preconditions as full generation).

## 1. Launch the review server

```bash
xlight-analyze review   # or the dashboard entry point
```

Confirm the Preview tab exists in the per-song workspace (from spec 046).

## 2. POST a preview (curl — backend smoke test)

Replace `<hash>` with your song's hash. This uses the saved Brief for
deterministic output.

```bash
curl -sX POST http://localhost:5173/api/song/<hash>/preview \
    -H 'Content-Type: application/json' \
    -d '{"section_index": null, "brief": "saved"}'
```

Expected response (HTTP 202):

```json
{"job_id": "6f1e...-....-4a..-..-...."}
```

If a recent identical preview is cached, you may instead see HTTP 200 with
the full `PreviewResult` payload and no `job_id` — this is the cache-hit
short-circuit.

## 3. Poll status

```bash
curl -s http://localhost:5173/api/song/<hash>/preview/<job_id>
```

Expected sequence (each poll ~500ms apart):

1. `{"status": "running", ...}`
2. `{"status": "running", ...}` (for the next few polls)
3. `{"status": "done", "result": {"section": {...}, "window_ms": 15000,
    "theme_name": "...", "placement_count": 47, "artifact_url": ".../download",
    "warnings": []}}`

Wall-clock from POST to `done` should be ≤ 10 seconds for a typical 3-minute
song (SC-001).

## 4. Download the preview .xsq

```bash
curl -sOJ http://localhost:5173/api/song/<hash>/preview/<job_id>/download
```

Produces a file like `preview_<hash>_<section>.xsq` in the current directory.
Its `sequenceDuration` should be exactly the previewed window (10–20
seconds); its `mediaFile` should match your original MP3's basename; its
`mediaOffset` should equal the section's start time in milliseconds.

Quick XML spot-check:

```bash
grep -E 'sequenceDuration|mediaFile|mediaOffset' preview_*.xsq
```

## 5. Open in xLights

1. Place the preview `.xsq` next to the song's MP3 (or download into the
   same directory you configured in xLights).
2. Open xLights, load the `.xsq`.
3. Press Play.

Expected: audio starts at the section's offset inside the MP3; effects play
on the prop groups for the full 10–20s window; timeline begins at t=0 in
the xLights view; no silent gap at the start.

## 6. Supersede behavior

While a preview is running (you can force a slow run by picking the longest
section), fire a second POST for the same song:

```bash
curl -sX POST http://localhost:5173/api/song/<hash>/preview \
    -H 'Content-Type: application/json' \
    -d '{"section_index": 2, "brief": "saved"}'
```

Expected:

- The second POST returns 202 with a new `job_id`.
- Polling the **first** `job_id`: returns `status: "cancelled"` within a few
  seconds of the second POST (cancellation is cooperative at stage
  boundaries, so up to ~3s lag).
- Attempting to download the first job: returns 410 Gone.
- The second job proceeds to `done` normally.

## 7. UI-level verification

On the Preview tab:

1. Open the tab for a song with saved Brief.
2. Click **Preview**. A "Previewing…" indicator appears; within ~10s the
   result pane shows the section label, metadata, and a **Download .xsq**
   link.
3. Click a different section in the dropdown and click **Preview** again.
   Result pane replaces the first section's output; the first section's
   download link is removed.
4. Edit any Brief field. The result pane grays out and shows
   **"Brief changed — click Re-preview"** within 500ms of the edit (SC-005).
5. Click **Re-preview**. A new job runs; the stale marker clears when it
   completes.

## 8. Regression guards

- `curl -s http://localhost:5173/api/generation-preview/<hash>` still
  returns its original static-summary payload (SC-007, FR-014).
- `pytest tests/ -v` passes (SC-008). New tests:
  - `tests/unit/test_preview_section_picker.py`
  - `tests/unit/test_preview_job.py`
  - `tests/integration/test_section_preview.py`
