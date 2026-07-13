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


def _make_assignment(section: SectionEnergy, layers: list[EffectLayer],
                     variation_seed: int = 0,
                     active_tiers: frozenset[int] = frozenset({1, 6})) -> SectionAssignment:
    theme = Theme(
        name="Test Theme", mood="structural", occasion="general", genre="any",
        intent="test", layers=layers, palette=["#ff0000", "#00ff00"],
    )
    return SectionAssignment(
        section=section, theme=theme,
        active_tiers=active_tiers,
        variation_seed=variation_seed,
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

_BEATS = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500]

_DEFAULT_LIBRARY_NAMES = ("Color Wash", "Shockwave", "Ripple", "Single Strand", "Spirals")


def _place(section: SectionEnergy, group: PowerGroup,
           variation_seed: int = 0,
           layers: list[EffectLayer] | None = None,
           hierarchy: HierarchyResult | None = None,
           library_names: tuple[str, ...] = _DEFAULT_LIBRARY_NAMES,
           active_tiers: frozenset[int] = frozenset({1, 6})):
    layers = layers or [EffectLayer(variant="Color Wash")]
    library = _make_library(*library_names)
    variant_library = _make_variant_library(*library_names)
    assignment = _make_assignment(section, layers, variation_seed=variation_seed,
                                  active_tiers=active_tiers)
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
        g = PowerGroup(name="06_PROP_CandyCane", tier=6, members=["Cane 1", "Cane 2"])
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

    def test_mega_topper_does_not_match_megatree(self) -> None:
        g = PowerGroup(name="06_PROP_Mega_Topper", tier=6,
                       members=["Mega Topper 1", "Mega Topper 2"])
        assert recipe_for_group(g) is None

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

    def test_repeated_section_alternates_to_ripple(self) -> None:
        # variation_seed is the global section index; the recipe halves it
        # before taking parity so verse/chorus alternation still cycles both
        # effects. Seeds 0-1 -> Shockwave, 2-3 -> Ripple.
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, variation_seed=3)
        placements = result["06_PROP_Snowflake"]
        assert placements
        assert all(p.effect_name == "Ripple" for p in placements)

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

    def test_alternate_effect_does_not_inherit_primary_preset(self) -> None:
        # Ripple must not receive Shockwave parameter overrides.
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP, variation_seed=3)
        placements = result["06_PROP_Snowflake"]
        assert placements
        for p in placements:
            assert p.effect_name == "Ripple"
            assert "E_SLIDER_Shockwave_End_Radius" not in p.parameters

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
        section = _make_section(label="chorus")
        result = _place(section, _MEGATREE_GROUP, library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Mega_Tree"]

        color_layers = [p for p in placements if p.effect_name == "On"]
        masks = [p for p in placements if p.effect_name == "Shockwave"]
        assert len(color_layers) == 1
        assert len(masks) == len(_BEATS)

        on = color_layers[0]
        # On sits on the top layer, spans the section, and carries the mined
        # Unmask blend so the mask below only contributes shape/brightness.
        assert on.layer == 0
        assert on.start_ms == section.start_ms
        assert on.end_ms == section.end_ms
        assert on.parameters["T_CHOICE_LayerMethod"] == "2 is Unmask"
        # Color comes from the section theme (one solid color), not white.
        assert len(on.color_palette) == 1

        # Masks move to layer 1, stay white (shape only).
        assert all(p.layer == 1 for p in masks)
        assert all(p.color_palette == ["#FFFFFF"] for p in masks)

    def test_spirals_alternate_also_gets_color_layer(self) -> None:
        result = _place(_make_section(label="chorus"), _MEGATREE_GROUP,
                        variation_seed=3, library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Mega_Tree"]
        assert [p.effect_name for p in placements].count("On") == 1
        masks = [p for p in placements if p.effect_name == "Spirals"]
        assert masks
        assert all(p.layer == 1 for p in masks)

    def test_snowflake_recipe_not_affected_by_on_in_library(self) -> None:
        # color_over_mask is megatree-only; snowflakes stay single-layer
        # bursts (plus their Off backdrop when Off exists).
        result = _place(_make_section(label="chorus"), _SNOWFLAKE_GROUP,
                        library_names=_LIBRARY_WITH_ON)
        placements = result["06_PROP_Snowflake"]
        assert all(p.effect_name != "On" for p in placements)
        assert all(p.layer == 0 for p in placements)


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

    def test_hero_non_megatree_unaffected(self) -> None:
        hero = PowerGroup(name="08_HERO_Matrix", tier=8, members=["Matrix"])
        result = _place(_make_section(label="chorus"), hero,
                        active_tiers=frozenset({8}))
        placements = result.get("08_HERO_Matrix", [])
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
