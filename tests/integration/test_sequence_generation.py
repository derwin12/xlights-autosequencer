"""Integration tests for end-to-end sequence generation."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.library import load_effect_library
from src.generator.models import GenerationConfig, SequencePlan
from src.generator.plan import build_plan
from src.generator.xsq_writer import write_xsq
from src.grouper.grouper import PowerGroup
from src.grouper.layout import Prop
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_hierarchy(
    duration_ms: int = 20000,
    num_sections: int = 4,
    with_beats: bool = True,
    with_sections: bool = True,
    with_energy: bool = True,
) -> HierarchyResult:
    """Build a realistic mock HierarchyResult."""
    beats = None
    if with_beats:
        beats = TimingTrack(
            name="beats", algorithm_name="librosa_beats", element_type="beat",
            marks=[
                TimingMark(time_ms=i * 500, confidence=1.0, label=str((i % 4) + 1))
                for i in range(duration_ms // 500)
            ],
            quality_score=0.85,
        )

    bars = None
    if with_beats:
        bars = TimingTrack(
            name="bars", algorithm_name="librosa_beats", element_type="bar",
            marks=[TimingMark(time_ms=i * 2000, confidence=1.0) for i in range(duration_ms // 2000)],
            quality_score=0.8,
        )

    sections = []
    if with_sections and num_sections > 0:
        labels = ["intro", "verse", "chorus", "outro"]
        section_dur = duration_ms // num_sections
        for i in range(num_sections):
            sections.append(TimingMark(
                time_ms=i * section_dur, confidence=1.0,
                label=labels[i % len(labels)], duration_ms=section_dur,
            ))

    energy_curves = {}
    energy_impacts = []
    if with_energy:
        fps = 4
        num_frames = duration_ms * fps // 1000
        values = [int(20 + 60 * (i / max(num_frames - 1, 1))) for i in range(num_frames)]
        energy_curves["full_mix"] = ValueCurve(
            name="full_mix", stem_source="full_mix", fps=fps, values=values,
        )
        energy_impacts = [TimingMark(time_ms=duration_ms // 2, confidence=1.0)]

    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        sections=sections,
        beats=beats,
        bars=bars,
        energy_curves=energy_curves,
        energy_impacts=energy_impacts,
    )


def _make_props() -> list[Prop]:
    return [
        Prop(name="ArchLeft", display_as="Arch",
             world_x=50, world_y=40, world_z=0,
             scale_x=2, scale_y=1, parm1=1, parm2=50,
             sub_models=[], pixel_count=50,
             norm_x=0.1, norm_y=0.1, aspect_ratio=2.0),
        Prop(name="MatrixCenter", display_as="Matrix",
             world_x=300, world_y=350, world_z=0,
             scale_x=3, scale_y=2, parm1=20, parm2=30,
             sub_models=[], pixel_count=600,
             norm_x=0.5, norm_y=0.9, aspect_ratio=1.5),
        Prop(name="TreeRight", display_as="Poly Line",
             world_x=500, world_y=200, world_z=0,
             scale_x=1, scale_y=2, parm1=10, parm2=100,
             sub_models=[], pixel_count=1000,
             norm_x=0.8, norm_y=0.5, aspect_ratio=0.5),
    ]


def _make_groups() -> list[PowerGroup]:
    return [
        PowerGroup(name="01_BASE_All", tier=1, members=["ArchLeft", "MatrixCenter", "TreeRight"]),
        PowerGroup(name="02_GEO_Left", tier=2, members=["ArchLeft"]),
        PowerGroup(name="08_HERO_Tree", tier=8, members=["TreeRight"]),
    ]


def _generate(tmp_path: Path, hierarchy: HierarchyResult,
              props: list[Prop] | None = None,
              groups: list[PowerGroup] | None = None) -> tuple[SequencePlan, Path]:
    """Run build_plan + write_xsq and return (plan, xsq_path)."""
    if props is None:
        props = _make_props()
    if groups is None:
        groups = _make_groups()

    effect_lib = load_effect_library()
    variant_lib = load_variant_library(effect_library=effect_lib)
    theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
    config = GenerationConfig(
        audio_path=tmp_path / "test.mp3",
        layout_path=tmp_path / "layout.xml",
        genre="pop", occasion="general",
    )

    plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)
    output = tmp_path / "test.xsq"
    write_xsq(plan, output)
    return plan, output


# ── T030: Full pipeline integration ──────────────────────────────────────────


class TestFullPipeline:
    """End-to-end: mock hierarchy + layout -> .xsq -> validate."""

    def test_produces_valid_xsq(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        _, xsq_path = _generate(tmp_path, hierarchy)

        tree = ET.parse(xsq_path)
        root = tree.getroot()
        assert root.tag == "xsequence"
        assert root.get("FixedPointTiming") == "25"

    def test_effects_placed_on_models(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        _, xsq_path = _generate(tmp_path, hierarchy)

        tree = ET.parse(xsq_path)
        root = tree.getroot()
        effects_el = root.find("ElementEffects")
        assert effects_el is not None

        model_names_with_effects = {el.get("name") for el in effects_el}
        assert len(model_names_with_effects) > 0

    def test_timing_alignment_sc003(self, tmp_path: Path):
        """SC-003: at least 80% of effects align to beat/onset/section marks."""
        hierarchy = _make_hierarchy()
        plan, _ = _generate(tmp_path, hierarchy)

        beat_times = set()
        if hierarchy.beats:
            beat_times = {m.time_ms for m in hierarchy.beats.marks}
        section_times = {m.time_ms for m in hierarchy.sections}
        all_timing_marks = beat_times | section_times

        total_effects = 0
        aligned_effects = 0
        for assignment in plan.sections:
            for placements in assignment.group_effects.values():
                for p in placements:
                    total_effects += 1
                    if p.start_ms in all_timing_marks or p.start_ms == assignment.section.start_ms:
                        aligned_effects += 1

        if total_effects > 0:
            ratio = aligned_effects / total_effects
            assert ratio >= 0.8, (
                f"SC-003: Expected >=80% timing alignment, got {ratio:.0%} "
                f"({aligned_effects}/{total_effects})"
            )

    def test_section_theme_variety_sc004(self, tmp_path: Path):
        """SC-004: adjacent sections use different themes >=80% of the time."""
        hierarchy = _make_hierarchy(num_sections=5)
        plan, _ = _generate(tmp_path, hierarchy)

        if len(plan.sections) <= 1:
            pytest.skip("Not enough sections to test variety")

        different = sum(
            1 for i in range(len(plan.sections) - 1)
            if plan.sections[i].theme.name != plan.sections[i + 1].theme.name
        )
        total_pairs = len(plan.sections) - 1
        ratio = different / total_pairs
        assert ratio >= 0.8, (
            f"SC-004: Expected >=80% variety, got {ratio:.0%} ({different}/{total_pairs})"
        )


# ── T031: Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:

    def test_no_power_groups_flat_fallback(self, tmp_path: Path):
        """Generator works with no power groups (flat model fallback)."""
        hierarchy = _make_hierarchy()
        plan, xsq_path = _generate(tmp_path, hierarchy, groups=[])

        tree = ET.parse(xsq_path)
        root = tree.getroot()
        assert root.tag == "xsequence"

    def test_no_detected_sections(self, tmp_path: Path):
        """Generator handles songs with no section structure."""
        hierarchy = _make_hierarchy(with_sections=False)
        # With no sections, the plan should still work (empty or single-section fallback)
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop", occasion="general",
        )
        plan = build_plan(config, hierarchy, _make_props(), _make_groups(), effect_lib, theme_lib)
        # Should not crash
        assert isinstance(plan, SequencePlan)

    def test_no_timing_tracks(self, tmp_path: Path):
        """Generator handles songs with no beat/bar tracks."""
        hierarchy = _make_hierarchy(with_beats=False)
        plan, xsq_path = _generate(tmp_path, hierarchy)

        tree = ET.parse(xsq_path)
        root = tree.getroot()
        assert root.tag == "xsequence"

    def test_short_song(self, tmp_path: Path):
        """Generator handles very short songs (<30s)."""
        hierarchy = _make_hierarchy(duration_ms=15000, num_sections=2)
        plan, xsq_path = _generate(tmp_path, hierarchy)

        assert len(plan.sections) <= 2
        tree = ET.parse(xsq_path)
        assert tree.getroot().tag == "xsequence"
