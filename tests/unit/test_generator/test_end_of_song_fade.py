"""Tests for the end-of-song fade over trailing silence (01_BASE_All_FADES)."""
from __future__ import annotations

from src.analyzer.result import HierarchyResult
from src.effects.library import EffectLibrary
from src.effects.models import EffectDefinition
from src.generator.models import SectionAssignment, SectionEnergy
from src.generator.plan import _place_end_of_song_fade
from src.grouper.grouper import PowerGroup, _tier1_canvas
from src.grouper.layout import Prop
from src.themes.models import Theme


def _make_effect(name: str) -> EffectDefinition:
    return EffectDefinition(
        name=name,
        xlights_id=f"E_{name.upper().replace(' ', '')}",
        category="test",
        description="test effect",
        intent="fill",
        parameters=[],
        prop_suitability={"matrix": "ideal", "outline": "good"},
        analysis_mappings=[],
        layer_role="standalone",
        duration_type="section",
    )


def _make_library(*names: str) -> EffectLibrary:
    effects = tuple(_make_effect(n) for n in names)
    return EffectLibrary(
        schema_version="1.0.0",
        target_xlights_version="2024.15",
        effects={e.name: e for e in effects},
    )


def _make_hierarchy(duration_ms: int) -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.0.0", source_file="test.mp3", source_hash="abc123",
        duration_ms=duration_ms, estimated_bpm=120.0,
    )


def _make_assignment(start_ms: int, end_ms: int) -> SectionAssignment:
    section = SectionEnergy(
        label="outro", start_ms=start_ms, end_ms=end_ms,
        energy_score=30, mood_tier="structural", impact_count=0,
    )
    theme = Theme(
        name="Test Theme", mood="structural", occasion="general", genre="any",
        intent="test", layers=[], palette=["#ff0000"],
    )
    return SectionAssignment(section=section, theme=theme)


_GROUPS = [
    PowerGroup(name="01_BASE_All", tier=1, members=["A", "B"]),
    PowerGroup(name="01_BASE_All_FADES", tier=1, members=["A", "B"]),
]


class TestTier1CanvasGroups:
    def test_returns_base_and_fades_with_same_members(self) -> None:
        props = [
            Prop(name="A", display_as="Arches", world_x=0, world_y=0, world_z=0,
                 scale_x=1, scale_y=1, parm1=1, parm2=50, sub_models=[]),
            Prop(name="B", display_as="Arches", world_x=1, world_y=1, world_z=0,
                 scale_x=1, scale_y=1, parm1=1, parm2=50, sub_models=[]),
        ]
        groups = _tier1_canvas(props)
        assert [g.name for g in groups] == ["01_BASE_All", "01_BASE_All_FADES"]
        assert groups[0].members == groups[1].members == ["A", "B"]
        assert all(g.tier == 1 for g in groups)


class TestFadesGroupExcludedFromThemePlacement:
    def test_place_effects_skips_fades_group(self) -> None:
        from tests.unit.test_generator.test_corpus_recipes import (
            _make_assignment as make_recipe_assignment,
            _make_hierarchy as make_beat_hierarchy,
            _make_library,
            _make_variant_library,
            _BEATS,
        )
        from src.generator.effect_placer import place_effects
        from src.themes.models import EffectLayer

        library = _make_library("Color Wash")
        variant_library = _make_variant_library("Color Wash")
        section = SectionEnergy(
            label="chorus", start_ms=0, end_ms=8000,
            energy_score=80, mood_tier="structural", impact_count=0,
        )
        assignment = make_recipe_assignment(
            section, [EffectLayer(variant="Color Wash")],
            active_tiers=frozenset({1}),
        )
        result = place_effects(
            assignment, _GROUPS, library,
            make_beat_hierarchy(_BEATS), variant_library=variant_library,
        )
        assert result.get("01_BASE_All")
        assert "01_BASE_All_FADES" not in result


class TestPlaceEndOfSongFade:
    def test_trailing_silence_gets_min_blend_fade(self) -> None:
        assignments = [_make_assignment(0, 8000), _make_assignment(8000, 20000)]
        library = _make_library("On")
        _place_end_of_song_fade(assignments, _GROUPS, library, _make_hierarchy(30000))
        fades = assignments[-1].group_effects.get("01_BASE_All_FADES", [])
        assert len(fades) == 1
        fade = fades[0]
        assert fade.effect_name == "On"
        assert fade.start_ms == 20000
        assert fade.end_ms == 30000
        assert fade.color_palette == ["#FFFFFF"]
        assert fade.parameters["E_TEXTCTRL_Eff_On_End"] == "0"
        assert fade.parameters["T_CHOICE_LayerMethod"] == "Min"
        assert fade.parameters["T_SLIDER_EffectLayerMix"] == "0"

    def test_no_trailing_silence_still_fades_last_two_seconds(self) -> None:
        # The fade always fires: with no silent tail it overlaps the final
        # stretch of audio, spanning at least the last 2 seconds.
        assignments = [_make_assignment(0, 29500)]
        library = _make_library("On")
        _place_end_of_song_fade(assignments, _GROUPS, library, _make_hierarchy(30000))
        fades = assignments[-1].group_effects["01_BASE_All_FADES"]
        assert len(fades) == 1
        assert fades[0].start_ms == 28000
        assert fades[0].end_ms == 30000

    def test_missing_fades_group_is_noop(self) -> None:
        assignments = [_make_assignment(0, 20000)]
        library = _make_library("On")
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["A"])]
        _place_end_of_song_fade(assignments, groups, library, _make_hierarchy(30000))
        assert "01_BASE_All_FADES" not in assignments[-1].group_effects

    def test_no_assignments_is_noop(self) -> None:
        library = _make_library("On")
        _place_end_of_song_fade([], _GROUPS, library, _make_hierarchy(30000))

    def test_on_missing_from_library_is_noop(self) -> None:
        assignments = [_make_assignment(0, 20000)]
        library = _make_library("Color Wash")
        _place_end_of_song_fade(assignments, _GROUPS, library, _make_hierarchy(30000))
        assert "01_BASE_All_FADES" not in assignments[-1].group_effects

    def test_song_end_uses_max_section_end(self) -> None:
        # Sections out of order — the fade must start at the latest end_ms.
        assignments = [_make_assignment(10000, 25000), _make_assignment(0, 10000)]
        library = _make_library("On")
        _place_end_of_song_fade(assignments, _GROUPS, library, _make_hierarchy(30000))
        fades = assignments[-1].group_effects["01_BASE_All_FADES"]
        assert fades[0].start_ms == 25000

    def test_energy_curve_overrides_section_tiling(self) -> None:
        # The section builder tiles the full duration (the last section's
        # end_ms covers trailing silence), so the audible end must come from
        # the full-mix energy curve: audio dies at 20s of a 30s file even
        # though the section runs to 29.9s.
        from src.analyzer.result import ValueCurve

        assignments = [_make_assignment(0, 29900)]
        hierarchy = _make_hierarchy(30000)
        # 10 fps, 300 frames: energy 50 for 200 frames (0-20s), then 0.
        hierarchy.energy_curves["full_mix"] = ValueCurve(
            name="full_mix", stem_source="full_mix", fps=10,
            values=[50] * 200 + [0] * 100,
        )
        library = _make_library("On")
        _place_end_of_song_fade(assignments, _GROUPS, library, hierarchy)
        fades = assignments[-1].group_effects["01_BASE_All_FADES"]
        assert len(fades) == 1
        assert fades[0].start_ms == 20000
        assert fades[0].end_ms == 30000

    def test_energy_curve_with_no_trailing_silence_fades_minimum_window(self) -> None:
        from src.analyzer.result import ValueCurve

        assignments = [_make_assignment(0, 29900)]
        hierarchy = _make_hierarchy(30000)
        hierarchy.energy_curves["full_mix"] = ValueCurve(
            name="full_mix", stem_source="full_mix", fps=10, values=[50] * 300,
        )
        library = _make_library("On")
        _place_end_of_song_fade(assignments, _GROUPS, library, hierarchy)
        fades = assignments[-1].group_effects["01_BASE_All_FADES"]
        assert len(fades) == 1
        assert fades[0].start_ms == 28000
        assert fades[0].end_ms == 30000
