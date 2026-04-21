"""Failing tests for section_transition_delta metric."""
from __future__ import annotations

import pytest
from src.evaluation.models import SequenceSummary, Placement
from src.evaluation.metrics.sections import section_transition_delta


def make_placement(start_ms: int, end_ms: int, effect_type: str, palette_colors: tuple[str, ...]) -> Placement:
    return Placement(
        start_ms=start_ms,
        end_ms=end_ms,
        effect_type=effect_type,
        model_name="Arch01",
        palette_colors=palette_colors,
        layer_index=0,
    )


def make_summary(placements: list[Placement], duration_ms: int = 60_000) -> SequenceSummary:
    return SequenceSummary(
        song_id="test",
        source_label="ours",
        duration_ms=duration_ms,
        placements=tuple(placements),
        model_names=("Arch01",),
        inferred_prop_types={"Arch01": "arch"},
    )


# ---------------------------------------------------------------------------
# 1. No sections → value=0.0, payload=[]
# ---------------------------------------------------------------------------

def test_no_sections_returns_zero():
    summary = make_summary([
        make_placement(0, 1000, "Marquee", ("#FF0000",)),
    ])
    result = section_transition_delta(summary, sections=None)
    assert result.value == pytest.approx(0.0)
    assert result.payload == []


# ---------------------------------------------------------------------------
# 2. Single section → value=0.0, payload=[]
# ---------------------------------------------------------------------------

def test_single_section_returns_zero():
    summary = make_summary([
        make_placement(0, 1000, "Marquee", ("#FF0000",)),
    ])
    sections = [{"start_ms": 0, "end_ms": 10_000, "label": "verse"}]
    result = section_transition_delta(summary, sections=sections)
    assert result.value == pytest.approx(0.0)
    assert result.payload == []


# ---------------------------------------------------------------------------
# 3. Identical sections → transition_score ≈ 0.0
# ---------------------------------------------------------------------------

def test_identical_sections_transition_zero():
    # Two sections: both end with same palette and effect pattern.
    # Section A: 0–10000ms, section B: 10000–20000ms.
    # Placements throughout both sections use "#FF0000" and "Marquee".
    placements = []
    for i in range(20):
        t = i * 1000
        placements.append(make_placement(t, t + 900, "Marquee", ("#FF0000",)))

    summary = make_summary(placements, duration_ms=20_000)
    sections = [
        {"start_ms": 0, "end_ms": 10_000, "label": "A"},
        {"start_ms": 10_000, "end_ms": 20_000, "label": "B"},
    ]
    result = section_transition_delta(summary, sections=sections)
    assert result.value == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. Completely different sections → transition_score > 0.5
# ---------------------------------------------------------------------------

def test_completely_different_sections():
    # Section A (0–10000ms): all "#FF0000" + "Marquee"
    # Section B (10000–20000ms): all "#0000FF" + "Plasma"
    placements = []
    for i in range(10):
        t = i * 1000
        placements.append(make_placement(t, t + 900, "Marquee", ("#FF0000",)))
    for i in range(10):
        t = 10_000 + i * 1000
        placements.append(make_placement(t, t + 900, "Plasma", ("#0000FF",)))

    summary = make_summary(placements, duration_ms=20_000)
    sections = [
        {"start_ms": 0, "end_ms": 10_000, "label": "A"},
        {"start_ms": 10_000, "end_ms": 20_000, "label": "B"},
    ]
    result = section_transition_delta(summary, sections=sections)
    assert result.value > 0.5


# ---------------------------------------------------------------------------
# 5. Payload structure: 3 sections → 2 boundary entries with correct keys
# ---------------------------------------------------------------------------

def test_payload_structure():
    placements = []
    for i in range(30):
        t = i * 1000
        placements.append(make_placement(t, t + 900, "Marquee", ("#FF0000",)))

    summary = make_summary(placements, duration_ms=30_000)
    sections = [
        {"start_ms": 0, "end_ms": 10_000, "label": "verse"},
        {"start_ms": 10_000, "end_ms": 20_000, "label": "chorus"},
        {"start_ms": 20_000, "end_ms": 30_000, "label": "bridge"},
    ]
    result = section_transition_delta(summary, sections=sections)
    assert isinstance(result.payload, list)
    assert len(result.payload) == 2

    for entry in result.payload:
        assert "boundary_label" in entry
        assert "palette_delta" in entry
        assert "effect_delta" in entry
        assert "transition_score" in entry

    assert result.payload[0]["boundary_label"] == "verse → chorus"
    assert result.payload[1]["boundary_label"] == "chorus → bridge"


# ---------------------------------------------------------------------------
# 6. Metric value: mean of 2 boundary scores
# ---------------------------------------------------------------------------

def test_metric_value():
    # Section A: "#FF0000" + "Marquee" throughout
    # Section B: "#00FF00" + "Plasma" throughout  (different palette, different effect)
    # Section C: "#FF0000" + "Marquee" throughout (same as A)
    placements = []
    for i in range(10):
        t = i * 1000
        placements.append(make_placement(t, t + 900, "Marquee", ("#FF0000",)))
    for i in range(10):
        t = 10_000 + i * 1000
        placements.append(make_placement(t, t + 900, "Plasma", ("#00FF00",)))
    for i in range(10):
        t = 20_000 + i * 1000
        placements.append(make_placement(t, t + 900, "Marquee", ("#FF0000",)))

    summary = make_summary(placements, duration_ms=30_000)
    sections = [
        {"start_ms": 0, "end_ms": 10_000, "label": "A"},
        {"start_ms": 10_000, "end_ms": 20_000, "label": "B"},
        {"start_ms": 20_000, "end_ms": 30_000, "label": "C"},
    ]
    result = section_transition_delta(summary, sections=sections)
    payload = result.payload

    # Both boundaries should be symmetric (A→B and B→C have same divergence since
    # A==C and B is distinct from both). The mean should equal each boundary score.
    assert len(payload) == 2
    expected_mean = (payload[0]["transition_score"] + payload[1]["transition_score"]) / 2
    assert result.value == pytest.approx(expected_mean)


# ---------------------------------------------------------------------------
# 7. Registry contains "section_transition_delta"
# ---------------------------------------------------------------------------

def test_metric_registered():
    # sections.py registers on import; the import at top of this file triggers it.
    from src.evaluation.metrics import get_registry
    registry = get_registry()
    assert "section_transition_delta" in registry

    defn = registry["section_transition_delta"]
    assert defn.kind.value == "per_section"
    assert defn.gated is True
    assert defn.pro_comparable is True


# ---------------------------------------------------------------------------
# 8. Empty placements with 2 sections → value=0.0
# ---------------------------------------------------------------------------

def test_empty_placements():
    summary = make_summary([], duration_ms=20_000)
    sections = [
        {"start_ms": 0, "end_ms": 10_000, "label": "A"},
        {"start_ms": 10_000, "end_ms": 20_000, "label": "B"},
    ]
    result = section_transition_delta(summary, sections=sections)
    assert result.value == pytest.approx(0.0)
