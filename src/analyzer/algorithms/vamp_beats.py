"""T032: Vamp beat tracking algorithms — QM and BeatRoot."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.algorithms.vamp_utils import vamp_outputs_to_marks
from src.analyzer.result import TimingTrack


class QMBeatAlgorithm(Algorithm):
    """QM beat tracker via Vamp qm-vamp-plugins:qm-tempotracker."""

    name = "qm_beats"
    element_type = "beat"
    library = "vamp"
    plugin_key = "qm-vamp-plugins:qm-tempotracker"
    parameters = {}
    vamp_output = "beats"
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        outputs = vamp.collect(
            audio, sample_rate, self.plugin_key,
            output=self.vamp_output,
            parameters=self.parameters,
        )
        marks = vamp_outputs_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class QMBarAlgorithm(Algorithm):
    """QM bar tracker via Vamp qm-vamp-plugins:qm-barbeattracker."""

    name = "qm_bars"
    element_type = "bar"
    library = "vamp"
    plugin_key = "qm-vamp-plugins:qm-barbeattracker"
    parameters = {}
    vamp_output = "bars"
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        outputs = vamp.collect(
            audio, sample_rate, self.plugin_key,
            output=self.vamp_output,
            parameters=self.parameters,
        )
        marks = vamp_outputs_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class BeatRootAlgorithm(Algorithm):
    """BeatRoot beat tracker via Vamp beatroot-vamp:beatroot."""

    name = "beatroot_beats"
    element_type = "beat"
    library = "vamp"
    plugin_key = "beatroot-vamp:beatroot"
    parameters = {}
    vamp_output = "beats"
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        outputs = vamp.collect(
            audio, sample_rate, self.plugin_key,
            output=self.vamp_output,
            parameters=self.parameters,
        )
        marks = vamp_outputs_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
