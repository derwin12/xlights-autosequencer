"""Unit tests for src/song_identity.py."""
from __future__ import annotations

from src.song_identity import clean_title, split_title_artist


# ---------------------------------------------------------------------------
# clean_title
# ---------------------------------------------------------------------------

def test_clean_title_strips_audio_suffix():
    assert clean_title("Blue Christmas (Audio)") == "Blue Christmas"


def test_clean_title_strips_official_video_suffix():
    assert clean_title("Blue Christmas [Official Video]") == "Blue Christmas"


def test_clean_title_strips_multiple_suffixes():
    assert clean_title("Blue Christmas (Official Audio) (HD)") == "Blue Christmas"


def test_clean_title_no_suffix_unchanged():
    assert clean_title("Blue Christmas") == "Blue Christmas"


def test_clean_title_preserves_meaningful_parenthetical():
    assert clean_title("Blue Christmas (Live)") == "Blue Christmas (Live)"


# ---------------------------------------------------------------------------
# split_title_artist
# ---------------------------------------------------------------------------

def test_split_title_artist_splits_when_artist_missing():
    title, artist = split_title_artist("Elvis Presley - Blue Christmas (Audio)", "")
    assert title == "Blue Christmas"
    assert artist == "Elvis Presley"


def test_split_title_artist_splits_when_artist_is_unknown():
    title, artist = split_title_artist("Elvis Presley - Blue Christmas (Audio)", "Unknown")
    assert title == "Blue Christmas"
    assert artist == "Elvis Presley"


def test_split_title_artist_does_not_split_when_artist_present():
    title, artist = split_title_artist("Some Song - Reprise", "Real Artist")
    assert title == "Some Song - Reprise"
    assert artist == "Real Artist"


def test_split_title_artist_no_hyphen_returns_cleaned_title_only():
    title, artist = split_title_artist("Blue Christmas (Audio)", "")
    assert title == "Blue Christmas"
    assert artist == ""


def test_split_title_artist_none_artist_treated_as_missing():
    title, artist = split_title_artist("Elvis Presley - Blue Christmas", None)
    assert title == "Blue Christmas"
    assert artist == "Elvis Presley"
