# Implementation Plan: Value Curves Integration

**Branch**: `032-value-curves-integration` | **Date**: 2026-04-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/032-value-curves-integration/spec.md`

## Summary

Enable value curves so effect parameters change dynamically over time following the music. The infrastructure is 97% built — `generate_value_curves()`, the xSQ encoder, 290+ flagged parameters, and 33/35 effects with analysis mappings all exist and are tested. This feature activates the disabled pipeline in `build_plan()`, adds CLI/config controls, and adds chord-triggered color accent support with quality thresholds.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing — numpy (curve math), click 8+ (CLI), no new deps
**Storage**: JSON (analysis cache, generation config), XML (.xsq output)
**Testing**: pytest (existing test suite for value_curves.py — 307 lines, all passing)
**Target Platform**: Local CLI tool + .xsq output for xLights
**Project Type**: CLI tool / sequence generator
**Performance Goals**: Value curve generation adds <20% to generation time (SC-005)
**Constraints**: Max 100 control points per parameter per placement (FR-005); xLights inline encoding format
**Scale/Scope**: 33 effects with mappings, 290+ curve-capable parameters; 3 curve categories (brightness, speed, color)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | Pass | Value curves are derived entirely from analysis data (L5 energy, L6 chords) — audio is the source of truth |
| II. xLights Compatibility | Pass | Output uses xLights' native inline value curve format (`Active=TRUE\|Id=...\|Type=Ramp\|Values=...`) |
| III. Modular Pipeline | Pass | Value curve generation is a self-contained stage; adding it to build_plan doesn't modify other stages |
| IV. Test-First Development | Pass | Existing test suite covers generation, curve shapes, downsampling; new tests for activation and CLI flag |
| V. Simplicity First | Pass | Activating existing code, not building new abstractions. CLI flag is a single option with clear modes |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/032-value-curves-integration/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI contract)
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── generator/
│   ├── plan.py              # MODIFY: activate value curves in build_plan(), add category filtering
│   ├── value_curves.py      # MODIFY: add chord-triggered color accent support, category filtering
│   ├── models.py            # MODIFY: add curves_mode to GenerationConfig
│   ├── effect_placer.py     # No changes — value curves are applied post-placement in plan.py
│   └── xsq_writer.py        # No changes — already encodes value curves
├── effects/
│   └── builtin_effects.json  # REVIEW: verify analysis_mappings for brightness/speed/color parameters
├── cli.py                    # MODIFY: add --curves flag to generate command

tests/
├── unit/
│   └── test_generator/
│       └── test_value_curves.py  # EXTEND: add tests for category filtering, chord accents, config flag
└── integration/
    └── test_generate_with_curves.py  # NEW: end-to-end test generating .xsq with curves
```

**Structure Decision**: Extends existing generator pipeline files. No new modules — value curve generation is already a module. Only modifications and one new integration test file.
