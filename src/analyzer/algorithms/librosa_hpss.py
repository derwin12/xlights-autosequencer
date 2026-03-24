"""T029: Librosa HPSS (Harmonic-Percussive Source Separation) algorithms."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack

_HOP_LENGTH = 512


class LibrosaDrumsAlgorithm(Algorithm):
    """Percussive source onset detection via HPSS."""

    name = "drums"
    element_type = "percussion"
    library = "librosa"
    plugin_key = None
    parameters = {"hop_length": 512}
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import librosa

        _, percussive = librosa.effects.hpss(audio)
        onset_env = librosa.onset.onset_strength(
            y=percussive, sr=sample_rate, hop_length=_HOP_LENGTH
        )
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env,
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


class LibrosaHarmonicAlgorithm(Algorithm):
    """Harmonic source peak detection via HPSS."""

    name = "harmonic_peaks"
    element_type = "harmonic"
    library = "librosa"
    plugin_key = None
    parameters = {"hop_length": 512}
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import librosa

        harmonic, _ = librosa.effects.hpss(audio)
        onset_env = librosa.onset.onset_strength(
            y=harmonic, sr=sample_rate, hop_length=_HOP_LENGTH
        )
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env,
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
