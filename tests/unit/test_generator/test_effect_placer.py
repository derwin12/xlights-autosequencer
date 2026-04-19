"""Tests for effect placement engine."""
from __future__ import annotations

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.library import EffectLibrary
from src.effects.models import AnalysisMapping, EffectDefinition, EffectParameter
from src.generator.models import (
    FRAME_INTERVAL_MS,
    EffectPlacement,
    SectionAssignment,
    SectionEnergy,
)
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer, Theme
from src.variants.library import VariantLibrary
from src.variants.models import EffectVariant, VariantTags


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_effect(
    name: str = "Color Wash",
    xlights_id: str = "E_COLORWASH",
    duration_type: str = "section",
    layer_role: str = "standalone",
) -> EffectDefinition:
    return EffectDefinition(
        name=name,
        xlights_id=xlights_id,
        category="color_wash",
        description="test effect",
        intent="fill",
        parameters=[],
        prop_suitability={"matrix": "ideal", "outline": "good"},
        analysis_mappings=[],
        layer_role=layer_role,
        duration_type=duration_type,
    )


def _make_library(*effects: EffectDefinition) -> EffectLibrary:
    if not effects:
        effects = (_make_effect(),)
    return EffectLibrary(
        schema_version="1.0.0",
        target_xlights_version="2024.15",
        effects={e.name: e for e in effects},
    )


def _make_variant_library(*effect_names: str) -> VariantLibrary:
    """Create a VariantLibrary mapping each effect name to a variant of the same name."""
    if not effect_names:
        effect_names = ("Color Wash",)
    variants = {}
    for name in effect_names:
        v = EffectVariant(
            name=name,
            base_effect=name,
            description=f"test variant for {name}",
            parameter_overrides={},
            tags=VariantTags(),
        )
        variants[name] = v
    return VariantLibrary(
        schema_version="1.0.0",
        variants=variants,
        builtin_names=set(effect_names),
    )


def _make_theme(
    layers: list[EffectLayer] | None = None,
    palette: list[str] | None = None,
) -> Theme:
    if layers is None:
        layers = [EffectLayer(variant="Color Wash")]
    if palette is None:
        palette = ["#ff0000", "#00ff00"]
    return Theme(
        name="Test Theme",
        mood="structural",
        occasion="general",
        genre="any",
        intent="background wash",
        layers=layers,
        palette=palette,
    )


def _make_section(
    energy_score: int = 50,
    start_ms: int = 0,
    end_ms: int = 10000,
) -> SectionEnergy:
    return SectionEnergy(
        label="verse",
        start_ms=start_ms,
        end_ms=end_ms,
        energy_score=energy_score,
        mood_tier="structural",
        impact_count=0,
    )


def _make_assignment(
    energy_score: int = 50,
    start_ms: int = 0,
    end_ms: int = 10000,
    layers: list[EffectLayer] | None = None,
    active_tiers: frozenset[int] | set[int] | None = None,
) -> SectionAssignment:
    """Build a SectionAssignment.  Defaults to ``active_tiers=frozenset({1})`` —
    matches the pre-048 test behaviour of passing ``tiers={1}`` to place_effects.
    """
    return SectionAssignment(
        section=_make_section(energy_score=energy_score, start_ms=start_ms, end_ms=end_ms),
        theme=_make_theme(layers=layers),
        active_tiers=frozenset(active_tiers) if active_tiers is not None else frozenset({1}),
    )


def _make_hierarchy(
    beat_times: list[int] | None = None,
    duration_ms: int = 10000,
) -> HierarchyResult:
    """Minimal HierarchyResult with optional beat marks."""
    beats_track = None
    if beat_times is not None:
        marks = [TimingMark(time_ms=t, confidence=1.0, label=str((i % 4) + 1))
                 for i, t in enumerate(beat_times)]
        beats_track = TimingTrack(
            name="beats",
            algorithm_name="test",
            element_type="beat",
            marks=marks,
            quality_score=0.9,
        )
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        beats=beats_track,
    )


def _make_groups() -> list[PowerGroup]:
    """Create a minimal set of power groups spanning multiple tiers."""
    return [
        PowerGroup(name="01_BASE_All", tier=1, members=["Model_A", "Model_B", "Model_C"]),
        PowerGroup(name="02_GEO_Left", tier=2, members=["Model_A"]),
        PowerGroup(name="02_GEO_Right", tier=2, members=["Model_B"]),
        PowerGroup(name="03_TYPE_Horizontal", tier=3, members=["Model_A", "Model_B"]),
        PowerGroup(name="04_BEAT_LR_1", tier=4, members=["Model_A"]),
        PowerGroup(name="05_TEX_HiDens", tier=5, members=["Model_C"]),
        PowerGroup(name="06_PROP_CandyCane", tier=6, members=["Model_A", "Model_B"]),
        PowerGroup(name="07_COMP_Window", tier=7, members=["Model_C"]),
        PowerGroup(name="08_HERO_Tree", tier=8, members=["Model_C"]),
    ]


# ── Import under test ────────────────────────────────────────────────────────

from src.generator.effect_placer import place_effects


# ── Tests ─────────────────────────────────────────────────────────────────────


def _used_tiers(result: dict[str, list], groups: list[PowerGroup]) -> set[int]:
    """Collect the set of tiers that actually received placements."""
    tier_of_group = {g.name: g.tier for g in groups}
    return {tier_of_group[name] for name in result if name in tier_of_group}


def _make_ethereal_section(start_ms: int = 0, end_ms: int = 10000) -> SectionEnergy:
    return SectionEnergy(
        label="intro", start_ms=start_ms, end_ms=end_ms,
        energy_score=15, mood_tier="ethereal", impact_count=0,
    )


def _make_aggressive_section(start_ms: int = 0, end_ms: int = 10000) -> SectionEnergy:
    return SectionEnergy(
        label="chorus", start_ms=start_ms, end_ms=end_ms,
        energy_score=85, mood_tier="aggressive", impact_count=0,
    )


class TestTierSelectionByMood:
    """Integration: exactly one partition tier active per section, driven by mood.

    These tests assert which partition tier from {2, 4, 6, 7} receives placements.
    Tier 8 (hero) is always in the active set per _compute_active_tiers, but whether
    it receives placements depends on layer-to-tier mapping (single-layer themes
    don't map any layer to tier 8).  TestComputeActiveTiers covers the full
    active-set semantics directly.
    """

    def _place(self, section: SectionEnergy, hierarchy: HierarchyResult) -> set[int]:
        from src.generator.effect_placer import _compute_active_tiers
        layers = [EffectLayer(variant="Color Wash")]
        assignment = SectionAssignment(
            section=section,
            theme=_make_theme(layers=layers),
            active_tiers=_compute_active_tiers(section, 0, hierarchy),
        )
        groups = _make_groups()
        # Library needs an effect from _PROP_EFFECT_POOL so the tier-6 rotation
        # (which picks from that pool, excluding the layer's own variant) has
        # something to place.
        library = _make_library(
            _make_effect("Color Wash"),
            _make_effect("Ripple", xlights_id="E_RIPPLE"),
        )
        variant_library = _make_variant_library("Color Wash", "Ripple")
        result = place_effects(assignment, groups, library, hierarchy,
                               variant_library=variant_library)
        return _used_tiers(result, groups)

    def test_ethereal_activates_tier_8_only(self) -> None:
        """Ethereal mood → HERO only (tier 8); no exhaustive partition tier so most props stay dark."""
        section = _make_ethereal_section()
        used = self._place(section, _make_hierarchy(beat_times=[0, 500, 1000, 1500]))
        assert 8 in used
        assert 1 not in used and 2 not in used and 4 not in used and 6 not in used and 7 not in used

    def test_structural_without_phrase_structure_uses_tier_6(self) -> None:
        """Structural + weak phrase structure → prop-type variety (tier 6)."""
        section = _make_section()  # default mood_tier="structural", no bars/curves
        used = self._place(section, _make_hierarchy(beat_times=[0, 500, 1000, 1500]))
        assert 6 in used
        assert 1 not in used and 2 not in used and 4 not in used and 7 not in used

    def test_aggressive_uses_tier_4_chase(self) -> None:
        """Aggressive mood → beat chase (tier 4)."""
        section = _make_aggressive_section()
        beat_times = list(range(0, 10000, 500))
        used = self._place(section, _make_hierarchy(beat_times=beat_times))
        assert 4 in used
        assert 1 not in used and 2 not in used and 6 not in used and 7 not in used

    def test_explicit_tiers_override_bypasses_selection(self) -> None:
        """Explicit `tiers=` argument bypasses the mood-based selection."""
        assignment = _make_assignment()  # structural mood
        groups = _make_groups()
        library = _make_library(_make_effect("Color Wash"))
        variant_library = _make_variant_library("Color Wash")
        hierarchy = _make_hierarchy(beat_times=[0, 500, 1000, 1500])

        # Force tier 1 active even though structural mood would normally pick 6
        result = place_effects(assignment, groups, library, hierarchy,
                               variant_library=variant_library)
        used = _used_tiers(result, groups)
        assert used == {1}


class TestDurationTypeSection:
    """Effect with duration_type='section' creates one instance spanning the section."""

    def test_duration_type_section(self) -> None:
        assignment = _make_assignment(start_ms=1000, end_ms=5000)
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        library = _make_library(_make_effect("Color Wash", duration_type="section"))
        variant_library = _make_variant_library("Color Wash")
        hierarchy = _make_hierarchy(beat_times=[1000, 1500, 2000, 2500, 3000])

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        # Should have exactly one placement for the group
        all_placements = [p for ps in result.values() for p in ps]
        section_placements = [p for p in all_placements if p.effect_name == "Color Wash"]
        assert len(section_placements) == 1, (
            f"section duration_type should produce 1 instance, got {len(section_placements)}"
        )
        p = section_placements[0]
        assert p.start_ms <= 1000  # frame-aligned at or before section start
        assert p.end_ms >= 5000    # frame-aligned at or after section end


class TestDurationTypeBeat:
    """Effect with duration_type='beat' creates one instance per beat mark."""

    def test_duration_type_beat(self) -> None:
        beat_times = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500]
        assignment = _make_assignment(start_ms=0, end_ms=5000, energy_score=100,
                                      layers=[EffectLayer(variant="Strobe")])
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        library = _make_library(_make_effect("Strobe", duration_type="beat"))
        variant_library = _make_variant_library("Strobe")
        hierarchy = _make_hierarchy(beat_times=beat_times, duration_ms=5000)

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        all_placements = [p for ps in result.values() for p in ps]
        beat_placements = [p for p in all_placements if p.effect_name == "Strobe"]
        # At max energy, should use ~90% of beats, so at least 8 out of 10
        assert len(beat_placements) >= 8, (
            f"beat duration_type at max energy should produce ~{len(beat_times)} instances, "
            f"got {len(beat_placements)}"
        )


class TestEnergyDrivenDensity:
    """Energy score controls what fraction of timing marks are used."""

    def test_energy_driven_density_high(self) -> None:
        """Energy 80+ should use ~90% of beat marks."""
        beat_times = list(range(0, 10000, 500))  # 20 beats
        assignment = _make_assignment(start_ms=0, end_ms=10000, energy_score=85,
                                      layers=[EffectLayer(variant="Strobe")])
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        library = _make_library(_make_effect("Strobe", duration_type="beat"))
        variant_library = _make_variant_library("Strobe")
        hierarchy = _make_hierarchy(beat_times=beat_times, duration_ms=10000)

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        all_placements = [p for ps in result.values() for p in ps]
        beat_placements = [p for p in all_placements if p.effect_name == "Strobe"]
        ratio = len(beat_placements) / len(beat_times)
        assert ratio >= 0.8, f"High energy should use >=80% of marks, got {ratio:.0%}"

    def test_energy_driven_density_low(self) -> None:
        """Energy 20 should use ~50% of beat marks."""
        beat_times = list(range(0, 10000, 500))  # 20 beats
        assignment = _make_assignment(start_ms=0, end_ms=10000, energy_score=20,
                                      layers=[EffectLayer(variant="Strobe")])
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        library = _make_library(_make_effect("Strobe", duration_type="beat"))
        variant_library = _make_variant_library("Strobe")
        hierarchy = _make_hierarchy(beat_times=beat_times, duration_ms=10000)

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        all_placements = [p for ps in result.values() for p in ps]
        beat_placements = [p for p in all_placements if p.effect_name == "Strobe"]
        ratio = len(beat_placements) / len(beat_times)
        assert 0.3 <= ratio <= 0.7, f"Low energy should use ~50% of marks, got {ratio:.0%}"


class TestFadeCalculation:
    """Fade values depend on duration_type: section/bar get 200-500ms, beat/trigger get 0."""

    def test_fade_calculation_section(self) -> None:
        assignment = _make_assignment(start_ms=0, end_ms=10000)
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        library = _make_library(_make_effect("Color Wash", duration_type="section"))
        variant_library = _make_variant_library("Color Wash")
        hierarchy = _make_hierarchy()

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        all_placements = [p for ps in result.values() for p in ps]
        assert len(all_placements) > 0, "Should produce at least one placement"
        for p in all_placements:
            assert p.fade_in_ms == 0, (
                f"Section effect fade_in should be 0 (xLights handles transitions), got {p.fade_in_ms}"
            )
            assert p.fade_out_ms == 0, (
                f"Section effect fade_out should be 0 (xLights handles transitions), got {p.fade_out_ms}"
            )

    def test_fade_calculation_beat(self) -> None:
        beat_times = [0, 500, 1000, 1500]
        assignment = _make_assignment(start_ms=0, end_ms=2000, energy_score=100,
                                      layers=[EffectLayer(variant="Strobe")])
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        library = _make_library(_make_effect("Strobe", duration_type="beat"))
        variant_library = _make_variant_library("Strobe")
        hierarchy = _make_hierarchy(beat_times=beat_times, duration_ms=2000)

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        all_placements = [p for ps in result.values() for p in ps]
        assert len(all_placements) > 0, "Should produce at least one placement"
        for p in all_placements:
            assert p.fade_in_ms == 0, f"Beat effect fade_in should be 0, got {p.fade_in_ms}"
            assert p.fade_out_ms == 0, f"Beat effect fade_out should be 0, got {p.fade_out_ms}"


class TestFrameAlignment:
    """All start_ms and end_ms must be multiples of 25 (xLights frame interval)."""

    def test_frame_alignment(self) -> None:
        # Use beat times that are NOT multiples of 25 to verify alignment
        beat_times = [0, 503, 1007, 1511, 2013]
        assignment = _make_assignment(start_ms=0, end_ms=2500, energy_score=100,
                                      layers=[EffectLayer(variant="Strobe")])
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        library = _make_library(_make_effect("Strobe", duration_type="beat"))
        variant_library = _make_variant_library("Strobe")
        hierarchy = _make_hierarchy(beat_times=beat_times, duration_ms=2500)

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        all_placements = [p for ps in result.values() for p in ps]
        assert len(all_placements) > 0, "Should produce at least one placement"
        for p in all_placements:
            assert p.start_ms % FRAME_INTERVAL_MS == 0, (
                f"start_ms {p.start_ms} is not a multiple of {FRAME_INTERVAL_MS}"
            )
            assert p.end_ms % FRAME_INTERVAL_MS == 0, (
                f"end_ms {p.end_ms} is not a multiple of {FRAME_INTERVAL_MS}"
            )


class TestFlatModelFallback:
    """When groups list is empty, place_effects falls back to using models directly."""

    def test_flat_model_fallback(self) -> None:
        assignment = _make_assignment(start_ms=0, end_ms=5000)
        groups: list[PowerGroup] = []
        library = _make_library(_make_effect("Color Wash", duration_type="section"))
        variant_library = _make_variant_library("Color Wash")
        hierarchy = _make_hierarchy()

        result = place_effects(assignment, groups, library, hierarchy, variant_library=variant_library)

        # With no groups, the result should still contain placements
        # keyed by individual model names rather than group names
        assert len(result) > 0, "Should produce placements even with no groups"
        all_placements = [p for ps in result.values() for p in ps]
        assert len(all_placements) > 0, "Should produce at least one placement in flat mode"


# ── T007: theme-variant-separation refactor contracts ────────────────────────
# These tests FAIL against the current implementation.  They document the
# expected post-refactor behaviour so that once the refactor lands all three
# should turn green.


class TestVariantLibraryResolution:
    """T007-1: place_effects resolves variant parameters from variant_library."""

    def test_place_effects_resolves_variant_from_library(self) -> None:
        """Variant parameters must come from variant_library."""
        fire_def = _make_effect("Fire", xlights_id="eff_FIRE", duration_type="section")
        library = _make_library(fire_def)

        variant = EffectVariant(
            name="fire-refactor-test",
            base_effect="Fire",
            description="test",
            parameter_overrides={"E_SLIDER_Fire_Height": 99},
            tags=VariantTags(),
        )
        variant_lib = VariantLibrary(
            schema_version="1.0.0",
            variants={"fire-refactor-test": variant},
            builtin_names=set(),
        )

        layer = EffectLayer(variant="fire-refactor-test")
        assert not hasattr(layer, "parameter_overrides"), (
            "Post-refactor EffectLayer must NOT have a parameter_overrides attribute."
        )

        assignment = _make_assignment(layers=[layer])
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["Model_A"])]
        hierarchy = _make_hierarchy()

        result = place_effects(assignment, groups, library, hierarchy,
                               variant_library=variant_lib)
        all_placements = [p for ps in result.values() for p in ps]
        assert len(all_placements) > 0

        found = any(p.parameters.get("E_SLIDER_Fire_Height") == 99 for p in all_placements)
        assert found, (
            "Expected E_SLIDER_Fire_Height=99 from variant_library, "
            f"got: {[p.parameters for p in all_placements]}"
        )


class TestApplyVariationRemoved:
    """T007-2: _apply_variation must not exist after the refactor."""

    def test_apply_variation_removed(self) -> None:
        """_apply_variation must not be importable from effect_placer after the refactor."""
        with pytest.raises(ImportError):
            from src.generator.effect_placer import _apply_variation  # noqa: F401


class TestNoParameterOverridesOnLayer:
    """T007-3: EffectLayer must not have a parameter_overrides attribute post-refactor."""

    def test_place_effects_no_parameter_overrides_on_layer(self) -> None:
        """EffectLayer instances must have no parameter_overrides attribute."""
        layer = EffectLayer(variant="Color Wash")
        assert not hasattr(layer, "parameter_overrides"), (
            "Post-refactor EffectLayer must NOT have a parameter_overrides field."
        )


# ── Tier-selection helpers (043) ─────────────────────────────────────────────


def _bar_marks(start_ms: int, count: int, bar_ms: int = 500) -> list[TimingMark]:
    """Build a list of bar marks at fixed intervals."""
    return [TimingMark(time_ms=start_ms + i * bar_ms, confidence=1.0, label=f"bar{i}")
            for i in range(count)]


def _hierarchy_with_bars_and_curve(
    bar_times: list[int],
    energy_values: list[int] | None = None,
    energy_fps: int = 47,
    duration_ms: int = 20000,
) -> HierarchyResult:
    """Build a HierarchyResult with bar track and optional full_mix energy curve."""
    bars_track = TimingTrack(
        name="bars", algorithm_name="test", element_type="bar",
        marks=[TimingMark(time_ms=t, confidence=1.0, label="downbeat") for t in bar_times],
        quality_score=0.9,
    )
    curves: dict[str, ValueCurve] = {}
    if energy_values is not None:
        curves["full_mix"] = ValueCurve(
            name="full_mix", stem_source="full_mix", fps=energy_fps, values=energy_values,
        )
    return HierarchyResult(
        schema_version="2.0.0", source_file="test.mp3", source_hash="abc",
        duration_ms=duration_ms, estimated_bpm=120.0,
        bars=bars_track, energy_curves=curves,
    )


class TestComputeActiveTiers:
    """_compute_active_tiers returns the single-partition tier set per section."""

    def test_ethereal_returns_tiers_1_and_8(self) -> None:
        from src.generator.effect_placer import _compute_active_tiers
        section = SectionEnergy(label="intro", start_ms=0, end_ms=10000,
                                energy_score=20, mood_tier="ethereal", impact_count=0)
        hierarchy = _make_hierarchy()
        assert _compute_active_tiers(section, 0, hierarchy) == frozenset({8})

    def test_aggressive_returns_tiers_4_and_8(self) -> None:
        from src.generator.effect_placer import _compute_active_tiers
        section = SectionEnergy(label="chorus", start_ms=0, end_ms=10000,
                                energy_score=85, mood_tier="aggressive", impact_count=0)
        hierarchy = _make_hierarchy()
        assert _compute_active_tiers(section, 0, hierarchy) == frozenset({4, 8})

    def test_structural_without_phrase_uses_prop_tier(self) -> None:
        """Structural section with no bar data → tier 6 (PROP variety)."""
        from src.generator.effect_placer import _compute_active_tiers
        section = SectionEnergy(label="verse", start_ms=0, end_ms=10000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _make_hierarchy()  # no bars, no energy curves
        assert _compute_active_tiers(section, 0, hierarchy) == frozenset({6, 8})

    def test_structural_with_strong_phrase_uses_geo(self) -> None:
        """Structural section with periodic bar-energy pattern → tier 2 (GEO call-response)."""
        from src.generator.effect_placer import _compute_active_tiers
        # 16 bars, every 4th bar is loud — classic phrase structure
        bar_times = list(range(0, 16 * 500, 500))
        # Energy values at 47fps; bars land on frames 0, 23, 47, 70, etc.
        # Build an energy signal where bars 0, 4, 8, 12 (every 4th) are 80, others 20.
        energy = [20] * 20000
        for i, bar_t in enumerate(bar_times):
            is_phrase_start = (i % 4) == 0
            peak = 80 if is_phrase_start else 20
            frame = int(bar_t * 47 / 1000)
            # set a small window around each bar onset
            for f in range(frame, min(frame + 5, len(energy))):
                energy[f] = peak
        section = SectionEnergy(label="verse", start_ms=0, end_ms=16 * 500,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _hierarchy_with_bars_and_curve(bar_times, energy_values=energy)
        assert _compute_active_tiers(section, 0, hierarchy) == frozenset({2, 8})


class TestHasStrongPhraseStructure:
    """_has_strong_phrase_structure detects periodicity at phrase length."""

    def test_no_energy_curve_returns_false(self) -> None:
        from src.generator.effect_placer import _has_strong_phrase_structure
        section = SectionEnergy(label="v", start_ms=0, end_ms=10000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _make_hierarchy()  # no curves
        assert _has_strong_phrase_structure(section, hierarchy) is False

    def test_no_bars_returns_false(self) -> None:
        from src.generator.effect_placer import _has_strong_phrase_structure
        section = SectionEnergy(label="v", start_ms=0, end_ms=10000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        # Hierarchy with energy curve but no bars
        hierarchy = HierarchyResult(
            schema_version="2.0.0", source_file="t.mp3", source_hash="a",
            duration_ms=10000, estimated_bpm=120.0,
            energy_curves={"full_mix": ValueCurve(name="full_mix", stem_source="full_mix", fps=47, values=[50] * 500)},
        )
        assert _has_strong_phrase_structure(section, hierarchy) is False

    def test_too_few_bars_returns_false(self) -> None:
        from src.generator.effect_placer import _has_strong_phrase_structure
        section = SectionEnergy(label="v", start_ms=0, end_ms=10000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        # Only 4 bars — less than 2 * phrase_len_bars
        hierarchy = _hierarchy_with_bars_and_curve([0, 500, 1000, 1500], energy_values=[50] * 500)
        assert _has_strong_phrase_structure(section, hierarchy) is False

    def test_flat_energy_returns_false(self) -> None:
        """Constant energy across 16 bars → zero variance → correlation 0 → False."""
        from src.generator.effect_placer import _has_strong_phrase_structure
        bar_times = list(range(0, 8000, 500))  # 16 bars
        energy = [50] * 1000
        section = SectionEnergy(label="v", start_ms=0, end_ms=8000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _hierarchy_with_bars_and_curve(bar_times, energy_values=energy)
        assert _has_strong_phrase_structure(section, hierarchy) is False

    def test_periodic_energy_returns_true(self) -> None:
        """Every 4th bar loud, others quiet → high lag-4 correlation → True."""
        from src.generator.effect_placer import _has_strong_phrase_structure
        bar_times = list(range(0, 16 * 500, 500))
        energy = [20] * 2000
        for i, bar_t in enumerate(bar_times):
            peak = 80 if (i % 4) == 0 else 20
            frame = int(bar_t * 47 / 1000)
            for f in range(frame, min(frame + 5, len(energy))):
                energy[f] = peak
        section = SectionEnergy(label="v", start_ms=0, end_ms=16 * 500,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _hierarchy_with_bars_and_curve(bar_times, energy_values=energy)
        assert _has_strong_phrase_structure(section, hierarchy) is True


class TestPlaceCallResponse:
    """_place_call_response alternates GEO zones between phrases."""

    def _geo_groups(self) -> list[PowerGroup]:
        return [
            PowerGroup(name="02_GEO_Left", tier=2, members=["Model_A"]),
            PowerGroup(name="02_GEO_Top", tier=2, members=["Model_B"]),
            PowerGroup(name="02_GEO_Right", tier=2, members=["Model_C"]),
            PowerGroup(name="02_GEO_Bot", tier=2, members=["Model_D"]),
        ]

    def test_phrase_1_places_on_call_side_only(self) -> None:
        from src.generator.effect_placer import _place_call_response
        # 4 bars = exactly one phrase
        bar_times = [0, 500, 1000, 1500]
        section = SectionEnergy(label="v", start_ms=0, end_ms=2000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _hierarchy_with_bars_and_curve(bar_times, duration_ms=2000)
        result = _place_call_response(
            _make_effect("Color Wash"),
            EffectLayer(variant="Color Wash"),
            self._geo_groups(), section, hierarchy,
            palette=["#ff0000"],
        )
        assert "02_GEO_Left" in result
        assert "02_GEO_Top" in result
        assert "02_GEO_Right" not in result
        assert "02_GEO_Bot" not in result

    def test_phrase_2_places_on_answer_side_only(self) -> None:
        from src.generator.effect_placer import _place_call_response
        # 8 bars = two phrases
        bar_times = list(range(0, 4000, 500))
        section = SectionEnergy(label="v", start_ms=0, end_ms=4000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _hierarchy_with_bars_and_curve(bar_times, duration_ms=4000)
        result = _place_call_response(
            _make_effect("Color Wash"),
            EffectLayer(variant="Color Wash"),
            self._geo_groups(), section, hierarchy,
            palette=["#ff0000"],
        )
        # Phrase 0 bars 0-3 → call side, phrase 1 bars 4-7 → answer side
        call_placements = result.get("02_GEO_Left", []) + result.get("02_GEO_Top", [])
        answer_placements = result.get("02_GEO_Right", []) + result.get("02_GEO_Bot", [])
        assert len(call_placements) >= 2                            # left + top, one each
        assert len(answer_placements) >= 2                          # right + bot, one each

        # Call-side placements should end at the phrase-1 boundary (bar 4 = 2000ms)
        for p in call_placements:
            assert p.end_ms <= 2000 + FRAME_INTERVAL_MS
        # Answer-side placements should start at the phrase-1 boundary
        for p in answer_placements:
            assert p.start_ms >= 2000 - FRAME_INTERVAL_MS

    def test_center_and_mid_zones_are_excluded(self) -> None:
        """Groups outside the call/answer sides (Center/Mid) never receive placements."""
        from src.generator.effect_placer import _place_call_response
        bar_times = [0, 500, 1000, 1500]
        section = SectionEnergy(label="v", start_ms=0, end_ms=2000,
                                energy_score=50, mood_tier="structural", impact_count=0)
        hierarchy = _hierarchy_with_bars_and_curve(bar_times, duration_ms=2000)
        groups = self._geo_groups() + [
            PowerGroup(name="02_GEO_Center", tier=2, members=["Model_X"]),
            PowerGroup(name="02_GEO_Mid", tier=2, members=["Model_Y"]),
        ]
        result = _place_call_response(
            _make_effect("Color Wash"),
            EffectLayer(variant="Color Wash"),
            groups, section, hierarchy,
            palette=["#ff0000"],
        )
        assert "02_GEO_Center" not in result
        assert "02_GEO_Mid" not in result
