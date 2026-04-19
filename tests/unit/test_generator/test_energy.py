"""Tests for section energy derivation."""
import pytest

from src.analyzer.result import TimingMark, ValueCurve
from src.generator.energy import derive_section_energies


def _make_curve(values: list[int], fps: int = 20) -> ValueCurve:
    return ValueCurve(name="full_mix", stem_source="full_mix", fps=fps, values=values)


def _make_sections(ranges: list[tuple[str, int, int]]) -> list[TimingMark]:
    return [
        TimingMark(time_ms=start, confidence=1.0, label=label, duration_ms=end - start)
        for label, start, end in ranges
    ]


class TestEnergyDerivation:
    """Test derive_section_energies with known inputs."""

    def test_average_energy_from_known_frames(self):
        # 20fps curve: each frame = 50ms. 10 frames = 500ms.
        # Section covers 0-500ms. Values are all 50 -> average should be 50.
        curve = _make_curve([50] * 10, fps=20)
        sections = _make_sections([("verse", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert len(result) == 1
        assert result[0].energy_score == 50

    def test_energy_average_low_values(self):
        curve = _make_curve([10, 20, 10, 20, 10], fps=20)
        sections = _make_sections([("intro", 0, 250)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert result[0].energy_score == 14  # mean([10,20,10,20,10]) = 14

    def test_l0_impact_boost(self):
        curve = _make_curve([30] * 10, fps=20)
        sections = _make_sections([("chorus", 0, 500)])
        impacts = [TimingMark(time_ms=100, confidence=1.0), TimingMark(time_ms=300, confidence=1.0)]
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, impacts)

        # base=30, 2 impacts * 5 = 10, total = 40
        assert result[0].energy_score == 40
        assert result[0].impact_count == 2

    def test_impact_boost_capped_at_100(self):
        curve = _make_curve([95] * 10, fps=20)
        sections = _make_sections([("chorus", 0, 500)])
        impacts = [TimingMark(time_ms=i * 50, confidence=1.0) for i in range(10)]
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, impacts)

        assert result[0].energy_score == 100

    def test_impacts_outside_section_not_counted(self):
        curve = _make_curve([30] * 20, fps=20)
        sections = _make_sections([("verse", 0, 500)])
        impacts = [TimingMark(time_ms=600, confidence=1.0)]
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, impacts)

        assert result[0].impact_count == 0
        assert result[0].energy_score == 30

    def test_mood_tier_ethereal(self):
        curve = _make_curve([20] * 10, fps=20)
        sections = _make_sections([("intro", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert result[0].mood_tier == "ethereal"

    def test_mood_tier_structural(self):
        curve = _make_curve([50] * 10, fps=20)
        sections = _make_sections([("verse", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert result[0].mood_tier == "structural"

    def test_mood_tier_aggressive(self):
        curve = _make_curve([80] * 10, fps=20)
        sections = _make_sections([("chorus", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert result[0].mood_tier == "aggressive"

    def test_empty_curve_returns_zero_energy(self):
        curve = _make_curve([], fps=20)
        sections = _make_sections([("intro", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert result[0].energy_score == 0
        assert result[0].mood_tier == "ethereal"

    def test_no_full_mix_curve_returns_zero_energy(self):
        sections = _make_sections([("intro", 0, 500)])
        energy_curves = {}

        result = derive_section_energies(sections, energy_curves, [])

        assert result[0].energy_score == 0

    def test_multiple_sections(self):
        # 20fps: frame every 50ms. 40 frames = 2000ms.
        values = [20] * 10 + [80] * 10 + [50] * 10 + [30] * 10
        curve = _make_curve(values, fps=20)
        sections = _make_sections([
            ("intro", 0, 500),
            ("chorus", 500, 1000),
            ("verse", 1000, 1500),
            ("outro", 1500, 2000),
        ])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert len(result) == 4
        assert result[0].label == "intro"
        assert result[1].label == "chorus"
        assert result[0].mood_tier == "ethereal"
        assert result[1].mood_tier == "aggressive"

    def test_last_section_extended_to_song_duration(self):
        """Last section's end_ms is extended to song_duration_ms when section
        detection stops short of the actual song end."""
        # Section detector found sections up to 500ms, but song is 1000ms.
        curve = _make_curve([50] * 20, fps=20)  # 20 frames at 20fps = 1000ms
        sections = _make_sections([("verse", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(
            sections, energy_curves, [], song_duration_ms=1000
        )

        assert len(result) == 1
        assert result[0].end_ms == 1000, (
            f"Last section should extend to song_duration_ms=1000, got {result[0].end_ms}"
        )

    def test_last_section_not_extended_when_already_covers_song(self):
        """No change when last section already ends at or past song_duration_ms."""
        curve = _make_curve([50] * 10, fps=20)
        sections = _make_sections([("verse", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(
            sections, energy_curves, [], song_duration_ms=500
        )

        assert result[0].end_ms == 500

    def test_song_duration_ms_none_preserves_existing_behavior(self):
        """Without song_duration_ms, last section end is unchanged (backward compat)."""
        curve = _make_curve([50] * 10, fps=20)
        sections = _make_sections([("verse", 0, 500)])
        energy_curves = {"full_mix": curve}

        result = derive_section_energies(sections, energy_curves, [])

        assert result[0].end_ms == 500
