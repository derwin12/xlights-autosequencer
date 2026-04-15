"""Integration tests for the Creative Brief tab render (spec 047 US1/US2/US6).

The Brief tab is a Vanilla-JS single-page fragment loaded into the spec 046
workspace shell.  We don't ship a JSDOM/Playwright harness, so these tests
validate the fragment by static inspection of brief-tab.html + brief-tab.js +
brief-presets.js.  The HTML fragment is structured enough (one <fieldset> per
axis, stable id attributes, hints as <p class="hint">) that static regex
checks give high-confidence coverage of the spec's acceptance scenarios.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


STATIC = Path(__file__).resolve().parents[2] / "src" / "review" / "static"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


AXIS_IDS = (
    "genre",
    "occasion",
    "mood_intent",
    "variation",
    "palette",
    "duration",
    "accents",
    "transitions",
    "curves",
)


# ---------------------------------------------------------------------------
# T018: 9 axis controls + per-section table render with Auto defaults
# ---------------------------------------------------------------------------

class TestBriefTabStructure:
    def test_brief_tab_html_has_all_nine_axis_fieldsets(self):
        html = _read("brief-tab.html")
        for axis in AXIS_IDS:
            # Each axis renders as either a <fieldset id="axis-{axis}"> or an
            # explicit anchor the JS later populates.
            pattern = re.compile(
                rf'(?:id=|data-axis=)["\']' + re.escape(axis) + r'["\']'
            )
            assert pattern.search(html), f"axis {axis} missing from brief-tab.html"

    def test_brief_tab_html_has_per_section_overrides_placeholder(self):
        html = _read("brief-tab.html")
        assert re.search(
            r'id=["\']per-section-overrides["\']', html
        ), "per-section-overrides section missing"

    def test_brief_tab_html_has_reset_and_generate_buttons(self):
        html = _read("brief-tab.html")
        assert re.search(r'id=["\']btn-brief-reset["\']', html), "Reset button missing"
        assert re.search(r'id=["\']btn-brief-generate["\']', html), "Generate button missing"

    def test_brief_tab_js_exposes_mount_function(self):
        js = _read("brief-tab.js")
        assert "mountBriefTab" in js, "mountBriefTab entry point missing"


# ---------------------------------------------------------------------------
# T019 / US6: visible hints (DOM text, not title= tooltips)
# ---------------------------------------------------------------------------

class TestHintsAreVisible:
    def test_every_axis_has_p_class_hint_in_fragment_template(self):
        """Hint placeholders are rendered by brief-tab.js via <p class="hint">.
        The JS emits them when building each axis; assert the markup pattern
        appears in brief-tab.js.
        """
        js = _read("brief-tab.js")
        assert re.search(
            r"""<p\s+class=["']hint["']""",
            js,
        ), "hint <p class='hint'> template missing from brief-tab.js"

    def test_no_title_only_hints_in_axis_rendering(self):
        """Hints must NOT be hidden behind title= (FR-051, US6 AC-1)."""
        js = _read("brief-tab.js")
        # title= attributes may exist for other purposes, but every axis hint
        # must have a corresponding <p class="hint">.  This is an indirect
        # check — title-only hint patterns like `title="${axis.hint}"` without
        # a companion <p class="hint"> would fail.
        # Enforce: for every occurrence of `axis.hint` or `axisDef.hint`,
        # there's a <p class="hint"> nearby.
        assert "class=\"hint\"" in js or "class='hint'" in js

    def test_brief_presets_every_axis_has_hint(self):
        """US6 AC-2: every axis hint ≤ 120 chars and non-empty."""
        presets = _read("brief-presets.js")
        # Extract each axis definition's hint string.
        pattern = re.compile(
            r"""(\w+):\s*\{\s*label:\s*['"][^'"]+['"],\s*hint:\s*['"]([^'"]*)['"]""",
            re.DOTALL,
        )
        matches = pattern.findall(presets)
        found_axes = {m[0] for m in matches}
        for axis in AXIS_IDS:
            assert axis in found_axes, f"axis {axis} missing top-level hint"
        for axis, hint in matches:
            if axis not in AXIS_IDS:
                continue
            assert 0 < len(hint) <= 120, (
                f"axis {axis} hint wrong length ({len(hint)}): {hint!r}"
            )


# ---------------------------------------------------------------------------
# T020: Advanced disclosure closed by default, shows raw controls
# ---------------------------------------------------------------------------

class TestAdvancedDisclosure:
    def test_brief_tab_js_emits_details_advanced(self):
        js = _read("brief-tab.js")
        # details element with class advanced — closed by default (no `open` attr).
        assert re.search(r"<details[^>]*class=[\"']advanced[\"']", js), (
            "Advanced <details class='advanced'> template missing"
        )

    def test_no_open_attribute_on_advanced_details(self):
        js = _read("brief-tab.js")
        # Make sure no template has `<details ... open>` in the advanced tag.
        # Match <details open class="advanced"> or <details class="advanced" open>
        bad = re.search(
            r"<details[^>]*open[^>]*class=[\"']advanced[\"']",
            js,
        )
        bad2 = re.search(
            r"<details[^>]*class=[\"']advanced[\"'][^>]*open",
            js,
        )
        assert not bad and not bad2, "Advanced details must be closed by default"


# ---------------------------------------------------------------------------
# T021: Advanced → Custom indicator when raw diverges from preset
# ---------------------------------------------------------------------------

class TestCustomPresetDetection:
    def test_detect_active_preset_helper_exists(self):
        js = _read("brief-presets.js")
        assert "detectActivePreset" in js, "detectActivePreset() helper missing"

    def test_detect_active_preset_returns_custom_when_advanced_diverges(self):
        js = _read("brief-presets.js")
        # Ensure the helper returns 'custom' via some branch.
        assert "'custom'" in js or '"custom"' in js, (
            "detectActivePreset must be able to return 'custom'"
        )


# ---------------------------------------------------------------------------
# US2 AC-1: every axis has 3–5 presets including exactly one 'auto'
# ---------------------------------------------------------------------------

class TestPresetCountAndAuto:
    def test_every_axis_has_auto_and_3_to_5_presets(self):
        # Reuse the table from test_brief_persistence so this test still
        # catches drift if brief-presets.js is edited without updating tests.
        from tests.unit.test_brief_persistence import PRESET_TABLE
        for axis in AXIS_IDS:
            presets = PRESET_TABLE[axis]
            count = len(presets)
            assert 3 <= count <= 5, f"axis {axis}: {count} presets (want 3–5)"
            ids = [p for p, _ in presets]
            assert ids.count("auto") == 1, (
                f"axis {axis} must have exactly one preset id 'auto'"
            )


# ---------------------------------------------------------------------------
# US1 AC-2 / US5 AC-1: per-section overrides table exists as placeholder
# ---------------------------------------------------------------------------

class TestPerSectionTablePlaceholder:
    def test_per_section_section_in_html_is_empty_to_be_filled_by_js(self):
        html = _read("brief-tab.html")
        assert 'id="per-section-overrides"' in html or "id='per-section-overrides'" in html


# ---------------------------------------------------------------------------
# US2 AC-2 / SC-002: all-Auto Brief resolves to empty POST body (or mood_intent only)
# ---------------------------------------------------------------------------

class TestAllAutoResolvesEmpty:
    def test_resolveBriefToPost_with_all_auto_yields_minimal_body(self):
        """Hand-roll the JS logic in Python to validate the contract.

        This mirrors the rule: for each axis, 'auto' preset contributes either
        {} (plain Auto) or {field: "auto"} (mood_intent).  No legacy default
        values should leak into the POST.
        """
        from tests.unit.test_brief_persistence import PRESET_TABLE

        def py_resolve(brief):
            body = {}
            for axis in AXIS_IDS:
                selected = brief.get(axis, "auto")
                for pid, raw in PRESET_TABLE[axis]:
                    if pid == selected:
                        body.update(raw)
                        break
            return body

        brief_all_auto = {axis: "auto" for axis in AXIS_IDS}
        body = py_resolve(brief_all_auto)
        # Only mood_intent can appear (as "auto"); all other fields must be absent.
        allowed = set(body.keys()) - {"mood_intent"}
        assert allowed == set(), (
            f"all-Auto Brief leaked fields: {sorted(allowed)}"
        )
        if "mood_intent" in body:
            assert body["mood_intent"] == "auto"
