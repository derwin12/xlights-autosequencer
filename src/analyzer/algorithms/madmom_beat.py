"""T031: Madmom RNN beat and downbeat tracking algorithms (optional)."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack


class MadmomBeatAlgorithm(Algorithm):
    """RNN+DBN beat tracker via madmom."""

    name = "madmom_beats"
    element_type = "beat"
    library = "madmom"
    plugin_key = None
    parameters = {}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        from madmom.features.beats import RNNBeatProcessor, BeatTrackingProcessor

        proc = BeatTrackingProcessor(fps=100)
        act = RNNBeatProcessor()(audio.astype(np.float32))
        beat_times = proc(act)
        marks = [
            TimingMark(time_ms=int(round(float(t) * 1000)), confidence=None)
            for t in beat_times
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class MadmomDownbeatAlgorithm(Algorithm):
    """RNN downbeat tracker via madmom."""

    name = "madmom_downbeats"
    element_type = "bar"
    library = "madmom"
    plugin_key = None
    parameters = {}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

        proc = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)
        act = RNNDownBeatProcessor()(audio.astype(np.float32))
        downbeats = proc(act)
        # downbeats is Nx2 array: [time, beat_number]; keep beat_number==1 (downbeats)
        marks = [
            TimingMark(time_ms=int(round(float(row[0]) * 1000)), confidence=None)
            for row in downbeats
            if int(row[1]) == 1
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
