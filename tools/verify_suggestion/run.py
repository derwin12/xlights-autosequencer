"""End-to-end verifier driver.

Runs the four phases (regen .xsq → render FSEQ → render MP4 → compose+metrics)
to produce one comparison artifact per show-improvement suggestion. Each
phase can be skipped via flags so the same script smoke-tests cleanly with
existing intermediates.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import click

from .compose import build_comparison
from .metrics import compute_metrics, write_metrics_json


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MP3 = Path("/Users/rob/xlights/01 - Baby Shark with Jaws Intro.mp3")
DEFAULT_SHOW_DIR = Path("/Users/rob/xlights")
DEFAULT_BASELINE = REPO_ROOT / "docs" / "video-samples" / "baseline.mp4"
DEFAULT_OUT_DIR = REPO_ROOT / "docs" / "video-samples"
DEFAULT_RENDER_IMAGE = "xlights-render"


@click.command()
@click.option("--suggestion", "-n", type=int, required=True, help="Suggestion number (e.g. 21)")
@click.option("--slug", required=True, help="Short kebab-case slug (e.g. 'qm-boundary-fix')")
@click.option("--what-changed", required=True, help="One-sentence summary of the change")
@click.option("--why", required=True, help="Reason for the change")
@click.option("--mp3", type=click.Path(path_type=Path), default=DEFAULT_MP3, show_default=True)
@click.option("--show-dir", type=click.Path(path_type=Path), default=DEFAULT_SHOW_DIR, show_default=True)
@click.option("--baseline", type=click.Path(path_type=Path), default=DEFAULT_BASELINE, show_default=True)
@click.option("--out-dir", type=click.Path(path_type=Path), default=DEFAULT_OUT_DIR, show_default=True)
@click.option("--render-image", default=DEFAULT_RENDER_IMAGE, show_default=True)
@click.option("--skip-regen", is_flag=True, help="Reuse the existing .xsq instead of regenerating")
@click.option("--skip-render", is_flag=True, help="Reuse existing .fseq + candidate .mp4 instead of re-rendering")
def main(
    suggestion: int, slug: str, what_changed: str, why: str,
    mp3: Path, show_dir: Path, baseline: Path, out_dir: Path,
    render_image: str, skip_regen: bool, skip_render: bool,
) -> None:
    """Run the verification pipeline and emit a comparison MP4 + metrics JSON.

    Skip flags:
      --skip-regen  reuses the existing .xsq next to the .mp3
      --skip-render reuses the existing .fseq + candidate .mp4 from the workdir

    Both skips are useful when smoke-testing the framework without re-running
    the slow Docker render for an unchanged generator.
    """
    if not baseline.is_file():
        raise click.UsageError(f"baseline not found: {baseline}")
    if not mp3.is_file():
        raise click.UsageError(f"mp3 not found: {mp3}")

    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_mp4 = out_dir / f"candidate_{suggestion:02d}_{slug}.mp4"
    comparison_mp4 = out_dir / f"comparison_{suggestion:02d}_{slug}.mp4"
    metrics_json = out_dir / f"metrics_{suggestion:02d}.json"
    notes_md = out_dir / f"notes_{suggestion:02d}_{slug}.md"

    xsq = mp3.with_suffix(".xsq")
    fseq = mp3.with_suffix(".fseq")

    # ---- Phase 1: regenerate .xsq ----
    if skip_regen:
        click.echo(f"[1/4] Skipping regen, reusing {xsq}", err=True)
        if not xsq.is_file():
            raise click.UsageError(f"--skip-regen but {xsq} missing")
    else:
        click.echo(f"[1/4] Regenerating .xsq from {mp3.name}", err=True)
        # The exact command depends on whether the user has the generator set up
        # via xlight-analyze generate or a direct module call. Most reliable
        # is a direct subprocess to the installed entry point.
        subprocess.run(
            ["xlight-analyze", "generate", "--mp3", str(mp3), "--show-dir", str(show_dir)],
            check=True,
        )

    # ---- Phase 2: render FSEQ via Docker ----
    if skip_render:
        click.echo(f"[2/4] Skipping FSEQ render, reusing {fseq}", err=True)
        if not fseq.is_file():
            raise click.UsageError(f"--skip-render but {fseq} missing")
    else:
        click.echo(f"[2/4] Rendering FSEQ via {render_image}", err=True)
        subprocess.run(
            [
                "docker", "run", "--rm", "--platform", "linux/amd64",
                "-v", f"{show_dir}:/work", render_image,
                "/work", f"/work/{xsq.name}",
            ],
            check=True,
        )

    # ---- Phase 3: render candidate MP4 via xlight-video ----
    rgbeffects = show_dir / "xlights_rgbeffects.xml"
    networks = show_dir / "xlights_networks.xml"
    if skip_render and candidate_mp4.is_file():
        click.echo(f"[3/4] Skipping MP4 render, reusing {candidate_mp4}", err=True)
    else:
        click.echo(f"[3/4] Rendering candidate MP4 → {candidate_mp4.name}", err=True)
        subprocess.run(
            [
                "xlight-video",
                str(fseq), str(mp3),
                "--rgbeffects", str(rgbeffects),
                "--networks", str(networks),
                "--out", str(candidate_mp4),
            ],
            check=True,
        )

    # ---- Phase 4: compose + metrics ----
    click.echo(f"[4/4] Computing metrics + composing comparison", err=True)
    baseline_metrics = compute_metrics(baseline)
    candidate_metrics = compute_metrics(candidate_mp4)
    notes = f"{what_changed}  // {why}"
    cmp = write_metrics_json(metrics_json, baseline_metrics, candidate_metrics,
                              suggestion=suggestion, slug=slug, notes=notes)

    build_comparison(
        baseline=baseline, candidate=candidate_mp4, output=comparison_mp4,
        suggestion=suggestion, slug=slug,
        what_changed=what_changed, why=why,
    )

    notes_md.write_text(
        f"# Suggestion #{suggestion}: {slug}\n\n"
        f"**What changed:** {what_changed}\n\n"
        f"**Why:** {why}\n\n"
        f"## Metric deltas\n\n"
        f"```json\n"
        f"{__import__('json').dumps(cmp['delta_pct'], indent=2)}\n"
        f"```\n\n"
        f"**Verdict:** {'NO-OP (within ±5% on every metric)' if cmp['noop'] else 'CHANGE DETECTED'}\n\n"
        f"## Artifacts\n\n"
        f"- Comparison video: `{comparison_mp4.name}`\n"
        f"- Metrics: `{metrics_json.name}`\n"
    )

    click.echo("", err=True)
    click.echo(f"Wrote:", err=True)
    click.echo(f"  {comparison_mp4}", err=True)
    click.echo(f"  {metrics_json}", err=True)
    click.echo(f"  {notes_md}", err=True)
    if cmp["noop"]:
        click.secho("\nVERDICT: NO-OP — every metric within ±5% of baseline. "
                    "Consider reverting before opening the PR.", fg="yellow", err=True)
    else:
        click.echo("\nMetric deltas:", err=True)
        for k, v in cmp["delta_pct"].items():
            click.echo(f"  {k:24s} {v:+7.2f}%", err=True)


if __name__ == "__main__":
    main()
