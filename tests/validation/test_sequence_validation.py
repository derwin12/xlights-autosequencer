"""Tests for the sequence validation framework.

Uses synthetic HierarchyResult and SequencePlan fixtures — no audio files needed.
Tests cover individual scorers, the report generator, and baseline comparison.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.library import load_effect_library
from src.generator.models import (
    EffectPlacement,
    GenerationConfig,
    SectionAssignment,
    SectionEnergy,
    SequencePlan,
    SongProfile,
)
from src.generator.plan import build_plan
from src.grouper.grouper import PowerGroup
from src.grouper.layout import Prop
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library
from src.themes.models import EffectLayer, Theme
from src.validation.baseline import (
    Baseline,
    BaselineEntry,
    compare_against_baseline,
    create_baseline_entry,
    load_baseline,
    save_baseline,
)
from src.validation.report import (
    ValidationReport,
    generate_report,
    load_report,
    save_report,
)
from src.validation.scorers import (
    ScorerResult,
    run_all_scorers,
    score_beat_alignment,
    score_color_usage,
    score_effect_variety,
    score_energy_tracking,
    score_repetition_avoidance,
    score_temporal_coverage,
    score_theme_coherence,
    score_tier_utilization,
    score_transition_quality,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_theme(name: str, mood: str = "structural") -> Theme:
    return Theme(
        name=name,
        mood=mood,
        occasion="general",
        genre="any",
        intent="Test theme",
        layers=[EffectLayer(variant="Color Wash")],
        palette=["#FF0000", "#00FF00", "#0000FF"],
    )


def _make_placement(
    effect: str,
    start_ms: int,
    end_ms: int,
    colors: list[str] | None = None,
    fade_in: int = 0,
    fade_out: int = 0,
) -> EffectPlacement:
    if colors is None:
        colors = ["#FF0000", "#00FF00"]
    return EffectPlacement(
        effect_name=effect,
        xlights_id=effect,
        model_or_group="test",
        start_ms=start_ms,
        end_ms=end_ms,
        color_palette=colors,
        fade_in_ms=fade_in,
        fade_out_ms=fade_out,
    )


def _make_section_assignment(
    label: str,
    start_ms: int,
    end_ms: int,
    energy: int,
    theme: Theme,
    groups: dict[str, list[EffectPlacement]] | None = None,
) -> SectionAssignment:
    mood = "ethereal" if energy <= 33 else ("structural" if energy <= 66 else "aggressive")
    return SectionAssignment(
        section=SectionEnergy(
            label=label,
            start_ms=start_ms,
            end_ms=end_ms,
            energy_score=energy,
            mood_tier=mood,
            impact_count=0,
        ),
        theme=theme,
        group_effects=groups or {},
    )


def _make_hierarchy(
    duration_ms: int = 30000,
    beat_interval_ms: int = 500,
    num_sections: int = 4,
) -> HierarchyResult:
    beats = TimingTrack(
        name="beats",
        algorithm_name="librosa_beats",
        element_type="beat",
        marks=[
            TimingMark(time_ms=i * beat_interval_ms, confidence=1.0)
            for i in range(duration_ms // beat_interval_ms)
        ],
        quality_score=0.85,
    )
    bars = TimingTrack(
        name="bars",
        algorithm_name="librosa_beats",
        element_type="bar",
        marks=[
            TimingMark(time_ms=i * 2000, confidence=1.0)
            for i in range(duration_ms // 2000)
        ],
        quality_score=0.8,
    )
    section_dur = duration_ms // max(1, num_sections)
    labels = ["intro", "verse", "chorus", "outro"]
    sections = [
        TimingMark(
            time_ms=i * section_dur,
            confidence=1.0,
            label=labels[i % len(labels)],
            duration_ms=section_dur,
        )
        for i in range(num_sections)
    ]
    fps = 4
    num_frames = duration_ms * fps // 1000
    values = [int(20 + 60 * (i / max(num_frames - 1, 1))) for i in range(num_frames)]
    energy_curves = {
        "full_mix": ValueCurve(
            name="full_mix", stem_source="full_mix", fps=fps, values=values,
        ),
    }
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
        energy_impacts=[TimingMark(time_ms=duration_ms // 2, confidence=1.0)],
    )


def _make_well_formed_plan(hierarchy: HierarchyResult) -> SequencePlan:
    """Build a plan that should score well across all metrics."""
    profile = SongProfile(
        title="Test Song",
        artist="Test Artist",
        genre="pop",
        occasion="general",
        duration_ms=hierarchy.duration_ms,
        estimated_bpm=120.0,
    )

    beat_times = [m.time_ms for m in hierarchy.beats.marks] if hierarchy.beats else []
    effects = ["Color Wash", "Bars", "Chase", "Meteors", "Wave", "Butterfly"]

    sections = []
    section_configs = [
        ("intro", 0, 7500, 20, "ethereal"),
        ("verse", 7500, 15000, 45, "structural"),
        ("chorus", 15000, 22500, 80, "aggressive"),
        ("outro", 22500, 30000, 25, "ethereal"),
    ]

    for i, (label, start, end, energy, mood) in enumerate(section_configs):
        theme = _make_theme(f"Theme_{mood.title()}", mood=mood)
        # Place effects on beat marks within this section
        group_effects: dict[str, list[EffectPlacement]] = {}
        section_beats = [t for t in beat_times if start <= t < end]

        # Base tier (continuous wash)
        group_effects["01_BASE_All"] = [
            _make_placement("Color Wash", start, end, theme.palette, fade_in=200, fade_out=200),
        ]
        # Mid tier (beat-synced)
        mid_placements = []
        for j, bt in enumerate(section_beats[:-1]):
            next_bt = section_beats[j + 1] if j + 1 < len(section_beats) else end
            effect_name = effects[(i + j) % len(effects)]
            mid_placements.append(
                _make_placement(effect_name, bt, next_bt, theme.palette)
            )
        if mid_placements:
            group_effects["04_BEAT_Chase"] = mid_placements

        # Upper tier only on high energy
        if energy >= 60:
            group_effects["08_HERO_Tree"] = [
                _make_placement("Meteors", start, end, theme.accent_palette or theme.palette),
            ]

        sections.append(SectionAssignment(
            section=SectionEnergy(
                label=label,
                start_ms=start,
                end_ms=end,
                energy_score=energy,
                mood_tier=mood,
                impact_count=1 if energy >= 60 else 0,
            ),
            theme=theme,
            group_effects=group_effects,
        ))

    return SequencePlan(
        song_profile=profile,
        sections=sections,
        layout_groups=[],
        models=["ArchLeft", "MatrixCenter", "TreeRight"],
    )


def _make_poor_plan(hierarchy: HierarchyResult) -> SequencePlan:
    """Build a plan that should score poorly — monotonous, misaligned."""
    profile = SongProfile(
        title="Bad Song",
        artist="Bad Artist",
        genre="pop",
        occasion="general",
        duration_ms=hierarchy.duration_ms,
        estimated_bpm=120.0,
    )

    same_theme = _make_theme("Boring", mood="aggressive")

    sections = []
    for i in range(4):
        start = i * 7500
        end = (i + 1) * 7500
        # Same theme, same effect, no colors, not on beats
        group_effects = {
            "01_BASE_All": [
                _make_placement("Color Wash", start + 137, end - 137, colors=[]),
            ],
        }
        sections.append(SectionAssignment(
            section=SectionEnergy(
                label="verse",
                start_ms=start,
                end_ms=end,
                energy_score=20,  # Low energy but aggressive theme = mismatch
                mood_tier="ethereal",
                impact_count=0,
            ),
            theme=same_theme,
            group_effects=group_effects,
        ))

    return SequencePlan(
        song_profile=profile,
        sections=sections,
        layout_groups=[],
        models=["Prop1"],
    )


# ── Scorer Tests ─────────────────────────────────────────────────────────────


class TestBeatAlignment:
    def test_aligned_effects_score_high(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_beat_alignment(plan, hierarchy)
        assert result.score >= 70.0, f"Expected high alignment, got {result.score}"

    def test_misaligned_effects_score_low(self):
        hierarchy = _make_hierarchy()
        plan = _make_poor_plan(hierarchy)
        result = score_beat_alignment(plan, hierarchy)
        assert result.score < 50.0, f"Expected low alignment, got {result.score}"

    def test_empty_plan_scores_zero(self):
        hierarchy = _make_hierarchy()
        plan = SequencePlan(
            song_profile=SongProfile("E", "", "pop", "general", 30000, 120.0),
            sections=[],
        )
        result = score_beat_alignment(plan, hierarchy)
        assert result.score == 0.0


class TestEnergyTracking:
    def test_well_matched_plan_scores_high(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_energy_tracking(plan, hierarchy)
        # Well-formed plan has ascending energy intro->chorus, descending outro
        assert result.score >= 50.0, f"Expected decent correlation, got {result.score}"

    def test_single_section_returns_neutral(self):
        hierarchy = _make_hierarchy(num_sections=1)
        plan = SequencePlan(
            song_profile=SongProfile("S", "", "pop", "general", 30000, 120.0),
            sections=[_make_section_assignment("verse", 0, 30000, 50, _make_theme("T"))],
        )
        result = score_energy_tracking(plan, hierarchy)
        assert result.score == 50.0


class TestEffectVariety:
    def test_diverse_effects_score_high(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_effect_variety(plan)
        assert result.score >= 50.0, f"Expected good variety, got {result.score}"

    def test_monotonous_effects_score_lower(self):
        hierarchy = _make_hierarchy()
        plan = _make_poor_plan(hierarchy)
        result = score_effect_variety(plan)
        # Poor plan uses only Color Wash everywhere
        assert result.details["unique_effects"] == 1


class TestThemeCoherence:
    def test_matched_moods_score_high(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_theme_coherence(plan)
        assert result.score >= 80.0, f"Expected high coherence, got {result.score}"

    def test_mismatched_moods_score_low(self):
        hierarchy = _make_hierarchy()
        plan = _make_poor_plan(hierarchy)
        result = score_theme_coherence(plan)
        # Aggressive theme on low-energy sections
        assert result.score < 80.0


class TestTemporalCoverage:
    def test_full_coverage_scores_high(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_temporal_coverage(plan, hierarchy)
        assert result.score >= 80.0, f"Expected high coverage, got {result.score}"


class TestTransitionQuality:
    def test_varied_themes_score_better(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result_good = score_transition_quality(plan)

        plan_bad = _make_poor_plan(hierarchy)
        result_bad = score_transition_quality(plan_bad)

        assert result_good.score >= result_bad.score


class TestTierUtilization:
    def test_multi_tier_plan_scores_higher(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_tier_utilization(plan)
        assert result.score >= 40.0, f"Expected decent tier usage, got {result.score}"

    def test_single_tier_plan_scores_lower(self):
        hierarchy = _make_hierarchy()
        plan = _make_poor_plan(hierarchy)
        result = score_tier_utilization(plan)
        # Only uses tier 1
        assert result.score < 80.0


class TestRepetitionAvoidance:
    def test_no_repeats_scores_perfect(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_repetition_avoidance(plan)
        # All sections have different labels
        assert result.score == 100.0

    def test_identical_repeats_score_low(self):
        hierarchy = _make_hierarchy()
        plan = _make_poor_plan(hierarchy)
        result = score_repetition_avoidance(plan)
        # All sections labeled "verse" with same effects
        assert result.score < 50.0


class TestColorUsage:
    def test_colored_effects_score_higher(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        result = score_color_usage(plan)
        assert result.score >= 50.0

    def test_no_colors_score_lower(self):
        hierarchy = _make_hierarchy()
        plan = _make_poor_plan(hierarchy)
        result = score_color_usage(plan)
        assert result.score < 50.0


# ── Report Tests ─────────────────────────────────────────────────────────────


class TestValidationReport:
    def test_generate_report_produces_all_scorers(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        report = generate_report(plan, hierarchy)

        assert report.song_title == "Test Song"
        assert report.num_sections == 4
        assert len(report.scorer_results) == 9
        assert 0 <= report.overall_score <= 100

    def test_report_round_trip_json(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        report = generate_report(plan, hierarchy)

        path = tmp_path / "report.json"
        save_report(report, path)
        loaded = load_report(path)

        assert loaded.song_title == report.song_title
        assert loaded.overall_score == report.overall_score
        assert len(loaded.scorer_results) == len(report.scorer_results)

    def test_summary_table_format(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        report = generate_report(plan, hierarchy)
        table = report.summary_table()

        assert "Test Song" in table
        assert "OVERALL" in table
        assert "beat_alignment" in table

    def test_well_formed_beats_poorly_formed(self):
        """Well-formed plan should outscore poorly-formed plan."""
        hierarchy = _make_hierarchy()
        good = generate_report(_make_well_formed_plan(hierarchy), hierarchy)
        bad = generate_report(_make_poor_plan(hierarchy), hierarchy)

        assert good.overall_score > bad.overall_score, (
            f"Good plan ({good.overall_score}) should outscore bad plan ({bad.overall_score})"
        )


# ── Baseline Tests ───────────────────────────────────────────────────────────


class TestBaseline:
    def test_save_load_round_trip(self, tmp_path: Path):
        baseline = Baseline(
            version="1.0",
            entries=[
                BaselineEntry(
                    scenario_name="pop_song",
                    scores={"beat_alignment": 85.0, "effect_variety": 70.0},
                    overall=77.5,
                ),
            ],
        )
        path = tmp_path / "baseline.json"
        save_baseline(baseline, path)
        loaded = load_baseline(path)

        assert loaded.version == "1.0"
        assert len(loaded.entries) == 1
        assert loaded.entries[0].scenario_name == "pop_song"
        assert loaded.entries[0].scores["beat_alignment"] == 85.0

    def test_no_regression_when_scores_match(self):
        entry = BaselineEntry(
            scenario_name="test",
            scores={"beat_alignment": 80.0, "effect_variety": 70.0},
            overall=75.0,
        )
        report = ValidationReport(
            song_title="Test",
            song_artist="Artist",
            duration_ms=30000,
            num_sections=4,
            total_effects=20,
            scorer_results=[
                ScorerResult(name="beat_alignment", score=82.0),
                ScorerResult(name="effect_variety", score=68.0),
            ],
        )
        result = compare_against_baseline(report, entry, tolerance_pct=5.0)
        assert result.passed is True
        assert len(result.regressions) == 0

    def test_regression_detected_on_large_drop(self):
        entry = BaselineEntry(
            scenario_name="test",
            scores={"beat_alignment": 80.0, "effect_variety": 70.0},
            overall=75.0,
        )
        report = ValidationReport(
            song_title="Test",
            song_artist="Artist",
            duration_ms=30000,
            num_sections=4,
            total_effects=20,
            scorer_results=[
                ScorerResult(name="beat_alignment", score=60.0),  # -20 pts
                ScorerResult(name="effect_variety", score=68.0),
            ],
        )
        result = compare_against_baseline(report, entry, tolerance_pct=5.0)
        assert result.passed is False
        assert len(result.regressions) == 1
        assert "beat_alignment" in result.regressions[0]

    def test_improvement_detected(self):
        entry = BaselineEntry(
            scenario_name="test",
            scores={"beat_alignment": 60.0},
            overall=60.0,
        )
        report = ValidationReport(
            song_title="Test",
            song_artist="Artist",
            duration_ms=30000,
            num_sections=4,
            total_effects=20,
            scorer_results=[
                ScorerResult(name="beat_alignment", score=85.0),
            ],
        )
        result = compare_against_baseline(report, entry, tolerance_pct=5.0)
        assert result.passed is True
        assert len(result.improvements) == 1

    def test_create_baseline_from_report(self):
        hierarchy = _make_hierarchy()
        plan = _make_well_formed_plan(hierarchy)
        report = generate_report(plan, hierarchy)

        entry = create_baseline_entry("pop_song", report)
        assert entry.scenario_name == "pop_song"
        assert len(entry.scores) == 9
        assert entry.overall == report.overall_score


# ── Integration: Full Pipeline ───────────────────────────────────────────────


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
        Prop(
            name="TreeRight", display_as="Poly Line",
            world_x=500, world_y=200, world_z=0,
            scale_x=1, scale_y=2, parm1=10, parm2=100,
            sub_models=[], pixel_count=1000,
            norm_x=0.8, norm_y=0.5, aspect_ratio=0.5,
        ),
    ]


def _make_groups() -> list[PowerGroup]:
    return [
        PowerGroup(name="01_BASE_All", tier=1, members=["ArchLeft", "MatrixCenter", "TreeRight"]),
        PowerGroup(name="02_GEO_Left", tier=2, members=["ArchLeft"]),
        PowerGroup(name="04_BEAT_Chase", tier=4, members=["ArchLeft", "MatrixCenter"]),
        PowerGroup(name="06_PROP_Matrix", tier=6, members=["MatrixCenter"]),
        PowerGroup(name="08_HERO_Tree", tier=8, members=["TreeRight"]),
    ]


class TestFullPipelineValidation:
    """Integration: build_plan -> generate_report -> baseline compare."""

    def test_real_plan_produces_valid_report(self, tmp_path: Path):
        hierarchy = _make_hierarchy()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
        )
        plan = build_plan(config, hierarchy, _make_props(), _make_groups(), effect_lib, theme_lib)
        report = generate_report(plan, hierarchy)

        assert report.overall_score > 0
        assert report.total_effects > 0
        assert all(0 <= r.score <= 100 for r in report.scorer_results)

    def test_baseline_workflow(self, tmp_path: Path):
        """Full workflow: generate -> report -> save baseline -> re-generate -> compare."""
        hierarchy = _make_hierarchy()
        effect_lib = load_effect_library()
        variant_lib = load_variant_library(effect_library=effect_lib)
        theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
        config = GenerationConfig(
            audio_path=tmp_path / "test.mp3",
            layout_path=tmp_path / "layout.xml",
            genre="pop",
            occasion="general",
        )

        # Generate and create baseline
        plan = build_plan(config, hierarchy, _make_props(), _make_groups(), effect_lib, theme_lib)
        report = generate_report(plan, hierarchy)
        entry = create_baseline_entry("pop_standard", report)
        baseline = Baseline(version="1.0", entries=[entry])
        baseline_path = tmp_path / "baseline.json"
        save_baseline(baseline, baseline_path)

        # Re-generate (deterministic, so should match)
        plan2 = build_plan(config, hierarchy, _make_props(), _make_groups(), effect_lib, theme_lib)
        report2 = generate_report(plan2, hierarchy)
        result = compare_against_baseline(report2, entry, tolerance_pct=5.0)

        assert result.passed, f"Regressions: {result.regressions}"
