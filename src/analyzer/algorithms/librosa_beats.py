"""T027: Librosa beat and bar tracking algorithms."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack


class LibrosaBeatAlgorithm(Algorithm):
    """Beat tracker using librosa's beat_track()."""

    name = "librosa_beats"
    element_type = "beat"
    library = "librosa"
    plugin_key = None
    parameters = {"hop_length": 512}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import librosa

        _, beat_frames = librosa.beat.beat_track(
            y=audio, sr=sample_rate, hop_length=512
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate, hop_length=512)
        marks = [
            TimingMark(time_ms=int(round(t * 1000)), confidence=None)
            for t in beat_times
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class LibrosaBarAlgorithm(Algorithm):
    """Bar tracker — every 4th beat from librosa beat_track()."""

    name = "librosa_bars"
    element_type = "bar"
    library = "librosa"
    plugin_key = None
    parameters = {"hop_length": 512, "beats_per_bar": 4}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import librosa

        _, beat_frames = librosa.beat.beat_track(
            y=audio, sr=sample_rate, hop_length=512
        )
        # Take every 4th beat as a bar downbeat
        bar_frames = beat_frames[::4]
        bar_times = librosa.frames_to_time(bar_frames, sr=sample_rate, hop_length=512)
        marks = [
            TimingMark(time_ms=int(round(t * 1000)), confidence=None)
            for t in bar_times
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
