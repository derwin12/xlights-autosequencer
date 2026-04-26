"""Acceptance-gate orchestrator.

Runs four suites against a corpus and aggregates results into a single
exit-code + JSON report:

1. Analyzer suite          — AnalyzerBaseline check for every fixture.
2. Generator suite         — existing quality calibration check (delegated).
3. UI suite                — pytest -m ui (Flask + Vite via conftest fixtures).
4. Section-fidelity suite  — library-mean agreement_score check.

Exit codes (highest-priority wins):
    8 — infrastructure failure (missing Playwright without --skip-ui,
         corpus download failed, unexpected exception)
    4 — no baseline for one or more required suites
    6 — at least one suite detected a regression
    0 — all suites pass
"""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.evaluation import analyzer_baseline
from src.evaluation.analyzer_baseline import (
    AnalyzerBaseline,
    BaselineMissingError,
    FixtureSnapshot,
    Violation,
)
from src.evaluation.corpus_resolver import CorpusEntry, resolve_corpus

EXIT_PASS = 0
EXIT_NO_BASELINE = 4
EXIT_REGRESSION = 6
EXIT_INFRA = 8

REPORTS_DIR = Path("tests/golden/reports")


@dataclass
class GateOptions:
    quick: bool = False
    skip_ui: bool = False
    fixture_slug: Optional[str] = None
    report_path: Optional[Path] = None
    analyzer_baseline_path: Path = analyzer_baseline.DEFAULT_BASELINE_PATH
    # Path resolved at run-time to avoid an import-time dependency on
    # section_fidelity (the gate module is imported by tests that don't
    # need the section-fidelity suite). None → use the module's default.
    section_fidelity_baseline_path: Optional[Path] = None
    # Run the independent suites concurrently via a ThreadPoolExecutor.
    # Default True — see openspec/changes/gate-parallelism/design.md for
    # the rationale (analyzer + UI are the long-poles; threads avoid
    # macOS fork-safety risks while still benefiting from C-extension
    # GIL release). Set False for debugging or on resource-constrained
    # boxes where parallel CPU + Playwright would thrash.
    parallel: bool = True


@dataclass
class SuiteResult:
    name: str
    status: str  # "pass" | "fail" | "skip" | "no-baseline" | "infra-error"
    fixtures_checked: int = 0
    violations: list[dict] = field(default_factory=list)
    message: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "fixtures_checked": self.fixtures_checked,
            "violations": list(self.violations),
            "message": self.message,
            "duration_seconds": round(self.duration_seconds, 3),
        }


@dataclass
class GateReport:
    started_at: str
    duration_seconds: float
    exit_code: int
    corpus: list[str]
    suites: dict[str, SuiteResult] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "started_at": self.started_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "exit_code": self.exit_code,
            "corpus": list(self.corpus),
            "suites": {name: r.to_dict() for name, r in self.suites.items()},
        }


# ---------- Analyzer suite ----------

def _snapshot_fixture_live(entry: CorpusEntry) -> FixtureSnapshot:
    """Run the full analyzer pipeline on one fixture; return its snapshot.

    Imported lazily so unit tests of the orchestrator don't pay the
    analyzer import cost unless they exercise this path.

    Schema v2 also captures `repetition_groups` (the SSM Chorus
    validator's output, which lives on HierarchyResult, not on
    timing_tracks). The legacy AnalysisRunner doesn't run SSM, so we
    invoke it here directly. Failures are non-fatal: a None
    repetition_groups field signals "SSM didn't run or errored" — the
    gate doesn't currently regression-check the field, just records it
    for forensic value.
    """
    from src.analyzer.audio import load
    from src.analyzer.runner import AnalysisRunner, default_algorithms
    from src.analyzer.self_similarity import compute_repetition_groups
    from src.evaluation.analyzer_baseline import TrackSnapshot

    runner = AnalysisRunner(algorithms=default_algorithms())
    result = runner.run(str(entry.path))
    algorithms = {
        t.algorithm_name: TrackSnapshot.from_track(t) for t in result.timing_tracks
    }

    repetition_groups: Optional[list[dict]] = None
    try:
        audio, sr, _meta = load(str(entry.path))
        groups = compute_repetition_groups(audio, sr)
        repetition_groups = [g.to_dict() for g in groups]
    except Exception as exc:
        print(f"  warning: SSM failed for {entry.slug}: {exc}", file=sys.stderr)
        repetition_groups = None

    return FixtureSnapshot(
        fixture_slug=entry.slug,
        algorithms=algorithms,
        repetition_groups=repetition_groups,
    )


def run_analyzer_suite(
    corpus: list[CorpusEntry],
    baseline_path: Path,
    *,
    snapshot_fn=None,
) -> SuiteResult:
    # Resolve snapshot function at call time so tests can patch the module-level
    # `_snapshot_fixture_live` and have the patch take effect.
    if snapshot_fn is None:
        snapshot_fn = _snapshot_fixture_live
    start = time.monotonic()
    try:
        baseline = analyzer_baseline.load(baseline_path)
    except BaselineMissingError as exc:
        return SuiteResult(
            "analyzer",
            status="no-baseline",
            message=str(exc),
            duration_seconds=time.monotonic() - start,
        )

    violations: list[Violation] = []
    for entry in corpus:
        if entry.source == "local":
            # Local corpus entries aren't in the CC0 baseline — skip silently.
            # They still run through the generator suite for benchmark value.
            continue
        current = snapshot_fn(entry)
        violations.extend(analyzer_baseline.check_fixture(baseline, entry.slug, current))

    return SuiteResult(
        "analyzer",
        status="fail" if violations else "pass",
        fixtures_checked=sum(1 for e in corpus if e.source != "local"),
        violations=[
            {
                "fixture_slug": v.fixture_slug,
                "algorithm_name": v.algorithm_name,
                "kind": v.kind,
                "detail": v.detail,
            }
            for v in violations
        ],
        duration_seconds=time.monotonic() - start,
    )


# ---------- Generator suite (delegates to existing check logic) ----------

def run_generator_suite(corpus: list[CorpusEntry]) -> SuiteResult:
    """Wrap `xlight-evaluate check` with the acceptance-gate corpus.

    The existing generator baseline treats the corpus as a filesystem directory
    with MP3s. We materialize a view to the CC0 directory (already the default)
    and shell out to the check logic.
    """
    start = time.monotonic()
    # Generator baseline comparison requires a fully generated .xsq per fixture,
    # which requires the generator pipeline. Delegate to `xlight-evaluate check`
    # as a subprocess so the gate preserves the existing exit-code contract
    # rather than re-implementing it.
    #
    # Resolve `xlight-evaluate` against the same Python that's running the gate
    # — the entry point lives in the same console-script bin directory as
    # `python` and `xlight-analyze`. Without this, `subprocess.run(["xlight-
    # evaluate", ...])` resolves against the caller's PATH, which fails with
    # FileNotFoundError when the gate is invoked via the .venv-vamp/bin/
    # absolute path (a common pattern: `PATH=".venv-vamp/bin:$PATH"
    # .venv-vamp/bin/xlight-evaluate gate` would no longer be required).
    cmd_path = Path(sys.executable).parent / "xlight-evaluate"
    cmd = [str(cmd_path) if cmd_path.exists() else "xlight-evaluate", "check"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return SuiteResult(
            "generator", status="infra-error",
            message=f"xlight-evaluate check failed to run: {exc}",
            duration_seconds=time.monotonic() - start,
        )

    duration = time.monotonic() - start

    if proc.returncode == 0:
        return SuiteResult(
            "generator", status="pass",
            fixtures_checked=len([e for e in corpus if e.source == "cc0"]),
            duration_seconds=duration,
        )
    if proc.returncode == 4:
        return SuiteResult(
            "generator", status="no-baseline",
            message=(proc.stdout + proc.stderr).strip()[:500],
            duration_seconds=duration,
        )
    if proc.returncode == 6:
        return SuiteResult(
            "generator", status="fail",
            message=(proc.stdout + proc.stderr).strip()[:500],
            duration_seconds=duration,
        )
    return SuiteResult(
        "generator", status="infra-error",
        message=f"unexpected exit code {proc.returncode}: {(proc.stdout + proc.stderr)[:300]}",
        duration_seconds=duration,
    )


# ---------- UI suite ----------

def _playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def run_ui_suite(skip: bool = False, quick: bool = False) -> SuiteResult:
    """Run the UI flow suite.

    - skip=True: do nothing; report `skip`. Used for --skip-ui or offline runs.
    - quick=True: run only the content flow (-m 'ui and content') — one
      upload + real analysis + manifest assertions, ~90s.
    - default: run all UI flows (-m ui) — smoke flows + content flow, ~2-3 min.
    """
    start = time.monotonic()
    if skip:
        return SuiteResult("ui", status="skip", message="--skip-ui passed")

    if not _playwright_available():
        return SuiteResult(
            "ui", status="infra-error",
            message="playwright not installed; pass --skip-ui to run without the UI suite",
            duration_seconds=time.monotonic() - start,
        )

    marker = "ui and content" if quick else "ui"
    # Auto-capture artifacts on failure for post-hoc debugging:
    #   --screenshot=only-on-failure       → PNG of final state
    #   --video=retain-on-failure          → WebM of full run
    #   --tracing=retain-on-failure        → Playwright trace.zip (timeline replay)
    # Lands under test-results/<test-id>/. View traces with `playwright show-trace`.
    cmd = [
        "pytest", "-m", marker, "--tb=short", "-v",
        "--screenshot=only-on-failure",
        "--video=retain-on-failure",
        "--tracing=retain-on-failure",
        "--full-page-screenshot",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return SuiteResult(
            "ui", status="infra-error",
            message=f"pytest -m ui failed to run: {exc}",
            duration_seconds=time.monotonic() - start,
        )

    duration = time.monotonic() - start
    if proc.returncode == 0:
        return SuiteResult("ui", status="pass", duration_seconds=duration)
    if proc.returncode == 5:
        return SuiteResult(
            "ui", status="skip",
            message="no UI tests collected (expected in environments without UI flows)",
            duration_seconds=duration,
        )
    return SuiteResult(
        "ui", status="fail",
        message=(proc.stdout + proc.stderr).strip()[-2000:],
        duration_seconds=duration,
    )


# ---------- Section-fidelity suite ----------

def run_section_fidelity_suite(
    corpus: list[CorpusEntry],
    baseline_path: Path,
) -> SuiteResult:
    """Compute library-mean agreement_score over the corpus and compare to baseline.

    Per design D2 in
    ``openspec/changes/agreement-score-operationalization/design.md`` the
    suite lives parallel to analyzer/generator/UI rather than being folded
    into ``run_analyzer_suite`` — a per-fixture check and a corpus-wide
    aggregate have different failure modes and merit separate baselines.

    Tolerance: library_mean must stay within ``DEFAULT_TOLERANCE`` of the
    baseline (drop only — a higher mean is always a pass).
    """
    from src.evaluation import section_fidelity

    start = time.monotonic()
    if not baseline_path.exists():
        return SuiteResult(
            "section_fidelity",
            status="no-baseline",
            message=(
                f"baseline not found: {baseline_path}. "
                "Run `xlight-evaluate snapshot-section-fidelity` first."
            ),
            duration_seconds=time.monotonic() - start,
        )

    try:
        baseline = section_fidelity.load_baseline(baseline_path)
    except (json.JSONDecodeError, OSError) as exc:
        return SuiteResult(
            "section_fidelity",
            status="infra-error",
            message=f"failed to read baseline {baseline_path}: {exc}",
            duration_seconds=time.monotonic() - start,
        )

    stories = section_fidelity.load_stories_for_corpus(corpus)
    if not stories:
        # Per spec: "Fixture without _story.json is skipped without failure".
        # If *every* fixture is missing a story we can't compute a mean —
        # report a skip rather than a regression.
        return SuiteResult(
            "section_fidelity",
            status="skip",
            message="no _story.json files found for any corpus fixture",
            fixtures_checked=0,
            duration_seconds=time.monotonic() - start,
        )

    library_mean = section_fidelity.compute_library_mean(stories)
    breakdown = section_fidelity.compute_per_fixture_breakdown(stories)
    delta = library_mean - baseline.library_mean
    tolerance = section_fidelity.DEFAULT_TOLERANCE

    violations: list[dict] = []
    if delta < -tolerance:
        violations.append({
            "fixture_slug": "<library>",
            "algorithm_name": "library_mean",
            "kind": "regression",
            "detail": (
                f"library_mean {library_mean:.4f} below baseline "
                f"{baseline.library_mean:.4f} by {-delta:.4f} "
                f"(tolerance {tolerance})"
            ),
        })
        # Per-fixture deltas to point at *which* song moved.
        for slug, summary in breakdown.items():
            base_summary = baseline.per_fixture.get(slug)
            if base_summary is None:
                continue
            base_mean = float(base_summary.get("mean_score", 0.0))
            cur_mean = float(summary["mean_score"])
            f_delta = cur_mean - base_mean
            if f_delta < -tolerance:
                violations.append({
                    "fixture_slug": slug,
                    "algorithm_name": "mean_score",
                    "kind": "regression",
                    "detail": (
                        f"mean_score {cur_mean:.4f} below baseline "
                        f"{base_mean:.4f} by {-f_delta:.4f}"
                    ),
                })

    status = "fail" if violations else "pass"
    message = (
        f"library_mean={library_mean:.4f} "
        f"(baseline={baseline.library_mean:.4f}, delta={delta:+.4f}, "
        f"tolerance={tolerance})"
    )
    return SuiteResult(
        "section_fidelity",
        status=status,
        fixtures_checked=len(stories),
        violations=violations,
        message=message,
        duration_seconds=time.monotonic() - start,
    )


# ---------- Top-level orchestrator ----------

def _aggregate_exit_code(suites: dict[str, SuiteResult]) -> int:
    statuses = [s.status for s in suites.values()]
    if "infra-error" in statuses:
        return EXIT_INFRA
    if "no-baseline" in statuses:
        return EXIT_NO_BASELINE
    if "fail" in statuses:
        return EXIT_REGRESSION
    return EXIT_PASS


def _run_suite_safe(name: str, fn: Callable[[], SuiteResult]) -> SuiteResult:
    """Run a suite callable; convert any unexpected exception into an
    `infra-error` SuiteResult.

    The `run_*_suite` functions are designed to handle their own expected
    failure modes (subprocess errors, missing baselines, etc.) and return
    a SuiteResult — they should never raise. But the parallel dispatch
    path must not let an unexpected exception (e.g. an OOM in a C
    extension surfacing as a Python exception) crash the whole gate and
    lose the partial results from the other suites. Wrap defensively.
    """
    start = time.monotonic()
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — intentional broad catch
        return SuiteResult(
            name,
            status="infra-error",
            message=f"unexpected exception in {name} suite: {exc!r}",
            duration_seconds=time.monotonic() - start,
        )


# Canonical order for assembling the suites dict in run_gate. Order here
# determines JSON output field order and the human-readable summary line
# ordering, which CI logs and humans grep against. Keep in sync with the
# dispatch list in run_gate.
_CANONICAL_SUITE_ORDER: tuple[str, ...] = ("analyzer", "generator", "ui")


def _dispatch_suites(
    plan: list[tuple[str, Callable[[], SuiteResult]]],
    *,
    parallel: bool,
) -> dict[str, SuiteResult]:
    """Run a list of (name, callable) suite tasks; return canonical-ordered results.

    - parallel=True: submit all tasks to a ThreadPoolExecutor sized to the
      task count, wait for every future, then re-assemble in
      `_CANONICAL_SUITE_ORDER`. Names not in the canonical list are
      appended at the end in plan order.
    - parallel=False: run sequentially in plan order.

    Both paths route every suite through `_run_suite_safe` so an
    unexpected exception in one suite does not abort the others.
    """
    results: dict[str, SuiteResult] = {}

    if parallel and len(plan) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(plan)) as ex:
            future_to_name = {
                ex.submit(_run_suite_safe, name, fn): name for name, fn in plan
            }
            for fut in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[fut]
                # _run_suite_safe never raises — but defend against future
                # changes by re-wrapping here too.
                results[name] = _run_suite_safe(name, fut.result)
    else:
        for name, fn in plan:
            results[name] = _run_suite_safe(name, fn)

    # Reassemble in canonical order so the JSON report and human summary
    # are byte-identical to the serial ordering regardless of which
    # future completed first.
    ordered: dict[str, SuiteResult] = {}
    for name in _CANONICAL_SUITE_ORDER:
        if name in results:
            ordered[name] = results.pop(name)
    # Anything left over (unrecognized suite name) goes at the end in
    # plan order.
    for name, _fn in plan:
        if name in results:
            ordered[name] = results.pop(name)
    return ordered


def run_gate(options: GateOptions) -> GateReport:
    start_wall = time.monotonic()
    started_iso = datetime.now(timezone.utc).isoformat()

    # Resolve corpus up front — a corpus-resolution error is infra.
    try:
        corpus = resolve_corpus(
            quick=options.quick,
            fixture_slug=options.fixture_slug,
        )
    except (FileNotFoundError, ValueError) as exc:
        report = GateReport(
            started_at=started_iso,
            duration_seconds=time.monotonic() - start_wall,
            exit_code=EXIT_INFRA,
            corpus=[],
            suites={
                "corpus": SuiteResult(
                    "corpus", status="infra-error", message=str(exc)
                )
            },
        )
        _write_report(report, options.report_path)
        return report

    # Build the dispatch plan. Each tuple is (suite_name, zero-arg
    # callable). The callables capture `corpus` and `options` at the same
    # point the serial implementation did.
    plan: list[tuple[str, Callable[[], SuiteResult]]] = [
        # Analyzer suite — quick mode still exercises the analyzer; it
        # just uses one fixture to save time.
        ("analyzer", lambda: run_analyzer_suite(corpus, options.analyzer_baseline_path)),
        # Generator suite.
        ("generator", lambda: run_generator_suite(corpus)),
        # UI suite — --quick runs only the content flow (smoke + assertions
        # on one fixture); full mode runs all flows.
        ("ui", lambda: run_ui_suite(skip=options.skip_ui, quick=options.quick)),
    ]

    suites = _dispatch_suites(plan, parallel=options.parallel)

    # Section-fidelity suite — defends the corpus-wide library-mean
    # `agreement_score` against silent regression. Cheap (just JSON
    # aggregation), so it always runs.
    from src.evaluation import section_fidelity as _sf
    sf_baseline = (
        options.section_fidelity_baseline_path
        if options.section_fidelity_baseline_path is not None
        else _sf.DEFAULT_BASELINE_PATH
    )
    suites["section_fidelity"] = run_section_fidelity_suite(corpus, sf_baseline)

    exit_code = _aggregate_exit_code(suites)
    report = GateReport(
        started_at=started_iso,
        duration_seconds=time.monotonic() - start_wall,
        exit_code=exit_code,
        corpus=[e.slug for e in corpus],
        suites=suites,
    )
    _write_report(report, options.report_path)
    return report


def _write_report(report: GateReport, explicit_path: Optional[Path]) -> Path:
    if explicit_path is not None:
        path = explicit_path
    else:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = report.started_at.replace(":", "-").replace("+00-00", "Z").replace(".", "-")
        path = REPORTS_DIR / f"gate-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    return path


def format_summary(report: GateReport) -> str:
    """Human-readable summary table for stdout."""
    lines = [
        f"Acceptance gate — {report.started_at}",
        f"Corpus: {', '.join(report.corpus) or '(empty)'}",
        f"Duration: {report.duration_seconds:.1f}s",
        "",
        f"{'SUITE':<12} {'STATUS':<14} {'CHECKED':<8} {'DURATION':<10}",
        "-" * 50,
    ]
    for name, suite in report.suites.items():
        lines.append(
            f"{name:<12} {suite.status.upper():<14} "
            f"{suite.fixtures_checked:<8} {suite.duration_seconds:>7.1f}s"
        )
        if suite.message:
            lines.append(f"    → {suite.message}")
        for v in suite.violations[:5]:
            lines.append(
                f"    × {v['fixture_slug']}/{v['algorithm_name']} ({v['kind']}): {v['detail']}"
            )
        if len(suite.violations) > 5:
            lines.append(f"    … and {len(suite.violations) - 5} more")

    lines.append("")
    verdict = {
        EXIT_PASS: "PASS — all suites passed",
        EXIT_REGRESSION: "FAIL — regression detected",
        EXIT_NO_BASELINE: "NO-BASELINE — run snapshot first",
        EXIT_INFRA: "INFRA — setup problem, re-run",
    }.get(report.exit_code, f"UNKNOWN ({report.exit_code})")
    lines.append(f"Verdict: {verdict} (exit {report.exit_code})")
    return "\n".join(lines)
