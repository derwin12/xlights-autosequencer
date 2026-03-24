"""Parallel pipeline executor: PipelineStep, DependencyGraph, ParallelRunner."""
from __future__ import annotations

import enum
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import numpy as np

if TYPE_CHECKING:
    from src.analyzer.algorithms.base import Algorithm
    from src.analyzer.result import AnalysisResult
    from src.analyzer.stems import StemSet

__all__ = [
    "PipelineStepStatus",
    "PipelineStep",
    "DependencyGraph",
    "ParallelRunner",
    "build_pipeline_steps",
]


# ---------------------------------------------------------------------------
# PipelineStep
# ---------------------------------------------------------------------------

class PipelineStepStatus(enum.Enum):
    PENDING = "pending"
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PipelineStep:
    """A single unit of work in the analysis pipeline with explicit dependencies."""

    name: str
    phase: str
    depends_on: list[str] = field(default_factory=list)
    status: PipelineStepStatus = field(default=PipelineStepStatus.PENDING)
    started_at: float | None = None
    completed_at: float | None = None
    mark_count: int = 0
    error: str = ""

    def is_ready(self, completed: set[str]) -> bool:
        """Return True when all declared dependencies have completed."""
        return all(dep in completed for dep in self.depends_on)


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------

class DependencyGraph:
    """Directed acyclic graph of PipelineSteps for computing execution layers."""

    def __init__(self, steps: list[PipelineStep]) -> None:
        self._steps = steps
        self._by_name: dict[str, PipelineStep] = {s.name: s for s in steps}

    def topological_sort(self) -> list[list[PipelineStep]]:
        """Return layers of steps that can run concurrently.

        Each layer contains all steps whose dependencies are satisfied by
        all prior layers.  Raises ValueError if a dependency cycle is detected.
        """
        remaining = list(self._steps)
        completed: set[str] = set()
        layers: list[list[PipelineStep]] = []

        while remaining:
            ready = [s for s in remaining if s.is_ready(completed)]
            if not ready:
                names = [s.name for s in remaining]
                raise ValueError(
                    f"Dependency cycle detected among steps: {names}"
                )
            layers.append(ready)
            for s in ready:
                completed.add(s.name)
                remaining.remove(s)

        return layers

    def propagate_failure(self, failed_step: PipelineStep) -> None:
        """Mark all transitively-dependent steps as SKIPPED."""
        failed_names: set[str] = {failed_step.name}
        changed = True
        while changed:
            changed = False
            for step in self._steps:
                if step.status == PipelineStepStatus.SKIPPED:
                    continue
                if any(dep in failed_names for dep in step.depends_on):
                    step.status = PipelineStepStatus.SKIPPED
                    step.error = (
                        f"dependency failed: "
                        + ", ".join(d for d in step.depends_on if d in failed_names)
                    )
                    failed_names.add(step.name)
                    changed = True


# ---------------------------------------------------------------------------
# build_pipeline_steps — T029
# ---------------------------------------------------------------------------

def build_pipeline_steps(
    algorithms: list["Algorithm"],
    use_stems: bool = True,
    use_phonemes: bool = False,
) -> list[PipelineStep]:
    """Build a list of PipelineSteps for a given algorithm set.

    Infrastructure steps (audio_load, stem_separation) are always included.
    Each algorithm step declares ``depends_on`` based on ``algo.depends_on``
    (if declared) or inferred from ``algo.preferred_stem``.
    """
    steps: list[PipelineStep] = []

    # Fixed infrastructure steps
    steps.append(PipelineStep(name="audio_load", phase="setup", depends_on=[]))
    if use_stems:
        steps.append(PipelineStep(
            name="stem_separation", phase="setup", depends_on=["audio_load"]
        ))
    if use_phonemes:
        steps.append(PipelineStep(
            name="phoneme_analysis", phase="analysis", depends_on=["audio_load"]
        ))

    for algo in algorithms:
        # Prefer explicit declaration; fall back to preferred_stem inference
        declared = getattr(algo, "depends_on", None)
        if declared:
            deps = list(declared)
        elif algo.preferred_stem == "full_mix":
            deps = ["audio_load"]
        else:
            deps = ["stem_separation"] if use_stems else ["audio_load"]

        steps.append(PipelineStep(name=algo.name, phase="analysis", depends_on=deps))

    return steps


# ---------------------------------------------------------------------------
# ParallelRunner — T030
# ---------------------------------------------------------------------------

class ParallelRunner:
    """Run algorithm steps in parallel using DependencyGraph layer ordering.

    Local (librosa) algorithms are run concurrently via ThreadPoolExecutor.
    Vamp/madmom algorithms are dispatched to the subprocess batch (which is
    itself parallel across stems).

    Usage::

        runner = ParallelRunner(algorithms=default_algorithms())
        result = runner.run(
            audio_path="song.mp3",
            audio=audio_array,   # pre-loaded, or pass None to load internally
            sample_rate=sr,
            stems=stems_set,
            progress_callback=my_callback,
        )
    """

    _SUBPROCESS_LIBS: frozenset[str] = frozenset({"vamp", "madmom"})

    def __init__(self, algorithms: list["Algorithm"]) -> None:
        self._algorithms = algorithms

    def run(
        self,
        audio_path: str,
        audio: np.ndarray | None = None,
        sample_rate: int | None = None,
        stems: "StemSet | None" = None,
        progress_callback: Callable | None = None,
        use_stems: bool = False,
        use_phonemes: bool = False,
    ) -> "AnalysisResult":
        """Run all algorithms in parallel and return an AnalysisResult.

        If *audio* is None, the audio file is loaded from *audio_path*.
        """
        from src.analyzer.audio import load
        from src.analyzer.result import AnalysisAlgorithm, AnalysisResult, TimingTrack
        from src.analyzer.scorer import score_track

        wall_start = time.perf_counter()

        # Load audio if not supplied
        if audio is None or sample_rate is None:
            audio_arr, sr, meta = load(audio_path)
            filename = meta.filename
            duration_ms = meta.duration_ms
            source_file = meta.path
        else:
            audio_arr = audio
            sr = sample_rate
            from pathlib import Path
            import librosa
            try:
                duration_ms = int(len(audio_arr) / sr * 1000)
            except Exception:
                duration_ms = 0
            p = Path(audio_path).resolve()
            filename = p.name
            source_file = str(p)

        # Estimate tempo (only when loading from disk; skip for pre-supplied audio)
        estimated_bpm = 0.0
        if audio is None:
            try:
                import librosa as _librosa
                import numpy as _np
                tempo_arr, _ = _librosa.beat.beat_track(y=audio_arr, sr=sr, hop_length=512)
                estimated_bpm = float(_np.atleast_1d(tempo_arr)[0])
            except Exception:
                estimated_bpm = 0.0

        # Split algorithms
        local_algos = [a for a in self._algorithms if a.library not in self._SUBPROCESS_LIBS]
        sub_algos = [a for a in self._algorithms if a.library in self._SUBPROCESS_LIBS]

        tracks: list[TimingTrack] = []
        used_algorithms: list[AnalysisAlgorithm] = []
        step_timings: dict[str, float] = {}
        cpu_ms_total: float = 0.0

        # ── Run local algorithms in parallel ─────────────────────────────────
        def _run_one(algo: "Algorithm") -> tuple["Algorithm", "TimingTrack | None", float]:
            t0 = time.perf_counter()
            from src.analyzer.runner import _select_audio
            try:
                algo_audio, algo_sr = _select_audio(algo, audio_arr, sr, stems)
            except Exception:
                algo_audio, algo_sr = audio_arr, sr
            track = algo.run(algo_audio, algo_sr)
            elapsed = time.perf_counter() - t0
            return algo, track, elapsed

        if local_algos:
            max_workers = min(len(local_algos), 8)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_run_one, a): a for a in local_algos}
                for future in as_completed(futures):
                    algo, track, elapsed_s = future.result()
                    cpu_ms_total += elapsed_s * 1000
                    step_timings[algo.name] = round(elapsed_s * 1000, 1)
                    if track is not None:
                        track.quality_score = score_track(track)
                        track.stem_source = algo.preferred_stem if stems is not None else "full_mix"
                        tracks.append(track)
                        used_algorithms.append(algo.metadata())
                    if progress_callback:
                        progress_callback(
                            algo.name, "done",
                            {"mark_count": track.mark_count if track else 0,
                             "duration_ms": int(elapsed_s * 1000), "error": ""},
                        )

        # ── Run subprocess (vamp/madmom) algorithms ───────────────────────────
        if sub_algos:
            from src.analyzer.runner import _run_subprocess_batch, _vamp_venv_available
            import sys as _sys
            if _vamp_venv_available():
                sub_offset = len(local_algos)
                total = len(self._algorithms)

                def _compat_cb(idx, tot, name, mark_count):
                    if progress_callback:
                        progress_callback(name, "done", {"mark_count": mark_count, "duration_ms": 0, "error": ""})

                sub_tracks, sub_algos_meta = _run_subprocess_batch(
                    audio_path=audio_path,
                    stems=stems,
                    algorithms=sub_algos,
                    offset=sub_offset,
                    total=total,
                    progress_callback=_compat_cb,
                )
                tracks.extend(sub_tracks)
                used_algorithms.extend(sub_algos_meta)
            else:
                print(
                    "INFO: .venv-vamp not found — vamp/madmom algorithms skipped.",
                    file=__import__("sys").stderr,
                )

        wall_elapsed = time.perf_counter() - wall_start
        wall_ms = wall_elapsed * 1000
        parallelism_ratio = (cpu_ms_total / wall_ms) if wall_ms > 0 else 1.0

        result = AnalysisResult(
            schema_version="1.0",
            source_file=source_file,
            filename=filename,
            duration_ms=duration_ms,
            sample_rate=sr,
            estimated_tempo_bpm=round(estimated_bpm, 2),
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            algorithms=used_algorithms,
            timing_tracks=tracks,
            stem_separation=stems is not None,
            pipeline_stats={
                "total_wall_clock_ms": round(wall_ms, 1),
                "total_cpu_ms": round(cpu_ms_total, 1),
                "parallelism_ratio": round(parallelism_ratio, 2),
                "step_timings": step_timings,
            },
        )
        return result

