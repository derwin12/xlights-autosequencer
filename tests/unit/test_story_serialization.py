"""Unit tests for song story serialization functions in src/story/builder.py.

Functions under test:
    write_song_story(story: dict, output_path: str) -> None
    load_song_story(path: str) -> dict
    write_edits(edits: dict, path: str) -> None
    load_edits(path: str) -> dict
    merge_story_with_edits(base: dict, edits: dict) -> dict

These tests MUST FAIL before implementation (module does not exist yet).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.story_fixture import make_hierarchy_dict, FIXTURE_DURATION_MS

# This import will fail until the module is implemented — that is intentional.
from src.story.builder import (
    build_song_story,
    load_edits,
    load_song_story,
    merge_story_with_edits,
    write_edits,
    write_song_story,
)

AUDIO_PATH = "/tmp/fixture_song.mp3"


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture()
def story():
    hier = make_hierarchy_dict()
    return build_song_story(hier, AUDIO_PATH)


@pytest.fixture()
def story_path(tmp_path, story):
    p = tmp_path / "test_story.json"
    write_song_story(story, str(p))
    return p


@pytest.fixture()
def loaded_story(story_path):
    return load_song_story(str(story_path))


# ── write_song_story / load_song_story ─────────────────────────────────────────

def test_write_song_story_creates_file(tmp_path, story):
    p = tmp_path / "out_story.json"
    write_song_story(story, str(p))
    assert p.exists(), "write_song_story did not create the output file"


def test_write_song_story_creates_valid_json(tmp_path, story):
    p = tmp_path / "out_story.json"
    write_song_story(story, str(p))
    with p.open() as fh:
        parsed = json.load(fh)  # raises if not valid JSON
    assert isinstance(parsed, dict)


def test_load_song_story_round_trip(story, loaded_story):
    """Data written by write_song_story must be identical when read back."""
    assert loaded_story == story


def test_schema_version_preserved_in_round_trip(story, loaded_story):
    assert loaded_story["schema_version"] == story["schema_version"]


def test_sections_count_preserved_in_round_trip(story, loaded_story):
    assert len(loaded_story["sections"]) == len(story["sections"])


def test_moments_preserved_in_round_trip(story, loaded_story):
    assert loaded_story["moments"] == story["moments"]


def test_moments_types_correct_after_round_trip(loaded_story):
    assert isinstance(loaded_story["moments"], list)


def test_stems_sample_rate_hz_is_2_after_round_trip(loaded_story):
    assert loaded_story["stems"]["sample_rate_hz"] == 2


def test_all_section_ids_preserved_in_round_trip(story, loaded_story):
    original_ids = {s["id"] for s in story["sections"]}
    loaded_ids = {s["id"] for s in loaded_story["sections"]}
    assert original_ids == loaded_ids


def test_load_song_story_raises_for_missing_file(tmp_path):
    missing = tmp_path / "nonexistent_story.json"
    with pytest.raises(FileNotFoundError):
        load_song_story(str(missing))


# ── write_edits / load_edits ───────────────────────────────────────────────────

def test_write_edits_creates_file(tmp_path):
    p = tmp_path / "test_edits.json"
    edits = {"section_edits": [], "moment_edits": [], "preferences": {}}
    write_edits(edits, str(p))
    assert p.exists(), "write_edits did not create the output file"


def test_load_edits_round_trip(tmp_path):
    p = tmp_path / "test_edits.json"
    edits = {
        "section_edits": [{"id": "s01", "action": "rename", "role": "verse"}],
        "moment_edits": [],
        "preferences": {"mood": "aggressive"},
    }
    write_edits(edits, str(p))
    loaded = load_edits(str(p))
    assert loaded == edits


# ── merge_story_with_edits ─────────────────────────────────────────────────────

@pytest.fixture()
def base_story():
    hier = make_hierarchy_dict()
    return build_song_story(hier, AUDIO_PATH)


def _first_section_id(story: dict) -> str:
    return story["sections"][0]["id"]


def test_merge_rename_action_updates_section_role(base_story):
    """An edits rename action must update the section role in the merged result."""
    sid = _first_section_id(base_story)
    edits = {
        "section_edits": [{"id": sid, "action": "rename", "role": "bridge"}],
        "moment_edits": [],
        "preferences": {},
    }
    merged = merge_story_with_edits(base_story, edits)
    target_section = next(s for s in merged["sections"] if s["id"] == sid)
    assert target_section["role"] == "bridge", (
        f"Expected section role 'bridge' after rename, got {target_section['role']!r}"
    )


def test_merge_dismissed_moment(base_story):
    """An edits dismissed=true must propagate to the merged moment."""
    # If the fixture produces no moments, build a synthetic story with one
    if not base_story["moments"]:
        pytest.skip("Fixture produces no moments; cannot test moment dismissal")

    mid = base_story["moments"][0]["id"]
    edits = {
        "section_edits": [],
        "moment_edits": [{"id": mid, "dismissed": True}],
        "preferences": {},
    }
    merged = merge_story_with_edits(base_story, edits)
    target_moment = next(m for m in merged["moments"] if m["id"] == mid)
    assert target_moment["dismissed"] is True


def test_merge_sets_review_status_reviewed(base_story):
    """Applying any edits file must set review.status to 'reviewed'."""
    edits = {
        "section_edits": [],
        "moment_edits": [],
        "preferences": {},
    }
    merged = merge_story_with_edits(base_story, edits)
    assert merged["review"]["status"] == "reviewed"


def test_merge_preferences_overwrite_base(base_story):
    """Preferences in edits must overwrite base preferences in the merged result."""
    edits = {
        "section_edits": [],
        "moment_edits": [],
        "preferences": {"mood": "ethereal", "intensity": 0.5},
    }
    merged = merge_story_with_edits(base_story, edits)
    assert merged["preferences"]["mood"] == "ethereal"
    assert merged["preferences"]["intensity"] == 0.5


def test_merge_does_not_mutate_base(base_story):
    """merge_story_with_edits must not mutate the original base dict."""
    import copy
    original_status = base_story["review"]["status"]
    original_sections_count = len(base_story["sections"])
    edits = {
        "section_edits": [],
        "moment_edits": [],
        "preferences": {"mood": "dark"},
    }
    _ = merge_story_with_edits(base_story, edits)
    assert base_story["review"]["status"] == original_status
    assert len(base_story["sections"]) == original_sections_count
