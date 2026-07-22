"""Unit tests for src/analyzer/synced_lyrics.py.

All lyric text used here is synthetic placeholder text ("la la placeholder
line one", etc.) invented for testing — never real, copyrighted song lyrics.
``syncedlyrics.search`` is monkeypatched in every test that would otherwise
make a real network call.
"""
from __future__ import annotations

import pytest

from src.analyzer import synced_lyrics as sl


# ---------------------------------------------------------------------------
# parse_lrc
# ---------------------------------------------------------------------------

def test_parse_lrc_basic():
    lrc = (
        "[ar:Placeholder Artist]\n"
        "[ti:Placeholder Title]\n"
        "[00:01.00]la la placeholder line one\n"
        "[00:03.50]la la placeholder line two\n"
    )
    lines = sl.parse_lrc(lrc)
    assert lines == [
        (1000, "la la placeholder line one"),
        (3500, "la la placeholder line two"),
    ]


def test_parse_lrc_skips_metadata_and_blank_lines():
    lrc = "[ar:Someone]\n\n[00:00.00]\n[00:02.00]only real line\n"
    lines = sl.parse_lrc(lrc)
    assert lines == [(2000, "only real line")]


def test_parse_lrc_sorts_by_time():
    lrc = "[00:05.00]second\n[00:01.00]first\n"
    lines = sl.parse_lrc(lrc)
    assert [t for t, _ in lines] == [1000, 5000]


def test_parse_lrc_empty_input_returns_empty_list():
    assert sl.parse_lrc("") == []
    assert sl.parse_lrc("not lrc at all, just plain text") == []


def test_parse_lrc_skips_cjk_credit_lines():
    lrc = (
        "[00:00.00]作词 : Placeholder Writer\n"
        "[00:01.00]作曲 : Placeholder Composer\n"
        "[00:02.00]制作人 : Placeholder Producer\n"
        "[00:03.00]la la placeholder line one\n"
    )
    lines = sl.parse_lrc(lrc)
    assert lines == [(3000, "la la placeholder line one")]


def test_parse_lrc_skips_english_credit_lines():
    lrc = (
        "[00:00.00]Lyrics by Placeholder Writer\n"
        "[00:01.00]Composed by Placeholder Composer\n"
        "[00:02.00]Producer: Placeholder Producer\n"
        "[00:03.00]la la placeholder line one\n"
    )
    lines = sl.parse_lrc(lrc)
    assert lines == [(3000, "la la placeholder line one")]


def test_parse_lrc_does_not_false_positive_on_ordinary_lyric():
    # A real lyric line merely containing a credit-label word shouldn't be
    # dropped -- only "<label> by"/"<label>:" openers are treated as credits.
    lrc = "[00:00.00]Music was my first love\n"
    lines = sl.parse_lrc(lrc)
    assert lines == [(0, "Music was my first love")]


# ---------------------------------------------------------------------------
# lines_to_word_marks
# ---------------------------------------------------------------------------

def test_lines_to_word_marks_assigns_line_timestamp_to_every_word():
    lines = [(1000, "la la placeholder"), (4000, "line two here")]
    marks = sl.lines_to_word_marks(lines, duration_ms=10_000)
    assert [m.label for m in marks] == ["LA", "LA", "PLACEHOLDER", "LINE", "TWO", "HERE"]
    # First three words inherit line 1's start/end (line 2's start).
    assert all(m.start_ms == 1000 and m.end_ms == 4000 for m in marks[:3])
    # Last three words inherit line 2's start, ending at duration_ms.
    assert all(m.start_ms == 4000 and m.end_ms == 10_000 for m in marks[3:])


def test_lines_to_word_marks_empty_lines_returns_empty():
    assert sl.lines_to_word_marks([], duration_ms=10_000) == []


# ---------------------------------------------------------------------------
# lines_to_timing_marks
# ---------------------------------------------------------------------------

def test_lines_to_timing_marks_one_mark_per_line():
    lines = [(1000, "la la placeholder"), (4000, "line two here")]
    marks = sl.lines_to_timing_marks(lines, duration_ms=10_000)
    assert [m.label for m in marks] == ["la la placeholder", "line two here"]
    assert marks[0].time_ms == 1000 and marks[0].duration_ms == 3000
    assert marks[1].time_ms == 4000 and marks[1].duration_ms == 6000


def test_lines_to_timing_marks_empty_lines_returns_empty():
    assert sl.lines_to_timing_marks([], duration_ms=10_000) == []


# ---------------------------------------------------------------------------
# find_chorus_body
# ---------------------------------------------------------------------------

def test_find_chorus_body_detects_repeated_block():
    lines = [
        (0, "la la placeholder line one"),
        (2000, "la la placeholder line two"),
        (4000, "a completely different verse line"),
        (6000, "another unique verse line here"),
        (8000, "la la placeholder line one"),
        (10000, "la la placeholder line two"),
    ]
    chorus = sl.find_chorus_body(lines, block_size=2, min_repeats=2)
    assert chorus == "la la placeholder line one la la placeholder line two"


def test_find_chorus_body_none_when_nothing_repeats():
    lines = [
        (0, "first unique line"),
        (2000, "second unique line"),
        (4000, "third unique line"),
        (6000, "fourth unique line"),
    ]
    assert sl.find_chorus_body(lines, block_size=2, min_repeats=2) is None


def test_find_chorus_body_none_when_too_few_lines():
    assert sl.find_chorus_body([(0, "only one line")], block_size=2) is None


def test_find_chorus_body_case_and_punctuation_insensitive_matching():
    lines = [
        (0, "La La, Placeholder!"),
        (2000, "Line Two."),
        (4000, "unrelated verse text here"),
        (6000, "la la placeholder"),
        (8000, "line two"),
    ]
    chorus = sl.find_chorus_body(lines, block_size=2, min_repeats=2)
    # Returns the original-cased text of the *earliest* occurrence.
    assert chorus == "La La, Placeholder! Line Two."


# ---------------------------------------------------------------------------
# fetch_synced_lyrics — provider allowlist + error handling
# ---------------------------------------------------------------------------

def test_fetch_synced_lyrics_excludes_genius_provider(monkeypatch):
    captured = {}

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            captured["providers"] = providers
            return "[00:01.00]la la placeholder\n"

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.fetch_synced_lyrics("Placeholder Title", "Placeholder Artist")
    assert result == "[00:01.00]la la placeholder\n"
    assert "genius" not in captured["providers"]
    assert captured["providers"] == sl._ALLOWED_PROVIDERS


def test_fetch_synced_lyrics_returns_none_on_no_match(monkeypatch):
    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return None

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    assert sl.fetch_synced_lyrics("Nonexistent Song Xyzzy", "Nobody") is None


def test_fetch_synced_lyrics_returns_none_on_exception(monkeypatch):
    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            raise RuntimeError("network error")

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    assert sl.fetch_synced_lyrics("Title", "Artist") is None


def test_fetch_synced_lyrics_returns_none_when_package_missing(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "syncedlyrics":
            raise ImportError("no module named syncedlyrics")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    assert sl.fetch_synced_lyrics("Title", "Artist") is None


def test_fetch_synced_lyrics_empty_title_and_artist_returns_none():
    assert sl.fetch_synced_lyrics("", "") is None


# ---------------------------------------------------------------------------
# parse_pasted_lyrics — "Paste Lyrics" fallback for un-indexed songs
# ---------------------------------------------------------------------------

def test_parse_pasted_lyrics_empty_text_not_found():
    result = sl.parse_pasted_lyrics("   ")
    assert result == {"found": False, "reason": "empty", "line_count": 0,
                       "preview": [], "source": "pasted"}


def test_parse_pasted_lyrics_plain_text():
    text = "First line\nSecond line\nThird line\n"
    result = sl.parse_pasted_lyrics(text)
    assert result["found"] is True
    assert result["reason"] is None
    assert result["line_count"] == 3
    assert result["preview"] == ["First line", "Second line", "Third line"]
    assert result["source"] == "pasted"


def test_parse_pasted_lyrics_lrc_format():
    text = "[00:01.00]la la placeholder\n[00:03.00]another line\n"
    result = sl.parse_pasted_lyrics(text)
    assert result["found"] is True
    assert result["line_count"] == 2
    assert result["preview"] == ["la la placeholder", "another line"]


def test_parse_pasted_lyrics_strips_credit_lines():
    text = "Real lyric line\nLyrics by Someone\nAnother real line\n"
    result = sl.parse_pasted_lyrics(text)
    assert result["found"] is True
    assert result["line_count"] == 2
    assert result["preview"] == ["Real lyric line", "Another real line"]


def test_parse_pasted_lyrics_only_credit_lines_not_found():
    result = sl.parse_pasted_lyrics("Lyrics by Someone\nMusic by Someone Else\n")
    assert result["found"] is False
    assert result["reason"] == "empty"


# ---------------------------------------------------------------------------
# check_synced_lyrics_with_text — exposes raw text for caching
# ---------------------------------------------------------------------------

def test_check_synced_lyrics_with_text_returns_raw_lrc(monkeypatch):
    lrc = "[00:01.00]la la placeholder\n"

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return lrc

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result, text = sl.check_synced_lyrics_with_text("Title", "Artist")
    assert result["found"] is True
    assert text == lrc


def test_check_synced_lyrics_with_text_returns_none_when_not_found(monkeypatch):
    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return None

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result, text = sl.check_synced_lyrics_with_text("Nonexistent Xyzzy", "Nobody")
    assert result["found"] is False
    assert text is None


def test_check_synced_lyrics_with_text_rejects_match_longer_than_song(monkeypatch):
    """A provider can return LRC for a longer version (e.g. extended remix)
    of the same title/artist — the last line lands well past the analyzed
    song's actual duration, which must be rejected rather than accepted."""
    lrc = "[00:01.00]first line\n[04:00.00]last line far past song end\n"

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return lrc

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result, text = sl.check_synced_lyrics_with_text("Title", "Artist", duration_ms=60_000)
    assert result["found"] is False
    assert result["reason"] == "duration_mismatch"
    assert text is None


def test_check_synced_lyrics_with_text_accepts_match_within_tolerance(monkeypatch):
    lrc = "[00:01.00]first line\n[00:58.00]last line near song end\n"

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return lrc

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result, text = sl.check_synced_lyrics_with_text("Title", "Artist", duration_ms=60_000)
    assert result["found"] is True
    assert text == lrc


# ---------------------------------------------------------------------------
# get_boundary_refinement_inputs — end-to-end wiring
# ---------------------------------------------------------------------------

def test_get_boundary_refinement_inputs_uses_cached_lyrics_text_without_refetching(monkeypatch):
    """A cached lyrics_text (e.g. from a prior Check Lyrics call) must skip
    fetch_synced_lyrics entirely — no second network round-trip."""
    lrc = "[00:01.00]cached line one\n[00:03.00]cached line two\n"

    def _should_not_be_called(title, artist):
        raise AssertionError("fetch_synced_lyrics should not be called when lyrics_text is cached")

    monkeypatch.setattr(sl, "fetch_synced_lyrics", _should_not_be_called)
    forced_words, chorus_body, line_marks = sl.get_boundary_refinement_inputs(
        "Title", "Artist", 12_000, lyrics_text=lrc,
    )
    assert len(forced_words) > 0
    assert [m.label for m in line_marks] == ["cached line one", "cached line two"]


def test_get_boundary_refinement_inputs_discards_lyrics_longer_than_song(monkeypatch):
    lrc = "[00:01.00]first line\n[04:00.00]last line far past song end\n"

    forced_words, chorus_body, line_marks = sl.get_boundary_refinement_inputs(
        "Title", "Artist", 60_000, lyrics_text=lrc,
    )
    assert forced_words == []
    assert chorus_body is None
    assert line_marks == []


def test_get_boundary_refinement_inputs_full_lrc(monkeypatch):
    lrc = (
        "[00:01.00]la la placeholder line one\n"
        "[00:03.00]la la placeholder line two\n"
        "[00:05.00]a unique verse line here\n"
        "[00:07.00]la la placeholder line one\n"
        "[00:09.00]la la placeholder line two\n"
    )
    monkeypatch.setattr(sl, "fetch_synced_lyrics", lambda title, artist: lrc)
    forced_words, chorus_body, line_marks = sl.get_boundary_refinement_inputs("Title", "Artist", 12_000)
    assert len(forced_words) > 0
    assert chorus_body == "la la placeholder line one la la placeholder line two"
    assert [m.label for m in line_marks] == [
        "la la placeholder line one",
        "la la placeholder line two",
        "a unique verse line here",
        "la la placeholder line one",
        "la la placeholder line two",
    ]


def test_get_boundary_refinement_inputs_no_match(monkeypatch):
    monkeypatch.setattr(sl, "fetch_synced_lyrics", lambda title, artist: None)
    forced_words, chorus_body, line_marks = sl.get_boundary_refinement_inputs("Title", "Artist", 12_000)
    assert forced_words == []
    assert chorus_body is None
    assert line_marks == []


# ---------------------------------------------------------------------------
# check_synced_lyrics_available — standalone diagnostic for the "Check
# Lyrics" button, distinguishing not_installed / search_failed / no_match.
# ---------------------------------------------------------------------------

def test_check_synced_lyrics_found_with_lrc(monkeypatch):
    lrc = (
        "[00:01.00]la la placeholder line one\n"
        "[00:03.00]la la placeholder line two\n"
        "[00:05.00]a unique verse line here\n"
    )

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return lrc

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Placeholder Title", "Placeholder Artist")
    assert result["found"] is True
    assert result["reason"] is None
    assert result["line_count"] == 3
    assert result["preview"] == [
        "la la placeholder line one",
        "la la placeholder line two",
        "a unique verse line here",
    ]


def test_check_synced_lyrics_found_plain_text(monkeypatch):
    plain = "la la placeholder line one\nla la placeholder line two\n"

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return plain

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Title", "Artist")
    assert result["found"] is True
    assert result["line_count"] == 2


def test_check_synced_lyrics_no_match(monkeypatch):
    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return None

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Nonexistent Song Xyzzy", "Nobody")
    assert result == {"found": False, "reason": "no_match", "line_count": 0, "preview": []}


def test_check_synced_lyrics_search_failed(monkeypatch):
    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            raise RuntimeError("network error")

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Title", "Artist")
    assert result == {"found": False, "reason": "search_failed", "line_count": 0, "preview": []}


def test_check_synced_lyrics_not_installed(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "syncedlyrics":
            raise ImportError("no module named syncedlyrics")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    result = sl.check_synced_lyrics_available("Title", "Artist")
    assert result == {"found": False, "reason": "not_installed", "line_count": 0, "preview": []}


def test_check_synced_lyrics_retries_and_prefers_timed_result_over_plain(monkeypatch):
    """megalobiz-style flakiness: first attempt returns plain text (no LRC
    tags), a later attempt returns real timed lines — the retry must keep
    trying until it lands on the timed result rather than settling for the
    first (untimed) hit."""
    calls = {"count": 0}
    plain = "la la placeholder line one\nla la placeholder line two\n"
    lrc = "[00:01.00]la la placeholder line one\n[00:03.00]la la placeholder line two\n"

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            calls["count"] += 1
            return plain if calls["count"] == 1 else lrc

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Title", "Artist")
    assert result["found"] is True
    assert result["line_count"] == 2
    assert calls["count"] == 2


def test_check_synced_lyrics_falls_back_to_plain_when_no_attempt_gets_timed(monkeypatch):
    """Every attempt returns plain text — after exhausting retries, the
    first plain-text result is still reported as found (chorus_body can
    still be derived from it), not discarded."""
    calls = {"count": 0}

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            calls["count"] += 1
            return "always plain text, never timed\n"

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Title", "Artist")
    assert result["found"] is True
    assert result["reason"] is None
    assert calls["count"] == 3


def test_check_synced_lyrics_no_match_when_all_attempts_cleanly_return_none(monkeypatch):
    """All attempts return None without raising — genuinely no match, not
    a provider failure."""
    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            return None

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Nonexistent Song Xyzzy", "Nobody")
    assert result == {"found": False, "reason": "no_match", "line_count": 0, "preview": []}


def test_check_synced_lyrics_search_failed_only_when_every_attempt_raises(monkeypatch):
    """A mix of one clean None and some raises must NOT be reported as
    search_failed — only report search_failed when every single attempt
    raised (a clean 'no result' response, even once, means the provider(s)
    are reachable and this is a genuine no-match)."""
    calls = {"count": 0}

    class _FakeSyncedLyrics:
        @staticmethod
        def search(term, providers=None, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return None
            raise RuntimeError("network error")

    monkeypatch.setitem(__import__("sys").modules, "syncedlyrics", _FakeSyncedLyrics)
    result = sl.check_synced_lyrics_available("Title", "Artist")
    assert result["reason"] == "no_match"


def test_check_synced_lyrics_empty_query_returns_no_match():
    result = sl.check_synced_lyrics_available("", "")
    assert result == {"found": False, "reason": "no_match", "line_count": 0, "preview": []}


def test_get_boundary_refinement_inputs_plain_text_no_timestamps(monkeypatch):
    """Some providers can return untimed plain text — no forced_words, but
    chorus_body can still be derived from line repetition."""
    plain = (
        "la la placeholder line one\n"
        "la la placeholder line two\n"
        "a unique verse line here\n"
        "la la placeholder line one\n"
        "la la placeholder line two\n"
    )
    monkeypatch.setattr(sl, "fetch_synced_lyrics", lambda title, artist: plain)
    forced_words, chorus_body, line_marks = sl.get_boundary_refinement_inputs("Title", "Artist", 12_000)
    assert forced_words == []
    assert chorus_body == "la la placeholder line one la la placeholder line two"
    assert line_marks == []
