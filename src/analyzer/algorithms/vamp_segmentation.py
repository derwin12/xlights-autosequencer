"""Segmentino Vamp plugin wrapper: automatic structural segmentation."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack

__all__ = [
    "SegmentinoAlgorithm",
]


class SegmentinoAlgorithm(Algorithm):
    """Segmentino structural segmenter — groups repeated sections."""

    name = "segmentino"
    element_type = "structure"
    library = "vamp"
    plugin_key = "segmentino:segmentino"
    parameters = {}
    preferred_stem = "full_mix"
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        items = outputs.get("list", [])
        marks = []
        for item in items:
            ts = item.get("timestamp") if isinstance(item, dict) else getattr(item, "timestamp", None)
            if ts is not None:
                ms = int(round(float(ts) * 1000))
                marks.append(TimingMark(time_ms=ms, confidence=None))
        return TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )
