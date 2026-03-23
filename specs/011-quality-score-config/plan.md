# Implementation Plan: Configurable Quality Scoring

**Branch**: `011-quality-score-config` | **Date**: 2026-03-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-quality-score-config/spec.md`

## Summary

Replace the current black-box quality scorer (density + regularity weighted sum) with an explainable, category-aware scoring system. Each of the 22 timing tracks is assigned to a scoring category (beats, bars, onsets, segments, pitch, harmony) with per-category target ranges for five criteria (density, regularity, mark count, coverage, minimum gap compliance). Users see per-criterion breakdowns, can adjust weights and thresholds via TOML configuration files, save settings as named profiles, and get diversity-filtered `--top N` selection that avoids near-identical tracks.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: numpy (scoring math), tomllib (TOML config parsing, stdlib in 3.11+), click 8+ (CLI), pytest (testing)
**Storage**: TOML files (scoring configs/profiles), JSON files (analysis output with score breakdowns)
**Testing**: pytest with fixture-based scoring tests
**Target Platform**: macOS (darwin), local machine
**Project Type**: CLI tool
**Performance Goals**: Scoring 22 tracks completes in < 100 ms (pure computation, no I/O bottleneck)
**Constraints**: No new pip dependencies required (tomllib is stdlib); backward-compatible JSON output
**Scale/Scope**: Single user, local machine; 22 algorithm tracks per analysis run

## Constitution Check

*Constitution version 1.0.0 — ratified 2026-03-22*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | Pass | Scoring criteria (density, regularity, coverage, mark count, min_gap) are all derived from analyzed audio timing data |
| II. xLights Compatibility | Pass | Scoring is internal to the analysis pipeline; no changes to xLights output formats |
| III. Modular Pipeline | Pass | Scorer remains an independent stage; communicates via ScoreBreakdown data contract; does not alter algorithm execution |
| IV. Test-First Development | Pass | Tests before implementation; fixture tracks with known scores for deterministic validation |
| V. Simplicity First | Pass | Replaces one file (scorer.py), adds config loading (scoring_config.py) and CLI subcommand; no new abstractions beyond what's needed |

**Complexity Tracking**: No violations. No additional justification needed.

## Project Structure

### Documentation (this feature)

```text
specs/011-quality-score-config/
├── plan.md              # This file
├── research.md          # Phase 0 output — scoring approach, categories, diversity algorithm
├── data-model.md        # Phase 1 output — ScoringCategory, CriterionResult, ScoreBreakdown, ScoringConfig
├── quickstart.md        # Phase 1 output — developer onboarding
├── contracts/
│   └── cli.md           # CLI schema: --scoring-config, --scoring-profile, --breakdown, scoring subcommand
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── analyzer/
│   ├── audio.py              # unchanged
│   ├── result.py             # +ScoreBreakdown, CriterionResult on TimingTrack
│   ├── runner.py             # unchanged
│   ├── scorer.py             # REWRITTEN: CategoryScorer, category-aware scoring, ScoreBreakdown output
│   ├── scoring_config.py     # NEW: ScoringConfig, ScoringCategory, config loading/validation, profile management
│   ├── diversity.py          # NEW: DiversityFilter — mark-alignment similarity, greedy selection
│   └── algorithms/           # unchanged (category assignment is in scoring_config.py lookup table)
├── cli.py                    # +--scoring-config, +--scoring-profile, +--breakdown; +scoring subcommand group
├── export.py                 # +ScoreBreakdown serialization/deserialization in JSON
└── review/
    ├── server.py             # +serve score_breakdown data to UI
    └── static/               # +breakdown visualization (future, minimal for this feature)

tests/
├── fixtures/
│   └── scoring/              # NEW: fixture TimingTracks with known expected scores
├── unit/
│   ├── test_scorer.py        # REWRITTEN: category-aware scoring, criterion computation, edge cases
│   ├── test_scoring_config.py # NEW: TOML loading, validation, defaults, error cases
│   └── test_diversity.py     # NEW: mark alignment, similarity threshold, greedy selection
└── integration/
    └── test_scoring_pipeline.py  # NEW: end-to-end scoring with config, breakdown in JSON output
```

**Structure Decision**: Single-project layout. Scorer rewritten in place (`scorer.py`), two new files (`scoring_config.py`, `diversity.py`) in `src/analyzer/`. Config loading and profile management in `scoring_config.py`.
