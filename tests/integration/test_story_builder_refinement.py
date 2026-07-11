"""Integration tests for boundary-refinement wiring in build_song_story.

Exercises Step 15c of ``src/story/builder.py``: the call into
``src.story.boundary_refinement.refine_section_boundaries`` and the
plumbing that surfaces free-transcription word marks from a standalone
WhisperX pass (``_try_free_transcription``).

Fix 1 (merge short post_chorus tails) and Fix 2 (relabel/split a bridge
whose sung content opens with the chorus first-line hook) required
Genius-sourced forced-aligned text and a known chorus body; since the
Genius integration was removed (see
docs/segment-classification-changelog.md, 2026-07-11), those two fixes are
now permanently inactive — ``forced_words`` is always ``[]`` and
``chorus_body`` is always ``None``. Only Fix 3 (split a pre-vocal
instrumental lead-in off a vocal section) still has live capability,
sourced from ``_try_free_transcription`` instead of the retired Genius
subprocess.

``_try_free_transcription`` is mocked so the test runs without
``.venv-vamp`` / WhisperX / a real audio fixture. The point of this test is
the wiring, not the algorithm — algorithm correctness is covered by
``tests/unit/test_boundary_refinement.py``.
"""
from __future__ import annotations

import pytest

from src.story import builder as builder_mod
from src.story.builder import build_song_story
from tests.fixtures.story_fixture import make_hierarchy_dict


AUDIO_PATH = "/tmp/fixture_song.mp3"


@pytest.fixture()
def hierarchy():
    return make_hierarchy_dict()


def test_no_free_words_emits_empty_boundary_refinements_field(hierarchy, monkeypatch):
    """No free-transcription word marks: every section gets boundary_refinements: []."""
    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: [])

    story = build_song_story(hierarchy, AUDIO_PATH)
    assert story["schema_version"] == "1.1.0"
    for sec in story["sections"]:
        assert "boundary_refinements" in sec
        assert sec["boundary_refinements"] == []


def test_fix3_fires_for_late_vocal_entry(hierarchy, monkeypatch):
    """Synthetic free_words showing a vocal section starts late triggers Fix 3.

    The fixture hierarchy contains multiple sections; we feed free_words
    consistent with one of them having its first transcribed word > 5 s
    after the section start. Fix 3 should split it.
    """

    # First, build with no free words to discover what sections the fixture
    # produces. Then we know which one to target with synthetic free_words.
    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: [])

    baseline = build_song_story(hierarchy, AUDIO_PATH)

    # Pick a vocal section ≥ 10 s long so we can simulate a late entry.
    vocal_target = next(
        (
            s for s in baseline["sections"]
            if s["role"] in {"verse", "chorus", "pre_chorus", "post_chorus", "bridge"}
            and (s["end"] - s["start"]) >= 10.0
            and "instrumental" not in s["role"]
            and "break" not in s["role"]
        ),
        None,
    )
    if vocal_target is None:
        pytest.skip("fixture has no vocal section ≥ 10s — Fix 3 untriggerable")

    # First transcribed word lands 7 s after the section start.
    word_start_ms = int(round(vocal_target["start"] * 1000)) + 7000
    free_words = [
        {"label": "HELLO", "start_ms": word_start_ms, "end_ms": word_start_ms + 400},
        {"label": "WORLD", "start_ms": word_start_ms + 600, "end_ms": word_start_ms + 1000},
    ]

    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: free_words)
    refined = build_song_story(hierarchy, AUDIO_PATH)

    # Fix 3 should produce a new instrumental section preceding the vocal one.
    refinement_notes = [
        n
        for sec in refined["sections"]
        for n in sec.get("boundary_refinements", [])
    ]
    assert any(
        "first transcribed word" in n or "pre-vocal gap split off" in n
        for n in refinement_notes
    ), (
        f"expected Fix 3 note in refinements; got: {refinement_notes}"
    )

    # And there is at least one section with role=='instrumental' adjacent
    # to (or within) the original target span.
    has_synth_instrumental = any(
        s["role"] == "instrumental" for s in refined["sections"]
    )
    assert has_synth_instrumental, "expected a synthetic instrumental section after Fix 3"


def test_legacy_story_dict_section_from_dict_handles_missing_field(hierarchy, monkeypatch):
    """Section.from_dict tolerates legacy section dicts lacking the field."""
    from src.story.models import Section

    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: [])
    story = build_song_story(hierarchy, AUDIO_PATH)
    legacy_dict = dict(story["sections"][0])
    # Simulate a legacy story that predates the field.
    legacy_dict.pop("boundary_refinements", None)

    section = Section.from_dict(legacy_dict)
    assert section.boundary_refinements == []
    assert section.to_dict()["boundary_refinements"] == []
