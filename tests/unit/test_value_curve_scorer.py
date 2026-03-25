"""Tests for value curve scoring — T011."""
from __future__ import annotations

import numpy as np
import pytest


class TestScoreValueCurve:
    """T011: score_value_curve() rates continuous data quality."""

    def test_returns_float_in_0_1(self):
        from src.analyzer.value_curve_scorer import score_value_curve
        curve = list(range(0, 100, 2))  # smooth ramp 0-98
        score = score_value_curve(curve)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_high_dynamic_range_scores_higher(self):
        from src.analyzer.value_curve_scorer import score_value_curve
        wide = [0, 50, 100, 50, 0, 50, 100, 50]  # full 0-100 range
        narrow = [48, 50, 52, 50, 48, 50, 52, 50]  # only 48-52
        assert score_value_curve(wide) > score_value_curve(narrow)

    def test_structured_scores_higher_than_random(self):
        from src.analyzer.value_curve_scorer import score_value_curve
        np.random.seed(42)
        structured = [int(50 + 40 * np.sin(i / 10)) for i in range(200)]
        random_noise = [int(np.random.randint(0, 100)) for _ in range(200)]
        assert score_value_curve(structured) > score_value_curve(random_noise)

    def test_flat_curve_scores_low(self):
        from src.analyzer.value_curve_scorer import score_value_curve
        flat = [50] * 100
        score = score_value_curve(flat)
        assert score < 0.2

    def test_empty_curve_scores_zero(self):
        from src.analyzer.value_curve_scorer import score_value_curve
        assert score_value_curve([]) == 0.0
