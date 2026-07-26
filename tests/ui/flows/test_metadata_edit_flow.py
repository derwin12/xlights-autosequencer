"""Metadata override flow: edit artist/title on the analyze-screen banner,
click Save & Refresh, confirm the override persists server-side.

This flow catches regressions in:
- Input wiring on `metadata-artist` / `metadata-title` fields
- The PATCH /api/v1/songs/<id>/metadata endpoint + response handling
- Persistence of overrides in the library/session storage

Smoke-level: no analyzer content assertions.

Note: the metadata row is button-triggered (`metadata-save-btn`), not
auto-saved on blur, and a successful save re-triggers a full analysis run
rather than showing a lightweight "saved" toast (handleSaveMetadata resets
the analysis state so the pipeline re-runs with the corrected metadata) --
so this test confirms the save via the PATCH response and server-side
persistence, not a transient UI indicator.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.ui, pytest.mark.slow]


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_metadata_artist_override_persists(
    page: Page, base_url: str, fixture_mp3: Path, snapshot
) -> None:
    page.goto(base_url)

    library_root = page.get_by_test_id("library-screen").or_(
        page.get_by_test_id("library-empty-drop")
    ).first
    expect(library_root).to_be_visible(timeout=10000)

    # Upload fresh fixture — library starts empty via autouse fixture.
    page.get_by_test_id("library-file-input").set_input_files(str(fixture_mp3))
    expect(page.get_by_test_id("analyze-screen").first).to_be_visible(timeout=30000)

    # Banner must render before we probe its inputs.
    banner = page.get_by_test_id("metadata-banner")
    expect(banner).to_be_visible(timeout=10000)

    artist_input = page.get_by_test_id("metadata-artist")
    expect(artist_input).to_be_visible()
    snapshot("banner-before-edit")

    # Replace whatever the ID3-derived artist is with a known test value.
    # Wrap the Save & Refresh click in an expect_response context so we
    # don't race the PATCH completion before asserting UI state.
    new_artist = "Acceptance Gate Test Artist"
    artist_input.fill(new_artist)
    with page.expect_response(
        lambda r: "/metadata" in r.url and r.request.method == "PATCH",
        timeout=30000,
    ) as resp_info:
        page.get_by_test_id("metadata-save-btn").click()
    assert resp_info.value.ok, (
        f"PATCH /metadata failed: {resp_info.value.status} "
        f"{resp_info.value.status_text}"
    )

    # No error state.
    assert not page.get_by_test_id("metadata-save-error").is_visible()
    snapshot("banner-after-save")

    # Verify the input's current value matches what we saved. A successful
    # save re-triggers analysis (screen transitions to the live-analysis
    # view) rather than showing a "saved" toast, but the metadata banner and
    # its inputs render in that view too, retaining the same React state.
    expect(artist_input).to_have_value(new_artist)

    # Persistence check via API: hit GET /api/v1/library and confirm the
    # override is persisted server-side. This survives page reload since it
    # reads the same library.json that the UI rehydrates from. Avoids the
    # fragility of reload-then-rerender which depends on last_screen prefs.
    # patch_song_metadata (src/review/api/v1/library.py) overwrites the
    # song's plain "artist" field directly -- there is no separate
    # "override_artist" field in library.json (that name only exists as an
    # internal concept in build_song_story's title_override/artist_override,
    # not the API/library schema).
    import requests
    lib = requests.get(f"{base_url}/api/v1/library", timeout=5).json()
    songs = lib.get("songs", [])
    song = next((s for s in songs if s.get("artist") == new_artist), None)
    assert song is not None, (
        f"Override not persisted to library. Songs: "
        f"{[(s.get('song_id'), s.get('artist')) for s in songs]}"
    )
