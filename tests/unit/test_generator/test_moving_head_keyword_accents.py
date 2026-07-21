"""Tests for moving_head.place_moving_head_keyword_accents (user-curated
lyric-keyword-triggered Moving Head accents -- shake/spin/bounce) and the
_keyword_triggers helper, plus place_moving_head_moves' existing_placements
exclusion of them."""
from __future__ import annotations

from pathlib import Path

from src.generator.models import EffectPlacement, SectionAssignment, SectionEnergy
from src.generator.moving_head import (
    _KEYWORD_ACCENT_DURATION_MS,
    _KEYWORD_ACCENT_MIN_GAP_MS,
    _keyword_triggers,
    place_moving_head_keyword_accents,
    place_moving_head_moves,
)
from src.grouper.layout import parse_layout
from src.themes.models import EffectLayer, Theme

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "grouper"
DEFAULT_KEYWORDS = ("shake", "spin", "bounce")


def _theme() -> Theme:
    return Theme(
        name="Test", mood="structural", occasion="general", genre="any", intent="test",
        layers=[EffectLayer(variant="Fire")], palette=["#FF0000", "#00FF00"],
    )


def _section(label: str, start_ms: int, end_ms: int, energy: int) -> SectionEnergy:
    return SectionEnergy(
        label=label, start_ms=start_ms, end_ms=end_ms,
        energy_score=energy, mood_tier="structural", impact_count=0,
    )


def _assignment(label: str, start_ms: int, end_ms: int, energy: int, variation_seed: int = 0) -> SectionAssignment:
    return SectionAssignment(
        section=_section(label, start_ms, end_ms, energy),
        theme=_theme(),
        variation_seed=variation_seed,
    )


def _word(label: str, start_ms: int, end_ms: int) -> dict:
    return {"label": label, "start_ms": start_ms, "end_ms": end_ms}


class TestKeywordTriggers:
    def test_no_match_returns_empty(self):
        words = [_word("hello", 0, 500), _word("world", 500, 900)]
        assert _keyword_triggers(words, DEFAULT_KEYWORDS) == []

    def test_case_insensitive_match(self):
        words = [_word("SHAKE", 1000, 1300)]
        assert _keyword_triggers(words, DEFAULT_KEYWORDS) == [("shake", 1000)]

    def test_punctuation_stripped(self):
        words = [_word("Shake,", 1000, 1300)]
        assert _keyword_triggers(words, DEFAULT_KEYWORDS) == [("shake", 1000)]

    def test_consecutive_same_keyword_collapses_to_one_trigger(self):
        # "Shake, shake, shake the snow globe" -- three hits within ~1s.
        words = [
            _word("Shake", 1000, 1300),
            _word("shake", 1350, 1600),
            _word("shake", 1650, 1900),
        ]
        assert _keyword_triggers(words, DEFAULT_KEYWORDS) == [("shake", 1000)]

    def test_same_keyword_far_apart_both_trigger(self):
        words = [
            _word("shake", 1000, 1300),
            _word("shake", 1000 + _KEYWORD_ACCENT_MIN_GAP_MS + 500, 1300 + _KEYWORD_ACCENT_MIN_GAP_MS + 500),
        ]
        triggers = _keyword_triggers(words, DEFAULT_KEYWORDS)
        assert len(triggers) == 2

    def test_different_keywords_do_not_collapse_together(self):
        words = [_word("shake", 1000, 1300), _word("spin", 1350, 1600)]
        assert _keyword_triggers(words, DEFAULT_KEYWORDS) == [("shake", 1000), ("spin", 1350)]

    def test_word_or_label_key_both_supported(self):
        assert _keyword_triggers([{"word": "bounce", "start_ms": 0, "end_ms": 300}], DEFAULT_KEYWORDS) == [
            ("bounce", 0),
        ]


class TestPlaceMovingHeadKeywordAccents:
    def test_no_words_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assert place_moving_head_keyword_accents(layout, None, DEFAULT_KEYWORDS, 200_000) == {}

    def test_no_keywords_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("shake", 1000, 1300)]
        assert place_moving_head_keyword_accents(layout, words, (), 200_000) == {}

    def test_no_matching_word_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("hello", 0, 500)]
        assert place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000) == {}

    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        words = [_word("shake", 1000, 1300)]
        assert place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000) == {}

    def test_shake_places_group_level_pan_vc_accent(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("shake", 10_000, 10_300)]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        assert set(result) == {"MH GRP"}
        punch = next(p for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"])
        assert punch.start_ms == 10_000
        assert punch.end_ms == 10_000 + _KEYWORD_ACCENT_DURATION_MS
        assert "Pan VC:" in punch.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Id=ID_VALUECURVE_MHPan" in punch.parameters["E_VALUECURVE_MHPan"]
        assert "Type=Ramp Up/Down" in punch.parameters["E_VALUECURVE_MHPan"]

    def test_bounce_places_group_level_tilt_vc_accent(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("bounce", 10_000, 10_300)]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        assert set(result) == {"MH GRP"}
        punch = next(p for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"])
        assert "Tilt VC:" in punch.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Id=ID_VALUECURVE_MHTilt" in punch.parameters["E_VALUECURVE_MHTilt"]
        assert "Type=Ramp Up/Down" in punch.parameters["E_VALUECURVE_MHTilt"]

    def test_spin_places_per_head_pattern_circle_on_every_head(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("spin", 10_000, 10_300)]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        assert set(result) == {"MH1", "MH2"}
        for head_name, slot in (("MH1", 1), ("MH2", 2)):
            punch = next(
                p for p in result[head_name]
                if "Shutter: On" in p.parameters[f"E_TEXTCTRL_MH{slot}_Settings"]
            )
            assert punch.parameters["E_CHOICE_MHPattern"] == "Circle"
            assert punch.parameters["E_CHECKBOX_MHPatternEnable"] == "1"

    def test_spin_skipped_when_a_prior_shake_still_occupies_the_group(self):
        # Regression (same bug class as _place_random_head_accents): a
        # "shake" trigger writes one group-level placement covering all
        # heads' channel slots. A "spin" trigger landing inside that same
        # window must be skipped even though the per-head occupancy check
        # only ever looked up individual head names before this fix.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("shake", 10_000, 10_300), _word("spin", 10_400, 10_700)]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        assert "MH GRP" in result  # the shake fired
        assert "MH1" not in result and "MH2" not in result  # the spin was skipped

    def test_unrecognized_keyword_in_config_is_silently_ignored(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("wiggle", 10_000, 10_300)]
        result = place_moving_head_keyword_accents(
            layout, words, ("wiggle",), 200_000,
        )
        assert result == {}

    def test_accent_clamped_to_song_duration(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("shake", 199_800, 200_000)]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        punch = next(p for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"])
        assert punch.end_ms == 200_000

    def test_skips_when_existing_placement_overlaps(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("shake", 10_000, 10_300)]
        existing = {
            "MH GRP": [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group="MH GRP", start_ms=9_500, end_ms=10_500,
                parameters={},
            )],
        }
        result = place_moving_head_keyword_accents(
            layout, words, DEFAULT_KEYWORDS, 200_000, existing_placements=existing,
        )
        assert result == {}

    def test_two_different_keyword_triggers_both_place(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("shake", 10_000, 10_300), _word("spin", 60_000, 60_300)]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        assert "MH GRP" in result  # shake
        assert "MH1" in result and "MH2" in result  # spin


class TestPlaceMovingHeadMovesRespectsKeywordAccents:
    """place_moving_head_moves must skip a section's move entirely when a
    keyword accent already occupies part of that section's natural move
    window, rather than colliding with it (bug class: real xLights channel-
    overlap warnings when two Moving Head placements share time+channels)."""

    def test_section_move_dropped_when_keyword_accent_overlaps(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 20_000, 90)]
        existing = {
            "MH GRP": [EffectPlacement(
                effect_name="Moving Head", xlights_id="eff_MOVINGHEAD",
                model_or_group="MH GRP", start_ms=5_000, end_ms=5_900,
                parameters={},
            )],
        }
        result = place_moving_head_moves(layout, assignments, existing_placements=existing)
        assert result == {}

    def test_section_move_placed_when_no_overlap(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 20_000, 90)]
        result = place_moving_head_moves(layout, assignments)
        assert result != {}
