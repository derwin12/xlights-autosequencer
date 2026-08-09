"""Tests for the Shadow Text word effect: two-layer Text placement on
user-tagged words, targeting the same Matrix/Mega Tree props as Pictures."""
from __future__ import annotations

from src.generator.effect_placer import (
    _SHADOW_TEXT_MATRIX_SHORT_WORD_MAX_LEN,
    _SHADOW_TEXT_MATRIX_SUBBUFFER,
    _SHADOW_TEXT_MIN_BURST_MS,
    _SHADOW_TEXT_TREE_SUBBUFFER,
    _SHADOW_TEXT_TREE_SHORT_WORD_MAX_LEN,
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
            shadow_occurrences=[{"word": "fire", "start_ms": 0}],
        )
        assert result == {}

    def test_no_vocal_words_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=None,
            shadow_occurrences=[{"word": "fire", "start_ms": 0}],
        )
        assert result == {}

    def test_no_shadow_occurrences_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 0)],
            shadow_occurrences=None,
        )
        assert result == {}

    def test_no_eligible_target_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Arch1", "Arches")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 0)],
            shadow_occurrences=[{"word": "fire", "start_ms": 0}],
        )
        assert result == {}

    def test_tagged_word_never_sung_returns_empty(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("water", 0)],
            shadow_occurrences=[{"word": "fire", "start_ms": 0}],
        )
        assert result == {}

    def test_matching_word_produces_two_layer_placement(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
            accent_palette=["#FF6B00", "#00FF00"],
        )
        placements = result["Matrix1"]
        assert len(placements) == 2
        front, shadow = sorted(placements, key=lambda p: p.layer)
        assert front.layer < shadow.layer
        assert front.color_palette == ["#FFFFFF"]
        assert shadow.color_palette == ["#FF6B00"]
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
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        assert "Matrix1" in result

    def test_single_accent_color_used_for_shadow_layer_only(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
            accent_palette=["#FF6B00"],
        )
        front, shadow = sorted(result["Matrix1"], key=lambda p: p.layer)
        assert front.color_palette == ["#FFFFFF"]
        assert shadow.color_palette == ["#FF6B00"]

    def test_no_accent_palette_falls_back_to_white(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
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
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        front = result["Matrix1"][0]
        assert front.end_ms - front.start_ms >= _SHADOW_TEXT_MIN_BURST_MS

    def test_burst_is_centered_on_the_word_midpoint_not_word_start(self):
        # 2026-08-03 (refined same day -- centering on word_start alone
        # read as slightly too early): the burst's MIDPOINT must land on
        # the WORD's own midpoint (start+end)/2, not just its start_ms.
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fireworks", 10_000, duration_ms=1_600)],
            shadow_occurrences=[{"word": "fireworks", "start_ms": 10_000}],
        )
        front = result["Matrix1"][0]
        burst_ms = front.end_ms - front.start_ms
        assert burst_ms == 1_600
        word_mid = 10_000 + 1_600 // 2  # (word_start + word_end) / 2
        assert front.start_ms == word_mid - 800
        assert front.end_ms == word_mid + 800
        midpoint = (front.start_ms + front.end_ms) / 2
        assert midpoint == word_mid

    def test_centered_burst_start_clamps_at_zero(self):
        # word_start near the very beginning of the song -- centering
        # would otherwise push start negative.
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fireworks", 0, duration_ms=1_600)],
            shadow_occurrences=[{"word": "fireworks", "start_ms": 0}],
        )
        front = result["Matrix1"][0]
        assert front.start_ms == 0

    def test_burst_clipped_to_song_duration(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=5_500,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        for p in result["Matrix1"]:
            assert p.end_ms <= 5_500

    def test_two_close_occurrences_stack_on_a_higher_layer_pair(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 0, duration_ms=200), _word("fire", 500, duration_ms=200)],
            shadow_occurrences=[
                {"word": "fire", "start_ms": 0}, {"word": "fire", "start_ms": 500},
            ],
        )
        placements = sorted(result["Matrix1"], key=lambda p: p.start_ms)
        # Second occurrence starts before the first burst (padded to the
        # minimum) ends -- rather than being dropped, its front/shadow pair
        # stacks on the next layer pair up (user request, 2026-08-09), so
        # all four placements (two occurrences x front+shadow) survive.
        assert len(placements) == 4
        first_pair_layers = {p.layer for p in placements[:2]}
        second_pair_layers = {p.layer for p in placements[2:]}
        assert first_pair_layers.isdisjoint(second_pair_layers)
        # The second occurrence's pair renders above (smaller indices than)
        # the first's.
        assert max(second_pair_layers) < min(first_pair_layers)

    def test_reserves_layers_below_existing_content(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
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
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        assert "06_PROP_Matrix" in result
        assert "Matrix1" not in result

    def test_front_text_is_always_white_regardless_of_accent_palette(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
            accent_palette=["#000000", "#3355FF"],
        )
        front, shadow = sorted(result["Matrix1"], key=lambda p: p.layer)
        assert front.color_palette == ["#FFFFFF"]
        assert shadow.color_palette == ["#000000"]

    def test_mega_tree_target_uses_vertical_text_family_params(self):
        # "fireworks" (9 chars) stays above the short-word font threshold,
        # so this exercises the family's default narrow font.
        result = _place_shadow_text_effects(
            props=[_prop("Mega Tree", "Custom")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fireworks", 5_000)],
            shadow_occurrences=[{"word": "fireworks", "start_ms": 5_000}],
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

    def test_mega_tree_text_is_x_centered(self):
        # 2026-08-03: -3 centers the vertical text column on the tree
        # instead of sitting flush against one edge.
        result = _place_shadow_text_effects(
            props=[_prop("Mega Tree", "Custom")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fireworks", 5_000)],
            shadow_occurrences=[{"word": "fireworks", "start_ms": 5_000}],
        )
        front, shadow = sorted(result["Mega Tree"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_SLIDER_Text_XStart"] == "-3"
            assert placement.parameters["E_SLIDER_Text_XEnd"] == "-3"

    def test_mega_tree_short_word_uses_larger_bold_font(self):
        # 2026-08-02: a word of 5 characters or fewer renders at the tree's
        # default bold font instead of the narrower 7-7x9 Bold.
        result = _place_shadow_text_effects(
            props=[_prop("Mega Tree", "Custom")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        front, shadow = sorted(result["Mega Tree"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_CHOICE_Text_Font"] == "10-12x12 Bold"

    def test_mega_tree_short_word_x_offset_is_the_same_fixed_value(self):
        # 2026-08-03: confirmed a per-font dynamic X-offset isn't needed --
        # the short-word font (wider than the default) still uses -3, not
        # a value scaled to its own width.
        word = "hi"
        assert len(word) <= _SHADOW_TEXT_TREE_SHORT_WORD_MAX_LEN
        result = _place_shadow_text_effects(
            props=[_prop("Mega Tree", "Custom")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word(word, 5_000)],
            shadow_occurrences=[{"word": word, "start_ms": 5_000}],
        )
        front, shadow = sorted(result["Mega Tree"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_SLIDER_Text_XStart"] == "-3"
            assert placement.parameters["E_SLIDER_Text_XEnd"] == "-3"

    def test_matrix_short_word_uses_larger_bold_font(self):
        # 2026-08-08: a word of 6 characters or fewer on a non-"small"
        # Matrix target renders at 12-15x15 Bold instead of the default
        # 10-12x12 Bold.
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        front, shadow = sorted(result["Matrix1"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_CHOICE_Text_Font"] == "12-15x15 Bold"

    def test_matrix_long_word_keeps_default_font(self):
        word = "fireworks"
        assert len(word) > _SHADOW_TEXT_MATRIX_SHORT_WORD_MAX_LEN
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word(word, 5_000)],
            shadow_occurrences=[{"word": word, "start_ms": 5_000}],
        )
        front, shadow = sorted(result["Matrix1"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert "E_CHOICE_Text_Font" not in placement.parameters

    def test_small_matrix_short_word_keeps_small_font_not_larger_bold(self):
        # A "small"-named matrix's 5-5x5 Mono is deliberately tiny for a
        # physically small display -- short words must NOT get bumped to
        # 12-15x15 Bold there.
        result = _place_shadow_text_effects(
            props=[_prop("Matrix Small", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        front, shadow = sorted(result["Matrix Small"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_CHOICE_Text_Font"] == "5-5x5 Mono"

    def test_mega_tree_shadow_text_never_rotates(self):
        # 2026-08-02: Mega Tree shadow text must never carry a rotation
        # value curve, regardless of which motion the seeded pick lands on.
        for seed in range(20):
            result = _place_shadow_text_effects(
                props=[_prop("Mega Tree", "Custom")],
                groups=[],
                duration_ms=60_000,
                variation_seed=seed,
                vocal_words=[_word("fireworks", 5_000)],
                shadow_occurrences=[{"word": "fireworks", "start_ms": 5_000}],
            )
            for placement in result["Mega Tree"]:
                assert "B_SLIDER_Rotations" not in placement.parameters
                assert "B_VALUECURVE_Rotation" not in placement.parameters

    def test_matrix_target_does_not_get_tree_params(self):
        result = _place_shadow_text_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            duration_ms=60_000,
            variation_seed=0,
            vocal_words=[_word("fire", 5_000)],
            shadow_occurrences=[{"word": "fire", "start_ms": 5_000}],
        )
        front, shadow = sorted(result["Matrix1"], key=lambda p: p.layer)
        for placement in (front, shadow):
            assert placement.parameters["E_CHOICE_Text_Effect"] == "normal"
            assert "E_NOTEBOOK" not in placement.parameters
            assert "E_SLIDER_Text_YStart" not in placement.parameters
