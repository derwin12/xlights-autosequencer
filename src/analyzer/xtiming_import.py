"""Import a user-supplied .xtiming file's Lyrics track as a WhisperX override.

Lets a user who already has correct word/phoneme timing (typed directly into
xLights' own Lyrics timing track, or from another tool) skip WhisperX
transcription/alignment entirely — sidesteps the all-or-nothing fallback in
``PhonemeAnalyzer._align_with_lyrics`` (see cerebrum 2026-07-21: a single bad
patch of pasted-lyrics alignment can drag whole-song coverage below 50% and
silently discard the ENTIRE alignment for free-transcription "made up" words
instead).

Schema (matches xLights' own .xtiming export/import, confirmed against
``tests/fixtures/*.xtiming`` and real user-exported files): a ``<timing>``
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

xLights' "export just this one timing track" option instead produces the
``<timing>`` element as the document root directly, with no ``<timings>``
wrapper — also accepted::

    <timing name="<anything>" SourceVersion="2024.01">
      <EffectLayer> ... same 2-3 layers as above ... </EffectLayer>
    </timing>
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


def parse_xtiming_lyrics(xml_bytes: bytes) -> tuple[list[dict], list[dict], list[dict]]:
    """Return ``(words, phonemes, lines)`` mark dicts from a .xtiming file's Lyrics track(s).

    The Lyrics track is identified structurally (>=2 EffectLayers), not by
    name — see the module docstring. A ``<timing name="lyrics">`` (or
    containing "lyric") is preferred when multiple multi-layer candidates
    exist in the same file; with exactly one multi-layer ``<timing>``
    overall, that one is used regardless of its name.

    When exactly two candidates are lyric-named (a lead + featured/backup
    singer, each exported as its own timing track), both are imported and
    merged: words are tagged with a ``speaker`` key (0=lead, 1=backup) —
    the same convention :func:`src.analyzer.vocal_diarization.diarize_words`
    uses — so the existing lead/backup pipeline (``_split_words_by_speaker``
    in effect_placer.py, ``_attribute_phoneme_speakers`` in xsq_writer.py)
    picks them up exactly as if diarization had detected two voices. Which
    track is lead vs. backup is decided by name keywords ("lead" vs.
    "backup"/"background") when present, else by whichever track has more
    words (majority = lead, matching vocal_diarization's own majority-
    duration convention). More than two lyric-named candidates is
    ambiguous — only lead+backup (two voices) is supported.

    Raises ``XTimingImportError`` when the file is malformed, has no
    multi-layer timing track, or multiple ambiguous candidates.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise XTimingImportError(f"Not a valid .xtiming XML file: {exc}") from exc

    candidates = [t for t in root.findall("timing") if len(t.findall("EffectLayer")) >= 2]
    if root.tag == "timing" and len(root.findall("EffectLayer")) >= 2:
        # xLights' "export just this track" shape: the root element IS the
        # <timing> node, not a <timings> wrapper containing one or more
        # <timing> children.
        candidates.append(root)
    if not candidates:
        raise XTimingImportError(
            "No timing track with a word-level layer was found in this "
            ".xtiming file — break the phrase into words in xLights "
            "(right-click the Lyrics track) before exporting."
        )

    named = [t for t in candidates if "lyric" in (t.get("name") or "").lower()]
    if len(named) == 2:
        return _merge_lead_backup(named[0], named[1])
    if len(named) > 2:
        names = ", ".join(repr(t.get("name") or "") for t in named)
        raise XTimingImportError(
            f"Found {len(named)} lyric-named timing tracks ({names}) — at "
            "most two (lead + backup) are supported. Export just the lead "
            "and backup Lyrics tracks."
        )
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

    words, phonemes, lines = _extract_raw(lyrics_timing)
    if not words:
        raise XTimingImportError("The Lyrics track's word layer is empty.")
    if not phonemes:
        phonemes = _derive_phonemes_from_words(words)
    return words, phonemes, lines


def _extract_raw(timing: ET.Element) -> tuple[list[dict], list[dict], list[dict]]:
    """Parse a single ``<timing>`` element's (words, phonemes, lines) layers.

    Unlike :func:`parse_xtiming_lyrics`, does not raise on an empty word
    layer or derive missing phonemes — callers merging two tracks need the
    raw per-track content before deciding which combination is usable.
    """
    layers = timing.findall("EffectLayer")
    words = _parse_marks(layers[1]) if len(layers) >= 2 else []
    phonemes = _parse_marks(layers[2]) if len(layers) >= 3 else []
    # Layer 0 ("phrases") holds full lyric lines -- same data the Timeline's
    # LyricTrack shows from synced-lyrics fetches, just sourced from the
    # user's own already-correct xLights timing instead.
    lines = _parse_marks(layers[0]) if len(layers) >= 1 else []
    return words, phonemes, lines


def _is_track_a_lead(name_a: str | None, name_b: str | None, count_a: int, count_b: int) -> bool:
    """Decide which of two lyric-named tracks is the lead singer.

    Name keywords take priority ("lead" vs. "backup"/"background"); when
    neither name disambiguates, the track with more words wins, matching
    ``vocal_diarization._label_utterances``'s own majority-duration
    convention (more content = lead).
    """
    a_lower, b_lower = (name_a or "").lower(), (name_b or "").lower()
    a_lead, b_lead = "lead" in a_lower, "lead" in b_lower
    if a_lead and not b_lead:
        return True
    if b_lead and not a_lead:
        return False
    a_backup = "backup" in a_lower or "background" in a_lower
    b_backup = "backup" in b_lower or "background" in b_lower
    if a_backup and not b_backup:
        return False
    if b_backup and not a_backup:
        return True
    return count_a >= count_b


def _merge_lead_backup(
    track_a: ET.Element, track_b: ET.Element,
) -> tuple[list[dict], list[dict], list[dict]]:
    words_a, phonemes_a, lines_a = _extract_raw(track_a)
    words_b, phonemes_b, lines_b = _extract_raw(track_b)

    if _is_track_a_lead(track_a.get("name"), track_b.get("name"), len(words_a), len(words_b)):
        lead_words, lead_phonemes, lead_lines = words_a, phonemes_a, lines_a
        backup_words, backup_phonemes, backup_lines = words_b, phonemes_b, lines_b
    else:
        lead_words, lead_phonemes, lead_lines = words_b, phonemes_b, lines_b
        backup_words, backup_phonemes, backup_lines = words_a, phonemes_a, lines_a

    if not lead_words and not backup_words:
        raise XTimingImportError("Both lyric tracks' word layers are empty.")
    if not lead_phonemes and lead_words:
        lead_phonemes = _derive_phonemes_from_words(lead_words)
    if not backup_phonemes and backup_words:
        backup_phonemes = _derive_phonemes_from_words(backup_words)

    words = sorted(
        [{**w, "speaker": 0} for w in lead_words] + [{**w, "speaker": 1} for w in backup_words],
        key=lambda w: w["start_ms"],
    )
    phonemes = sorted(lead_phonemes + backup_phonemes, key=lambda p: p["start_ms"])
    lines = sorted(lead_lines + backup_lines, key=lambda m: m["start_ms"])
    return words, phonemes, lines


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
