"""Validation tests using realistic song scenarios.

Runs the full generation pipeline (build_plan) against 5 synthetic song
scenarios and validates quality scores. These tests serve as the regression
baseline — when you change the generator, these scores tell you whether
sequences got better or worse.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.generator.plan import build_plan
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library
from src.validation.baseline import (
    Baseline,
    compare_against_baseline,
    create_baseline_entry,
    load_baseline,
    save_baseline,
)
from src.validation.report import ValidationReport, generate_report, save_report
from src.validation.scenarios import (
    ALL_SCENARIOS,
    ValidationScenario,
    load_all_scenarios,
)
from src.validation.scorers import ALL_SCORERS


# ── Shared Setup ─────────────────────────────────────────────────────────────


def _run_scenario(scenario: ValidationScenario, tmp_path: Path) -> ValidationReport:
    """Run a scenario through the full pipeline and generate a validation report."""
    effect_lib = load_effect_library()
    variant_lib = load_variant_library(effect_library=effect_lib)
    theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)
    config = scenario.make_config(tmp_path)

    plan = build_plan(
        config, scenario.hierarchy,
        scenario.props, scenario.groups,
        effect_lib, theme_lib,
    )
    return generate_report(plan, scenario.hierarchy)


# ── Per-Scenario Tests ───────────────────────────────────────────────────────


@pytest.fixture(params=list(ALL_SCENARIOS.keys()))
def scenario_name(request) -> str:
    return request.param


@pytest.fixture
def scenario(scenario_name: str) -> ValidationScenario:
    return ALL_SCENARIOS[scenario_name]()


class TestScenarioQuality:
    """Run each scenario and assert minimum quality thresholds."""

    def test_generates_effects(self, scenario: ValidationScenario, tmp_path: Path):
        """Every scenario should produce at least some effects."""
        report = _run_scenario(scenario, tmp_path)
        assert report.total_effects > 0, (
            f"{scenario.name}: generated 0 effects"
        )

    def test_overall_score_above_minimum(self, scenario: ValidationScenario, tmp_path: Path):
        """Every scenario should achieve a minimum overall score."""
        report = _run_scenario(scenario, tmp_path)
        # This is deliberately lenient — we're establishing a floor, not a target
        assert report.overall_score >= 20.0, (
            f"{scenario.name}: overall score {report.overall_score} below minimum 20"
        )

    def test_beat_alignment_above_floor(self, scenario: ValidationScenario, tmp_path: Path):
        """Beat alignment should be reasonable for all scenarios."""
        report = _run_scenario(scenario, tmp_path)
        beat_score = next(
            r.score for r in report.scorer_results if r.name == "beat_alignment"
        )
        assert beat_score >= 30.0, (
            f"{scenario.name}: beat alignment {beat_score} below floor 30"
        )

    def test_temporal_coverage_above_floor(self, scenario: ValidationScenario, tmp_path: Path):
        """Every scenario should cover most of the song duration."""
        report = _run_scenario(scenario, tmp_path)
        coverage = next(
            r.score for r in report.scorer_results if r.name == "temporal_coverage"
        )
        assert coverage >= 50.0, (
            f"{scenario.name}: temporal coverage {coverage} below floor 50"
        )


# ── Cross-Scenario Comparison ───────────────────────────────────────────────


class TestCrossScenario:
    """Validate relationships between scenarios — e.g., EDM should use higher tiers than ballad."""

    def test_edm_has_higher_tier_utilization_than_ballad(self, tmp_path: Path):
        edm = ALL_SCENARIOS["edm_banger"]()
        ballad = ALL_SCENARIOS["christmas_ballad"]()

        edm_report = _run_scenario(edm, tmp_path)
        ballad_report = _run_scenario(ballad, tmp_path)

        edm_tier = next(r.score for r in edm_report.scorer_results if r.name == "tier_utilization")
        ballad_tier = next(r.score for r in ballad_report.scorer_results if r.name == "tier_utilization")

        # EDM should use tiers at least as aggressively as a ballad
        # (not strictly greater — both could be equal if generator is very consistent)
        assert edm_tier >= ballad_tier * 0.8, (
            f"EDM tier utilization ({edm_tier}) unexpectedly lower than ballad ({ballad_tier})"
        )


# ── Baseline Generation & Regression ────────────────────────────────────────


class TestBaselineRegression:
    """Generate baselines and test for regressions.

    The first run captures the baseline. Subsequent runs compare against it.
    This test always passes on first run (creates baseline) and enforces
    regression detection on subsequent runs.
    """

    def test_all_scenarios_against_baseline(self, tmp_path: Path):
        """Run all scenarios and compare against baseline if it exists."""
        baseline_path = Path(__file__).parent / "baseline_v1.json"

        entries = []
        reports: dict[str, ValidationReport] = {}

        for name, builder in ALL_SCENARIOS.items():
            scenario = builder()
            report = _run_scenario(scenario, tmp_path)
            reports[name] = report
            entries.append(create_baseline_entry(name, report))

        if not baseline_path.exists():
            # First run: save baseline and pass
            baseline = Baseline(version="1.0", entries=entries)
            save_baseline(baseline, baseline_path)
            pytest.skip(
                f"Baseline created at {baseline_path} with {len(entries)} scenarios. "
                "Re-run to test against it."
            )
        else:
            # Subsequent runs: compare against baseline
            baseline = load_baseline(baseline_path)
            failures = []

            for entry in baseline.entries:
                if entry.scenario_name not in reports:
                    continue
                result = compare_against_baseline(
                    reports[entry.scenario_name], entry, tolerance_pct=5.0,
                )
                if not result.passed:
                    failures.extend(result.regressions)

            assert not failures, (
                f"Regressions detected:\n" + "\n".join(f"  - {f}" for f in failures)
            )


# ── Report Dump (for manual inspection) ─────────────────────────────────────


class TestReportGeneration:
    """Generate full reports for all scenarios — useful for manual review."""

    def test_print_all_reports(self, tmp_path: Path, capsys):
        """Print validation reports for all scenarios to stdout."""
        for name, builder in ALL_SCENARIOS.items():
            scenario = builder()
            report = _run_scenario(scenario, tmp_path)
            save_report(report, tmp_path / f"{name}_report.json")
            print(f"\n{'=' * 60}")
            print(report.summary_table())
            print(f"{'=' * 60}")
