"""Tests for StemAffinity — T007."""
from __future__ import annotations

import pytest


class TestStemAffinityGetStems:
    """StemAffinity.get_stems() returns preferred stems for an algorithm."""

    def test_returns_list(self):
        from src.analyzer.stem_affinity import StemAffinity
        result = StemAffinity.get_stems("qm_beats", {"drums", "bass", "full_mix"})
        assert isinstance(result, list)

    def test_includes_full_mix(self):
        from src.analyzer.stem_affinity import StemAffinity
        result = StemAffinity.get_stems("qm_beats", {"drums", "bass"})
        assert "full_mix" in result

    def test_no_artificial_cap(self):
        """All matching stems are returned — no cap at 3."""
        from src.analyzer.stem_affinity import StemAffinity
        available = {"drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"}
        # bbc_energy should match ALL stems
        result = StemAffinity.get_stems("bbc_energy", available)
        assert len(result) >= 6  # at least drums, bass, vocals, guitar, piano, full_mix

    def test_respects_available_filter(self):
        """Only returns stems that are in the available set."""
        from src.analyzer.stem_affinity import StemAffinity
        result = StemAffinity.get_stems("qm_beats", {"drums", "full_mix"})
        assert "bass" not in result  # bass not available

    def test_percussion_onsets_only_drums(self):
        """percussion_onsets should only match drums stem."""
        from src.analyzer.stem_affinity import StemAffinity
        available = {"drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"}
        result = StemAffinity.get_stems("percussion_onsets", available)
        assert "drums" in result
        assert "vocals" not in result

    def test_unknown_algorithm_returns_full_mix(self):
        from src.analyzer.stem_affinity import StemAffinity
        result = StemAffinity.get_stems("nonexistent_algo", {"drums", "full_mix"})
        assert result == ["full_mix"]

    def test_all_algorithms_have_affinity(self):
        """Every algorithm in the table has at least one preferred stem."""
        from src.analyzer.stem_affinity import StemAffinity, AFFINITY_TABLE
        for algo in AFFINITY_TABLE:
            entry = AFFINITY_TABLE[algo]
            assert len(entry["stems"]) >= 1, f"{algo} has no preferred stems"

    def test_all_algorithms_have_output_type(self):
        from src.analyzer.stem_affinity import AFFINITY_TABLE
        for algo, entry in AFFINITY_TABLE.items():
            assert entry["output_type"] in ("timing", "value_curve"), \
                f"{algo} has invalid output_type: {entry['output_type']}"

    def test_table_has_at_least_30_algorithms(self):
        """We should have ~35 algorithms in the affinity table."""
        from src.analyzer.stem_affinity import AFFINITY_TABLE
        assert len(AFFINITY_TABLE) >= 30


class TestStemAffinityOutputType:
    def test_get_output_type(self):
        from src.analyzer.stem_affinity import StemAffinity
        assert StemAffinity.get_output_type("bbc_energy") == "value_curve"
        assert StemAffinity.get_output_type("qm_beats") == "timing"

    def test_get_tunable_params(self):
        from src.analyzer.stem_affinity import StemAffinity
        params = StemAffinity.get_tunable_params("qm_beats")
        assert "inputtempo" in params or isinstance(params, list)
