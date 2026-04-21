"""Tests for palette metrics: palette_top5_colors and per_section_palette_diversity."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.evaluation.models import Placement, SequenceSummary, load_sequence_summary
from src.evaluation.metrics import get_registry


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "degenerate"


def make_summary(placements_spec, duration_ms=60000):
    placements = tuple(
        Placement(s, e, "Marquee", "Arch01", tuple(colors), 0)
        for s, e, colors in placements_spec
    )
    return SequenceSummary(
        song_id="test", source_label="ours", duration_ms=duration_ms,
        placements=placements, model_names=("Arch01",),
        inferred_prop_types={"Arch01": "arch"}
    )


# ---------------------------------------------------------------------------
# palette_top5_colors tests
# ---------------------------------------------------------------------------

def test_palette_top5_single_color():
    from src.evaluation.metrics.palette import palette_top5_colors

    summary = make_summary([(i * 1000, (i + 1) * 1000, ["#FF0000"]) for i in range(10)])
    result = palette_top5_colors(summary)

    assert result.name == "palette_top5_colors"
    assert result.payload, "payload should not be empty"
    assert result.payload[0][0] == "#FF0000"
    assert math.isclose(result.payload[0][1], 1.0, abs_tol=1e-9)
    assert math.isclose(result.value, 1.0, abs_tol=1e-9)


def test_palette_top5_two_colors_equal_time():
    from src.evaluation.metrics.palette import palette_top5_colors

    spec = [(i * 1000, (i + 1) * 1000, ["#FF0000"]) for i in range(5)]
    spec += [(i * 1000 + 5000, i * 1000 + 6000, ["#0000FF"]) for i in range(5)]
    summary = make_summary(spec)
    result = palette_top5_colors(summary)

    assert len(result.payload) == 2
    colors = {entry[0]: entry[1] for entry in result.payload}
    assert "#FF0000" in colors
    assert "#0000FF" in colors
    assert math.isclose(colors["#FF0000"], 0.5, abs_tol=1e-9)
    assert math.isclose(colors["#0000FF"], 0.5, abs_tol=1e-9)


def test_palette_top5_max_5_colors():
    from src.evaluation.metrics.palette import palette_top5_colors

    colors_list = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF",
                   "#00FFFF", "#FF8800", "#8800FF", "#00FF88", "#880000"]
    spec = [(i * 1000, (i + 1) * 1000, [colors_list[i]]) for i in range(10)]
    summary = make_summary(spec)
    result = palette_top5_colors(summary)

    assert len(result.payload) <= 5


def test_palette_top5_empty():
    from src.evaluation.metrics.palette import palette_top5_colors

    summary = make_summary([])
    result = palette_top5_colors(summary)

    assert result.value == 0.0
    assert result.payload == []


def test_palette_top5_value_is_top_color_share():
    from src.evaluation.metrics.palette import palette_top5_colors

    spec = [(0, 3000, ["#FF0000"]), (3000, 5000, ["#0000FF"])]
    summary = make_summary(spec)
    result = palette_top5_colors(summary)

    assert result.payload, "payload should not be empty"
    assert math.isclose(result.value, result.payload[0][1], abs_tol=1e-9)


# ---------------------------------------------------------------------------
# per_section_palette_diversity tests
# ---------------------------------------------------------------------------

def test_per_section_palette_diversity_basic():
    from src.evaluation.metrics.palette import per_section_palette_diversity

    # section A: placements with red; section B: placements with blue + green
    spec = [
        (0, 1000, ["#FF0000"]),
        (1000, 2000, ["#FF0000"]),
        (5000, 6000, ["#0000FF"]),
        (5000, 6000, ["#00FF00"]),
    ]
    summary = make_summary(spec, duration_ms=10000)
    sections = [
        {"start_ms": 0, "end_ms": 4000, "label": "A"},
        {"start_ms": 4000, "end_ms": 10000, "label": "B"},
    ]
    result = per_section_palette_diversity(summary, sections)

    assert result.name == "per_section_palette_diversity"
    by_label = {e["section_label"]: e["unique_colors"] for e in result.payload}
    assert by_label["A"] == 1
    assert by_label["B"] == 2
    # mean = (1 + 2) / 2 = 1.5
    assert math.isclose(result.value, 1.5, abs_tol=1e-9)


def test_per_section_palette_diversity_no_sections():
    from src.evaluation.metrics.palette import per_section_palette_diversity

    spec = [(0, 1000, ["#FF0000"]), (1000, 2000, ["#00FF00"])]
    summary = make_summary(spec, duration_ms=5000)
    result = per_section_palette_diversity(summary, sections=None)

    assert len(result.payload) == 1
    assert result.payload[0]["unique_colors"] == 2
    assert math.isclose(result.value, 2.0, abs_tol=1e-9)


def test_per_section_palette_diversity_empty_placements():
    from src.evaluation.metrics.palette import per_section_palette_diversity

    summary = make_summary([])
    sections = [{"start_ms": 0, "end_ms": 60000, "label": "whole"}]
    result = per_section_palette_diversity(summary, sections)

    assert result.value == 0.0


# ---------------------------------------------------------------------------
# Registry test
# ---------------------------------------------------------------------------

def test_metrics_registered():
    import src.evaluation.metrics.palette  # noqa: F401 — trigger registration

    registry = get_registry()
    assert "palette_top5_colors" in registry
    assert "per_section_palette_diversity" in registry


# ---------------------------------------------------------------------------
# Fixture-based test
# ---------------------------------------------------------------------------

def test_monochrome_fixture_top_color_share_is_1():
    from src.evaluation.metrics.palette import palette_top5_colors

    summary = load_sequence_summary(FIXTURES_DIR / "monochrome.json")
    result = palette_top5_colors(summary)

    assert result.value is not None
    assert math.isclose(result.value, 1.0, abs_tol=0.01), (
        f"Expected top color share ≈ 1.0 for monochrome fixture, got {result.value}"
    )
    assert result.payload[0][0] == "#FFFFFF"
