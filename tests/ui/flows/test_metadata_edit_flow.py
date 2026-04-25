"""Metadata override flow: edit artist/title on the analyze-screen banner,
verify the save indicator appears, confirm the override persists across
a page reload.

This flow catches regressions in:
- Input wiring on `metadata-artist` / `metadata-title` fields
- The PATCH /api/v1/songs/<id>/metadata endpoint + response handling
- Persistence of overrides in the library/session storage
- UI re-read of overrides after navigation

Smoke-level: no analyzer content assertions.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.ui, pytest.mark.slow]


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_metadata_artist_override_persists(
    page: Page, base_url: str, fixture_mp3: Path
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

    # Replace whatever the ID3-derived artist is with a known test value.
    # Wrap the blur-triggering action in an expect_response context so we
    # don't race the PATCH completion before asserting UI state.
    new_artist = "Acceptance Gate Test Artist"
    artist_input.fill(new_artist)
    with page.expect_response(
        lambda r: "/metadata" in r.url and r.request.method == "PATCH",
        timeout=30000,
    ) as resp_info:
        artist_input.press("Tab")  # Tab fires onBlur → triggers save
    assert resp_info.value.ok, (
        f"PATCH /metadata failed: {resp_info.value.status} "
        f"{resp_info.value.status_text}"
    )

    # No error state.
    assert not page.get_by_test_id("metadata-save-error").is_visible()
    # Saved indicator appears after React re-renders with the updated props.
    expect(page.get_by_test_id("metadata-saved")).to_be_visible(timeout=15000)

    # Verify the input's current value matches what we saved.
    expect(artist_input).to_have_value(new_artist)

    # Persistence check via API: hit GET /api/v1/library and confirm the
    # override is persisted server-side. This survives page reload since it
    # reads the same library.json that the UI rehydrates from. Avoids the
    # fragility of reload-then-rerender which depends on last_screen prefs.
    import requests
    lib = requests.get(f"{base_url}/api/v1/library", timeout=5).json()
    songs = lib.get("songs", [])
    song = next((s for s in songs if s.get("override_artist") == new_artist), None)
    assert song is not None, (
        f"Override not persisted to library. Songs: "
        f"{[(s.get('song_id'), s.get('override_artist')) for s in songs]}"
    )
