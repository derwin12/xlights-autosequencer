"""Tests for corpus-derived prop-family recipes (tier-6 PROP placement)."""
from __future__ import annotations

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.effects.library import EffectLibrary
from src.effects.models import EffectDefinition
from src.generator.corpus_recipes import (
    CORPUS_RECIPES,
    recipe_for_group,
    section_qualifies,
)
from src.generator.effect_placer import place_effects
from src.generator.models import SectionAssignment, SectionEnergy
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer, Theme
from src.variants.library import VariantLibrary
from src.variants.models import EffectVariant, VariantTags


# ── Helpers (mirroring test_effect_placer.py fixtures) ───────────────────────


def _make_effect(name: str, xlights_id: str = "", duration_type: str = "section") -> EffectDefinition:
    return EffectDefinition(
        name=name,
        xlights_id=xlights_id or f"E_{name.upper().replace(' ', '')}",
        category="test",
        description="test effect",
        intent="fill",
        parameters=[],
        prop_suitability={"matrix": "ideal", "outline": "good"},
        analysis_mappings=[],
        layer_role="standalone",
        duration_type=duration_type,
    )


def _make_library(*names: str) -> EffectLibrary:
    effects = tuple(_make_effect(n) for n in names)
    return EffectLibrary(
        schema_version="1.0.0",
        target_xlights_version="2024.15",
        effects={e.name: e for e in effects},
    )


def _make_variant_library(*effect_names: str) -> VariantLibrary:
    variants = {
        name: EffectVariant(
            name=name, base_effect=name, description=f"variant {name}",
            parameter_overrides={}, tags=VariantTags(),
        )
        for name in effect_names
    }
    return VariantLibrary(
        schema_version="1.0.0", variants=variants, builtin_names=set(effect_names),
    )


def _make_section(label: str = "chorus", energy: int = 80,
                  start_ms: int = 0, end_ms: int = 8000) -> SectionEnergy:
    return SectionEnergy(
        label=label, start_ms=start_ms, end_ms=end_ms,
        energy_score=energy, mood_tier="structural", impact_count=0,
    )


def _make_hierarchy(beat_times: list[int] | None, duration_ms: int = 8000) -> HierarchyResult:
    beats_track = None
    if beat_times is not None:
        marks = [TimingMark(time_ms=t, confidence=None, label=str((i % 4) + 1))
                 for i, t in enumerate(beat_times)]
        beats_track = TimingTrack(
            name="beats", algorithm_name="test", element_type="beat",
            marks=marks, quality_score=0.9,
        )
    return HierarchyResult(
        schema_version="2.0.0", source_file="test.mp3", source_hash="abc123",
        duration_ms=duration_ms, estimated_bpm=120.0, beats=beats_track,
    )


def _make_full_hierarchy(beat_times: list[int] | None) -> HierarchyResult:
    """Like _make_hierarchy, plus the marks VU Meter's mapped tracks need
    (kick_hits/riff_bursts/events "bass"+"vocals") so every matrix
    motion_rotation slot resolves to its intended effect instead of falling
    back to the primary pair for a missing track."""
    hierarchy = _make_hierarchy(beat_times)
    hierarchy.kick_hits = [TimingMark(time_ms=100, confidence=None)]
    hierarchy.riff_bursts = [TimingMark(time_ms=200, confidence=None)]
    hierarchy.events = {
        "bass": TimingTrack(name="bass", algorithm_name="test", element_type="onset",
                             marks=[TimingMark(time_ms=150, confidence=None)], quality_score=0.9),
        "vocals": TimingTrack(name="vocals", algorithm_name="test", element_type="onset",
                               marks=[TimingMark(time_ms=250, confidence=None)], quality_score=0.9),
    }
    return hierarchy


def _make_assignment(section: SectionEnergy, layers: list[EffectLayer],
                     variation_seed: int = 0,
                     active_tiers: frozenset[int] = frozenset({1, 6}),
                     corpus_occurrence: dict[str, int] | None = None) -> SectionAssignment:
    theme = Theme(
        name="Test Theme", mood="structural", occasion="general", genre="any",
        intent="test", layers=layers, palette=["#ff0000", "#00ff00"],
    )
    return SectionAssignment(
        section=section, theme=theme,
        active_tiers=active_tiers,
        variation_seed=variation_seed,
        corpus_occurrence=corpus_occurrence or {},
    )


_SNOWFLAKE_GROUP = PowerGroup(
    name="06_PROP_Snowflake", tier=6, members=["Snowflake 1", "Snowflake 2"],
)
_ARCH_GROUP = PowerGroup(
    name="06_PROP_Arch", tier=6, members=["Arch 1", "Arch 2"],
)
_MEGATREE_GROUP = PowerGroup(
    name="06_PROP_Mega_Tree", tier=6, members=["Mega Tree 1", "Mega Tree 2"],
)
_CANE_GROUP = PowerGroup(
    name="06_PROP_Candy_Cane", tier=6, members=["Cane 1", "Cane 2"],
)
_HORIZONTAL_GROUP = PowerGroup(
    name="06_PROP_Horizontal", tier=6, members=["Horizontal 1", "Horizontal 2"],
)
_VERTICAL_GROUP = PowerGroup(
    name="06_PROP_Vertical", tier=6, members=["Vertical 1", "Vertical 2"],
)

_BEATS = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500]

_DEFAULT_LIBRARY_NAMES = ("Color Wash", "Shockwave", "Ripple", "Single Strand", "Spirals")


def _place(section: SectionEnergy, group: PowerGroup,
           variation_seed: int = 0,
           layers: list[EffectLayer] | None = None,
           hierarchy: HierarchyResult | None = None,
           library_names: tuple[str, ...] = _DEFAULT_LIBRARY_NAMES,
           active_tiers: frozenset[int] = frozenset({1, 6}),
           corpus_occurrence: dict[str, int] | None = None):
    layers = layers or [EffectLayer(variant="Color Wash")]
    library = _make_library(*library_names)
    variant_library = _make_variant_library(*library_names)
    assignment = _make_assignment(section, layers, variation_seed=variation_seed,
                                  active_tiers=active_tiers,
                                  corpus_occurrence=corpus_occurrence)
    return place_effects(
        assignment, [group], library,
        hierarchy if hierarchy is not None else _make_hierarchy(_BEATS),
        variant_library=variant_library,
    )


# ── recipe_for_group matching ─────────────────────────────────────────────────


class TestRecipeMatching:
    def test_snowflake_group_name_matches(self) -> None:
        assert recipe_for_group(_SNOWFLAKE_GROUP).family == "snowflake"

    def test_flake_token_matches(self) -> None:
        g = PowerGroup(name="06_PROP_HFlake", tier=6, members=["HFlake1"])
        assert recipe_for_group(g).family == "snowflake"

    def test_arch_group_name_matches(self) -> None:
        assert recipe_for_group(_ARCH_GROUP).family == "arch"

    def test_unrelated_group_no_match(self) -> None:
        g = PowerGroup(name="06_PROP_Wreath", tier=6, members=["Wreath 1", "Wreath 2"])
        assert recipe_for_group(g) is None

    def test_member_majority_matches(self) -> None:
        g = PowerGroup(name="06_PROP_Yard", tier=6,
                       members=["EFlake46", "ChromaFlake L", "Santa"])
        assert recipe_for_group(g).family == "snowflake"

    def test_member_minority_no_match(self) -> None:
        g = PowerGroup(name="06_PROP_Yard", tier=6,
                       members=["EFlake46", "Santa", "Sleigh"])
        assert recipe_for_group(g) is None

    def test_radial_subgroup_excluded(self) -> None:
        g = PowerGroup(name="06_PROP_EFlake46_Rings", tier=6,
                       members=["EFlake46/Ring 1", "EFlake46/Ring 2"],
                       prop_type="radial")
        assert recipe_for_group(g) is None

    def test_non_tier6_excluded(self) -> None:
        g = PowerGroup(name="07_COMP_Arches", tier=7, members=["Arch 1", "Arch 2"])
        assert recipe_for_group(g) is None

    def test_megatree_group_name_matches(self) -> None:
        assert recipe_for_group(_MEGATREE_GROUP).family == "megatree"

    def test_megatree_member_majority_matches(self) -> None:
        g = PowerGroup(name="06_PROP_Trees", tier=6,
                       members=["Mega Tree 1", "Mega Tree 2", "Palm Tree"])
        assert recipe_for_group(g).family == "megatree"

    def test_mega_topper_matches_its_own_family_not_megatree(self) -> None:
        g = PowerGroup(name="06_PROP_Mega_Topper", tier=6,
                       members=["Mega Topper 1", "Mega Topper 2"])
        assert recipe_for_group(g).family == "megatopper"

    def test_hero_megatree_group_matches(self) -> None:
        # A solo mega tree never forms a tier-6 pair group — it is promoted
        # to a tier-8 HERO group, which must still receive the recipe.
        g = PowerGroup(name="08_HERO_Mega_Tree", tier=8, members=["Mega Tree"])
        assert recipe_for_group(g).family == "megatree"

    def test_hero_with_submodel_members_matches(self) -> None:
        g = PowerGroup(name="08_HERO_Mega_Tree", tier=8,
                       members=["Mega Tree/Ring 1", "Mega Tree/Ring 2"])
        assert recipe_for_group(g).family == "megatree"

    def test_non_recipe_tiers_still_excluded(self) -> None:
        g = PowerGroup(name="07_COMP_Mega_Tree", tier=7, members=["Mega Tree"])
        assert recipe_for_group(g) is None


# ── section_qualifies gating ──────────────────────────────────────────────────


class TestSectionQualifies:
    def test_chorus_label_qualifies(self) -> None:
        recipe = CORPUS_RECIPES[0]
        assert section_qualifies(recipe, _make_section(label="chorus", energy=40))

    def test_low_energy_verse_does_not_qualify(self) -> None:
        recipe = CORPUS_RECIPES[0]
        assert not section_qualifies(recipe, _make_section(label="verse", energy=40))

    def test_high_energy_verse_qualifies(self) -> None:
        recipe = CORPUS_RECIPES[0]
        assert section_qualifies(recipe, _make_section(label="verse", energy=70))


# ── place_effects integration ─────────────────────────────────────────────────


class TestCorpusRecipePlacement:
    def test_snowflake_chorus_gets_white_shockwave_per_beat(self) -> None:
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP)
        placements = result["06_PROP_Snowflake"]
        assert len(placements) == len(_BEATS)
        assert all(p.effect_name == "Shockwave" for p in placements)
        assert all(p.color_palette == ["#FFFFFF"] for p in placements)
        # Back-to-back full-beat segments: each starts on its beat mark and
        # ends on the next (500ms apart), including the extended last beat.
        for i, p in enumerate(placements):
            assert p.start_ms == _BEATS[i]
            assert p.end_ms - p.start_ms == 500

    def test_arch_chorus_gets_white_single_strand_per_beat(self) -> None:
        result = _place(_make_section(label="chorus"), _ARCH_GROUP)
        placements = result["06_PROP_Arch"]
        assert len(placements) == len(_BEATS)
        assert all(p.effect_name == "Single Strand" for p in placements)
        assert all(p.color_palette == ["#FFFFFF"] for p in placements)

    def test_repeated_section_alternates_to_single_strand(self) -> None:
        # variation_seed is the global section index; the recipe halves it
        # before taking parity so verse/chorus alternation still cycles both
        # effects. Seeds 0-1 -> Shockwave, 2-3 -> SingleStrand.
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, variation_seed=3)
        placements = result["06_PROP_Snowflake"]
        assert placements
        assert all(p.effect_name == "Single Strand" for p in placements)

    def test_snowflake_burst_size_rotates_with_occurrence_style(self) -> None:
        # Shockwave End_Radius is mined per-song (40-150); rotate between the
        # two best-supported values by variation_seed parity, same idiom as
        # arch's chase-size rotation.
        even = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, variation_seed=0)
        odd = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, variation_seed=1)
        assert all(p.parameters["E_SLIDER_Shockwave_End_Radius"] == "100" for p in even["06_PROP_Snowflake"])
        assert all(p.parameters["E_SLIDER_Shockwave_End_Radius"] == "50" for p in odd["06_PROP_Snowflake"])

    def test_snowflake_placements_carry_shockwave_burst_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP)
        placements = result["06_PROP_Snowflake"]
        assert placements
        for p in placements:
            assert p.parameters["E_CHECKBOX_Shockwave_Blend_Edges"] == "1"
            assert p.parameters["E_SLIDER_Shockwave_Start_Radius"] == "1"
            assert p.parameters["E_SLIDER_Shockwave_End_Radius"] == "100"

    def test_arch_placements_carry_from_head_chase_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _ARCH_GROUP)
        placements = result["06_PROP_Arch"]
        assert placements
        for p in placements:
            assert p.parameters["E_CHOICE_Fade_Type"] == "From Head"
            assert p.parameters["E_CHOICE_SingleStrand_Colors"] == "Palette"

    def test_arch_chorus_ping_pongs_chase_direction_per_beat(self) -> None:
        # variation_seed=0: primary effect (0//2%2==0) and ping-pong style
        # (0%2==0) -- direction alternates Left-Right/Right-Left per beat,
        # mirroring the mined per-beat pattern on genuine arch elements.
        result = _place(_make_section(label="chorus"), _ARCH_GROUP, variation_seed=0)
        placements = result["06_PROP_Arch"]
        directions = [p.parameters["E_CHOICE_Chase_Type1"] for p in placements]
        assert directions == ["Left-Right", "Right-Left"] * (len(directions) // 2)

    def test_arch_chorus_bounce_direction_constant_on_odd_seed(self) -> None:
        # variation_seed=1: still the primary effect (1//2%2==0) but the
        # odd seed parity (1%2==1) selects the constant "Bounce from Right"
        # style instead of ping-ponging.
        result = _place(_make_section(label="chorus"), _ARCH_GROUP, variation_seed=1)
        placements = result["06_PROP_Arch"]
        assert placements
        assert all(p.parameters["E_CHOICE_Chase_Type1"] == "Bounce from Right" for p in placements)

    def test_arch_chase_size_rotates_with_occurrence_style(self) -> None:
        # Chase band size is paired with the same style bit as direction:
        # ping-pong occurrences (even seed) get the tighter 25, bounce
        # occurrences (odd seed) get the wider 50.
        even = _place(_make_section(label="chorus"), _ARCH_GROUP, variation_seed=0)
        odd = _place(_make_section(label="chorus"), _ARCH_GROUP, variation_seed=1)
        assert all(p.parameters["E_SLIDER_Color_Mix1"] == "25" for p in even["06_PROP_Arch"])
        assert all(p.parameters["E_SLIDER_Color_Mix1"] == "50" for p in odd["06_PROP_Arch"])

    def test_arch_bridge_gets_spirals(self) -> None:
        # "bridge" is not in the default qualifying_labels, but arch adds it
        # specifically so its label-alt (mined: Spirals 56/76 bridge
        # placements) can fire even at ordinary (non-chorus) energy.
        result = _place(_make_section(label="bridge", energy=40), _ARCH_GROUP)
        placements = result["06_PROP_Arch"]
        assert placements
        assert all(p.effect_name == "Spirals" for p in placements)
        for p in placements:
            assert p.parameters["E_SLIDER_Spirals_Rotation"] == "-100"
            assert p.parameters["E_SLIDER_Spirals_Thickness"] == "20"
            assert "E_CHOICE_Fade_Type" not in p.parameters

    def test_arch_bridge_label_alt_overrides_seed_alternation(self) -> None:
        # A bridge section must get Spirals regardless of variation_seed
        # parity -- the label-alt takes priority over the chorus seed-based
        # Single Strand/Shockwave alternation.
        result = _place(_make_section(label="bridge", energy=40), _ARCH_GROUP, variation_seed=3)
        placements = result["06_PROP_Arch"]
        assert placements
        assert all(p.effect_name == "Spirals" for p in placements)

    def test_arch_repeated_section_alternates_to_shockwave(self) -> None:
        # Mirrors test_repeated_section_alternates_to_ripple: seeds 0-1 keep
        # Single Strand, seeds 2-3 alternate to Shockwave.
        result = _place(_make_section(label="chorus"), _ARCH_GROUP, variation_seed=3)
        placements = result["06_PROP_Arch"]
        assert placements
        assert all(p.effect_name == "Shockwave" for p in placements)

    def test_arch_alternate_effect_does_not_inherit_chase_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _ARCH_GROUP, variation_seed=3)
        placements = result["06_PROP_Arch"]
        assert placements
        for p in placements:
            assert p.effect_name == "Shockwave"
            assert "E_CHOICE_Fade_Type" not in p.parameters
            assert p.parameters["E_SLIDER_Shockwave_End_Radius"] == "100"

    def test_alternate_effect_does_not_inherit_primary_preset(self) -> None:
        # SingleStrand must not receive Shockwave parameter overrides, and
        # must carry its own mined preset.
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, variation_seed=3)
        placements = result["06_PROP_Snowflake"]
        assert placements
        for p in placements:
            assert p.effect_name == "Single Strand"
            assert "E_SLIDER_Shockwave_End_Radius" not in p.parameters
            assert p.parameters["E_CHOICE_Chase_Type1"] == "To Middle"
            assert p.parameters["E_CHOICE_SingleStrand_FX"] == "Fireworks 1D"

    def test_adjacent_seed_keeps_primary_effect(self) -> None:
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, variation_seed=1)
        placements = result["06_PROP_Snowflake"]
        assert placements
        assert all(p.effect_name == "Shockwave" for p in placements)

    def test_low_energy_verse_keeps_normal_placement(self) -> None:
        result = _place(_make_section(label="verse", energy=40), _SNOWFLAKE_GROUP)
        placements = result.get("06_PROP_Snowflake", [])
        # Normal pool placement applies: not the corpus recipe's solid-white
        # per-beat Shockwave stack.
        assert not (
            placements
            and all(p.effect_name == "Shockwave" and p.color_palette == ["#FFFFFF"] for p in placements)
        )

    def test_no_beats_track_falls_back_to_normal_placement(self) -> None:
        # bug-159 lesson: missing analysis data must never suppress placement.
        result = _place(
            _make_section(label="chorus"), _SNOWFLAKE_GROUP,
            hierarchy=_make_hierarchy(None),
        )
        assert result.get("06_PROP_Snowflake"), "group must still receive placements"

    def test_megatree_without_on_falls_back_to_single_layer(self) -> None:
        # The default test library has no "On" definition, so the
        # color-over-mask composition degrades to the flat form.
        result = _place(_make_section(label="chorus"), _MEGATREE_GROUP)
        placements = result["06_PROP_Mega_Tree"]
        assert len(placements) == len(_BEATS)
        assert all(p.effect_name == "Shockwave" for p in placements)
        assert all(p.color_palette == ["#FFFFFF"] for p in placements)
        assert all(p.layer == 0 for p in placements)

    def test_megatree_alternate_is_spirals_with_mined_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _MEGATREE_GROUP, variation_seed=3)
        placements = result["06_PROP_Mega_Tree"]
        assert placements
        for p in placements:
            assert p.effect_name == "Spirals"
            assert p.parameters["E_SLIDER_Spirals_Count"] == "1"
            assert p.parameters["E_CHECKBOX_Spirals_Grow"] == "0"
            assert "E_SLIDER_Shockwave_End_Radius" not in p.parameters


# ── megatree color-over-mask composition ─────────────────────────────────────


_LIBRARY_WITH_ON = _DEFAULT_LIBRARY_NAMES + ("On",)


class TestMegatreeColorOverMask:
    def test_on_color_layer_over_mask_layer(self) -> None:
        # 8 beats at the default color_cycle_beats=4 -> 2 bar-cycled blocks,
        # not one section-spanning block (direct corpus block-duration
        # measurement, 2026-07-15, corrected the section-spanning claim).
        section = _make_section(label="chorus")
        result = _place(section, _MEGATREE_GROUP, library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Mega_Tree"]

        color_layers = sorted(
            (p for p in placements if p.effect_name == "On"), key=lambda p: p.start_ms,
        )
        masks = [p for p in placements if p.effect_name == "Shockwave"]
        assert len(color_layers) == 2
        assert len(masks) == len(_BEATS)

        first, second = color_layers
        # On sits on the top layer and carries the mined Unmask blend so the
        # mask below only contributes shape/brightness.
        assert first.layer == 0 and second.layer == 0
        assert first.start_ms == section.start_ms
        assert first.end_ms == _BEATS[4]
        assert second.start_ms == _BEATS[4]
        assert second.end_ms == section.end_ms
        assert first.parameters["T_CHOICE_LayerMethod"] == "2 is Unmask"
        assert second.parameters["T_CHOICE_LayerMethod"] == "2 is Unmask"
        # Color comes from the section theme (one solid color per block),
        # cycling to a different color for the second bar.
        assert len(first.color_palette) == 1
        assert first.color_palette != second.color_palette

        # Masks move to layer 1, stay white (shape only).
        assert all(p.layer == 1 for p in masks)
        assert all(p.color_palette == ["#FFFFFF"] for p in masks)

    def test_spirals_alternate_also_gets_color_layer(self) -> None:
        result = _place(_make_section(label="chorus"), _MEGATREE_GROUP,
                        variation_seed=3, library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Mega_Tree"]
        assert [p.effect_name for p in placements].count("On") == 2
        masks = [p for p in placements if p.effect_name == "Spirals"]
        assert masks
        assert all(p.layer == 1 for p in masks)

    def test_color_cycle_length_bundles_with_occurrence_style(self) -> None:
        # variation_seed=1 keeps the primary effect (Shockwave stays --
        # effect alternation only flips at (seed//2)%2==1) but is odd, so
        # the alt-style bit (same one bundling direction/size on other
        # families) applies: 8-beat cycle instead of the default 4-beat.
        even = _place(_make_section(label="chorus"), _MEGATREE_GROUP,
                      variation_seed=0, library_names=_LIBRARY_WITH_ON)
        odd = _place(_make_section(label="chorus"), _MEGATREE_GROUP,
                     variation_seed=1, library_names=_LIBRARY_WITH_ON)
        even_ons = [p for p in even["06_PROP_Mega_Tree"] if p.effect_name == "On"]
        odd_ons = [p for p in odd["06_PROP_Mega_Tree"] if p.effect_name == "On"]
        assert len(even_ons) == 2
        assert len(odd_ons) == 1

    def test_snowflake_recipe_not_affected_by_on_in_library(self) -> None:
        # color_over_mask is megatree-only; snowflakes stay single-layer
        # bursts (plus their Off backdrop when Off exists).
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Snowflake"]
        assert all(p.effect_name != "On" for p in placements)
        assert all(p.layer == 0 for p in placements)


# ── candy cane recipe ────────────────────────────────────────────────────────


class TestCaneRecipe:
    def test_cane_group_name_matches(self) -> None:
        assert recipe_for_group(_CANE_GROUP).family == "cane"

    def test_candy_token_matches(self) -> None:
        group = PowerGroup(name="06_PROP_Candy", tier=6, members=["Candy 1"])
        assert recipe_for_group(group).family == "cane"

    def test_member_majority_matches(self) -> None:
        group = PowerGroup(
            name="06_PROP_Misc", tier=6,
            members=["Cane 1", "Cane 2 Lines", "Star"],
        )
        assert recipe_for_group(group).family == "cane"

    def test_cane_chorus_gets_white_chase_per_beat(self) -> None:
        result = _place(_make_section(label="chorus"), _CANE_GROUP)
        placements = result["06_PROP_Candy_Cane"]
        assert len(placements) == len(_BEATS)
        for p in placements:
            assert p.effect_name == "Single Strand"
            assert p.color_palette == ["#FFFFFF"]
            assert p.parameters["E_CHOICE_Fade_Type"] == "From Head"

    def test_cane_alternate_is_flat_spirals_with_mined_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=3)
        placements = result["06_PROP_Candy_Cane"]
        assert placements
        for p in placements:
            assert p.effect_name == "Spirals"
            assert p.parameters["E_CHECKBOX_Spirals_3D"] == "0"
            assert p.parameters["E_SLIDER_Spirals_Thickness"] == "33"
            assert "E_CHOICE_Fade_Type" not in p.parameters

    def test_cane_on_color_layer_over_chase_mask(self) -> None:
        # Bar-cycled, not section-spanning (see megatree test for the same
        # correction and its rationale).
        section = _make_section(label="chorus")
        result = _place(section, _CANE_GROUP, library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Candy_Cane"]
        color_layers = sorted(
            (p for p in placements if p.effect_name == "On"), key=lambda p: p.start_ms,
        )
        masks = [p for p in placements if p.effect_name == "Single Strand"]
        assert len(color_layers) == 2
        assert all(p.layer == 0 for p in color_layers)
        assert color_layers[0].start_ms == section.start_ms
        assert color_layers[-1].end_ms == section.end_ms
        assert all(p.parameters["T_CHOICE_LayerMethod"] == "2 is Unmask" for p in color_layers)
        assert len(masks) == len(_BEATS)
        assert all(p.layer == 1 for p in masks)
        assert all(p.color_palette == ["#FFFFFF"] for p in masks)

    def test_cane_recipe_has_no_off_backdrop(self) -> None:
        # Off backdrop is not part of the mined cane idiom (29/3.0k placements).
        result = _place(_make_section(label="chorus"), _CANE_GROUP,
                        library_names=_DEFAULT_LIBRARY_NAMES + ("Off",))
        offs = [p for p in result["06_PROP_Candy_Cane"] if p.effect_name == "Off"]
        assert offs == []

    def test_cane_low_energy_verse_keeps_normal_placement(self) -> None:
        result = _place(_make_section(label="verse", energy=40), _CANE_GROUP)
        placements = result.get("06_PROP_Candy_Cane", [])
        assert all(p.effect_name != "Single Strand" or
                   "E_NOTEBOOK_SSEFFECT_TYPE" not in p.parameters
                   for p in placements)

    def test_cane_ping_pongs_chase_direction_per_beat(self) -> None:
        result = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=0)
        placements = result["06_PROP_Candy_Cane"]
        directions = [p.parameters["E_CHOICE_Chase_Type1"] for p in placements]
        assert directions == ["Left-Right", "Right-Left"] * (len(directions) // 2)

    def test_cane_bounce_direction_constant_on_odd_seed(self) -> None:
        result = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=1)
        placements = result["06_PROP_Candy_Cane"]
        assert placements
        assert all(p.parameters["E_CHOICE_Chase_Type1"] == "Bounce from Right" for p in placements)

    def test_cane_chase_size_rotates_with_occurrence_style(self) -> None:
        even = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=0)
        odd = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=1)
        assert all(p.parameters["E_SLIDER_Color_Mix1"] == "37" for p in even["06_PROP_Candy_Cane"])
        assert all(p.parameters["E_SLIDER_Color_Mix1"] == "50" for p in odd["06_PROP_Candy_Cane"])

    def test_cane_bounce_style_uses_sparse_four_beat_pacing(self) -> None:
        # Even seed (ping-pong style): one segment per beat, matching _BEATS
        # (8 marks). Odd seed (bounce style): mined whole-song 4-beat pacing
        # -- only 2 segments (marks 0 and 4) instead of 8.
        even = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=0)
        odd = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=1)
        assert len(even["06_PROP_Candy_Cane"]) == len(_BEATS)
        assert len(odd["06_PROP_Candy_Cane"]) == 2

    def test_cane_color_cycle_length_bundles_with_occurrence_style(self) -> None:
        # Same bundled parity bit as direction/size/pacing (variation_seed %
        # 2), and deterministic: re-placing with the same seed reproduces
        # the same cycle length every time, matching "re-rendering the same
        # song stays at whichever cycle was picked" (2026-07-15 user
        # requirement). Even seed -> default 4-beat cycle (2 blocks across
        # 8 marks); odd seed -> 8-beat alt cycle (1 block, since 8 marks
        # exactly fill one 8-beat cycle).
        even = _place(_make_section(label="chorus"), _CANE_GROUP,
                      variation_seed=0, library_names=_LIBRARY_WITH_ON)
        odd = _place(_make_section(label="chorus"), _CANE_GROUP,
                     variation_seed=1, library_names=_LIBRARY_WITH_ON)
        even_again = _place(_make_section(label="chorus"), _CANE_GROUP,
                            variation_seed=0, library_names=_LIBRARY_WITH_ON)

        even_ons = [p for p in even["06_PROP_Candy_Cane"] if p.effect_name == "On"]
        odd_ons = [p for p in odd["06_PROP_Candy_Cane"] if p.effect_name == "On"]
        even_again_ons = [p for p in even_again["06_PROP_Candy_Cane"] if p.effect_name == "On"]

        assert len(even_ons) == 2
        assert len(odd_ons) == 1
        assert len(even_again_ons) == len(even_ons)
        assert [p.start_ms for p in even_again_ons] == [p.start_ms for p in even_ons]


# ── horizontal / vertical house-line recipes ─────────────────────────────────


class TestHouseLineRecipes:
    def test_horizontal_group_name_matches(self) -> None:
        assert recipe_for_group(_HORIZONTAL_GROUP).family == "horizontal"

    def test_vertical_group_name_matches(self) -> None:
        assert recipe_for_group(_VERTICAL_GROUP).family == "vertical"

    def test_horiz_and_vert_short_tokens_match(self) -> None:
        horiz = PowerGroup(name="06_PROP_Horiz_Lines", tier=6, members=["Horiz 1"])
        vert = PowerGroup(name="06_PROP_Vert_Lines", tier=6, members=["Vert 1"])
        assert recipe_for_group(horiz).family == "horizontal"
        assert recipe_for_group(vert).family == "vertical"

    def test_chorus_gets_white_chase_per_beat(self) -> None:
        for group in (_HORIZONTAL_GROUP, _VERTICAL_GROUP):
            result = _place(_make_section(label="chorus"), group)
            placements = result[group.name]
            assert len(placements) == len(_BEATS)
            for p in placements:
                assert p.effect_name == "Single Strand"
                assert p.color_palette == ["#FFFFFF"]
                assert p.parameters["E_CHOICE_Fade_Type"] == "From Head"

    def test_alternate_is_lightning_with_mined_preset(self) -> None:
        # Direction/Width/Number_Segments are randomized per bolt (user
        # request 2026-07-18: xLights' Number_Segments field is labeled
        # "Width of Bolt" in the UI despite its ID -- verified against
        # resources/effectmetadata/Lightning.json); Number_Bolts (UI label
        # "Number of Segments") stays fixed at the mined value of 10.
        result = _place(_make_section(label="chorus"), _VERTICAL_GROUP,
                        variation_seed=3,
                        library_names=_DEFAULT_LIBRARY_NAMES + ("Lightning",))
        placements = result["06_PROP_Vertical"]
        assert placements
        for p in placements:
            assert p.effect_name == "Lightning"
            assert p.parameters["E_CHOICE_Lightning_Direction"] in ("Up", "Down")
            assert 1 <= int(p.parameters["E_SLIDER_Lightning_WIDTH"]) <= 3
            assert 1 <= int(p.parameters["E_SLIDER_Number_Segments"]) <= 5
            assert p.parameters["E_SLIDER_Number_Bolts"] == "10"
            assert "E_CHOICE_Fade_Type" not in p.parameters

    def test_lightning_randomization_is_deterministic(self) -> None:
        result_a = _place(_make_section(label="chorus"), _VERTICAL_GROUP,
                          variation_seed=3,
                          library_names=_DEFAULT_LIBRARY_NAMES + ("Lightning",))
        result_b = _place(_make_section(label="chorus"), _VERTICAL_GROUP,
                          variation_seed=3,
                          library_names=_DEFAULT_LIBRARY_NAMES + ("Lightning",))
        params_a = [p.parameters for p in result_a["06_PROP_Vertical"]]
        params_b = [p.parameters for p in result_b["06_PROP_Vertical"]]
        assert params_a == params_b

    def test_on_color_layer_over_chase_mask(self) -> None:
        # Bar-cycled, not section-spanning (see megatree test for the same
        # correction and its rationale).
        section = _make_section(label="chorus")
        result = _place(section, _HORIZONTAL_GROUP, library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Horizontal"]
        color_layers = [p for p in placements if p.effect_name == "On"]
        masks = [p for p in placements if p.effect_name == "Single Strand"]
        assert len(color_layers) == 2
        assert all(p.parameters["T_CHOICE_LayerMethod"] == "2 is Unmask" for p in color_layers)
        assert len(masks) == len(_BEATS)
        assert all(p.layer == 1 for p in masks)

    def test_adds_off_backdrop(self) -> None:
        for group in (_HORIZONTAL_GROUP, _VERTICAL_GROUP):
            result = _place(_make_section(label="chorus"), group,
                            library_names=_DEFAULT_LIBRARY_NAMES + ("Off",))
            offs = [p for p in result[group.name] if p.effect_name == "Off"]
            assert len(offs) == 1

    def test_ping_pongs_chase_direction_per_beat(self) -> None:
        for group in (_HORIZONTAL_GROUP, _VERTICAL_GROUP):
            result = _place(_make_section(label="chorus"), group, variation_seed=0)
            placements = result[group.name]
            directions = [p.parameters["E_CHOICE_Chase_Type1"] for p in placements]
            assert directions == ["Left-Right", "Right-Left"] * (len(directions) // 2)

    def test_bounce_direction_constant_on_odd_seed(self) -> None:
        for group in (_HORIZONTAL_GROUP, _VERTICAL_GROUP):
            result = _place(_make_section(label="chorus"), group, variation_seed=1)
            placements = result[group.name]
            assert placements
            assert all(p.parameters["E_CHOICE_Chase_Type1"] == "From Middle" for p in placements)

    def test_chase_size_rotates_with_occurrence_style(self) -> None:
        for group in (_HORIZONTAL_GROUP, _VERTICAL_GROUP):
            even = _place(_make_section(label="chorus"), group, variation_seed=0)
            odd = _place(_make_section(label="chorus"), group, variation_seed=1)
            assert all(p.parameters["E_SLIDER_Color_Mix1"] == "46" for p in even[group.name])
            assert all(p.parameters["E_SLIDER_Color_Mix1"] == "50" for p in odd[group.name])

    def test_horizontal_bounce_style_uses_sparse_four_beat_pacing(self) -> None:
        # Only horizontal has beats_per_placement_alt (mined: one strong
        # corpus song, 4.90 beats/seg); vertical's evidence wasn't
        # independently corroborated, so it keeps per-beat pacing always.
        even = _place(_make_section(label="chorus"), _HORIZONTAL_GROUP, variation_seed=0)
        odd = _place(_make_section(label="chorus"), _HORIZONTAL_GROUP, variation_seed=1)
        assert len(even["06_PROP_Horizontal"]) == len(_BEATS)
        assert len(odd["06_PROP_Horizontal"]) == 2

    def test_vertical_keeps_per_beat_pacing_on_both_styles(self) -> None:
        even = _place(_make_section(label="chorus"), _VERTICAL_GROUP, variation_seed=0)
        odd = _place(_make_section(label="chorus"), _VERTICAL_GROUP, variation_seed=1)
        assert len(even["06_PROP_Vertical"]) == len(_BEATS)
        assert len(odd["06_PROP_Vertical"]) == len(_BEATS)


# ── matrix recipe (three-layer stack) ────────────────────────────────────────


_MATRIX_GROUP = PowerGroup(
    name="06_PROP_Matrix", tier=6, members=["Matrix", "Matrix 2"],
)


class TestMatrixRecipe:
    def test_matrix_group_name_matches(self) -> None:
        assert recipe_for_group(_MATRIX_GROUP).family == "matrix"

    def test_lyrics_matrix_excluded(self) -> None:
        group = PowerGroup(
            name="06_PROP_Lyrics_Matrix", tier=6, members=["Lyrics Matrix"],
        )
        recipe = recipe_for_group(group)
        assert recipe is None or recipe.family != "matrix"

    def test_matrix_chorus_gets_three_layer_stack(self) -> None:
        section = _make_section(label="chorus")
        result = _place(section, _MATRIX_GROUP, library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Matrix"]
        ons = [p for p in placements if p.effect_name == "On"]
        bursts = [p for p in placements if p.effect_name == "Shockwave"]
        spins = [p for p in placements if p.effect_name == "Spirals"]
        assert len(ons) == 1 and ons[0].layer == 0
        assert ons[0].parameters["T_CHOICE_LayerMethod"] == "2 is Unmask"
        assert len(bursts) == len(_BEATS)
        assert all(p.layer == 1 for p in bursts)
        # 8 beats at 4 beats per secondary placement -> 2 sustained spins
        assert len(spins) == 2
        assert all(p.layer == 2 for p in spins)
        assert all(p.color_palette == ["#FFFFFF"] for p in spins)
        # seed 0, no occurrence index -> secondary_rotation pool slot 0,
        # the mined thin twin-spiral pair.
        assert all(p.parameters["E_SLIDER_Spirals_Count"] == "2" for p in spins)
        assert all(p.parameters["E_SLIDER_Spirals_Thickness"] == "7" for p in spins)
        # The spins tile the section without gaps
        assert spins[0].start_ms == 0
        assert spins[-1].end_ms == section.end_ms

    def test_matrix_secondary_spirals_alternate_flip_horizontal(self) -> None:
        # User request (2026-07-15): identical back-to-back sustained
        # Spirals spins on the matrix's secondary motion layer read as
        # repetitive -- every other one flips.
        section = _make_section(label="chorus")
        result = _place(section, _MATRIX_GROUP, library_names=_LIBRARY_WITH_ON)
        spins = [p for p in result["06_PROP_Matrix"] if p.effect_name == "Spirals"]
        assert len(spins) == 2
        assert "B_CHOICE_BufferTransform" not in spins[0].parameters
        assert spins[1].parameters["B_CHOICE_BufferTransform"] == "Flip Horizontal"

    def test_matrix_alternate_is_pinwheel_with_mined_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                        variation_seed=3,
                        library_names=_LIBRARY_WITH_ON + ("Pinwheel",))
        placements = result["06_PROP_Matrix"]
        pins = [p for p in placements if p.effect_name == "Pinwheel"]
        assert len(pins) == len(_BEATS)
        for p in pins:
            assert p.parameters["E_CHOICE_Pinwheel_Style"] == "New Render Method"
            assert p.parameters["E_SLIDER_Pinwheel_Arms"] == "2"
            assert "E_SLIDER_Shockwave_End_Radius" not in p.parameters

    def test_motion_rotation_walks_every_slot_via_occurrence(self) -> None:
        # Regression for the seed-aliasing bug: (variation_seed // 2) % len
        # could skip pool slots for songs with regular section strides
        # (Lightning never fired on a real song). Occurrence-driven rotation
        # must reach every slot in pool order.
        from src.generator.corpus_recipes import CORPUS_RECIPES
        recipe = next(r for r in CORPUS_RECIPES if r.family == "matrix")
        pool = recipe.motion_rotation
        libs = _LIBRARY_WITH_ON + ("Pinwheel", "Ripple", "Shape", "VU Meter")
        seen: list[tuple[str, str | None]] = []
        for occ in range(len(pool)):
            result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                            library_names=libs,
                            hierarchy=_make_full_hierarchy(_BEATS),
                            corpus_occurrence={"matrix": occ})
            motion = [p for p in result["06_PROP_Matrix"]
                      if p.effect_name in
                      ("Shockwave", "Pinwheel", "Ripple", "Color Wash", "Shape", "VU Meter")
                      and p.layer == 1]
            assert motion, f"occurrence {occ} placed no motion effects"
            names = {p.effect_name for p in motion}
            assert len(names) == 1
            radius = motion[0].parameters.get("E_SLIDER_Shockwave_End_Radius")
            seen.append((names.pop(), radius))
        expected = [(name, dict(params).get("E_SLIDER_Shockwave_End_Radius"))
                    for name, params in pool]
        assert seen == expected

    def test_secondary_pool_cycles_per_occurrence(self) -> None:
        # Each qualifying occurrence advances the sustained-Spirals preset;
        # distinguish presets by (Count, Thickness).
        expected = [("2", "7"), ("1", "35"), ("1", "20"), ("1", "33"), ("4", "20")]
        for occ, (count, thickness) in enumerate(expected):
            result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                            library_names=_LIBRARY_WITH_ON,
                            corpus_occurrence={"matrix": occ})
            spins = [p for p in result["06_PROP_Matrix"] if p.effect_name == "Spirals"]
            assert spins, f"occurrence {occ} placed no spins"
            assert spins[0].parameters["E_SLIDER_Spirals_Count"] == count
            assert spins[0].parameters["E_SLIDER_Spirals_Thickness"] == thickness

    def test_secondary_missing_from_library_still_places_primary(self) -> None:
        # No "Spirals" in the catalog: the recipe degrades to the two-layer
        # form instead of failing.
        result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                        library_names=("Color Wash", "Shockwave", "On"))
        placements = result["06_PROP_Matrix"]
        assert [p.effect_name for p in placements].count("Shockwave") == len(_BEATS)
        assert all(p.effect_name != "Spirals" for p in placements)

    def test_other_recipes_have_no_secondary_layer(self) -> None:
        result = _place(_make_section(label="chorus"), _CANE_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Candy_Cane"]
        assert all(p.layer <= 1 for p in placements)


# ── mini-tree recipe ─────────────────────────────────────────────────────────


_MINITREE_GROUP = PowerGroup(
    name="06_PROP_Tree", tier=6, members=["Tree 1", "Tree 2", "Tree 3", "Tree 4"],
)


class TestMinitreeRecipe:
    def test_tree_group_name_matches(self) -> None:
        assert recipe_for_group(_MINITREE_GROUP).family == "minitree"

    def test_treestar_group_excluded(self) -> None:
        group = PowerGroup(
            name="06_PROP_TreeStar", tier=6, members=["TreeStar 1", "TreeStar 2"],
        )
        recipe = recipe_for_group(group)
        assert recipe is None or recipe.family != "minitree"

    def test_megatree_still_wins_over_minitree(self) -> None:
        group = PowerGroup(
            name="06_PROP_Mega_Tree", tier=6, members=["Mega Tree 1", "Mega Tree 2"],
        )
        assert recipe_for_group(group).family == "megatree"

    def test_singing_tree_member_majority_excluded(self) -> None:
        group = PowerGroup(
            name="06_PROP_Misc", tier=6,
            members=["Singing Tree Male", "Singing Tree Female"],
        )
        assert recipe_for_group(group) is None

    def test_spiral_tree_group_excluded_from_minitree(self) -> None:
        group = PowerGroup(
            name="06_PROP_Spiral_Tree", tier=6,
            members=["Spiral Tree 1", "Spiral Tree 2"],
        )
        recipe = recipe_for_group(group)
        assert recipe is not None
        assert recipe.family != "minitree"

    def test_second_theme_layer_mapped_to_tier_6_does_not_overwrite_mask(self) -> None:
        # Bug report: a generated sequence showed Fire painting over the
        # Shockwave/On-mask idiom on a Tree group. Root cause: any theme with
        # 3+ layers maps tier 6 to BOTH layer 0 and the middle layer(s)
        # (_assign_layers_to_tiers), so a second theme layer reaches this
        # group after the recipe already claimed it. Before the fix, that
        # second layer fell through to a rotation-plan/pool pick which
        # defaults to EffectPlacement.layer == 0 (nothing overrides it),
        # silently overwriting the recipe's own color-mask "On" layer.
        section = _make_section(label="chorus")
        layers = [
            EffectLayer(variant="Color Wash"),
            EffectLayer(variant="Ripple"),
            EffectLayer(variant="Spirals"),
        ]
        result = _place(
            section, _MINITREE_GROUP, layers=layers,
            library_names=_LIBRARY_WITH_ON + ("Ripple", "Spirals"),
            active_tiers=frozenset({1, 6}),
        )
        placements = result["06_PROP_Tree"]

        # The recipe's own On color-mask must be the ONLY thing on layer 0.
        # Before the fix, a fallback pick from the second tier-6-mapped
        # layer also defaulted to layer 0 (EffectPlacement.layer's default
        # — the fallback path never overrides it), silently sitting
        # alongside/overwriting the recipe's mask.
        layer0_names = {p.effect_name for p in placements if p.layer == 0}
        assert layer0_names == {"On"}


class TestSpiralTreeRecipe:
    """Spiral trees get their own recipe (family='spiraltree'), separate
    from ordinary mini trees, so their effects can be tuned independently
    once real-world rendering is evaluated -- see corpus_recipes.py's
    2026-07-21 comment above the recipe definition."""

    def test_spiral_tree_group_name_matches_spiraltree(self) -> None:
        group = PowerGroup(
            name="06_PROP_Spiral_Tree", tier=6,
            members=["Spiral Tree 1", "Spiral Tree 2"],
        )
        assert recipe_for_group(group).family == "spiraltree"

    def test_ordinary_tree_group_is_unaffected(self) -> None:
        assert recipe_for_group(_MINITREE_GROUP).family == "minitree"

    def test_megatree_still_wins_over_spiraltree(self) -> None:
        # "spiral" isn't a mega-tree token, so this just confirms the new
        # recipe's insertion point doesn't shadow the earlier megatree match.
        group = PowerGroup(
            name="06_PROP_Mega_Tree", tier=6, members=["Mega Tree 1", "Mega Tree 2"],
        )
        assert recipe_for_group(group).family == "megatree"

    def test_spiraltree_borrows_vertical_treatment_not_minitree(self) -> None:
        # The reference corpus has no spiral-tree family to mine, so per
        # explicit user direction this borrows "vertical"'s Single-Strand-led
        # treatment (shape match: a tall thin line) rather than mini-tree's
        # chase-across-the-whole-group preset.
        spiraltree = next(r for r in CORPUS_RECIPES if r.family == "spiraltree")
        vertical = next(r for r in CORPUS_RECIPES if r.family == "vertical")
        assert spiraltree.effect_name == vertical.effect_name == "Single Strand"
        assert spiraltree.alt_effect_name == vertical.alt_effect_name == "Lightning"
        assert spiraltree.parameter_overrides == vertical.parameter_overrides
        assert spiraltree.alt_parameter_overrides == vertical.alt_parameter_overrides
        assert spiraltree.direction_field == vertical.direction_field
        assert spiraltree.direction_ping_pong_values == vertical.direction_ping_pong_values
        assert spiraltree.direction_alt_value == vertical.direction_alt_value
        assert spiraltree.size_field == vertical.size_field
        assert spiraltree.size_values == vertical.size_values

    def test_minitree_chorus_gets_white_group_chase_per_beat(self) -> None:
        result = _place(_make_section(label="chorus"), _MINITREE_GROUP)
        placements = result["06_PROP_Tree"]
        assert len(placements) == len(_BEATS)
        for p in placements:
            assert p.effect_name == "Single Strand"
            assert p.color_palette == ["#FFFFFF"]
            assert p.parameters["E_CHOICE_Chase_Type1"] == "Right-Left"
            assert p.parameters["E_CHECKBOX_Chase_Group_All"] == "1"

    def test_minitree_alternate_is_shockwave_burst(self) -> None:
        result = _place(_make_section(label="chorus"), _MINITREE_GROUP, variation_seed=3)
        placements = result["06_PROP_Tree"]
        assert placements
        for p in placements:
            assert p.effect_name == "Shockwave"
            assert p.parameters["E_SLIDER_Shockwave_End_Radius"] == "100"
            assert "E_CHOICE_Chase_Type1" not in p.parameters

    def test_minitree_on_color_layer_over_chase_mask(self) -> None:
        result = _place(_make_section(label="chorus"), _MINITREE_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Tree"]
        ons = [p for p in placements if p.effect_name == "On"]
        masks = [p for p in placements if p.effect_name == "Single Strand"]
        assert len(ons) == 1
        assert ons[0].parameters["T_CHOICE_LayerMethod"] == "2 is Unmask"
        assert all(p.layer == 1 for p in masks)


# ── MusicSparkles on the color_over_mask "On" layer ──────────────────────────
# User request (2026-07-15), matching a real xLights clipboard paste of an
# On effect with C_CHECKBOX_MusicSparkles=1. Only horizontal/vertical/cane/
# minitree opted in (PropFamilyRecipe.mask_sparkles) -- megatree and matrix
# also use color_over_mask but weren't part of the request and must stay
# unaffected.


class TestMaskSparkles:
    def test_cane_on_layer_gets_sparkles(self) -> None:
        result = _place(_make_section(label="chorus", energy=80), _CANE_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        ons = [p for p in result["06_PROP_Candy_Cane"] if p.effect_name == "On"]
        assert ons
        assert all(p.music_sparkles > 0 for p in ons)

    def test_horizontal_and_vertical_on_layer_gets_sparkles(self) -> None:
        for group in (_HORIZONTAL_GROUP, _VERTICAL_GROUP):
            result = _place(_make_section(label="chorus", energy=80), group,
                            library_names=_LIBRARY_WITH_ON)
            ons = [p for p in result[group.name] if p.effect_name == "On"]
            assert ons
            assert all(p.music_sparkles > 0 for p in ons)

    def test_minitree_on_layer_gets_sparkles(self) -> None:
        result = _place(_make_section(label="chorus", energy=80), _MINITREE_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        ons = [p for p in result["06_PROP_Tree"] if p.effect_name == "On"]
        assert ons
        assert all(p.music_sparkles > 0 for p in ons)

    def test_megatree_on_layer_not_affected(self) -> None:
        # Also color_over_mask, but not part of the request -- must stay off.
        result = _place(_make_section(label="chorus", energy=80), _MEGATREE_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        ons = [p for p in result["06_PROP_Mega_Tree"] if p.effect_name == "On"]
        assert ons
        assert all(p.music_sparkles == 0 for p in ons)

    def test_matrix_on_layer_not_affected(self) -> None:
        result = _place(_make_section(label="chorus", energy=80), _MATRIX_GROUP,
                        library_names=_LIBRARY_WITH_ON + ("Pinwheel", "Lightning", "Ripple", "Spirals"))
        ons = [p for p in result["06_PROP_Matrix"] if p.effect_name == "On"]
        assert ons
        assert all(p.music_sparkles == 0 for p in ons)

    def test_sparkle_frequency_scales_with_energy(self) -> None:
        # Same deterministic formula as tier-1 BASE's unconditional sparkles:
        # 15 + round(energy_score * 0.5).
        low = _place(_make_section(label="chorus", energy=20), _CANE_GROUP,
                     library_names=_LIBRARY_WITH_ON)
        high = _place(_make_section(label="chorus", energy=100), _CANE_GROUP,
                      library_names=_LIBRARY_WITH_ON)
        low_on = [p for p in low["06_PROP_Candy_Cane"] if p.effect_name == "On"][0]
        high_on = [p for p in high["06_PROP_Candy_Cane"] if p.effect_name == "On"][0]
        assert low_on.music_sparkles == 15 + round(20 * 0.5)
        assert high_on.music_sparkles == 15 + round(100 * 0.5)


# ── Alternating Flip Horizontal buffer transform ─────────────────────────────
# User request (2026-07-15), matching a real xLights clipboard paste of a
# Spirals effect with B_CHOICE_BufferTransform="Flip Horizontal". Scoped to
# effect name (Spirals, Single Strand), not prop family -- applies to
# whichever recipe places one of these at the normal 1-beat-per-segment
# stride. Only the 2nd/4th placement of each 4-beat bar flips (odd
# instance_index); the sparse "alt style" 4-beat-per-segment pacing has only
# one placement per bar, so it never qualifies.


class TestFlipTransformAlternation:
    def test_cane_single_strand_flips_every_other_beat(self) -> None:
        # variation_seed=0: primary Single Strand, normal 1-beat stride.
        result = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=0)
        placements = result["06_PROP_Candy_Cane"]
        assert len(placements) == len(_BEATS)
        for i, p in enumerate(placements):
            if i % 2 == 1:
                assert p.parameters["B_CHOICE_BufferTransform"] == "Flip Horizontal"
            else:
                assert "B_CHOICE_BufferTransform" not in p.parameters

    def test_cane_spirals_alt_flips_every_other_beat(self) -> None:
        # variation_seed=3: alt effect (Spirals) selected, still normal
        # 1-beat stride (use_alt_style/sparse pacing only applies to the
        # primary effect's own bounce style, not the alt effect).
        result = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=3)
        placements = result["06_PROP_Candy_Cane"]
        assert placements
        assert all(p.effect_name == "Spirals" for p in placements)
        for i, p in enumerate(placements):
            if i % 2 == 1:
                assert p.parameters["B_CHOICE_BufferTransform"] == "Flip Horizontal"
            else:
                assert "B_CHOICE_BufferTransform" not in p.parameters

    def test_cane_sparse_bounce_pacing_never_flips(self) -> None:
        # variation_seed=1: primary effect's bounce style -- sparse 4-beat
        # pacing means only one segment per bar, so there's no "2nd/4th of
        # the bar" and the transform must never appear.
        result = _place(_make_section(label="chorus"), _CANE_GROUP, variation_seed=1)
        placements = result["06_PROP_Candy_Cane"]
        assert placements
        assert all("B_CHOICE_BufferTransform" not in p.parameters for p in placements)

    def test_star_single_strand_flips_every_other_beat(self) -> None:
        # Matches TestStarRecipe.test_repeated_section_alternates_to_chase's
        # setup: chorus + variation_seed=3 selects the alt effect (Single
        # Strand) at the normal 1-beat stride.
        result = _place(_make_section(label="chorus"), _STAR_GROUP,
                        variation_seed=3, library_names=_LIBRARY_STAR)
        chase_placements = [p for p in result["06_PROP_Star"] if p.effect_name == "Single Strand"]
        assert chase_placements
        for i, p in enumerate(chase_placements):
            if i % 2 == 1:
                assert p.parameters["B_CHOICE_BufferTransform"] == "Flip Horizontal"
            else:
                assert "B_CHOICE_BufferTransform" not in p.parameters

    def test_snowflake_shockwave_not_affected(self) -> None:
        # Shockwave is not in the flip scope (effect-name-scoped, not
        # family-scoped) -- snowflake's primary effect must stay untouched.
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP)
        placements = result["06_PROP_Snowflake"]
        assert placements
        assert all("B_CHOICE_BufferTransform" not in p.parameters for p in placements)


# ── vivid unmask color selection ─────────────────────────────────────────────


class TestVividMaskColor:
    def test_saturated_palette_color_wins_and_is_vivified(self) -> None:
        from src.generator.effect_placer import _vivid_mask_color
        # Muted olive (#63A600 ≈ s=1.0 v=0.65) keeps its hue, gains value.
        color = _vivid_mask_color(["#63A600", "#FFFFFF"], 0)
        assert color != "#63A600"
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        assert max(r, g, b) >= 242  # value pushed to >= 0.95

    def test_white_skipped_for_first_saturated(self) -> None:
        from src.generator.effect_placer import _vivid_mask_color
        assert _vivid_mask_color(["#FFFFFF", "#FF0000", "#00FF00", "#0000FF"], 0) == "#FF0000"

    def test_all_white_palette_falls_back_to_primary_rotation(self) -> None:
        from src.generator.effect_placer import (
            _CORPUS_MASK_PRIMARIES, _vivid_mask_color,
        )
        assert _vivid_mask_color(["#FFFFFF", "#EEEEEE"], 0) == _CORPUS_MASK_PRIMARIES[0]
        assert _vivid_mask_color(["#FFFFFF"], 3) == _CORPUS_MASK_PRIMARIES[3]

    def test_groups_spread_across_palette_colors(self) -> None:
        from src.generator.effect_placer import _vivid_mask_color
        palette = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]
        groups = [
            "06_PROP_Cane", "06_PROP_Tree", "06_PROP_Matrix",
            "06_PROP_Snowflake", "06_PROP_Horizontal_Lines",
            "06_PROP_Vertical_Lines", "08_HERO_Mega_Tree",
        ]
        colors = {g: _vivid_mask_color(palette, 0, g) for g in groups}
        # Different families land on different colors in the same section.
        assert len(set(colors.values())) >= 3

    def test_same_group_varies_across_sections(self) -> None:
        from src.generator.effect_placer import _vivid_mask_color
        palette = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]
        colors = {
            _vivid_mask_color(palette, seed, "06_PROP_Cane") for seed in range(4)
        }
        assert len(colors) == 4

    def test_deterministic_per_group_and_seed(self) -> None:
        from src.generator.effect_placer import _vivid_mask_color
        palette = ["#FF0000", "#00FF00", "#0000FF"]
        a = _vivid_mask_color(palette, 2, "06_PROP_Cane")
        b = _vivid_mask_color(palette, 2, "06_PROP_Cane")
        assert a == b

    def test_recipe_on_layer_is_never_white(self) -> None:
        # Even a white-heavy section palette must not produce a white unmask.
        result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        ons = [p for p in result["06_PROP_Matrix"] if p.effect_name == "On"]
        assert ons and ons[0].color_palette[0].upper() != "#FFFFFF"

    def test_single_hue_accent_never_borrows_an_off_theme_primary(self) -> None:
        # Bug-419: Festive Flash's accent_palette (gold/orange/green/dark-green)
        # collapses to a single distinct hue bucket after hue-separation dedup
        # (gold and orange are 11 degrees apart; the two greens are identical
        # hue) -- this used to trip the old "< 3 candidates" fallback and mix
        # in unrelated corpus primaries (blue/cyan/magenta) on a Christmas
        # theme's mask layer. Every rotation entry must stay within the
        # palette's own hue family now.
        from src.generator.effect_placer import _hue_distance_deg, _vivid_mask_color
        import colorsys
        palette = ["#FFD700", "#FFAA00", "#00CC00", "#009900"]
        own_hues = [50.6, 40.0, 120.0]  # gold, orange, green (both greens)
        for seed in range(12):
            color = _vivid_mask_color(palette, seed, "06_PROP_Horizontal_Lines", offset=seed)
            c = color.lstrip("#")
            r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            hue, sat, _ = colorsys.rgb_to_hsv(r, g, b)
            if sat < 0.05:
                continue  # near-white/gray variants carry no meaningful hue
            assert any(_hue_distance_deg(hue * 360.0, h) < 25.0 for h in own_hues), (
                f"{color} is not within any of the theme's own hues {own_hues}"
            )

    def test_two_hue_accent_still_rotates_without_off_theme_primaries(self) -> None:
        # A 2-distinct-hue accent_palette (e.g. Haunted Pulse) should rotate
        # between its own two hues plus in-hue variants, never a corpus
        # primary from an unrelated hue family.
        from src.generator.effect_placer import _hue_distance_deg, _vivid_mask_color
        import colorsys
        palette = ["#00FF44", "#44FF00"]  # both acid-green, ~100-135 deg
        own_hues = [100.0, 135.0]
        for seed in range(12):
            color = _vivid_mask_color(palette, seed, "06_PROP_Vertical_Lines", offset=seed)
            c = color.lstrip("#")
            r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            hue, sat, _ = colorsys.rgb_to_hsv(r, g, b)
            if sat < 0.05:
                continue
            assert any(_hue_distance_deg(hue * 360.0, h) < 25.0 for h in own_hues), (
                f"{color} is not within any of the theme's own hues {own_hues}"
            )


# ── placement progress callback ──────────────────────────────────────────────


class TestPlacementProgressCallback:
    def test_prop_groups_announced_once_with_human_names(self) -> None:
        from src.generator.effect_placer import _humanize_group_name

        assert _humanize_group_name("06_PROP_Mega_Tree") == "Mega Tree"
        assert _humanize_group_name("08_HERO_Mega_Tree") == "Mega Tree"
        assert _humanize_group_name("06_PROP_Snowflake") == "Snowflake"

        messages: list[str] = []
        layers = [EffectLayer(variant="Color Wash")]
        library = _make_library(*_DEFAULT_LIBRARY_NAMES)
        variant_library = _make_variant_library(*_DEFAULT_LIBRARY_NAMES)
        assignment = _make_assignment(_make_section(label="chorus"), layers)
        place_effects(
            assignment, [_SNOWFLAKE_GROUP, _ARCH_GROUP], library,
            _make_hierarchy(_BEATS),
            variant_library=variant_library,
            progress_cb=messages.append,
        )
        assert "placing Snowflake" in messages
        assert "placing Arch" in messages
        assert len(messages) == len(set(messages)), "groups must be announced once"

    def test_no_callback_is_silent_default(self) -> None:
        # Smoke: omitting progress_cb keeps the original behavior.
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP)
        assert result["06_PROP_Snowflake"]


# ── tier-8 HERO wiring (solo mega tree) ──────────────────────────────────────


_HERO_MEGATREE_GROUP = PowerGroup(
    name="08_HERO_Mega_Tree", tier=8, members=["Mega Tree"],
)


class TestHeroRecipePlacement:
    def test_hero_megatree_chorus_gets_white_shockwave_per_beat(self) -> None:
        result = _place(_make_section(label="chorus"), _HERO_MEGATREE_GROUP,
                        active_tiers=frozenset({8}))
        placements = result["08_HERO_Mega_Tree"]
        assert len(placements) == len(_BEATS)
        assert all(p.effect_name == "Shockwave" for p in placements)
        assert all(p.color_palette == ["#FFFFFF"] for p in placements)

    def test_hero_megatree_alternate_is_spirals_with_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _HERO_MEGATREE_GROUP,
                        variation_seed=3, active_tiers=frozenset({8}))
        placements = result["08_HERO_Mega_Tree"]
        assert placements
        for p in placements:
            assert p.effect_name == "Spirals"
            assert p.parameters["E_SLIDER_Spirals_Count"] == "1"

    def test_hero_megatree_low_energy_verse_keeps_normal_placement(self) -> None:
        result = _place(_make_section(label="verse", energy=40),
                        _HERO_MEGATREE_GROUP, active_tiers=frozenset({8}))
        placements = result.get("08_HERO_Mega_Tree", [])
        # The hero still gets its normal theme placement, not the recipe stack.
        assert placements
        assert not all(
            p.effect_name == "Shockwave" and p.color_palette == ["#FFFFFF"]
            for p in placements
        )

    def test_hero_non_recipe_prop_unaffected(self) -> None:
        hero = PowerGroup(name="08_HERO_Wreath", tier=8, members=["Wreath"])
        result = _place(_make_section(label="chorus"), hero,
                        active_tiers=frozenset({8}))
        placements = result.get("08_HERO_Wreath", [])
        assert placements
        assert not all(p.color_palette == ["#FFFFFF"] for p in placements)


# ── Off backdrop (layer beneath the bursts) ──────────────────────────────────


_LIBRARY_WITH_OFF = _DEFAULT_LIBRARY_NAMES + ("Off",)


class TestOffBackdrop:
    def test_snowflake_recipe_adds_section_spanning_off_on_layer_1(self) -> None:
        section = _make_section(label="chorus")
        result = _place(section, _SNOWFLAKE_GROUP, library_names=_LIBRARY_WITH_OFF)
        placements = result["06_PROP_Snowflake"]
        offs = [p for p in placements if p.effect_name == "Off"]
        assert len(offs) == 1
        assert offs[0].layer == 1
        assert offs[0].start_ms == section.start_ms
        assert offs[0].end_ms == section.end_ms
        # The bursts stay on the top layer, one per beat, unchanged.
        bursts = [p for p in placements if p.effect_name == "Shockwave"]
        assert len(bursts) == len(_BEATS)
        assert all(p.layer == 0 for p in bursts)

    def test_arch_recipe_adds_off_backdrop(self) -> None:
        result = _place(_make_section(label="chorus"), _ARCH_GROUP,
                        library_names=_LIBRARY_WITH_OFF)
        offs = [p for p in result["06_PROP_Arch"] if p.effect_name == "Off"]
        assert len(offs) == 1
        assert offs[0].layer == 1

    def test_megatree_recipe_has_no_off_backdrop(self) -> None:
        # Off backdrop is not part of the mined megatree idiom.
        result = _place(_make_section(label="chorus"), _MEGATREE_GROUP,
                        library_names=_LIBRARY_WITH_OFF)
        offs = [p for p in result["06_PROP_Mega_Tree"] if p.effect_name == "Off"]
        assert offs == []

    def test_minitree_recipe_adds_off_backdrop(self) -> None:
        # User request 2026-07-22: match horizontal/vertical/spiraltree —
        # an Off backdrop beneath the On-mask + motion stack instead of
        # picking up whole-house bleed.
        result = _place(_make_section(label="chorus"), _MINITREE_GROUP,
                        library_names=_LIBRARY_WITH_OFF + ("On",))
        offs = [p for p in result["06_PROP_Tree"] if p.effect_name == "Off"]
        assert len(offs) == 1
        # Beneath both the On-mask (layer 0) and motion (layer 1) layers.
        assert offs[0].layer == 2

    def test_star_recipe_adds_off_backdrop(self) -> None:
        star_group = PowerGroup(
            name="06_PROP_Star", tier=6, members=["Star 1", "Star 2"],
        )
        result = _place(_make_section(label="chorus"), star_group,
                        library_names=_LIBRARY_WITH_OFF + ("On",))
        offs = [p for p in result["06_PROP_Star"] if p.effect_name == "Off"]
        assert len(offs) == 1
        assert offs[0].layer == 2

    def test_off_missing_from_library_skips_backdrop(self) -> None:
        # A catalog without "Off" must not break the recipe placement.
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP)
        placements = result["06_PROP_Snowflake"]
        assert len(placements) == len(_BEATS)
        assert all(p.effect_name == "Shockwave" for p in placements)

    def test_multi_layer_theme_adds_single_off_backdrop(self) -> None:
        layers = [
            EffectLayer(variant="Color Wash"),
            EffectLayer(variant="Ripple"),
        ]
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP,
                        layers=layers, library_names=_LIBRARY_WITH_OFF)
        offs = [p for p in result["06_PROP_Snowflake"] if p.effect_name == "Off"]
        assert len(offs) == 1

    def test_multi_layer_theme_places_recipe_once(self) -> None:
        # 3-layer theme: layers 0 and 1 both map to tier 6 — the recipe must
        # fire once, not stack duplicate per-beat placements.
        layers = [
            EffectLayer(variant="Color Wash"),
            EffectLayer(variant="Ripple"),
            EffectLayer(variant="Color Wash"),
        ]
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, layers=layers)
        recipe_placements = [
            p for p in result.get("06_PROP_Snowflake", [])
            if p.color_palette == ["#FFFFFF"]
        ]
        assert len(recipe_placements) == len(_BEATS)


# ── icicle recipe ─────────────────────────────────────────────────────────────


_ICICLE_GROUP = PowerGroup(
    name="06_PROP_Icicles", tier=6, members=["Icicles 1", "Icicles 2"],
)
_LIBRARY_ICICLE = ("Color Wash", "Spirals", "Meteors", "On", "Shockwave",
                   "Ripple", "Single Strand")


class TestIcicleRecipe:
    def test_icicle_group_name_matches(self) -> None:
        assert recipe_for_group(_ICICLE_GROUP).family == "icicle"

    def test_outline_combo_group_does_not_match(self) -> None:
        g = PowerGroup(name="06_PROP_Outline_Icicles", tier=6,
                       members=["House Outline + Icicles"])
        assert recipe_for_group(g) is None

    def test_member_majority_matches(self) -> None:
        g = PowerGroup(name="06_PROP_Roof", tier=6,
                       members=["Icicles 1", "Icicles 2", "Gutter"])
        assert recipe_for_group(g).family == "icicle"

    def test_chorus_gets_two_beat_spirals_segments(self) -> None:
        # 8 beats at 500ms -> 4 two-beat segments of 1000ms each.
        section = _make_section(label="chorus")
        result = _place(section, _ICICLE_GROUP, library_names=_LIBRARY_ICICLE)
        placements = result["06_PROP_Icicles"]
        spirals = sorted(
            (p for p in placements if p.effect_name == "Spirals"),
            key=lambda p: p.start_ms,
        )
        assert len(spirals) == 4
        assert [p.start_ms for p in spirals] == [0, 1000, 2000, 3000]
        assert all(p.end_ms - p.start_ms == 1000 for p in spirals[:-1])
        params = dict(spirals[0].parameters)
        assert params["E_CHECKBOX_Spirals_3D"] == "1"
        assert params["E_SLIDER_Spirals_Thickness"] == "33"
        assert params["E_TEXTCTRL_Spirals_Movement"] == "1"

    def test_on_layer_cycles_per_bar(self) -> None:
        section = _make_section(label="chorus")
        result = _place(section, _ICICLE_GROUP, library_names=_LIBRARY_ICICLE)
        ons = sorted(
            (p for p in result["06_PROP_Icicles"] if p.effect_name == "On"),
            key=lambda p: p.start_ms,
        )
        assert len(ons) == 2  # 8 beats = 2 bars
        assert all(p.parameters["T_CHOICE_LayerMethod"] == "2 is Unmask" for p in ons)
        assert ons[0].color_palette != ons[1].color_palette

    def test_repeated_section_alternates_to_meteors_down(self) -> None:
        result = _place(_make_section(label="chorus"), _ICICLE_GROUP,
                        variation_seed=3, library_names=_LIBRARY_ICICLE)
        placements = result["06_PROP_Icicles"]
        meteors = [p for p in placements if p.effect_name == "Meteors"]
        assert len(meteors) == 4
        params = dict(meteors[0].parameters)
        assert params["E_CHOICE_Meteors_Effect"] == "Down"
        assert params["E_SLIDER_Meteors_Count"] == "28"
        assert params["E_CHECKBOX_Meteors_UseMusic"] == "0"

    def test_low_energy_verse_keeps_normal_placement(self) -> None:
        result = _place(_make_section(label="verse", energy=40), _ICICLE_GROUP,
                        library_names=_LIBRARY_ICICLE)
        placements = result.get("06_PROP_Icicles", [])
        assert not any(p.effect_name == "Spirals" and
                       dict(p.parameters).get("E_SLIDER_Spirals_Thickness") == "33"
                       for p in placements)


# ── mega-topper recipe ────────────────────────────────────────────────────────


_TOPPER_GROUP = PowerGroup(
    name="08_HERO_Mega_Topper", tier=8, members=["Mega Topper"],
)
_LIBRARY_TOPPER = ("Color Wash", "Shockwave", "On", "Off", "Ripple",
                   "Single Strand", "Spirals")


class TestMegaTopperRecipe:
    def test_hero_topper_matches(self) -> None:
        assert recipe_for_group(_TOPPER_GROUP).family == "megatopper"

    def test_megatree_group_does_not_match_megatopper(self) -> None:
        assert recipe_for_group(_MEGATREE_GROUP).family == "megatree"

    def test_chorus_stack_bursts_on_color_and_off_backdrop(self) -> None:
        section = _make_section(label="chorus")
        result = _place(section, _TOPPER_GROUP, library_names=_LIBRARY_TOPPER,
                        active_tiers=frozenset({1, 8}))
        placements = result["08_HERO_Mega_Topper"]
        bursts = [p for p in placements if p.effect_name == "Shockwave"]
        assert len(bursts) == len(_BEATS)  # no volley: per-beat like the corpus
        assert all(p.layer == 1 for p in bursts)
        params = dict(bursts[0].parameters)
        assert params["E_SLIDER_Shockwave_End_Radius"] == "100"  # prop-scale burst
        ons = sorted((p for p in placements if p.effect_name == "On"),
                     key=lambda p: p.start_ms)
        assert len(ons) == 2  # bar-cycling color
        assert ons[0].color_palette != ons[1].color_palette
        offs = [p for p in placements if p.effect_name == "Off"]
        assert len(offs) == 1
        assert offs[0].layer == 2
        assert offs[0].start_ms == section.start_ms
        assert offs[0].end_ms == section.end_ms

    def test_no_alternate_on_repeated_sections(self) -> None:
        # The topper deliberately has no alt effect: it stays on Shockwave
        # while the megatree recipe alternates to Spirals, reproducing the
        # corpus's dominant Shockwave-over-Spirals pairing.
        result = _place(_make_section(label="chorus"), _TOPPER_GROUP,
                        variation_seed=3, library_names=_LIBRARY_TOPPER,
                        active_tiers=frozenset({1, 8}))
        placements = result["08_HERO_Mega_Topper"]
        bursts = [p for p in placements if p.effect_name == "Shockwave"]
        assert len(bursts) == len(_BEATS)


# ── star recipe ───────────────────────────────────────────────────────────────


_STAR_GROUP = PowerGroup(
    name="06_PROP_Star", tier=6,
    members=["Star 1", "Star 2", "Star 3", "Star 4"], prop_type="radial",
)
_LIBRARY_STAR = ("Color Wash", "Shockwave", "On", "Ripple",
                 "Single Strand", "Spirals")


class TestStarRecipe:
    def test_star_group_matches_despite_radial_prop_type(self) -> None:
        # Whole-prop star groups classify as radial but are not subModel
        # chase groups — they must reach the star recipe.
        assert recipe_for_group(_STAR_GROUP).family == "star"

    def test_treestar_group_matches_star_not_minitree(self) -> None:
        g = PowerGroup(name="06_PROP_TreeStar", tier=6,
                       members=["TreeStar 1", "TreeStar 2"], prop_type="radial")
        assert recipe_for_group(g).family == "star"

    def test_arch_star_group_matches_star_not_arch(self) -> None:
        g = PowerGroup(name="06_PROP_Arch_Star", tier=6,
                       members=["Arch Star 1", "Arch Star 2"])
        assert recipe_for_group(g).family == "star"

    def test_starburst_excluded(self) -> None:
        g = PowerGroup(name="06_PROP_Starburst", tier=6,
                       members=["Starburst_6ft_8_Point A", "Starburst_6ft_8_Point B"])
        assert recipe_for_group(g) is None

    def test_ring_submodel_group_still_blocked(self) -> None:
        g = PowerGroup(name="06_PROP_Star_Rings", tier=6,
                       members=["Star 1/Ring 1", "Star 1/Ring 2"],
                       prop_type="radial")
        assert recipe_for_group(g) is None

    def test_chorus_gets_simultaneous_pops_with_cycling_color(self) -> None:
        section = _make_section(label="chorus")
        result = _place(section, _STAR_GROUP, library_names=_LIBRARY_STAR)
        placements = result["06_PROP_Star"]
        pops = [p for p in placements if p.effect_name == "Shockwave"]
        assert len(pops) == len(_BEATS)
        params = dict(pops[0].parameters)
        assert params["E_SLIDER_Shockwave_End_Radius"] == "100"
        ons = sorted((p for p in placements if p.effect_name == "On"),
                     key=lambda p: p.start_ms)
        assert len(ons) == 2
        assert ons[0].color_palette != ons[1].color_palette

    def test_repeated_section_alternates_to_chase(self) -> None:
        result = _place(_make_section(label="chorus"), _STAR_GROUP,
                        variation_seed=3, library_names=_LIBRARY_STAR)
        placements = result["06_PROP_Star"]
        chases = [p for p in placements if p.effect_name == "Single Strand"]
        assert len(chases) == len(_BEATS)
        assert dict(chases[0].parameters)["E_CHOICE_Fade_Type"] == "From Head"

    def test_verse_falls_back_to_radial_chase(self) -> None:
        # Non-qualifying sections keep the existing radial chase-across-
        # members behavior (placements land on individual member models).
        result = _place(_make_section(label="verse", energy=40), _STAR_GROUP,
                        library_names=_LIBRARY_STAR)
        assert "06_PROP_Star" not in result or not any(
            p.effect_name == "Shockwave" and
            dict(p.parameters).get("E_SLIDER_Shockwave_End_Radius") == "100"
            for p in result.get("06_PROP_Star", [])
        )

    def test_tree_and_topper_heroes_place_together(self) -> None:
        # The hero spotlight rotation must not solo one of a corpus-paired
        # hero couple: the reference packages run the topper co-active with
        # the tree.
        tree = PowerGroup(name="08_HERO_Mega_Tree", tier=8, members=["Mega Tree"])
        topper = PowerGroup(name="08_HERO_Mega_Topper", tier=8,
                            members=["Mega Topper"])
        library = _make_library(*_LIBRARY_TOPPER)
        variant_library = _make_variant_library(*_LIBRARY_TOPPER)
        assignment = _make_assignment(
            _make_section(label="chorus"), [EffectLayer(variant="Color Wash")],
            active_tiers=frozenset({8}),
        )
        result = place_effects(
            assignment, [tree, topper], library, _make_hierarchy(_BEATS),
            variant_library=variant_library,
        )
        assert "08_HERO_Mega_Tree" in result
        assert "08_HERO_Mega_Topper" in result


# ── matrix motion rotation ────────────────────────────────────────────────────


_MATRIX_GROUP = PowerGroup(
    name="06_PROP_Matrix", tier=6, members=["Matrix 1", "Matrix 2"],
    prop_type="matrix",
)
_LIBRARY_MATRIX = ("Color Wash", "Shockwave", "Pinwheel", "Lightning",
                   "Ripple", "Spirals", "On", "Single Strand")


class TestMatrixMotionRotation:
    def _motion_effects(self, seed: int, library=_LIBRARY_MATRIX, hierarchy=None) -> set[str]:
        result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                        variation_seed=seed, library_names=library, hierarchy=hierarchy)
        return {
            p.effect_name for p in result.get("06_PROP_Matrix", [])
            if p.effect_name not in ("On", "Spirals")
        }

    def test_rotation_walks_the_fourteen_slot_pool(self) -> None:
        # Seed fallback path: seed s -> slot (s // 2) % 14. The pool
        # interleaves Shockwave/Pinwheel/Ripple/Color Wash/Shape/VU Meter
        # preset variants; Lightning was moved to the crash-accent pass
        # (2026-07-18); Color Wash + Shape + VU Meter added 2026-07-23.
        # VU Meter slots need both the effect in the library AND their
        # mapped timing track populated on the hierarchy, else they fall
        # back to the primary Shockwave.
        full_lib = _LIBRARY_MATRIX + ("Shape", "VU Meter")
        full_hierarchy = _make_full_hierarchy(_BEATS)
        assert self._motion_effects(0) == {"Shockwave"}
        assert self._motion_effects(2) == {"Pinwheel"}
        assert self._motion_effects(4) == {"Ripple"}
        assert self._motion_effects(6) == {"Color Wash"}
        assert self._motion_effects(8) == {"Shockwave"}
        assert self._motion_effects(10) == {"Pinwheel"}
        assert self._motion_effects(12, library=full_lib) == {"Shape"}
        assert self._motion_effects(14, library=full_lib, hierarchy=full_hierarchy) == {"VU Meter"}
        assert self._motion_effects(16) == {"Ripple"}
        assert self._motion_effects(18) == {"Shockwave"}
        assert self._motion_effects(20, library=full_lib) == {"Shape"}
        assert self._motion_effects(22, library=full_lib, hierarchy=full_hierarchy) == {"VU Meter"}
        assert self._motion_effects(24, library=full_lib, hierarchy=full_hierarchy) == {"VU Meter"}
        assert self._motion_effects(26, library=full_lib, hierarchy=full_hierarchy) == {"VU Meter"}
        assert self._motion_effects(28) == {"Shockwave"}  # cycle repeats

    def test_vu_meter_slot_falls_back_without_its_mapped_track(self) -> None:
        # Slot 7 (occurrence 7, seed 14) is VU Meter mapped to Kick Hits.
        # Without kick_hits populated on the hierarchy, it must fall back
        # to the primary Shockwave rather than silently placing nothing.
        full_lib = _LIBRARY_MATRIX + ("VU Meter",)
        assert self._motion_effects(14, library=full_lib) == {"Shockwave"}

    def test_shockwave_slots_carry_distinct_mined_presets(self) -> None:
        # Slots 0/4/9 are all Shockwave but different mined reaches.
        radii = []
        for seed in (0, 8, 18):
            result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                            variation_seed=seed, library_names=_LIBRARY_MATRIX)
            bursts = [p for p in result["06_PROP_Matrix"]
                      if p.effect_name == "Shockwave"]
            assert bursts
            radii.append(dict(bursts[0].parameters)["E_SLIDER_Shockwave_End_Radius"])
        assert radii == ["100", "100", "50"]
        widths = []
        for seed in (0, 8):
            result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                            variation_seed=seed, library_names=_LIBRARY_MATRIX)
            bursts = [p for p in result["06_PROP_Matrix"]
                      if p.effect_name == "Shockwave"]
            widths.append(dict(bursts[0].parameters)["E_SLIDER_Shockwave_End_Width"])
        assert widths == ["35", "62"]

    def test_ripple_slot_carries_implode_preset(self) -> None:
        result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                        variation_seed=4, library_names=_LIBRARY_MATRIX)
        ripples = [p for p in result["06_PROP_Matrix"]
                   if p.effect_name == "Ripple"]
        assert ripples
        params = dict(ripples[0].parameters)
        assert params["E_CHOICE_Ripple_Movement"] == "Implode"
        assert params["E_TEXTCTRL_Ripple_Cycles"] == "0.2"
        assert params["E_SLIDER_Ripple_Thickness"] == "12"

    def test_lightning_not_in_section_rotation(self) -> None:
        # Lightning rides the crash-accent pass now, never the per-section
        # rotation — even with Lightning present in the catalog.
        for seed in range(0, 16, 2):
            assert "Lightning" not in self._motion_effects(seed)

    def test_missing_rotation_effect_falls_back_to_primary_pair(self) -> None:
        # A catalog missing a rotation slot's effect must not break the slot —
        # the primary/alt pair takes over (seed 4 -> halved parity 0 -> primary).
        library = tuple(n for n in _LIBRARY_MATRIX if n != "Ripple")
        assert self._motion_effects(4, library=library) == {"Shockwave"}

    def test_sustained_spirals_layer_survives_rotation(self) -> None:
        result = _place(_make_section(label="chorus"), _MATRIX_GROUP,
                        variation_seed=4, library_names=_LIBRARY_MATRIX)
        spirals = [p for p in result["06_PROP_Matrix"]
                   if p.effect_name == "Spirals"]
        assert spirals
        # seed 4 -> secondary pool slot (4 // 2) % 5 = 2, the fast tight
        # flat spiral.
        params = dict(spirals[0].parameters)
        assert params["E_SLIDER_Spirals_Rotation"] == "-100"
        assert params["E_SLIDER_Spirals_Thickness"] == "20"

    def test_families_without_rotation_unchanged(self) -> None:
        # Snowflakes keep the two-effect alternation: seed 4 halves to
        # parity 0 -> primary Shockwave (not a third look).
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP,
                        variation_seed=4)
        placements = result["06_PROP_Snowflake"]
        assert all(p.effect_name == "Shockwave" for p in placements)
