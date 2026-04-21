"""Failing tests for ours-only internal metrics: tier_utilization, theme_assignment_consistency."""
from __future__ import annotations

import pytest

from src.evaluation.models import MetricValue, Placement, SequenceSummary


def make_summary(
    models_and_placements: list[tuple[str, int, int, str]],
    duration_ms: int = 60_000,
) -> SequenceSummary:
    """models_and_placements: list of (model_name, start_ms, end_ms, effect_type)"""
    placements = tuple(
        Placement(s, e, et, m, ("#FF0000",), 0)
        for m, s, e, et in models_and_placements
    )
    model_names = tuple(dict.fromkeys(m for m, _, _, _ in models_and_placements))
    return SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=duration_ms,
        placements=placements,
        model_names=model_names,
        inferred_prop_types={m: "arch" for m in model_names},
    )


# ---------------------------------------------------------------------------
# tier_utilization
# ---------------------------------------------------------------------------


def test_tier_utilization_all_active():
    """3 models, all appear in a single section → utilization = 1.0."""
    from src.evaluation.metrics.internal import tier_utilization

    summary = make_summary([
        ("Arch01", 0, 5000, "Marquee"),
        ("Arch02", 0, 5000, "Plasma"),
        ("Arch03", 0, 5000, "Chase"),
    ])
    sections = [{"label": "verse", "start_ms": 0, "end_ms": 60_000}]
    result = tier_utilization(summary, sections)

    assert isinstance(result, MetricValue)
    assert result.value == pytest.approx(1.0)
    assert result.name == "tier_utilization"


def test_tier_utilization_partial():
    """3 models total, only 2 appear in the section → utilization ≈ 0.667."""
    from src.evaluation.metrics.internal import tier_utilization

    summary = make_summary([
        ("Arch01", 0, 5000, "Marquee"),
        ("Arch02", 0, 5000, "Plasma"),
        ("Arch03", 30_000, 35_000, "Chase"),   # outside section window
    ])
    sections = [{"label": "verse", "start_ms": 0, "end_ms": 10_000}]
    result = tier_utilization(summary, sections)

    assert result.value == pytest.approx(2 / 3, rel=1e-3)


def test_tier_utilization_no_sections():
    """sections=None → treats whole song as one section, returns some utilization."""
    from src.evaluation.metrics.internal import tier_utilization

    summary = make_summary([
        ("Arch01", 0, 5000, "Marquee"),
        ("Arch02", 0, 5000, "Plasma"),
    ])
    result = tier_utilization(summary, None)

    assert result.value is not None
    assert 0.0 <= result.value <= 1.0


def test_tier_utilization_empty():
    """No placements → value = 0.0."""
    from src.evaluation.metrics.internal import tier_utilization

    summary = SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=60_000,
        placements=(),
        model_names=(),
        inferred_prop_types={},
    )
    result = tier_utilization(summary, None)

    assert result.value == pytest.approx(0.0)


def test_tier_utilization_payload_structure():
    """Payload entries must have the required keys."""
    from src.evaluation.metrics.internal import tier_utilization

    summary = make_summary([
        ("Arch01", 0, 5000, "Marquee"),
        ("Arch02", 0, 5000, "Plasma"),
    ])
    sections = [
        {"label": "intro", "start_ms": 0, "end_ms": 10_000},
        {"label": "verse", "start_ms": 10_000, "end_ms": 30_000},
    ]
    result = tier_utilization(summary, sections)

    assert isinstance(result.payload, list)
    required_keys = {"section_label", "start_ms", "end_ms", "utilization", "active_models", "total_models"}
    for entry in result.payload:
        assert required_keys <= set(entry.keys()), f"Missing keys in payload entry: {entry}"


# ---------------------------------------------------------------------------
# theme_assignment_consistency
# ---------------------------------------------------------------------------


def test_theme_consistency_no_sections():
    """sections=None → value = 1.0 (full consistency assumed)."""
    from src.evaluation.metrics.internal import theme_assignment_consistency

    summary = make_summary([
        ("Arch01", 0, 5000, "Marquee"),
    ])
    result = theme_assignment_consistency(summary, None)

    assert result.value == pytest.approx(1.0)
    assert result.name == "theme_assignment_consistency"


def test_theme_consistency_consistent():
    """verse sections all use Marquee, chorus sections all use Plasma → value = 1.0."""
    from src.evaluation.metrics.internal import theme_assignment_consistency

    summary = make_summary([
        # verse1
        ("Arch01", 0, 5000, "Marquee"),
        ("Arch02", 0, 5000, "Marquee"),
        # chorus1
        ("Arch01", 10_000, 15_000, "Plasma"),
        ("Arch02", 10_000, 15_000, "Plasma"),
        # verse2
        ("Arch01", 20_000, 25_000, "Marquee"),
        ("Arch02", 20_000, 25_000, "Marquee"),
        # chorus2
        ("Arch01", 30_000, 35_000, "Plasma"),
        ("Arch02", 30_000, 35_000, "Plasma"),
    ])
    sections = [
        {"label": "verse",   "start_ms": 0,      "end_ms": 10_000},
        {"label": "chorus",  "start_ms": 10_000,  "end_ms": 20_000},
        {"label": "verse",   "start_ms": 20_000,  "end_ms": 30_000},
        {"label": "chorus",  "start_ms": 30_000,  "end_ms": 40_000},
    ]
    result = theme_assignment_consistency(summary, sections)

    assert result.value == pytest.approx(1.0)


def test_theme_consistency_inconsistent():
    """verse1 uses Marquee, verse2 uses Plasma → value < 1.0."""
    from src.evaluation.metrics.internal import theme_assignment_consistency

    summary = make_summary([
        # verse1
        ("Arch01", 0, 5000, "Marquee"),
        # verse2 — different effect
        ("Arch01", 20_000, 25_000, "Plasma"),
    ])
    sections = [
        {"label": "verse", "start_ms": 0,      "end_ms": 10_000},
        {"label": "verse", "start_ms": 20_000, "end_ms": 30_000},
    ]
    result = theme_assignment_consistency(summary, sections)

    assert result.value is not None
    assert result.value < 1.0


def test_theme_consistency_no_repeats():
    """All unique section labels → no repeated labels → value = 1.0."""
    from src.evaluation.metrics.internal import theme_assignment_consistency

    summary = make_summary([
        ("Arch01", 0, 5000, "Marquee"),
        ("Arch01", 10_000, 15_000, "Plasma"),
        ("Arch01", 20_000, 25_000, "Chase"),
    ])
    sections = [
        {"label": "intro",  "start_ms": 0,      "end_ms": 10_000},
        {"label": "verse",  "start_ms": 10_000, "end_ms": 20_000},
        {"label": "chorus", "start_ms": 20_000, "end_ms": 30_000},
    ]
    result = theme_assignment_consistency(summary, sections)

    assert result.value == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_metrics_registered():
    """Both metrics appear in the registry after import."""
    import src.evaluation.metrics.internal  # noqa: F401 — triggers registration
    from src.evaluation.metrics import get_registry

    registry = get_registry()
    assert "tier_utilization" in registry
    assert "theme_assignment_consistency" in registry

    tu = registry["tier_utilization"]
    assert tu.gated is True
    assert tu.pro_comparable is False
    assert tu.tolerance is not None
    assert tu.tolerance.kind == "absolute"
    assert tu.tolerance.value == pytest.approx(0.05)

    tac = registry["theme_assignment_consistency"]
    assert tac.gated is True
    assert tac.pro_comparable is False
