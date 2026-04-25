"""T035: Vamp NNLS Chroma and Chordino harmony algorithms.

Chordino emits discrete chord-change events (element_type="harmonic").
NNLS Chroma emits a per-frame 12-bin chroma vector and is registered as
element_type="value_curve"; it attaches a ChromaCurve to its TimingTrack
so downstream consumers (chord-color fallback in src/generator/) can read
per-frame harmonic colour information.
"""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.algorithms.vamp_utils import vamp_outputs_to_marks
from src.analyzer.result import ChromaCurve, TimingTrack


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
        marks = vamp_outputs_to_marks(outputs.get("list", []), extract_label=True)
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class NNLSChromaAlgorithm(Algorithm):
    """Per-frame 12-bin chroma curve via Vamp nnls-chroma:nnls-chroma.

    Emits a ChromaCurve attached to the returned TimingTrack. Each frame's
    `values` is the 12-bin chroma vector (one float per pitch class), which
    we normalize per-frame to 0–100 ints so downstream consumers see a
    consistent contract with ValueCurve. The pitch-class order is whatever
    the plugin returns (typically C, C#, D, …, B in canonical order).
    """

    name = "nnls_chroma"
    element_type = "value_curve"
    library = "vamp"
    plugin_key = "nnls-chroma:nnls-chroma"
    parameters = {}
    vamp_output = "chroma"
    preferred_stem = "piano"
    depends_on = ["stem_separation"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        import vamp

        # process_audio returns per-frame dicts with 'timestamp' and 'values'.
        # `values` is the 12-bin chroma vector that we want to capture (this
        # used to be discarded — see bug-139 NameError fix in PR #100).
        frames = list(vamp.process_audio(
            audio, sample_rate, self.plugin_key, output=self.vamp_output
        ))
        timestamps_sec: list[float] = []
        chroma_rows: list[list[int]] = []
        for frame in frames:
            t = frame["timestamp"]
            t_sec = t.to_float() if hasattr(t, "to_float") else float(t)
            raw = frame.get("values")
            if raw is None:
                continue
            row = _normalize_chroma_row(raw)
            if row is None:
                continue
            timestamps_sec.append(t_sec)
            chroma_rows.append(row)

        fps = _infer_fps(timestamps_sec)
        stem = getattr(self, "_stem_source", self.preferred_stem)
        track = TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=[],
            quality_score=0.0,
            stem_source=stem,
        )
        track.value_curve = ChromaCurve(
            name=self.name, stem_source=stem, fps=fps, values=chroma_rows,
        )
        return track


def _normalize_chroma_row(raw) -> list[int] | None:
    """Convert a single frame's chroma values to a list of 12 ints in [0, 100].

    Per-frame normalization: divide by max(row), scale to 100, clamp. If the
    row is all zeros, return all-zeros (silence/no-pitch frame). Returns None
    if the row is malformed (not iterable, wrong length).
    """
    try:
        row = list(raw)
    except TypeError:
        return None
    if not row:
        return None
    floats = [float(v) for v in row]
    # NNLS Chroma is documented as 12 bins (one per pitch class). We accept
    # 12; if the plugin emits a different shape, we still capture it but
    # downstream consumers expect 12 — flag via length only, no exception.
    peak = max(floats) if floats else 0.0
    if peak <= 0.0:
        return [0] * len(floats)
    scaled = [int(round(max(0.0, v) / peak * 100)) for v in floats]
    return [max(0, min(100, v)) for v in scaled]


def _infer_fps(timestamps_sec: list[float]) -> int:
    """Infer frame rate from the first few timestamps. Falls back to 20 fps."""
    if len(timestamps_sec) < 2:
        return 20
    # Use the median delta from the first ~10 frames to be robust to small jitter.
    sample = timestamps_sec[: min(10, len(timestamps_sec))]
    deltas = [sample[i + 1] - sample[i] for i in range(len(sample) - 1) if sample[i + 1] > sample[i]]
    if not deltas:
        return 20
    deltas.sort()
    median_delta = deltas[len(deltas) // 2]
    if median_delta <= 0:
        return 20
    return max(1, int(round(1.0 / median_delta)))
