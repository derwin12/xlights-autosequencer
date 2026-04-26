# Parallelize Acceptance-Gate Independent Suites

## Why

`xlight-evaluate gate` runs three independent suites serially today — analyzer
(~390s), generator (~1s), and UI (~120s) — totalling ~510s wall time end-to-end.
A fourth suite (section_fidelity, ~0s) is being added in parallel work on
another branch and will fold into this same dispatch path with no additional
work once both land. Analyzer and UI are the long-poles and they share
no mutable state: the analyzer reads MP3s from disk and writes per-fixture
snapshots, the UI suite spawns Playwright against a Flask sub-server.
Running them concurrently cuts wall time to ~max(analyzer, ui) + small
overhead — roughly a 22% reduction on full runs, and a larger fraction
when the UI suite is slow.

The gate is the pre-merge friction point. Faster gate, faster dev loops.

## What Changes

- **`src/evaluation/acceptance_gate.py`** — `run_gate` dispatches the three
  current suites to a `ThreadPoolExecutor`, waits for every future to
  complete, and assembles the `suites` dict in the existing canonical
  order (analyzer, generator, ui) so the JSON report field ordering and
  human summary line ordering are bit-identical to the serial
  implementation. The dispatch is built around an extensible
  `_dispatch_suites` helper that takes a list of `(name, callable)` pairs,
  so adding a fourth (section_fidelity) suite later is a one-line list
  append.
- The `run_*_suite` functions are unchanged in signature and behavior —
  they remain individually callable and the unit tests that mock them keep
  working. Only the orchestrator's dispatch is parallelized.
- A new CLI / programmatic `parallel: bool = True` field on `GateOptions`
  preserves the serial path for environments where parallelism is not
  desired (debugging, low-RAM CI runners). Default is True.

Non-goals:
- No change to the four suites' implementations.
- No change to JSON report schema (`schema_version` stays at 1).
- No change to exit-code aggregation.
- No change to the `format_summary` output other than (potentially) the
  per-suite `duration_seconds` summing to more than the gate's wall time
  — which is the entire point.

## Impact

- **Files modified**: `src/evaluation/acceptance_gate.py`,
  `tests/evaluation/test_gate_cli.py` (new tests covering parallel
  dispatch + ordering).
- **Files added**: none.
- **Files removed**: none.

## Capabilities

### Modified Capabilities
- `acceptance-gate` — `run_gate` orchestration becomes parallel by default.
  Public API surface (`GateOptions`, `GateReport`, `SuiteResult`,
  `run_gate`, `_aggregate_exit_code`, `format_summary`, every
  `run_*_suite`) preserved.
