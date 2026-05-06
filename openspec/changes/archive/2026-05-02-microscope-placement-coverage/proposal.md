## Why

The microscope panel has no way to detect when the generator stops producing
placements on a layout-defined prop. PR #151's matrix-heavy panel surfaced
the symptom: in the default reference layout, `MatrixCenter` falls into
placement-inactive spatial bins (`02_GEO_Mid` / `02_GEO_Center`) and receives
zero placements across all four CC0 fixtures. The microscope reported zero
deltas for every change to matrix logic because the metric set has no signal
for "this prop got nothing." A future generator change could quietly starve
an entire prop type and the panel would still produce a clean zero-delta
diff. This proposal closes that detection gap with one additional metric.

## What Changes

- Add `placement_coverage_pct` metric: fraction of layout-defined models that
  received at least one placement (directly or via a group whose members
  include them), computed as `len(covered_models) / len(layout_models)`.
  Direction: `higher_is_better=True` — a coverage drop is a regression.
- Extend `SequenceSummary` with two new fields:
  - `layout_model_names: tuple[str, ...]` — every model the layout XML defines,
    regardless of whether the placer reached it.
  - `layout_group_members: dict[str, tuple[str, ...]]` — map from group target
    name (e.g. `02_GEO_Left`, `08_HERO_MegaTree`) to its underlying layout
    model names. Required because the placer emits placements at the group
    level; without expansion the coverage intersection is mostly empty even
    when the placer is reaching every prop indirectly.
  Existing `model_names` (placement-target names — group OR model) is
  preserved unchanged for backward compatibility.
- Update `parse()` / `parse_bytes()` to accept optional `layout_path` and
  `layout_group_members` kwargs; when supplied, the parser reads the layout
  XML once and populates `layout_model_names`. When omitted, both fields
  default to empty and `placement_coverage_pct` reports
  `reliability="no_layout"` (so old callers and synthetic-summary tests
  continue to work).
- Plumb the layout path from `MicroscopeResult` / `run_song` / `run_panel`
  to `parse()` so panel runs always have layout coverage data. The runner
  also re-derives the synthetic groups (via `src/grouper/` — the same path
  `generate_sequence` uses) to populate `layout_group_members`. This keeps
  the generator-side coupling inside `src/microscope`, not `src/evaluation`.

## Capabilities

### New Capabilities
- `microscope-placement-coverage`: the new metric plus the
  `SequenceSummary.layout_model_names` data flow that supports it.

### Modified Capabilities
None — `visual-quality-microscope` was archived after its initial change
merged, and the new metric is registered alongside (not in place of) the
existing six suitability/vitality metrics.

## Impact

**Code touched**
- `src/evaluation/models.py` — `SequenceSummary` schema bump (two new fields
  with empty defaults).
- `src/evaluation/xsq_reader.py` — `parse()` / `parse_bytes()` kwargs,
  layout reader helper.
- `src/evaluation/metrics/coverage.py` — new module, one metric (with group
  expansion).
- `src/microscope/runner.py` — pass `layout_path` and pre-derived
  `layout_group_members` to `parse()`.
- All synthetic `SequenceSummary` constructors continue to work — the new
  fields have defaults.
- `tests/evaluation/test_coverage_metric.py` — new file, ~7 tests.
- `tests/evaluation/test_xsq_reader_layout_models.py` — new file for the
  layout reader helper.

**Baselines**
- Re-running `microscope sensitivity` is required (metric registry changes
  `metric_set_hash`).
- Both default panel baselines and matrix panel baselines must be
  re-captured after the new metric is registered. Empirical from
  implementation: default panel ≈ 0.5–0.7 (group expansion catches the
  HERO + GEO targets); matrix panel similar.

**Out of scope**
- A passing `placement_coverage_pct` does not mean the placement *quality*
  is good — only that some placement landed. Pairing-fit metrics retain
  that responsibility.
- The metric reads layout from XML; no plumbing through internal layout
  representations (`Prop`, `PowerGroup`) is added.
