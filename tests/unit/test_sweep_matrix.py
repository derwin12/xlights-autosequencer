"""Tests for segment selector (T009) and SweepMatrixConfig (T013)."""
from __future__ import annotations

import numpy as np
import pytest


class TestSelectRepresentativeSegment:
    """T009: select_representative_segment() picks a high-energy window."""

    def test_returns_start_and_end_ms(self, tmp_path):
        from src.analyzer.segment_selector import select_representative_segment
        # Create a simple WAV with energy spike in the middle
        import soundfile as sf
        sr = 22050
        audio = np.random.randn(sr * 10).astype(np.float32) * 0.01  # 10s quiet
        audio[sr * 4:sr * 7] = np.random.randn(sr * 3).astype(np.float32) * 0.5  # loud 4-7s
        path = tmp_path / "test.wav"
        sf.write(str(path), audio, sr)

        start_ms, end_ms = select_representative_segment(str(path), duration_s=3.0)
        assert isinstance(start_ms, int)
        assert isinstance(end_ms, int)
        assert end_ms > start_ms

    def test_avoids_first_10_percent(self, tmp_path):
        from src.analyzer.segment_selector import select_representative_segment
        import soundfile as sf
        sr = 22050
        # Energy spike at the very beginning (0-1s)
        audio = np.random.randn(sr * 20).astype(np.float32) * 0.01
        audio[:sr] = np.random.randn(sr).astype(np.float32) * 1.0
        # Energy spike in middle (10-13s)
        audio[sr * 10:sr * 13] = np.random.randn(sr * 3).astype(np.float32) * 0.8
        path = tmp_path / "test.wav"
        sf.write(str(path), audio, sr)

        start_ms, end_ms = select_representative_segment(str(path), duration_s=3.0)
        # Should avoid the first 10% (0-2s) and pick the middle spike instead
        assert start_ms >= 1500  # at least past the first 10%

    def test_segment_duration_matches_requested(self, tmp_path):
        from src.analyzer.segment_selector import select_representative_segment
        import soundfile as sf
        sr = 22050
        audio = np.random.randn(sr * 30).astype(np.float32) * 0.1
        audio[sr * 15:sr * 20] = np.random.randn(sr * 5).astype(np.float32) * 0.5
        path = tmp_path / "test.wav"
        sf.write(str(path), audio, sr)

        start_ms, end_ms = select_representative_segment(str(path), duration_s=5.0)
        duration = end_ms - start_ms
        assert abs(duration - 5000) < 200  # within 200ms of requested

    def test_short_audio_returns_full_range(self, tmp_path):
        from src.analyzer.segment_selector import select_representative_segment
        import soundfile as sf
        sr = 22050
        audio = np.random.randn(sr * 10).astype(np.float32) * 0.1
        path = tmp_path / "test.wav"
        sf.write(str(path), audio, sr)

        start_ms, end_ms = select_representative_segment(str(path), duration_s=30.0)
        # Song is only 10s, requested 30s → return full song
        assert start_ms == 0
        assert abs(end_ms - 10000) < 200


class TestSweepMatrixConfig:
    """T013: SweepMatrixConfig.build_matrix() produces correct permutations."""

    def test_build_matrix_cross_product(self):
        from src.analyzer.sweep_matrix import SweepMatrixConfig
        config = SweepMatrixConfig(
            algorithms=["qm_beats"],
            available_stems={"drums", "bass", "full_mix"},
            param_overrides={"qm_beats": {"inputtempo": [100, 120, 140]}},
        )
        matrix = config.build_matrix()
        # qm_beats affinity: drums, bass, full_mix → 3 stems × 3 tempos = 9
        assert matrix.total_count == 9

    def test_deduplicates(self):
        from src.analyzer.sweep_matrix import SweepMatrixConfig
        config = SweepMatrixConfig(
            algorithms=["qm_tempo"],  # no tunable params
            available_stems={"drums", "full_mix"},
        )
        matrix = config.build_matrix()
        # No params → 1 permutation per stem = 2 total
        assert matrix.total_count == 2

    def test_safety_cap(self):
        from src.analyzer.sweep_matrix import SweepMatrixConfig
        config = SweepMatrixConfig(
            algorithms=["qm_beats"],
            available_stems={"drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"},
            param_overrides={"qm_beats": {"inputtempo": list(range(40, 240, 5))}},
            max_permutations=10,
        )
        matrix = config.build_matrix()
        assert matrix.exceeds_cap is True

    def test_from_toml(self, tmp_path):
        from src.analyzer.sweep_matrix import SweepMatrixConfig
        toml_path = tmp_path / "sweep.toml"
        toml_path.write_text("""
algorithms = ["qm_beats", "aubio_onset"]
stems = ["drums", "bass"]
max_permutations = 100
sample_duration_s = 20

[params.qm_beats]
inputtempo = [100, 120, 140]
""")
        config = SweepMatrixConfig.from_toml(str(toml_path), available_stems={"drums", "bass", "full_mix"})
        assert config.algorithms == ["qm_beats", "aubio_onset"]
        assert config.max_permutations == 100

    def test_algorithm_with_no_params_gets_one_per_stem(self):
        from src.analyzer.sweep_matrix import SweepMatrixConfig
        config = SweepMatrixConfig(
            algorithms=["segmentino"],
            available_stems={"full_mix", "vocals", "drums"},
        )
        matrix = config.build_matrix()
        # segmentino affinity: full_mix, vocals, drums → 3 stems × 1 param set = 3
        assert matrix.total_count == 3
