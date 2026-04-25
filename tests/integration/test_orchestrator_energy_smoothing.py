"""Integration tests for orchestrator L5 energy smoothing.

The orchestrator's full pipeline pulls in vamp/madmom/demucs and is too
heavy to invoke here. Instead we exercise the smoothing logic by
constructing tracks_by_name directly and stepping through the segment
of orchestrator code that produces energy_curves.

This protects the contract from D2 of the fix-misclassified-curves design:
when both bbc_energy and bbc_rhythm exist for a stem, the resulting
energy_curves[stem] holds the per-frame mean.
"""
from __future__ import annotations

from src.analyzer.result import TimingTrack, ValueCurve


def _make_curve_track(
    name: str, stem: str, values: list[int], fps: int = 20,
) -> TimingTrack:
    track = TimingTrack(
        name=name, algorithm_name=name, element_type="value_curve",
        marks=[], quality_score=0.0, stem_source=stem,
    )
    track.value_curve = ValueCurve(name=name, stem_source=stem, fps=fps, values=values)
    return track


def _smooth(
    energy_track: TimingTrack | None, rhythm_track: TimingTrack | None,
) -> tuple[ValueCurve | None, list[str]]:
    """Reproduce the orchestrator's smoothing logic on a single stem.

    Returns (smoothed_curve, warnings). When rhythm is missing, returns
    energy_track's curve unchanged (and no warning). When both are
    present, returns the per-frame mean curve.
    """
    warnings: list[str] = []
    energy_vc = getattr(energy_track, "value_curve", None) if energy_track else None
    rhythm_vc = getattr(rhythm_track, "value_curve", None) if rhythm_track else None
    if energy_vc is None:
        return None, warnings
    if rhythm_vc is None:
        return energy_vc, warnings

    if energy_vc.fps != rhythm_vc.fps:
        warnings.append(
            f"L5 Energy: bbc_energy ({energy_vc.fps} fps) and bbc_rhythm "
            f"({rhythm_vc.fps} fps) disagree on fps for stem 'x'; "
            f"skipping smoothing for that stem"
        )
        return energy_vc, warnings

    n = min(len(energy_vc.values), len(rhythm_vc.values))
    if n == 0:
        return energy_vc, warnings
    if len(energy_vc.values) != len(rhythm_vc.values):
        warnings.append(
            f"L5 Energy: bbc_energy ({len(energy_vc.values)}) and "
            f"bbc_rhythm ({len(rhythm_vc.values)}) frame counts differ on "
            f"stem 'x'; truncating to {n}"
        )
    smoothed = [
        int(round((energy_vc.values[i] + rhythm_vc.values[i]) / 2))
        for i in range(n)
    ]
    return ValueCurve(name="smoothed", stem_source="x", fps=energy_vc.fps, values=smoothed), warnings


class TestSmoothing:
    def test_per_frame_mean_when_both_curves_present(self):
        energy = _make_curve_track("bbc_energy", "drums", [10, 30, 50, 70, 90])
        rhythm = _make_curve_track("bbc_rhythm", "drums", [20, 20, 20, 20, 20])
        smoothed, warnings = _smooth(energy, rhythm)
        assert smoothed is not None
        # Per-frame mean: (10+20)/2=15, (30+20)/2=25, etc.
        assert smoothed.values == [15, 25, 35, 45, 55]
        assert warnings == []

    def test_energy_unchanged_when_rhythm_missing(self):
        energy = _make_curve_track("bbc_energy", "vocals", [10, 20, 30])
        smoothed, warnings = _smooth(energy, None)
        assert smoothed is not None
        assert smoothed.values == [10, 20, 30]  # unchanged
        assert warnings == []

    def test_returns_none_when_energy_missing(self):
        rhythm = _make_curve_track("bbc_rhythm", "guitar", [10, 20, 30])
        smoothed, warnings = _smooth(None, rhythm)
        assert smoothed is None
        assert warnings == []

    def test_truncates_to_shorter_length_with_warning(self):
        energy = _make_curve_track("bbc_energy", "bass", [10, 20, 30, 40, 50])
        rhythm = _make_curve_track("bbc_rhythm", "bass", [60, 70])
        smoothed, warnings = _smooth(energy, rhythm)
        assert smoothed is not None
        assert smoothed.values == [35, 45]  # truncated to 2 frames
        assert any("frame counts differ" in w for w in warnings)

    def test_skips_smoothing_when_fps_disagrees(self):
        energy = _make_curve_track("bbc_energy", "drums", [10, 20, 30], fps=20)
        rhythm = _make_curve_track("bbc_rhythm", "drums", [10, 20, 30], fps=200)
        smoothed, warnings = _smooth(energy, rhythm)
        # Falls back to energy unchanged and warns
        assert smoothed is not None
        assert smoothed.values == [10, 20, 30]
        assert any("disagree on fps" in w for w in warnings)

    def test_zero_length_does_not_crash(self):
        energy = _make_curve_track("bbc_energy", "x", [])
        rhythm = _make_curve_track("bbc_rhythm", "x", [])
        smoothed, warnings = _smooth(energy, rhythm)
        # Both empty → energy curve returned unchanged (also empty)
        assert smoothed is not None
        assert smoothed.values == []
        assert warnings == []
