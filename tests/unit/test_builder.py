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
    assert story["schema_version"] == "1.1.0"


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


# ── title/artist override ───────────────────────────────────────────────────────

def test_title_override_wins_over_filename_fallback(hierarchy):
    """AUDIO_PATH has no ID3 tags, so title normally falls back to the
    filename stem — an explicit override must win over that fallback."""
    result = build_song_story(hierarchy, AUDIO_PATH, title_override="Real Title")
    assert result["song"]["title"] == "Real Title"


def test_artist_override_wins_over_unknown_fallback(hierarchy):
    """AUDIO_PATH has no ID3 tags, so artist normally falls back to
    'Unknown' — an explicit override must win over that fallback."""
    result = build_song_story(hierarchy, AUDIO_PATH, artist_override="Real Artist")
    assert result["song"]["artist"] == "Real Artist"


def test_no_override_keeps_existing_fallback_behavior(hierarchy):
    """Omitting the override params must not change existing behavior."""
    result = build_song_story(hierarchy, AUDIO_PATH)
    assert result["song"]["title"] == "fixture_song"
    assert result["song"]["artist"] == "Unknown"


def test_blank_override_does_not_clobber_fallback(hierarchy):
    """An empty-string override (e.g. an unmodified form field) must not
    stomp the filename/ID3-derived value with an empty title."""
    result = build_song_story(hierarchy, AUDIO_PATH, title_override="", artist_override="")
    assert result["song"]["title"] == "fixture_song"
    assert result["song"]["artist"] == "Unknown"


def test_lyrics_text_override_populates_lyrics_without_network_fetch(hierarchy, monkeypatch):
    """A cached lyrics_text_override (e.g. from a prior Check Lyrics call)
    must populate story['lyrics'] directly, without a fresh synced-lyrics
    network fetch — the actual analyze pass should reuse a confirmed-good
    result rather than risk a flaky provider giving a different one."""
    from src.analyzer import synced_lyrics as sl

    def _should_not_be_called(title, artist):
        raise AssertionError("fetch_synced_lyrics should not be called when lyrics_text_override is set")

    monkeypatch.setattr(sl, "fetch_synced_lyrics", _should_not_be_called)
    lrc = "[00:01.00]cached line one\n[00:03.00]cached line two\n"
    result = build_song_story(hierarchy, AUDIO_PATH, lyrics_text_override=lrc)
    assert [line["text"] for line in result["lyrics"]] == ["cached line one", "cached line two"]


def test_lyrics_text_found_true_for_pasted_plain_text_with_no_timing(hierarchy):
    """Plain pasted text (no LRC timestamps) produces a chorus_body for
    section detection but zero timed lyric lines -- lyrics_text_found must
    still report True so the Timeline can tell this apart from a genuine
    'nothing found' case (both would otherwise show empty result['lyrics']).
    Needs an actually-repeating 2-line block (find_chorus_body's default
    min_repeats=2, block_size=2), not just a single repeated line."""
    plain_text = "\n".join([
        "verse line one", "verse line two",
        "chorus line repeats", "next chorus line",
        "verse line three",
        "chorus line repeats", "next chorus line",
    ])
    result = build_song_story(hierarchy, AUDIO_PATH, lyrics_text_override=plain_text)
    assert result["lyrics"] == []
    assert result["lyrics_text_found"] is True


def test_lyrics_text_found_false_when_nothing_available(hierarchy, monkeypatch):
    from src.analyzer import synced_lyrics as sl

    monkeypatch.setattr(sl, "fetch_synced_lyrics", lambda title, artist: None)
    result = build_song_story(hierarchy, AUDIO_PATH)
    assert result["lyrics"] == []
    assert result["lyrics_text_found"] is False


def test_lyrics_cache_path_writes_disk_cache_on_first_fetch(hierarchy, monkeypatch, tmp_path):
    """When lyrics_cache_path is supplied, a fresh fetch's result is
    persisted to disk keyed by the hierarchy's own source_hash."""
    from src.analyzer import synced_lyrics as sl

    fetch_calls = []

    def _fetch(title, artist):
        fetch_calls.append((title, artist))
        return "[00:01.00]fetched line one\n"

    monkeypatch.setattr(sl, "fetch_synced_lyrics", _fetch)
    cache_path = tmp_path / "song_synced_lyrics.json"
    result = build_song_story(hierarchy, AUDIO_PATH, lyrics_cache_path=cache_path)

    assert len(fetch_calls) == 1
    assert [line["text"] for line in result["lyrics"]] == ["fetched line one"]
    hit, cached_text = sl.load_cached_lyrics_text(cache_path, FIXTURE_HASH)
    assert hit is True
    assert cached_text == "[00:01.00]fetched line one\n"


def test_lyrics_cache_path_reuses_cached_text_without_refetching(hierarchy, monkeypatch, tmp_path):
    """A second build_song_story call for the same source_hash must reuse
    the disk-cached lyrics text instead of hitting the network again --
    this is the actual determinism fix (2026-08-08)."""
    from src.analyzer import synced_lyrics as sl

    cache_path = tmp_path / "song_synced_lyrics.json"
    sl.save_cached_lyrics_text(
        cache_path, FIXTURE_HASH, "Title", "Artist", "[00:01.00]cached line one\n",
    )

    def _should_not_be_called(title, artist):
        raise AssertionError("fetch_synced_lyrics should not be called on a cache hit")

    monkeypatch.setattr(sl, "fetch_synced_lyrics", _should_not_be_called)
    result = build_song_story(hierarchy, AUDIO_PATH, lyrics_cache_path=cache_path)
    assert [line["text"] for line in result["lyrics"]] == ["cached line one"]


def test_lyrics_cache_path_ignored_when_lyrics_text_override_given(hierarchy, monkeypatch, tmp_path):
    """An explicit Check-Lyrics override still wins over the disk cache, and
    is never written into it (that cache is owned by the automatic-fetch
    path only)."""
    from src.analyzer import synced_lyrics as sl

    def _should_not_be_called(title, artist):
        raise AssertionError("fetch_synced_lyrics should not be called when override is set")

    monkeypatch.setattr(sl, "fetch_synced_lyrics", _should_not_be_called)
    cache_path = tmp_path / "song_synced_lyrics.json"
    lrc = "[00:01.00]override line one\n"
    result = build_song_story(
        hierarchy, AUDIO_PATH, lyrics_text_override=lrc, lyrics_cache_path=cache_path,
    )
    assert [line["text"] for line in result["lyrics"]] == ["override line one"]
    assert not cache_path.exists()


# ---------------------------------------------------------------------------
# "qm_boundary" placeholder must not count as a real repetition label
# ---------------------------------------------------------------------------

def _qm_boundary_bug_hierarchy():
    """9 raw sections, 10s each (90s song): 'A' repeats 3x with 'qm_boundary'
    placeholders interleaved between each repeat, 'B' repeats 2x, 'N1' once
    (non-vocal outro). 'qm_boundary'-labeled spans are deliberately given
    HIGHER energy than the real 'A' spans -- if "qm_boundary" is wrongly
    treated as a real repeating label (pre-fix), it ties 'A' at count=3 and
    wins the energy tie-break as chorus_label, so no 'A' section is ever
    classified chorus. Post-fix, 'qm_boundary' positions correctly fall back
    to the preceding real label ('A'), giving 'A' an unambiguous count=6
    with no tie at all -- confirmed 2026-08-08 as the real-world cause of a
    14/9/11/7-section swing between identical-audio analyze runs whose raw
    boundaries only shifted by tens of ms (see
    docs/segment-classification-changelog.md).
    """
    from tests.fixtures.story_fixture import make_hierarchy_dict

    d = make_hierarchy_dict(duration_ms=90_000)
    d["sections"] = [
        {"time_ms": 0, "label": "A"},
        {"time_ms": 10_000, "label": "qm_boundary"},
        {"time_ms": 20_000, "label": "A"},
        {"time_ms": 30_000, "label": "qm_boundary"},
        {"time_ms": 40_000, "label": "A"},
        {"time_ms": 50_000, "label": "qm_boundary"},
        {"time_ms": 60_000, "label": "B"},
        {"time_ms": 70_000, "label": "B"},
        {"time_ms": 80_000, "label": "N1"},
    ]

    def _energy_at(t_sec: float) -> float:
        if t_sec < 60:
            # A: 0-10, 20-30, 40-50 = 0.5; qm_boundary: 10-20, 30-40, 50-60 = 0.9
            return 0.9 if int(t_sec // 10) % 2 == 1 else 0.5
        if t_sec < 80:
            return 0.3  # B
        return 0.1  # N1 (outro)

    def _vocals_at(t_sec: float) -> float:
        return 0.6 if t_sec < 80 else 0.0  # N1 section is non-vocal

    frames = 900  # 90s * 10fps
    d["energy_curves"] = {
        "full_mix": {
            "sample_rate": 10.0,
            "values": [round(_energy_at(i / 10), 3) for i in range(frames)],
        },
        "vocals": {
            "sample_rate": 10.0,
            "values": [round(_vocals_at(i / 10), 3) for i in range(frames)],
        },
    }
    return d


def test_qm_boundary_placeholder_not_counted_as_repeating_label():
    hierarchy = _qm_boundary_bug_hierarchy()
    result = build_song_story(hierarchy, AUDIO_PATH)
    sections = result["sections"]

    # The 3 real 'A' spans must all end up inside chorus-role section(s) --
    # they must NOT lose the chorus tie-break to the meaningless
    # 'qm_boundary' placeholder despite it having higher raw energy.
    a_span_midpoints_ms = [5_000, 25_000, 45_000]
    for t_ms in a_span_midpoints_ms:
        matching = [s for s in sections if s["start"] * 1000 <= t_ms < s["end"] * 1000]
        assert matching, f"no section covers t={t_ms}ms"
        assert matching[0]["role"] == "chorus", (
            f"t={t_ms}ms (a real 'A' repeat) got role {matching[0]['role']!r}, "
            "expected 'chorus' -- 'qm_boundary' likely won the chorus "
            "tie-break instead of the real repeating label"
        )
