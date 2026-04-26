"""Smoke tests for tools/verify_suggestion/metrics.py.

Decodes a tiny synthetic MP4 we build on the fly and confirms the metrics
extractor returns sensible values. No reliance on real show data.
"""
from __future__ import annotations

import shutil
import subprocess

import numpy as np
import pytest

# Skip everything if scipy/zstandard not installed (the [video] extra)
zstd = pytest.importorskip("zstandard")  # noqa: F401  (transitively used)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


pytestmark = pytest.mark.skipif(
    not _ffmpeg_available(), reason="ffmpeg not installed; verifier needs it",
)


def _make_synthetic_video(path, w: int = 320, h: int = 180, seconds: int = 4, fps: int = 25,
                            background: int = 0, blob: tuple[int, int, int] = (200, 100, 50)) -> None:
    """Build a tiny MP4 with a moving bright square so motion + lit pixels are nonzero."""
    n_frames = seconds * fps
    frames = np.full((n_frames, h, w, 3), background, dtype=np.uint8)
    # Animate a 30x30 blob across the frame
    for i in range(n_frames):
        x = int((i / n_frames) * (w - 30))
        frames[i, h // 2 - 15 : h // 2 + 15, x : x + 30] = blob

    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(path),
        ],
        input=frames.tobytes(), capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace"))


def test_metrics_synthetic_video(tmp_path) -> None:
    from tools.verify_suggestion.metrics import compute_metrics

    video = tmp_path / "syn.mp4"
    _make_synthetic_video(video, seconds=4, fps=25)

    metrics = compute_metrics(video, fps=4)
    assert metrics.n_frames >= 14  # ~16 frames for 4s @ 4 fps
    assert metrics.lit_mean > 0, "synthetic blob should produce lit pixels"
    assert metrics.lit_max >= metrics.lit_min
    assert metrics.motion_mean > 0, "moving blob should register motion"
    # Blob is in the middle band, so middle-third activation should be 100%
    assert metrics.middle_third_pct == 100.0


def test_compare_and_noop(tmp_path) -> None:
    from tools.verify_suggestion.metrics import compute_metrics, compare, is_noop

    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _make_synthetic_video(a, seconds=4, fps=25)
    _make_synthetic_video(b, seconds=4, fps=25)

    ma = compute_metrics(a, fps=4)
    mb = compute_metrics(b, fps=4)
    delta = compare(ma, mb)
    # Identical synthetic videos should classify as a no-op
    assert is_noop(delta), f"identical videos flagged as change: {delta['delta_pct']}"
