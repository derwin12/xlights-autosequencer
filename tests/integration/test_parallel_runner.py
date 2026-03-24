"""T027: Integration test for ParallelRunner — parallel execution speedup.

Tests that the ParallelRunner executes independent algorithms concurrently,
giving a measurable speedup over sequential execution.
"""
from __future__ import annotations

import time
from typing import ClassVar

import numpy as np
import pytest

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack


# ──────────────────────────────────────────────────────────────────────────────
# Controlled mock algorithms for deterministic timing
# ──────────────────────────────────────────────────────────────────────────────

SLEEP_DURATION = 0.25  # Each mock algorithm sleeps for 250ms


def _make_slow_algo(algo_name: str, stem: str = "full_mix", sleep: float = SLEEP_DURATION):
    """Dynamically construct a slow mock algorithm class."""

    class SlowAlgo(Algorithm):
        name: ClassVar[str] = algo_name
        element_type: ClassVar[str] = "beat"
        library: ClassVar[str] = "mock"
        preferred_stem: ClassVar[str] = stem
        depends_on: ClassVar[list[str]] = ["audio_load"]

        def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
            time.sleep(sleep)
            return TimingTrack(
                name=self.name,
                algorithm_name=self.name,
                element_type="beat",
                marks=[TimingMark(500, None)],
                quality_score=0.5,
            )

    SlowAlgo.__name__ = f"SlowAlgo_{algo_name}"
    return SlowAlgo()


class TestParallelRunnerSpeedup:
    """ParallelRunner runs independent algorithms concurrently (SC-002)."""

    N_PARALLEL_ALGOS = 4  # 4 independent algorithms × 250ms = 1000ms sequential

    def _make_algorithms(self) -> list:
        return [_make_slow_algo(f"mock_{i}") for i in range(self.N_PARALLEL_ALGOS)]

    def test_parallel_faster_than_sequential(self, tmp_path):
        """Parallel run should be ≤ 70% of sequential run time (SC-002)."""
        from src.analyzer.parallel import ParallelRunner, build_pipeline_steps

        fake_audio = tmp_path / "song.wav"
        fake_audio.write_bytes(b"FAKEAUDIO")
        algos = self._make_algorithms()

        # ── Sequential baseline ───────────────────────────────────────────────
        t0 = time.perf_counter()
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        for algo in algos:
            algo.run(audio, sr)
        elapsed_sequential = time.perf_counter() - t0

        # ── Parallel run ──────────────────────────────────────────────────────
        runner = ParallelRunner(algorithms=algos)
        t0 = time.perf_counter()
        result = runner.run(
            audio_path=str(fake_audio),
            audio=audio,
            sample_rate=sr,
            stems=None,
        )
        elapsed_parallel = time.perf_counter() - t0

        assert elapsed_parallel <= 0.70 * elapsed_sequential, (
            f"Parallel ({elapsed_parallel:.2f}s) should be ≤70% of "
            f"sequential ({elapsed_sequential:.2f}s)"
        )

    def test_result_contains_all_tracks(self, tmp_path):
        """All algorithm tracks are present in the parallel result."""
        from src.analyzer.parallel import ParallelRunner

        fake_audio = tmp_path / "song.wav"
        fake_audio.write_bytes(b"FAKEAUDIO")
        algos = self._make_algorithms()

        audio = np.zeros(22050, dtype=np.float32)
        runner = ParallelRunner(algorithms=algos)
        result = runner.run(
            audio_path=str(fake_audio),
            audio=audio,
            sample_rate=22050,
            stems=None,
        )

        algo_names = {a.name for a in algos}
        result_names = {t.name for t in result.timing_tracks}
        assert algo_names == result_names

    def test_pipeline_stats_present(self, tmp_path):
        """ParallelRunner attaches pipeline_stats to the result."""
        from src.analyzer.parallel import ParallelRunner

        fake_audio = tmp_path / "song.wav"
        fake_audio.write_bytes(b"FAKEAUDIO")
        algos = self._make_algorithms()

        audio = np.zeros(22050, dtype=np.float32)
        runner = ParallelRunner(algorithms=algos)
        result = runner.run(
            audio_path=str(fake_audio),
            audio=audio,
            sample_rate=22050,
            stems=None,
        )

        assert result.pipeline_stats is not None
        assert result.pipeline_stats.get("parallelism_ratio", 0) > 1.0
