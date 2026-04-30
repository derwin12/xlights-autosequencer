"""Tests for ``src.microscope.sensitivity``.

Two layers:
  * Unit tests: each synthetic probe passes on a hand-built
    ``SequenceSummary`` and fails when a registered metric's
    ``compute`` is monkeypatched to return a wrong value. Patching
    follows the ``_REGISTRY`` pattern from ``test_diff.py``: replace
    the registered ``MetricDefinition`` for the duration of a test,
    then restore the original.
  * Integration tests (marked ``slow``, skipped without fixtures)
    drive the real generator on the ``funshine`` fixture and verify
    every probe — including the deterministic-seed probe — passes.

The deterministic-seed probe checks placement-level diff (not
metric-level) because flipping ``variation_seed`` between 42 and
9999 perturbs only ~3% of placements on ``funshine`` and does not
move any registered scalar metric by ≥ 1e-3. See
``tests/microscope/test_runner.py::test_integration_funshine_seed_has_effect``.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from src.evaluation.metrics import (
    MetricDefinition,
    MetricKind,
    _REGISTRY,
)
from src.evaluation.models import MetricValue
from src.microscope.sensitivity import (
    SensitivityReport,
    SensitivityResult,
    _build_all_black_palette_summary,
    _build_forced_bad_pairing_summary,
    _build_single_effect_summary,
    _import_all_metrics,
    _run_all_black_palette_probe,
    _run_forced_bad_pairing_probe,
    _run_single_effect_probe,
    compute_metric_set_hash,
    run_sensitivity,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FUNSHINE_MP3 = _REPO_ROOT / "tests" / "fixtures" / "cc0_music" / "funshine.mp3"
_REFERENCE_LAYOUT = _REPO_ROOT / "tests" / "fixtures" / "reference" / "layout.xml"
_HAS_INTEGRATION_FIXTURES = _FUNSHINE_MP3.is_file() and _REFERENCE_LAYOUT.is_file()


@pytest.fixture(autouse=True)
def _ensure_metrics_imported():
    """Every test in this module needs the registry populated."""
    _import_all_metrics()
    yield


# ---------------------------------------------------------------------------
# Registry patching helper (mirrors test_diff.py's _register_test_metrics
# pattern but is scoped per-test rather than per-module).
# ---------------------------------------------------------------------------


@contextmanager
def _override_metric(name: str, new_compute):
    """Temporarily replace a registered metric's ``compute`` callable.

    The original ``MetricDefinition`` is restored on exit even if the
    test raises, so the global registry is not polluted.
    """
    original = _REGISTRY[name]
    patched = MetricDefinition(
        name=original.name,
        kind=original.kind,
        gated=original.gated,
        tolerance=original.tolerance,
        compute=new_compute,
        pro_comparable=original.pro_comparable,
        higher_is_better=original.higher_is_better,
    )
    _REGISTRY[name] = patched
    try:
        yield
    finally:
        _REGISTRY[name] = original


def _bad_scalar(name: str, value: float):
    """Return a ``compute`` callable that returns a fixed wrong scalar."""

    def _compute(_summary):
        return MetricValue(
            name=name,
            kind="scalar",
            value=value,
            payload=None,
            reliability="ok",
        )

    return _compute


# ---------------------------------------------------------------------------
# Unit tests — synthetic summaries
# ---------------------------------------------------------------------------


def test_single_effect_probe_passes_on_synthetic_summary():
    result = _run_single_effect_probe()
    assert result.passed, result.failure_reason
    assert result.probe_name == "single_effect"
    assert result.failure_reason is None
    # Detail names both metrics so an operator can read it.
    assert "distinct_effect_count" in result.detail
    assert "effect_repeat_rate" in result.detail


def test_single_effect_probe_fails_when_distinct_count_is_wrong():
    # Force distinct_effect_count to 7.0 — should fail the == 1.0 check.
    with _override_metric("distinct_effect_count", _bad_scalar("distinct_effect_count", 7.0)):
        result = _run_single_effect_probe()
    assert not result.passed
    assert result.failure_reason is not None
    assert "distinct_effect_count" in result.detail


def test_single_effect_probe_fails_when_repeat_rate_is_low():
    # Force effect_repeat_rate to 0.1 — should fail the >= 0.95 check.
    with _override_metric("effect_repeat_rate", _bad_scalar("effect_repeat_rate", 0.1)):
        result = _run_single_effect_probe()
    assert not result.passed
    assert result.failure_reason is not None


def test_all_black_palette_probe_passes_on_synthetic_summary():
    result = _run_all_black_palette_probe()
    assert result.passed, result.failure_reason
    assert result.probe_name == "all_black_palette"
    assert "palette_luminance_mean" in result.detail
    assert "palette_luminance_cv" in result.detail


def test_all_black_palette_probe_fails_when_mean_is_nonzero():
    with _override_metric(
        "palette_luminance_mean", _bad_scalar("palette_luminance_mean", 42.0)
    ):
        result = _run_all_black_palette_probe()
    assert not result.passed
    assert result.failure_reason is not None


def test_all_black_palette_probe_fails_when_cv_is_nonzero():
    with _override_metric(
        "palette_luminance_cv", _bad_scalar("palette_luminance_cv", 0.5)
    ):
        result = _run_all_black_palette_probe()
    assert not result.passed


def test_forced_bad_pairing_probe_passes_on_synthetic_summary():
    result = _run_forced_bad_pairing_probe()
    assert result.passed, result.failure_reason
    assert result.probe_name == "forced_bad_pairing"
    assert "bad_pairing_pct_handlist" in result.detail
    assert "bad_pairing_pct_catalog" in result.detail
    assert "pairing_disagreement_pct" in result.detail


def test_forced_bad_pairing_probe_fails_when_handlist_doesnt_flag():
    # Drop handlist flag rate to 0.0 — fails the > 0.95 check.
    with _override_metric(
        "bad_pairing_pct_handlist",
        _bad_scalar("bad_pairing_pct_handlist", 0.0),
    ):
        result = _run_forced_bad_pairing_probe()
    assert not result.passed


def test_forced_bad_pairing_probe_fails_when_catalog_does_flag():
    # If the catalog wrongly flags the pair, the disagreement collapses.
    with _override_metric(
        "bad_pairing_pct_catalog",
        _bad_scalar("bad_pairing_pct_catalog", 1.0),
    ):
        result = _run_forced_bad_pairing_probe()
    assert not result.passed


def test_forced_bad_pairing_probe_fails_when_disagreement_is_zero():
    with _override_metric(
        "pairing_disagreement_pct",
        _bad_scalar("pairing_disagreement_pct", 0.0),
    ):
        result = _run_forced_bad_pairing_probe()
    assert not result.passed


# ---------------------------------------------------------------------------
# Synthetic-summary structure invariants (cheap sanity)
# ---------------------------------------------------------------------------


def test_single_effect_summary_uses_only_plasma():
    summary = _build_single_effect_summary()
    assert summary.placements
    assert all(p.effect_type == "Plasma" for p in summary.placements)


def test_all_black_summary_uses_only_black():
    summary = _build_all_black_palette_summary()
    assert summary.placements
    assert all(p.palette_colors == ("#000000",) for p in summary.placements)


def test_forced_bad_pairing_summary_resolves_to_outline():
    summary = _build_forced_bad_pairing_summary()
    assert summary.placements
    assert all(p.effect_type == "Plasma" for p in summary.placements)
    assert all(
        summary.inferred_prop_types[p.model_name] == "outline"
        for p in summary.placements
    )


# ---------------------------------------------------------------------------
# metric_set_hash + to_dict
# ---------------------------------------------------------------------------


def test_metric_set_hash_is_deterministic():
    a = compute_metric_set_hash()
    b = compute_metric_set_hash()
    assert a == b
    # SHA-256 hex digest is 64 chars.
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_metric_set_hash_changes_when_a_metric_is_added():
    a = compute_metric_set_hash()
    extra = MetricDefinition(
        name="__sensitivity_test_extra__",
        kind=MetricKind.SCALAR,
        gated=False,
        tolerance=None,
        compute=lambda *_a, **_k: None,
        pro_comparable=False,
        higher_is_better=None,
    )
    _REGISTRY[extra.name] = extra
    try:
        b = compute_metric_set_hash()
    finally:
        _REGISTRY.pop(extra.name, None)
    assert a != b


def test_report_to_dict_is_json_serializable():
    report = SensitivityReport(
        run_at="2026-04-29T00:00:00Z",
        metric_set_hash="deadbeef",
        results=[
            SensitivityResult(
                probe_name="single_effect",
                passed=True,
                detail="ok",
                failure_reason=None,
            ),
            SensitivityResult(
                probe_name="other",
                passed=False,
                detail="bad",
                failure_reason="explained",
            ),
        ],
    )
    payload = report.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["run_at"] == "2026-04-29T00:00:00Z"
    assert decoded["metric_set_hash"] == "deadbeef"
    assert decoded["all_passed"] is False
    assert len(decoded["results"]) == 2
    assert decoded["results"][0] == {
        "probe_name": "single_effect",
        "passed": True,
        "detail": "ok",
        "failure_reason": None,
    }


def test_report_all_passed_property():
    rs_pass = [
        SensitivityResult(probe_name=n, passed=True, detail="", failure_reason=None)
        for n in ("a", "b", "c")
    ]
    report_pass = SensitivityReport(
        run_at="x", metric_set_hash="y", results=rs_pass
    )
    assert report_pass.all_passed is True

    rs_mixed = list(rs_pass) + [
        SensitivityResult(
            probe_name="d", passed=False, detail="", failure_reason="bad"
        )
    ]
    report_mixed = SensitivityReport(
        run_at="x", metric_set_hash="y", results=rs_mixed
    )
    assert report_mixed.all_passed is False


# ---------------------------------------------------------------------------
# Integration test (real generator) — slow, fixture-gated
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    not _HAS_INTEGRATION_FIXTURES,
    reason="CC0 fixture tests/fixtures/cc0_music/funshine.mp3 not downloaded",
)
def test_run_sensitivity_integration_funshine(tmp_path):
    report = run_sensitivity(_FUNSHINE_MP3, _REFERENCE_LAYOUT, tmp_path)

    assert isinstance(report, SensitivityReport)
    by_name = {r.probe_name: r for r in report.results}
    # All four probes ran.
    assert set(by_name.keys()) == {
        "single_effect",
        "all_black_palette",
        "forced_bad_pairing",
        "deterministic_seed",
    }
    # Synthetic probes always pass on the hand-built summaries.
    assert by_name["single_effect"].passed, by_name["single_effect"].detail
    assert by_name["all_black_palette"].passed, by_name["all_black_palette"].detail
    assert by_name["forced_bad_pairing"].passed, by_name["forced_bad_pairing"].detail
    # Real-generator probe: same seed → identical scalars; flipped seed →
    # at least one placement differs.
    assert by_name["deterministic_seed"].passed, by_name["deterministic_seed"].detail
    assert report.all_passed
    # JSON-serializable.
    json.dumps(report.to_dict())
