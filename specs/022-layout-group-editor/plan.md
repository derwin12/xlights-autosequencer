# Implementation Plan: Layout Group Editor

**Branch**: `022-layout-group-editor` | **Date**: 2026-03-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/022-layout-group-editor/spec.md`

## Summary

Build a browser-based interactive editor that lets users view the auto-generated 8-tier layout grouping, drag-and-drop props between groups within a per-tier tabbed view, and persist edits separately from the baseline grouping. Edits are keyed by MD5 hash of the layout file and stored as JSON. Export merges baseline + edits into a `_grouping.json` file consumable by the sequence generator.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JS (frontend — matches existing review UI pattern)
**Primary Dependencies**: Flask 3+ (web server), click 8+ (CLI), xml.etree.ElementTree (stdlib, layout XML parsing), hashlib (stdlib, MD5 keying), json (stdlib)
**Storage**: JSON files — `<md5>_grouping_edits.json` (user edits), `<md5>_grouping.json` (merged export)
**Testing**: pytest (backend unit/integration tests), manual browser testing (frontend drag-and-drop)
**Target Platform**: Local browser-based UI served via Flask (localhost)
**Project Type**: Web UI (local Flask server + vanilla JS frontend) extending existing review server
**Performance Goals**: Layout loads and renders within 3 seconds for up to 200 props; drag-and-drop updates are instant (<100ms)
**Constraints**: No new Python dependencies; frontend uses vanilla JS (no frameworks) matching existing static assets; offline operation only
**Scale/Scope**: Layouts with 10-200 props, 8 tiers, typically 20-40 groups total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | N/A | This feature edits layout grouping, not audio timing. Grouping is a post-analysis step. |
| II. xLights Compatibility | PASS | Layout is read from xLights XML via existing parser. Export produces JSON for the generator, not direct XML injection. xLights XML is not modified. |
| III. Modular Pipeline | PASS | New grouper_editor module is independent from existing grouper. Communicates via PowerGroup data contract. Edit persistence is a separate concern from group generation. |
| IV. Test-First Development | PASS | Unit tests for edit model (apply/merge/reset), JSON serialization, and MD5 keying. Integration test for load→edit→save→reload round-trip. |
| V. Simplicity First | PASS | No new dependencies. Reuses existing Flask server pattern, existing grouper/layout/classifier modules. Vanilla JS frontend. No abstractions beyond what's needed. |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/022-layout-group-editor/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api-routes.md    # Flask route contracts
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── grouper/
│   ├── layout.py          # [EXISTING] Prop/Layout dataclasses, parse_layout()
│   ├── classifier.py      # [EXISTING] normalize_coords(), classify_props()
│   ├── grouper.py         # [EXISTING] PowerGroup, generate_groups()
│   ├── writer.py          # [EXISTING] inject_groups(), write_layout()
│   └── editor.py          # [NEW] GroupingEdits model, apply/merge/reset/export logic
├── review/
│   ├── server.py          # [MODIFY] Register grouper editor routes
│   └── static/
│       ├── grouper.html   # [NEW] Layout group editor page
│       ├── grouper.js     # [NEW] Drag-and-drop UI, tier tabs, API calls
│       └── grouper.css    # [NEW] Editor-specific styles
└── cli.py                 # [MODIFY] Add `grouper-edit` command to launch editor

tests/
├── unit/
│   └── test_grouper_editor.py  # [NEW] Edit model, merge, reset, serialization
└── integration/
    └── test_grouper_editor_roundtrip.py  # [NEW] Load→edit→save→reload→export
```

**Structure Decision**: Extends the existing `src/grouper/` package with a new `editor.py` module for edit logic. Frontend assets follow the existing pattern in `src/review/static/`. Routes are registered directly in `server.py` (no blueprints, matching existing pattern).

## Complexity Tracking

No constitution violations — table not needed.
