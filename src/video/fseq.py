"""FSEQ v2 binary reader.

Decodes the Falcon Player Sequence v2 format used by xLights:
fixed 32-byte header, compression-block index, optional sparse-range table,
then zstd-compressed channel-data blocks.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import zstandard as zstd


@dataclass
class FseqHeader:
    channels: int
    frames: int
    step_ms: int
    data_offset: int


def load_fseq(path: Path) -> tuple[FseqHeader, np.ndarray]:
    """Return (header, frames) where frames is a uint8 [num_frames, channels] array."""
    raw = path.read_bytes()
    if raw[:4] != b"PSEQ":
        raise ValueError(f"{path} is not an FSEQ v2 file (magic={raw[:4]!r})")

    data_offset = struct.unpack_from("<H", raw, 4)[0]
    channels = struct.unpack_from("<I", raw, 10)[0]
    num_frames = struct.unpack_from("<I", raw, 14)[0]
    step_ms = raw[18]

    # Walk the compression-block index. Each entry is 4-byte first-frame +
    # 4-byte block byte length. The list ends at the first entry with blen=0
    # (empty/uninitialised slot) or a frame index past num_frames.
    blocks = []
    i = 0
    while True:
        off = 32 + i * 8
        if off + 8 > data_offset:
            break
        frame_idx = struct.unpack_from("<I", raw, off)[0]
        blen = struct.unpack_from("<I", raw, off + 4)[0]
        if blen == 0 or frame_idx > num_frames:
            break
        blocks.append((frame_idx, blen))
        i += 1

    out = np.zeros((num_frames, channels), dtype=np.uint8)
    dctx = zstd.ZstdDecompressor()
    cursor = data_offset
    for frame_idx, blen in blocks:
        block = raw[cursor:cursor + blen]
        cursor += blen
        decompressed = dctx.decompress(block, max_output_size=channels * 200)
        n_frames_in_block = len(decompressed) // channels
        arr = np.frombuffer(decompressed, dtype=np.uint8).reshape(n_frames_in_block, channels)
        out[frame_idx:frame_idx + n_frames_in_block] = arr

    return FseqHeader(
        channels=channels,
        frames=num_frames,
        step_ms=step_ms,
        data_offset=data_offset,
    ), out
