# Implementation Plan: Prop-Type Effect Affinity

**Branch**: `041-prop-type-affinity` | **Date**: 2026-04-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/041-prop-type-affinity/spec.md`

## Summary

Generated sequences show the same effect (e.g., Bars) on all prop groups simultaneously
because `embrace_repetition=True` (default since spec 036) disables intra-section
deduplication. When 5 arch groups all score "Bars" as their top variant, all 5 pick it.

Fix: add within-tier base-effect tracking to `build_rotation_plan()` so no two groups
in the same tier share the same base effect in the same section (best-effort, with
graceful fallback). Also filter `not_recommended` effects from the `_build_effect_pool()`
fallback path using the group's `prop_type`.

All required infrastructure already exists: `PowerGroup.prop_type`, `prop_suitability`
ratings in `builtin_effects.json`, and the RotationEngine scoring system. This feature
connects existing pieces rather than building new ones.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: No new dependencies — all existing generator pipeline
**Storage**: N/A — no new data stored; changes are in-memory generation logic
**Testing**: pytest
**Target Platform**: Linux devcontainer / macOS host
**Project Type**: CLI pipeline stage (generator)
**Performance Goals**: No measurable overhead — within-tier dedup is O(n) per tier with n ≤ ~20 groups
**Constraints**: Must not change generated output when only one group exists per tier
**Scale/Scope**: Affects `src/generator/rotation.py` and `src/generator/effect_placer.py` only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | ✅ PASS | No change to analysis pipeline; effect selection remains downstream of audio data |
| II. xLights Compatibility | ✅ PASS | Output format unchanged; only which effect is placed changes |
| III. Modular Pipeline | ✅ PASS | Changes isolated to `rotation.py` and `effect_placer.py`; no stage boundary changes |
| IV. Test-First Development | ✅ PASS | Unit tests for within-tier dedup and prop_type filtering written before implementation |
| V. Simplicity First | ✅ PASS | ~30 lines total; no new abstractions; connects existing data to existing code paths |

No violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/041-prop-type-affinity/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (affected files)

```text
src/
└── generator/
    ├── rotation.py          # Add within-tier base-effect tracking in build_rotation_plan()
    └── effect_placer.py     # Add prop_type param to _build_effect_pool(), wire through

tests/
└── unit/
    └── test_rotation.py     # Add within-tier diversity and prop-type routing tests
```

No new files created. No new directories. No schema changes.

**Structure Decision**: Single-file modifications to existing generator pipeline. No new modules needed.

## Implementation Approach

### Change 1: Within-Tier Base-Effect Diversity (`src/generator/rotation.py`)

In `build_rotation_plan()`, after scoring and ranking variants for each group, add a
`used_effects_per_tier: dict[int, set[str]]` tracking structure. When assigning a
variant to a group:

1. Check if the variant's base effect is already used in this tier
2. If yes, advance to the next-highest-ranked variant whose base effect is free
3. If all options are exhausted, fall back to the best-scored variant (reuse allowed)

This runs independently of `embrace_repetition` — it operates at the base-effect
level (e.g., "Spirals") not the variant level (e.g., "Spirals 3D Fast Spin"), and
applies within a single tier only (not section-wide).

### Change 2: Prop-Type Filtering in Fallback Pool (`src/generator/effect_placer.py`)

Add `prop_type: str | None = None` to `_build_effect_pool()`. When provided:
1. Load `prop_suitability` from each `EffectDefinition`
2. Exclude effects rated `not_recommended` for the given prop type
3. If filtering leaves an empty pool, relax to include `possible`-rated effects

Wire `group.prop_type` through to the `_build_effect_pool()` call site at the
tier 6-7 fallback path (~line 545 in `place_effects()`).
