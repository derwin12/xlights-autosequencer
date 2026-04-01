# Implementation Plan: Theme Editor

**Branch**: `026-theme-editor` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/026-theme-editor/spec.md`

## Summary

Build a standalone theme editor web UI that allows users to browse, create, edit, rename, duplicate, and delete lighting themes — without requiring song analysis. The editor uses a split-panel layout (theme list + detail/edit panel), stores custom themes as individual JSON files in `~/.xlight/custom_themes/`, and supports deep linking from other pages. This supersedes spec 025 (theme data endpoint).

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JS + HTML/CSS (frontend)
**Primary Dependencies**: Flask 3+ (web server), existing `src/themes/` and `src/effects/` modules
**Storage**: JSON files — `src/themes/builtin_themes.json` (read-only), `~/.xlight/custom_themes/*.json` (read-write, one file per theme)
**Testing**: pytest (backend API routes), manual browser testing (frontend)
**Target Platform**: Local web application (localhost), modern browsers
**Project Type**: Web application (Flask backend + vanilla JS SPA frontend)
**Performance Goals**: Theme library loads in <2s; supports 100+ custom themes without degradation
**Constraints**: Offline-only; no external APIs; no build toolchain for frontend (vanilla JS consistent with existing review UI)
**Scale/Scope**: ~21 built-in themes + up to 100+ custom themes; single-user local application

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | **N/A** | Theme editor is a UI tool, not an audio analysis stage. Themes are consumed by the pipeline but the editor itself doesn't process audio. |
| II. xLights Compatibility | **PASS** | Themes define xLights effect names, blend modes, and parameter storage names. Validation ensures all referenced effects exist in the effect library. No xLights output format changes. |
| III. Modular Pipeline | **PASS** | Theme editor is a new standalone module (`src/review/theme_routes.py` + `src/review/static/theme-editor.*`). It uses existing `src/themes/` and `src/effects/` modules via their public APIs. No shared mutable state. |
| IV. Test-First Development | **PASS** | Backend pytest tests are written before implementation (Phase 2: tests first, then implementation to make them pass). Frontend is vanilla JS (manual testing consistent with existing review UI pattern). |
| V. Simplicity First | **PASS** | No new dependencies. Reuses existing theme models, validation, and effect library. Vanilla JS frontend consistent with existing UI. No build toolchain. |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/026-theme-editor/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API endpoint contracts)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/
├── themes/
│   ├── models.py            # Existing: Theme, ThemeVariant, EffectLayer dataclasses
│   ├── library.py           # Existing: ThemeLibrary, load_theme_library()
│   ├── validator.py         # Existing: validate_theme()
│   ├── builtin_themes.json  # Existing: 21 built-in themes (read-only)
│   └── writer.py            # NEW: save/delete/rename custom theme JSON files
├── effects/
│   ├── models.py            # Existing: EffectDefinition, EffectParameter
│   ├── library.py           # Existing: EffectLibrary, load_effect_library()
│   └── builtin_effects.json # Existing: effect definitions (read for param auto-populate)
├── review/
│   ├── server.py            # MODIFY: register theme_bp blueprint, add /themes route
│   ├── story_routes.py      # MODIFY: add deep link integration (theme name → editor URL)
│   ├── theme_routes.py      # NEW: Flask blueprint for theme CRUD API endpoints
│   └── static/
│       ├── theme-editor.html  # NEW: theme editor HTML shell
│       ├── theme-editor.js    # NEW: theme editor SPA logic
│       ├── theme-editor.css   # NEW: theme editor styles
│       └── story-review.js    # MODIFY: add theme name deep links to editor

tests/
├── unit/
│   └── test_theme_routes.py   # NEW: pytest tests for theme API endpoints
│   └── test_theme_writer.py   # NEW: pytest tests for file write/delete/rename
└── fixtures/
    └── themes/                # Existing: test theme JSON fixtures
```

**Structure Decision**: Follows the existing project pattern — Flask blueprint for API routes, vanilla JS SPA for frontend, one-file-per-concern. The theme writer module (`writer.py`) isolates file I/O from the Flask routes for testability.

## Constitution Re-Check (Post-Design)

| Principle | Status | Post-Design Notes |
|-----------|--------|-------------------|
| I. Audio-First Pipeline | **N/A** | No audio processing introduced. Theme editor is purely a UI/data tool. |
| II. xLights Compatibility | **PASS** | All effect names, blend modes, and parameter storage names reference existing validated data from the effect library. No new xLights format output. |
| III. Modular Pipeline | **PASS** | New `theme_routes.py` blueprint and `writer.py` module are self-contained. They consume `src/themes/` and `src/effects/` via public APIs only. No shared mutable state. |
| IV. Test-First Development | **PASS** | Test files written before implementation in Phase 2 (Red-Green-Refactor). Tests: `test_theme_writer.py` (file I/O) and `test_theme_routes.py` (API endpoints + scale validation). |
| V. Simplicity First | **PASS** | Zero new dependencies. Reuses existing models, validation, and library loading. Vanilla JS frontend. File naming via simple slugification. Full library reload (not incremental cache). |

**Post-design gate result**: PASS — no violations. No entries needed in Complexity Tracking.

## Complexity Tracking

No constitution violations to justify.
