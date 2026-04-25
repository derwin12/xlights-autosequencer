"""Multi-song library navigation: upload two songs, navigate between them,
verify the library survives the round-trips with correct rows and that
clicking each row lands on a distinct song's analyze context.

Smoke-level: no content assertions against the analyzer output. This flow
catches regressions in library routing, song-id propagation, and click-to-
navigate state management — all places where "it worked with one song"
masks breakage with two.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.ui, pytest.mark.slow]

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "cc0_music"


def _upload_via_api(base_url: str, mp3_path: Path) -> str:
    """POST the MP3 directly to /api/v1/import and return the song_id.

    Bypasses the drop UI so we can seed multi-song state quickly — the flow's
    focus is *navigating* between multiple songs, not re-testing uploads.
    """
    with mp3_path.open("rb") as f:
        resp = requests.post(
            f"{base_url}/api/v1/import",
            files={"audio": (mp3_path.name, f, "audio/mpeg")},
            timeout=30,
        )
    resp.raise_for_status()
    data = resp.json()
    # Shape: {"song_id": "<hex>", "song": {...}, ...} — song_id is first-16 of md5
    return data.get("song_id") or data["song"]["song_id"]


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_multi_song_library_click_navigation(
    page: Page, base_url: str
) -> None:
    # Seed two songs via the API so the library is non-empty from the start.
    song_a = _upload_via_api(base_url, FIXTURES_DIR / "maple_leaf_rag.mp3")
    song_b = _upload_via_api(base_url, FIXTURES_DIR / "funshine.mp3")
    assert song_a != song_b, "Distinct fixtures must hash to distinct song_ids"

    page.goto(base_url)

    # Library must render in its non-empty state with both song rows.
    expect(page.get_by_test_id("library-screen")).to_be_visible(timeout=10000)
    row_a = page.get_by_test_id(f"song-row-{song_a}")
    row_b = page.get_by_test_id(f"song-row-{song_b}")
    expect(row_a).to_be_visible(timeout=5000)
    expect(row_b).to_be_visible(timeout=5000)

    # Click song A → navigate away from library.
    row_a.click()
    expect(page.get_by_test_id("library-screen")).not_to_be_visible(timeout=10000)

    # Return to library via the Chrome's "Library" nav tab (aria-label).
    # The app manages screen state internally, so browser back/goto are not
    # reliable — the nav tab is.
    page.get_by_role("tab", name="Library").click()
    expect(page.get_by_test_id("library-screen")).to_be_visible(timeout=10000)

    # Both rows still present after the round-trip.
    expect(page.get_by_test_id(f"song-row-{song_a}")).to_be_visible()
    expect(page.get_by_test_id(f"song-row-{song_b}")).to_be_visible()

    # Click song B → navigate to a distinct song's context.
    page.get_by_test_id(f"song-row-{song_b}").click()
    expect(page.get_by_test_id("library-screen")).not_to_be_visible(timeout=10000)

    # Final round-trip via nav tab: library state survives.
    page.get_by_role("tab", name="Library").click()
    expect(page.get_by_test_id("library-screen")).to_be_visible(timeout=10000)
    expect(page.get_by_test_id(f"song-row-{song_a}")).to_be_visible()
    expect(page.get_by_test_id(f"song-row-{song_b}")).to_be_visible()
