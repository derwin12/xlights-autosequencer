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

# Credit/attribution lines some providers (notably netease, a Chinese
# source) inject as timed LRC lines rather than a proper [ar:]/[ti:] tag —
# syntactically valid lyric lines that aren't lyrics (e.g. a real generated
# .xsq surfaced "作词 : Paul McCartney/John Lennon" as the song's first
# on-screen "lyric", 2026-07-19). CJK labels require a colon; English labels
# require "by" as a whole word so an ordinary lyric that merely starts with
# "Music ..." isn't caught.
_CREDIT_LINE_RE = re.compile(
    r"^(?:作词|作曲|编曲|填词|制作人|监制|混音|母带|演唱|和声|录音)\s*[:：]"
    r"|^(?:lyrics?|lyricist|composed?|composer|music|written|produced?|producer"
    r"|arranged?|arranger|mixed|mixing|mastered|mastering|performed)\s+by\b"
    r"|^(?:lyricist|composer|producer|arranger)\s*:",
    re.IGNORECASE,
)


def _is_credit_line(text: str) -> bool:
    return bool(_CREDIT_LINE_RE.match(text.strip()))


def parse_lrc(lrc_text: str) -> list[tuple[int, str]]:
    """Parse LRC-format text into a list of ``(start_ms, line_text)`` tuples.

    Skips metadata tags (e.g. ``[ar:Artist]``, ``[ti:Title]``), timestamp
    tags with empty text, blank lines, and credit/attribution lines (see
    ``_CREDIT_LINE_RE``). Returned in chronological order.
    """
    lines: list[tuple[int, str]] = []
    for raw_line in lrc_text.splitlines():
        m = _LRC_LINE_RE.match(raw_line.strip())
        if not m:
            continue
        minutes, seconds, text = m.groups()
        text = text.strip()
        if not text or _is_credit_line(text):
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


def _search_synced_lyrics(search_term: str, *, max_attempts: int = 3) -> tuple[Optional[str], Optional[str]]:
    """Try ``syncedlyrics.search()`` up to ``max_attempts`` times, preferring
    a timed-LRC result over plain text.

    One provider in the allowlist (``megalobiz``) has been observed to time
    out intermittently; when it does, ``syncedlyrics`` silently falls back
    to a different provider that may only return plain (untimed) text —
    which is useless for forced word/line timing even though "lyrics were
    found". Retrying a couple of times gives a transient timeout another
    chance to land on a provider that returns real LRC timestamps instead.

    Returns ``(text, reason)``: ``text`` is the best result found (a timed
    result if any attempt got one, else the first plain-text result, else
    ``None``). ``reason`` is ``None`` when ``text`` is not ``None``,
    ``"not_installed"`` if the package is missing, ``"search_failed"`` if
    every attempt raised, or ``"no_match"`` if every attempt returned
    nothing without raising.
    """
    try:
        import syncedlyrics
    except ImportError:
        return None, "not_installed"

    best_result: Optional[str] = None
    any_attempt_succeeded = False
    for _ in range(max_attempts):
        try:
            result = syncedlyrics.search(search_term, providers=list(_ALLOWED_PROVIDERS))
        except Exception as exc:
            log.warning("syncedlyrics search failed for %r: %s", search_term, exc)
            continue
        any_attempt_succeeded = True
        if not result:
            continue
        if best_result is None:
            best_result = result
        if parse_lrc(result):
            return result, None

    if best_result is not None:
        return best_result, None
    return None, "search_failed" if not any_attempt_succeeded else "no_match"


def fetch_synced_lyrics(title: str, artist: str) -> Optional[str]:
    """Search for synced lyrics via ``syncedlyrics``, restricted to non-Genius providers.

    Returns raw LRC (or plain, provider-dependent) text, or ``None`` when no
    match is found, the search fails, or ``syncedlyrics`` isn't installed.
    """
    search_term = f"{title} {artist}".strip()
    if not search_term:
        return None

    text, reason = _search_synced_lyrics(search_term)
    if reason == "not_installed":
        log.warning("syncedlyrics is not installed — skipping synced-lyrics lookup")
    return text


_DURATION_MISMATCH_TOLERANCE_MS = 5000


def check_synced_lyrics_with_text(
    title: str, artist: str, duration_ms: Optional[int] = None,
) -> tuple[dict, Optional[str]]:
    """Same lookup as ``check_synced_lyrics_available``, also returning the
    raw lyrics text so a caller (the review API) can cache a confirmed-good
    result and reuse it for the real analyze pass instead of re-fetching —
    a second independent network round-trip against the same flaky provider
    could land on a worse (or no) result than what was already confirmed.

    ``duration_ms``, when given, is compared against the last LRC line's
    timestamp: a provider can return timed lyrics for a differently-timed
    recording (e.g. a longer remix or extended version) of the same
    title/artist, and nothing else here would catch that. A last line
    timestamped more than ``_DURATION_MISMATCH_TOLERANCE_MS`` past the
    analyzed song's actual duration is rejected with reason
    ``"duration_mismatch"`` rather than accepted as a good match.
    """
    search_term = f"{title} {artist}".strip()
    if not search_term:
        return {"found": False, "reason": "no_match", "line_count": 0, "preview": []}, None

    result, reason = _search_synced_lyrics(search_term)
    if result is None:
        return {"found": False, "reason": reason, "line_count": 0, "preview": []}, None

    lines = parse_lrc(result)
    if lines:
        last_start_ms = lines[-1][0]
        if duration_ms is not None and last_start_ms > duration_ms + _DURATION_MISMATCH_TOLERANCE_MS:
            return {"found": False, "reason": "duration_mismatch", "line_count": 0, "preview": []}, None
        preview = [text for _, text in lines[:3]]
        return {"found": True, "reason": None, "line_count": len(lines), "preview": preview}, result

    plain_lines = [
        ln.strip() for ln in result.splitlines()
        if ln.strip() and not _is_credit_line(ln)
    ]
    return {"found": True, "reason": None, "line_count": len(plain_lines), "preview": plain_lines[:3]}, result


def parse_pasted_lyrics(text: str) -> dict:
    """Validate/preview user-pasted lyrics text for the "Paste Lyrics" fallback.

    Runs pasted text through the same ``parse_lrc`` / plain-line /
    ``_is_credit_line`` path ``check_synced_lyrics_with_text`` uses for a
    provider result, so manually pasted text (e.g. copied from a lyrics site
    with an attribution block) can't reintroduce the credit-line
    contamination bug fixed there for provider results. Returns the same
    ``{found, reason, line_count, preview}`` shape as
    ``check_synced_lyrics_available``, plus ``source: "pasted"``.
    """
    text = (text or "").strip()
    if not text:
        return {"found": False, "reason": "empty", "line_count": 0, "preview": [], "source": "pasted"}

    lines = parse_lrc(text)
    if lines:
        preview = [line_text for _, line_text in lines[:3]]
        return {"found": True, "reason": None, "line_count": len(lines),
                "preview": preview, "source": "pasted"}

    plain_lines = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not _is_credit_line(ln)
    ]
    if not plain_lines:
        return {"found": False, "reason": "empty", "line_count": 0, "preview": [], "source": "pasted"}
    return {"found": True, "reason": None, "line_count": len(plain_lines),
            "preview": plain_lines[:3], "source": "pasted"}


def check_synced_lyrics_available(title: str, artist: str, duration_ms: Optional[int] = None) -> dict:
    """Look up synced lyrics for (title, artist) and report why, not just whether.

    Standalone diagnostic for the review UI's "Check Lyrics" button — same
    underlying lookup as ``fetch_synced_lyrics``, but distinguishes the four
    cases that otherwise all collapse to ``None`` there: the package isn't
    installed, the provider search raised (network/rate-limit), the search
    genuinely found no match, or (when ``duration_ms`` is given) the match
    found is timed for a differently-timed recording. Returns
    ``{"found": bool, "reason": str | None, "line_count": int, "preview": list[str]}``
    — ``reason`` is one of ``"not_installed"``, ``"search_failed"``,
    ``"no_match"``, or ``"duration_mismatch"`` when ``found`` is False, else
    ``None``.
    """
    result, _text = check_synced_lyrics_with_text(title, artist, duration_ms)
    return result


def get_boundary_refinement_inputs(
    title: str, artist: str, duration_ms: int, *, lyrics_text: Optional[str] = None,
) -> tuple[list[WordMark], Optional[str], list[TimingMark]]:
    """Fetch synced lyrics and derive ``(forced_words, chorus_body, line_marks)``.

    Returns ``([], None, [])`` when no synced lyrics are found, when
    ``syncedlyrics`` isn't installed, or when the search failed. When a
    provider returns untimed plain text (no LRC tags), ``forced_words`` and
    ``line_marks`` are empty but ``chorus_body`` can still be derived from
    line repetition. ``line_marks`` is one ``TimingMark`` per LRC line, for
    the lyric timeline track — fetched once here rather than a second time
    per call site to avoid a duplicate network lookup.

    ``lyrics_text``, when provided (e.g. a cached result from a prior
    "Check Lyrics" lookup), is used directly instead of performing a fresh
    ``fetch_synced_lyrics()`` call — avoids a second independent network
    round-trip against a potentially flaky provider that could return a
    different (or no) result than what was already confirmed.
    """
    if lyrics_text is None:
        lyrics_text = fetch_synced_lyrics(title, artist)
    if not lyrics_text:
        return [], None, []

    lines = parse_lrc(lyrics_text)
    if not lines:
        plain_lines = [
            (0, ln.strip()) for ln in lyrics_text.splitlines()
            if ln.strip() and not _is_credit_line(ln)
        ]
        return [], find_chorus_body(plain_lines), []

    if lines[-1][0] > duration_ms + _DURATION_MISMATCH_TOLERANCE_MS:
        log.warning(
            "synced lyrics for %r/%r run past the song's duration (last line at %dms, "
            "song is %dms) — likely a different recording, discarding",
            title, artist, lines[-1][0], duration_ms,
        )
        return [], None, []

    forced_words = lines_to_word_marks(lines, duration_ms)
    chorus_body = find_chorus_body(lines)
    line_marks = lines_to_timing_marks(lines, duration_ms)
    return forced_words, chorus_body, line_marks
