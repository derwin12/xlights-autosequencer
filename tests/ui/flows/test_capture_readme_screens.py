"""Capture screenshots of every main UI screen for the README documentation.

Opt-in via `pytest -m readme_capture`. Loads a single CC0 fixture, walks
through Library → Drop → Analyze → Timeline → Theme → Export, captures
each at a representative state, and writes PNGs to `assets/screenshots/`
that the README references.

Re-run after any meaningful UI change to keep the screenshots fresh.
Diagnostic / docs only — not part of any gate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.ui, pytest.mark.slow, pytest.mark.readme_capture]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SHOT_DIR = REPO_ROOT / "assets" / "screenshots"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cc0_music" / "maple_leaf_rag.mp3"


@pytest.fixture(autouse=True)
def _ensure_dir() -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)


def _save(page: Page, name: str) -> Path:
    """Capture full-page PNG; return path."""
    path = SHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True, type="png")
    assert path.exists() and path.stat().st_size > 1000, f"empty screenshot: {path}"
    return path


def test_capture_all_readme_screens(page: Page, base_url: str) -> None:
    """Walk the full UI journey, screenshotting each main screen."""

    # ---- 1. Library — empty state -----------------------------------------
    page.goto(base_url)
    empty_drop = page.get_by_test_id("library-empty-drop")
    expect(empty_drop).to_be_visible(timeout=10000)
    _save(page, "01-library-empty")

    # ---- 2. Drop / Import — file picker visible ---------------------------
    # The library-empty-drop is the import target; capture it as the Drop screen.
    # (When the library has songs, the same flow uses the "+ Add" button.)
    _save(page, "02-drop-target")

    # Trigger upload via the file input.
    page.get_by_test_id("library-file-input").set_input_files(str(FIXTURE))

    # ---- 3. Analyze — analyzing in progress -------------------------------
    expect(page.get_by_test_id("analyze-screen").first).to_be_visible(timeout=30000)
    # Capture early — pipeline is still running, progress bars active.
    page.wait_for_timeout(2500)
    _save(page, "03-analyze-running")

    # ---- 3b. Analyze — completed ------------------------------------------
    analysis_complete = page.locator(
        '[data-testid="analyze-header-title"][data-analysis-complete="true"]'
    )
    expect(analysis_complete).to_be_visible(timeout=300_000)
    page.wait_for_timeout(1500)
    _save(page, "04-analyze-complete")

    # ---- 4. Timeline — full review screen ---------------------------------
    review_btn = page.get_by_role("button", name=re.compile(r"review timeline", re.I)).first
    expect(review_btn).to_be_visible(timeout=10000)
    review_btn.click()
    expect(page.get_by_text("ZOOM", exact=False).first).to_be_visible(timeout=15000)
    expect(page.get_by_text("WAVEFORM", exact=False).first).to_be_visible(timeout=5000)
    page.wait_for_timeout(1200)
    _save(page, "05-timeline")

    # ---- 5. Theme — section/theme assignment ------------------------------
    # The Chrome tab named "5 Theme" navigates to the theme screen.
    theme_tab = page.get_by_role("tab", name=re.compile(r"theme", re.I)).first
    expect(theme_tab).to_be_visible(timeout=5000)
    theme_tab.click()
    page.wait_for_timeout(1500)
    _save(page, "06-theme")

    # ---- 6. Export — export screen ---------------------------------------
    export_tab = page.get_by_role("tab", name=re.compile(r"export", re.I)).first
    expect(export_tab).to_be_visible(timeout=5000)
    export_tab.click()
    page.wait_for_timeout(1200)
    _save(page, "07-export")

    # ---- 7. Library — populated state -----------------------------------
    # Now that a song is imported, navigating back shows the populated library.
    library_tab = page.get_by_role("tab", name=re.compile(r"library", re.I)).first
    expect(library_tab).to_be_visible(timeout=5000)
    library_tab.click()
    page.wait_for_timeout(1200)
    _save(page, "08-library-populated")

    # All screens captured — end of journey.
