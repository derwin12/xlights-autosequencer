# Contract: xLights Layout

**Superseded 2026-07-20**: the layout is no longer imported per-session. A
fixed `xlights_rgbeffects.xml` / `xlights_networks.xml` pair is committed to
the repo at `layout/` and every song exports against it. The `POST
/api/v1/layout` upload endpoint described below has been removed.

## GET `/api/v1/layout`

Return the repo-committed layout's parsed summary, or `{"layout": null}` if
`layout/xlights_rgbeffects.xml` is missing from the checkout.

**Response 200**
```json
{
  "layout_id": "layout_b3f01a",
  "display_name": "xLights Layout",
  "imported_at": "2026-04-21T17:00:00Z",
  "props": [
    { "name": "Arch 1", "display_type": "SingleLine", "pixel_count": 50, "pixel_range": [0, 49] }
  ],
  "total_pixels": 2400,
  "xml_path": "/workspace/layout/xlights_rgbeffects.xml"
}
```

**Response 200** (file missing)
```json
{ "layout": null }
```

## Notes

- The parsed layout is cached in-process after first read (`src/review/api/v1/layout.py::get_committed_layout`) — the committed file only changes via a repo checkout + server restart, never at runtime.
- `GET /api/v1/songs/<song_id>/export/download-package` bundles the generated `.xsq` with both committed layout files into a single `.xsqz` (xLights' zipped-sequence-package extension).
