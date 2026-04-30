"""ID3 confirmation modal flow — drives the modal through Confirm / Correct
(with write-back checkbox) / Skip and emits a screenshot at each waypoint.

The modal fires in pre-flight before every analyze run (OpenSpec change
``lyric-anchored-boundary-refinement`` §6a). On a fresh upload it's the
first thing the user sees on the Analyze screen, so we can capture all
three states from a single test without needing to run the full pipeline.

Marked ``ui`` — runs under ``pytest -m ui`` and the PR-screenshots
workflow.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.ui, pytest.mark.slow]


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_id3_modal_three_states(
    page: Page, base_url: str, fixture_mp3: Path, snapshot
) -> None:
    page.goto(base_url)

    # Upload a CC0 fixture — the post-upload navigation lands on Analyze
    # which immediately fires the pre-flight ID3 confirmation modal.
    page.get_by_test_id("library-file-input").set_input_files(str(fixture_mp3))

    modal = page.get_by_test_id("id3-confirm-modal")
    expect(modal).to_be_visible(timeout=20000)
    snapshot("01-id3-modal-confirm")

    # Click Correct — surfaces editable inputs prefilled with the current
    # tags, plus the "save back to MP3" checkbox.
    page.get_by_test_id("id3-modal-correct").click()
    expect(page.get_by_test_id("id3-modal-input-title")).to_be_visible()
    page.get_by_test_id("id3-modal-input-title").fill("Corrected Title")
    page.get_by_test_id("id3-modal-input-artist").fill("Corrected Artist")
    page.get_by_test_id("id3-modal-write-back").check()
    snapshot("02-id3-modal-correct")

    # Back to the confirm view (also tests state reset).
    page.get_by_test_id("id3-modal-correct-cancel").click()
    expect(page.get_by_test_id("id3-modal-confirm")).to_be_visible()
    snapshot("03-id3-modal-confirm-after-back")

    # Skip dismisses the modal and the analyzer proceeds with skip_genius=True.
    page.get_by_test_id("id3-modal-skip").click()
    expect(modal).not_to_be_visible(timeout=5000)
    snapshot("04-id3-modal-dismissed")
