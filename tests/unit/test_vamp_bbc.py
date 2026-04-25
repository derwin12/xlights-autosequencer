"""Unit tests for BBC vamp algorithm wrappers.

These tests stub `vamp.collect` so they run without the real BBC vamp plugin
installed (CI doesn't have vamp plugin .dylibs). The point is to verify the
shape contract — element_type, value_curve attachment, empty marks — that
downstream consumers depend on, not the audio analysis itself.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from src.analyzer.algorithms.vamp_bbc import (
    BBCEnergyAlgorithm,
    BBCRhythmAlgorithm,
    _bbc_rhythm_list_to_curve,
)
from src.analyzer.result import ValueCurve


@pytest.fixture
def fake_vamp(monkeypatch):
    """Inject a fake `vamp` module into sys.modules so the algorithm's
    `import vamp` inside `_run` resolves to our stub. Returns a holder we
    populate per-test with the desired output shape."""
    holder = types.SimpleNamespace(last_call=None, output={})

    def _collect(audio, sample_rate, plugin_key, parameters=None, output=None):
        holder.last_call = {
            "audio_len": len(audio),
            "sample_rate": sample_rate,
            "plugin_key": plugin_key,
        }
        return holder.output

    fake_module = types.ModuleType("vamp")
    fake_module.collect = _collect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vamp", fake_module)
    return holder


class TestBBCRhythmReclassification:
    def test_element_type_is_value_curve(self):
        # Class attribute, no need to instantiate.
        assert BBCRhythmAlgorithm.element_type == "value_curve"

    def test_run_attaches_value_curve_with_empty_marks(self, fake_vamp):
        # Stub returns 100 dense list items each with a scalar `value`.
        fake_vamp.output = {
            "list": [
                {"timestamp": i * 0.005, "value": [float(i % 50)]}
                for i in range(100)
            ]
        }
        algo = BBCRhythmAlgorithm()
        # 1 second of audio at 22050 Hz
        audio = np.zeros(22050, dtype=np.float32)
        track = algo._run(audio, 22050)

        assert track.element_type == "value_curve"
        assert track.marks == []
        vc = getattr(track, "value_curve", None)
        assert vc is not None
        assert isinstance(vc, ValueCurve)
        assert len(vc.values) == 100
        assert all(0 <= v <= 100 for v in vc.values)
        assert vc.fps > 0

    def test_run_handles_empty_output(self, fake_vamp):
        fake_vamp.output = {"list": []}
        algo = BBCRhythmAlgorithm()
        audio = np.zeros(22050, dtype=np.float32)
        track = algo._run(audio, 22050)
        assert track.value_curve is not None
        assert track.value_curve.values == []
        assert track.marks == []

    def test_run_handles_constant_signal(self, fake_vamp):
        # All-equal values must not produce divide-by-zero in normalization.
        fake_vamp.output = {
            "list": [{"timestamp": i * 0.005, "value": [42.0]} for i in range(10)]
        }
        algo = BBCRhythmAlgorithm()
        audio = np.zeros(22050, dtype=np.float32)
        track = algo._run(audio, 22050)
        assert track.value_curve.values == [50] * 10  # neutral midpoint


class TestBBCEnergyShapeContract:
    """Sanity-check that BBCEnergyAlgorithm still emits a ValueCurve with
    empty marks. The bbc_rhythm change must not regress the existing pattern."""

    def test_element_type_is_value_curve(self):
        assert BBCEnergyAlgorithm.element_type == "value_curve"

    def test_run_attaches_value_curve_with_empty_marks(self, fake_vamp):
        fake_vamp.output = {
            "vector": (np.array([0.0, 0.005]), np.array([0.1, 0.5]))
        }
        algo = BBCEnergyAlgorithm()
        audio = np.zeros(22050, dtype=np.float32)
        track = algo._run(audio, 22050)
        assert track.element_type == "value_curve"
        assert track.marks == []
        assert isinstance(track.value_curve, ValueCurve)


class TestBBCRhythmListToCurveHelper:
    def test_handles_iterable_value_field(self):
        items = [{"timestamp": 0, "values": [10.0]}, {"timestamp": 0.005, "values": [90.0]}]
        values, fps = _bbc_rhythm_list_to_curve(items, duration_ms=1000)
        assert values == [0, 100]
        assert fps > 0

    def test_handles_scalar_value_field(self):
        items = [{"timestamp": 0, "value": 10.0}, {"timestamp": 0.005, "value": 90.0}]
        values, _ = _bbc_rhythm_list_to_curve(items, duration_ms=1000)
        assert values == [0, 100]

    def test_skips_items_with_no_value(self):
        items = [
            {"timestamp": 0},  # no value field
            {"timestamp": 0.005, "value": [50.0]},
        ]
        values, _ = _bbc_rhythm_list_to_curve(items, duration_ms=1000)
        assert values == [50]

    def test_zero_duration_returns_default_fps(self):
        items = [{"timestamp": 0, "value": [1.0]}]
        values, fps = _bbc_rhythm_list_to_curve(items, duration_ms=0)
        assert values == []
        assert fps == 20
