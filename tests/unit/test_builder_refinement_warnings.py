"""Unit tests for §7 — Step 15c capability-skip warnings.

``build_song_story`` emits a warning into ``story["refinement_warnings"]``
for each boundary-refinement fix that can't run:

- Fix 3 (split a pre-vocal instrumental lead-in off a vocal section) needs
  free-transcription word marks (``_try_free_transcription``, a standalone
  WhisperX pass).
- Fix 1 (merge short post_chorus tails) needs forced-aligned word marks,
  and Fix 2 (relabel/split a bridge whose sung content opens with the
  chorus first-line hook) needs a known chorus body — both sourced from
  ``src.analyzer.synced_lyrics.get_boundary_refinement_inputs`` since the
  Genius integration was removed (see
  docs/segment-classification-changelog.md, 2026-07-11 and the follow-up
  2026-07-11 "Fix 1/Fix 2 restored via syncedlyrics" entry).

These tests exercise the builder's Step 15c warning emission directly by
mocking ``_try_free_transcription`` and
``src.analyzer.synced_lyrics.get_boundary_refinement_inputs`` to vary
capability availability. All lyric/chorus text used is synthetic
placeholder text, never real song lyrics.
"""
from __future__ import annotations

import pytest

from src.analyzer import synced_lyrics
from src.story import builder as builder_mod
from src.story.builder import build_song_story
from tests.fixtures.story_fixture import make_hierarchy_dict


AUDIO_PATH = "/tmp/fixture_song.mp3"


@pytest.fixture()
def hierarchy():
    return make_hierarchy_dict()


@pytest.fixture(autouse=True)
def _no_synced_lyrics_by_default(monkeypatch):
    """Default every test to "no synced lyrics found" unless it opts in.

    Prevents accidental real network calls and keeps Fix 1/Fix 2 warning
    behavior deterministic for tests that only care about Fix 3.
    """
    monkeypatch.setattr(
        synced_lyrics, "get_boundary_refinement_inputs", lambda *a, **kw: ([], None, []),
    )


# ── Field always present ────────────────────────────────────────────────────────

def test_story_always_has_refinement_warnings_field(hierarchy, monkeypatch):
    """``refinement_warnings`` is always present in the story dict.

    With no free-transcription word marks, Fix 3 emits its capability-skip
    warning.
    """
    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: [])
    story = build_song_story(hierarchy, AUDIO_PATH)
    assert "refinement_warnings" in story
    assert any("Fix 3" in w for w in story["refinement_warnings"])


def test_free_words_present_emits_no_fix3_skip_warning(hierarchy, monkeypatch):
    """When free-transcription word marks are available: no Fix-3 skip warning."""
    free_words = [{"label": "HELLO", "start_ms": 1000, "end_ms": 1400}]
    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: free_words)
    story = build_song_story(hierarchy, AUDIO_PATH)
    assert not any("Fix 3" in w for w in story["refinement_warnings"])


def test_no_free_words_emits_fix3_skip_warning(hierarchy, monkeypatch):
    """When free word marks are empty → Fix 3 skipped, exactly one Fix-3 warning."""
    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: [])
    story = build_song_story(hierarchy, AUDIO_PATH)
    warnings = story["refinement_warnings"]
    fix3_warnings = [
        w for w in warnings if "Fix 3" in w and "no free-transcription" in w
    ]
    assert len(fix3_warnings) == 1, (
        f"expected one Fix-3 'no free-transcription' warning, got {warnings}"
    )


def test_synced_lyrics_present_emits_no_fix1_fix2_skip_warnings(hierarchy, monkeypatch):
    """When synced lyrics supply forced words + a chorus body: no Fix-1/Fix-2 skip warnings."""
    forced_words = [synced_lyrics.WordMark(label="PLACEHOLDER", start_ms=1000, end_ms=1400)]
    monkeypatch.setattr(
        synced_lyrics, "get_boundary_refinement_inputs",
        lambda *a, **kw: (forced_words, "la la placeholder chorus text", []),
    )
    story = build_song_story(hierarchy, AUDIO_PATH)
    warnings = story["refinement_warnings"]
    assert not any("Fix 1" in w for w in warnings)
    assert not any("Fix 2" in w for w in warnings)


def test_no_synced_lyrics_emits_fix1_and_fix2_skip_warnings(hierarchy):
    """Default fixture (no synced lyrics) → Fix 1 and Fix 2 both skipped."""
    story = build_song_story(hierarchy, AUDIO_PATH)
    warnings = story["refinement_warnings"]
    assert any("Fix 1" in w for w in warnings)
    assert any("Fix 2" in w for w in warnings)


# ── One-warning-per-skipped-fix-per-song (NOT per section) ──────────────────────

def test_warnings_are_per_song_not_per_section(hierarchy, monkeypatch):
    """The fixture has 4 sections; each skipped fix still gets exactly one
    warning entry — proving emission is per song, not per section."""
    monkeypatch.setattr(builder_mod, "_try_free_transcription", lambda *a, **kw: [])
    story = build_song_story(hierarchy, AUDIO_PATH)

    # The fixture must produce > 1 section for this assertion to be meaningful.
    assert len(story["sections"]) > 1
    # One warning per skipped fix (Fix 1, Fix 2, Fix 3) even though many
    # sections exist — not one per section.
    assert len(story["refinement_warnings"]) == 3


# ── refine_section_boundaries (the function) is silent on chorus_body=None ──────

def test_refine_function_with_no_chorus_body_does_not_raise() -> None:
    """The function itself does NOT emit warnings — it returns notes that
    describe what fired. The CALLER (builder.py Step 15c) is responsible
    for emitting capability-skip warnings to the song-level list. This test
    locks in that contract: passing chorus_body=None is a normal call that
    just causes Fix 2 to skip per-section. (builder.py now always passes
    chorus_body=None since Genius removal, but the function's contract is
    unchanged and still exercised directly here.)"""
    from src.story.boundary_refinement import refine_section_boundaries

    bridge = {
        "id": "s0", "role": "bridge", "label": "Bridge",
        "start": 100.0, "end": 130.0, "start_ms": 100_000, "end_ms": 130_000,
    }
    out, notes = refine_section_boundaries(
        [bridge], forced_words=[], free_words=[], chorus_body=None
    )
    # Section list unchanged, no relabel notes.
    assert out[0]["role"] == "bridge"
    assert not any("relabel" in n for n in notes)
    # The boundary_refinements field is always present (per §2).
    assert out[0]["boundary_refinements"] == []
