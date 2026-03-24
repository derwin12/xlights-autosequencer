"""T033: Vamp onset detection algorithms — QM onset detector."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack


def _vamp_outputs_to_marks(outputs: list) -> list[TimingMark]:
    marks = []
    for output in outputs:
        t = output["timestamp"]
        t_sec = t.to_float() if hasattr(t, "to_float") else float(t)
        marks.append(TimingMark(time_ms=int(round(t_sec * 1000)), confidence=None))
    return marks


class QMOnsetComplexAlgorithm(Algorithm):
    """QM onset detector (complex domain) via Vamp."""

    name = "qm_onsets_complex"
    element_type = "onset"
    library = "vamp"
    plugin_key = "qm-vamp-plugins:qm-onsetdetector"
    parameters = {"dftype": 3}  # 3 = Complex Domain
    vamp_output = "onsets"
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        outputs = vamp.collect(
            audio, sample_rate, self.plugin_key,
            output=self.vamp_output,
            parameters=self.parameters,
        )
        marks = _vamp_outputs_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class QMOnsetHFCAlgorithm(Algorithm):
    """QM onset detector (high-frequency content) via Vamp."""

    name = "qm_onsets_hfc"
    element_type = "onset"
    library = "vamp"
    plugin_key = "qm-vamp-plugins:qm-onsetdetector"
    parameters = {"dftype": 0}  # 0 = High-Frequency Content
    vamp_output = "onsets"
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        outputs = vamp.collect(
            audio, sample_rate, self.plugin_key,
            output=self.vamp_output,
            parameters=self.parameters,
        )
        marks = _vamp_outputs_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class QMOnsetPhaseAlgorithm(Algorithm):
    """QM onset detector (phase deviation) via Vamp."""

    name = "qm_onsets_phase"
    element_type = "onset"
    library = "vamp"
    plugin_key = "qm-vamp-plugins:qm-onsetdetector"
    parameters = {"dftype": 2}  # 2 = Phase Deviation
    vamp_output = "onsets"
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        outputs = vamp.collect(
            audio, sample_rate, self.plugin_key,
            output=self.vamp_output,
            parameters=self.parameters,
        )
        marks = _vamp_outputs_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
