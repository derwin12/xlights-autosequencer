"""Tests for plan builder — integration-level tests with mock data."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.library import load_effect_library
from src.generator.models import GenerationConfig, SequencePlan
from src.generator.plan import build_plan, read_song_metadata
from src.generator.xsq_writer import write_xsq
from src.grouper.grouper import PowerGroup
from src.grouper.layout import Prop
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library


def _make_hierarchy() -> HierarchyResult:
    """Build a realistic mock HierarchyResult."""
    beats = TimingTrack(
        name="beats",
        algorithm_name="librosa_beats",
        element_type="beat",
        marks=[
            TimingMark(time_ms=i * 500, confidence=1.0, label=str((i % 4) + 1))
            for i in range(40)
        ],
        quality_score=0.85,
    )
    bars = TimingTrack(
        name="bars",
        algorithm_name="librosa_beats",
        element_type="bar",
        marks=[TimingMark(time_ms=i * 2000, confidence=1.0) for i in range(10)],
        quality_score=0.8,
    )
    sections = [
        TimingMark(time_ms=0, confidence=1.0, label="intro", duration_ms=4000),
        TimingMark(time_ms=4000, confidence=1.0, label="verse", duration_ms=6000),
        TimingMark(time_ms=10000, confidence=1.0, label="chorus", duration_ms=6000),
        TimingMark(time_ms=16000, confidence=1.0, label="outro", duration_ms=4000),
    ]
    energy_values = (
        [20] * 16 +  # intro: low
        [45] * 24 +  # verse: medium
        [80] * 24 +  # chorus: high
        [25] * 16    # outro: low
    )
    energy_curve = ValueCurve(
        name="full_mix", stem_source="full_mix", fps=4, values=energy_values
    )
    impacts = [
        TimingMark(time_ms=10500, confidence=1.0),
        TimingMark(time_ms=13000, confidence=1.0),
    ]

    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=20000,
        estimated_bpm=120.0,
        sections=sections,
        beats=beats,
        bars=bars,
        energy_curves={"full_mix": energy_curve},
        energy_impacts=impacts,
    )


def _make_props() -> list[Prop]:
    return [
        Prop(
            name="ArchLeft", display_as="Arch",
            world_x=50, world_y=40, world_z=0,
            scale_x=2, scale_y=1, parm1=1, parm2=50,
            sub_models=[], pixel_count=50,
            norm_x=0.1, norm_y=0.1, aspect_ratio=2.0,
        ),
        Prop(
            name="MatrixCenter", display_as="Matrix",
            world_x=300, world_y=350, world_z=0,
            scale_x=3, scale_y=2, parm1=20, parm2=30,
            sub_models=[], pixel_count=600,
            norm_x=0.5, norm_y=0.9, aspect_ratio=1.5,
        ),
    ]


def _make_groups() -> list[PowerGroup]:
    return [
        PowerGroup(name="01_BASE_All", tier=1, members=["ArchLeft", "MatrixCenter"]),
        PowerGroup(name="08_HERO_Matrix", tier=8, members=["MatrixCenter"]),
    ]


@pytest.mark.xfail(reason="US2: builtin_themes.json still uses old EffectLayer format; passes after US2 migration", strict=False)
class TestBuildPlan:
    """Integration tests for build_plan with real effect/theme libraries."""

    def test_plan_has_all_sections_assigned(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        props = _make_props()
        groups = _make_groups()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        assert len(plan.sections) == 4
        for assignment in plan.sections:
            assert assignment.theme is not None
            assert assignment.section.label in ("intro", "verse", "chorus", "outro")

    def test_plan_has_group_placements(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        props = _make_props()
        groups = _make_groups()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        # At least some sections should have effect placements
        has_placements = any(
            len(a.group_effects) > 0 for a in plan.sections
        )
        assert has_placements, "At least one section should have effect placements"

    def test_xsq_output_is_valid_xml(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        props = _make_props()
        groups = _make_groups()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)
        output = tmp_path / "test.xsq"
        write_xsq(plan, output)

        # Should produce valid XML
        tree = ET.parse(output)
        root = tree.getroot()
        assert root.tag == "xsequence"
        assert root.get("FixedPointTiming") == "25"

        # Should have effects in ElementEffects
        element_effects = root.find("ElementEffects")
        assert element_effects is not None
        elements = list(element_effects)
        assert len(elements) > 0, "ElementEffects should have at least one model element"


class TestReadSongMetadata:
    """Tests for read_song_metadata."""

    def test_returns_profile_from_filename(self, tmp_path: Path):
        audio = tmp_path / "My Song.mp3"
        audio.touch()

        profile = read_song_metadata(audio)

        assert profile.title == "My Song"
        assert profile.genre == "pop"  # default

    def test_uses_hierarchy_duration_and_bpm(self, tmp_path: Path):
        audio = tmp_path / "test.mp3"
        audio.touch()
        hierarchy = HierarchyResult(
            schema_version="2.0.0",
            source_file="test.mp3",
            source_hash="abc",
            duration_ms=180000,
            estimated_bpm=140.0,
        )

        profile = read_song_metadata(audio, hierarchy)

        assert profile.duration_ms == 180000
        assert profile.estimated_bpm == 140.0
