"""Integration tests for the full hierarchy → SongStory pipeline.

Covers build_song_story(hierarchy, audio_path) end-to-end using the
deterministic fixture dict (no real audio file needed).

These tests MUST FAIL before implementation (module does not exist yet).
"""
from __future__ import annotations

import math

import pytest

from tests.fixtures.story_fixture import make_hierarchy_dict, FIXTURE_DURATION_MS

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

VALID_ROLES = {
    "intro",
    "verse",
    "pre_chorus",
    "chorus",
    "post_chorus",
    "bridge",
    "instrumental_break",
    "climax",
    "ambient_bridge",
    "outro",
    "interlude",
}

VALID_ENERGY_ARCS = {"ramp", "arch", "flat", "valley", "sawtooth", "bookend"}
VALID_TEMPO_STABILITIES = {"steady", "variable", "free"}


@pytest.fixture(scope="module")
def story():
    hier = make_hierarchy_dict()
    return build_song_story(hier, AUDIO_PATH)


# ── Top-level structure ────────────────────────────────────────────────────────

def test_all_required_top_level_keys_present(story):
    missing = REQUIRED_TOP_LEVEL_KEYS - story.keys()
    assert not missing, f"Missing top-level keys: {missing}"


# ── sections ───────────────────────────────────────────────────────────────────

def test_sections_non_empty(story):
    assert len(story["sections"]) > 0


def test_sections_contiguous_no_gaps_or_overlaps(story):
    """Sections must tile the song timeline with no gaps or overlaps (1 ms tolerance)."""
    sections = story["sections"]
    for i in range(len(sections) - 1):
        end_n = sections[i]["end"]
        start_next = sections[i + 1]["start"]
        delta_ms = abs(end_n - start_next) * 1000
        assert delta_ms <= 1, (
            f"Contiguity violation between section {i} and {i+1}: "
            f"end={end_n:.4f}s, next_start={start_next:.4f}s, gap={delta_ms:.3f}ms"
        )


def test_sections_have_valid_roles(story):
    for sec in story["sections"]:
        assert sec["role"] in VALID_ROLES, (
            f"Section {sec.get('id')} has unexpected role: {sec['role']!r}"
        )


def test_sections_lighting_active_tiers_non_empty(story):
    for sec in story["sections"]:
        tiers = sec["lighting"]["active_tiers"]
        assert isinstance(tiers, list) and len(tiers) > 0, (
            f"Section {sec.get('id')} has empty active_tiers"
        )


def test_sections_lighting_brightness_ceiling_in_range(story):
    for sec in story["sections"]:
        bc = sec["lighting"]["brightness_ceiling"]
        assert 0.0 <= bc <= 1.0, (
            f"Section {sec.get('id')} brightness_ceiling {bc} outside [0.0, 1.0]"
        )


# ── review ─────────────────────────────────────────────────────────────────────

def test_review_status_is_draft(story):
    assert story["review"]["status"] == "draft"


# ── stems ──────────────────────────────────────────────────────────────────────

def test_stems_sample_rate_hz_equals_2(story):
    assert story["stems"]["sample_rate_hz"] == 2


def test_all_stem_arrays_same_length(story):
    """All stem RMS arrays must have length == ceil(duration_seconds * 2)."""
    duration_seconds = FIXTURE_DURATION_MS / 1000
    expected_len = math.ceil(duration_seconds * 2)

    stems_dict = story["stems"]
    stem_names = ["drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"]

    lengths = {}
    for name in stem_names:
        if name in stems_dict and "rms" in stems_dict[name]:
            lengths[name] = len(stems_dict[name]["rms"])

    assert lengths, "No stem RMS arrays found in story['stems']"

    unique_lengths = set(lengths.values())
    assert len(unique_lengths) == 1, (
        f"Stem RMS arrays have inconsistent lengths: {lengths}"
    )

    actual_len = unique_lengths.pop()
    assert actual_len == expected_len, (
        f"Stem array length {actual_len} != expected {expected_len} "
        f"(duration={duration_seconds}s * 2)"
    )


# ── moments ────────────────────────────────────────────────────────────────────

def test_moments_sorted_by_time(story):
    times = [m["time"] for m in story["moments"]]
    assert times == sorted(times), "Moments are not sorted by time"


def test_moment_section_ids_reference_existing_sections(story):
    """Every moment's section_id must point to an existing section id."""
    section_ids = {s["id"] for s in story["sections"]}
    for m in story["moments"]:
        assert m["section_id"] in section_ids, (
            f"Moment {m.get('id')} references unknown section_id {m['section_id']!r}"
        )


# ── global properties ──────────────────────────────────────────────────────────

def test_global_tempo_bpm_positive(story):
    assert story["global"]["tempo_bpm"] > 0


def test_global_energy_arc_valid(story):
    arc = story["global"]["energy_arc"]
    assert arc in VALID_ENERGY_ARCS, (
        f"energy_arc {arc!r} not in valid set {VALID_ENERGY_ARCS}"
    )


def test_global_vocal_coverage_in_range(story):
    vc = story["global"]["vocal_coverage"]
    assert 0.0 <= vc <= 1.0, f"vocal_coverage {vc} outside [0.0, 1.0]"


def test_global_tempo_stability_valid(story):
    ts = story["global"]["tempo_stability"]
    assert ts in VALID_TEMPO_STABILITIES, (
        f"tempo_stability {ts!r} not in valid set {VALID_TEMPO_STABILITIES}"
    )
