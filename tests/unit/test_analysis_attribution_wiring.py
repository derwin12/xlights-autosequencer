"""Guard that only genuinely part-annotated pasted lyrics trigger attribution."""
from __future__ import annotations

from src.review.api.v1 import analysis


def test_detects_singer_header():
    txt = "[Intro]\nOoh\n[Verse 1: Blake Shelton]\nI want to thank the storm\n"
    assert analysis._has_singer_annotations(txt) is True


def test_plain_lyrics_not_annotated():
    assert analysis._has_singer_annotations("I want to thank the storm\nThanks to the lights\n") is False


def test_section_headers_without_singer_not_annotated():
    # [Chorus] with no ": Name" must NOT trigger attribution.
    assert analysis._has_singer_annotations("[Chorus]\nsweet gingerbread\n") is False


def test_empty_or_none():
    assert analysis._has_singer_annotations("") is False
    assert analysis._has_singer_annotations(None) is False
