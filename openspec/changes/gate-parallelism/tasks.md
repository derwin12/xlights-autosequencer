# Tasks — gate-parallelism

## 1. Implementation

- [x] 1.1 Add `parallel: bool = True` to `GateOptions` in
  `src/evaluation/acceptance_gate.py`.
- [x] 1.2 Replace the sequential suite dispatch in `run_gate` with a
  `ThreadPoolExecutor` block that submits the suites and waits for every
  future to complete. Implemented as a small `_dispatch_suites` helper
  taking a list of `(name, callable)` pairs so a future fourth suite
  (section_fidelity) folds in cleanly.
- [x] 1.3 Wrap every future's `.result()` call in `_run_suite_safe`,
  which converts any unexpected exception into a
  `SuiteResult(name, status="infra-error", message=...)` so the
  exit-code priority (infra > no-baseline > regression > pass) continues
  to apply.
- [x] 1.4 Reassemble the `suites` dict in `_CANONICAL_SUITE_ORDER`
  (analyzer, generator, ui) regardless of future completion order so
  JSON output and `format_summary` are byte-identical to the serial
  path.
- [x] 1.5 Preserve the serial path under `parallel=False` for
  debugging.

## 2. Tests

- [x] 2.1 `test_run_gate_parallel_dispatch_is_faster_than_serial` — mock
  the suites with 0.5s sleeps, assert wall time < 2 × SLEEP (the 3 ×
  SLEEP serial sum).
- [x] 2.2 `test_run_gate_canonical_ordering_under_parallel_dispatch` —
  stagger sleeps so completion order is reversed; assert `report.suites`
  keys still iterate as `analyzer, generator, ui`.
- [x] 2.3 `test_run_gate_serial_path_respects_parallel_false` — explicit
  `parallel=False`; verify wall time ≥ sum of suite durations.
- [x] 2.4 `test_run_gate_exception_in_parallel_future_becomes_infra_error`
  — patch one suite to raise; verify the gate aggregates exit_code=8
  instead of crashing and other suites still run.
- [x] 2.5 `test_run_gate_default_parallel_is_true` — guard against
  silent default change.
- [x] 2.6 `test_run_gate_serial_and_parallel_produce_same_report_shape`
  — direct equality check between the two dispatch modes' reports for
  fixed mock suites.

## 3. Validation

- [x] 3.1 `pytest tests/evaluation/test_gate_cli.py -v` — 22/22 green.
- [x] 3.2 Wall-time benchmark across 3 back-to-back mock runs (analyzer
  2.0s + generator 0.05s + ui 1.0s): serial ≈ 3.08s, parallel ≈ 2.01s,
  speedup 1.53x — deterministic across all 3 runs.
- [x] 3.3 Determinism: same 3 runs produce identical wall times to 0.01s
  resolution. Report shape (suite ordering, statuses, exit codes)
  identical between serial and parallel modes.
- [ ] 3.4 Open PR with before/after wall times in the body.
