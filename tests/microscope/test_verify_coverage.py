"""Tests for ``verify_panel_coverage`` (OpenSpec
``microscope-panel-tier-coverage`` §3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.microscope.verify import (
    _REQUIRED_TIER_COVERAGE,
    FixtureCoverageResult,
    verify_panel_coverage,
)


def _write_manifest(path: Path, slugs: list) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slugs": slugs,
                "layout": "tests/fixtures/reference/layout.xml",
            }
        ),
        encoding="utf-8",
    )


def _write_metrics(output_dir: Path, slug: str, active_tiers: list[str]) -> None:
    """Synthesize a metrics.json with the active_tiers we want."""
    song_dir = output_dir / "microscope" / slug
    song_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "metrics": {
            "tier_placement_breakdown": {
                "value": float(len(active_tiers)),
                "kind": "structured",
                "reliability": "ok",
                "payload": {
                    "counts": {t: 1 for t in active_tiers},
                    "active_tiers": active_tiers,
                },
            }
        },
    }
    (song_dir / "metrics.json").write_text(json.dumps(payload), encoding="utf-8")


# ── Spec scenario: all fixtures cover their intent ──────────────────────────


def test_all_fixtures_pass_yields_passed_report(tmp_path):
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "out"
    # Cover all required tiers across two fixtures.
    _write_manifest(
        manifest,
        [
            {"slug": "song_a", "tier_intent": ["01_BASE", "02_GEO", "08_HERO"]},
            {"slug": "song_b", "tier_intent": ["04_BEAT", "06_PROP", "08_HERO"]},
        ],
    )
    _write_metrics(out, "song_a", ["01_BASE", "02_GEO", "08_HERO"])
    _write_metrics(out, "song_b", ["04_BEAT", "06_PROP", "08_HERO"])

    report = verify_panel_coverage(manifest, out)
    assert report.passed
    assert report.all_fixtures_passed
    assert report.required_coverage_satisfied
    assert all(f.missing == () for f in report.fixtures)


# ── Spec scenario: a fixture missed a declared tier ─────────────────────────


def test_fixture_missing_declared_tier_fails(tmp_path):
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "out"
    _write_manifest(
        manifest,
        [{"slug": "song", "tier_intent": ["06_PROP", "08_HERO"]}],
    )
    # Only HERO actually observed.
    _write_metrics(out, "song", ["08_HERO"])

    report = verify_panel_coverage(manifest, out)
    assert not report.passed
    assert not report.all_fixtures_passed
    fixture = report.fixtures[0]
    assert fixture.missing == ("06_PROP",)
    assert fixture.passed is False


# ── Spec scenario: output dir missing ───────────────────────────────────────


def test_missing_metrics_json_raises_filenotfound(tmp_path):
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "out"
    _write_manifest(manifest, [{"slug": "song", "tier_intent": ["08_HERO"]}])
    # Don't write metrics.json — output dir is empty.

    with pytest.raises(FileNotFoundError, match="song"):
        verify_panel_coverage(manifest, out)


# ── Spec scenario: a required tier has no fixture (orphan) ──────────────────


def test_required_tier_orphaned_when_no_fixture_declares_it(tmp_path):
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "out"
    # Declare HERO + GEO + BEAT + BASE but nothing for PROP.
    _write_manifest(
        manifest,
        [
            {"slug": "a", "tier_intent": ["01_BASE", "02_GEO", "08_HERO"]},
            {"slug": "b", "tier_intent": ["04_BEAT", "08_HERO"]},
        ],
    )
    _write_metrics(out, "a", ["01_BASE", "02_GEO", "08_HERO"])
    _write_metrics(out, "b", ["04_BEAT", "08_HERO"])

    report = verify_panel_coverage(manifest, out)
    assert report.all_fixtures_passed  # individual intents are met
    assert not report.required_coverage_satisfied  # but PROP is orphaned
    assert "06_PROP" in report.orphaned_required_tiers
    assert not report.passed


# ── Spec scenario: malformed manifest rejected ──────────────────────────────


def test_malformed_manifest_raises(tmp_path):
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "out"
    _write_manifest(manifest, [{"tier_intent": ["08_HERO"]}])  # missing slug
    with pytest.raises(ValueError, match="'slug'"):
        verify_panel_coverage(manifest, out)


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify_panel_coverage(tmp_path / "nope.json", tmp_path)


# ── Required tier set itself ────────────────────────────────────────────────


def test_required_tier_coverage_constant_matches_spec():
    """Spec text in openspec/specs/microscope-panel-tier-coverage/spec.md
    requires {01_BASE, 02_GEO, 04_BEAT, 06_PROP, 08_HERO}; tier 07_COMP
    is intentionally excluded (no mood routes to it)."""
    assert _REQUIRED_TIER_COVERAGE == frozenset(
        {"01_BASE", "02_GEO", "04_BEAT", "06_PROP", "08_HERO"}
    )
    assert "07_COMP" not in _REQUIRED_TIER_COVERAGE


# ── Edge: legacy plain-string slug entries ──────────────────────────────────


def test_legacy_string_slug_has_empty_intent_and_passes(tmp_path):
    """A plain-string slug declares no intent; verify-coverage is a no-op
    for that fixture per the manifest schema requirement."""
    manifest = tmp_path / "manifest.json"
    out = tmp_path / "out"
    _write_manifest(manifest, ["legacy_song"])
    _write_metrics(out, "legacy_song", ["08_HERO"])
    report = verify_panel_coverage(manifest, out)
    fixture = report.fixtures[0]
    assert fixture.declared == ()
    assert fixture.missing == ()
    assert fixture.passed is True
