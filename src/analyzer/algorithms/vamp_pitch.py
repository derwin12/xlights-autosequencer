"""T035: Vamp pYIN pitch/note algorithms."""
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


class PYINNotesAlgorithm(Algorithm):
    """pYIN note detector via Vamp pyin:pyin."""

    name = "pyin_notes"
    element_type = "melody"
    library = "vamp"
    plugin_key = "pyin:pyin"
    parameters = {}
    vamp_output = "notes"
    preferred_stem = "vocals"
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


class PYINPitchChangesAlgorithm(Algorithm):
    """pYIN smoothed pitch output (pitch changes) via Vamp pyin:pyin."""

    name = "pyin_pitch_changes"
    element_type = "melody"
    library = "vamp"
    plugin_key = "pyin:pyin"
    parameters = {}
    vamp_output = "smoothedpitchtrack"
    preferred_stem = "vocals"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        outputs = vamp.collect(
            audio, sample_rate, self.plugin_key,
            output=self.vamp_output,
            parameters=self.parameters,
        )
        # smoothedpitchtrack is a dense frame-by-frame output; pick frames
        # where pitch is voiced (value > 0) to generate pitch-change events.
        raw = outputs.get("list", [])
        marks = []
        prev_pitch = 0.0
        for item in raw:
            pitch = float(item.get("value", [0])[0]) if item.get("value") else 0.0
            if pitch > 0 and abs(pitch - prev_pitch) > 10:
                t = item["timestamp"]
                t_sec = t.to_float() if hasattr(t, "to_float") else float(t)
                marks.append(TimingMark(time_ms=int(round(t_sec * 1000)), confidence=None))
                prev_pitch = pitch
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
