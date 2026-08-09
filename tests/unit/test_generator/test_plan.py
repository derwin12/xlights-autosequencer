"""Tests for plan builder — integration-level tests with mock data."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.library import load_effect_library
from src.generator.models import GenerationConfig, SequencePlan
from src.generator.plan import _manual_picture_matches, build_plan, read_song_metadata
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


class TestManualPictureMatches:
    """_manual_picture_matches: config.image_manual_occurrences -> synthetic word_image_matches entries."""

    def test_empty_input_returns_empty(self):
        assert _manual_picture_matches([]) == []

    def test_resolves_image_id_to_stored_path(self, tmp_path, monkeypatch):
        from src.generator.image_catalog import save_image_to_library

        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
        entry = save_image_to_library(tag="manual", filename="a.png", data=b"bytes", uploaded_at="t1")

        matches = _manual_picture_matches([{"start_ms": 46675, "image_id": entry["id"]}])
        assert len(matches) == 1
        assert matches[0]["start_ms"] == 46675
        assert matches[0]["end_ms"] == 46675
        assert matches[0]["stored_path"] == entry["stored_path"]
        assert matches[0]["word"] == ""

    def test_unknown_image_id_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
        assert _manual_picture_matches([{"start_ms": 1000, "image_id": "nope"}]) == []

    def test_missing_start_ms_is_skipped(self, tmp_path, monkeypatch):
        from src.generator.image_catalog import save_image_to_library

        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
        entry = save_image_to_library(tag="manual", filename="a.png", data=b"bytes", uploaded_at="t1")
        assert _manual_picture_matches([{"image_id": entry["id"]}]) == []

    def test_multiple_entries_all_resolved(self, tmp_path, monkeypatch):
        from src.generator.image_catalog import save_image_to_library

        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
        first = save_image_to_library(tag="manual", filename="a.png", data=b"1", uploaded_at="t1")
        second = save_image_to_library(tag="manual", filename="b.png", data=b"2", uploaded_at="t2")

        matches = _manual_picture_matches([
            {"start_ms": 1000, "image_id": first["id"]},
            {"start_ms": 2000, "image_id": second["id"]},
        ])
        assert {m["start_ms"] for m in matches} == {1000, 2000}


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
        # plan_validator.validate_plan() output (see
        # openspec/changes/plan-variety-validator) -- this short fixture
        # doesn't have enough qualifying occurrences to trip the monotony
        # check, but the attribute must exist and be a list.
        assert isinstance(plan.warnings, list)

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

    def test_title_artist_override_wins_over_id3_and_filename(self, tmp_path: Path):
        """A caller-supplied title/artist (e.g. the review library's
        corrected metadata) must win over read_song_metadata()'s raw
        ID3/filename-stem fallback in the resulting SongProfile."""
        hierarchy = _make_hierarchy()
        props = _make_props()
        groups = _make_groups()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        config = GenerationConfig(
            audio_path=tmp_path / "some-raw-filename-slug.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
            title_override="With a Little Help From My Friends",
            artist_override="Wet Wet Wet",
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        assert plan.song_profile.title == "With a Little Help From My Friends"
        assert plan.song_profile.artist == "Wet Wet Wet"

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


class TestThemeOverrides:
    """Regression coverage for the theme_overrides slug/name mismatch
    (2026-07-18): src/review's session assignments and story overrides
    pass slug-format theme_id values (e.g. "stellar-wind"), while the CLI
    and tests/integration/test_phase1_metrics.py pass display names (e.g.
    "Stellar Wind"). build_plan must resolve both — the slug lookup
    previously fell through silently, so no theme choice made through the
    Theme screen ever actually applied (confirmed on a real export: none
    of a song's 4 confirmed theme assignments' colors appeared in the
    output; auto-selected themes rendered instead). NOT inside
    TestBuildPlan: that class is xfail'd for an unrelated reason, which
    would hide a real regression here.
    """

    def test_slug_theme_override_resolves(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        props = _make_props()
        groups = _make_groups()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
        assert theme_lib.themes.get("Stellar Wind") is not None, (
            "fixture assumption: builtin theme 'Stellar Wind' must exist"
        )

        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
            theme_overrides={0: "stellar-wind"},
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        assert plan.sections[0].theme.name == "Stellar Wind"

    def test_slug_override_resolves_after_theme_rename(self, tmp_path: Path):
        # bug found 2026-08-03: a custom theme created as "test2" (theme_id
        # = filename stem "test2") later renamed to "Aerosmith DreamOn" via
        # the Edit dialog. The override index used to be built by
        # re-slugifying each theme's CURRENT .name ("aerosmith-dreamon"),
        # so an assignment still holding the original theme_id "test2"
        # silently found nothing and fell through to auto-selection. The
        # index must be built from each Theme's own stable .theme_id
        # (set by load_theme_library from the file, unaffected by rename)
        # instead.
        import json as _json

        custom_dir = tmp_path / "custom_themes"
        custom_dir.mkdir()
        (custom_dir / "test2.json").write_text(_json.dumps({
            "name": "Aerosmith DreamOn", "mood": "structural", "occasion": "general",
            "genre": "rock", "intent": "From the AI pull",
            "palette": ["#0D1B2A", "#1B263B", "#22333B", "#415A77"],
            "layers": [{"variant": "Color Wash Smooth", "blend_mode": "Normal"}],
        }))

        hierarchy = _make_hierarchy()
        props = _make_props()
        groups = _make_groups()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(
            effect_library=effect_lib, variant_library=variant_lib, custom_dir=custom_dir,
        )
        assert theme_lib.get("Aerosmith DreamOn").theme_id == "test2"

        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
            theme_overrides={0: "test2"},
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        assert plan.sections[0].theme.name == "Aerosmith DreamOn"

    def test_display_name_theme_override_still_resolves(self, tmp_path: Path):
        # The CLI and test_phase1_metrics.py pass display names directly —
        # must keep working alongside the new slug path.
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
            theme_overrides={0: "Stellar Wind"},
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        assert plan.sections[0].theme.name == "Stellar Wind"


class TestSectionOverrides:
    """Coverage for the Theme screen's per-section parameter sliders
    (brightness/hit_strength/dwell_time/color_shift), wired via
    GenerationConfig.section_overrides -> SectionAssignment fields.
    Regression target: these sliders previously saved to the review
    session but were never read by the generator at all (verified via
    grep — no caller of assignment["overrides"] outside assignments.py).
    """

    def test_section_overrides_apply_to_matching_section(self, tmp_path: Path):
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
            section_overrides={
                0: {"brightness": 1.5, "hit_strength": 1.2, "dwell_time": 1.8, "color_shift": 0.3},
            },
        )

        plan = build_plan(config, hierarchy, props, groups, effect_lib, theme_lib)

        assert plan.sections[0].brightness == 1.5
        assert plan.sections[0].hit_strength == 1.2
        assert plan.sections[0].dwell_time == 1.8
        assert plan.sections[0].color_shift == 0.3
        # Untouched sections keep the defaults matching
        # src/review/api/v1/assignments.py's _DEFAULT_OVERRIDES.
        assert plan.sections[1].brightness == 1.0
        assert plan.sections[1].hit_strength == 0.5
        assert plan.sections[1].dwell_time == 1.0
        assert plan.sections[1].color_shift == 0.0

    def test_dwell_time_scales_duration_target(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        props = _make_props()
        groups = _make_groups()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

        baseline_config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
        )
        baseline_plan = build_plan(baseline_config, hierarchy, props, groups, effect_lib, theme_lib)
        baseline_target = baseline_plan.sections[0].duration_target
        assert baseline_target is not None

        scaled_config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
            section_overrides={0: {"dwell_time": 2.0}},
        )
        scaled_plan = build_plan(scaled_config, hierarchy, props, groups, effect_lib, theme_lib)
        scaled_target = scaled_plan.sections[0].duration_target
        assert scaled_target is not None

        assert scaled_target.target_ms == round(baseline_target.target_ms * 2.0)
        assert scaled_target.min_ms == round(baseline_target.min_ms * 2.0)
        assert scaled_target.max_ms == round(baseline_target.max_ms * 2.0)


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
