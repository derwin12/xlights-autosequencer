"""Unit tests for src/analyzer/drum_classifier.py.

Covers both classification strategies: the spectral-band fallback
(``classify_drum_events``, unchanged behavior) and the drumsep-stem
comparison classifier (``classify_drum_events_from_stems``, 2026-07-20).
"""
from __future__ import annotations

import numpy as np

from src.analyzer import drum_classifier
from src.analyzer.result import TimingMark, TimingTrack


def _track(*time_ms: int) -> TimingTrack:
    return TimingTrack(
        name="drums", algorithm_name="aubio_onset", element_type="onset",
        marks=[TimingMark(time_ms=t, confidence=1.0) for t in time_ms],
        quality_score=1.0, stem_source="drums",
    )


class TestClassifyDrumEventsFromStems:
    def test_loudest_stem_wins_kick(self):
        sr = 22050
        n = sr
        kick = np.ones(n, dtype=np.float32) * 0.9
        snare = np.ones(n, dtype=np.float32) * 0.1
        cymbals = np.ones(n, dtype=np.float32) * 0.1
        track = _track(0)
        drum_classifier.classify_drum_events_from_stems(
            track, kick, sr, snare, sr, cymbals, sr,
        )
        assert track.marks[0].label == "kick"

    def test_loudest_stem_wins_snare(self):
        sr = 22050
        n = sr
        kick = np.ones(n, dtype=np.float32) * 0.1
        snare = np.ones(n, dtype=np.float32) * 0.9
        cymbals = np.ones(n, dtype=np.float32) * 0.1
        track = _track(0)
        drum_classifier.classify_drum_events_from_stems(
            track, kick, sr, snare, sr, cymbals, sr,
        )
        assert track.marks[0].label == "snare"

    def test_loudest_stem_wins_hihat(self):
        sr = 22050
        n = sr
        kick = np.ones(n, dtype=np.float32) * 0.1
        snare = np.ones(n, dtype=np.float32) * 0.1
        cymbals = np.ones(n, dtype=np.float32) * 0.9
        track = _track(0)
        drum_classifier.classify_drum_events_from_stems(
            track, kick, sr, snare, sr, cymbals, sr,
        )
        assert track.marks[0].label == "hihat"

    def test_missing_stem_still_classifies_from_the_others(self):
        sr = 22050
        n = sr
        snare = np.ones(n, dtype=np.float32) * 0.9
        cymbals = np.ones(n, dtype=np.float32) * 0.1
        track = _track(0)
        drum_classifier.classify_drum_events_from_stems(
            track, None, sr, snare, sr, cymbals, sr,
        )
        assert track.marks[0].label == "snare"

    def test_all_stems_none_leaves_label_untouched(self):
        track = _track(0)
        track.marks[0].label = "preexisting"
        drum_classifier.classify_drum_events_from_stems(
            track, None, 22050, None, 22050, None, 22050,
        )
        assert track.marks[0].label == "preexisting"

    def test_empty_track_is_a_noop(self):
        track = _track()
        drum_classifier.classify_drum_events_from_stems(
            track, np.ones(100, dtype=np.float32), 22050,
            None, 22050, None, 22050,
        )
        assert track.marks == []

    def test_classifies_each_mark_independently(self):
        sr = 22050
        n = 2 * sr
        kick = np.zeros(n, dtype=np.float32)
        snare = np.zeros(n, dtype=np.float32)
        cymbals = np.zeros(n, dtype=np.float32)
        kick[:sr] = 0.9        # loud kick in the first second
        snare[sr:] = 0.9       # loud snare in the second second
        track = _track(0, 1000)
        drum_classifier.classify_drum_events_from_stems(
            track, kick, sr, snare, sr, cymbals, sr,
        )
        assert track.marks[0].label == "kick"
        assert track.marks[1].label == "snare"


class TestClassifyDrumEventsFallback:
    def test_low_frequency_dominant_labeled_kick(self):
        sr = 22050
        t = np.arange(sr) / sr
        low_freq_tone = 0.5 * np.sin(2 * np.pi * 60 * t).astype(np.float32)
        track = _track(0)
        drum_classifier.classify_drum_events(track, low_freq_tone, sr)
        assert track.marks[0].label == "kick"

    def test_high_frequency_dominant_labeled_hihat(self):
        sr = 22050
        t = np.arange(sr) / sr
        high_freq_tone = 0.5 * np.sin(2 * np.pi * 10_000 * t).astype(np.float32)
        track = _track(0)
        drum_classifier.classify_drum_events(track, high_freq_tone, sr)
        assert track.marks[0].label == "hihat"

    def test_no_marks_is_a_noop(self):
        track = _track()
        drum_classifier.classify_drum_events(track, np.ones(100, dtype=np.float32), 22050)
        assert track.marks == []

    def test_none_audio_is_a_noop(self):
        track = _track(0)
        drum_classifier.classify_drum_events(track, None, 22050)
        assert track.marks[0].label is None
