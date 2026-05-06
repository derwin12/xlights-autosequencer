"""Tier-coverage verification for the microscope panel.

The :func:`verify_panel_coverage` entry point reads a previously-run
panel's per-fixture metrics.json files and asserts that every fixture's
``tier_placement_breakdown`` payload contains every tier prefix listed
in its declared ``tier_intent`` (from the manifest). This is the
runtime side of the OpenSpec change ``microscope-panel-tier-coverage``
spec.

The required-tier set (the panel-level "every panel must exercise these
tiers between them" floor) is hardcoded as ``_REQUIRED_TIER_COVERAGE``
below — it is the contract spelled out in
``openspec/specs/microscope-panel-tier-coverage/spec.md`` (see review
feedback on PR #156: required tier set must live in code, not only in
spec prose).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.microscope.panel import _ParsedSlug, parse_panel_manifest_slugs


# ---------------------------------------------------------------------------
# Required tier coverage — see specs/microscope-panel-tier-coverage/spec.md
# Requirement "Each tier in {01_BASE, 02_GEO, 04_BEAT, 06_PROP, 08_HERO}
# has at least one fixture exercising it".  Tier 07_COMP is intentionally
# excluded (no mood routes to it; out of scope per design.md).
# ---------------------------------------------------------------------------
_REQUIRED_TIER_COVERAGE: frozenset[str] = frozenset(
    {"01_BASE", "02_GEO", "04_BEAT", "06_PROP", "08_HERO"}
)


@dataclass(frozen=True)
class FixtureCoverageResult:
    """Per-fixture verdict from verify-coverage."""

    slug: str
    declared: tuple[str, ...]    # tier_intent from manifest
    observed: tuple[str, ...]    # active_tiers from tier_placement_breakdown
    missing: tuple[str, ...]     # declared - observed
    passed: bool                 # missing is empty


@dataclass(frozen=True)
class VerifyReport:
    """Aggregate verdict for a panel verify-coverage run."""

    fixtures: tuple[FixtureCoverageResult, ...]
    orphaned_required_tiers: tuple[str, ...]  # in REQUIRED but no manifest fixture declares them

    @property
    def all_fixtures_passed(self) -> bool:
        return all(f.passed for f in self.fixtures)

    @property
    def required_coverage_satisfied(self) -> bool:
        return not self.orphaned_required_tiers

    @property
    def passed(self) -> bool:
        return self.all_fixtures_passed and self.required_coverage_satisfied


def _load_metrics(output_dir: Path, slug: str) -> dict | None:
    """Load ``output_dir/microscope/<slug>/metrics.json`` or return None."""
    path = output_dir / "microscope" / slug / "metrics.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _active_tiers(metrics: dict) -> tuple[str, ...]:
    """Extract active_tiers from a fixture's metrics.json payload."""
    breakdown = metrics.get("metrics", {}).get("tier_placement_breakdown", {})
    payload = breakdown.get("payload") or {}
    active = payload.get("active_tiers") or []
    return tuple(active)


def verify_panel_coverage(
    manifest_path: Path | str,
    output_dir: Path | str,
) -> VerifyReport:
    """Run the verify-coverage check against a panel run.

    Args:
        manifest_path: Panel manifest JSON.
        output_dir: Where ``microscope panel`` wrote its per-slug
            ``metrics.json`` files.

    Returns:
        :class:`VerifyReport` describing per-fixture passes/failures
        and any required tiers that no fixture declared.

    Raises:
        FileNotFoundError: Manifest is missing.
        FileNotFoundError: A slug declared in the manifest has no
            corresponding ``metrics.json`` under ``output_dir``.
            Caller should run ``microscope panel`` first.
    """
    manifest_path_obj = Path(manifest_path)
    output_dir_obj = Path(output_dir)
    parsed: list[_ParsedSlug] = parse_panel_manifest_slugs(manifest_path_obj)

    fixture_results: list[FixtureCoverageResult] = []
    declared_tiers: set[str] = set()

    for entry in parsed:
        declared_tiers.update(entry.tier_intent)
        metrics = _load_metrics(output_dir_obj, entry.slug)
        if metrics is None:
            raise FileNotFoundError(
                f"No metrics.json for slug {entry.slug!r} under {output_dir_obj}; "
                f"run `xlight-evaluate microscope panel --output-dir {output_dir_obj}` first"
            )
        observed = _active_tiers(metrics)
        missing = tuple(t for t in entry.tier_intent if t not in observed)
        fixture_results.append(
            FixtureCoverageResult(
                slug=entry.slug,
                declared=entry.tier_intent,
                observed=observed,
                missing=missing,
                passed=not missing,
            )
        )

    orphaned = tuple(sorted(_REQUIRED_TIER_COVERAGE - declared_tiers))
    return VerifyReport(
        fixtures=tuple(fixture_results),
        orphaned_required_tiers=orphaned,
    )
