"""xlight-evaluate microscope — visual-quality measurement subcommand group.

Four subcommands:

* ``run <audio_path>`` — single-song measurement.
* ``panel`` — multi-song panel measurement.
* ``baseline`` — copies metric files into the golden directory after
  verifying the sensitivity gate.
* ``sensitivity`` — runs the sensitivity probes and writes
  ``tests/golden/microscope/sensitivity_passed.json`` on success.

Registered on the existing ``xlight-evaluate`` Click CLI; see
``src/cli/evaluate.py`` for the registration call.
"""
from __future__ import annotations

import datetime
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import click

from src.evaluation.models import MetricValue


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_LAYOUT = "tests/fixtures/reference/layout.xml"
_DEFAULT_OUTPUT_DIR = "./microscope-out/"
_DEFAULT_MANIFEST = "tests/fixtures/reference/panel_manifest.json"
_DEFAULT_GOLDEN_DIR = "tests/golden/microscope/"
_DEFAULT_INPUT_DIR = "./microscope-out/microscope/"
_SENSITIVITY_PROOF_PATH = Path("tests/golden/microscope/sensitivity_passed.json")

# Paths whose newer commits invalidate the sensitivity proof.
_STALENESS_CONE = (
    "src/evaluation/metrics/",
    "src/evaluation/xsq_reader.py",
    "src/effects/builtin_effects.json",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_metric_value(value: object) -> str:
    """Render a metric value for the per-song table."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}"
    return str(value)


def _print_metric_table(slug: str, metrics: dict[str, MetricValue]) -> None:
    """Print a fixed-width per-song metric table to stdout."""
    headers = ("Metric", "Value", "Kind", "Reliability")
    rows: list[tuple[str, str, str, str]] = []
    for name in sorted(metrics):
        mv = metrics[name]
        rows.append(
            (
                name,
                _format_metric_value(mv.value),
                mv.kind,
                mv.reliability or "",
            )
        )

    widths = [len(h) for h in headers]
    for cells in rows:
        for i, cell in enumerate(cells):
            if len(cell) > widths[i]:
                widths[i] = len(cell)

    align_left = {0, 2, 3}

    def _fmt(cells: tuple[str, ...]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            if i in align_left:
                parts.append(cell.ljust(widths[i]))
            else:
                parts.append(cell.rjust(widths[i]))
        return "  ".join(parts).rstrip()

    click.echo(f"\n=== {slug} ===")
    click.echo(_fmt(headers))
    click.echo("  ".join("-" * w for w in widths))
    for cells in rows:
        click.echo(_fmt(cells))


def _write_metrics_json(result, output_dir: Path) -> Path:
    """Write a result's ``to_dict()`` to ``<output_dir>/microscope/<slug>/metrics.json``.

    The microscope runner already creates the per-slug directory under
    ``<output_dir>/microscope/<slug>/`` for the generated XSQ; we re-use
    that directory for ``metrics.json``.
    """
    target_dir = output_dir / "microscope" / result.slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "metrics.json"
    target_path.write_text(
        json.dumps(result.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    return target_path


def _print_panel_aggregate(results: list) -> None:
    """Print a one-row aggregate (mean across songs) of every scalar metric."""
    if not results:
        return

    metric_names = sorted({name for r in results for name in r.metrics})
    aggregates: dict[str, float] = {}
    for name in metric_names:
        values: list[float] = []
        for r in results:
            mv = r.metrics.get(name)
            if mv is None or mv.kind != "scalar":
                continue
            v = mv.value
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                values.append(float(v))
        if values:
            aggregates[name] = statistics.fmean(values)

    if not aggregates:
        return

    click.echo("\n=== Aggregate (mean across songs) ===")
    headers = ("Metric", "Mean")
    width0 = max(len(headers[0]), max(len(n) for n in aggregates))
    width1 = max(
        len(headers[1]),
        max(len(f"{v:.4f}") for v in aggregates.values()),
    )
    click.echo(f"{headers[0].ljust(width0)}  {headers[1].rjust(width1)}")
    click.echo(f"{'-' * width0}  {'-' * width1}")
    for name in sorted(aggregates):
        click.echo(f"{name.ljust(width0)}  {f'{aggregates[name]:.4f}'.rjust(width1)}")


def _latest_cone_commit_timestamp(repo_root: Path) -> int | None:
    """Return the committer timestamp (UTC seconds) of the most recent commit
    touching any file in the staleness cone, or ``None`` on git failure.
    """
    cmd = [
        "git",
        "log",
        "-1",
        "--format=%ct",
        "--",
        *_STALENESS_CONE,
    ]
    try:
        completed = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    out = completed.stdout.strip()
    if not out:
        return None
    try:
        return int(out)
    except ValueError:
        return None


def _parse_run_at(proof: dict) -> datetime.datetime | None:
    raw = proof.get("run_at")
    if not isinstance(raw, str):
        return None
    # Tolerate trailing ``Z`` ISO 8601 form.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group(name="microscope")
def microscope_group() -> None:
    """Visual-quality microscope — per-song metric measurement."""


@microscope_group.command(name="run")
@click.argument("audio_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--layout", "layout_path", type=click.Path(),
              default=_DEFAULT_LAYOUT, show_default=True,
              help="xLights layout XML for prop classification.")
@click.option("--output-dir", "output_dir", type=click.Path(),
              default=_DEFAULT_OUTPUT_DIR, show_default=True,
              help="Output root; XSQ + metrics.json go under "
                   "<output-dir>/microscope/<slug>/.")
@click.option("--curves-mode", type=str, default="none", show_default=True,
              help="GenerationConfig.curves_mode override.")
@click.option("--variation-seed", type=int, default=42, show_default=True,
              help="GenerationConfig.variation_seed override.")
@click.option("--baseline", "baseline_dir", type=click.Path(), default=None,
              help="If given, also print a diff against per-song baselines "
                   "under this directory.")
def run_command(
    audio_path: str,
    layout_path: str,
    output_dir: str,
    curves_mode: str,
    variation_seed: int,
    baseline_dir: str | None,
) -> None:
    """Measure visual quality on a single song."""
    from src.microscope.diff import diff_results
    from src.microscope.runner import run_song

    config_overrides = {
        "curves_mode": curves_mode,
        "variation_seed": variation_seed,
    }
    output_dir_path = Path(output_dir)

    result = run_song(
        audio_path=audio_path,
        layout_path=layout_path,
        output_dir=output_dir_path,
        config_overrides=config_overrides,
    )

    metrics_path = _write_metrics_json(result, output_dir_path)
    _print_metric_table(result.slug, result.metrics)
    click.echo(f"\nMetrics written to {metrics_path}")

    if baseline_dir is not None:
        report = diff_results([result], Path(baseline_dir))
        click.echo("\n=== Diff vs baseline ===")
        click.echo(report.format_table())

    sys.exit(0)


@microscope_group.command(name="panel")
@click.option("--manifest", "manifest_path", type=click.Path(),
              default=_DEFAULT_MANIFEST, show_default=True,
              help="Panel manifest JSON describing the song slugs.")
@click.option("--layout", "layout_path", type=click.Path(),
              default=_DEFAULT_LAYOUT, show_default=True,
              help="xLights layout XML for prop classification.")
@click.option("--output-dir", "output_dir", type=click.Path(),
              default=_DEFAULT_OUTPUT_DIR, show_default=True,
              help="Output root for XSQ + metrics.json.")
@click.option("--parallel/--no-parallel", default=False,
              help="Run panel songs in a process pool.")
@click.option("--baseline", "baseline_dir", type=click.Path(), default=None,
              help="If given, also print a diff against per-song baselines.")
@click.option("--variation-seed", type=int, default=42, show_default=True,
              help="GenerationConfig.variation_seed override.")
def panel_command(
    manifest_path: str,
    layout_path: str,
    output_dir: str,
    parallel: bool,
    baseline_dir: str | None,
    variation_seed: int,
) -> None:
    """Measure visual quality across the reference panel."""
    from src.microscope.diff import diff_results
    from src.microscope.panel import run_panel

    manifest = Path(manifest_path)
    if not manifest.exists():
        click.echo(f"Manifest not found: {manifest}", err=True)
        sys.exit(2)

    output_dir_path = Path(output_dir)

    config_overrides = {
        "variation_seed": variation_seed,
        "curves_mode": "none",
    }

    results = run_panel(
        manifest,
        output_dir_path,
        config_overrides=config_overrides,
        parallel=parallel,
    )

    for result in results:
        metrics_path = _write_metrics_json(result, output_dir_path)
        _print_metric_table(result.slug, result.metrics)
        click.echo(f"Metrics written to {metrics_path}")

    _print_panel_aggregate(results)

    if baseline_dir is not None:
        report = diff_results(results, Path(baseline_dir))
        click.echo("\n=== Diff vs baseline ===")
        click.echo(report.format_table())

    sys.exit(0)


@microscope_group.command(name="baseline")
@click.option("--input-dir", "input_dir", type=click.Path(),
              default=_DEFAULT_INPUT_DIR, show_default=True,
              help="Directory containing <slug>/metrics.json files to "
                   "promote to the golden dir.")
@click.option("--golden-dir", "golden_dir", type=click.Path(),
              default=_DEFAULT_GOLDEN_DIR, show_default=True,
              help="Destination golden directory.")
def baseline_command(input_dir: str, golden_dir: str) -> None:
    """Promote per-song metrics.json files into the golden directory.

    Refuses to run unless the sensitivity proof exists and is at least as
    recent as the most recent commit touching the staleness cone (the
    metric implementations, the XSQ reader, and the effect catalog).
    """
    proof_path = _SENSITIVITY_PROOF_PATH
    if not proof_path.exists():
        click.echo(
            f"Refusing to write a baseline: {proof_path} is missing.\n"
            f"Run `xlight-evaluate microscope sensitivity` first to "
            f"prove the metrics are responsive.",
            err=True,
        )
        sys.exit(1)

    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        click.echo(
            f"Refusing to write a baseline: could not read sensitivity "
            f"proof at {proof_path}: {exc}",
            err=True,
        )
        sys.exit(1)

    run_at = _parse_run_at(proof)
    if run_at is None:
        click.echo(
            f"Refusing to write a baseline: sensitivity proof at "
            f"{proof_path} is missing or has an unparseable `run_at` "
            f"field. Re-run `xlight-evaluate microscope sensitivity`.",
            err=True,
        )
        sys.exit(1)

    repo_root = Path.cwd()
    cone_ts = _latest_cone_commit_timestamp(repo_root)
    if cone_ts is None:
        click.echo(
            "Refusing to write a baseline: could not query git for the "
            "most recent commit touching the staleness cone "
            f"({', '.join(_STALENESS_CONE)}). Is this a git repository "
            "with at least one commit?",
            err=True,
        )
        sys.exit(1)

    cone_dt = datetime.datetime.fromtimestamp(cone_ts, tz=datetime.timezone.utc)
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=datetime.timezone.utc)

    if cone_dt > run_at:
        click.echo(
            f"Refusing to write a baseline: a commit touching the "
            f"staleness cone is newer than the sensitivity proof.\n"
            f"  proof run_at:    {run_at.isoformat()}\n"
            f"  latest cone commit: {cone_dt.isoformat()}\n"
            f"Re-run `xlight-evaluate microscope sensitivity` before "
            f"committing a new baseline.",
            err=True,
        )
        sys.exit(1)

    input_root = Path(input_dir)
    if not input_root.exists():
        click.echo(f"Input directory not found: {input_root}", err=True)
        sys.exit(1)

    golden_root = Path(golden_dir)
    golden_root.mkdir(parents=True, exist_ok=True)

    copied = 0
    for child in sorted(input_root.iterdir()):
        if not child.is_dir():
            continue
        metrics_path = child / "metrics.json"
        if not metrics_path.exists():
            continue
        dest_dir = golden_root / child.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(metrics_path, dest_dir / "baseline.json")
        copied += 1

    click.echo(
        f"Baseline updated for {copied} song(s). "
        f"Run 'git add {golden_root}/ && git commit' to persist."
    )
    sys.exit(0)


@microscope_group.command(name="sensitivity")
@click.option("--manifest", "manifest_path", type=click.Path(),
              default=_DEFAULT_MANIFEST, show_default=True,
              help="Panel manifest JSON describing the song slugs.")
@click.option("--layout", "layout_path", type=click.Path(),
              default=_DEFAULT_LAYOUT, show_default=True,
              help="xLights layout XML for prop classification.")
@click.option("--output-dir", "output_dir", type=click.Path(),
              default=_DEFAULT_OUTPUT_DIR, show_default=True,
              help="Working directory for sensitivity-probe outputs.")
def sensitivity_command(
    manifest_path: str,
    layout_path: str,
    output_dir: str,
) -> None:
    """Run sensitivity probes and write the proof file on success."""
    from src.microscope.sensitivity import run_sensitivity

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    slugs = manifest.get("slugs") or []
    if not slugs:
        click.echo(f"Manifest has no slugs: {manifest_path}", err=True)
        sys.exit(2)
    audio_fixture = Path("tests/fixtures/cc0_music") / f"{slugs[0]}.mp3"
    if not audio_fixture.is_file():
        click.echo(
            f"Audio fixture missing: {audio_fixture}. "
            f"Run `python tests/validation/download_fixtures.py` first.",
            err=True,
        )
        sys.exit(2)

    report = run_sensitivity(
        audio_fixture,
        Path(layout_path),
        Path(output_dir),
    )

    for r in report.results:
        marker = "PASS" if r.passed else "FAIL"
        click.echo(f"  [{marker}] {r.probe_name}")

    if not report.all_passed:
        click.echo("Sensitivity probes FAILED — proof file not written.", err=True)
        sys.exit(6)

    _SENSITIVITY_PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SENSITIVITY_PROOF_PATH.write_text(
        json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    click.echo(f"Sensitivity proof written: {_SENSITIVITY_PROOF_PATH}")
    sys.exit(0)
