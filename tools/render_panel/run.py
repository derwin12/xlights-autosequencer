"""Repeatable render harness — generate, render headless, contact-sheet.

Three subcommands:

* ``setup``  — fetch + extract the xLights AppImage so a fresh ephemeral
  container can self-provision (the Docker-free equivalent of
  ``tools/render/build.sh``).
* ``render`` — one song: generate ``.xsq`` with the repo generator →
  headless xLights ``-r`` → ``.fseq`` → ``src.video`` MP4 → contact sheet.
* ``panel``  — read a manifest of several songs and render each, then
  tile every song's mid-frame into one combined panel sheet.

Run from the repo root::

    python -m tools.render_panel.run setup
    python -m tools.render_panel.run render \\
        --song path/to/song.mp3 \\
        --layout ~/xlights/xlights_rgbeffects.xml \\
        --networks ~/xlights/xlights_networks.xml \\
        --story path/to/song_story.json        # optional
    python -m tools.render_panel.run panel --manifest panel.json

The headless render needs Xvfb + a software-GL stack (llvmpipe) and
ffmpeg on PATH. ``setup`` does not install those system packages — see
README.md for the one-line apt command.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RENDER_DIR = REPO_ROOT / "tools" / "render"
XLIGHTS_TREE = RENDER_DIR / "xlights"
APPRUN = XLIGHTS_TREE / "AppRun"
APPIMAGE = RENDER_DIR / "xLights.AppImage"
DEFAULT_RELEASE = "2026.06"


# ── setup ───────────────────────────────────────────────────────────────────


def _extract_appimage(appimage: Path, dest: Path) -> None:
    """Extract the squashfs appended to an AppImage into ``dest``.

    AppImage = ELF runtime + appended squashfs filesystem. The squashfs
    starts immediately after the ELF section-header table, whose end is
    computed from the ELF header fields (mirrors tools/render/build.sh).
    """
    header = appimage.read_bytes()[:64]
    e_shoff = struct.unpack_from("<Q", header, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", header, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", header, 0x3C)[0]
    offset = e_shoff + e_shentsize * e_shnum

    with tempfile.TemporaryDirectory() as tmp:
        squashfs = Path(tmp) / "xlights.squashfs"
        with appimage.open("rb") as src, squashfs.open("wb") as dst:
            src.seek(offset)
            shutil.copyfileobj(src, dst)
        if shutil.which("unsquashfs") is None:
            raise click.ClickException(
                "unsquashfs not found — install with "
                "`apt-get install -y squashfs-tools`."
            )
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(
            ["unsquashfs", "-d", str(dest), str(squashfs)],
            check=True, capture_output=True,
        )


@click.group()
def cli() -> None:
    """Generate + headless-render + contact-sheet harness."""


@cli.command()
@click.option("--release", default=DEFAULT_RELEASE, show_default=True,
              help="xLights release tag to download.")
@click.option("--force", is_flag=True, help="Re-download/re-extract even if present.")
def setup(release: str, force: bool) -> None:
    """Fetch + extract the xLights AppImage (no Docker)."""
    if APPRUN.exists() and not force:
        click.echo(f"xLights already extracted at {XLIGHTS_TREE} — skipping.")
        return

    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    if not APPIMAGE.exists() or force:
        url = (
            f"https://github.com/xLightsSequencer/xLights/releases/download/"
            f"{release}/xLights-{release}-x86_64.AppImage"
        )
        click.echo(f"Downloading xLights {release} AppImage…")
        if shutil.which("curl") is None:
            raise click.ClickException("curl not found.")
        subprocess.run(
            ["curl", "-fL", "--progress-bar", "-o", str(APPIMAGE), url],
            check=True,
        )

    click.echo("Extracting squashfs…")
    _extract_appimage(APPIMAGE, XLIGHTS_TREE)
    APPRUN.chmod(0o755)
    real_bin = XLIGHTS_TREE / "usr" / "bin" / "xLights"
    if real_bin.exists():
        real_bin.chmod(0o755)
    click.echo(f"Ready: {APPRUN}")


# ── render primitives ─────────────────────────────────────────────────────────


def _count_model_placements(xsq_path: Path) -> int:
    """Number of ``<Element type="model">`` entries under <ElementEffects>.

    Zero means the generator produced a timing-only (unlit) sequence — the
    silent-empty-sequence failure mode. Counting via ElementTree rather than
    a line grep so nested timing elements don't inflate the count.
    """
    root = ET.parse(xsq_path).getroot()
    effects = root.find("ElementEffects")
    if effects is None:
        return 0
    return sum(
        1 for el in effects.findall("Element")
        if el.get("type") == "model"
    )


def _generate(song: Path, layout: Path, story: Path | None, out_dir: Path,
              variation_seed: int) -> Path:
    """Run the repo generator; return the .xsq path."""
    from src.generator.models import GenerationConfig
    from src.generator.plan import generate_sequence

    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GenerationConfig(
        audio_path=song,
        layout_path=layout,
        output_dir=out_dir,
        story_path=story,
        variation_seed=variation_seed,
    )
    return generate_sequence(cfg)


def _render_fseq(show_dir: Path, xsq: Path, display: int, timeout_s: int) -> Path:
    """Render an .xsq to .fseq via headless xLights under a private Xvfb."""
    fseq = xsq.with_suffix(".fseq")
    if fseq.exists():
        fseq.unlink()

    env = dict(os.environ)
    env.update(
        LIBGL_ALWAYS_SOFTWARE="1",
        GALLIUM_DRIVER="llvmpipe",
        DISPLAY=f":{display}",
    )
    lock = Path(f"/tmp/.X{display}-lock")
    if lock.exists():
        lock.unlink()

    xvfb = subprocess.Popen(
        ["Xvfb", f":{display}", "-screen", "0", "1920x1080x24",
         "-ac", "+extension", "GLX", "+render", "-noreset"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        proc = subprocess.run(
            [str(APPRUN), "-r", "-s", str(show_dir), "-m", str(show_dir), str(xsq)],
            env=env, capture_output=True, text=True, timeout=timeout_s,
        )
        if not fseq.exists():
            tail = "\n".join(
                ln for ln in proc.stdout.splitlines()[-15:]
                if "Gtk" not in ln
            )
            raise click.ClickException(
                f"xLights produced no FSEQ for {xsq.name}.\n"
                f"Likely a first-run dialog on a non-current layout file.\n"
                f"Last non-GTK output:\n{tail}"
            )
        return fseq
    finally:
        xvfb.terminate()


def _extract_frames(mp4: Path, out_dir: Path, n: int, duration_s: float) -> list[Path]:
    """Pull ``n`` evenly spaced still frames from the MP4."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    # spread across the interior of the song, avoiding the very ends
    for i in range(n):
        t = duration_s * (i + 0.5) / n
        frame = out_dir / f"frame_{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-ss", f"{t:.2f}", "-i", str(mp4),
             "-frames:v", "1", "-q:v", "2", str(frame), "-y"],
            check=True, capture_output=True,
        )
        frames.append(frame)
    return frames


def _tile(frames: list[Path], out: Path, cols: int) -> None:
    """Tile JPEGs into a grid using ffmpeg's xstack (no ImageMagick dep)."""
    n = len(frames)
    if n == 1:
        # xstack requires >= 2 inputs; a single frame is just copied.
        shutil.copy(frames[0], out)
        return
    rows = (n + cols - 1) // cols
    layout = []
    for i in range(n):
        r, c = divmod(i, cols)
        x = "+".join(f"w{j}" for j in range(c)) if c else "0"
        y = "+".join(f"h{j * cols}" for j in range(r)) if r else "0"
        layout.append(f"{x}_{y}")
    inputs: list[str] = []
    for f in frames:
        inputs += ["-i", str(f)]
    streams = "".join(f"[{i}]" for i in range(n))
    subprocess.run(
        ["ffmpeg", "-nostdin", *inputs,
         "-filter_complex",
         f"{streams}xstack=inputs={n}:layout={'|'.join(layout)}:fill=black",
         str(out), "-y"],
        check=True, capture_output=True,
    )


def _render_one(song: Path, layout: Path, networks: Path, story: Path | None,
                out_dir: Path, frames: int, cols: int, width: int,
                display: int, variation_seed: int) -> dict:
    """Full chain for one song. Returns a result dict with artifact paths."""
    from src.video.renderer import render_video

    slug = song.stem
    click.echo(f"\n=== {slug} ===")
    work = out_dir / slug
    work.mkdir(parents=True, exist_ok=True)

    click.echo("  [1/5] generate")
    xsq = _generate(song, layout, story, work, variation_seed)
    placements = _count_model_placements(xsq)
    if placements == 0:
        click.secho(
            "  WARNING: 0 model placements — generator produced a timing-only "
            "(unlit) sequence. Render will be black. This usually means "
            "analysis found 0 sections (no vamp segmenter) and no --story was "
            "supplied.", fg="yellow",
        )
    else:
        click.echo(f"        {placements} model placements")

    # xLights renders relative to a show dir containing the layout + media,
    # with the media named exactly as the xsq's <mediaFile> (the audio stem).
    show = work / "show"
    show.mkdir(exist_ok=True)
    shutil.copy(layout, show / "xlights_rgbeffects.xml")
    shutil.copy(networks, show / "xlights_networks.xml")
    show_xsq = show / xsq.name
    shutil.copy(xsq, show_xsq)
    shutil.copy(song, show / f"{slug}.mp3")

    click.echo("  [2/5] render fseq (headless xLights)")
    fseq = _render_fseq(show, show_xsq, display, timeout_s=300)

    click.echo("  [3/5] fseq → mp4")
    mp4 = work / f"{slug}.mp4"
    render_video(
        fseq_path=fseq,
        rgbeffects_path=show / "xlights_rgbeffects.xml",
        networks_path=show / "xlights_networks.xml",
        audio_path=show / f"{slug}.mp3",
        output_path=mp4,
        canvas_w=width,
        canvas_h=width * 9 // 16,
    )

    duration_s = _probe_duration(mp4)
    click.echo("  [4/5] extract frames")
    stills = _extract_frames(mp4, work / "frames", frames, duration_s)

    click.echo("  [5/5] contact sheet")
    sheet = work / f"{slug}_contact_sheet.jpg"
    _tile(stills, sheet, cols)

    click.secho(f"  done: {sheet}", fg="green")
    return {
        "slug": slug, "xsq": str(xsq), "mp4": str(mp4),
        "contact_sheet": str(sheet), "placements": placements,
        "mid_frame": str(stills[len(stills) // 2]),
    }


def _probe_duration(mp4: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(mp4)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _require_xlights() -> None:
    if not APPRUN.exists():
        raise click.ClickException(
            "xLights not extracted. Run `python -m tools.render_panel.run setup` first."
        )
    for tool in ("Xvfb", "ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise click.ClickException(
                f"{tool} not found on PATH. Install the render stack:\n"
                "  apt-get install -y xvfb ffmpeg libgl1 libosmesa6 "
                "libgtk-3-0 libsdl2-2.0-0 libwebkit2gtk-4.1-0"
            )


# ── render (single) ───────────────────────────────────────────────────────────


@cli.command()
@click.option("--song", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--layout", required=True, type=click.Path(exists=True, path_type=Path),
              help="xlights_rgbeffects.xml")
@click.option("--networks", required=True, type=click.Path(exists=True, path_type=Path),
              help="xlights_networks.xml")
@click.option("--story", type=click.Path(exists=True, path_type=Path), default=None,
              help="Optional song_story.json — supplies sections when analysis can't.")
@click.option("--out", "out_dir", type=click.Path(path_type=Path),
              default=Path("render-out"), show_default=True)
@click.option("--frames", default=8, show_default=True, help="Stills in the contact sheet.")
@click.option("--cols", default=4, show_default=True, help="Contact-sheet columns.")
@click.option("--width", default=1024, show_default=True, help="MP4 width (16:9).")
@click.option("--variation-seed", default=0, show_default=True)
def render(song: Path, layout: Path, networks: Path, story: Path | None,
           out_dir: Path, frames: int, cols: int, width: int,
           variation_seed: int) -> None:
    """Generate + headless-render + contact-sheet a single song."""
    _require_xlights()
    result = _render_one(song, layout, networks, story, out_dir,
                         frames, cols, width, display=89,
                         variation_seed=variation_seed)
    click.echo("\n" + json.dumps(result, indent=2))


# ── panel (manifest) ──────────────────────────────────────────────────────────


@cli.command()
@click.option("--manifest", required=True, type=click.Path(exists=True, path_type=Path),
              help="JSON: {layout, networks, songs:[{song, story?}, ...]}")
@click.option("--out", "out_dir", type=click.Path(path_type=Path),
              default=Path("render-out"), show_default=True)
@click.option("--frames", default=6, show_default=True, help="Stills per song.")
@click.option("--width", default=768, show_default=True)
def panel(manifest: Path, out_dir: Path, frames: int, width: int) -> None:
    """Render every song in a manifest; tile mid-frames into one panel sheet.

    Manifest schema::

        {
          "layout":   "path/to/xlights_rgbeffects.xml",
          "networks": "path/to/xlights_networks.xml",
          "songs": [
            {"song": "a.mp3", "story": "a_story.json"},
            {"song": "b.mp3"}
          ]
        }

    Relative paths resolve against the manifest's directory.
    """
    _require_xlights()
    spec = json.loads(manifest.read_text())
    base = manifest.parent

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (base / path)

    layout = _resolve(spec["layout"])
    networks = _resolve(spec["networks"])
    songs = spec["songs"]

    results = []
    for i, entry in enumerate(songs):
        song = _resolve(entry["song"])
        story = _resolve(entry["story"]) if entry.get("story") else None
        # Each song gets its own Xvfb display to stay isolated.
        results.append(
            _render_one(song, layout, networks, story, out_dir,
                       frames, cols=frames, width=width,
                       display=80 + i, variation_seed=0)
        )

    panel_sheet = out_dir / "panel_contact_sheet.jpg"
    _tile([Path(r["mid_frame"]) for r in results], panel_sheet, cols=1)

    summary = out_dir / "panel_results.json"
    summary.write_text(json.dumps(results, indent=2))
    click.secho(f"\nPanel sheet: {panel_sheet}", fg="green")
    click.echo(f"Per-song results: {summary}")
    dark = [r["slug"] for r in results if r["placements"] == 0]
    if dark:
        click.secho(f"Unlit (0 placements): {', '.join(dark)}", fg="yellow")


if __name__ == "__main__":
    cli()
