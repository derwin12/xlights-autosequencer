# API Contract: Settings Endpoints (grouper save update)

This documents the change to the existing grouper save endpoint so that it persists the layout path to `~/.xlight/settings.json` for use by the generation feature.

---

## Existing: POST /grouper/save (modified)

Saves the current grouper edits to disk **and** writes the active layout path to `~/.xlight/settings.json`.

**Change**: After the existing save logic, write `{"layout_path": "<abs-path>"}` to `~/.xlight/settings.json`.

**No change to the response shape** — the existing response is preserved:
```json
{"success": true, "edits_path": "/path/to/<md5>_grouping_edits.json"}
```

---

## Notes

- `~/.xlight/settings.json` is created if it does not exist.
- If the file already exists, only the `layout_path` key is updated (other keys preserved via merge).
- The generate endpoint reads `layout_path` from this file at job start time (not cached in memory).
