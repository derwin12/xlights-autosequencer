# Implementation Plan: Devcontainer Path Resolution

**Branch**: `023-devcontainer-path-resolution` | **Date**: 2026-03-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/023-devcontainer-path-resolution/spec.md`
**Constitution**: 1.0.0 (2026-03-22)

## Summary

The system currently stores absolute paths in analysis results, library index entries, and stem manifests. When users switch between the dev container and host, these paths break because the same file has different absolute paths in each environment (e.g., `/home/node/xlights/song.mp3` vs `~/xlights/song.mp3`). This plan introduces a `PathContext` module that detects the runtime environment, maps between container and host path prefixes, and ensures all persisted paths are either relative (to the show directory) or accompanied by a content hash for environment-independent cache lookup. Existing cache keys (MD5) and XSQ media references (basename-only) are already safe and need no changes.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: pathlib (stdlib), os (stdlib), hashlib (stdlib) — no new dependencies
**Storage**: JSON files (analysis cache, library index, stem manifests)
**Testing**: pytest
**Target Platform**: Linux (devcontainer), macOS (host) — both POSIX
**Project Type**: CLI tool + pipeline library
**Performance Goals**: Path resolution overhead < 1ms per operation (negligible vs audio analysis)
**Constraints**: No new user-facing configuration required; backward-compatible with existing JSON
**Scale/Scope**: Single-user local tool; dozens of songs in library

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | Path resolution is infrastructure; does not alter audio analysis pipeline |
| II. xLights Compatibility | PASS | XSQ already uses basename-only mediaFile references; no change needed |
| III. Modular Pipeline | PASS | PathContext is a new standalone module; existing stages communicate via unchanged data contracts |
| IV. Test-First Development | PASS | Plan includes fixture-based tests for path mapping in both environments |
| V. Simplicity First | PASS | Minimal changes: one new module (~100 lines), targeted edits to 4 existing files |

**Technical Constraints**:
- Offline operation: PASS — no network calls
- Performance baseline: PASS — path string manipulation is sub-millisecond

## Project Structure

### Documentation (this feature)

```text
specs/023-devcontainer-path-resolution/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── paths.py              # NEW — PathContext, environment detection, path mapping
├── cache.py              # MODIFY — add relative path storage alongside absolute
├── library.py            # MODIFY — store relative paths, deduplicate by hash
├── analyzer/
│   ├── audio.py          # MODIFY — store relative path in AudioFile
│   ├── orchestrator.py   # MODIFY — use PathContext for source_file storage
│   ├── result.py         # MODIFY — add relative_source_file field
│   └── stems.py          # MODIFY — store relative path in manifest
└── generator/
    └── xsq_writer.py     # NO CHANGE — already uses basename only

tests/
├── unit/
│   └── test_paths.py     # NEW — PathContext unit tests
└── integration/
    └── test_path_resolution.py  # NEW — cross-environment path resolution tests
```

**Structure Decision**: Single new module `src/paths.py` with targeted modifications to existing files. No new directories or packages needed.

## Constitution Check — Post-Design

*Re-evaluation after Phase 1 design completion.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | No changes to audio analysis; PathContext is read at path resolution time only |
| II. xLights Compatibility | PASS | XSQ output unchanged; mediaFile already uses basename |
| III. Modular Pipeline | PASS | PathContext is a standalone module with no dependencies on analysis stages; data contracts gain optional fields only |
| IV. Test-First Development | PASS | `test_paths.py` covers all PathContext methods; `test_path_resolution.py` covers cross-environment scenarios with env var mocking |
| V. Simplicity First | PASS | One new module, 4 modified files, no new dependencies, no abstraction layers beyond what's needed |

**All gates pass. Proceed to task generation.**

## Complexity Tracking

No constitution violations. No complexity justifications required.
