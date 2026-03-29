"""Aubio Vamp plugin wrappers: onset detection, tempo/beat tracking, note events."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.algorithms.vamp_utils import vamp_list_to_marks
from src.analyzer.result import TimingTrack

__all__ = [
    "AubioOnsetAlgorithm",
    "AubioTempoAlgorithm",
    "AubioNotesAlgorithm",
]


class AubioOnsetAlgorithm(Algorithm):
    """Aubio onset detector — multiple detection functions."""

    name = "aubio_onset"
    element_type = "onset"
    library = "vamp"
    plugin_key = "vamp-aubio:aubioonset"
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


class AubioTempoAlgorithm(Algorithm):
    """Aubio tempo/beat tracker."""

    name = "aubio_tempo"
    element_type = "beat"
    library = "vamp"
    plugin_key = "vamp-aubio:aubiotempo"
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


class AubioNotesAlgorithm(Algorithm):
    """Aubio note tracker — onset + pitch + duration."""

    name = "aubio_notes"
    element_type = "melody"
    library = "vamp"
    plugin_key = "vamp-aubio:aubionotes"
    parameters = {}
    preferred_stem = "vocals"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        marks = vamp_list_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )
