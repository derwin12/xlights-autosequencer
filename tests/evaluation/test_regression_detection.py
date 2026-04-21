"""Regression detection tests (SC-002).

Verify that compare_against_baseline catches ≥ 90% of injected regressions.
One regression is injected per gated metric.
"""
from __future__ import annotations

import pytest

from src.evaluation.baseline import compare_against_baseline
from src.evaluation.models import MetricValue
from src.evaluation.metrics import get_registry

# Import all metric modules to populate the registry
import src.evaluation.metrics.pacing
import src.evaluation.metrics.palette
import src.evaluation.metrics.effects
import src.evaluation.metrics.alignment
import src.evaluation.metrics.sections
import src.evaluation.metrics.internal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_baseline_dict(metric_dicts: list[dict]) -> dict:
    """Build a baseline dict in the format returned by load_baseline()."""
    return {
        "schema_version": 1,
        "generator_commit": "deadbeef",
        "generated_at": "2026-01-01T00:00:00Z",
        "entries": {
            "test-song": {"metrics": metric_dicts}
        },
    }


def _mv(name: str, value: float, kind: str = "scalar") -> MetricValue:
    """Construct a minimal MetricValue for injection."""
    return MetricValue(
        name=name,
        kind=kind,
        value=value,
        payload=None,
        reliability="ok",
    )


def _detect(metric_name: str, baseline_value: float, current_value: float, kind: str = "scalar") -> bool:
    """Return True if compare_against_baseline flags a regression for metric_name."""
    baseline_dict = _make_baseline_dict([
        {"name": metric_name, "kind": kind, "value": baseline_value, "payload": None, "reliability": "ok"}
    ])
    current_metrics = {"test-song": [_mv(metric_name, current_value, kind)]}
    result = compare_against_baseline(baseline_dict, current_metrics, get_registry())
    return not result.passed and any(v.metric_name == metric_name for v in result.violations)


# ---------------------------------------------------------------------------
# Individual regression tests (one per gated metric)
# ---------------------------------------------------------------------------

def test_regression_placements_per_minute():
    """placements_per_minute: drop from 100 → 50 (50% relative, tolerance ±15%)."""
    assert _detect("placements_per_minute", baseline_value=100.0, current_value=50.0)


def test_regression_palette_top5_colors():
    """palette_top5_colors: top color share rises from 0.3 → 0.8 (monochromatic regression).

    Tolerance is DEFAULT relative ±10%. delta=0.5/0.3 ≈ 167% — well above threshold.
    """
    assert _detect("palette_top5_colors", baseline_value=0.3, current_value=0.8)


def test_regression_effect_type_histogram():
    """effect_type_histogram: unknown fraction rises from 0.0 → 0.8.

    Baseline value 0.0 means the divisor is clamped to 1e-9, making the relative
    delta enormous — the regression is detected.
    """
    assert _detect("effect_type_histogram", baseline_value=0.0, current_value=0.8)


def test_regression_beat_alignment_pct():
    """beat_alignment_pct: drops from 0.85 → 0.50 (absolute delta 0.35, tolerance ±0.03)."""
    assert _detect("beat_alignment_pct", baseline_value=0.85, current_value=0.50)


def test_regression_density_energy_correlation():
    """density_energy_correlation: drops from 0.75 → 0.20 (73% relative, tolerance ±10%)."""
    assert _detect("density_energy_correlation", baseline_value=0.75, current_value=0.20)


def test_regression_per_section_palette_diversity():
    """per_section_palette_diversity: drops from 5.0 → 1.0 (80% relative, tolerance ±10%)."""
    assert _detect("per_section_palette_diversity", baseline_value=5.0, current_value=1.0)


def test_regression_section_transition_delta():
    """section_transition_delta: drops from 0.4 → 0.05 (87.5% relative, tolerance ±10%)."""
    assert _detect("section_transition_delta", baseline_value=0.4, current_value=0.05)


def test_regression_tier_utilization():
    """tier_utilization: drops from 0.9 → 0.3 (absolute delta 0.6, tolerance ±0.05)."""
    assert _detect("tier_utilization", baseline_value=0.9, current_value=0.3)


def test_regression_theme_assignment_consistency():
    """theme_assignment_consistency: drops from 0.95 → 0.4 (57.9% relative, tolerance ±10%)."""
    assert _detect("theme_assignment_consistency", baseline_value=0.95, current_value=0.4)


# ---------------------------------------------------------------------------
# SC-002 summary: ≥ 90% detection rate
# ---------------------------------------------------------------------------

def test_regression_detection_rate():
    """SC-002: ≥ 90% of 9 injected regressions must be caught (spec requires ≥ 9)."""
    regressions = [
        ("placements_per_minute",          100.0, 50.0),
        ("palette_top5_colors",            0.3,   0.8),
        ("effect_type_histogram",          0.0,   0.8),
        ("beat_alignment_pct",             0.85,  0.50),
        ("density_energy_correlation",     0.75,  0.20),
        ("per_section_palette_diversity",  5.0,   1.0),
        ("section_transition_delta",       0.4,   0.05),
        ("tier_utilization",               0.9,   0.3),
        ("theme_assignment_consistency",   0.95,  0.4),
    ]

    total = len(regressions)
    detected = sum(
        1 for name, baseline, current in regressions
        if _detect(name, baseline, current)
    )

    # Spec SC-002: ≥ 90% of 9 = ≥ 8.1, rounded up = ≥ 9
    assert detected >= total, (
        f"Only {detected}/{total} regressions detected — spec requires ≥ {total}"
    )
