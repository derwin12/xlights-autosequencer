"""Tests for _place_chase_across_groups energy-trend-driven chase direction."""
from __future__ import annotations

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.models import EffectDefinition
from src.generator.effect_placer import _place_chase_across_groups
from src.generator.models import SectionEnergy
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer

_SECTION = SectionEnergy(
    label="chorus", start_ms=0, end_ms=10000, energy_score=80,
    mood_tier="structural", impact_count=0,
)
_LAYER = EffectLayer(variant="Color Wash")


def _effect_def() -> EffectDefinition:
    return EffectDefinition(
        name="Color Wash", xlights_id="E_COLORWASH", category="test",
        description="test effect", intent="fill", parameters=[],
        prop_suitability={}, analysis_mappings=[], layer_role="standalone",
        duration_type="beat",
    )


def _groups() -> list[PowerGroup]:
    return [
        PowerGroup(name=f"04_BEAT_{i}", tier=4, members=[f"Model_{i}"])
        for i in (1, 2, 3, 4)
    ]


def _beats(count: int, interval_ms: int = 500) -> list[TimingMark]:
    return [TimingMark(time_ms=i * interval_ms, confidence=1.0) for i in range(count)]


def _hierarchy(beat_marks: list[TimingMark], energy_values: list[int] | None,
               fps: int = 20, duration_ms: int = 10000) -> HierarchyResult:
    beats_track = TimingTrack(
        name="beats", algorithm_name="test", element_type="beat",
        marks=beat_marks, quality_score=0.9,
    )
    hierarchy = HierarchyResult(
        schema_version="2.0.0", source_file="test.mp3", source_hash="abc123",
        duration_ms=duration_ms, estimated_bpm=120.0, beats=beats_track,
    )
    if energy_values is not None:
        hierarchy.energy_curves = {
            "full_mix": ValueCurve(name="full_mix", stem_source="full_mix",
                                    fps=fps, values=energy_values),
        }
    return hierarchy


def _group_index_sequence(result: dict) -> list[int]:
    """Flatten {group_name: [placement]} into the 1-4 group-index sequence,
    ordered by start_ms. Doesn't assume every beat survives
    _apply_density_filter -- only the relative order of whatever placements
    exist matters for these tests."""
    flat = [(p.start_ms, int(gname.rsplit("_", 1)[-1]))
            for gname, placements in result.items() for p in placements]
    flat.sort(key=lambda t: t[0])
    return [idx for _, idx in flat]


def _step_deltas(indices: list[int], num_groups: int = 4) -> list[int]:
    """Consecutive step deltas mod num_groups, normalized to -1 or +1."""
    deltas = []
    for a, b in zip(indices, indices[1:]):
        raw = (b - a) % num_groups
        deltas.append(1 if raw == 1 else -1 if raw == num_groups - 1 else raw)
    return deltas


class TestNoEnergyCurveFallsBackToRoundRobin:
    def test_fixed_forward_round_robin_when_no_curve(self) -> None:
        beats = _beats(8)
        hierarchy = _hierarchy(beats, energy_values=None)
        result = _place_chase_across_groups(
            _effect_def(), _LAYER, _groups(), _SECTION, hierarchy, ["#FFFFFF"],
        )
        indices = _group_index_sequence(result)
        assert indices[0] == 1
        assert all(d == 1 for d in _step_deltas(indices))


class TestRisingEnergyStepsForward:
    def test_steady_rise_steps_forward_through_groups(self) -> None:
        beats = _beats(16)
        # Monotonically increasing energy -> every trend check reads "rising".
        # Curve must cover the full beat range at this fps, or
        # _sample_energy_curve returns 0 past the end and fakes a "falling"
        # trend on the last few beats.
        fps = 20
        frames_needed = int(beats[-1].time_ms * fps / 1000) + 10
        energy = [min(100, i) for i in range(frames_needed)]
        hierarchy = _hierarchy(beats, energy_values=energy, fps=fps)
        result = _place_chase_across_groups(
            _effect_def(), _LAYER, _groups(), _SECTION, hierarchy, ["#FFFFFF"],
        )
        indices = _group_index_sequence(result)
        assert len(indices) >= 8
        assert all(d == 1 for d in _step_deltas(indices))


class TestFallingEnergyStepsBackward:
    def test_steady_fall_steps_backward_through_groups(self) -> None:
        beats = _beats(16)
        # Monotonically decreasing energy -> every trend check (once enough
        # history exists) reads "falling". Curve covers the full beat range
        # (see rising-energy test for why that matters).
        fps = 20
        frames_needed = int(beats[-1].time_ms * fps / 1000) + 10
        energy = [max(0, 100 - i) for i in range(frames_needed)]
        hierarchy = _hierarchy(beats, energy_values=energy, fps=fps)
        result = _place_chase_across_groups(
            _effect_def(), _LAYER, _groups(), _SECTION, hierarchy, ["#FFFFFF"],
        )
        indices = _group_index_sequence(result)
        assert len(indices) >= 8
        deltas = _step_deltas(indices)
        # First couple of steps use the default forward direction (no trend
        # signal yet); once the trend kicks in every remaining step is -1.
        assert deltas[-4:] == [-1, -1, -1, -1]


class TestFlatEnergyPersistsDirection:
    def test_flat_energy_keeps_current_direction_no_flicker(self) -> None:
        beats = _beats(16)
        # Rises briefly then goes flat -- direction should stay forward
        # rather than resetting or flip-flopping once the trend is flat.
        # Curve covers the full beat range (see rising-energy test).
        fps = 20
        frames_needed = int(beats[-1].time_ms * fps / 1000) + 10
        energy = ([0, 10, 20, 30] + [30] * frames_needed)[:frames_needed]
        hierarchy = _hierarchy(beats, energy_values=energy, fps=fps)
        result = _place_chase_across_groups(
            _effect_def(), _LAYER, _groups(), _SECTION, hierarchy, ["#FFFFFF"],
        )
        indices = _group_index_sequence(result)
        assert all(d == 1 for d in _step_deltas(indices))


class TestDeterministic:
    def test_same_inputs_produce_same_sequence(self) -> None:
        beats = _beats(16)
        energy = [i % 40 for i in range(len(beats))]
        hierarchy_a = _hierarchy(beats, energy_values=energy, fps=20)
        hierarchy_b = _hierarchy(beats, energy_values=energy, fps=20)
        result_a = _place_chase_across_groups(
            _effect_def(), _LAYER, _groups(), _SECTION, hierarchy_a, ["#FFFFFF"],
        )
        result_b = _place_chase_across_groups(
            _effect_def(), _LAYER, _groups(), _SECTION, hierarchy_b, ["#FFFFFF"],
        )
        assert _group_index_sequence(result_a) == _group_index_sequence(result_b)
