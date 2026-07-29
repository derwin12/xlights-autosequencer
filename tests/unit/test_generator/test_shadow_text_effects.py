"""Tests for the Shadow Text word effect: two-layer Text placement on
user-tagged words, targeting the same Matrix/Mega Tree props as Pictures."""
from __future__ import annotations

from src.generator.effect_placer import (
    _SHADOW_TEXT_MATRIX_SUBBUFFER,
    _SHADOW_TEXT_MIN_BURST_MS,
    _SHADOW_TEXT_TREE_SUBBUFFER,
    _place_shadow_text_effects,
)
from src.grouper.grouper import PowerGroup


def _prop(name: str, display_as: str):
    return type("FakeProp", (), {"name": name, "display_as": display_as})()


def _group(name: str, members: list[str], tier: int = 6) -> PowerGroup:
    return PowerGroup(name=name, tier=tier, members=members)


def _word(label: str, start_ms: int, duration_ms: int = 400) -> dict:
    return {"label": label, "start_ms": start_ms, "end_ms": start_ms + duration_ms}


class TestPlaceShadowTextEffects:
    def test_zero_duration_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=0,
            variation_seed=0,
            vocal_words=[_word("fire", 0)],
            shadow_words=["fire"],
        )
        assert result == {}

    def test_no_vocal_words_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=None,
            shadow_words=["fire"],
        )
        assert result == {}

    def test_no_shadow_words_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 0)],
            shadow_words=None,
        )
        assert result == {}

    def test_no_eligible_target_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Arch1", "Arches")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 0)],
            shadow_words=["fire"],
        )
        assert result == {}

    def test_tagged_word_never_sung_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("water", 0)],
            shadow_words=["fire"],
        )
        assert result == {}

    def test_matching_word_produces_two_layer_placement(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
            anchor_palette=["#FF0000", "#00FF00"],
        )
        placements = result["Matrix1"]
        assert len(placements) == 2
        front, shadow = sorted(placements, key=lambda p: p.layer)
        assert front.layer < shadow.layer
        assert front.color_palette == ["#FF0000"]
        assert shadow.color_palette == ["#00FF00"]
        assert front.parameters["E_TEXTCTRL_Text"] == "fire"
        assert shadow.parameters["E_TEXTCTRL_Text"] == "fire"
        assert "B_CUSTOM_SubBuffer" not in front.parameters
        assert shadow.parameters["B_CUSTOM_SubBuffer"] == _SHADOW_TEXT_MATRIX_SUBBUFFER
        assert front.parameters["E_CHOICE_Text_Effect"] == "normal"

    def test_word_matching_case_insensitive_and_punctuation_stripped(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("Fire!", 5_000)],
            shadow_words=["fire"],
        )
        assert "Matrix1" in result

    def test_single_color_palette_reuses_it_for_both_layers(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
            anchor_palette=["#FF0000"],
        )
        placements = result["Matrix1"]
        assert {p.color_palette[0] for p in placements} == {"#FF0000"}

    def test_no_anchor_palette_falls_back_to_white(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
        )
        placements = result["Matrix1"]
        assert {p.color_palette[0] for p in placements} == {"#FFFFFF"}

    def test_short_word_padded_to_minimum_burst(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000, duration_ms=50)],
            shadow_words=["fire"],
        )
        front = result["Matrix1"][0]
        assert front.end_ms - front.start_ms >= _SHADOW_TEXT_MIN_BURST_MS

    def test_burst_clipped_to_song_duration(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=5_500,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
        )
        for p in result["Matrix1"]:
            assert p.end_ms <= 5_500

    def test_two_occurrences_do_not_overlap(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 0, duration_ms=200), _word("fire", 500, duration_ms=200)],
            shadow_words=["fire"],
        )
        placements = sorted(result["Matrix1"], key=lambda p: p.start_ms)
        # Second occurrence starts before the first burst (padded to the
        # minimum) ends, so it must be skipped -- only one occurrence's
        # two layers survive.
        assert len(placements) == 2

    def test_reserves_layers_below_existing_content(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
            existing_layers={"Matrix1": 1},
        )
        placements = {p.layer: p for p in result["Matrix1"]}
        assert set(placements) == {-1, 0}

    def test_redirects_to_enclosing_tier_group(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[_group("06_PROP_Matrix", ["Matrix1"])],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
        )
        assert "06_PROP_Matrix" in result
        assert "Matrix1" not in result

    def test_front_text_uses_contrast_color_like_lyric_text(self):
        # Black is never the lightest entry -- front/main text should pick
        # the lighter palette color (matching _place_lyric_text's
        # _lightest_color contrast choice), not simply palette[0].
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
            anchor_palette=["#000000", "#FFFFFF"],
        )
        front, shadow = sorted(result["Matrix1"], key=lambda p: p.layer)
        assert front.color_palette == ["#FFFFFF"]
        assert shadow.color_palette == ["#000000"]

    def test_mega_tree_target_uses_vertical_text_family_params(self):
        result = _place_shadow_text_effects(
            props=[_prop("Mega Tree", "Custom")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
        )
        front, shadow = sorted(result["Mega Tree"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_CHOICE_Text_Effect"] == "vert text down"
            assert placement.parameters["E_CHOICE_Text_Font"] == "7-7x9 Bold"
            assert placement.parameters["E_NOTEBOOK"] == "End Position"
            assert placement.parameters["E_SLIDER_Text_YStart"] == "25"
            assert placement.parameters["E_SLIDER_Text_YEnd"] == "25"
        assert "B_CUSTOM_SubBuffer" not in front.parameters
        assert shadow.parameters["B_CUSTOM_SubBuffer"] == _SHADOW_TEXT_TREE_SUBBUFFER

    def test_matrix_target_does_not_get_tree_params(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_words=["fire"],
        )
        front, shadow = sorted(result["Matrix1"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_CHOICE_Text_Effect"] == "normal"
            assert "E_NOTEBOOK" not in placement.parameters
            assert "E_SLIDER_Text_YStart" not in placement.parameters
