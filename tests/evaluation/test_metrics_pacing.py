"""Failing tests for pacing metrics: placements_per_minute, density_energy_correlation."""
import pytest
from pathlib import Path
from src.evaluation.models import SequenceSummary, Placement, load_sequence_summary
from src.evaluation.metrics.pacing import placements_per_minute, density_energy_correlation

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "degenerate"


def make_summary(n_placements: int, duration_ms: int, effect_type: str = "Marquee") -> SequenceSummary:
    placements = tuple(
        Placement(i * 1000, i * 1000 + 500, effect_type, "Arch01", ("#FF0000",), 0)
        for i in range(n_placements)
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
# placements_per_minute
# ---------------------------------------------------------------------------

def test_placements_per_minute_basic():
    """60 placements in 60 seconds → 60.0 ppm."""
    summary = make_summary(60, 60_000)
    result = placements_per_minute(summary)
    assert result.value == pytest.approx(60.0)


def test_placements_per_minute_two_minutes():
    """120 placements in 120 seconds → still 60.0 ppm."""
    summary = make_summary(120, 120_000)
    result = placements_per_minute(summary)
    assert result.value == pytest.approx(60.0)


def test_placements_per_minute_empty_placements():
    """Zero placements → value is 0.0."""
    summary = make_summary(0, 60_000)
    result = placements_per_minute(summary)
    assert result.value == pytest.approx(0.0)


def test_placements_per_minute_zero_duration():
    """duration_ms == 0 must not raise; value is 0.0."""
    summary = make_summary(5, 0)
    result = placements_per_minute(summary)
    assert result.value == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# density_energy_correlation
# ---------------------------------------------------------------------------

def test_density_energy_correlation_perfect():
    """Placement counts that perfectly track the energy curve → correlation > 0.9."""
    window_ms = 500
    n_windows = 20
    duration_ms = n_windows * window_ms  # 10 000 ms

    # Build an energy curve: linearly rising from 0.1 to 1.0
    energy_curve = [
        (w * window_ms, 0.1 + 0.9 * w / (n_windows - 1))
        for w in range(n_windows)
    ]

    # Place exactly round(energy * 10) placements in each window so counts
    # mirror the energy curve perfectly.
    placements: list[Placement] = []
    for w, (t_ms, energy) in enumerate(energy_curve):
        count = max(1, round(energy * 10))
        for k in range(count):
            start = t_ms + k * (window_ms // count)
            placements.append(
                Placement(start, start + 100, "Marquee", "Arch01", ("#FF0000",), 0)
            )

    summary = SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=duration_ms,
        placements=tuple(placements),
        model_names=("Arch01",),
        inferred_prop_types={"Arch01": "arch"},
    )

    audio_context = {"energy_curve": energy_curve, "window_ms": window_ms}
    result = density_energy_correlation(summary, audio_context)
    assert result.value is not None
    assert result.value > 0.9


def test_density_energy_correlation_no_audio_context():
    """None audio_context → value == 0.0."""
    summary = make_summary(30, 60_000)
    result = density_energy_correlation(summary, None)
    assert result.value == pytest.approx(0.0)


def test_density_energy_correlation_empty_energy():
    """Empty energy_curve list → value == 0.0."""
    summary = make_summary(30, 60_000)
    audio_context = {"energy_curve": [], "window_ms": 500}
    result = density_energy_correlation(summary, audio_context)
    assert result.value == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_metric_registered():
    """Both metrics appear in the registry with correct tolerances after import."""
    from src.evaluation.metrics import get_registry, DEFAULT_TOLERANCE

    registry = get_registry()
    assert "placements_per_minute" in registry
    assert "density_energy_correlation" in registry

    ppm_defn = registry["placements_per_minute"]
    assert ppm_defn.gated is True
    assert ppm_defn.pro_comparable is True
    assert ppm_defn.tolerance is not None
    assert ppm_defn.tolerance.kind == "relative"
    assert ppm_defn.tolerance.value == pytest.approx(0.15)

    dec_defn = registry["density_energy_correlation"]
    assert dec_defn.gated is True
    assert dec_defn.pro_comparable is True
    # tolerance=None means DEFAULT_TOLERANCE applies; the stored value is None
    assert dec_defn.tolerance is None


# ---------------------------------------------------------------------------
# Fixture-based
# ---------------------------------------------------------------------------

def test_placements_per_minute_on_monochrome_fixture():
    """monochrome.json has 300 placements over 180 s → 100 ppm."""
    summary = load_sequence_summary(FIXTURES_DIR / "monochrome.json")
    result = placements_per_minute(summary)
    assert result.value == pytest.approx(100.0)
