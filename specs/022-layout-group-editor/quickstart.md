# Quickstart: Layout Group Editor

**Feature**: 022-layout-group-editor | **Date**: 2026-03-30

## Prerequisites

- Python 3.11+
- Existing dependencies installed (`pip install click flask pytest`)
- An xLights layout file (`xlights_rgbeffects.xml`)

## Launch the Editor

```bash
# Open the layout group editor in browser
xlight-analyze grouper-edit /path/to/xlights_rgbeffects.xml
```

This launches the Flask server and opens `http://localhost:5173/grouper` in your default browser.

## Workflow

1. **View**: The editor loads your layout, runs auto-grouping, and displays 8 tier tabs
2. **Navigate**: Click tier tabs to switch between tiers (Canvas, Spatial, Architecture, etc.)
3. **Edit**: Drag props between groups or to/from the "Ungrouped" section
4. **Save**: Click Save to persist edits (stored separately from the original grouping)
5. **Export**: Click Export to produce `_grouping.json` for the sequence generator

## File Locations

| File | Purpose | Location |
|------|---------|----------|
| Layout XML | Input (read-only) | User-provided path |
| Edit file | User modifications | `<md5>_grouping_edits.json` adjacent to layout |
| Export file | Merged grouping for generator | `<md5>_grouping.json` adjacent to layout |

## Using with Sequence Generator

```bash
# Generate sequence using edited grouping
xlight-analyze generate song.mp3 --layout /path/to/xlights_rgbeffects.xml
# Generator auto-detects _grouping.json if present
```

## Development

```bash
# Run editor tests
pytest tests/unit/test_grouper_editor.py -v
pytest tests/integration/test_grouper_editor_roundtrip.py -v
```
