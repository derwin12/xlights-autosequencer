"""Build the side-by-side comparison MP4 from baseline + candidate.

Text overlays are rendered to PNG via PIL and composited with ffmpeg's overlay
filter — this avoids requiring a libfreetype-enabled ffmpeg (Homebrew's default
build doesn't include drawtext).
"""
from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ImportError):
            continue
    return ImageFont.load_default()


def _build_overlay_png(width: int, banner_h: int, footer_h: int, panel_h: int,
                       suggestion: int, slug: str,
                       what_changed: str, why: str, dest: Path) -> None:
    """Render the banner + footer text + panel labels as a single PNG."""
    total_h = banner_h + panel_h + footer_h
    img = Image.new("RGBA", (width, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Top banner
    draw.rectangle((0, 0, width, banner_h), fill=(15, 15, 22, 230))
    title_font = _load_font(18)
    title = f"#{suggestion}  {slug}    BASELINE  vs.  CANDIDATE"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, (banner_h - title_font.size) // 2),
              title, fill=(255, 255, 255, 255), font=title_font)

    # Footer band
    footer_y0 = banner_h + panel_h
    draw.rectangle((0, footer_y0, width, total_h), fill=(15, 15, 22, 230))
    body_font = _load_font(14)
    sub_font = _load_font(13)
    draw.text((12, footer_y0 + 6),
              f"What changed: {what_changed}", fill=(204, 204, 204, 255), font=body_font)
    draw.text((12, footer_y0 + 28),
              f"Why: {why}", fill=(136, 200, 255, 255), font=sub_font)

    # Panel labels (BASELINE / CANDIDATE) — translucent black box top-left of each panel
    label_font = _load_font(14)
    for i, label in enumerate(("BASELINE", "CANDIDATE")):
        x = i * (width // 2) + 8
        y = banner_h + 8
        bbox = draw.textbbox((0, 0), label, font=label_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.rectangle((x - 4, y - 2, x + tw + 4, y + th + 4), fill=(0, 0, 0, 180))
        draw.text((x, y), label, fill=(255, 255, 255, 255), font=label_font)

    img.save(dest)


def build_comparison(
    baseline: Path,
    candidate: Path,
    output: Path,
    *,
    suggestion: int,
    slug: str,
    what_changed: str,
    why: str,
    panel_w: int = 640,
    panel_h: int = 360,
    banner_h: int = 36,
    footer_h: int = 56,
) -> None:
    """Write a side-by-side MP4 with a top banner and a bottom 'what / why' band.

    Layout:
       [ top banner: "#NN — slug" + tags ]
       [ baseline (panel_w x panel_h) | candidate ]
       [ footer: "What changed: …" + "Why: …" ]

    Audio is taken from the candidate so the user can listen while watching both.
    """
    out_w = panel_w * 2
    out_h = panel_h + banner_h + footer_h

    with tempfile.TemporaryDirectory() as tmpdir:
        overlay_png = Path(tmpdir) / "overlay.png"
        _build_overlay_png(
            out_w, banner_h, footer_h, panel_h,
            suggestion, slug, what_changed, why, overlay_png,
        )

        # Filter graph: scale both inputs, hstack, pad to add banner+footer space,
        # then overlay the PNG (which carries all the text).
        filter_complex = (
            f"[0:v]scale={panel_w}:{panel_h}[bl];"
            f"[1:v]scale={panel_w}:{panel_h}[cl];"
            f"[bl][cl]hstack=inputs=2[panels];"
            f"[panels]pad=width={out_w}:height={out_h}:x=0:y={banner_h}:color=0x0c0c12[padded];"
            f"[padded][2:v]overlay=0:0"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(baseline),
            "-i", str(candidate),
            "-i", str(overlay_png),
            "-filter_complex", filter_complex,
            "-map", "1:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            str(output),
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed (rc={res.returncode}):\n"
                f"  cmd: {' '.join(shlex.quote(c) for c in cmd)}\n"
                f"  stderr tail:\n{res.stderr.decode('utf-8', errors='replace')[-2000:]}"
            )
