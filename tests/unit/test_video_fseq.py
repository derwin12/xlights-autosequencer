"""Smoke tests for the video pipeline's FSEQ reader and layout parser.

These tests build a tiny synthetic FSEQ in-memory rather than depending on a
real fixture, so they run on any machine with zstandard + numpy installed.
"""
from __future__ import annotations

import struct

import numpy as np
import pytest

zstd = pytest.importorskip("zstandard")

from src.video.fseq import load_fseq


def _build_minimal_fseq(tmp_path, *, channels: int, frames: int, step_ms: int) -> "Path":
    """Build a valid FSEQ v2 file with one zstd-compressed block holding all frames."""
    # Frame data: each frame's channel i = (frame_idx + i) & 0xFF
    payload = np.zeros((frames, channels), dtype=np.uint8)
    for f in range(frames):
        payload[f, :] = (np.arange(channels) + f) & 0xFF

    cctx = zstd.ZstdCompressor()
    compressed = cctx.compress(payload.tobytes())

    # Single block in the index: (frame_idx=0, blen=len(compressed))
    block_index = struct.pack("<II", 0, len(compressed))
    fixed_header_size = 32
    data_offset = fixed_header_size + len(block_index)

    header = bytearray(fixed_header_size)
    header[0:4] = b"PSEQ"
    struct.pack_into("<H", header, 4, data_offset)
    header[6] = 0   # minor version
    header[7] = 2   # major version
    struct.pack_into("<H", header, 8, fixed_header_size)
    struct.pack_into("<I", header, 10, channels)
    struct.pack_into("<I", header, 14, frames)
    header[18] = step_ms

    out = tmp_path / "test.fseq"
    out.write_bytes(bytes(header) + block_index + compressed)
    return out


def test_load_fseq_roundtrip(tmp_path) -> None:
    path = _build_minimal_fseq(tmp_path, channels=12, frames=5, step_ms=25)
    header, frames = load_fseq(path)

    assert header.channels == 12
    assert header.frames == 5
    assert header.step_ms == 25
    assert frames.shape == (5, 12)
    assert frames.dtype == np.uint8

    # Verify exact byte values match the synthetic pattern: frame f, channel c → (f + c) & 0xFF
    for f in range(5):
        for c in range(12):
            assert frames[f, c] == (f + c) & 0xFF, f"mismatch at frame={f} ch={c}"


def test_load_fseq_rejects_non_fseq(tmp_path) -> None:
    bad = tmp_path / "bad.fseq"
    bad.write_bytes(b"NOTFSEQ" + b"\x00" * 100)
    with pytest.raises(ValueError, match="not an FSEQ"):
        load_fseq(bad)
