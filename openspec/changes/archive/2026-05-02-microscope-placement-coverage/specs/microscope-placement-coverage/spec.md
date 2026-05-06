## ADDED Requirements

### Requirement: SequenceSummary exposes the layout's model universe

`SequenceSummary` SHALL include a `layout_model_names: tuple[str, ...]` field
holding every model name defined in the source layout XML, regardless of
whether the placer reached it, AND a `layout_group_members:
dict[str, tuple[str, ...]]` field mapping each placement-target group name
(e.g. `08_HERO_MegaTree`, `02_GEO_Left`) to the underlying layout model
names it expands to. The existing `model_names` field SHALL be preserved
unchanged and continue to enumerate placement-target names (group OR model)
that received at least one placement in the parsed XSQ.

#### Scenario: Default value when no layout is supplied

- **WHEN** `parse()` is called without a `layout_path` argument
- **THEN** the returned `SequenceSummary.layout_model_names` is the empty
  tuple `()`, and `model_names` carries the placement-bearing models as
  before

#### Scenario: Populated when a layout is supplied

- **WHEN** `parse(xsq_path, layout_path=layout)` is called with a layout
  whose `<models>` section defines props "A", "B", "C", and the XSQ only
  contains placements on "A"
- **THEN** `summary.layout_model_names == ("A", "B", "C")` and
  `summary.model_names == ("A",)`

#### Scenario: Layout file order preserved

- **WHEN** `parse()` reads a layout whose `<model>` elements appear in
  the order "Z", "A", "M"
- **THEN** `summary.layout_model_names == ("Z", "A", "M")` (no sorting,
  no de-duplication beyond what XML enforces)

### Requirement: Microscope runner threads layout into the parser

`run_song()` and `run_panel()` SHALL pass their `layout_path` argument
through to `parse()` so every microscope-produced `SequenceSummary` has
`layout_model_names` populated.

#### Scenario: Single-song run includes layout coverage

- **WHEN** `run_song(audio, layout, output_dir)` completes
- **THEN** `result.summary.layout_model_names` is non-empty and contains
  every `<model>` name defined in `layout`

#### Scenario: Panel run propagates layout to every per-song summary

- **WHEN** `run_panel(manifest_path, output_dir)` produces N
  `MicroscopeResult` instances
- **THEN** every result's `summary.layout_model_names` reflects the
  manifest's `layout` field, identically across all N results

### Requirement: placement_coverage_pct metric

The metric registry SHALL include `placement_coverage_pct`. The metric
SHALL compute the covered set by expanding each name in `model_names`
through `layout_group_members` (where present) and unioning with names
that are directly in `layout_model_names`, then intersecting with
`layout_model_names` and dividing by its cardinality. The metric is
registered with `kind=SCALAR`, `gated=False`, and `higher_is_better=True`
(coverage drops register as `↓✗` in the diff direction column).

#### Scenario: Full coverage produces 1.0

- **WHEN** every model in `summary.layout_model_names` also appears in
  `summary.model_names`
- **THEN** `placement_coverage_pct.value == 1.0` and
  `reliability == "ok"`

#### Scenario: Partial coverage produces a fraction

- **WHEN** `summary.layout_model_names == ("A","B","C","D")` and
  `summary.model_names == ("A","B")` and `layout_group_members` is empty
- **THEN** `placement_coverage_pct.value == 0.5`

#### Scenario: Group placement expands to its members

- **WHEN** `summary.layout_model_names == ("A","B","C","D")`,
  `summary.model_names == ("HERO_GroupOne",)`, and
  `summary.layout_group_members == {"HERO_GroupOne": ("A", "B")}`
- **THEN** `placement_coverage_pct.value == 0.5` (A and B covered via
  the group)

#### Scenario: Group expansion ignores non-layout members

- **WHEN** a placement targets a group whose members include a name not
  present in `layout_model_names` (e.g. a sub-model addressed as
  ``Parent/SubModel``)
- **THEN** that name does not contribute to the numerator; only members
  in `layout_model_names` count toward coverage

#### Scenario: Unknown when layout context is missing

- **WHEN** `summary.layout_model_names` is the empty tuple (caller did
  not supply a layout to `parse()`)
- **THEN** `placement_coverage_pct.value is None` and
  `reliability == "no_layout"`

#### Scenario: Empty layout treated as unknown

- **WHEN** `layout_model_names` is non-empty but somehow contains zero
  unique entries (would only happen with a malformed layout XML)
- **THEN** the metric returns `value=None, reliability="no_layout"`
  rather than raising `ZeroDivisionError`

### Requirement: Sensitivity proof guards baselines after registration

The `microscope baseline` subcommand SHALL refuse to promote new
baselines until `microscope sensitivity` has been re-run after
`placement_coverage_pct` was added to the registry. Adding the metric
changes the `metric_set_hash` returned by `compute_metric_set_hash()`,
so any pre-existing proof file is stale by definition.

#### Scenario: Stale proof blocks baseline promotion

- **WHEN** `metrics/coverage.py` is added but `microscope sensitivity`
  has not been re-run
- **THEN** `microscope baseline` exits non-zero with a message naming
  the stale proof and the cone commit that invalidated it

#### Scenario: Refreshed proof unblocks promotion

- **WHEN** `microscope sensitivity` is re-run after the metric is
  registered
- **THEN** `tests/golden/microscope/sensitivity_passed.json` reflects
  the new `metric_set_hash` and `microscope baseline` proceeds
