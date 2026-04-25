"""BBC Vamp plugin wrappers: energy, spectral flux, peaks, rhythm.

All four produce value curves (continuous frame-level data). Rhythm emits as
a dense list output at ~200 fps; the list values are extracted into a
ValueCurve for consistency with the other three.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingTrack, ValueCurve

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
    """BBC rhythmic features — continuous rhythm-strength curve.

    The plugin emits a dense list output (~200 fps, ~5 ms per frame). Each
    list item carries a per-frame strength value; we collect them into a
    ValueCurve so downstream consumers can treat it like the other BBC
    curves (smoothed against bbc_energy in orchestrator L5 assembly).
    """

    name = "bbc_rhythm"
    element_type = "value_curve"
    library = "vamp"
    plugin_key = "bbc-vamp-plugins:bbc-rhythm"
    parameters = {}
    preferred_stem = "drums"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp
        outputs = vamp.collect(audio, sample_rate, self.plugin_key, parameters=self.parameters)
        duration_ms = int(len(audio) / sample_rate * 1000)
        values, fps = _bbc_rhythm_list_to_curve(outputs.get("list", []), duration_ms)
        stem = getattr(self, "_stem_source", self.preferred_stem)
        track = TimingTrack(
            name=self.name, algorithm_name=self.name,
            element_type=self.element_type, marks=[], quality_score=0.0,
            stem_source=stem,
        )
        track.value_curve = ValueCurve(name=self.name, stem_source=stem, fps=fps, values=values)
        return track


def _bbc_rhythm_list_to_curve(items: list, duration_ms: int) -> tuple[list[int], int]:
    """Convert a dense vamp list output (timestamp + per-item value) into a
    normalized 0-100 ValueCurve. Returns (values, fps). Empty list → (
    [], 20)."""
    if not items or duration_ms <= 0:
        return [], 20
    raw: list[float] = []
    for item in items:
        v = item.get("values") if isinstance(item, dict) else None
        if v is None:
            v = item.get("value") if isinstance(item, dict) else None
        if v is None:
            continue
        # `value` / `values` may be a scalar or a 1-element list/array.
        if hasattr(v, "__iter__") and not isinstance(v, (str, bytes)):
            seq = list(v)
            if not seq:
                continue
            raw.append(float(seq[0]))
        else:
            raw.append(float(v))
    if not raw:
        return [], 20
    arr = np.array(raw, dtype=np.float64)
    vmin, vmax = float(arr.min()), float(arr.max())
    if vmax - vmin < 1e-9:
        normalized = [50] * len(arr)
    else:
        normalized = ((arr - vmin) / (vmax - vmin) * 100).astype(int).tolist()
        normalized = [max(0, min(100, int(v))) for v in normalized]
    fps = round(len(normalized) * 1000 / duration_ms) if duration_ms > 0 else 20
    return normalized, max(1, fps)
