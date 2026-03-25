# Implementation Plan: Hierarchy Orchestrator

**Branch**: `016-hierarchy-orchestrator` | **Date**: 2026-03-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/016-hierarchy-orchestrator/spec.md`

## Summary

Replace the existing 14-flag `analyze` command with a zero-flag orchestrator that accepts a single MP3 path and produces a structured hierarchical analysis (L0–L6). The orchestrator auto-detects installed capabilities (Vamp, madmom, demucs), runs only the algorithms needed per hierarchy level (~15 instead of 36), auto-selects the best result per level, and outputs a `HierarchyResult` JSON plus `.xtiming` export. Data model is updated to support value curves as a first-class type and preserve labels/durations from segmentation and harmony algorithms.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: librosa 0.10+, vamp (optional), madmom 0.16+ (optional), demucs/torch (optional), click 8+ (CLI), numpy
**Storage**: JSON files (hierarchy result), XML files (.xtiming export), WAV stems cached in `.stems/<md5>/`
**Testing**: pytest
**Target Platform**: macOS (primary), Linux (secondary)
**Project Type**: CLI tool
**Performance Goals**: <60s without stems, <5 min with stems for a 3-min MP3
**Constraints**: Offline-only, graceful degradation when dependencies missing
**Scale/Scope**: Single user, processes 1-20 MP3s per session

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Audio-First Pipeline** | PASS | Audio is the sole input. All timing derives from analysis. No manual input required. |
| **II. xLights Compatibility** | PASS | .xtiming output follows xLights XML schema. HierarchyResult JSON is an intermediate format consumed by downstream .xsq generation. |
| **III. Modular Pipeline** | PASS | Orchestrator composes existing algorithm modules. Each stage (detect → load → analyze → select → derive → export) is independently testable. Data flows via HierarchyResult dataclass, not shared state. |
| **IV. Test-First Development** | PASS | Tests written per phase: data model unit tests, orchestrator integration tests, CLI acceptance tests. Fixture MP3s already exist in `tests/fixtures/`. |
| **V. Simplicity First** | PASS | Removes 14 flags, not adds complexity. Reuses existing algorithm implementations. New code is orchestration logic only. |

## Project Structure

### Documentation (this feature)

```text
specs/016-hierarchy-orchestrator/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/
│   └── cli.md           # CLI contract
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── analyzer/
│   ├── orchestrator.py      # NEW: main pipeline — detect → analyze → select → derive
│   ├── capabilities.py      # NEW: auto-detect installed tools
│   ├── selector.py          # NEW: best-of selection per hierarchy level
│   ├── derived.py           # NEW: compute energy impacts, gaps from curves
│   ├── result.py            # MODIFIED: add ValueCurve, update TimingMark, add HierarchyResult
│   ├── algorithms/
│   │   ├── vamp_bbc.py      # MODIFIED: return ValueCurve instead of fake timing marks
│   │   ├── vamp_segmentation.py  # MODIFIED: preserve labels and durations
│   │   └── vamp_harmony.py  # MODIFIED: preserve chord names as labels
│   ├── interaction.py       # EXISTING: reused as-is
│   ├── conditioning.py      # EXISTING: reused as-is
│   ├── stems.py             # EXISTING: reused as-is
│   ├── xtiming.py           # EXISTING: reused as-is (updated to handle labeled marks)
│   └── runner.py            # EXISTING: reused internally by orchestrator
├── cli.py                   # MODIFIED: replace analyze command with orchestrator entry point
└── review/
    └── server.py            # MODIFIED: read HierarchyResult instead of AnalysisResult

tests/
├── unit/
│   ├── test_result.py       # NEW: ValueCurve, updated TimingMark, HierarchyResult
│   ├── test_capabilities.py # NEW: capability detection
│   ├── test_selector.py     # NEW: best-of selection logic
│   └── test_derived.py      # NEW: energy impact and gap derivation
├── integration/
│   └── test_orchestrator.py # NEW: end-to-end pipeline test
└── fixtures/                # EXISTING: short MP3s for deterministic tests
```

**Structure Decision**: Extends existing `src/analyzer/` with 4 new modules (orchestrator, capabilities, selector, derived). Modifies 4 existing modules (result, vamp_bbc, vamp_segmentation, vamp_harmony). Replaces CLI entry point. No new directories needed.

## Complexity Tracking

No constitution violations to justify — all gates pass.
