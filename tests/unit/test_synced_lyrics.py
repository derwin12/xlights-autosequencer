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
# get_boundary_refinement_inputs — end-to-end wiring
# ---------------------------------------------------------------------------

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
