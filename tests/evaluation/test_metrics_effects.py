"""Failing tests for effect histogram metrics: effect_type_histogram, js_divergence."""
import pytest
from pathlib import Path
from src.evaluation.models import SequenceSummary, Placement, load_sequence_summary
from src.evaluation.metrics.effects import effect_type_histogram, js_divergence

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "degenerate"


def make_summary(placements: list[tuple[str, str]]) -> SequenceSummary:
    """Build a SequenceSummary from a list of (effect_type, model_name) tuples."""
    pl = tuple(
        Placement(i * 1000, i * 1000 + 500, effect_type, model_name, ("#FF0000",), 0)
        for i, (effect_type, model_name) in enumerate(placements)
    )
    return SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=10_000,
        placements=pl,
        model_names=("Arch01",),
        inferred_prop_types={"Arch01": "arch"},
    )


# ---------------------------------------------------------------------------
# effect_type_histogram
# ---------------------------------------------------------------------------

def test_histogram_uniform_distribution():
    """10 placements with 2 effect types (5 each) → histogram has 2 keys, each ≈ 0.5."""
    summary = make_summary(
        [("Marquee", "Arch01")] * 5 + [("Plasma", "Arch01")] * 5
    )
    result = effect_type_histogram(summary)
    assert result.value == pytest.approx(0.0)
    hist = result.payload["histogram"]
    assert set(hist.keys()) == {"Marquee", "Plasma"}
    assert hist["Marquee"] == pytest.approx(0.5)
    assert hist["Plasma"] == pytest.approx(0.5)
    assert result.payload["unknown_fraction"] == pytest.approx(0.0)


def test_histogram_all_unknown():
    """10 placements all Unknown → histogram = {}, unknown_fraction = 1.0."""
    summary = make_summary([("Unknown", "Arch01")] * 10)
    result = effect_type_histogram(summary)
    assert result.payload["histogram"] == {}
    assert result.payload["unknown_fraction"] == pytest.approx(1.0)


def test_histogram_mixed_with_unknown():
    """8 'Marquee' + 2 'Unknown' → unknown_fraction = 0.2, histogram = {'Marquee': 1.0}."""
    summary = make_summary(
        [("Marquee", "Arch01")] * 8 + [("Unknown", "Arch01")] * 2
    )
    result = effect_type_histogram(summary)
    assert result.payload["unknown_fraction"] == pytest.approx(0.2)
    hist = result.payload["histogram"]
    assert hist == {"Marquee": pytest.approx(1.0)}


def test_histogram_empty_placements():
    """No placements → value=0.0, payload has empty histogram."""
    summary = make_summary([])
    result = effect_type_histogram(summary)
    assert result.value == pytest.approx(0.0)
    assert result.payload == {"histogram": {}, "unknown_fraction": 0.0}


# ---------------------------------------------------------------------------
# js_divergence
# ---------------------------------------------------------------------------

def test_js_divergence_identical():
    """Identical histograms → divergence ≈ 0.0."""
    h = {"Marquee": 0.5, "Plasma": 0.5}
    assert js_divergence(h, h) == pytest.approx(0.0, abs=1e-9)


def test_js_divergence_completely_different():
    """{'A': 1.0} vs {'B': 1.0} → divergence = 1.0."""
    assert js_divergence({"A": 1.0}, {"B": 1.0}) == pytest.approx(1.0)


def test_js_divergence_partial_overlap():
    """{'A': 0.5, 'B': 0.5} vs {'A': 0.5, 'C': 0.5} → in (0, 1) and symmetric."""
    p = {"A": 0.5, "B": 0.5}
    q = {"A": 0.5, "C": 0.5}
    pq = js_divergence(p, q)
    qp = js_divergence(q, p)
    assert 0.0 < pq < 1.0
    assert pq == pytest.approx(qp)


def test_js_divergence_both_empty():
    """Both empty dicts → 0.0."""
    assert js_divergence({}, {}) == pytest.approx(0.0)


def test_js_divergence_bounded():
    """Result is always in [0.0, 1.0] for various inputs."""
    cases = [
        ({"A": 1.0}, {"A": 1.0}),
        ({"A": 0.3, "B": 0.7}, {"B": 0.4, "C": 0.6}),
        ({"X": 0.25, "Y": 0.25, "Z": 0.5}, {"X": 0.5, "Y": 0.5}),
        ({}, {"A": 1.0}),
        ({"A": 1.0}, {}),
        ({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}),
    ]
    for p, q in cases:
        result = js_divergence(p, q)
        assert 0.0 <= result <= 1.0, f"Out of bounds for p={p}, q={q}: {result}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_metric_registered():
    """'effect_type_histogram' appears in the registry after import."""
    from src.evaluation.metrics import get_registry, DEFAULT_TOLERANCE

    registry = get_registry()
    assert "effect_type_histogram" in registry

    defn = registry["effect_type_histogram"]
    assert defn.kind.value == "distribution"
    assert defn.gated is True
    assert defn.pro_comparable is True
    # tolerance=None means DEFAULT_TOLERANCE applies at comparison time
    assert defn.tolerance is None


# ---------------------------------------------------------------------------
# Fixture-based
# ---------------------------------------------------------------------------

def test_single_effect_fixture_histogram():
    """single_effect.json: all placements have the same effect_type → one histogram key."""
    summary = load_sequence_summary(FIXTURES_DIR / "single_effect.json")
    result = effect_type_histogram(summary)
    hist = result.payload["histogram"]
    # All placements use the same known effect type → exactly one key
    assert len(hist) == 1
    # That single key maps to 1.0 (normalized)
    only_value = next(iter(hist.values()))
    assert only_value == pytest.approx(1.0)
    # No unknowns
    assert result.payload["unknown_fraction"] == pytest.approx(0.0)
