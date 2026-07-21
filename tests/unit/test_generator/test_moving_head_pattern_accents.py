"""Tests for moving_head.place_moving_head_beat_bursts / _pattern_accents
(short ~1.4s dimmer-burst / Pattern Circle-Square accents on a random subset
of heads, mined from MH Samples.xsq's 2026-07-19 update -- see the module's
"Random accents" section docstring)."""
from __future__ import annotations

from pathlib import Path

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.generator.models import EffectPlacement, SectionAssignment, SectionEnergy
from src.generator.moving_head import (
    _ACCENT_DURATION_MS,
    _MAX_BEAT_BURSTS_PER_SONG,
    _MAX_PATTERN_ACCENTS_PER_SONG,
    _STRONG_ENERGY_GATE,
    place_moving_head_beat_bursts,
    place_moving_head_pattern_accents,
)
from src.grouper.layout import parse_layout
from src.themes.models import EffectLayer, Theme

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "grouper"


def _theme() -> Theme:
    return Theme(
        name="Test", mood="structural", occasion="general", genre="any", intent="test",
        layers=[EffectLayer(variant="Fire")], palette=["#FF0000", "#00FF00"],
    )


def _section(label: str, start_ms: int, end_ms: int, energy: int) -> SectionEnergy:
    return SectionEnergy(
        label=label, start_ms=start_ms, end_ms=end_ms,
        energy_score=energy, mood_tier="structural", impact_count=0,
    )


def _assignment(label: str, start_ms: int, end_ms: int, energy: int, variation_seed: int = 0) -> SectionAssignment:
    return SectionAssignment(
        section=_section(label, start_ms, end_ms, energy),
        theme=_theme(),
        variation_seed=variation_seed,
    )


def _hierarchy(duration_ms: int, beat_interval_ms: int = 500) -> HierarchyResult:
    count = duration_ms // beat_interval_ms
    return HierarchyResult(
        schema_version="2.4.0", source_file="song.mp3", source_hash="abc123",
        duration_ms=duration_ms, estimated_bpm=120.0,
        beats=TimingTrack(
            name="Beats", algorithm_name="test", element_type="beat",
            marks=[TimingMark(time_ms=i * beat_interval_ms, confidence=1.0) for i in range(count)],
            quality_score=1.0,
        ),
    )


class TestPlaceMovingHeadBeatBursts:
    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, _STRONG_ENERGY_GATE)]
        assert place_moving_head_beat_bursts(layout, assignments, _hierarchy(30_000)) == {}

    def test_no_strong_section_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 30_000, 40)]
        assert place_moving_head_beat_bursts(layout, assignments, _hierarchy(30_000)) == {}

    def test_no_beats_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, _STRONG_ENERGY_GATE)]
        hierarchy = HierarchyResult(
            schema_version="2.4.0", source_file="song.mp3", source_hash="abc123",
            duration_ms=30_000, estimated_bpm=120.0, beats=None,
        )
        assert place_moving_head_beat_bursts(layout, assignments, hierarchy) == {}

    def test_burst_fires_near_section_midpoint_on_a_beat(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, _STRONG_ENERGY_GATE, variation_seed=0)]
        result = place_moving_head_beat_bursts(layout, assignments, _hierarchy(30_000))
        assert result
        for placements in result.values():
            burst = placements[-1]  # last placement for a head is its own burst, not the warmup
            assert burst.end_ms - burst.start_ms == _ACCENT_DURATION_MS
            assert burst.start_ms % 500 == 0  # lands exactly on a beat mark

    def test_burst_disables_pattern(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, _STRONG_ENERGY_GATE, variation_seed=0)]
        result = place_moving_head_beat_bursts(layout, assignments, _hierarchy(30_000))
        for placements in result.values():
            burst = placements[-1]
            assert burst.parameters["E_CHECKBOX_MHPatternEnable"] == "0"

    def test_capped_at_max_bursts_per_song(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("chorus", i * 30_000, (i + 1) * 30_000, _STRONG_ENERGY_GATE, variation_seed=0)
            for i in range(_MAX_BEAT_BURSTS_PER_SONG + 5)
        ]
        duration_ms = 30_000 * len(assignments)
        result = place_moving_head_beat_bursts(layout, assignments, _hierarchy(duration_ms))
        # Each qualifying occurrence adds at most 1 burst + 1 warmup per
        # chosen head, so total placements per head never exceed the cap.
        for placements in result.values():
            assert len(placements) <= _MAX_BEAT_BURSTS_PER_SONG * 2

    def test_skips_when_channel_already_occupied(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, _STRONG_ENERGY_GATE, variation_seed=0)]
        # Occupy every head for the whole song already.
        existing = {
            "MH1": [_fake_placement("MH1", 0, 30_000)],
            "MH2": [_fake_placement("MH2", 0, 30_000)],
        }
        result = place_moving_head_beat_bursts(
            layout, assignments, _hierarchy(30_000), existing_placements=existing,
        )
        assert result == {}

    def test_skips_when_group_level_placement_occupies_the_channel(self):
        # Regression: a group-targeted move (e.g. one of place_moving_head_moves'
        # "Fan" moves) writes into every head's channel slots, but only ever
        # appears under the GROUP's own key in existing_placements -- the
        # occupancy check must still catch it even though it never appears
        # under any individual head's key (user-found real .xsq: a 46s
        # group-level Fan move had individual head accents overlapping it
        # for the entire duration, since the old check only looked up
        # per-head keys).
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, _STRONG_ENERGY_GATE, variation_seed=0)]
        existing = {"MH GRP": [_fake_placement("MH GRP", 0, 30_000)]}
        result = place_moving_head_beat_bursts(
            layout, assignments, _hierarchy(30_000), existing_placements=existing,
        )
        assert result == {}

    def test_warmup_respects_group_level_placement_that_just_ended(self):
        # Regression, one level deeper than the skip-check above: an accent
        # whose OWN window doesn't overlap a group-level placement (so it
        # isn't skipped) must still treat that group placement as its true
        # prior occupant for the WARMUP's duration -- otherwise the warmup
        # is computed as if nothing had been there and extends backward
        # into the group placement's still-active tail.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 4_000, 8_000, _STRONG_ENERGY_GATE, variation_seed=0)]
        # Beat marks land on exact 500ms multiples; section midpoint (6000)
        # is itself a mark, so the accent starts at exactly 6000ms.
        group_end_ms = 5_800
        existing = {"MH GRP": [_fake_placement("MH GRP", 0, group_end_ms)]}
        result = place_moving_head_beat_bursts(
            layout, assignments, _hierarchy(30_000), existing_placements=existing,
        )
        assert result, "accent should have fired -- its own window doesn't overlap the group placement"
        for placements in result.values():
            warmup = min(placements, key=lambda p: p.start_ms)
            assert warmup.start_ms == group_end_ms, (
                f"warmup should start exactly at the group placement's end ({group_end_ms}), "
                f"not extend back to {warmup.start_ms}"
            )


class TestPlaceMovingHeadPatternAccents:
    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assignments = [_assignment("verse", 0, 30_000, 40)]
        assert place_moving_head_pattern_accents(layout, assignments, _hierarchy(30_000)) == {}

    def test_only_quiet_sections_qualify(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 30_000, _STRONG_ENERGY_GATE)]
        assert place_moving_head_pattern_accents(layout, assignments, _hierarchy(30_000)) == {}

    def test_pattern_fires_with_circle_or_square(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("verse", 0, 30_000, 40, variation_seed=0)]
        result = place_moving_head_pattern_accents(layout, assignments, _hierarchy(30_000))
        assert result
        for placements in result.values():
            accent = placements[-1]
            assert accent.parameters["E_CHECKBOX_MHPatternEnable"] == "1"
            assert accent.parameters["E_CHOICE_MHPattern"] in ("Circle", "Square")
            assert accent.end_ms - accent.start_ms == _ACCENT_DURATION_MS

    def test_capped_at_max_pattern_accents_per_song(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment("verse", i * 30_000, (i + 1) * 30_000, 40, variation_seed=0)
            for i in range(_MAX_PATTERN_ACCENTS_PER_SONG + 5)
        ]
        duration_ms = 30_000 * len(assignments)
        result = place_moving_head_pattern_accents(layout, assignments, _hierarchy(duration_ms))
        for placements in result.values():
            assert len(placements) <= _MAX_PATTERN_ACCENTS_PER_SONG * 2

    def test_never_picks_three_heads(self):
        # _PATTERN_HEAD_COUNTS excludes 3 by explicit user instruction.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        for seed in range(10):
            assignments = [_assignment("verse", 0, 30_000, 40, variation_seed=seed)]
            result = place_moving_head_pattern_accents(layout, assignments, _hierarchy(30_000))
            assert len(result) != 3


def _fake_placement(name: str, start_ms: int, end_ms: int) -> EffectPlacement:
    return EffectPlacement(
        effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
        model_or_group=name, start_ms=start_ms, end_ms=end_ms, parameters={},
    )
