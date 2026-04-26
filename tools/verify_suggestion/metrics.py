"""Frame-level metrics computed from a rendered MP4.

We decode the video at a fixed sample rate (default 4 fps) into a small numpy
array and compute the metrics that distinguish a *visible* improvement from a
no-op:

  - mean lit pixel count per frame  (was the show "on"?)
  - distinct quantized colors per frame  (palette diversity)
  - motion delta = mean abs diff between consecutive sampled frames
  - third activations: % of frames with any lit pixel in upper / middle / lower
    third of the canvas. This is what catches "show only fills the bottom".

A suggestion is judged a no-op (and flagged for revert) if every metric is
within ±5% of baseline.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class FrameMetrics:
    """Aggregate metrics for a video clip."""
    duration_s: float
    sample_fps: int
    n_frames: int
    motion_mean: float
    motion_p50: float
    motion_p90: float
    motion_max: float
    lit_mean: float
    lit_min: int
    lit_max: int
    distinct_colors_mean: float
    distinct_colors_max: int
    upper_third_pct: float    # frames with any lit pixel in upper third
    middle_third_pct: float
    lower_third_pct: float

    def to_json(self) -> dict:
        return asdict(self)


def decode_at_fps(video: Path, fps: int = 4, width: int = 200, height: int = 112) -> np.ndarray:
    """Use ffmpeg to decode the video at `fps` and return an (N, H, W, 3) uint8 array."""
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video),
            "-vf", f"fps={fps},scale={width}:{height}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ],
        capture_output=True, check=True,
    )
    raw = proc.stdout
    n_frames = len(raw) // (width * height * 3)
    return np.frombuffer(raw, dtype=np.uint8).reshape(n_frames, height, width, 3)


def compute_metrics(video: Path, fps: int = 4) -> FrameMetrics:
    """Compute frame-level metrics for `video`."""
    frames = decode_at_fps(video, fps=fps)
    if frames.shape[0] < 2:
        raise RuntimeError(f"video {video} decoded to {frames.shape[0]} frames; need at least 2")

    height = frames.shape[1]

    # "Lit" = any channel above background threshold (30/255).
    lit_mask = frames.max(axis=3) > 30
    lit_per_frame = lit_mask.sum(axis=(1, 2)).astype(np.int32)

    # Quantize to 32 buckets per channel and count unique tuples per frame
    # (only over lit pixels — counting the background is meaningless).
    quantized = (frames >> 3).astype(np.uint8)
    distinct_per_frame = np.zeros(frames.shape[0], dtype=np.int32)
    for i in range(frames.shape[0]):
        flat = quantized[i].reshape(-1, 3)
        packed = (flat[:, 0].astype(np.uint32) << 10) | (flat[:, 1].astype(np.uint32) << 5) | flat[:, 2]
        bg_mask = lit_mask[i].flatten()
        if bg_mask.any():
            distinct_per_frame[i] = len(np.unique(packed[bg_mask]))

    # Motion delta: mean absolute pixel difference between consecutive sampled frames.
    diff = np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16))
    motion = np.zeros(frames.shape[0], dtype=np.float32)
    motion[1:] = diff.mean(axis=(1, 2, 3))

    # Third-band activation
    upper = lit_mask[:, :height // 3, :].any(axis=(1, 2))
    middle = lit_mask[:, height // 3 : 2 * height // 3, :].any(axis=(1, 2))
    lower = lit_mask[:, 2 * height // 3 :, :].any(axis=(1, 2))

    return FrameMetrics(
        duration_s=frames.shape[0] / fps,
        sample_fps=fps,
        n_frames=int(frames.shape[0]),
        motion_mean=float(motion.mean()),
        motion_p50=float(np.percentile(motion, 50)),
        motion_p90=float(np.percentile(motion, 90)),
        motion_max=float(motion.max()),
        lit_mean=float(lit_per_frame.mean()),
        lit_min=int(lit_per_frame.min()),
        lit_max=int(lit_per_frame.max()),
        distinct_colors_mean=float(distinct_per_frame.mean()),
        distinct_colors_max=int(distinct_per_frame.max()),
        upper_third_pct=float(upper.mean() * 100),
        middle_third_pct=float(middle.mean() * 100),
        lower_third_pct=float(lower.mean() * 100),
    )


def compare(baseline: FrameMetrics, candidate: FrameMetrics) -> dict:
    """Return a delta dict suitable for embedding in metrics_<NN>.json."""
    def pct_change(b: float, c: float) -> float:
        if b == 0:
            return float("inf") if c != 0 else 0.0
        return (c - b) / b * 100.0

    return {
        "baseline": baseline.to_json(),
        "candidate": candidate.to_json(),
        "delta_pct": {
            "motion_mean": pct_change(baseline.motion_mean, candidate.motion_mean),
            "lit_mean": pct_change(baseline.lit_mean, candidate.lit_mean),
            "distinct_colors_mean": pct_change(baseline.distinct_colors_mean, candidate.distinct_colors_mean),
            "upper_third_pct": pct_change(baseline.upper_third_pct, candidate.upper_third_pct),
            "middle_third_pct": pct_change(baseline.middle_third_pct, candidate.middle_third_pct),
            "lower_third_pct": pct_change(baseline.lower_third_pct, candidate.lower_third_pct),
        },
    }


def is_noop(delta: dict, tolerance_pct: float = 5.0) -> bool:
    """True if every metric in the delta is within ±tolerance_pct of baseline."""
    for v in delta.get("delta_pct", {}).values():
        if abs(v) > tolerance_pct:
            return False
    return True


def write_metrics_json(path: Path, baseline: FrameMetrics, candidate: FrameMetrics,
                       suggestion: int, slug: str, notes: str) -> dict:
    """Write the metrics JSON sidecar and return the comparison dict."""
    cmp = compare(baseline, candidate)
    cmp["suggestion"] = suggestion
    cmp["slug"] = slug
    cmp["notes"] = notes
    cmp["noop"] = is_noop(cmp)
    path.write_text(json.dumps(cmp, indent=2))
    return cmp
