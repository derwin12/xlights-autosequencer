"""Additional Vamp plugin wrappers: key detection, transcription, percussion, etc."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.algorithms.vamp_utils import vamp_list_to_marks
from src.analyzer.result import TimingMark, TimingTrack

__all__ = [
    "QMKeyAlgorithm",
    "QMTranscriptionAlgorithm",
    "SilvetNotesAlgorithm",
    "PercussionOnsetsAlgorithm",
    "AmplitudeFollowerAlgorithm",
    "TempogramAlgorithm",
]


class QMKeyAlgorithm(Algorithm):
    """QM key detector — key change events."""

    name = "qm_key"
    element_type = "harmonic"
    library = "vamp"
    plugin_key = "qm-vamp-plugins:qm-keydetector"
    parameters = {}
    preferred_stem = "full_mix"
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        marks = vamp_list_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )


class QMTranscriptionAlgorithm(Algorithm):
    """QM polyphonic transcription — note events."""

    name = "qm_transcription"
    element_type = "melody"
    library = "vamp"
    plugin_key = "qm-vamp-plugins:qm-transcription"
    parameters = {}
    preferred_stem = "piano"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        marks = vamp_list_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )


class SilvetNotesAlgorithm(Algorithm):
    """Silvet polyphonic transcription with velocity."""

    name = "silvet_notes"
    element_type = "melody"
    library = "vamp"
    plugin_key = "silvet:silvet"
    parameters = {}
    preferred_stem = "piano"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        marks = vamp_list_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )


class PercussionOnsetsAlgorithm(Algorithm):
    """Percussion-specific onset detector — drums only."""

    name = "percussion_onsets"
    element_type = "onset"
    library = "vamp"
    plugin_key = "vamp-example-plugins:percussiononsets"
    parameters = {}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        marks = vamp_list_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )


class AmplitudeFollowerAlgorithm(Algorithm):
    """Continuous amplitude envelope — value curve."""

    name = "amplitude_follower"
    element_type = "value_curve"
    library = "vamp"
    plugin_key = "vamp-example-plugins:amplitudefollower"
    parameters = {}
    preferred_stem = "full_mix"
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        # amplitudefollower returns vector output
        vectors = outputs.get("vector", [])
        marks = []
        curve = []
        if vectors and len(vectors) >= 2:
            timestamps, values = vectors
            arr = np.array(values, dtype=np.float64) if not isinstance(values, np.ndarray) else values.astype(np.float64)
            if arr.ndim > 1:
                arr = arr.mean(axis=-1)
            vmin, vmax = float(arr.min()), float(arr.max())
            if vmax - vmin > 1e-9:
                normalized = ((arr - vmin) / (vmax - vmin) * 100).astype(int)
                curve = [max(0, min(100, int(v))) for v in normalized]
            else:
                curve = [50] * len(arr)
            marks = [TimingMark(time_ms=i * 50, confidence=None) for i in range(len(curve))]
        track = TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )
        track.value_curve = curve
        return track


class TempogramAlgorithm(Algorithm):
    """Tempogram — tempo variation over time as a value curve."""

    name = "tempogram"
    element_type = "value_curve"
    library = "vamp"
    plugin_key = "tempogram:tempogram"
    parameters = {}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        # tempogram returns matrix output — take mean across frequency bins
        matrix = outputs.get("matrix", [])
        marks = []
        curve = []
        if matrix and len(matrix) >= 2:
            timestamps, values = matrix
            arr = np.array(values, dtype=np.float64) if not isinstance(values, np.ndarray) else values.astype(np.float64)
            if arr.ndim > 1:
                arr = arr.mean(axis=-1)
            vmin, vmax = float(arr.min()), float(arr.max())
            if vmax - vmin > 1e-9:
                normalized = ((arr - vmin) / (vmax - vmin) * 100).astype(int)
                curve = [max(0, min(100, int(v))) for v in normalized]
            else:
                curve = [50] * len(arr)
            marks = [TimingMark(time_ms=i * 50, confidence=None) for i in range(len(curve))]
        track = TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )
        track.value_curve = curve
        return track
