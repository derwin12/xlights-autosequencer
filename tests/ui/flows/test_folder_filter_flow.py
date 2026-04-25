"""Folder toggle + filter pill interactions on the library screen.

Catches regressions in the library's client-side state machine:
- Folder collapse/expand (data-testid `folder-toggle-<id>`)
- Filter pills by analysis status (aria-label + data-active attribute)

These are pure UI state changes — no backend calls, no analyzer. Fast
(~5s per scenario) but catches React state-management breakage that the
upload flows don't exercise.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.ui, pytest.mark.slow]

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "cc0_music"


def _upload_via_api(base_url: str, mp3_path: Path) -> str:
    with mp3_path.open("rb") as f:
        resp = requests.post(
            f"{base_url}/api/v1/import",
            files={"audio": (mp3_path.name, f, "audio/mpeg")},
            timeout=30,
        )
    resp.raise_for_status()
    data = resp.json()
    return data.get("song_id") or data["song"]["song_id"]


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_folder_toggle_hides_and_reveals_songs(
    page: Page, base_url: str
) -> None:
    song_id = _upload_via_api(base_url, FIXTURES_DIR / "maple_leaf_rag.mp3")

    page.goto(base_url)
    expect(page.get_by_test_id("library-screen")).to_be_visible(timeout=10000)

    row = page.get_by_test_id(f"song-row-{song_id}")
    expect(row).to_be_visible(timeout=5000)

    # Songs land in the default "unfiled" folder on fresh upload.
    folder_toggle = page.get_by_test_id("folder-toggle-unfiled")
    expect(folder_toggle).to_be_visible(timeout=5000)

    # Click to collapse — song row should disappear.
    folder_toggle.click()
    expect(row).not_to_be_visible(timeout=5000)

    # Click again to expand — song row returns.
    folder_toggle.click()
    expect(row).to_be_visible(timeout=5000)


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_filter_pill_active_state_updates(
    page: Page, base_url: str
) -> None:
    _upload_via_api(base_url, FIXTURES_DIR / "maple_leaf_rag.mp3")

    page.goto(base_url)
    expect(page.get_by_test_id("library-screen")).to_be_visible(timeout=10000)

    # Filter pills are `<button role="button">` with aria-label per pill.
    # The "All" pill is the initial default; clicking a sibling changes active
    # state via data-active="true"|"false".
    all_pill = page.get_by_role("button", name="All").first
    analyzed_pill = page.get_by_role("button", name="Analyzed").first

    expect(all_pill).to_be_visible(timeout=5000)
    expect(analyzed_pill).to_be_visible(timeout=5000)

    # Initial state: "All" is active.
    expect(all_pill).to_have_attribute("data-active", "true")
    expect(analyzed_pill).to_have_attribute("data-active", "false")

    # Click "Analyzed" — active state moves.
    analyzed_pill.click()
    expect(analyzed_pill).to_have_attribute("data-active", "true", timeout=2000)
    expect(all_pill).to_have_attribute("data-active", "false")

    # Click back to "All" — active state returns.
    all_pill.click()
    expect(all_pill).to_have_attribute("data-active", "true", timeout=2000)
    expect(analyzed_pill).to_have_attribute("data-active", "false")
