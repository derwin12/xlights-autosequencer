"""`xlight-video` CLI entry point.

Renders an FSEQ to MP4 using the show layout XML and source audio.
The FSEQ must already exist — generate it via the headless render container
(`tools/render/`) or any other means.
"""
from __future__ import annotations

from pathlib import Path

import click

from .renderer import render_video


@click.command()
@click.argument("fseq", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("audio", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--rgbeffects", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              required=True, help="xlights_rgbeffects.xml from your show directory")
@click.option("--networks", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              required=True, help="xlights_networks.xml from your show directory")
@click.option("--out", "output", type=click.Path(dir_okay=False, path_type=Path),
              required=True, help="MP4 output path")
@click.option("--width", default=1280, show_default=True, type=int)
@click.option("--height", default=720, show_default=True, type=int)
def main(fseq: Path, audio: Path, rgbeffects: Path, networks: Path,
         output: Path, width: int, height: int) -> None:
    """Render a populated FSEQ + show layout into a watchable MP4 preview.

    Example:

        xlight-video song.fseq song.mp3 \\
            --rgbeffects ~/xlights/xlights_rgbeffects.xml \\
            --networks ~/xlights/xlights_networks.xml \\
            --out song_preview.mp4
    """
    render_video(
        fseq_path=fseq,
        rgbeffects_path=rgbeffects,
        networks_path=networks,
        audio_path=audio,
        output_path=output,
        canvas_w=width,
        canvas_h=height,
    )


if __name__ == "__main__":
    main()
