"""Tests for vitality metrics: palette_luminance_mean and palette_luminance_cv.

§2.3 of OpenSpec ``visual-quality-microscope``.
"""
from __future__ import annotations

import math

from src.evaluation.metrics import get_registry
from src.evaluation.metrics.vitality import (
    palette_luminance_cv,
    palette_luminance_mean,
)
from src.evaluation.models import Placement, SequenceSummary


def _make_summary(
    placements_spec: list[tuple[int, int, list[str]]],
    duration_ms: int = 60_000,
) -> SequenceSummary:
    placements = tuple(
        Placement(
            start_ms=s,
            end_ms=e,
            effect_type="Marquee",
            model_name="Arch01",
            palette_colors=tuple(colors),
            layer_index=0,
        )
        for s, e, colors in placements_spec
    )
    return SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=duration_ms,
        placements=placements,
        model_names=("Arch01",),
        inferred_prop_types={"Arch01": "arch"},
    )


# ---------------------------------------------------------------------------
# palette_luminance_mean
# ---------------------------------------------------------------------------


def test_mean_all_black() -> None:
    summary = _make_summary([
        (0, 1000, ["#000000"]),
        (1000, 2000, ["#000000", "#000000"]),
    ])
    result = palette_luminance_mean(summary)

    assert result.name == "palette_luminance_mean"
    assert result.reliability == "ok"
    assert result.value == 0.0


def test_mean_all_white() -> None:
    summary = _make_summary([
        (0, 1000, ["#FFFFFF"]),
        (1000, 2000, ["#FFFFFF", "#FFFFFF"]),
    ])
    result = palette_luminance_mean(summary)

    assert result.reliability == "ok"
    assert math.isclose(result.value, 255.0, abs_tol=1e-9)


def test_mean_mixed_palette_rec601_pure_red() -> None:
    """Pure red ``#FF0000`` → ``0.299 * 255 = 76.245``."""
    summary = _make_summary([(0, 1000, ["#FF0000"])])
    result = palette_luminance_mean(summary)

    assert result.reliability == "ok"
    assert math.isclose(result.value, 76.245, abs_tol=1e-6)


def test_mean_mixed_palette_rec601_pure_green() -> None:
    """Pure green ``#00FF00`` → ``0.587 * 255 = 149.685``."""
    summary = _make_summary([(0, 1000, ["#00FF00"])])
    result = palette_luminance_mean(summary)

    assert math.isclose(result.value, 149.685, abs_tol=1e-6)


def test_mean_mixed_palette_rec601_pure_blue() -> None:
    """Pure blue ``#0000FF`` → ``0.114 * 255 = 29.07``."""
    summary = _make_summary([(0, 1000, ["#0000FF"])])
    result = palette_luminance_mean(summary)

    assert math.isclose(result.value, 29.07, abs_tol=1e-6)


def test_mean_skips_placements_with_no_palette() -> None:
    """A placement without ``palette_colors`` must not penalise the mean."""
    summary = _make_summary([
        (0, 1000, ["#FFFFFF"]),
        (1000, 9000, []),  # skipped — no palette
    ])
    result = palette_luminance_mean(summary)

    # Mean should be 255 (only the white placement counted), not diluted.
    assert math.isclose(result.value, 255.0, abs_tol=1e-9)
    assert result.reliability == "ok"


def test_mean_empty_placements_returns_zero_with_no_placements() -> None:
    summary = _make_summary([])
    result = palette_luminance_mean(summary)

    assert result.value == 0.0
    assert result.reliability == "no_placements"


def test_mean_all_placements_have_no_palette_returns_no_placements() -> None:
    """If no placement has a palette, treat the song as empty for vitality."""
    summary = _make_summary([
        (0, 1000, []),
        (1000, 2000, []),
    ])
    result = palette_luminance_mean(summary)

    assert result.value == 0.0
    assert result.reliability == "no_placements"


# ---------------------------------------------------------------------------
# palette_luminance_cv
# ---------------------------------------------------------------------------


def test_cv_single_placement_is_zero() -> None:
    summary = _make_summary([(0, 1000, ["#FF0000"])])
    result = palette_luminance_cv(summary)

    assert result.name == "palette_luminance_cv"
    assert result.reliability == "ok"
    assert result.value == 0.0


def test_cv_two_placements_identical_luminance_is_zero() -> None:
    summary = _make_summary([
        (0, 1000, ["#FF0000"]),
        (1000, 5000, ["#FF0000"]),
    ])
    result = palette_luminance_cv(summary)

    assert result.value == 0.0
    assert result.reliability == "ok"


def test_cv_duration_weighted_population() -> None:
    """Two placements, very different luminance, very different durations.

    Hand-computed expected value:
      luma1 = 0      (black) weight = 1000
      luma2 = 255    (white) weight = 9000
      weighted_mean = (0*1000 + 255*9000) / 10000 = 229.5
      weighted_var  = (1000*(0-229.5)**2 + 9000*(255-229.5)**2) / 10000
                    = (52670250 + 5852250) / 10000 = 5852.25
      weighted_std  = 76.5
      cv            = 76.5 / 229.5 = 1/3 ≈ 0.3333333

    The unweighted population on the *same* two values would give
    cv = 1.0 (mean=127.5, std=127.5). Confirming the metric is using
    the weighted form.
    """
    summary = _make_summary([
        (0, 1000, ["#000000"]),
        (1000, 10_000, ["#FFFFFF"]),
    ])
    result = palette_luminance_cv(summary)

    expected = 1.0 / 3.0
    assert math.isclose(result.value, expected, abs_tol=1e-9), (
        f"weighted cv expected ≈ {expected}, got {result.value}"
    )
    # Sanity: confirm the unweighted answer (1.0) is *not* what we got.
    assert not math.isclose(result.value, 1.0, abs_tol=1e-3)


def test_cv_empty_placements_returns_zero_with_no_placements() -> None:
    summary = _make_summary([])
    result = palette_luminance_cv(summary)

    assert result.value == 0.0
    assert result.reliability == "no_placements"


def test_cv_zero_mean_returns_zero() -> None:
    """All-black palette → mean=0; cv must guard against div-by-zero."""
    summary = _make_summary([
        (0, 1000, ["#000000"]),
        (1000, 5000, ["#000000"]),
    ])
    result = palette_luminance_cv(summary)

    assert result.value == 0.0
    assert result.reliability == "ok"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_metrics_registered() -> None:
    import src.evaluation.metrics.vitality  # noqa: F401 — trigger registration

    registry = get_registry()
    assert "palette_luminance_mean" in registry
    assert "palette_luminance_cv" in registry

    mean_def = registry["palette_luminance_mean"]
    cv_def = registry["palette_luminance_cv"]

    for defn in (mean_def, cv_def):
        assert defn.gated is True
        assert defn.pro_comparable is False
        assert defn.higher_is_better is None
