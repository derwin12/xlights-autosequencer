# Design — gate-parallelism

## Goal

One sentence: *Run the independent acceptance-gate suites concurrently
instead of serially so the pre-merge wall time drops from ~510s to ~max(analyzer, ui) + overhead.*

Note on suite count: `main` currently has three suites (analyzer, generator,
ui). A fourth suite (section_fidelity) is being added on a parallel branch
(`agreement-score-operationalization`). The parallel-dispatch helper here
is built to take an arbitrary list of suite callables so the section_fidelity
addition will fold in cleanly with no further refactor.

## Approach

Use `concurrent.futures.ThreadPoolExecutor` inside `run_gate`.
Submit all suites at once, wait for every future, and re-assemble the
`suites` dict in the canonical order before exit-code aggregation and
report write.

### Why threads, not processes

- Two of the four suites (`run_generator_suite`, `run_ui_suite`) already
  spawn their own subprocesses via `subprocess.run(...)`. Wrapping the
  Python orchestrator in `multiprocessing.ProcessPoolExecutor` would
  fork-spawn those subprocesses through an extra layer of fork()
  semantics — risky on macOS (default `fork` start method has known
  issues with libdispatch and CFNetwork; `spawn` re-imports the world).
- The two fully-Python suites (`run_analyzer_suite`,
  `run_section_fidelity_suite`) do their CPU work in C extensions
  (numpy / librosa / madmom / vamp) which release the GIL during
  long-running calls — so threads benefit nearly the full
  parallelism speed-up despite the GIL.
- `subprocess.run` itself releases the GIL while the child is running.
- Threads avoid the ~1s start-up cost of `spawn`-based ProcessPoolExecutor
  and inherit the parent's environment (PATH, venv) without re-shimming.

### What runs in parallel

All current suites (analyzer, generator, ui) run concurrently. Generator
(~1s) is fast enough that serializing it after the long-poles would add
no measurable benefit — submitting it in the same pool keeps the
dispatch logic uniform. `max_workers` is set to the suite count so no
extra threads are spawned.

### Resource-contention reasoning

- **CPU**: analyzer suite is CPU-bound (numpy / madmom RNN). UI suite is
  mostly I/O-bound (Flask responses + Playwright DOM polling). Generator
  and section_fidelity are negligible. No contention.
- **RAM**: analyzer holds an MP3 + numpy arrays (~500 MB peak per
  fixture). Playwright Chromium is ~250 MB. Headroom required: ~1 GB.
  The CC0 quick-mode corpus is one fixture, so analyzer never holds
  more than one in flight. Modern dev machines and CI runners (≥8 GB)
  handle this comfortably.
- **Ports**: UI suite's Flask sub-server uses an ephemeral port chosen
  by the OS (the existing pytest fixture `live_server` binds 0).
  No port conflict with parallel suites.
- **File system**: each suite writes to its own report sub-file.
  Analyzer reads `tests/fixtures/cc0_music/` (read-only). UI writes
  to `test-results/`. Generator writes to `tests/golden/reports/`.
  No write contention.
- **Subprocess fork safety**: both shell-out suites use
  `subprocess.run(capture_output=True)`, which is implemented via
  fork+exec with proper pipe plumbing — thread-safe in CPython.

### Output ordering

`format_summary` iterates `report.suites.items()` in dict insertion
order. The post-parallel reassembly explicitly inserts in canonical
order — `analyzer, generator, ui, section_fidelity` — so the human
summary and JSON report are byte-identical to the serial version
(modulo the wall-time-vs-sum-of-durations field).

### Determinism

The four suites read their own deterministic inputs (snapshots from disk
or fixed corpus). Parallel execution does not introduce shared mutable
state, so library_mean and per-fixture results are unchanged. The
existing 3-run determinism check (library_mean=2.0390 across 3 serial
runs) is the baseline; the new tests re-assert it across 3 parallel
runs.

## Alternatives considered

1. **`asyncio.gather` with `loop.run_in_executor`** — the orchestrator
   isn't async anywhere else in the project; introducing it for one
   call site would mean either making `run_gate` async (caller-breaking)
   or running an event loop just to await one gather. Rejected: no
   payoff vs. plain `ThreadPoolExecutor`.
2. **`multiprocessing.ProcessPoolExecutor`** — see fork safety
   discussion above. Rejected: no GIL benefit (suites already release
   the GIL inside C ext / subprocess), real macOS forking risk.
3. **Parallelize only analyzer + UI; serialize the others after** —
   simpler dispatch, but the simpler-still answer is "submit all four
   to the pool" since the fast ones cost nothing in either path.
   Rejected: minor code-clarity loss for zero operational benefit.
4. **Keep serial, optimize analyzer instead** — out of scope; even a
   30% analyzer speed-up would still leave UI as a serial blocker.

## Files touched

- **Modified**: `src/evaluation/acceptance_gate.py` — replace the
  4-line sequential dispatch in `run_gate` with a pool-based dispatch
  and canonical-order reassembly. Add a `parallel: bool = True`
  field to `GateOptions`.
- **Modified**: `tests/evaluation/test_gate_cli.py` — add three new
  tests:
  - `test_run_gate_parallel_dispatch` — mock the four suites with
    different sleep durations, assert wall time < sum of durations.
  - `test_run_gate_serial_path_unchanged` — set
    `GateOptions(parallel=False)`, verify suites run in canonical
    order with no concurrency.
  - `test_run_gate_canonical_ordering` — re-run with reversed mock
    completion times, verify the report still lists suites in
    canonical order.

## Regression surface

Public symbols modified:
- `GateOptions` — adds `parallel: bool = True` with a default. All
  existing call sites (`src/cli/evaluate.py:415`, all
  `tests/evaluation/test_gate_cli.py:124, 156, 176, 213, 311, 337`)
  construct `GateOptions` with keyword args; the new optional field
  is backward-compatible. **No callers updated** — all current
  callers get the new default behavior automatically, which is the
  intended speed-up.
- `run_gate` — internal dispatch changes; signature and return value
  unchanged. Same JSON report schema. Same exit codes.

Public symbols not modified:
- `SuiteResult`, `GateReport`, `_aggregate_exit_code`,
  `_write_report`, `format_summary`, `run_analyzer_suite`,
  `run_generator_suite`, `run_ui_suite`,
  `run_section_fidelity_suite` — untouched.

Callers grepped:
- `src/cli/evaluate.py` — constructs `GateOptions` and calls
  `run_gate`. Inherits new default. No code change required.
- `tests/evaluation/test_gate_cli.py` — same; existing tests with
  mocked suites still pass because the parallel path produces
  identical reports for instant-returning mocks.

## Historical echoes

`.wolf/cerebrum.md` Do-Not-Repeat:
- [2026-04-25] *xfail/skip is band-aid* — relevant. We must NOT mask
  parallel-induced flakiness with retries or skips. If parallel runs
  produce non-deterministic output, that's a real bug to fix.
- [2026-04-19] *Audit callers when modifying public symbols* —
  applied above (`GateOptions` constructor sites grepped, all
  backward-compatible).
- [2026-04-25] *Module-level state inheritance across runs* — relevant
  to thread-safety check: the four suites must not share module-level
  mutable state. `acceptance_gate.py` has no module-level mutables;
  the four suite functions write only to local `SuiteResult` objects
  they return. Confirmed clean.

`.wolf/buglog.json` matches:
- Multiple bug entries reference `acceptance_gate.py` for missing
  error handling — already addressed in current code with explicit
  `try/except` wrappers per suite. The parallel dispatch must
  preserve this: an exception inside a suite future should surface
  as `infra-error` SuiteResult on that suite, not crash the gate.
  Implementation captures suite-level exceptions in the future and
  converts to `SuiteResult(name, "infra-error", message=str(exc))`.

No prior parallelism work exists in this module — nothing to repeat.

## Test gap

- Unit: parallel dispatch + canonical ordering + serial fallback +
  exception-in-future handling (covered by new tests in
  `tests/evaluation/test_gate_cli.py`).
- Integration: existing `test_run_gate_*` tests already exercise the
  end-to-end path with mocked suites; they will run through the
  parallel dispatch by default and prove the report shape is
  unchanged.
- Live wall-time benchmark is captured in the PR description, not as
  a test — wall-time assertions in tests are flaky on shared CI
  runners.
- Determinism: 3-back-to-back parallel run check is captured in the
  PR description against the live CC0 corpus; encoding it as a test
  would require running the full analyzer suite and is out of scope
  for the test layer.
