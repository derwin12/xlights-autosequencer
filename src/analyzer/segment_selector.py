"""Representative audio segment selection for sweep optimization.

Selects a high-energy window of the song (typically a chorus or energetic
verse) to run sweep permutations against, avoiding intros, outros, and
fade-outs.  The sweep tunes parameters on this segment, then the winning
config is re-run on the full song.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "select_representative_segment",
]


def select_representative_segment(
    audio_path: str,
    duration_s: float = 30.0,
) -> tuple[int, int]:
    """Return (start_ms, end_ms) of the highest-energy window.

    Algorithm:
    1. Compute RMS energy with hop_length=2048 (~93ms frames at 22050 Hz).
    2. Exclude first/last 10% of frames (avoid intro/outro).
    3. Apply a rolling mean over *duration_s*-length windows.
    4. Select the window with the highest mean energy.

    If the audio is shorter than *duration_s*, returns (0, song_duration_ms).
    """
    import librosa

    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    song_duration_s = len(y) / sr
    song_duration_ms = int(song_duration_s * 1000)

    # If song is shorter than requested segment, return full song
    if song_duration_s <= duration_s:
        return 0, song_duration_ms

    hop = 2048
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    n_frames = len(rms)
    frame_duration_s = hop / sr

    # Exclude first/last 10%
    margin = max(1, int(n_frames * 0.1))
    search_start = margin
    search_end = n_frames - margin

    # Window size in frames
    window_frames = max(1, int(duration_s / frame_duration_s))

    if search_end - search_start < window_frames:
        # Not enough room after excluding margins — use full range
        search_start = 0
        search_end = n_frames

    # Rolling mean energy
    best_energy = -1.0
    best_start_frame = search_start
    for i in range(search_start, search_end - window_frames + 1):
        window_energy = float(np.mean(rms[i:i + window_frames]))
        if window_energy > best_energy:
            best_energy = window_energy
            best_start_frame = i

    start_ms = int(best_start_frame * frame_duration_s * 1000)
    end_ms = min(song_duration_ms, int(start_ms + duration_s * 1000))

    return start_ms, end_ms
