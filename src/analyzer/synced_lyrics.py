"""Synced-lyrics lookup: fetch, parse, and derive chorus text for boundary refinement.

Uses ``syncedlyrics`` (a token-free, multi-provider LRC aggregator) to feed
``src.story.boundary_refinement``'s Fix 1 (merge short post_chorus tails)
and Fix 2 (relabel/split a bridge whose sung content opens with the chorus
first-line hook). Unlike the retired Genius integration, LRC carries no
``[Chorus]``/``[Verse]`` structural headers — this module does not produce
section labels or boundaries, only word timing and a best-guess chorus text
block derived from line repetition.

Provider allowlist deliberately excludes ``syncedlyrics``'s built-in Genius
scraper: this project does not access genius.com in any form (see
docs/segment-classification-changelog.md, 2026-07-11 entry).
"""
from __future__ import annotations

import re
from typing import Optional

from src.analyzer.phonemes import WordMark
from src.analyzer.result import TimingMark
from src.log import get_logger

log = get_logger("xlight.synced_lyrics")

_ALLOWED_PROVIDERS = ["lrclib", "musixmatch", "netease", "deezer", "megalobiz", "lyricsify"]

_LRC_LINE_RE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")


def parse_lrc(lrc_text: str) -> list[tuple[int, str]]:
    """Parse LRC-format text into a list of ``(start_ms, line_text)`` tuples.

    Skips metadata tags (e.g. ``[ar:Artist]``, ``[ti:Title]``), timestamp
    tags with empty text, and blank lines. Returned in chronological order.
    """
    lines: list[tuple[int, str]] = []
    for raw_line in lrc_text.splitlines():
        m = _LRC_LINE_RE.match(raw_line.strip())
        if not m:
            continue
        minutes, seconds, text = m.groups()
        text = text.strip()
        if not text:
            continue
        start_ms = int(round((int(minutes) * 60 + float(seconds)) * 1000))
        lines.append((start_ms, text))
    lines.sort(key=lambda pair: pair[0])
    return lines


def lines_to_timing_marks(lines: list[tuple[int, str]], duration_ms: int) -> list[TimingMark]:
    """Expand ``(start_ms, line_text)`` pairs into one ``TimingMark`` per line.

    Used for the lyric timeline track (one labeled, duration-spanning block
    per line), as opposed to ``lines_to_word_marks`` which is per-word for
    boundary-refinement's word-window matching.
    """
    marks: list[TimingMark] = []
    for i, (start_ms, text) in enumerate(lines):
        end_ms = lines[i + 1][0] if i + 1 < len(lines) else duration_ms
        end_ms = max(end_ms, start_ms + 1)
        marks.append(TimingMark(time_ms=start_ms, confidence=None, label=text,
                                 duration_ms=end_ms - start_ms))
    return marks


def lines_to_word_marks(lines: list[tuple[int, str]], duration_ms: int) -> list[WordMark]:
    """Expand ``(start_ms, line_text)`` pairs into per-word ``WordMark``s.

    Every word in a line inherits that line's start timestamp; a word's
    end is the next line's start (or ``duration_ms`` for the last line).
    This is coarser than true per-word alignment, but matches the
    granularity boundary refinement's sliding-window text matching needs —
    it only checks whether a word appears within a window, not its exact
    millisecond position.
    """
    marks: list[WordMark] = []
    for i, (start_ms, text) in enumerate(lines):
        end_ms = lines[i + 1][0] if i + 1 < len(lines) else duration_ms
        end_ms = max(end_ms, start_ms + 1)
        for word in re.sub(r"[^a-zA-Z0-9\s']", " ", text).split():
            marks.append(WordMark(label=word.upper(), start_ms=start_ms, end_ms=end_ms))
    return marks


def _normalize_line(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def find_chorus_body(
    lines: list[tuple[int, str]], *, min_repeats: int = 2, block_size: int = 2,
) -> Optional[str]:
    """Find the most-repeated contiguous block of lyric lines.

    LRC carries no ``[Chorus]``/``[Verse]`` headers, so repetition is the
    only available signal: a chorus repeats near-verbatim across the song;
    a verse doesn't. Returns the original-cased text of the earliest
    occurrence of the most-repeated ``block_size``-line window, or ``None``
    if nothing repeats at least ``min_repeats`` times.
    """
    if len(lines) < block_size:
        return None

    occurrences: dict[str, list[int]] = {}
    for i in range(len(lines) - block_size + 1):
        key = " ".join(_normalize_line(lines[j][1]) for j in range(i, i + block_size))
        if not key:
            continue
        occurrences.setdefault(key, []).append(i)

    candidates = [(key, idxs) for key, idxs in occurrences.items() if len(idxs) >= min_repeats]
    if not candidates:
        return None

    # Most repeats wins; ties broken by earliest first occurrence.
    _best_key, best_idxs = min(candidates, key=lambda kv: (-len(kv[1]), kv[1][0]))
    first_idx = best_idxs[0]
    return " ".join(lines[j][1] for j in range(first_idx, first_idx + block_size))


def fetch_synced_lyrics(title: str, artist: str) -> Optional[str]:
    """Search for synced lyrics via ``syncedlyrics``, restricted to non-Genius providers.

    Returns raw LRC (or plain, provider-dependent) text, or ``None`` when no
    match is found, the search fails, or ``syncedlyrics`` isn't installed.
    """
    try:
        import syncedlyrics
    except ImportError:
        log.warning("syncedlyrics is not installed — skipping synced-lyrics lookup")
        return None

    search_term = f"{title} {artist}".strip()
    if not search_term:
        return None

    try:
        result = syncedlyrics.search(search_term, providers=list(_ALLOWED_PROVIDERS))
    except Exception as exc:
        log.warning("syncedlyrics search failed for %r: %s", search_term, exc)
        return None
    return result


def get_boundary_refinement_inputs(
    title: str, artist: str, duration_ms: int,
) -> tuple[list[WordMark], Optional[str], list[TimingMark]]:
    """Fetch synced lyrics and derive ``(forced_words, chorus_body, line_marks)``.

    Returns ``([], None, [])`` when no synced lyrics are found, when
    ``syncedlyrics`` isn't installed, or when the search failed. When a
    provider returns untimed plain text (no LRC tags), ``forced_words`` and
    ``line_marks`` are empty but ``chorus_body`` can still be derived from
    line repetition. ``line_marks`` is one ``TimingMark`` per LRC line, for
    the lyric timeline track — fetched once here rather than a second time
    per call site to avoid a duplicate network lookup.
    """
    lyrics_text = fetch_synced_lyrics(title, artist)
    if not lyrics_text:
        return [], None, []

    lines = parse_lrc(lyrics_text)
    if not lines:
        plain_lines = [(0, ln.strip()) for ln in lyrics_text.splitlines() if ln.strip()]
        return [], find_chorus_body(plain_lines), []

    forced_words = lines_to_word_marks(lines, duration_ms)
    chorus_body = find_chorus_body(lines)
    line_marks = lines_to_timing_marks(lines, duration_ms)
    return forced_words, chorus_body, line_marks
