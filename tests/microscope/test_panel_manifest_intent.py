"""Tests for tier_intent manifest schema (OpenSpec
``microscope-panel-tier-coverage`` §2)."""
from __future__ import annotations

import json

import pytest

from src.microscope.panel import (
    PanelFixtureResult,
    _ParsedSlug,
    _parse_slug_entries,
    parse_panel_manifest_slugs,
)


# ── _parse_slug_entries ─────────────────────────────────────────────────────


def test_legacy_string_slug_yields_empty_intent():
    parsed = _parse_slug_entries(["funshine", "maple_leaf_rag"])
    assert parsed == [
        _ParsedSlug(slug="funshine", tier_intent=()),
        _ParsedSlug(slug="maple_leaf_rag", tier_intent=()),
    ]


def test_object_slug_with_tier_intent():
    parsed = _parse_slug_entries(
        [{"slug": "structural_no_phrase", "tier_intent": ["06_PROP", "08_HERO"]}]
    )
    assert parsed == [
        _ParsedSlug(
            slug="structural_no_phrase",
            tier_intent=("06_PROP", "08_HERO"),
        )
    ]


def test_object_slug_without_tier_intent_defaults_to_empty():
    parsed = _parse_slug_entries([{"slug": "song"}])
    assert parsed[0].tier_intent == ()


def test_mixed_string_and_object_entries():
    parsed = _parse_slug_entries(
        [
            "legacy_song",
            {"slug": "new_song", "tier_intent": ["06_PROP"]},
        ]
    )
    assert parsed[0].slug == "legacy_song"
    assert parsed[0].tier_intent == ()
    assert parsed[1].tier_intent == ("06_PROP",)


def test_missing_slug_raises_with_index():
    with pytest.raises(ValueError, match=r"\[1\].*'slug'"):
        _parse_slug_entries(
            [{"slug": "ok"}, {"tier_intent": ["08_HERO"]}]
        )


def test_non_string_slug_raises():
    with pytest.raises(ValueError, match=r"'slug' string field"):
        _parse_slug_entries([{"slug": 42, "tier_intent": []}])


def test_tier_intent_must_be_list_of_strings():
    with pytest.raises(ValueError, match="'tier_intent'"):
        _parse_slug_entries(
            [{"slug": "song", "tier_intent": "06_PROP"}]
        )


def test_tier_intent_with_non_string_element_raises():
    with pytest.raises(ValueError, match="'tier_intent'"):
        _parse_slug_entries(
            [{"slug": "song", "tier_intent": ["06_PROP", 8]}]
        )


def test_unknown_entry_type_raises():
    with pytest.raises(ValueError, match="must be a string slug"):
        _parse_slug_entries([42])


# ── parse_panel_manifest_slugs (public-ish helper) ──────────────────────────


def test_parse_panel_manifest_slugs_round_trip(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slugs": [
                    "song_a",
                    {"slug": "song_b", "tier_intent": ["06_PROP", "08_HERO"]},
                ],
                "layout": "tests/fixtures/reference/layout.xml",
            }
        ),
        encoding="utf-8",
    )
    parsed = parse_panel_manifest_slugs(manifest_path)
    assert len(parsed) == 2
    assert parsed[0].slug == "song_a" and parsed[0].tier_intent == ()
    assert parsed[1].slug == "song_b"
    assert parsed[1].tier_intent == ("06_PROP", "08_HERO")


def test_parse_panel_manifest_slugs_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_panel_manifest_slugs(tmp_path / "nope.json")


# ── PanelFixtureResult shape ────────────────────────────────────────────────


def test_panel_fixture_result_is_frozen_pair():
    """Smoke check that the wrapper carries both fields and is hashable."""
    from src.evaluation.models import SequenceSummary
    from src.microscope.runner import MicroscopeResult

    summary = SequenceSummary(
        song_id="t", source_label="ours", duration_ms=1000,
        placements=(), model_names=(), inferred_prop_types={},
    )
    result = MicroscopeResult(
        slug="t", audio_path="/tmp/t.mp3", xsq_path="/tmp/t.xsq",
        summary=summary, metrics={}, generated_at="2026-05-02T00:00:00Z",
        config_snapshot={},
    )
    pfr = PanelFixtureResult(result=result, tier_intent=("08_HERO",))
    assert pfr.result is result
    assert pfr.tier_intent == ("08_HERO",)
