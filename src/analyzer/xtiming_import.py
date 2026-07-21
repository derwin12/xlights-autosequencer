"""Import a user-supplied .xtiming file's Lyrics track as a WhisperX override.

Lets a user who already has correct word/phoneme timing (typed directly into
xLights' own Lyrics timing track, or from another tool) skip WhisperX
transcription/alignment entirely — sidesteps the all-or-nothing fallback in
``PhonemeAnalyzer._align_with_lyrics`` (see cerebrum 2026-07-21: a single bad
patch of pasted-lyrics alignment can drag whole-song coverage below 50% and
silently discard the ENTIRE alignment for free-transcription "made up" words
instead).

Schema (matches xLights' own .xtiming export/import, confirmed against
``tests/fixtures/*.xtiming`` and a real user-exported file): a ``<timing>``
element with 2-3 ``EffectLayer`` children (phrases / words / phonemes).
The track is *not* reliably named "Lyrics" — our own ``XTimingWriter``
names it after the sanitized source filename (e.g.
"shakethesnowglobegwenstefani"), and a hand-exported xLights sequence may
use whatever name the user gave the timing track. Identify it structurally
(>=2 EffectLayers) rather than by name::

    <timings>
      <timing name="<anything>" SourceVersion="2024.01">
        <EffectLayer>  <!-- layer 1: phrases (ignored here) -->
        <EffectLayer>  <!-- layer 2: words -- REQUIRED -->
          <Effect label="WORD" starttime="1000" endtime="1400" />
        <EffectLayer>  <!-- layer 3: phonemes -- optional, auto-derived if absent -->
      </timing>
    </timings>
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from src.log import get_logger

log = get_logger("xlight.xtiming_import")


class XTimingImportError(Exception):
    """Raised when a .xtiming file has no usable Lyrics word-level layer."""


def _parse_marks(layer: ET.Element) -> list[dict]:
    marks: list[dict] = []
    for effect in layer.findall("Effect"):
        label = effect.get("label", "")
        start = effect.get("starttime")
        end = effect.get("endtime")
        if not label or start is None or end is None:
            continue
        try:
            start_ms, end_ms = int(round(float(start))), int(round(float(end)))
        except ValueError:
            continue
        if end_ms <= start_ms:
            continue
        marks.append({"label": label, "start_ms": start_ms, "end_ms": end_ms})
    return marks


def parse_xtiming_lyrics(xml_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Return ``(words, phonemes)`` mark dicts from a .xtiming file's Lyrics track.

    The Lyrics track is identified structurally (>=2 EffectLayers), not by
    name — see the module docstring. A ``<timing name="lyrics">`` (or
    containing "lyric") is preferred when multiple multi-layer candidates
    exist in the same file; with exactly one multi-layer ``<timing>``
    overall, that one is used regardless of its name.

    Raises ``XTimingImportError`` when the file is malformed, has no
    multi-layer timing track, or multiple ambiguous candidates.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise XTimingImportError(f"Not a valid .xtiming XML file: {exc}") from exc

    candidates = [t for t in root.findall("timing") if len(t.findall("EffectLayer")) >= 2]
    if not candidates:
        raise XTimingImportError(
            "No timing track with a word-level layer was found in this "
            ".xtiming file — break the phrase into words in xLights "
            "(right-click the Lyrics track) before exporting."
        )

    named = [t for t in candidates if "lyric" in (t.get("name") or "").lower()]
    if named:
        lyrics_timing = named[0]
    elif len(candidates) == 1:
        lyrics_timing = candidates[0]
    else:
        names = ", ".join(repr(t.get("name") or "") for t in candidates)
        raise XTimingImportError(
            f"Multiple timing tracks with word-level layers found ({names}) "
            "and none is named \"Lyrics\" — export just the Lyrics track, "
            "or rename it to include \"lyrics\"."
        )

    layers = lyrics_timing.findall("EffectLayer")

    words = _parse_marks(layers[1])
    if not words:
        raise XTimingImportError("The Lyrics track's word layer is empty.")

    if len(layers) >= 3:
        phonemes = _parse_marks(layers[2])
    else:
        phonemes = []

    if not phonemes:
        phonemes = _derive_phonemes_from_words(words)

    return words, phonemes


def _derive_phonemes_from_words(words: list[dict]) -> list[dict]:
    """Fallback when a .xtiming Lyrics track has no phoneme layer: derive one
    from the words via the same cmudict-based decomposition WhisperX
    alignment already uses.

    A separate function (rather than inlined) so tests can monkeypatch it
    without needing the optional ``nltk`` dependency installed.
    """
    from src.analyzer.phonemes import distribute_phoneme_timing, word_to_papagayo
    try:
        import nltk
        nltk.download("cmudict", quiet=True)
        from nltk.corpus import cmudict as _cmudict
        cmu_dict = _cmudict.dict()
    except ImportError as exc:
        raise XTimingImportError(
            "This file has no phoneme layer, and nltk (needed to derive "
            "phonemes from the words) isn't installed here. Export the "
            "Lyrics track's phoneme layer too (right-click the Lyrics "
            "track in xLights -> break words into phonemes) before "
            "uploading."
        ) from exc
    phonemes: list[dict] = []
    for w in words:
        papagayo = word_to_papagayo(w["label"], cmu_dict)
        phonemes.extend(
            m.to_dict() for m in
            distribute_phoneme_timing(papagayo, w["start_ms"], w["end_ms"])
        )
    return phonemes
