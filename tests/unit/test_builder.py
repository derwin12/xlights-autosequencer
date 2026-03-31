"""Unit tests for src/story/builder.py — build_song_story orchestration.

These tests MUST FAIL before implementation (module does not exist yet).
"""
from __future__ import annotations

import pytest

from tests.fixtures.story_fixture import make_hierarchy_dict, FIXTURE_DURATION_MS, FIXTURE_HASH

# This import will fail until the module is implemented — that is intentional.
from src.story.builder import build_song_story

AUDIO_PATH = "/tmp/fixture_song.mp3"

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "song",
    "global",
    "preferences",
    "sections",
    "moments",
    "stems",
    "review",
}

REQUIRED_SECTION_KEYS = {"id", "role", "start", "end", "character", "stems", "lighting", "overrides"}


# ── Helpers ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def hierarchy():
    return make_hierarchy_dict()


@pytest.fixture()
def story(hierarchy):
    return build_song_story(hierarchy, AUDIO_PATH)


# ── Return type ────────────────────────────────────────────────────────────────

def test_returns_dict(story):
    assert isinstance(story, dict)


def test_returns_non_none(hierarchy):
    result = build_song_story(hierarchy, AUDIO_PATH)
    assert result is not None


def test_returns_non_empty(story):
    assert len(story) > 0


# ── Top-level keys ─────────────────────────────────────────────────────────────

def test_top_level_keys_present(story):
    assert REQUIRED_TOP_LEVEL_KEYS.issubset(story.keys()), (
        f"Missing keys: {REQUIRED_TOP_LEVEL_KEYS - story.keys()}"
    )


def test_no_extra_unexpected_top_level_keys(story):
    # All required keys must be there; unknown extra keys are a schema drift warning but not failure.
    # This test simply verifies the mandatory set is complete.
    missing = REQUIRED_TOP_LEVEL_KEYS - story.keys()
    assert not missing


# ── schema_version ─────────────────────────────────────────────────────────────

def test_schema_version_is_string(story):
    assert isinstance(story["schema_version"], str)


def test_schema_version_value(story):
    assert story["schema_version"] == "1.0.0"


# ── sections ───────────────────────────────────────────────────────────────────

def test_sections_is_list(story):
    assert isinstance(story["sections"], list)


def test_sections_non_empty(story):
    assert len(story["sections"]) > 0


def test_sections_count_reasonable(story):
    count = len(story["sections"])
    assert 1 <= count <= 20, f"Sections count {count} outside expected range [1, 20]"


def test_sections_always_have_8_required_keys(story):
    for i, sec in enumerate(story["sections"]):
        missing = REQUIRED_SECTION_KEYS - sec.keys()
        assert not missing, f"Section {i} missing keys: {missing}"


def test_sections_ordered_by_start_time(story):
    starts = [sec["start"] for sec in story["sections"]]
    assert starts == sorted(starts), "Sections are not ordered by start time"


def test_sections_contiguous(story):
    """section[n]['end'] must equal section[n+1]['start'] within 1 ms tolerance."""
    sections = story["sections"]
    for i in range(len(sections) - 1):
        end_n = sections[i]["end"]
        start_next = sections[i + 1]["start"]
        delta_ms = abs(end_n - start_next) * 1000
        assert delta_ms <= 1, (
            f"Gap/overlap between section {i} and {i+1}: "
            f"end={end_n}, next_start={start_next}, delta_ms={delta_ms:.3f}"
        )


# ── Section sub-fields ─────────────────────────────────────────────────────────

def test_sections_have_character_energy_level(story):
    for i, sec in enumerate(story["sections"]):
        assert "energy_level" in sec["character"], (
            f"Section {i} character missing energy_level"
        )


def test_sections_have_stems_vocals_active(story):
    for i, sec in enumerate(story["sections"]):
        assert "vocals_active" in sec["stems"], (
            f"Section {i} stems missing vocals_active"
        )


def test_sections_have_lighting_active_tiers(story):
    for i, sec in enumerate(story["sections"]):
        assert "active_tiers" in sec["lighting"], (
            f"Section {i} lighting missing active_tiers"
        )


# ── moments ────────────────────────────────────────────────────────────────────

def test_moments_is_list(story):
    assert isinstance(story["moments"], list)


# moments may be empty for this fixture, but must be a list


# ── stems ──────────────────────────────────────────────────────────────────────

def test_stems_is_dict(story):
    assert isinstance(story["stems"], dict)


def test_stems_sample_rate_hz_equals_2(story):
    assert story["stems"]["sample_rate_hz"] == 2


# ── review ─────────────────────────────────────────────────────────────────────

def test_review_status_is_draft(story):
    assert story["review"]["status"] == "draft"


# ── song identity ──────────────────────────────────────────────────────────────

def test_song_source_hash_matches_hierarchy(hierarchy, story):
    assert story["song"]["source_hash"] == hierarchy["source_hash"]


# ── global properties ──────────────────────────────────────────────────────────

def test_global_tempo_bpm_within_5_percent_of_hierarchy(hierarchy, story):
    expected_bpm = hierarchy["estimated_bpm"]
    actual_bpm = story["global"]["tempo_bpm"]
    tolerance = expected_bpm * 0.05
    assert abs(actual_bpm - expected_bpm) <= tolerance, (
        f"tempo_bpm {actual_bpm} deviates more than 5% from hierarchy bpm {expected_bpm}"
    )


# ── robustness ─────────────────────────────────────────────────────────────────

def test_handles_hierarchy_with_no_solos_no_key_error():
    """Must not raise KeyError when solos dict is empty."""
    hier = make_hierarchy_dict()
    hier["solos"] = {}
    result = build_song_story(hier, AUDIO_PATH)
    assert isinstance(result, dict)
    assert "sections" in result


def test_handles_hierarchy_with_none_optional_fields():
    """Must not crash when optional hierarchy fields are None."""
    hier = make_hierarchy_dict()
    hier["bars"] = None
    hier["half_bars"] = None
    hier["eighth_notes"] = None
    hier["spectral_flux"] = None
    hier["key_changes"] = None
    hier["interactions"] = None
    result = build_song_story(hier, AUDIO_PATH)
    assert isinstance(result, dict)
