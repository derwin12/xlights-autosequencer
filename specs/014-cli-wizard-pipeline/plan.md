# Implementation Plan: Interactive CLI Wizard & Pipeline Optimization

**Branch**: `014-cli-wizard-pipeline` | **Date**: 2026-03-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/014-cli-wizard-pipeline/spec.md`
**Constitution**: v1.0.0 (2026-03-22)

## Summary

Add an interactive CLI wizard (`xlight-analyze wizard`) that guides users through analysis configuration with arrow-key navigable menus, visible cache status, and Whisper model selection. Restructure the analysis pipeline around an explicit dependency graph to enable parallel execution of independent algorithms, targeting a 30% wall-clock speedup. Two new dependencies: `questionary` (interactive prompts) and `rich` (live multi-track progress display).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: click 8+ (CLI), questionary 2+ (interactive prompts, new), rich 13+ (progress display, new), concurrent.futures (stdlib, parallelism)
**Storage**: JSON files (existing `_analysis.json` cache, `~/.xlight/library.json`)
**Testing**: pytest
**Target Platform**: macOS (primary), Linux
**Project Type**: CLI tool
**Performance Goals**: 30% wall-clock speedup via parallelization (SC-002); wizard launch <2s (SC-004)
**Constraints**: Offline operation (constitution II); must preserve vamp subprocess isolation (.venv-vamp boundary); existing `analyze` command unchanged
**Scale/Scope**: 22 algorithms across 3 libraries (librosa, vamp, madmom), 6 stems, 5 wizard steps

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | Wizard configures but does not alter the analysis pipeline. All timing still derives from audio data. |
| II. xLights Compatibility | PASS | No changes to output format. The wizard adds configuration UI, not output changes. |
| III. Modular Pipeline | PASS | The dependency graph restructuring *improves* modularity — each pipeline step becomes independently declared and testable. New modules (wizard.py, pipeline.py, progress.py) are isolated. |
| IV. Test-First Development | PASS | Plan includes unit tests for pipeline DAG execution, wizard config mapping, and integration tests for parallel runner. Fixture-based tests preserved. |
| V. Simplicity First | PASS | Two new dependencies (questionary, rich) are standard Python CLI libraries. No speculative abstractions — the DAG is a simple adjacency list, not a generic workflow engine. |
| Offline Operation | PASS | Genius lyrics fetch (optional, already existing) is the only network call. Whisper model download is user-initiated. No new cloud dependencies. |
| Performance Baseline | PASS | Parallelization targets faster performance, not slower. 3-minute MP3 must still complete under 60s — parallelization helps this. |

**Post-Phase-1 Re-check**: All gates still pass. The dependency graph is a static adjacency list (not a generic DAG engine), keeping V. Simplicity satisfied. No new output formats affect II. xLights Compatibility.

## Project Structure

### Documentation (this feature)

```text
specs/014-cli-wizard-pipeline/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity definitions
├── quickstart.md        # Phase 1: developer setup guide
├── contracts/
│   └── cli-wizard.md    # Phase 1: wizard CLI contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── cli.py                      # Extended: new `wizard` subcommand
├── wizard.py                   # NEW: interactive wizard UI (questionary prompts)
├── cache.py                    # Extended: CacheStatus snapshot for wizard display
├── analyzer/
│   ├── runner.py               # Preserved: backward-compat progress_callback wrapper only — parallel dispatch moved to pipeline.py
│   ├── pipeline.py             # NEW: PipelineStep, DependencyGraph, DAG executor
│   ├── progress.py             # NEW: multi-track rich progress display
│   ├── stems.py                # Unchanged
│   ├── scorer.py               # Unchanged
│   ├── phonemes.py             # Unchanged
│   └── algorithms/
│       └── base.py             # Extended: `depends_on` class attribute

tests/
├── unit/
│   ├── test_pipeline.py        # NEW: DAG topological sort, parallel dispatch, failure isolation
│   ├── test_wizard_config.py   # NEW: WizardConfig → CLI flag equivalence
│   └── test_cache_status.py    # NEW: CacheStatus snapshot accuracy
└── integration/
    └── test_parallel_runner.py # NEW: end-to-end parallel run with timing assertions
```

**Structure Decision**: Extends the existing single-project layout. Three new source files (`wizard.py`, `pipeline.py`, `progress.py`) follow the existing pattern of one concern per module. No new directories needed beyond what exists.

## Complexity Tracking

No constitution violations requiring justification. Two new dependencies (`questionary`, `rich`) are the simplest libraries for their respective purposes — building interactive prompts and live terminal displays from scratch would be more complex, not less.
