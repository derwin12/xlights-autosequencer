"""T025: Tests for Vamp harmony algorithms.

Plugin-dependent tests skip when nnls-chroma vamp plugins aren't installed.
The mock-based smoke tests run unconditionally and protect the shape
contract that downstream consumers (chord_color_for_time, the orchestrator's
L6 chroma_curve assembly) depend on.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from src.analyzer.audio import load
from src.analyzer.result import ChromaCurve
from tests.conftest import vamp_plugin_available

nnls_available = pytest.mark.skipif(
    not vamp_plugin_available("nnls-chroma:chordino"),
    reason="NNLS Chroma / Chordino Vamp plugin not installed",
)


# ── Module-level smoke (no vamp plugin required) ─────────────────────────────


def test_module_imports_with_no_nameerror():
    """bug-139 / PR #100 regression guard. The original NNLSChromaAlgorithm
    referenced TimingMark without importing it, so importing the module
    raised at the first invocation. Reading the module-level symbols here
    is the cheapest possible coverage for that class of import bug."""
    from src.analyzer.algorithms.vamp_harmony import (
        ChordinoAlgorithm,
        NNLSChromaAlgorithm,
    )
    assert ChordinoAlgorithm.name == "chordino_chords"
    assert NNLSChromaAlgorithm.name == "nnls_chroma"


def test_nnls_chroma_element_type_is_value_curve():
    """Spec contract: nnls_chroma must register as value_curve, not harmonic."""
    from src.analyzer.algorithms.vamp_harmony import NNLSChromaAlgorithm
    assert NNLSChromaAlgorithm.element_type == "value_curve"


def test_chordino_element_type_is_harmonic():
    """Spec contract: Chordino emits discrete chord events; remains harmonic."""
    from src.analyzer.algorithms.vamp_harmony import ChordinoAlgorithm
    assert ChordinoAlgorithm.element_type == "harmonic"


# ── Mock-based unit tests for NNLS Chroma _run shape ─────────────────────────


@pytest.fixture
def fake_vamp(monkeypatch):
    """Stub `vamp.process_audio` with a synthetic chroma generator."""
    holder = types.SimpleNamespace(frames=[])

    def _process_audio(audio, sample_rate, plugin_key, output=None):
        for frame in holder.frames:
            yield frame

    fake_module = types.ModuleType("vamp")
    fake_module.process_audio = _process_audio  # type: ignore[attr-defined]
    fake_module.collect = lambda *a, **kw: {"list": []}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vamp", fake_module)
    return holder


class TestNNLSChromaShape:
    def test_returns_chroma_curve_with_empty_marks(self, fake_vamp):
        # 100 frames of synthetic chroma at 50 ms intervals (20 fps)
        fake_vamp.frames = [
            {"timestamp": i * 0.05, "values": [(i + p) % 12 / 11.0 for p in range(12)]}
            for i in range(100)
        ]
        from src.analyzer.algorithms.vamp_harmony import NNLSChromaAlgorithm

        algo = NNLSChromaAlgorithm()
        track = algo._run(np.zeros(22050, dtype=np.float32), 22050)

        assert track.element_type == "value_curve"
        assert track.marks == []
        vc = getattr(track, "value_curve", None)
        assert isinstance(vc, ChromaCurve)
        assert len(vc.values) == 100
        # Each row has 12 entries, all in [0, 100]
        for row in vc.values:
            assert len(row) == 12
            assert all(0 <= v <= 100 for v in row)
        # fps inferred from 50 ms spacing should be ~20
        assert vc.fps == 20

    def test_handles_empty_frames(self, fake_vamp):
        fake_vamp.frames = []
        from src.analyzer.algorithms.vamp_harmony import NNLSChromaAlgorithm
        track = NNLSChromaAlgorithm()._run(np.zeros(22050, dtype=np.float32), 22050)
        assert isinstance(track.value_curve, ChromaCurve)
        assert track.value_curve.values == []
        assert track.value_curve.fps == 20  # default fallback
        assert track.marks == []

    def test_silent_frame_yields_zeros_not_division_error(self, fake_vamp):
        # Frame with all-zero chroma (silence) must not divide by zero.
        fake_vamp.frames = [
            {"timestamp": 0.0, "values": [0.0] * 12},
            {"timestamp": 0.05, "values": [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
        ]
        from src.analyzer.algorithms.vamp_harmony import NNLSChromaAlgorithm
        track = NNLSChromaAlgorithm()._run(np.zeros(22050, dtype=np.float32), 22050)
        assert track.value_curve.values[0] == [0] * 12
        # Second frame: peak is 0.5, so first bin should be 100, rest 0
        assert track.value_curve.values[1][0] == 100
        assert track.value_curve.values[1][1:] == [0] * 11

    def test_skips_frames_with_no_values_field(self, fake_vamp):
        fake_vamp.frames = [
            {"timestamp": 0.0},  # missing values
            {"timestamp": 0.05, "values": [1.0] * 12},
        ]
        from src.analyzer.algorithms.vamp_harmony import NNLSChromaAlgorithm
        track = NNLSChromaAlgorithm()._run(np.zeros(22050, dtype=np.float32), 22050)
        # Only the second frame contributed
        assert len(track.value_curve.values) == 1


# ── Plugin-dependent integration tests (skipped on CI) ───────────────────────


@pytest.fixture(scope="module")
def beat_audio(beat_fixture_path):
    audio, sr, _ = load(str(beat_fixture_path))
    return audio, sr


@nnls_available
def test_chord_changes_produces_track(beat_audio):
    from src.analyzer.algorithms.vamp_harmony import ChordinoAlgorithm
    audio, sr = beat_audio
    track = ChordinoAlgorithm().run(audio, sr)
    assert track is not None
    assert track.element_type == "harmonic"


@nnls_available
def test_chroma_curve_has_more_frames_than_chord_events(beat_audio):
    """The chroma curve emits at ~20 fps; chord events emit on chord changes
    (typically ~once per bar). On any non-trivial fixture, frames > events."""
    from src.analyzer.algorithms.vamp_harmony import (
        ChordinoAlgorithm,
        NNLSChromaAlgorithm,
    )
    audio, sr = beat_audio
    chords = ChordinoAlgorithm().run(audio, sr)
    chroma = NNLSChromaAlgorithm().run(audio, sr)
    assert chroma.element_type == "value_curve"
    assert isinstance(chroma.value_curve, ChromaCurve)
    assert len(chroma.value_curve.values) >= chords.mark_count
