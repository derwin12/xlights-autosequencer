"""Cleanup helpers for song title/artist metadata read from ID3 tags.

YouTube-to-MP3 rippers and similar tools commonly write the entire video
title (e.g. "Elvis Presley - Blue Christmas (Audio)") into the ID3 title
tag and leave the artist tag empty. Downstream consumers that trust the
title tag verbatim end up sending garbled title/artist pairs to external
lookups (synced lyrics, etc.), which increases the odds of a mismatched
result — see docs/segment-classification-changelog.md, 2026-07-15 entry.
"""
from __future__ import annotations

import re

# Suffixes commonly appended by YouTube-to-MP3 rippers and similar tools.
_JUNK_SUFFIX_RE = re.compile(
    r"\s*[\(\[]\s*(official\s*(video|audio|lyrics|music\s*video)?|audio|"
    r"lyrics?(\s*video)?|hd|hq|remaster(ed)?(\s*\d{4})?|explicit)\s*[\)\]]\s*",
    re.IGNORECASE,
)

# "Artist - Title" / "Artist – Title" / "Artist — Title" (hyphen, en dash, em dash).
_ARTIST_TITLE_RE = re.compile(r"^\s*(?P<artist>[^-–—]+?)\s*[-–—]\s*(?P<title>.+?)\s*$")


def clean_title(raw_title: str) -> str:
    """Strip common upload-tool suffixes like "(Official Audio)" from a title."""
    cleaned = raw_title
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _JUNK_SUFFIX_RE.sub(" ", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or raw_title.strip()


def split_title_artist(raw_title: str, raw_artist: str | None) -> tuple[str, str]:
    """Derive a clean ``(title, artist)`` pair from ID3 tag values.

    When no usable artist tag is present and the title looks like
    "Artist - Title" (the shape YouTube-to-MP3 tools commonly produce),
    splits the two apart. Junk suffixes like "(Audio)"/"(Official Video)"
    are stripped from the title in all cases.

    ``raw_artist`` of "" or "Unknown" (case-insensitive) is treated as
    absent, matching the "no artist tag" defaults used by
    ``src.story.builder`` and ``src.generator.plan.read_song_metadata``.
    """
    title = clean_title(raw_title or "")
    artist = (raw_artist or "").strip()

    has_artist = bool(artist) and artist.lower() != "unknown"
    if not has_artist:
        m = _ARTIST_TITLE_RE.match(title)
        if m:
            candidate_artist = m.group("artist").strip()
            candidate_title = clean_title(m.group("title").strip())
            if candidate_artist and candidate_title:
                return candidate_title, candidate_artist

    return title, artist
