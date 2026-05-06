## 1. Schema bump on SequenceSummary

- [x] 1.1 Add `layout_model_names: tuple[str, ...] = ()` to `SequenceSummary` in `src/evaluation/models.py`
- [x] 1.2 Update `SequenceSummary.to_dict()` and `SequenceSummary.from_dict()` round-trip to include `layout_model_names`
- [x] 1.3 Update synthetic-summary fixtures in `tests/microscope/test_runner.py`, `tests/microscope/test_diff.py`, `tests/microscope/test_sensitivity.py`, `tests/microscope/test_panel.py`, and any other `tests/evaluation/` fixtures that construct a `SequenceSummary(...)` literal — add `layout_model_names=()` (no-op: default value `()` covers all existing call sites; 287 tests pass unchanged)

## 2. Layout reader + parse() kwarg

- [x] 2.1 Add a private helper `_read_layout_model_names(layout_path: Path) -> tuple[str, ...]` to `src/evaluation/xsq_reader.py`. Implement as an `xml.etree.ElementTree` walk over `<models>/<model>` collecting `name` attributes in document order. Raise `ValueError` (with the offending path) if the file exists but has no `<models>` root.
- [x] 2.2 Add `layout_path: Path | None = None` kwarg to `parse()` and `parse_bytes()`. When supplied, call the helper and pass the result to the `SequenceSummary` constructor.
- [x] 2.3 Add a unit test `tests/evaluation/test_xsq_reader_layout_models.py` covering: (a) layout supplied → field populated in document order; (b) layout omitted → field is `()`; (c) malformed layout → `ValueError`. (8 tests pass)

## 3. placement_coverage_pct metric

- [x] 3.1 Create `src/evaluation/metrics/coverage.py` with a single metric. The compute callable handles three cases: empty `layout_model_names` → `value=None, reliability="no_layout"`; non-empty layout → `value = len(set(model_names)) / len(set(layout_model_names))`, `reliability="ok"`.
- [x] 3.2 Register the metric with `kind=MetricKind.SCALAR`, `gated=False`, `tolerance=DEFAULT_TOLERANCE`, `pro_comparable=False`, `higher_is_better=True`.
- [x] 3.3 Add `import src.evaluation.metrics.coverage` to `_import_all_metrics()` (deviation: that helper is duplicated in `src/microscope/runner.py` and `src/microscope/sensitivity.py`, not in `src/evaluation/metrics/__init__.py`. Updated both call sites.)
- [x] 3.4 Write `tests/evaluation/test_coverage_metric.py` covering the spec scenarios (6 tests pass).

## 4. Microscope runner + panel plumbing

- [x] 4.1 Update `src/microscope/runner.py:run_song()` so the call to `parse(xsq_path, ...)` passes `layout_path=layout_path_obj`.
- [x] 4.2 Verify `src/microscope/panel.py:run_panel()` already routes `layout_path` to `run_song` — confirmed at `panel.py:100` (positional). No change needed.
- [x] 4.3 Add `test_run_song_passes_layout_path_to_parser` (mocked) and `test_integration_layout_universe_populated` (slow, gated on fixtures) — 313 tests pass.

## 5. Sensitivity + baseline refresh

- [x] 5.1 Run `xlight-evaluate microscope sensitivity` to refresh `tests/golden/microscope/sensitivity_passed.json` with the new `metric_set_hash`.
- [x] 5.2 Run the default panel and promote — aggregate `placement_coverage_pct = 0.528`. Per-fixture: funshine 0.67, maple_leaf_rag 0.22, nostalgic_piano 1.00, space_ambience 0.22.
- [x] 5.3 Run the matrix panel and promote — aggregate 0.523. Per-fixture: funshine 0.73, maple_leaf_rag 0.18, nostalgic_piano 1.00, space_ambience 0.18.
- [x] 5.4 Both panels round-trip clean (zero deltas vs newly-promoted baselines).

## 6. Documentation + commit

- [x] 6.1 No new CLAUDE.md entry needed — the metric registers automatically and the panel commands are unchanged.
- [x] 6.2 `pytest tests/evaluation/ tests/microscope/ tests/cli/` → 316 passed, 1 skipped.
- [ ] 6.3 PR body should call out: (a) the schema bump on `SequenceSummary` (two new fields), (b) the `metric_set_hash` change requiring sensitivity refresh, (c) Decision 6 (group expansion via runner-side grouper invocation), (d) actual per-fixture values from §5.
