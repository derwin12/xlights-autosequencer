"""xlight-evaluate CLI — quality calibration subcommands."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from src.evaluation.models import MetricValue, SequenceSummary


@click.group()
def cli() -> None:
    """xlight-evaluate — quality calibration harness."""


def main() -> None:
    cli()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _import_all_metrics() -> None:
    """Import all metric modules to populate the registry."""
    import src.evaluation.metrics.pacing  # noqa: F401
    import src.evaluation.metrics.palette  # noqa: F401
    import src.evaluation.metrics.effects  # noqa: F401
    import src.evaluation.metrics.alignment  # noqa: F401
    import src.evaluation.metrics.sections  # noqa: F401
    import src.evaluation.metrics.internal  # noqa: F401


def _compute_metrics_for_summary(
    summary: SequenceSummary,
    audio_context: dict,
) -> list[MetricValue]:
    """Compute all registered metrics for a SequenceSummary.

    Each metric is called with the appropriate arguments drawn from audio_context.
    For v0, audio_context contains empty beats/energy when no analysis is available.
    """
    from src.evaluation.metrics import get_registry

    registry = get_registry()
    results: list[MetricValue] = []

    beats: list[int] = audio_context.get("beats", [])
    energy_curve = audio_context.get("energy_curve", [])
    sections = audio_context.get("sections", None)
    window_ms: int = audio_context.get("window_ms", 500)

    for name, defn in registry.items():
        try:
            # Dispatch by metric name — each has a known signature
            if name == "placements_per_minute":
                mv = defn.compute(summary)
            elif name == "density_energy_correlation":
                mv = defn.compute(summary, {"energy_curve": energy_curve, "window_ms": window_ms})
            elif name == "palette_top5_colors":
                mv = defn.compute(summary)
            elif name == "per_section_palette_diversity":
                mv = defn.compute(summary, sections)
            elif name == "effect_type_histogram":
                mv = defn.compute(summary)
            elif name == "beat_alignment_pct":
                mv = defn.compute(summary, beats)
            elif name == "section_transition_delta":
                mv = defn.compute(summary, sections)
            elif name == "tier_utilization":
                mv = defn.compute(summary, sections)
            elif name == "theme_assignment_consistency":
                mv = defn.compute(summary, sections)
            else:
                # Unknown metric — try calling with just summary
                mv = defn.compute(summary)
        except Exception as exc:
            # Metric computation failure produces a None-value entry
            from src.evaluation.models import MetricValue
            mv = MetricValue(
                name=name,
                kind="scalar",
                value=None,
                payload={"error": str(exc)},
                reliability="reduced",
            )

        results.append(mv)

    return results


def _run_corpus(corpus_dir: str) -> tuple[dict[str, list], list[str]]:
    """Load corpus and generate metrics for each measurable song.

    Returns:
        (song_metrics, generator_errors)
        song_metrics: dict mapping song_id -> list[MetricValue]
        generator_errors: list of error messages for songs that failed
    """
    import src.evaluation.generator_runner as generator_runner
    from src.evaluation.corpus import Corpus
    from src.evaluation.xsq_reader import parse_bytes

    _import_all_metrics()

    manifest_path = Path(corpus_dir) / "manifest.json"
    corpus = Corpus(manifest_path)

    song_metrics: dict = {}
    generator_errors: list[str] = []

    from src.evaluation.compare import build_audio_context

    for song_id in corpus.measurable_songs():
        mp3_path = corpus.mp3_path_for_song(song_id)
        audio_hash = corpus.audio_hash_for_song(song_id)

        try:
            xsq_bytes = generator_runner.run(
                song_id=song_id,
                audio_path=mp3_path,
                audio_hash=audio_hash,
            )
        except generator_runner.GeneratorError as exc:
            generator_errors.append(f"{song_id}: {exc}")
            continue

        audio_context = build_audio_context(mp3_path)
        summary = parse_bytes(xsq_bytes, song_id=song_id, source_label="ours")
        metrics = _compute_metrics_for_summary(summary, audio_context)
        song_metrics[song_id] = metrics

    return song_metrics, generator_errors


# ---------------------------------------------------------------------------
# check subcommand
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--corpus",
    default="tests/golden/pro_reference",
    type=click.Path(),
    help="Corpus directory containing manifest.json",
)
@click.option(
    "--baseline",
    default="tests/golden/baseline.json",
    type=click.Path(),
    help="Baseline JSON path",
)
def check(corpus: str, baseline: str) -> None:
    """Check current generator metrics against a saved baseline."""
    from src.evaluation.baseline import (
        BaselineMissingError,
        BaselineSchemaError,
        compare_against_baseline,
        load_baseline,
    )
    from src.evaluation.metrics import get_registry

    # Run the corpus
    song_metrics, generator_errors = _run_corpus(corpus)

    if generator_errors:
        for err in generator_errors:
            click.echo(f"[SKIP] Generator error — {err}")
        sys.exit(3)

    # Load baseline
    baseline_path = Path(baseline)
    try:
        baseline_dict = load_baseline(baseline_path)
    except BaselineMissingError as exc:
        click.echo(f"No baseline found: {exc}")
        sys.exit(4)
    except BaselineSchemaError as exc:
        click.echo(f"Baseline schema mismatch: {exc}")
        sys.exit(5)

    registry = get_registry()
    compare_result = compare_against_baseline(baseline_dict, song_metrics, registry)

    if compare_result.song_count_mismatch:
        baseline_songs = compare_result.baseline_songs
        current_songs = compare_result.current_songs
        click.echo(
            f"Song count mismatch: baseline has {len(baseline_songs)} songs, "
            f"corpus produced {len(current_songs)}."
        )
        only_in_baseline = baseline_songs - current_songs
        only_in_current = current_songs - baseline_songs
        if only_in_baseline:
            click.echo(f"  In baseline only: {sorted(only_in_baseline)}")
        if only_in_current:
            click.echo(f"  In corpus only:   {sorted(only_in_current)}")
        sys.exit(7)

    if compare_result.violations:
        click.echo(f"FAIL — {len(compare_result.violations)} regression(s) detected:")
        for v in compare_result.violations:
            click.echo(
                f"  {v.song_id}  {v.metric_name}: "
                f"baseline={v.baseline_value:.4f}, "
                f"current={v.current_value:.4f}, "
                f"delta={v.delta:+.4f}  ({v.tolerance_str})"
            )
        sys.exit(6)

    click.echo(f"PASS — {len(song_metrics)} song(s) checked, all metrics within tolerance.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# snapshot subcommand
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--corpus",
    default="tests/golden/pro_reference",
    type=click.Path(),
    help="Corpus directory containing manifest.json",
)
@click.option(
    "--baseline",
    default="tests/golden/baseline.json",
    type=click.Path(),
    help="Output baseline JSON path",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite even if the new snapshot would regress against the existing baseline.",
)
def snapshot(corpus: str, baseline: str, force: bool) -> None:
    """Capture a new baseline snapshot from the current generator output."""
    from src.evaluation.baseline import (
        BaselineMissingError,
        BaselineSchemaError,
        compare_against_baseline,
        load_baseline,
        write_baseline,
    )
    from src.evaluation.metrics import get_registry

    # Run the corpus
    song_metrics, generator_errors = _run_corpus(corpus)

    if generator_errors:
        for err in generator_errors:
            click.echo(f"[SKIP] Generator error — {err}")
        sys.exit(3)

    # Without --force: dry-run compare against the existing baseline (if any)
    if not force:
        baseline_path = Path(baseline)
        try:
            existing_baseline = load_baseline(baseline_path)
            registry = get_registry()
            compare_result = compare_against_baseline(existing_baseline, song_metrics, registry)

            if compare_result.violations:
                click.echo(
                    f"Would regress on {len(compare_result.violations)} metric(s) — "
                    f"use --force to overwrite anyway:"
                )
                for v in compare_result.violations:
                    click.echo(
                        f"  {v.song_id}  {v.metric_name}: "
                        f"baseline={v.baseline_value:.4f} → "
                        f"current={v.current_value:.4f}  ({v.tolerance_str})"
                    )
                sys.exit(8)
        except (BaselineMissingError, BaselineSchemaError):
            # No existing baseline or incompatible schema — proceed with write
            pass

    write_baseline(song_metrics, Path(baseline))
    click.echo(f"Baseline written to {baseline} ({len(song_metrics)} song(s)).")
    sys.exit(0)


# ---------------------------------------------------------------------------
# compare subcommand
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--corpus",
    default="tests/golden/pro_reference",
    type=click.Path(),
    help="Corpus directory containing manifest.json",
)
@click.option(
    "--json",
    "json_only",
    is_flag=True,
    default=False,
    help="Suppress terminal summary; emit only JSON report path on stdout",
)
@click.option(
    "--song",
    "song_ids",
    multiple=True,
    help="Limit to specific song_id(s)",
)
def compare(corpus: str, json_only: bool, song_ids: tuple[str, ...]) -> None:
    """Compare generator output against professional reference sequences."""
    import json as json_mod

    from src.evaluation.compare import (
        REPORT_DIR,
        render_terminal_summary,
        run_compare,
    )
    from src.evaluation.corpus import Corpus

    manifest_path = Path(corpus) / "manifest.json"
    if not manifest_path.exists():
        click.echo(f"Manifest not found: {manifest_path}", err=True)
        sys.exit(1)

    try:
        corpus_obj = Corpus(manifest_path)
    except Exception as exc:
        click.echo(f"Failed to load corpus: {exc}", err=True)
        sys.exit(1)

    filter_ids: list[str] | None = list(song_ids) if song_ids else None

    # Check that at least one song is measurable (after filter)
    measurable = corpus_obj.measurable_songs()
    if filter_ids is not None:
        measurable = [s for s in measurable if s in filter_ids]

    if not measurable:
        click.echo("No measurable corpus entries — all songs skipped (corpus-side).", err=True)
        sys.exit(2)

    # Run comparison
    report = run_compare(corpus_obj, song_ids=filter_ids)

    # Inject corpus_manifest_hash now that we have the path
    try:
        import hashlib
        digest = hashlib.md5(manifest_path.read_bytes()).hexdigest()
        report["corpus_manifest_hash"] = f"md5:{digest}"
    except Exception:
        pass

    # Strip internal-only field before writing
    our_side_errors: list[str] = report.pop("_our_side_errors", [])

    # Write report to disk
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = report["generated_at"].replace(":", "-")
    report_path = REPORT_DIR / f"{timestamp}.json"
    report_path.write_text(json_mod.dumps(report, indent=2), encoding="utf-8")

    # Determine exit code
    has_our_errors = bool(our_side_errors)

    if json_only:
        click.echo(str(report_path))
    else:
        summary_text = render_terminal_summary(report, corpus_dir=corpus)
        click.echo(summary_text)
        click.echo(f"\nReport: {report_path}")
        if our_side_errors:
            for err in our_side_errors:
                click.echo(f"[SKIP] Generator error — {err}")

    if has_our_errors:
        sys.exit(3)
    sys.exit(0)
