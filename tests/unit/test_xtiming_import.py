"""Tests for src.analyzer.xtiming_import.parse_xtiming_lyrics.

The Lyrics track is identified structurally (>=2 EffectLayers), not by
name -- a real user-exported .xtiming from XTimingWriter names the track
after the sanitized source filename (e.g. "shakethesnowglobegwenstefani"),
not "Lyrics" (discovered 2026-07-21 against a real file).
"""
from __future__ import annotations

import pytest

import src.analyzer.xtiming_import as xtiming_import
from src.analyzer.xtiming_import import XTimingImportError, parse_xtiming_lyrics


@pytest.fixture(autouse=True)
def _stub_phoneme_derivation(monkeypatch):
    """The nltk-based phoneme derivation is exercised separately (it needs
    the optional nltk dependency) -- stub it here so these tests focus on
    XML parsing/track-selection logic."""
    monkeypatch.setattr(
        xtiming_import, "_derive_phonemes_from_words",
        lambda words: [{"label": "etc", "start_ms": w["start_ms"], "end_ms": w["end_ms"]}
                       for w in words],
    )


def _xtiming(*timings: str) -> bytes:
    body = "\n".join(timings)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<timings>\n{body}\n</timings>'.encode()


_THREE_LAYER_UNNAMED = """
<timing name="shakethesnowglobegwenstefani" SourceVersion="2021.09">
    <EffectLayer>
        <Effect label="full phrase" starttime="0" endtime="2000" />
    </EffectLayer>
    <EffectLayer>
        <Effect label="HELLO" starttime="0" endtime="500" />
        <Effect label="WORLD" starttime="600" endtime="1000" />
    </EffectLayer>
    <EffectLayer>
        <Effect label="E" starttime="0" endtime="250" />
        <Effect label="L" starttime="250" endtime="500" />
        <Effect label="WQ" starttime="600" endtime="800" />
        <Effect label="etc" starttime="800" endtime="1000" />
    </EffectLayer>
</timing>
"""

_TWO_LAYER_NO_PHONEMES = """
<timing name="Lyrics" SourceVersion="2024.01">
    <EffectLayer>
        <Effect label="full phrase" starttime="0" endtime="2000" />
    </EffectLayer>
    <EffectLayer>
        <Effect label="HELLO" starttime="0" endtime="500" />
        <Effect label="WORLD" starttime="600" endtime="1000" />
    </EffectLayer>
</timing>
"""

_SINGLE_LAYER_ONLY = """
<timing name="beats" SourceVersion="2024.01">
    <EffectLayer>
        <Effect label="1" starttime="0" endtime="500" />
    </EffectLayer>
</timing>
"""

_FLOAT_TIMESTAMPS = """
<timing name="Lyrics" SourceVersion="2024.01">
    <EffectLayer>
        <Effect label="full phrase" starttime="0" endtime="2000" />
    </EffectLayer>
    <EffectLayer>
        <Effect label="HELLO" starttime="20390.0" endtime="20530.5" />
    </EffectLayer>
    <EffectLayer>
        <Effect label="E" starttime="20390.0" endtime="20530.5" />
    </EffectLayer>
</timing>
"""


class TestParseXTimingLyrics:
    def test_three_layer_track_not_named_lyrics(self):
        # Real-world case: XTimingWriter names the track after the sanitized
        # source filename, not "Lyrics" -- must still be found and parsed.
        words, phonemes = parse_xtiming_lyrics(_xtiming(_THREE_LAYER_UNNAMED))
        assert [w["label"] for w in words] == ["HELLO", "WORLD"]
        assert words[0] == {"label": "HELLO", "start_ms": 0, "end_ms": 500}
        assert [p["label"] for p in phonemes] == ["E", "L", "WQ", "etc"]

    def test_two_layer_track_derives_phonemes_from_words(self):
        words, phonemes = parse_xtiming_lyrics(_xtiming(_TWO_LAYER_NO_PHONEMES))
        assert [w["label"] for w in words] == ["HELLO", "WORLD"]
        assert len(phonemes) > 0
        assert phonemes[0]["start_ms"] == 0

    def test_single_layer_track_raises(self):
        with pytest.raises(XTimingImportError, match="word-level layer"):
            parse_xtiming_lyrics(_xtiming(_SINGLE_LAYER_ONLY))

    def test_no_timing_elements_raises(self):
        with pytest.raises(XTimingImportError, match="word-level layer"):
            parse_xtiming_lyrics(_xtiming())

    def test_malformed_xml_raises(self):
        with pytest.raises(XTimingImportError, match="Not a valid"):
            parse_xtiming_lyrics(b"not xml at all <<<")

    def test_float_timestamps_rounded_to_int_ms(self):
        # Real user file used float starttime/endtime values
        # (e.g. "163266.6666666667") -- confirmed 2026-07-21.
        words, _ = parse_xtiming_lyrics(_xtiming(_FLOAT_TIMESTAMPS))
        assert words[0]["start_ms"] == 20390
        assert words[0]["end_ms"] == round(20530.5)  # Python 3 banker's rounding

    def test_ambiguous_multiple_unnamed_multilayer_tracks_raises(self):
        with pytest.raises(XTimingImportError, match="Multiple timing tracks"):
            parse_xtiming_lyrics(_xtiming(
                _THREE_LAYER_UNNAMED.replace("shakethesnowglobegwenstefani", "trackA"),
                _THREE_LAYER_UNNAMED.replace("shakethesnowglobegwenstefani", "trackB"),
            ))

    def test_named_lyrics_track_preferred_among_multiple_candidates(self):
        other_track = (
            _THREE_LAYER_UNNAMED
            .replace("shakethesnowglobegwenstefani", "somethingelse")
            .replace("HELLO", "FOO").replace("WORLD", "BAR")
        )
        data = _xtiming(other_track, _TWO_LAYER_NO_PHONEMES)
        words, _ = parse_xtiming_lyrics(data)
        assert [w["label"] for w in words] == ["HELLO", "WORLD"]
