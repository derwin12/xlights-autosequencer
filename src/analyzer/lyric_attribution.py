"""Attribute timed words to singers using part-annotated lyrics.

Genius-style annotated lyrics carry section headers with singer attribution and
inline parenthetical ad-libs, e.g.::

    [Intro]
    Ooh, ooh
    [Verse 1: Blake Shelton]
    I want to thank the storm that brought the snow
    [Chorus: Gwen Stefani & Blake Shelton]
    Sweet gingerbread made with molasses
    [Verse 3: Blake Shelton]
    And I want to thank you, baby (I want to thank you)

This module parses that into an ordered stream of ``LyricWord`` (each tagged
with the set of singers who sing it, or flagged as backing), then joins that
stream onto ASR-produced *timed* words by text sequence-alignment — so timings
come from WhisperX and "who sings it" comes from the lyrics.

No ML/audio dependencies; pure text + difflib. Safe to import anywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Section types that carry backing/non-lead content when they have no singer.
_BACKING_TYPES = frozenset({"intro", "instrumental", "interlude", "break", "outro"})
_SINGER_SPLIT = re.compile(r"\s*(?:&|,|/|\band\b|\bwith\b)\s*", re.IGNORECASE)
_HEADER = re.compile(r"^\[(?P<body>.+)\]\s*$")


@dataclass
class LyricWord:
    text: str                    # display token, e.g. "gingerbread"
    singers: frozenset           # canonical singer names; empty when backing/unknown
    backing: bool = False        # intro/ad-lib/harmony (non-lead) word


@dataclass
class ParsedLyrics:
    words: list[LyricWord] = field(default_factory=list)
    singers: list[str] = field(default_factory=list)  # lead singers, first-appearance order


def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9']", "", token.lower())


def _split_singers(s: str) -> list[str]:
    parts = [p.strip() for p in _SINGER_SPLIT.split(s) if p.strip()]
    return parts


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", text.strip()) if t]


def parse_annotated_lyrics(text: str) -> ParsedLyrics:
    """Parse Genius-style annotated lyrics into an ordered attributed word stream.

    - ``[Type: A & B]`` header → following lines' words sung by {A, B}.
    - ``[Type]`` with no singer and a backing-type name (Intro/Instrumental/…)
      → following words flagged backing.
    - Inline ``(ad-libs)`` anywhere → backing words at that position.
    - Distinct lead singers are collected in first-appearance order.
    """
    parsed = ParsedLyrics()
    cur_singers: frozenset = frozenset()
    cur_backing = True  # before any header, treat as backing (e.g. stray intro)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _HEADER.match(line)
        if m:
            body = m.group("body")
            if ":" in body:
                stype, who = body.split(":", 1)
                names = _split_singers(who)
                cur_singers = frozenset(names)
                cur_backing = False
                for n in names:
                    if n not in parsed.singers:
                        parsed.singers.append(n)
            else:
                stype = body.strip()
                cur_singers = frozenset()
                cur_backing = stype.lower() in _BACKING_TYPES
            continue

        # Lyric line: split into lead spans and parenthetical (backing) spans.
        for chunk, is_paren in _split_parens(line):
            for tok in _tokenize(chunk):
                if not _norm(tok):
                    continue
                backing = cur_backing or is_paren
                parsed.words.append(
                    LyricWord(text=tok,
                              singers=frozenset() if backing else cur_singers,
                              backing=backing)
                )
    return parsed


def _split_parens(line: str) -> list[tuple[str, bool]]:
    """Split a line into (text, is_parenthetical) spans, dropping the brackets."""
    out: list[tuple[str, bool]] = []
    pos = 0
    for m in re.finditer(r"\(([^)]*)\)", line):
        if m.start() > pos:
            out.append((line[pos:m.start()], False))
        out.append((m.group(1), True))
        pos = m.end()
    if pos < len(line):
        out.append((line[pos:], False))
    return out or [(line, False)]


@dataclass
class AttributedWord:
    """A timed word (from ASR) tagged with singers + backing from the lyrics."""
    label: str
    start_ms: int
    end_ms: int
    singers: frozenset
    backing: bool


def attribute_timed_words(
    timed: list[dict],
    parsed: ParsedLyrics,
) -> list[AttributedWord]:
    """Join ASR timed words onto the attributed lyric stream by text alignment.

    ``timed`` items are ``{"label"/"word", "start_ms", "end_ms"}``. Uses
    difflib to align the two normalized word sequences; matched timed words take
    the lyric word's singers/backing. Unmatched timed words (ASR extras) inherit
    the previous attribution so nothing is left unassigned.
    """
    def _label(d: dict) -> str:
        return str(d.get("label", d.get("word", "")))

    t_norm = [_norm(_label(d)) for d in timed]
    l_norm = [_norm(w.text) for w in parsed.words]

    out: list[AttributedWord] = [None] * len(timed)  # type: ignore
    sm = SequenceMatcher(a=t_norm, b=l_norm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                lw = parsed.words[j1 + k]
                td = timed[i1 + k]
                out[i1 + k] = AttributedWord(_label(td), int(td["start_ms"]),
                                             int(td["end_ms"]), lw.singers, lw.backing)
        elif tag in ("replace", "delete"):
            # ASR words with no lyric match: fill later from neighbours.
            pass

    # Fill unmatched timed words from the nearest attributed neighbour.
    last = None
    for idx in range(len(out)):
        if out[idx] is not None:
            last = out[idx]
        else:
            td = timed[idx]
            singers = last.singers if last else frozenset()
            backing = last.backing if last else False
            out[idx] = AttributedWord(_label(td), int(td["start_ms"]),
                                      int(td["end_ms"]), singers, backing)
    # Back-fill any leading unattributed run from the first known attribution.
    first_known = next((w for w in out if w.singers or w.backing), None)
    if first_known:
        for idx in range(len(out)):
            if not out[idx].singers and not out[idx].backing:
                out[idx].singers = first_known.singers
                out[idx].backing = first_known.backing
            else:
                break
    return out


def apply_to_marks(words: list[dict], phonemes: list[dict], annotated_text: str) -> None:
    """Attribute word + phoneme mark dicts in place from annotated lyrics.

    Sets ``singers`` (sorted list of names) and ``backing`` (bool) on each word
    dict. Each phoneme inherits the attribution of the word whose time span
    contains its start (nearest word otherwise). Mutates the dicts in place.
    """
    parsed = parse_annotated_lyrics(annotated_text)
    att = attribute_timed_words(words, parsed)
    for w, a in zip(words, att):
        w["singers"] = sorted(a.singers)
        w["backing"] = a.backing
    propagate_singers_to_phonemes(words, phonemes)


def propagate_singers_to_phonemes(words: list[dict], phonemes: list[dict]) -> None:
    """Copy each phoneme's ``singers``/``backing`` from the word that contains it.

    A phoneme inherits the attribution of the nearest word whose ``start_ms`` is
    at or before the phoneme's start. Mutates phoneme dicts in place. Used both
    when attributing from lyrics and when re-persisting user edits.
    """
    if not words:
        return
    import bisect
    ordered = sorted(range(len(words)), key=lambda i: int(words[i]["start_ms"]))
    starts = [int(words[i]["start_ms"]) for i in ordered]
    for pm in phonemes:
        ps = int(pm.get("start_ms", 0))
        pos = bisect.bisect_right(starts, ps) - 1
        if pos < 0:
            pos = 0
        w = words[ordered[pos]]
        pm["singers"] = list(w.get("singers", []))
        pm["backing"] = bool(w.get("backing", False))


BACKING_TRACK = "Backing"


def group_marks_by_named_singer(marks: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group attributed marks into named per-singer buckets + a Backing bucket.

    Each mark carries ``singers: list[str]`` (a shared/"Both" word belongs to
    several and lands in each) and ``backing: bool``. Returns ``(name, marks)``
    with named singers in first-appearance order, then ``"Backing"`` last (only
    if any backing marks exist). Input order preserved within each bucket.
    """
    order: list[str] = []
    buckets: dict[str, list[dict]] = {}
    backing: list[dict] = []
    for m in marks:
        if m.get("backing"):
            backing.append(m)
            continue
        for name in (m.get("singers") or []):
            if name not in buckets:
                buckets[name] = []
                order.append(name)
            buckets[name].append(m)
    result = [(name, buckets[name]) for name in order]
    if backing:
        result.append((BACKING_TRACK, backing))
    return result
