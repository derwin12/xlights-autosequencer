"""T030: Librosa full-spectrum onset detection algorithm."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack

_HOP_LENGTH = 512


class LibrosaOnsetAlgorithm(Algorithm):
    """Full-spectrum onset detection using librosa."""

    name = "librosa_onsets"
    element_type = "onset"
    library = "librosa"
    plugin_key = None
    parameters = {"hop_length": 512}
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import librosa

        onset_frames = librosa.onset.onset_detect(
            y=audio,
            sr=sample_rate,
            hop_length=_HOP_LENGTH,
            backtrack=True,
        )
        times = librosa.frames_to_time(onset_frames, sr=sample_rate, hop_length=_HOP_LENGTH)
        marks = [
            TimingMark(time_ms=int(round(t * 1000)), confidence=None) for t in times
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
