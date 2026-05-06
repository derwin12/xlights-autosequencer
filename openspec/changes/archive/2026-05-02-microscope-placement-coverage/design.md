## Context

`SequenceSummary` is built by `src/evaluation/xsq_reader.py:parse()` from the
generated XSQ alone. Its `model_names` field captures only models referenced
in `<ElementEffects>`, so a layout-defined prop that received zero placements
is invisible to every existing metric. PR #151 (matrix-heavy panel) hit the
ceiling this creates: the matrix panel's whole purpose was to detect changes
that affect matrix placements, but the metric set could only count what was
placed, not what should have been.

The fix is small in API terms — one new metric, one new dataclass field, one
new parser kwarg — but `SequenceSummary` is shared infrastructure: every
test that synthesizes one (5 microscope test files) needs the new field
filled in, and the metric registry's `metric_set_hash` will change, so all
existing golden baselines (default panel + matrix panel) must be re-promoted
behind a refreshed sensitivity proof.

## Goals / Non-Goals

**Goals:**
- Detect "this layout-defined prop got zero placements" as a panel signal,
  with `higher_is_better=True` so a coverage drop registers as `↓✗`.
- Make `parse()` / `parse_bytes()` layout-aware without breaking existing
  callers (the analyzer's `compare` flow doesn't have a layout to pass).
- Cover the matrix panel and default panel with a single, additive metric
  registration — no mutation of existing metric definitions.

**Non-Goals:**
- Per-tier coverage (e.g., "tier 8 HERO got zero placements"). Tier
  classification lives in `src/grouper/`, which is generator-side; reading
  it would couple the evaluation layer to internals it intentionally
  doesn't depend on.
- Per-prop-type coverage rollup. `per_prop_type_diversity` already exposes
  per-type effect counts; extending it for zero-coverage cases is a
  follow-up if the scalar metric proves insufficient.
- Substituting models by `<modelGroup>` membership. We count concrete
  `<model>` elements only — model groups are placement targets, not the
  universe being measured.

## Decisions

### Decision 1: Extend `SequenceSummary` (vs. side-channel)

Add `layout_model_names: tuple[str, ...] = ()` to `SequenceSummary`.

**Alternatives considered:**
1. **Side-channel argument to the metric** — change the metric registry's
   `compute(summary)` signature to `compute(summary, audio_context=None,
   layout_context=None)`. **Rejected**: ripples through every existing
   metric module's `compute=` registration, plus the dispatcher in
   `src/evaluation/compare.py` already has a hard-coded per-metric
   audio-context plumbing path that would need extending in a parallel
   way. Higher cross-cutting risk than the dataclass field.
2. **Compute coverage outside the metric registry** — e.g., as a
   `MicroscopeResult.placement_coverage_pct` field that the CLI surfaces
   separately from `result.metrics`. **Rejected**: would create a
   second-class metric outside the diff/baseline machinery, requiring CLI
   special cases and breaking the "every measured number lives in the
   registry" invariant.

The dataclass field with `()` default is the smallest change that keeps
both backward compat (old callers don't supply it) and the existing
metric-registration contract.

### Decision 2: Layout reading via `parse()` kwarg

`parse(path, ..., layout_path: Path | None = None)`. When supplied, an
inline helper reads the layout XML, walks `<models>/<model>`, and collects
`name` attributes. The result is stored on `SequenceSummary.layout_model_names`.

**Alternatives considered:**
1. **A separate `read_layout_models(path)` helper called by `run_song`**,
   merged into the summary after parsing. **Rejected**: splits the
   construction of `SequenceSummary` across two call sites, easy to forget
   one.
2. **Reuse `src/grouper/layout.py:parse_layout()`**. **Rejected**: that
   module returns a richer `Layout` / `Prop` representation pulling in
   classification logic and coordinate normalization. We need just a flat
   list of model names — a 10-line ElementTree walk is simpler and
   doesn't depend on generator-side modules.

### Decision 3: `placement_coverage_pct` direction

`higher_is_better=True`.

A drop in coverage means the placer stopped reaching some prop that it
previously reached. That is structurally a regression, regardless of
whether the change was intentional. If a future redesign deliberately
narrows coverage (e.g., "leave non-hero props dark for ethereal
sections"), the panel diff will flag it, the developer will see `↓✗`,
and the baseline will be re-promoted to lock in the new floor — exactly
how every other directional metric in the registry works.

### Decision 4: `reliability` field for layout-less callers

When `parse()` is called without a layout path, `layout_model_names` is
the empty tuple. The metric returns `value=None,
reliability="no_layout"` rather than synthesizing a value from
`model_names` (which would always report 1.0 — every placement-bearing
model is in the placement-bearing set, by definition). The `MetricValue`
shape already supports `value=None` for unknowable cases (see
`per_prop_type_diversity` with `reliability="no_known_props"`), so this
extends an established pattern.

### Decision 5: Don't unify default and matrix baselines

After this change, both panels' baselines need to be re-captured because
`metric_set_hash` changes. They remain separate baseline sets. Merging
them under a shared registry would force the layout to expose the same
prop-type distribution across both, which they intentionally don't.

### Decision 6: Group expansion via runner-side grouper invocation

**Surfaced during implementation**: the placer emits placements at
synthetic group targets (`08_HERO_MegaTree`, `02_GEO_Left`), not at
underlying layout model names. So `set(model_names) ∩
set(layout_model_names)` is mostly empty even when every prop is
indirectly reached. The naive "intersect placement targets with layout
models" formula reports ~0% coverage on real panels — useless as a
regression sentinel.

The XSQ does NOT carry the group → members mapping (only a
`<DisplayElements>` list of names). The mapping exists only in memory
during generation. To recover it the evaluation layer would either need
to (a) re-classify the layout itself (couples evaluation to grouper) or
(b) receive the map as input.

`SequenceSummary` gains a second optional field
`layout_group_members: dict[str, tuple[str, ...]]`. The runner
re-invokes the grouper modules (`parse_layout` + `classify_props` +
`normalize_coords` + `generate_groups`) to derive the same groups the
generator would have used, then passes the `{name: members}` map to
`parse()`. The metric's expansion logic resolves each placement target
through this map, unioning expanded members with direct-model
placements before intersecting with the layout universe.

**Alternatives considered:**
1. **Generator-side sidecar** — have `generate_sequence` write a
   `groups.json` alongside the XSQ. **Rejected**: changes a stable
   generator output contract for one downstream consumer.
2. **Substring heuristic in the evaluation layer** — check if each
   layout model name appears in any placement target name (so
   `MegaTree ∈ 08_HERO_MegaTree` matches). **Rejected**: catches the
   HERO case but misses the GEO case (`02_GEO_Left` doesn't contain
   `ArchLeft`). Fragile and hard to validate.
3. **Recompute groups in evaluation** — import `src/grouper/` from
   `src/evaluation/`. **Rejected**: explicit non-goal under
   "evaluation must not depend on generator internals." The runner
   sits in `src/microscope` which is already coupled to both layers,
   so deriving there is fine.

**Bright line preserved:** `src/evaluation/metrics/coverage.py` does
not import from `src/grouper/`. The expansion data arrives via the
`SequenceSummary` field, populated by `src/microscope/runner.py`.

## Risks / Trade-offs

- **Synthetic `SequenceSummary` test fixtures break.** Mitigation:
  five test files (`test_runner.py`, `test_diff.py`,
  `test_sensitivity.py`, `test_panel.py`, plus one in
  `tests/evaluation/`) construct `SequenceSummary(...)` literals. Each
  needs `layout_model_names=()` added — straightforward but mechanical.
  All updates are in the tasks file.
- **Metric_set_hash invalidation.** Mitigation: documented requirement
  to re-run `microscope sensitivity` and re-promote both panels'
  baselines, captured in the tasks file.
- **Layout XML parser is duplicated** (a thin one in `xsq_reader`, a
  rich one in `grouper/layout.py`). Mitigation: the new helper is ~10
  lines, well-commented as "evaluation-side, just model name extraction;
  see grouper/layout.py for the generator-side rich representation."
  If a third caller appears, this would be the right time to extract a
  shared module — not now.
- **Coverage interpretation can mislead.** A 100% coverage panel doesn't
  mean placements are *good*, only present. Mitigation: documented in
  the spec's `### Why this metric` section; the existing pairing-fit
  metrics are explicitly the quality side of the same question.
