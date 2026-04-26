"""Frame renderer: world transform → ortho projection → splat + bloom + ffmpeg pipe."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from .fseq import FseqHeader, load_fseq
from .layout import Controller, Model, model_local_pixels, parse_controllers, parse_models


def _rotation_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
    """Z-Y-X intrinsic Tait-Bryan order (matches xLights)."""
    rx, ry, rz = np.deg2rad([rx_deg, ry_deg, rz_deg])
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float32)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float32)
    return Rz @ Ry @ Rx


def _model_to_world(local: np.ndarray, default_size: tuple, model: Model) -> np.ndarray:
    """Center on origin → scale by Scale × default → rotate → translate to WorldPos."""
    w, h, d = default_size
    pts = local.copy()
    pts[:, 0] -= w / 2
    pts[:, 1] -= h / 2
    pts[:, 2] -= d / 2
    pts[:, 0] *= model.scale_x
    pts[:, 1] *= model.scale_y
    pts[:, 2] *= model.scale_z
    if abs(model.rotate_x) + abs(model.rotate_y) + abs(model.rotate_z) > 0.01:
        R = _rotation_matrix(model.rotate_x, model.rotate_y, model.rotate_z)
        pts = pts @ R.T
    pts[:, 0] += model.world_x
    pts[:, 1] += model.world_y
    pts[:, 2] += model.world_z
    return pts


def render_video(
    fseq_path: Path,
    rgbeffects_path: Path,
    networks_path: Path,
    audio_path: Path,
    output_path: Path,
    canvas_w: int = 1280,
    canvas_h: int = 720,
    bloom_sigma: float = 1.8,
    bloom_strength: float = 0.7,
    smoothing: float = 0.4,
) -> None:
    """End-to-end FSEQ → MP4 render. Front-facing orthographic projection, single
    pixel splat per channel, Gaussian bloom for halos, temporal smoothing for trails.
    """
    print(f"[1/5] FSEQ {fseq_path.name}", file=sys.stderr)
    header, frames = load_fseq(fseq_path)
    print(f"      channels={header.channels:,}  frames={header.frames}  step={header.step_ms}ms",
          file=sys.stderr)

    print(f"[2/5] Networks {networks_path.name}", file=sys.stderr)
    controllers = parse_controllers(networks_path)
    for c in controllers.values():
        print(f"      {c.name:30}  start={c.start:7,}  length={c.length:7,}", file=sys.stderr)

    print(f"[3/5] Models {rgbeffects_path.name}", file=sys.stderr)
    models = parse_models(rgbeffects_path, controllers)
    print(f"      {len(models)} models", file=sys.stderr)

    # World positions for every pixel
    all_world = []
    all_channels = []
    for m in models:
        local, default_size = model_local_pixels(m)
        if local.shape[0] == 0:
            continue
        world = _model_to_world(local, default_size, m)
        all_world.append(world)
        all_channels.append(m.start_channel + 3 * np.arange(m.n_pixels))
    world_pts = np.concatenate(all_world, axis=0)
    channel_starts = np.concatenate(all_channels, axis=0)
    print(f"      total pixels: {world_pts.shape[0]:,}", file=sys.stderr)

    bbox_min = world_pts.min(axis=0)
    bbox_max = world_pts.max(axis=0)
    print(f"      world bbox  min={bbox_min}  max={bbox_max}", file=sys.stderr)

    # Orthographic projection — preserves relative scales between props of wildly
    # different sizes (perspective compresses far props into invisibility for shows
    # whose Z range spans 1000+ world units).
    pad_x = (bbox_max[0] - bbox_min[0]) * 0.05
    pad_y = (bbox_max[1] - bbox_min[1]) * 0.05
    min_x, max_x = bbox_min[0] - pad_x, bbox_max[0] + pad_x
    min_y, max_y = bbox_min[1] - pad_y, bbox_max[1] + pad_y
    scale = min(canvas_w / (max_x - min_x), canvas_h / (max_y - min_y))
    offset_x = (canvas_w - scale * (max_x - min_x)) / 2
    offset_y = (canvas_h - scale * (max_y - min_y)) / 2
    sx = (offset_x + (world_pts[:, 0] - min_x) * scale).astype(np.int32)
    sy = (canvas_h - offset_y - (world_pts[:, 1] - min_y) * scale).astype(np.int32)

    in_canvas = (
        (sx >= 0) & (sx < canvas_w) & (sy >= 0) & (sy < canvas_h)
        & (channel_starts + 2 < header.channels)
    )
    sxs = sx[in_canvas]
    sys_ = sy[in_canvas]
    channel_starts = channel_starts[in_canvas]
    print(f"      pixels in view: {sxs.shape[0]:,}", file=sys.stderr)

    # Ground line at world Y=0 if it falls inside the bbox
    ground_y_screen = None
    if min_y < 0 < max_y:
        ground_y_screen = int(canvas_h - offset_y - (0 - min_y) * scale)
        print(f"      ground line at screen y={ground_y_screen}", file=sys.stderr)

    fps = round(1000 / header.step_ms)
    duration = header.frames * header.step_ms / 1000
    print(f"[4/5] Rendering {header.frames} frames @ {fps}fps ({duration:.1f}s)", file=sys.stderr)

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{canvas_w}x{canvas_h}", "-r", str(fps),
        "-i", "pipe:0",
        "-i", str(audio_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    bg_color = np.array([6, 6, 12], dtype=np.uint8)
    sharp = np.empty((canvas_h, canvas_w, 3), dtype=np.uint8)
    prev_sharp = np.zeros_like(sharp)
    output = np.empty_like(sharp)

    try:
        for fi in range(header.frames):
            # Sharp layer = temporal-faded previous + this frame's pixel splats.
            # Bloom is computed ONCE per frame, OUTSIDE the temporal feedback loop —
            # feeding bloomed output back into prev_sharp creates runaway saturation.
            np.multiply(prev_sharp, smoothing, out=sharp, casting="unsafe")
            np.maximum(sharp, bg_color, out=sharp)

            if ground_y_screen is not None and 0 <= ground_y_screen < canvas_h:
                sharp[ground_y_screen, :, :] = np.maximum(
                    sharp[ground_y_screen, :, :], (15, 15, 25)
                )

            row = frames[fi]
            sharp[sys_, sxs, 0] = np.maximum(sharp[sys_, sxs, 0], row[channel_starts])
            sharp[sys_, sxs, 1] = np.maximum(sharp[sys_, sxs, 1], row[channel_starts + 1])
            sharp[sys_, sxs, 2] = np.maximum(sharp[sys_, sxs, 2], row[channel_starts + 2])

            blurred = gaussian_filter(sharp, sigma=(bloom_sigma, bloom_sigma, 0))
            combined = sharp.astype(np.int16) + (
                (blurred.astype(np.int16) * int(bloom_strength * 256)) >> 8
            )
            np.clip(combined, 0, 255, out=combined)
            output[:] = combined.astype(np.uint8)

            proc.stdin.write(output.tobytes())
            np.copyto(prev_sharp, sharp)
            if fi % 200 == 0:
                print(f"      frame {fi}/{header.frames}", file=sys.stderr)
    finally:
        proc.stdin.close()
        rc = proc.wait()
        err = proc.stderr.read().decode("utf-8", errors="replace")
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited {rc}:\n{err}")

    print(f"[5/5] Wrote {output_path}", file=sys.stderr)
