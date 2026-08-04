"""Regression test for deriving bars from beats when bar-tracker coverage
is bad.

Every dedicated bar-tracking algorithm (qm_bars, librosa_bars,
madmom_downbeats) prefers the "drums" stem, same as the beat trackers -- so
on a song with a drum-less intro they can ALL share the same coverage gap
bug-760's beat fold-down fix specifically solved for beats. Coverage-aware
L2 selection alone (bug-764) can't rescue this because there's no
better-coverage bar candidate among them to promote. ``_derive_bars_from_beats``
is the fallback: build bars directly from the (more reliable) winning beat
track instead of trusting a separately-tracked, possibly-blind bar track.
"""
from __future__ import annotations

from src.analyzer.orchestrator import _derive_bars_from_beats
from src.analyzer.result import TimingMark, TimingTrack


def test_derives_every_fourth_beat_as_a_bar():
    beats = TimingTrack(
        name="beats", algorithm_name="qm_beats", element_type="beat",
        marks=[TimingMark(time_ms=i * 750, confidence=None) for i in range(12)],
        quality_score=0.9,
    )

    bars = _derive_bars_from_beats(beats)

    assert [m.time_ms for m in bars.marks] == [0, 3000, 6000]
    assert bars.element_type == "bar"
    assert bars.algorithm_name == "derived_from_beats"


def test_full_beat_coverage_produces_full_bar_coverage():
    """The whole point: a beat track with marks from song-start guarantees
    the derived bar track also starts at song-start, unlike a
    drums-stem-only bar tracker that might have nothing until the drums
    kick in.
    """
    beats = TimingTrack(
        name="beats", algorithm_name="qm_beats", element_type="beat",
        marks=[TimingMark(time_ms=t, confidence=None) for t in [731, 1486, 2252, 3030, 3820]],
        quality_score=0.9,
    )

    bars = _derive_bars_from_beats(beats)

    assert bars.marks[0].time_ms == 731
