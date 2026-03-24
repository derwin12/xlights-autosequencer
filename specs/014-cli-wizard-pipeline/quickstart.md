# Developer Quickstart: 014-cli-wizard-pipeline

**Branch**: `014-cli-wizard-pipeline` | **Date**: 2026-03-24

---

## Setup

```bash
# Switch to feature branch
git checkout 014-cli-wizard-pipeline

# Install new dependencies
pip install questionary rich

# Existing dependencies should already be installed:
# pip install click librosa vamp madmom pytest
```

## Key Files to Modify

| File | Change |
|------|--------|
| `src/cli.py` | Add `wizard` subcommand, wire up WizardConfig → parallel runner |
| `src/analyzer/runner.py` | Refactor `AnalysisRunner.run()` to accept dependency graph, dispatch parallel |
| `src/analyzer/pipeline.py` | **New** — PipelineStep, DependencyGraph, parallel executor |
| `src/wizard.py` | **New** — Interactive wizard UI (questionary prompts, cache status display) |
| `src/analyzer/progress.py` | **New** — Multi-track rich progress display |
| `src/cache.py` | Extend with CacheStatus snapshot for wizard display |

## Architecture Overview

```
wizard.py (UI) → WizardConfig → pipeline.py (DAG executor) → runner.py (algorithm dispatch)
                                     ↓
                              ThreadPoolExecutor (local)
                              + Popen (subprocess batches)
                                     ↓
                              progress.py (live display)
```

## Running & Testing

```bash
# Run the wizard interactively
xlight-analyze wizard song.mp3

# Run with specific flags (non-interactive)
xlight-analyze wizard song.mp3 --no-stems --phoneme-model tiny --non-interactive

# Run tests
pytest tests/ -v -k "wizard or pipeline or parallel"

# Benchmark parallelization speedup
xlight-analyze wizard song.mp3 --non-interactive 2>&1 | grep pipeline_stats
```

## New Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| `questionary` | Interactive terminal prompts (arrow-key menus, confirms) | >=2.0 |
| `rich` | Multi-track live progress display, terminal capability detection | >=13.0 |
