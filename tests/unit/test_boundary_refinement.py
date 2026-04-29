"""Unit tests for src.story.boundary_refinement.

Each test constructs synthetic ``sections`` + ``WordMark`` inputs to exercise
one branch of one fix; no audio loading. Cases are drawn from the v7-final
corpus result documented in the OpenSpec change
``lyric-anchored-boundary-refinement``.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.analyzer.phonemes import WordMark
from src.story.boundary_refinement import (
    _chorus_first_line_distinctives,
    _consecutive_in_order_count,
    _hook_matches,
    merge_short_post_chorus_tail,
    refine_section_boundaries,
    relabel_or_split_bridge,
    split_pre_vocal_instrumental,
)


# ── Test helpers ──────────────────────────────────────────────────────────────


def _section(
    role: str,
    start: float,
    end: float,
    *,
    agreement_score: int = 3,
    **extra: Any,
) -> dict:
    base: dict[str, Any] = {
        "role": role,
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "agreement_score": agreement_score,
    }
    base.update(extra)
    return base


def _wm(label: str, start_ms: int, end_ms: int) -> WordMark:
    return WordMark(label=label.upper(), start_ms=start_ms, end_ms=end_ms)


def _words_at(start_s: float, labels: list[str], spacing_ms: int = 400) -> list[WordMark]:
    """Synthesise word marks starting at ``start_s`` with uniform spacing."""
    out = []
    cur = int(round(start_s * 1000))
    for label in labels:
        out.append(_wm(label, cur, cur + spacing_ms - 50))
        cur += spacing_ms
    return out


# ── _chorus_first_line_distinctives ───────────────────────────────────────────


def test_distinctives_extracts_long_words_in_order() -> None:
    targets = _chorus_first_line_distinctives(
        "DJ play a Christmas song\nI wanna keep on dancing"
    )
    # First line: "DJ play a Christmas song"
    # Filtered: "DJ" (too short, len<3), "play"(stopword? no — keep),
    #           "a" (too short), "Christmas" (keep), "song" (keep).
    assert targets == ["play", "christmas", "song"]


def test_distinctives_filters_stopwords_and_short() -> None:
    # "I am the with you" → all stopwords or len<3.
    targets = _chorus_first_line_distinctives("I am the with you")
    assert targets == []


def test_distinctives_caps_at_n() -> None:
    targets = _chorus_first_line_distinctives(
        "alpha bravo charlie delta echo foxtrot", n=3
    )
    assert targets == ["alpha", "bravo", "charlie"]


def test_distinctives_handles_empty_body() -> None:
    assert _chorus_first_line_distinctives("") == []
    assert _chorus_first_line_distinctives(None or "") == []


# ── _consecutive_in_order_count / _hook_matches ───────────────────────────────


def test_consecutive_in_order_finds_all_in_window() -> None:
    targets = ["alpha", "bravo", "charlie"]
    words = _words_at(0.0, ["alpha", "noise", "bravo", "noise", "charlie"])
    assert _consecutive_in_order_count(targets, words) == 3


def test_consecutive_in_order_tolerates_one_drop() -> None:
    # "bravo" missing from middle — alpha + charlie still match in order.
    targets = ["alpha", "bravo", "charlie"]
    words = _words_at(0.0, ["alpha", "noise", "noise", "charlie"])
    # alpha @ 0, charlie @ 3 (within window), bravo never found
    assert _consecutive_in_order_count(targets, words) == 2


def test_consecutive_in_order_respects_order() -> None:
    # charlie appears before alpha — only one of them matches as a starting anchor
    targets = ["alpha", "bravo", "charlie"]
    words = _words_at(0.0, ["charlie", "alpha", "bravo"])
    # alpha found at idx 1, bravo at idx 2 (within window), charlie searched after idx 3 → not found
    assert _consecutive_in_order_count(targets, words) == 2


def test_hook_matches_threshold_n_minus_1() -> None:
    # 4 targets → threshold is max(2, 3) = 3.
    targets = ["dj", "play", "christmas", "song"]
    # 3 of 4 in order → meets threshold of 3.
    assert _hook_matches(targets, _words_at(0.0, ["dj", "play", "song"])) is True
    # 2 of 4 in order → below threshold of 3.
    assert _hook_matches(targets, _words_at(0.0, ["dj", "song"])) is False


def test_hook_matches_two_targets_threshold_two() -> None:
    # 2 targets → threshold is max(2, 1) = 2 — both must match.
    targets = ["alpha", "bravo"]
    assert _hook_matches(targets, _words_at(0.0, ["alpha", "bravo"])) is True
    assert _hook_matches(targets, _words_at(0.0, ["alpha"])) is False


def test_hook_matches_requires_at_least_two_targets() -> None:
    # Single target → spec says insufficient lexical content.
    assert _hook_matches(["solo"], _words_at(0.0, ["solo"])) is False


# ── Fix 1: merge_short_post_chorus_tail ───────────────────────────────────────


def test_fix1_short_post_chorus_continuous_with_chorus_is_merged() -> None:
    # Cher chorus 2: chorus 105.58→116.83, post_chorus 116.83→120.65 (3.82s).
    # Last chorus word ends at 116.73, first post word at 116.83 → gap 100ms.
    chorus = _section("chorus", 105.58, 116.83, agreement_score=4)
    post = _section("post_chorus", 116.83, 120.65, agreement_score=1)
    forced = (
        _words_at(106.0, ["one", "two", "three"])
        + [_wm("only", 116000, 116730)]
        + _words_at(116.83, ["the", "only", "thing"])
    )
    out, notes = merge_short_post_chorus_tail([chorus, post], forced)

    assert len(out) == 1
    assert out[0]["role"] == "chorus"
    # End extended to last word + 250ms tail. Last word ends at 116.83 + 800 + 50 = ...
    assert out[0]["end"] > 116.83
    assert "merged short post_chorus" in out[0]["boundary_refinements"][0]
    assert len(notes) == 1


def test_fix1_long_post_chorus_is_not_merged() -> None:
    chorus = _section("chorus", 100.0, 110.0)
    post = _section("post_chorus", 110.0, 120.0, agreement_score=1)  # 10s — too long
    forced = _words_at(100.0, ["a", "b"]) + _words_at(110.5, ["c"])
    out, _ = merge_short_post_chorus_tail([chorus, post], forced)
    assert len(out) == 2


def test_fix1_high_agreement_post_chorus_is_not_merged() -> None:
    chorus = _section("chorus", 100.0, 105.0)
    post = _section("post_chorus", 105.0, 108.0, agreement_score=2)  # high agreement
    forced = _words_at(100.0, ["a", "b"]) + _words_at(105.0, ["c"])
    out, _ = merge_short_post_chorus_tail([chorus, post], forced)
    assert len(out) == 2


def test_fix1_large_gap_post_chorus_is_not_merged() -> None:
    chorus = _section("chorus", 100.0, 105.0)
    post = _section("post_chorus", 107.0, 110.0, agreement_score=1)
    # Last chorus word at 104s, first post word at 109s → 5s gap (>1500ms)
    forced = [_wm("a", 100000, 104000), _wm("b", 109000, 109500)]
    out, _ = merge_short_post_chorus_tail([chorus, post], forced)
    assert len(out) == 2


def test_fix1_ignores_skipped_sections() -> None:
    # Verify untouched sections gain no refinement note.
    chorus = _section("chorus", 100.0, 105.0)
    post = _section("post_chorus", 105.0, 108.0, agreement_score=3)  # high agreement
    out, _ = merge_short_post_chorus_tail([chorus, post], [])
    assert "boundary_refinements" not in out[0] or out[0]["boundary_refinements"] == []
    assert "boundary_refinements" not in out[1] or out[1]["boundary_refinements"] == []


# ── Fix 2: relabel_or_split_bridge ────────────────────────────────────────────


def test_fix2_bridge_with_full_chorus_hook_relabels_whole() -> None:
    # Cher: bridge 120.65–150.13 with chorus first-line "DJ play a Christmas song"
    bridge = _section("bridge", 120.65, 150.13)
    free = _words_at(121.0, ["dj", "play", "christmas", "song", "i", "wanna"])
    out, notes = relabel_or_split_bridge([bridge], free, "DJ play a Christmas song")

    assert len(out) == 1
    assert out[0]["role"] == "chorus"
    assert any("relabel whole" in n for n in notes)


def test_fix2_bridge_with_prefix_chorus_then_silence_then_other_lyrics_splits() -> None:
    # Crazy Train pattern: bridge 140.31–176.89 with chorus prefix, gap, then bridge tail.
    bridge = _section("bridge", 140.31, 176.89)
    free = (
        _words_at(140.49, ["dj", "play", "christmas", "song"], spacing_ms=800)  # prefix hook
        # gap 143.71 → 151.54 (~7.8s)
        + _words_at(151.54, ["mental", "wounds", "still", "screaming"])
    )
    out, notes = relabel_or_split_bridge([bridge], free, "DJ play a Christmas song")

    assert len(out) == 2
    assert out[0]["role"] == "chorus"
    assert out[1]["role"] == "bridge"
    assert out[0]["end"] == out[1]["start"]
    assert any("split" in n.lower() for n in notes)


def test_fix2_bridge_with_chorus_in_both_halves_relabels_whole() -> None:
    # Ghostbusters pattern: hook in both halves of bridge around silence gap.
    bridge = _section("bridge", 100.0, 130.0)
    free = (
        _words_at(101.0, ["who", "you", "gonna", "call", "ghostbusters"], spacing_ms=400)
        + _words_at(120.0, ["who", "you", "gonna", "call", "ghostbusters"], spacing_ms=400)
    )
    # Gap from 102.7 → 120.0 ≈ 17s
    out, notes = relabel_or_split_bridge(
        [bridge], free, "Who you gonna call Ghostbusters"
    )
    assert len(out) == 1
    assert out[0]["role"] == "chorus"
    assert any("BOTH halves" in n for n in notes)


def test_fix2_bridge_with_no_hook_match_unchanged() -> None:
    bridge = _section("bridge", 100.0, 130.0)
    free = _words_at(101.0, ["i", "believe", "after", "love"])
    out, notes = relabel_or_split_bridge(
        [bridge], free, "DJ play a Christmas song"
    )
    assert len(out) == 1
    assert out[0]["role"] == "bridge"
    assert notes == []


def test_fix2_chorus_first_line_too_short_skips() -> None:
    bridge = _section("bridge", 100.0, 130.0)
    free = _words_at(101.0, ["the", "of", "to"])
    out, notes = relabel_or_split_bridge([bridge], free, "I am the one")
    assert len(out) == 1
    assert out[0]["role"] == "bridge"
    assert notes == []


def test_fix2_non_bridge_sections_untouched() -> None:
    chorus = _section("chorus", 100.0, 110.0)
    free = _words_at(100.0, ["dj", "play", "christmas", "song"])
    out, _ = relabel_or_split_bridge([chorus], free, "DJ play a Christmas song")
    assert out[0]["role"] == "chorus"  # was already chorus, unchanged
    # And no refinement note added.
    assert out[0].get("boundary_refinements") in (None, [])


# ── Fix 3: split_pre_vocal_instrumental ───────────────────────────────────────


def test_fix3_long_pre_vocal_ramp_is_split() -> None:
    # Cher chorus 3: 150.13–174.16, first word at 163.75 → 13.6s ramp.
    chorus = _section("chorus", 150.13, 174.16)
    free = _words_at(163.75, ["you", "make", "me"])
    out, notes = split_pre_vocal_instrumental([chorus], free)

    assert len(out) == 2
    assert out[0]["role"] == "instrumental"
    assert out[1]["role"] == "chorus"
    assert out[1]["start"] > 150.13
    assert out[1]["start"] < 163.75 + 0.5
    # Synthetic instrumental section's start is original section start
    assert out[0]["start"] == 150.13
    assert any("first transcribed word" in n for n in notes)


def test_fix3_immediate_vocal_entry_unchanged() -> None:
    chorus = _section("chorus", 100.0, 130.0)
    free = _words_at(100.5, ["hello", "there"])  # only 0.5s gap
    out, _ = split_pre_vocal_instrumental([chorus], free)
    assert len(out) == 1
    assert out[0]["start"] == 100.0


def test_fix3_instrumental_role_skipped() -> None:
    inst = _section("instrumental_break", 100.0, 130.0)
    free = _words_at(120.0, ["leak"])
    out, _ = split_pre_vocal_instrumental([inst], free)
    assert len(out) == 1
    assert out[0]["role"] == "instrumental_break"


def test_fix3_short_remainder_marked_mislabel() -> None:
    # 30s section with first word at 28.5s → only 1.5s of vocal remainder.
    chorus = _section("chorus", 100.0, 130.0)
    free = [_wm("late", 128500, 128900)]
    out, _ = split_pre_vocal_instrumental([chorus], free)
    assert len(out) == 1
    assert out[0]["role"] == "chorus"
    assert any(
        "mislabeled" in n.lower() for n in out[0].get("boundary_refinements", [])
    )


def test_fix3_no_transcribed_words_unchanged() -> None:
    chorus = _section("chorus", 100.0, 130.0)
    out, notes = split_pre_vocal_instrumental([chorus], [])
    assert len(out) == 1
    assert notes == []


# ── Orchestrator: refine_section_boundaries ───────────────────────────────────


def test_refine_orchestrator_runs_fixes_in_order() -> None:
    # Crazy Train: bridge with chorus prefix + gap + bridge tail (Fix 2 fires
    # first), and Fix 3 then splits the bridge tail's instrumental gap before
    # vocals re-enter.
    bridge = _section("bridge", 140.31, 176.89, agreement_score=2)
    free = (
        _words_at(140.49, ["dj", "play", "christmas", "song"], spacing_ms=800)
        + _words_at(155.0, ["mental", "wounds"])  # in tail at 155 → 10s gap from 144.45
    )
    out, notes = refine_section_boundaries(
        [bridge],
        forced_words=[],
        free_words=free,
        chorus_body="DJ play a Christmas song",
    )
    # Expect: Fix 2 splits into chorus prefix + bridge tail; Fix 3 then splits
    # bridge tail because its first word at 155 leaves a >5s pre-vocal ramp.
    roles = [s["role"] for s in out]
    assert "chorus" in roles
    assert "instrumental" in roles
    assert "bridge" in roles
    assert any("chorus hook" in n for n in notes)


def test_refine_orchestrator_always_emits_boundary_refinements_field() -> None:
    chorus = _section("chorus", 0.0, 10.0)
    out, _ = refine_section_boundaries(
        [chorus], forced_words=[], free_words=[], chorus_body=None
    )
    assert "boundary_refinements" in out[0]
    assert out[0]["boundary_refinements"] == []


def test_refine_orchestrator_with_no_chorus_body_skips_fix2() -> None:
    # Bridge with chorus-shaped content but no chorus_body → Fix 2 doesn't fire.
    bridge = _section("bridge", 100.0, 130.0)
    free = _words_at(101.0, ["dj", "play", "christmas", "song"])
    out, notes = refine_section_boundaries(
        [bridge], forced_words=[], free_words=free, chorus_body=None
    )
    assert out[0]["role"] == "bridge"
    # No Fix-2 fire on this section.
    assert not any("relabel" in n for n in notes)
