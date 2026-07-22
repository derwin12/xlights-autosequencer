"""Tests for moving_head.place_moving_head_keyword_accents (user-curated
lyric-keyword-triggered Moving Head accents -- shake/spin/bounce) and the
_keyword_triggers helper, plus place_moving_head_moves' existing_placements
exclusion of them."""
from __future__ import annotations

from pathlib import Path

from src.generator.models import EffectPlacement, SectionAssignment, SectionEnergy, frame_align
from src.generator.moving_head import (
    _KEYWORD_ACCENT_DURATION_MS,
    _KEYWORD_PULSE_GAP_MS,
    _keyword_trigger_end_ms,
    _keyword_triggers,
    _PREFERRED_WARMUP_DURATION_MS,
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

    def test_consecutive_same_keyword_each_gets_its_own_trigger(self):
        # "Shake, shake, shake, shake the snow globe" -- one trigger per
        # word, NOT collapsed (user-confirmed 2026-07-21 after testing a
        # hand-built version: "one shake per word... was good and quick").
        words = [
            _word("Shake,", 1000, 1141),
            _word("shake,", 1181, 1481),
            _word("shake,", 1681, 2002),
            _word("shake", 2222, 2503),
        ]
        assert _keyword_triggers(words, DEFAULT_KEYWORDS) == [
            ("shake", 1000), ("shake", 1181), ("shake", 1681), ("shake", 2222),
        ]

    def test_same_keyword_far_apart_both_trigger(self):
        words = [
            _word("shake", 1000, 1300),
            _word("shake", 60_000, 60_300),
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


class TestKeywordTriggerEndMs:
    def test_uses_full_base_duration_when_no_next_same_keyword(self):
        triggers = [("shake", 1000)]
        end_ms = _keyword_trigger_end_ms(triggers, 0, 200_000)
        assert end_ms == 1000 + _KEYWORD_ACCENT_DURATION_MS["shake"]

    def test_shortened_to_fit_before_a_tight_next_same_keyword_hit(self):
        # Real reference-song gap: only 40ms between two consecutive
        # "shake" words -- the pulse must shrink to fit, not overlap.
        triggers = [("shake", 1000), ("shake", 1040)]
        end_ms = _keyword_trigger_end_ms(triggers, 0, 200_000)
        assert end_ms == 1040 - _KEYWORD_PULSE_GAP_MS

    def test_full_duration_used_when_next_trigger_is_a_different_keyword(self):
        triggers = [("shake", 1000), ("spin", 1040)]
        end_ms = _keyword_trigger_end_ms(triggers, 0, 200_000)
        assert end_ms == 1000 + _KEYWORD_ACCENT_DURATION_MS["shake"]

    def test_clamped_to_song_duration(self):
        triggers = [("shake", 199_900)]
        end_ms = _keyword_trigger_end_ms(triggers, 0, 200_000)
        assert end_ms == 200_000

    def test_spin_uses_pattern_accent_duration(self):
        from src.generator.moving_head import _ACCENT_DURATION_MS
        triggers = [("spin", 1000)]
        end_ms = _keyword_trigger_end_ms(triggers, 0, 200_000)
        assert end_ms == 1000 + _ACCENT_DURATION_MS


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
        assert punch.end_ms == 10_000 + _KEYWORD_ACCENT_DURATION_MS["shake"]
        assert "Pan VC:" in punch.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Id=ID_VALUECURVE_MHPan" in punch.parameters["E_VALUECURVE_MHPan"]
        assert "Type=Ramp Up/Down" in punch.parameters["E_VALUECURVE_MHPan"]

    def test_repeated_shake_words_each_get_their_own_quick_pulse(self):
        # The actual user-reported scenario: "Shake, shake, shake, shake"
        # sung in rapid succession (real reference-song gaps as tight as
        # 40ms) must produce FOUR distinct pulses, not one merged trigger.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [
            _word("Shake,", 46_054, 46_195),
            _word("shake,", 46_235, 46_535),
            _word("shake,", 46_735, 47_056),
            _word("shake", 47_276, 47_557),
        ]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        punches = sorted(
            (p for p in result["MH GRP"] if "Shutter: On" in p.parameters["E_TEXTCTRL_MH1_Settings"]),
            key=lambda p: p.start_ms,
        )
        assert len(punches) == 4
        # Placement timing is frame-aligned (nearest 25ms) like every other
        # EffectPlacement in this project -- compare against the aligned
        # word starts, not the raw millisecond values.
        assert [p.start_ms for p in punches] == [frame_align(t) for t in (46_054, 46_235, 46_735, 47_276)]
        # No punch overlaps the next word's own start, and each is shortened
        # to fit the tighter gaps rather than colliding.
        for punch, next_word_start in zip(punches, [46_235, 46_735, 47_276]):
            assert punch.end_ms <= next_word_start

    def test_shake_warmup_is_capped_not_filling_the_whole_gap(self):
        # Fixed 2026-07-21: this warmup used to fill the ENTIRE gap back to
        # the previous placement (or to time 0), unbounded. Fine for
        # crash_accents/ending_punches (rare-by-design, a handful per
        # song), but a keyword can repeat throughout a song's own lyrics
        # (real case: "Shake the Snow Globe" sings "shake" in clusters
        # roughly every 40s) -- an unbounded warmup there monopolizes the
        # group's channel for the entire span between clusters, starving
        # place_moving_head_moves of any usable segment. Must now cap to
        # _PREFERRED_WARMUP_DURATION_MS (3s) like every other move's warmup.
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        words = [_word("shake", 50_000, 50_300)]
        result = place_moving_head_keyword_accents(layout, words, DEFAULT_KEYWORDS, 200_000)
        warmup = next(p for p in result["MH GRP"] if "Shutter: On" not in p.parameters["E_TEXTCTRL_MH1_Settings"])
        assert warmup.end_ms == frame_align(50_000)
        assert warmup.end_ms - warmup.start_ms == _PREFERRED_WARMUP_DURATION_MS
        assert warmup.start_ms > 0  # NOT reaching all the way back to the start of the song

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
        # shake's own duration is short (250ms) -- put the spin inside that
        # window rather than after it, so this test still exercises the
        # actual overlap-skip case regardless of shake's tuned duration.
        words = [_word("shake", 10_000, 10_300), _word("spin", 10_100, 10_400)]
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

    def test_section_move_splits_around_keyword_accent_overlap(self):
        # Fixed 2026-07-21: a keyword-accent pulse in the middle of a
        # section used to drop the section's move ENTIRELY (result=={}).
        # A song whose lyrics repeat a keyword throughout the chorus (e.g.
        # "shake") would then get zero per-head/group moves for nearly the
        # whole song. Now the section's move splits around the obstacle
        # into the usable segments on either side instead.
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
        assert result != {}
        all_placements = [p for placements in result.values() for p in placements]
        assert not any(p.start_ms < 5_900 and p.end_ms > 5_000 for p in all_placements)
        assert any(p.end_ms <= 5_000 for p in all_placements)
        assert any(p.start_ms >= 5_900 for p in all_placements)

    def test_section_move_placed_when_no_overlap(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment("chorus", 0, 20_000, 90)]
        result = place_moving_head_moves(layout, assignments)
        assert result != {}
