"""Failing TDD tests for src/story/moment_classifier.py.

These tests define the contract for classify_moments() and MUST fail before
the implementation exists. Do not create the implementation to make them pass
until the full module is ready.
"""
from __future__ import annotations

import re

import pytest

from tests.fixtures.story_fixture import (
    make_hierarchy_dict,
    FIXTURE_SECTIONS,
    FIXTURE_DURATION_MS,
)

# This import MUST fail until the module is implemented.
from src.story.moment_classifier import classify_moments  # noqa: E402


# ── Fixture helpers ────────────────────────────────────────────────────────────

# Sections as (start_ms, end_ms) tuples derived from the fixture boundaries.
FIXTURE_SECTION_TUPLES = [
    (FIXTURE_SECTIONS[i]["time_ms"], FIXTURE_SECTIONS[i + 1]["time_ms"])
    for i in range(len(FIXTURE_SECTIONS) - 1)
]


@pytest.fixture()
def hierarchy():
    return make_hierarchy_dict()


@pytest.fixture()
def moments(hierarchy):
    return classify_moments(hierarchy, FIXTURE_SECTION_TUPLES)


# ── Return structure ───────────────────────────────────────────────────────────

class TestReturnStructure:
    def test_returns_list(self, moments):
        assert isinstance(moments, list)

    def test_each_moment_is_dict(self, moments):
        for m in moments:
            assert isinstance(m, dict)

    def test_required_fields_present(self, moments):
        required = {"id", "time", "time_fmt", "section_id", "type", "stem",
                    "intensity", "description", "pattern", "rank", "dismissed"}
        for m in moments:
            missing = required - set(m.keys())
            assert not missing, f"Moment {m.get('id')} missing fields: {missing}"


# ── id format ─────────────────────────────────────────────────────────────────

class TestMomentIdFormat:
    ID_PATTERN = re.compile(r"^m\d{3}$")

    def test_ids_match_format(self, moments):
        for m in moments:
            assert self.ID_PATTERN.match(m["id"]), f"Bad id format: {m['id']!r}"

    def test_ids_are_sequential(self, moments):
        """IDs should be m001, m002, m003, ... with no gaps."""
        ids = [m["id"] for m in moments]
        for i, mid in enumerate(ids, start=1):
            assert mid == f"m{i:03d}", f"Expected m{i:03d}, got {mid!r}"

    def test_ids_are_unique(self, moments):
        ids = [m["id"] for m in moments]
        assert len(ids) == len(set(ids))


# ── Sorting ────────────────────────────────────────────────────────────────────

class TestSorting:
    def test_moments_sorted_by_time_ascending(self, moments):
        times = [m["time"] for m in moments]
        assert times == sorted(times), "Moments are not sorted by time ascending"


# ── Ranks ─────────────────────────────────────────────────────────────────────

class TestRanks:
    def test_ranks_are_integers(self, moments):
        for m in moments:
            assert isinstance(m["rank"], int)

    def test_ranks_are_unique(self, moments):
        ranks = [m["rank"] for m in moments]
        assert len(ranks) == len(set(ranks)), "Duplicate ranks found"

    def test_rank_1_assigned_to_highest_intensity(self, moments):
        if not moments:
            pytest.skip("No moments in fixture")
        rank1 = next(m for m in moments if m["rank"] == 1)
        max_intensity = max(m["intensity"] for m in moments)
        assert rank1["intensity"] == max_intensity

    def test_ranks_cover_1_to_n(self, moments):
        if not moments:
            pytest.skip("No moments in fixture")
        n = len(moments)
        ranks = sorted(m["rank"] for m in moments)
        assert ranks == list(range(1, n + 1)), f"Ranks do not form 1..{n}: {ranks}"


# ── dismissed defaults ─────────────────────────────────────────────────────────

class TestDismissed:
    def test_dismissed_defaults_to_false(self, moments):
        for m in moments:
            assert m["dismissed"] is False, f"Moment {m['id']} has dismissed={m['dismissed']}"


# ── Moment types produced ─────────────────────────────────────────────────────

class TestMomentTypes:
    VALID_TYPES = {
        "energy_surge", "energy_drop", "percussive_impact", "brightness_spike",
        "tempo_change", "silence", "vocal_entry", "vocal_exit",
        "texture_shift", "handoff",
    }

    def test_all_types_are_valid(self, moments):
        for m in moments:
            assert m["type"] in self.VALID_TYPES, f"Unknown type: {m['type']!r}"

    def test_energy_surge_moments_present(self, moments):
        """Fixture has energy impacts at 36000ms and 48000ms."""
        types = [m["type"] for m in moments]
        assert "energy_surge" in types

    def test_energy_drop_moments_present(self, moments):
        """Fixture has energy drop at 54000ms."""
        types = [m["type"] for m in moments]
        assert "energy_drop" in types

    def test_vocal_entry_moment_present(self, moments):
        """Fixture vocals go from 0.0 to 0.6 at 12000ms → vocal_entry."""
        types = [m["type"] for m in moments]
        assert "vocal_entry" in types

    def test_vocal_exit_moment_present(self, moments):
        """Fixture vocals drop from 0.6 to 0.0 at 54000ms → vocal_exit."""
        types = [m["type"] for m in moments]
        assert "vocal_exit" in types


# ── Energy surge at specific fixture timestamps ────────────────────────────────

class TestFixtureEnergyImpacts:
    def test_energy_surge_at_36000ms(self, moments):
        """Fixture energy_impacts contains an event at 36000ms."""
        surge_times = [m["time"] for m in moments if m["type"] == "energy_surge"]
        assert 36.0 in surge_times, f"No energy_surge at 36s; found: {surge_times}"

    def test_energy_surge_at_48000ms(self, moments):
        """Fixture energy_impacts contains an event at 48000ms."""
        surge_times = [m["time"] for m in moments if m["type"] == "energy_surge"]
        assert 48.0 in surge_times, f"No energy_surge at 48s; found: {surge_times}"

    def test_energy_drop_at_54000ms(self, moments):
        """Fixture energy_drops contains an event at 54000ms."""
        drop_times = [m["time"] for m in moments if m["type"] == "energy_drop"]
        assert 54.0 in drop_times, f"No energy_drop at 54s; found: {drop_times}"


# ── pattern ────────────────────────────────────────────────────────────────────

class TestPattern:
    VALID_PATTERNS = {"isolated", "plateau", "cascade", "double_tap", "scattered"}

    def test_patterns_are_valid(self, moments):
        for m in moments:
            assert m["pattern"] in self.VALID_PATTERNS, (
                f"Moment {m['id']} has invalid pattern: {m['pattern']!r}"
            )


# ── section_id references ─────────────────────────────────────────────────────

class TestSectionIdReferences:
    def test_all_section_ids_are_valid(self, moments):
        """Every moment's section_id must reference one of the sections passed in."""
        # Build a set of valid section IDs in the same way the implementation should
        # (s01, s02, s03, s04 for 4 sections)
        n = len(FIXTURE_SECTION_TUPLES)
        valid_ids = {f"s{i:02d}" for i in range(1, n + 1)}
        for m in moments:
            assert m["section_id"] in valid_ids, (
                f"Moment {m['id']} has unknown section_id: {m['section_id']!r}"
            )


# ── time_fmt ──────────────────────────────────────────────────────────────────

class TestTimeFmt:
    TIME_FMT_PATTERN = re.compile(r"^\d{2}:\d{2}\.\d{3}$")

    def test_time_fmt_matches_pattern(self, moments):
        for m in moments:
            assert self.TIME_FMT_PATTERN.match(m["time_fmt"]), (
                f"Moment {m['id']} has bad time_fmt: {m['time_fmt']!r}"
            )

    def test_time_fmt_consistent_with_time(self, moments):
        """time_fmt should encode the same value as 'time' (seconds)."""
        for m in moments:
            parts = m["time_fmt"].split(":")
            minutes = int(parts[0])
            sec_parts = parts[1].split(".")
            seconds = int(sec_parts[0])
            millis = int(sec_parts[1])
            total_sec = minutes * 60 + seconds + millis / 1000.0
            assert abs(total_sec - m["time"]) < 0.001, (
                f"Moment {m['id']} time/time_fmt mismatch: {m['time']} vs {m['time_fmt']}"
            )


# ── intensity ─────────────────────────────────────────────────────────────────

class TestIntensity:
    def test_intensity_is_float(self, moments):
        for m in moments:
            assert isinstance(m["intensity"], float)

    def test_intensity_positive(self, moments):
        for m in moments:
            assert m["intensity"] > 0.0


# ── description ───────────────────────────────────────────────────────────────

class TestDescription:
    def test_description_is_non_empty_string(self, moments):
        for m in moments:
            assert isinstance(m["description"], str)
            assert len(m["description"]) > 0


# ── silence moments ───────────────────────────────────────────────────────────

class TestSilenceMoments:
    def test_silence_moments_when_gaps_present(self):
        """When hierarchy has gaps, silence moments are produced."""
        import copy
        h = copy.deepcopy(make_hierarchy_dict())
        h["gaps"] = [{"time_ms": 20_000, "duration_ms": 500, "label": "gap"}]
        result = classify_moments(h, FIXTURE_SECTION_TUPLES)
        types = [m["type"] for m in result]
        assert "silence" in types


# ── No duplicate moments at same time with same type ──────────────────────────

class TestDeduplication:
    def test_no_duplicate_type_at_same_time(self, moments):
        seen = set()
        for m in moments:
            key = (round(m["time"], 3), m["type"])
            assert key not in seen, f"Duplicate moment: type={m['type']} at t={m['time']}"
            seen.add(key)
