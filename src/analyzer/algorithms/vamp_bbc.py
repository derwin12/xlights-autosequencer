"""BBC Vamp plugin wrappers: energy, spectral flux, peaks, rhythm.

Energy, spectral flux, and peaks produce value curves (continuous data).
Rhythm produces timing marks (discrete events).
"""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack, ValueCurve

__all__ = [
    "BBCEnergyAlgorithm",
    "BBCSpectralFluxAlgorithm",
    "BBCPeaksAlgorithm",
    "BBCRhythmAlgorithm",
]


def _vamp_vector_to_curve(output: dict, duration_ms: int) -> list[int]:
    """Convert vamp vector output to normalized 0-100 int values."""
    vectors = output.get("vector", [])
    if not vectors or len(vectors) < 2:
        return []
    # vectors is (timestamps, np.array) pairs
    timestamps, values = vectors
    if hasattr(values, '__len__') and len(values) == 0:
        return []
    arr = np.array(values, dtype=np.float64) if not isinstance(values, np.ndarray) else values.astype(np.float64)
    if arr.ndim > 1:
        arr = arr.mean(axis=1) if arr.shape[0] > arr.shape[1] else arr.mean(axis=0)
    # Normalize to 0-100
    vmin, vmax = float(arr.min()), float(arr.max())
    if vmax - vmin < 1e-9:
        return [50] * len(arr)
    normalized = ((arr - vmin) / (vmax - vmin) * 100).astype(int)
    return [max(0, min(100, int(v))) for v in normalized]


def _vamp_list_to_marks(items: list) -> list[TimingMark]:
    marks = []
    for item in items:
        ts = item.get("timestamp") if isinstance(item, dict) else getattr(item, "timestamp", None)
        if ts is not None:
            ms = int(round(float(ts) * 1000))
            marks.append(TimingMark(time_ms=ms, confidence=None))
    return marks


class BBCEnergyAlgorithm(Algorithm):
    """BBC RMS energy envelope — continuous value curve."""

    name = "bbc_energy"
    element_type = "value_curve"
    library = "vamp"
    plugin_key = "bbc-vamp-plugins:bbc-energy"
    parameters = {}
    preferred_stem = "full_mix"
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        duration_ms = int(len(audio) / sample_rate * 1000)
        values = _vamp_vector_to_curve(outputs, duration_ms)
        fps = round(len(values) * 1000 / duration_ms) if duration_ms > 0 and values else 20
        stem = getattr(self, "_stem_source", self.preferred_stem)
        track = TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=[], quality_score=0.0,
            stem_source=stem,
        )
        track.value_curve = ValueCurve(name=self.name, stem_source=stem, fps=fps, values=values)
        return track


class BBCSpectralFluxAlgorithm(Algorithm):
    """BBC spectral change rate — continuous value curve."""

    name = "bbc_spectral_flux"
    element_type = "value_curve"
    library = "vamp"
    plugin_key = "bbc-vamp-plugins:bbc-spectral-flux"
    parameters = {}
    preferred_stem = "full_mix"
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        duration_ms = int(len(audio) / sample_rate * 1000)
        values = _vamp_vector_to_curve(outputs, duration_ms)
        fps = round(len(values) * 1000 / duration_ms) if duration_ms > 0 and values else 20
        stem = getattr(self, "_stem_source", self.preferred_stem)
        track = TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=[], quality_score=0.0,
            stem_source=stem,
        )
        track.value_curve = ValueCurve(name=self.name, stem_source=stem, fps=fps, values=values)
        return track


class BBCPeaksAlgorithm(Algorithm):
    """BBC amplitude peak/trough detection — continuous value curve."""

    name = "bbc_peaks"
    element_type = "value_curve"
    library = "vamp"
    plugin_key = "bbc-vamp-plugins:bbc-peaks"
    parameters = {}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        duration_ms = int(len(audio) / sample_rate * 1000)
        values = _vamp_vector_to_curve(outputs, duration_ms)
        fps = round(len(values) * 1000 / duration_ms) if duration_ms > 0 and values else 20
        stem = getattr(self, "_stem_source", self.preferred_stem)
        track = TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=[], quality_score=0.0,
            stem_source=stem,
        )
        track.value_curve = ValueCurve(name=self.name, stem_source=stem, fps=fps, values=values)
        return track


class BBCRhythmAlgorithm(Algorithm):
    """BBC rhythmic features — timing marks (discrete events)."""

    name = "bbc_rhythm"
    element_type = "onset"
    library = "vamp"
    plugin_key = "bbc-vamp-plugins:bbc-rhythm"
    parameters = {}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        marks = _vamp_list_to_marks(outputs.get("list", []))
        return TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=marks, quality_score=0.0,
        )
