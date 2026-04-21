# Implementation Plan: xLights Sequence Quality Calibration Harness

**Branch**: `050-quality-calibration` | **Date**: 2026-04-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/workspace/specs/050-quality-calibration/spec.md`

## Summary

Build an evaluation harness that extracts a shared set of metrics from both professionally-made `.xsq` sequences and our generator's output on the same songs, producing (a) an informational pro-vs-ours comparison report and (b) a CI-gated regression check against a committed own-baseline. Reuses existing audio analysis cache (beats, energy curves, section boundaries) and existing generator pipeline. No new heavyweight dependencies — the harness is pure Python over `xml.etree.ElementTree`, `zipfile`, `numpy`, and the existing click CLI.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `click` 8+ (CLI, existing), `numpy` (metric math, already transitively present), `xml.etree.ElementTree` (stdlib, `.xsq` parsing), `zipfile` (stdlib, `.xsqz` extraction), `hashlib` (stdlib, audio hashing). Existing internal modules: `src.analyzer` (audio analysis cache), `src.generator` (generator pipeline), `src.cache` (hash-keyed analysis storage).
**Storage**: JSON files — corpus manifest, per-run reports, baseline snapshot — all under `tests/golden/pro_reference/` (manifest, notes) and `tests/golden/` (baseline, reports). Pro `.xsq`/`.xsqz` and source `.mp3` files live on local disk outside the repo.
**Testing**: pytest. Unit tests per metric with hand-crafted `SequenceSummary` fixtures. Integration test on a 1-song smoke corpus. Pathological-floor test suite (synthetic degenerate sequences).
**Target Platform**: Linux / macOS dev workstation. Offline-only (constitution III).
**Project Type**: Python CLI + library (matches existing `src/` layout).
**Performance Goals**: Full 6-song / 9-pro-sequence comparison in ≤ 5 minutes wall-time (SC-001). Per-song metric extraction from a parsed `SequenceSummary` must complete in ≤ 500 ms so report generation is dominated by generator runs, not metric math.
**Constraints**: No xLights rendering in any automated flow (FR-021, user feedback memory). No network calls (constitution). Generator invocation must be deterministic given a fixed seed (FR-019).
**Scale/Scope**: 6–10 songs, 9–15 pro sequences, 9 metrics at v0. Expected growth: +3 missing MP3s later, +3 metrics before promoting any to gated status.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|---|---|---|
| I. Audio-First Pipeline | ✅ Pass | All audio-window metrics use the authoritative audio analysis cache (beats, energy, section boundaries). Generation-time sections are explicitly rejected for measurement (spec FR-008). |
| II. xLights Compatibility | ✅ Pass | Harness only reads `.xsq`/`.xsqz`; no new output format. Does not alter generator output. |
| III. Modular Pipeline | ✅ Pass | New `src/evaluation/` module is independently testable; communicates with existing code via read-only interfaces (parsed `SequenceSummary`, cached analysis results). No shared mutable state. |
| IV. Test-First Development | ✅ Pass | Per-metric unit tests, pathological-floor fixtures, and an integration test on a seeded smoke corpus are required deliverables (see Phase 2 task ordering in `tasks.md`). |
| V. Simplicity First | ✅ Pass | v0 scope is deliberately narrow: 9 metrics, stdlib parsing, no tuning automation, no render integration. Each added complexity was challenged in spec assumptions and clarifications. |

**Result**: No violations. Complexity Tracking section omitted.

## Project Structure

### Documentation (this feature)

```text
specs/050-quality-calibration/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — resolved unknowns
├── data-model.md        # Phase 1 output — entities & schemas
├── contracts/           # Phase 1 output — CLI command contracts
│   ├── evaluate-compare.md
│   ├── evaluate-check.md
│   └── evaluate-snapshot.md
├── quickstart.md        # Phase 1 output — usage walkthrough
├── checklists/
│   └── requirements.md  # Quality checklist from /speckit.specify
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/
├── evaluation/                   # NEW — feature scope
│   ├── __init__.py
│   ├── xsq_reader.py             # Parse .xsq / .xsqz into SequenceSummary
│   ├── models.py                 # SequenceSummary, Placement, MetricValue, Report, Baseline
│   ├── metrics/
│   │   ├── __init__.py           # Metric registry + tolerance defaults
│   │   ├── pacing.py             # placements_per_minute, density_energy_correlation
│   │   ├── palette.py            # palette_top5_colors, per_section_palette_diversity
│   │   ├── effects.py            # effect_type_histogram, unknown_effect_fraction
│   │   ├── alignment.py          # beat_alignment_pct
│   │   ├── sections.py           # section_transition_delta
│   │   └── internal.py           # tier_utilization, theme_assignment_consistency (ours-only)
│   ├── corpus.py                 # Manifest loader, hash verification, skip categorization
│   ├── generator_runner.py       # Deterministic wrapper around existing generator pipeline
│   ├── compare.py                # Cross-song report assembly
│   └── baseline.py               # Baseline read/write + regression gate logic
├── cli/
│   └── evaluate.py               # NEW — xlight-evaluate subcommands (compare, check, snapshot)
└── ... (existing modules untouched)

tests/
├── evaluation/                   # NEW — unit + integration tests
│   ├── fixtures/                 # Hand-crafted SequenceSummary + degenerate cases
│   │   ├── degenerate/
│   │   │   ├── monochrome.json
│   │   │   ├── single_effect.json
│   │   │   ├── random_alignment.json
│   │   │   └── empty.json
│   │   └── minimal_xsq/
│   │       └── tiny.xsq          # Hand-authored minimal valid .xsq for reader tests
│   ├── test_xsq_reader.py
│   ├── test_metrics_*.py         # One file per metric module
│   ├── test_pathological_floor.py
│   ├── test_corpus.py
│   ├── test_baseline_gate.py
│   └── test_integration_smoke.py # 1-song end-to-end
└── golden/                       # NEW — corpus + baseline + reports
    ├── pro_reference/
    │   ├── manifest.json         # Committed
    │   ├── notes/                # Committed
    │   │   └── <song-id>.md
    │   └── README.md             # How to set up local paths
    ├── baseline.json             # Committed own-baseline
    └── reports/                  # Gitignored; timestamped run artifacts
        └── .gitkeep
```

**Structure Decision**: Single-project layout consistent with existing `src/` / `tests/` structure. The new work is isolated in `src/evaluation/` and `tests/evaluation/`, with no edits to existing generator or analyzer code. The CLI entry point follows the established pattern of per-feature subcommand files in `src/cli/`.

## Phase 0: Outline & Research

See [research.md](./research.md). All topics resolved — no `NEEDS CLARIFICATION` markers remain in Technical Context.

## Phase 1: Design & Contracts

See:
- [data-model.md](./data-model.md) — entity schemas (manifest, `SequenceSummary`, `Placement`, `MetricValue`, `Report`, `Baseline`) with field-level validation rules drawn from spec FRs.
- [contracts/](./contracts/) — one markdown file per CLI subcommand, specifying args, exit codes, output format, and acceptance behaviors.
- [quickstart.md](./quickstart.md) — end-to-end walkthrough: bootstrap the manifest, run the first comparison, commit the first baseline, simulate a regression, see the gate fire.

**Agent context**: `.specify/scripts/bash/update-agent-context.sh claude` ran successfully; `CLAUDE.md` updated with this feature's tech additions.

### Constitution re-check (post-design)

No design choices introduced violations:
- All metric computation is pure-function over `SequenceSummary` + cached audio analysis — no side effects, trivially testable (I, III, IV).
- No new output file formats; only reads `.xsq` / `.xsqz` (II).
- No speculative abstractions: one module per metric group, one dataclass per entity, no plugin system (V).

## Complexity Tracking

N/A — no constitution violations.
