"""Unit tests for HierarchyResult data model (016-hierarchy-orchestrator)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analyzer.result import (
    HierarchyResult,
    InteractionResult,
    LeaderTrack,
    TimingMark,
    TimingTrack,
    ValueCurve,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_track(name: str, element_type: str, marks_ms: list[int], stem: str = "full_mix") -> TimingTrack:
    marks = [TimingMark(time_ms=t, confidence=None) for t in marks_ms]
    return TimingTrack(
        name=name, algorithm_name=name, element_type=element_type,
        marks=marks, quality_score=0.8, stem_source=stem,
    )


def _make_curve(name: str, stem: str = "full_mix") -> ValueCurve:
    return ValueCurve(name=name, stem_source=stem, fps=20, values=list(range(100)))


def _make_minimal_result() -> HierarchyResult:
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="/path/to/song.mp3",
        source_hash="abc123",
        duration_ms=180000,
        estimated_bpm=120.0,
    )


def _make_full_result() -> HierarchyResult:
    result = _make_minimal_result()
    result.energy_impacts = [TimingMark(time_ms=5000, confidence=None, label="impact")]
    result.energy_drops = [TimingMark(time_ms=10000, confidence=None, label="drop")]
    result.gaps = [TimingMark(time_ms=15000, confidence=None, label="gap", duration_ms=2000)]
    result.sections = [
        TimingMark(time_ms=0, confidence=None, label="A", duration_ms=30000),
        TimingMark(time_ms=30000, confidence=None, label="B", duration_ms=30000),
    ]
    result.bars = _make_track("qm_bars", "bar", list(range(0, 180000, 2000)))
    result.beats = _make_track("qm_beats", "beat", list(range(0, 180000, 500)))
    result.events = {
        "full_mix": _make_track("librosa_onsets", "onset", list(range(0, 180000, 250))),
        "drums": _make_track("aubio_onset_drums", "onset", list(range(0, 180000, 500)), "drums"),
    }
    result.energy_curves = {
        "full_mix": _make_curve("energy_full_mix", "full_mix"),
        "drums": _make_curve("energy_drums", "drums"),
    }
    result.spectral_flux = _make_curve("spectral_flux", "full_mix")
    result.chords = _make_track("chordino_chords", "harmonic", [0, 4000, 8000, 12000])
    # Add labels to chord marks
    result.chords.marks[0].label = "Am"
    result.chords.marks[1].label = "G"
    result.stems_available = ["full_mix", "drums", "bass"]
    result.capabilities = {"vamp": True, "madmom": False, "demucs": True}
    result.algorithms_run = ["librosa_bars", "qm_bars", "segmentino"]
    result.warnings = []
    return result


# ── Schema structure tests ─────────────────────────────────────────────────────

class TestHierarchyResultSchema:
    def test_schema_version_is_200(self):
        r = _make_minimal_result()
        assert r.schema_version == "2.0.0"

    def test_to_dict_top_level_keys(self):
        r = _make_full_result()
        d = r.to_dict()
        expected_keys = {
            "schema_version", "source_file", "source_hash", "duration_ms", "estimated_bpm",
            "energy_impacts", "energy_drops", "gaps", "sections",
            "bars", "beats", "events", "energy_curves", "spectral_flux",
            "chords", "key_changes", "interactions",
            "stems_available", "capabilities", "algorithms_run", "warnings",
        }
        assert expected_keys == set(d.keys())

    def test_from_dict_round_trip(self):
        r = _make_full_result()
        d = r.to_dict()
        r2 = HierarchyResult.from_dict(d)
        assert r2.schema_version == r.schema_version
        assert r2.source_hash == r.source_hash
        assert r2.duration_ms == r.duration_ms
        assert r2.estimated_bpm == r.estimated_bpm

    def test_json_serializable(self):
        r = _make_full_result()
        d = r.to_dict()
        json_str = json.dumps(d)
        data = json.loads(json_str)
        assert data["schema_version"] == "2.0.0"


# ── Value curve tests ─────────────────────────────────────────────────────────

class TestValueCurveInResult:
    def test_energy_curves_keyed_by_stem(self):
        r = _make_full_result()
        d = r.to_dict()
        assert isinstance(d["energy_curves"], dict)
        assert "full_mix" in d["energy_curves"]
        assert "drums" in d["energy_curves"]

    def test_value_curve_has_integer_values(self):
        r = _make_full_result()
        d = r.to_dict()
        curve = d["energy_curves"]["full_mix"]
        assert isinstance(curve["values"], list)
        assert all(isinstance(v, int) for v in curve["values"])

    def test_value_curve_round_trip(self):
        r = _make_full_result()
        d = r.to_dict()
        r2 = HierarchyResult.from_dict(d)
        assert "full_mix" in r2.energy_curves
        vc = r2.energy_curves["full_mix"]
        assert vc.fps == 20
        assert vc.values == list(range(100))

    def test_spectral_flux_round_trip(self):
        r = _make_full_result()
        d = r.to_dict()
        r2 = HierarchyResult.from_dict(d)
        assert r2.spectral_flux is not None
        assert isinstance(r2.spectral_flux.values, list)


# ── TimingMark label/duration tests ───────────────────────────────────────────

class TestTimingMarkFields:
    def test_timing_marks_have_time_ms_int(self):
        r = _make_full_result()
        d = r.to_dict()
        for mark in d["energy_impacts"]:
            assert isinstance(mark["time_ms"], int)

    def test_sections_have_label_and_duration(self):
        r = _make_full_result()
        d = r.to_dict()
        sections = d["sections"]
        assert len(sections) == 2
        assert sections[0]["label"] == "A"
        assert sections[0]["duration_ms"] == 30000
        assert isinstance(sections[0]["duration_ms"], int)

    def test_gaps_have_duration_ms(self):
        r = _make_full_result()
        d = r.to_dict()
        gaps = d["gaps"]
        assert len(gaps) == 1
        assert gaps[0]["label"] == "gap"
        assert gaps[0]["duration_ms"] == 2000

    def test_impacts_have_label(self):
        r = _make_full_result()
        d = r.to_dict()
        assert d["energy_impacts"][0]["label"] == "impact"

    def test_drops_have_label(self):
        r = _make_full_result()
        d = r.to_dict()
        assert d["energy_drops"][0]["label"] == "drop"

    def test_chord_marks_have_labels(self):
        r = _make_full_result()
        d = r.to_dict()
        chord_marks = d["chords"]["marks"]
        assert chord_marks[0]["label"] == "Am"
        assert chord_marks[1]["label"] == "G"

    def test_none_label_omitted_from_dict(self):
        mark = TimingMark(time_ms=1000, confidence=None, label=None, duration_ms=None)
        t = TimingTrack(name="t", algorithm_name="t", element_type="beat",
                        marks=[mark], quality_score=0.5)
        d = t.to_dict()
        assert "label" not in d["marks"][0]
        assert "duration_ms" not in d["marks"][0]


# ── Events structure tests ────────────────────────────────────────────────────

class TestEventsStructure:
    def test_events_keyed_by_stem(self):
        r = _make_full_result()
        d = r.to_dict()
        assert isinstance(d["events"], dict)
        assert "full_mix" in d["events"]
        assert "drums" in d["events"]

    def test_events_round_trip(self):
        r = _make_full_result()
        d = r.to_dict()
        r2 = HierarchyResult.from_dict(d)
        assert "full_mix" in r2.events
        assert isinstance(r2.events["full_mix"], TimingTrack)

    def test_events_stem_source_preserved(self):
        r = _make_full_result()
        d = r.to_dict()
        r2 = HierarchyResult.from_dict(d)
        assert r2.events["drums"].stem_source == "drums"


# ── Derived features pre-computed ────────────────────────────────────────────

class TestDerivedFeaturesPreComputed:
    def test_impacts_drops_gaps_in_json(self):
        """Derived features should be pre-computed, not requiring re-derivation."""
        r = _make_full_result()
        d = r.to_dict()
        # All present as top-level arrays (not nested inside energy_curves)
        assert isinstance(d["energy_impacts"], list)
        assert isinstance(d["energy_drops"], list)
        assert isinstance(d["gaps"], list)
        assert len(d["energy_impacts"]) > 0
        assert len(d["energy_drops"]) > 0
        assert len(d["gaps"]) > 0

    def test_derived_features_round_trip(self):
        r = _make_full_result()
        d = r.to_dict()
        r2 = HierarchyResult.from_dict(d)
        assert len(r2.energy_impacts) == len(r.energy_impacts)
        assert len(r2.energy_drops) == len(r.energy_drops)
        assert len(r2.gaps) == len(r.gaps)
        assert r2.gaps[0].duration_ms == 2000


# ── ValueCurve standalone tests ───────────────────────────────────────────────

class TestValueCurve:
    def test_duration_ms_property(self):
        vc = ValueCurve(name="test", stem_source="full_mix", fps=20, values=list(range(200)))
        assert vc.duration_ms == 10000  # 200 / 20 * 1000

    def test_round_trip(self):
        vc = ValueCurve(name="energy_drums", stem_source="drums", fps=20, values=[0, 50, 100])
        d = vc.to_dict()
        vc2 = ValueCurve.from_dict(d)
        assert vc2.name == vc.name
        assert vc2.fps == vc.fps
        assert vc2.values == vc.values


# ── TimingMark label/duration round-trip ─────────────────────────────────────

class TestTimingMarkRoundTrip:
    def test_label_round_trip_in_track(self):
        marks = [
            TimingMark(time_ms=0, confidence=None, label="A", duration_ms=5000),
            TimingMark(time_ms=5000, confidence=None, label="B", duration_ms=5000),
        ]
        track = TimingTrack(name="seg", algorithm_name="segmentino", element_type="structure",
                            marks=marks, quality_score=0.9)
        d = track.to_dict()
        track2 = TimingTrack.from_dict(d)
        assert track2.marks[0].label == "A"
        assert track2.marks[0].duration_ms == 5000
        assert track2.marks[1].label == "B"
