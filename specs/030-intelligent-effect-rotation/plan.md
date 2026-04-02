# Implementation Plan: Intelligent Effect Rotation

**Branch**: `030-intelligent-effect-rotation` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/030-intelligent-effect-rotation/spec.md`

## Summary

Replace the hardcoded tier 6-7 round-robin effect rotation with an intelligent variant selection system for tiers 5-8 (fidelity, prop, comp, hero). The existing variant scorer (feature 028) provides weighted multi-dimensional ranking; this feature wires it into the effect placement pipeline, adds intra-section variety constraints, introduces theme effect pools (list of variant names per layer), builds symmetry pair detection for mirrored prop groups, and provides rotation diagnostics via CLI and web dashboard.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: click 8+ (CLI), Flask 3+ (web server), existing variant scorer (`src/variants/scorer.py`), existing effect library (`src/effects/library.py`)
**Storage**: JSON files — existing builtin_themes.json (extended with effect_pool), existing variant library
**Testing**: pytest
**Target Platform**: Linux/macOS (local CLI tool + local web dashboard)
**Project Type**: CLI tool + local web application
**Performance Goals**: Sequence generation for a 4-minute song with 20+ sections must complete in under 60 seconds; rotation report renders in under 2 seconds
**Constraints**: Offline operation only; deterministic output given same inputs; backward compatible with all existing themes
**Scale/Scope**: Typical layout: 20-60 props, 8-30 power groups, 10-30 sections per song, 100+ variants in library

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | Effect selection uses audio-derived energy scores, section roles, and timing. Audio analysis remains the source of truth. |
| II. xLights Compatibility | PASS | Output is still EffectPlacement → XSQ. No changes to the XSQ writer or output format. |
| III. Modular Pipeline | PASS | New rotation engine is a self-contained module (`src/generator/rotation.py`) consumed by the existing effect placer. Symmetry detection is a new module in grouper. No shared mutable state. |
| IV. Test-First Development | PASS | Plan requires tests written before implementation for each user story. |
| V. Simplicity First | PASS | Reuses existing variant scorer and progressive fallback. No new abstractions beyond RotationPlan and SymmetryGroup. |

No violations. No entries needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/030-intelligent-effect-rotation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── cli-commands.md
│   └── api-endpoints.md
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── generator/
│   ├── effect_placer.py      # MODIFIED: replace tier 5-8 rotation with intelligent selection
│   ├── rotation.py           # NEW: RotationEngine, RotationPlan, RotationEntry — builds rotation plan from scored variants
│   ├── plan.py               # MODIFIED: pass variant_library through pipeline
│   └── models.py             # (unchanged by this feature)
├── grouper/
│   ├── grouper.py            # MODIFIED: add prop_type field population (from 029)
│   └── symmetry.py           # NEW: SymmetryGroup detection from naming + spatial position
├── themes/
│   └── models.py             # MODIFIED: add effect_pool field to EffectLayer
├── review/
│   └── server.py             # MODIFIED: add GET /rotation-report endpoint
└── cli.py                    # MODIFIED: add rotation-report subcommand

tests/
├── unit/
│   ├── test_rotation.py          # NEW: RotationEngine unit tests
│   ├── test_symmetry.py          # NEW: symmetry detection tests
│   └── test_generator/
│       └── test_effect_placer.py # MODIFIED: update tier 5-8 placement tests
├── integration/
│   └── test_rotation_integration.py  # NEW: end-to-end rotation tests
└── fixtures/
    └── themes/
        └── theme_with_effect_pool.json  # NEW: test fixture
```

**Structure Decision**: Single project structure. Two new modules (`rotation.py`, `symmetry.py`) plus modifications to existing files. No new packages or directories beyond existing structure.
