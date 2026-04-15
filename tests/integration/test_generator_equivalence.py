"""Canonical-XML equivalence gate for spec 048 (pipeline decision-ordering refactor).

The refactor MUST NOT change `.xsq` output for any fixture permutation. This test
regenerates `.xsq` for four fixture permutations from a deterministic mock hierarchy +
mock layout, canonicalises via `xml.etree.ElementTree.canonicalize` (C14N 2.0), and
compares byte-for-byte against pre-captured goldens committed under
`tests/fixtures/xsq/048_golden/`.

Any surviving diff after canonicalisation is a merge-blocking regression. No per-fixture
whitelist.

Golden capture is one-shot and explicit: run the `capture_goldens` helper via the
`--capture-only` flag (skipped by default). Goldens are versioned with the refactor
branch — they are NOT regenerated during a refactor pass.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
from src.effects.library import load_effect_library
from src.generator.models import GenerationConfig
from src.generator.plan import build_plan
from src.generator.xsq_writer import write_xsq
from src.grouper.classifier import classify_props, normalize_coords
from src.grouper.grouper import generate_groups
from src.grouper.layout import parse_layout
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library


GOLDEN_DIR = Path(__file__).parent.parent / "fixtures" / "xsq" / "048_golden"
LAYOUT_PATH = Path(__file__).parent.parent / "fixtures" / "generate" / "mock_layout.xml"
FIXTURE_AUDIO = Path(__file__).parent.parent / "fixtures" / "10s_vocals.wav"


PERMUTATIONS = ("default", "no_focus", "no_tier_selection", "no_accents")


# ---------------------------------------------------------------------------
# Deterministic fixture hierarchy
# ---------------------------------------------------------------------------

def _build_fixture_hierarchy() -> HierarchyResult:
    """Build a deterministic mock HierarchyResult — avoids running heavy analysis.

    Designed to exercise multiple sections with varying energy so the generator
    traverses tier selection, palette restraint, duration scaling, and accent gate
    branches. The fixture is stable across runs by construction.
    """
    # 20 seconds at 120 BPM → 500ms per beat, 2000ms per bar
    beats = TimingTrack(
        name="beats",
        algorithm_name="librosa_beats",
        element_type="beat",
        marks=[
            TimingMark(time_ms=i * 500, confidence=1.0, label=str((i % 4) + 1))
            for i in range(40)
        ],
        quality_score=0.85,
    )
    bars = TimingTrack(
        name="bars",
        algorithm_name="librosa_beats",
        element_type="bar",
        marks=[TimingMark(time_ms=i * 2000, confidence=1.0) for i in range(10)],
        quality_score=0.8,
    )
    sections = [
        TimingMark(time_ms=0, confidence=1.0, label="intro", duration_ms=4000),
        TimingMark(time_ms=4000, confidence=1.0, label="verse", duration_ms=6000),
        TimingMark(time_ms=10000, confidence=1.0, label="chorus", duration_ms=6000),
        TimingMark(time_ms=16000, confidence=1.0, label="outro", duration_ms=4000),
    ]
    energy_values = (
        [20] * 16 +  # intro: low
        [45] * 24 +  # verse: medium
        [85] * 24 +  # chorus: high — will trigger impact accent gate
        [25] * 16    # outro: low
    )
    full_mix_curve = ValueCurve(
        name="full_mix", stem_source="full_mix", fps=4, values=energy_values
    )
    # Drum curve — higher during chorus so the per-hit energy gate passes
    drums_curve = ValueCurve(
        name="drums",
        stem_source="drums",
        fps=4,
        values=[10] * 16 + [30] * 24 + [80] * 24 + [15] * 16,
    )
    drum_track = TimingTrack(
        name="drums",
        algorithm_name="onsets",
        element_type="onset",
        marks=[
            TimingMark(time_ms=i * 500, confidence=1.0, label="kick" if i % 4 == 0 else "snare")
            for i in range(40)
        ],
        quality_score=0.8,
    )
    impacts = [
        TimingMark(time_ms=10500, confidence=1.0),
        TimingMark(time_ms=13000, confidence=1.0),
    ]
    return HierarchyResult(
        schema_version="2.0.0",
        source_file=str(FIXTURE_AUDIO),
        source_hash="fixture048",
        duration_ms=20000,
        estimated_bpm=120.0,
        sections=sections,
        beats=beats,
        bars=bars,
        energy_curves={"full_mix": full_mix_curve, "drums": drums_curve},
        events={"drums": drum_track},
        energy_impacts=impacts,
    )


def _config_for(permutation: str, tmp_path: Path) -> GenerationConfig:
    """Build a GenerationConfig for one of the fixture permutations."""
    base = dict(
        audio_path=FIXTURE_AUDIO,
        layout_path=LAYOUT_PATH,
        output_dir=tmp_path,
        genre="pop",
        occasion="general",
        curves_mode="none",           # curves disabled so output is stable
        transition_mode="none",       # transitions disabled so output is stable
        focused_vocabulary=True,
        embrace_repetition=True,
        palette_restraint=True,
        duration_scaling=True,
        beat_accent_effects=True,
        tier_selection=True,
    )
    if permutation == "default":
        pass
    elif permutation == "no_focus":
        base["focused_vocabulary"] = False
    elif permutation == "no_tier_selection":
        base["tier_selection"] = False
    elif permutation == "no_accents":
        base["beat_accent_effects"] = False
    else:
        raise ValueError(f"Unknown permutation: {permutation}")
    return GenerationConfig(**base)


def _generate_xsq(permutation: str, tmp_path: Path) -> Path:
    """Run the full pipeline on the mock hierarchy + layout; return the written .xsq path."""
    config = _config_for(permutation, tmp_path)
    hierarchy = _build_fixture_hierarchy()

    layout = parse_layout(config.layout_path)
    props = layout.props
    normalize_coords(props)
    classify_props(props)
    groups = generate_groups(props)

    effect_library = load_effect_library()
    variant_library = load_variant_library(effect_library=effect_library)
    theme_library = load_theme_library(
        effect_library=effect_library, variant_library=variant_library
    )

    plan = build_plan(config, hierarchy, props, groups, effect_library, theme_library)

    output_path = tmp_path / f"{permutation}.xsq"
    write_xsq(plan, output_path, hierarchy=hierarchy, audio_path=None)
    return output_path


# ---------------------------------------------------------------------------
# Canonical XML helper (FR-031, research.md §3)
# ---------------------------------------------------------------------------

def _canon(xsq_path: Path) -> str:
    """Return the C14N 2.0 canonicalised XML of an .xsq file.

    `strip_text=True` collapses insignificant whitespace. C14N 2.0 guarantees
    lexicographic attribute order. Any surviving diff is a true regression.
    """
    return ET.canonicalize(
        xml_data=xsq_path.read_text(encoding="utf-8"),
        strip_text=True,
    )


# ---------------------------------------------------------------------------
# Equivalence tests (T005) — one per permutation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("permutation", PERMUTATIONS)
def test_xsq_canonical_equivalence(permutation: str, tmp_path: Path) -> None:
    """Generated .xsq must be canonically equal to the pre-captured golden."""
    golden_path = GOLDEN_DIR / f"{permutation}.xsq"
    if not golden_path.exists():
        pytest.skip(
            f"Golden missing: {golden_path.relative_to(Path.cwd()) if golden_path.is_absolute() else golden_path}"
            f" — run capture_goldens first"
        )
    generated = _generate_xsq(permutation, tmp_path)
    got = _canon(generated)
    expected = _canon(golden_path)
    assert got == expected, (
        f"XSQ output diverged for permutation '{permutation}'. "
        f"The refactor has introduced a behavioural change — this is forbidden by spec 048."
    )


# ---------------------------------------------------------------------------
# Capture helper (T006) — gated by @pytest.mark.capture_only; skipped by default
# ---------------------------------------------------------------------------

@pytest.mark.capture_only
def test_capture_goldens(tmp_path: Path) -> None:
    """Write current-code output as new goldens. Normally skipped.

    Invoke explicitly:  pytest -v -m capture_only tests/integration/test_generator_equivalence.py

    This helper is used ONCE per intentional behaviour change — never during a
    pure refactor. For spec 048, goldens are captured on pre-refactor `main` and
    are thereafter read-only.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for permutation in PERMUTATIONS:
        generated = _generate_xsq(permutation, tmp_path)
        dest = GOLDEN_DIR / f"{permutation}.xsq"
        dest.write_bytes(generated.read_bytes())
        print(f"Captured golden: {dest}")


def capture_goldens(target_dir: Path | None = None) -> None:
    """Programmatic entry point for one-shot golden capture from a shell/CLI script."""
    import tempfile

    out_dir = target_dir or GOLDEN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for permutation in PERMUTATIONS:
            generated = _generate_xsq(permutation, tmp_path)
            dest = out_dir / f"{permutation}.xsq"
            dest.write_bytes(generated.read_bytes())
            print(f"Captured golden: {dest}")


if __name__ == "__main__":
    # Allow: python tests/integration/test_generator_equivalence.py
    capture_goldens()
