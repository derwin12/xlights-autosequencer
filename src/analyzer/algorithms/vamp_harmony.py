"""T035: Vamp NNLS Chroma and Chordino harmony algorithms."""
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


class ChordinoAlgorithm(Algorithm):
    """Chord change detector via Vamp nnls-chroma:chordino."""

    name = "chordino_chords"
    element_type = "harmonic"
    library = "vamp"
    plugin_key = "nnls-chroma:chordino"
    parameters = {}
    vamp_output = "simplechord"
    preferred_stem = "piano"
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


class NNLSChromaAlgorithm(Algorithm):
    """Chroma frame events via Vamp nnls-chroma:nnls-chroma."""

    name = "nnls_chroma"
    element_type = "harmonic"
    library = "vamp"
    plugin_key = "nnls-chroma:nnls-chroma"
    parameters = {}
    vamp_output = "chroma"
    preferred_stem = "piano"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        # process_audio returns per-frame dicts with 'timestamp' and 'values'
        frames = list(vamp.process_audio(
            audio, sample_rate, self.plugin_key, output=self.vamp_output
        ))
        marks = []
        for frame in frames:
            t = frame["timestamp"]
            t_sec = t.to_float() if hasattr(t, "to_float") else float(t)
            marks.append(TimingMark(time_ms=int(round(t_sec * 1000)), confidence=None))
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
