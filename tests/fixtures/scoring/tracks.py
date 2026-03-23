"""Fixture TimingTracks with known properties for scoring tests."""
from __future__ import annotations

from src.analyzer.result import TimingMark, TimingTrack


SONG_DURATION_MS = 180_000  # 3-minute song


def _regular_track(
    name: str,
    algorithm_name: str,
    element_type: str,
    interval_ms: int,
    duration_ms: int = SONG_DURATION_MS,
) -> TimingTrack:
    """Create a perfectly regular track with the given interval."""
    marks = [
        TimingMark(t, 1.0)
        for t in range(0, duration_ms, interval_ms)
    ]
    return TimingTrack(
        name=name,
        algorithm_name=algorithm_name,
        element_type=element_type,
        marks=marks,
        quality_score=0.0,
    )


# --- Beat category: high density, high regularity ---
# 120 BPM = 500ms intervals = 2.0 marks/s, 360 marks over 3 min
BEAT_TRACK = _regular_track("librosa_beats", "librosa_beats", "beat", 500)

# --- Bar category: moderate density, high regularity ---
# 30 BPM bars = 2000ms intervals = 0.5 marks/s, 90 marks over 3 min
BAR_TRACK = _regular_track("librosa_bars", "librosa_bars", "bar", 2000)

# --- Onset category: high density, irregular ---
def _make_onset_track() -> TimingTrack:
    """Irregular onsets — dense but not regular."""
    import random
    rng = random.Random(42)
    marks = []
    t = 0
    while t < SONG_DURATION_MS:
        marks.append(TimingMark(t, 0.8))
        t += rng.randint(80, 400)  # avg ~240ms = ~4.2 marks/s
    return TimingTrack(
        name="librosa_onsets",
        algorithm_name="librosa_onsets",
        element_type="onset",
        marks=marks,
        quality_score=0.0,
    )


ONSET_TRACK = _make_onset_track()

# --- Segment category: very low density ---
# ~8 segments in a 3-minute song = ~0.044 marks/s
SEGMENT_TRACK = TimingTrack(
    name="qm_segments",
    algorithm_name="qm_segments",
    element_type="segment",
    marks=[TimingMark(t, 1.0) for t in [0, 22000, 45000, 68000, 91000, 114000, 137000, 160000]],
    quality_score=0.0,
)

# --- Pitch category: moderate density ---
# ~1.5 marks/s, 270 marks, somewhat regular
PITCH_TRACK = _regular_track("pyin_notes", "pyin_notes", "pitch", 667)

# --- Harmony category: low density ---
# ~0.5 marks/s, chord changes every 2 seconds
HARMONY_TRACK = _regular_track("chordino_chords", "chordino_chords", "harmony", 2000)

# --- Edge case: empty track ---
EMPTY_TRACK = TimingTrack(
    name="empty", algorithm_name="empty", element_type="beat",
    marks=[], quality_score=0.0,
)

# --- Edge case: single mark ---
SINGLE_MARK_TRACK = TimingTrack(
    name="single", algorithm_name="single", element_type="beat",
    marks=[TimingMark(1000, 1.0)], quality_score=0.0,
)

# --- Edge case: sub-25ms gaps ---
def _make_dense_track() -> TimingTrack:
    """Track with many sub-25ms intervals (bad for lighting)."""
    marks = [TimingMark(t, 0.5) for t in range(0, 5000, 10)]  # 10ms intervals
    return TimingTrack(
        name="too_dense",
        algorithm_name="too_dense",
        element_type="onset",
        marks=marks,
        quality_score=0.0,
    )


DENSE_TRACK = _make_dense_track()

# --- Near-identical tracks for diversity filter testing ---
BEAT_TRACK_CLONE = TimingTrack(
    name="madmom_beats",
    algorithm_name="madmom_beats",
    element_type="beat",
    marks=[TimingMark(m.time_ms + 5, m.confidence) for m in BEAT_TRACK.marks],  # 5ms offset
    quality_score=0.0,
)
