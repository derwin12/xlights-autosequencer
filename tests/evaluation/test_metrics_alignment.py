"""Failing tests for beat alignment metric: beat_alignment_pct."""
import pytest
from pathlib import Path
from src.evaluation.models import SequenceSummary, Placement, load_sequence_summary

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "degenerate"


def make_summary_with_starts(start_times, duration_ms=60000):
    placements = tuple(
        Placement(s, s + 200, "Marquee", "Arch01", ("#FF0000",), 0)
        for s in start_times
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
# beat_alignment_pct
# ---------------------------------------------------------------------------

def test_all_aligned():
    """5 placements each exactly on a beat → value == 1.0."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    summary = make_summary_with_starts([0, 500, 1000, 1500, 2000])
    result = beat_alignment_pct(summary, beats=[0, 500, 1000, 1500, 2000])
    assert result.value == pytest.approx(1.0)


def test_none_aligned():
    """3 placements all > 80ms from any beat → value == 0.0."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    # placements at 0, 500, 1000; beats at 250, 750, 1250 — gap is 250ms each
    summary = make_summary_with_starts([0, 500, 1000])
    result = beat_alignment_pct(summary, beats=[250, 750, 1250])
    assert result.value == pytest.approx(0.0)


def test_within_tolerance():
    """Placement at 80ms, beat at 0 — exactly 80ms away — should be ALIGNED."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    summary = make_summary_with_starts([80])
    result = beat_alignment_pct(summary, beats=[0])
    assert result.value == pytest.approx(1.0)


def test_just_outside_tolerance():
    """Placement at 81ms, beat at 0 — 81ms away — NOT aligned."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    summary = make_summary_with_starts([81])
    result = beat_alignment_pct(summary, beats=[0])
    assert result.value == pytest.approx(0.0)


def test_partial_alignment():
    """4 placements: 2 aligned, 2 not → value == 0.5."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    # beats at 0 and 1000; placements at 0 (aligned), 81 (not), 1000 (aligned), 1200 (not)
    summary = make_summary_with_starts([0, 81, 1000, 1200])
    result = beat_alignment_pct(summary, beats=[0, 1000])
    assert result.value == pytest.approx(0.5)


def test_empty_placements():
    """No placements → value == 0.0."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    summary = make_summary_with_starts([])
    result = beat_alignment_pct(summary, beats=[0, 500, 1000])
    assert result.value == pytest.approx(0.0)


def test_none_beats():
    """beats=None → value == 0.0."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    summary = make_summary_with_starts([0, 500, 1000])
    result = beat_alignment_pct(summary, beats=None)
    assert result.value == pytest.approx(0.0)


def test_empty_beats():
    """beats=[] → value == 0.0."""
    from src.evaluation.metrics.alignment import beat_alignment_pct

    summary = make_summary_with_starts([0, 500, 1000])
    result = beat_alignment_pct(summary, beats=[])
    assert result.value == pytest.approx(0.0)


def test_metric_registered():
    """Registry contains 'beat_alignment_pct' with absolute tolerance of 0.03."""
    import src.evaluation.metrics.alignment  # ensure module is imported and registered  # noqa: F401
    from src.evaluation.metrics import get_registry

    registry = get_registry()
    assert "beat_alignment_pct" in registry

    defn = registry["beat_alignment_pct"]
    assert defn.gated is True
    assert defn.pro_comparable is True
    assert defn.tolerance is not None
    assert defn.tolerance.kind == "absolute"
    assert defn.tolerance.value == pytest.approx(0.03)


def test_random_alignment_fixture_low_score():
    """random_alignment.json uses (i*1237+73) % 179000 start times.

    With evenly-spaced beats every 500ms, the score should be < 0.5 since
    the random starts are unlikely to land within 80ms of any beat.
    """
    from src.evaluation.metrics.alignment import beat_alignment_pct

    summary = load_sequence_summary(FIXTURES_DIR / "random_alignment.json")
    beats = list(range(0, summary.duration_ms + 1, 500))

    # Compute what perfect alignment would score (all placements on beats)
    perfectly_aligned = make_summary_with_starts(
        beats[: len(summary.placements)], duration_ms=summary.duration_ms
    )
    perfect_result = beat_alignment_pct(perfectly_aligned, beats=beats)

    random_result = beat_alignment_pct(summary, beats=beats)

    assert random_result.value is not None
    assert random_result.value < 0.5
    # Perfect alignment should score higher than random
    assert perfect_result.value > random_result.value
