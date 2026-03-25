"""Sweep matrix: comprehensive algorithm×stem×parameter sweep engine."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional

from src.analyzer.stem_affinity import StemAffinity, AFFINITY_TABLE

__all__ = [
    "SweepMatrixConfig",
    "SweepMatrix",
    "Permutation",
    "PermutationResult",
    "MatrixSweepRunner",
    "auto_select_best",
]


@dataclass
class Permutation:
    """A single algorithm×stem×params combination to execute."""
    algorithm: str
    stem: str
    parameters: dict
    result_type: str  # "timing" or "value_curve"


@dataclass
class SweepMatrix:
    """The computed cross-product of algorithms × stems × parameter permutations."""
    permutations: list[Permutation]
    total_count: int
    exceeds_cap: bool = False
    cap: int = 500


@dataclass
class PermutationResult:
    """Result of executing a single permutation."""
    algorithm: str
    stem: str
    parameters: dict
    result_type: str
    quality_score: float = 0.0
    mark_count: int = 0
    sample_count: int = 0
    avg_interval_ms: int = 0
    dynamic_range: float = 0.0
    status: str = "pending"  # "success", "failed", "skipped"
    error: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "stem": self.stem,
            "parameters": self.parameters,
            "result_type": self.result_type,
            "quality_score": self.quality_score,
            "mark_count": self.mark_count,
            "sample_count": self.sample_count,
            "avg_interval_ms": self.avg_interval_ms,
            "dynamic_range": self.dynamic_range,
            "status": self.status,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SweepMatrixConfig:
    """Configuration for a sweep matrix run."""
    algorithms: list[str] = field(default_factory=lambda: list(AFFINITY_TABLE.keys()))
    available_stems: set[str] = field(default_factory=lambda: {"full_mix"})
    param_overrides: dict[str, dict[str, list]] = field(default_factory=dict)
    max_permutations: int = 500
    sample_duration_s: float = 30.0
    sample_start_ms: Optional[int] = None
    output_dir: Optional[str] = None
    dry_run: bool = False

    def build_matrix(self) -> SweepMatrix:
        """Compute the full permutation cross-product."""
        permutations: list[Permutation] = []
        seen: set[tuple] = set()

        for algo in self.algorithms:
            stems = StemAffinity.get_stems(algo, self.available_stems)
            output_type = StemAffinity.get_output_type(algo)

            # Get parameter ranges
            param_names = StemAffinity.get_tunable_params(algo)
            overrides = self.param_overrides.get(algo, {})

            if not param_names and not overrides:
                # No tunable params — one run per stem
                param_combos = [{}]
            else:
                # Build parameter value lists
                param_values: dict[str, list] = {}
                for pname in param_names:
                    if pname in overrides:
                        param_values[pname] = overrides[pname]
                    # else: auto-derived values will be filled by the runner
                # Add any override-only params not in the affinity table
                for pname, pvals in overrides.items():
                    if pname not in param_values:
                        param_values[pname] = pvals

                if param_values:
                    keys = sorted(param_values.keys())
                    combos = list(itertools.product(*(param_values[k] for k in keys)))
                    param_combos = [dict(zip(keys, vals)) for vals in combos]
                else:
                    param_combos = [{}]

            for stem in stems:
                for params in param_combos:
                    # Deduplicate
                    key = (algo, stem, tuple(sorted(params.items())))
                    if key in seen:
                        continue
                    seen.add(key)
                    permutations.append(Permutation(
                        algorithm=algo,
                        stem=stem,
                        parameters=dict(params),
                        result_type=output_type,
                    ))

        exceeds = len(permutations) > self.max_permutations
        return SweepMatrix(
            permutations=permutations,
            total_count=len(permutations),
            exceeds_cap=exceeds,
            cap=self.max_permutations,
        )

    @classmethod
    def from_toml(
        cls,
        path: str,
        available_stems: set[str] | None = None,
    ) -> "SweepMatrixConfig":
        """Load configuration from a TOML file."""
        import tomllib
        from pathlib import Path

        with open(path, "rb") as f:
            data = tomllib.load(f)

        algorithms = data.get("algorithms", list(AFFINITY_TABLE.keys()))
        stems_list = data.get("stems")
        max_perm = data.get("max_permutations", 500)
        sample_dur = data.get("sample_duration_s", 30.0)

        # If stems specified in TOML, use those + full_mix
        if stems_list and available_stems:
            filtered = {s for s in stems_list if s in available_stems}
            filtered.add("full_mix")
        elif available_stems:
            filtered = available_stems
        else:
            filtered = {"full_mix"}

        # Parse per-algorithm param overrides
        param_overrides: dict[str, dict[str, list]] = {}
        params_section = data.get("params", {})
        for algo_name, algo_params in params_section.items():
            param_overrides[algo_name] = {
                k: list(v) if isinstance(v, (list, tuple)) else [v]
                for k, v in algo_params.items()
            }

        return cls(
            algorithms=algorithms,
            available_stems=filtered,
            param_overrides=param_overrides,
            max_permutations=max_perm,
            sample_duration_s=sample_dur,
        )


def auto_select_best(
    results: list[PermutationResult],
) -> dict[str, PermutationResult]:
    """Select the best result per algorithm (highest score, tie-break: fewer marks)."""
    best: dict[str, PermutationResult] = {}
    for r in results:
        if r.status != "success":
            continue
        current = best.get(r.algorithm)
        if current is None:
            best[r.algorithm] = r
        elif r.quality_score > current.quality_score:
            best[r.algorithm] = r
        elif (r.quality_score == current.quality_score
              and r.mark_count < current.mark_count):
            best[r.algorithm] = r
    return best


def rerun_winners_full_song(
    audio_path: str,
    winners: dict[str, PermutationResult],
    output_dir: str,
) -> dict[str, PermutationResult]:
    """Re-run winning parameter sets on the full song (not sample segment).

    Returns updated PermutationResult objects with full-song scores.
    """
    import json
    import time
    from pathlib import Path

    import librosa
    import numpy as np

    from src.analyzer.scorer import score_track
    from src.analyzer.value_curve_scorer import score_value_curve
    from src.log import get_logger

    log = get_logger("xlight.sweep_matrix")
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    audio_p = Path(audio_path)
    stems_dir = None
    for cand in [audio_p.parent / "stems", audio_p.parent / audio_p.stem / "stems",
                 audio_p.parent / ".stems"]:
        if cand.exists():
            stems_dir = cand
            break
    if stems_dir is None:
        stems_dir = audio_p.parent / "stems"

    out = Path(output_dir) / "winners"
    out.mkdir(parents=True, exist_ok=True)

    from src.analyzer.runner import default_algorithms
    algo_map = {a.name: a for a in default_algorithms()}
    full_results: dict[str, PermutationResult] = {}
    winners_data: list[dict] = []  # full marks for winners.json

    for algo_name, winner in winners.items():
        algo = algo_map.get(algo_name)
        if algo is None:
            log.warning("Algorithm %s not found for full-song re-run", algo_name)
            continue

        # Select stem audio
        if winner.stem == "full_mix":
            audio = y
        else:
            stem_file = stems_dir / f"{winner.stem}.mp3"
            if stem_file.exists():
                audio, _ = librosa.load(str(stem_file), sr=sr, mono=True)
            else:
                audio = y

        # Apply winning parameters
        if winner.parameters:
            algo.parameters = dict(winner.parameters)

        t0 = time.perf_counter()
        track = algo.run(audio, sr)
        elapsed = int((time.perf_counter() - t0) * 1000)

        if track is None:
            log.warning("Full-song re-run of %s returned None", algo_name)
            continue

        result = PermutationResult(
            algorithm=algo_name,
            stem=winner.stem,
            parameters=winner.parameters,
            result_type=winner.result_type,
            duration_ms=elapsed,
            status="success",
        )

        if winner.result_type == "value_curve" and hasattr(track, "value_curve"):
            curve = track.value_curve
            result.quality_score = score_value_curve(curve)
            result.sample_count = len(curve)
            # Export as .xvc
            try:
                from src.analyzer.xvc_export import write_value_curve
                xvc_path = out / f"{algo_name}_{winner.stem}.xvc"
                write_value_curve(curve, str(xvc_path), track_name=f"{algo_name}_{winner.stem}")
                log.info("Exported value curve: %s", xvc_path)
            except Exception as exc:
                log.warning("Failed to export .xvc for %s: %s", algo_name, exc)
        else:
            result.quality_score = score_track(track)
            result.mark_count = track.mark_count
            result.avg_interval_ms = track.avg_interval_ms
            # Export as .xtiming
            try:
                from src.analyzer.xtiming import write_timing_tracks
                xtiming_path = out / f"{algo_name}_{winner.stem}.xtiming"
                write_timing_tracks([track], str(xtiming_path))
                log.info("Exported timing track: %s", xtiming_path)
            except Exception as exc:
                log.warning("Failed to export .xtiming for %s: %s", algo_name, exc)

        full_results[algo_name] = result

        # Collect full-song marks for winners.json
        entry = result.to_dict()
        entry["marks"] = [{"time_ms": m.time_ms} for m in track.marks]
        if hasattr(track, "value_curve"):
            entry["value_curve"] = track.value_curve
        winners_data.append(entry)

    # Write winners.json with full marks for the UI
    winners_json_path = out / "winners.json"
    winners_json_path.write_text(json.dumps({
        "audio_path": str(Path(audio_path).resolve()),
        "results": winners_data,
    }, indent=2), encoding="utf-8")
    log.info("Wrote winners.json with %d full-song results", len(winners_data))

    return full_results


class MatrixSweepRunner:
    """Execute a sweep matrix: run every permutation, collect results, write reports.

    Usage::

        config = SweepMatrixConfig(...)
        matrix = config.build_matrix()
        runner = MatrixSweepRunner(audio_path="song.mp3", matrix=matrix)
        results = runner.run(progress_callback=my_callback)
    """

    def __init__(
        self,
        audio_path: str,
        matrix: SweepMatrix,
        output_dir: str | None = None,
        sample_start_ms: int | None = None,
        sample_end_ms: int | None = None,
    ) -> None:
        self._audio_path = audio_path
        self._matrix = matrix
        self._output_dir = output_dir
        self._sample_start_ms = sample_start_ms
        self._sample_end_ms = sample_end_ms

    def run(
        self,
        progress_callback=None,
    ) -> list[PermutationResult]:
        """Execute all permutations and return results.

        Uses ThreadPoolExecutor for parallel execution. Failed permutations
        are logged and skipped. Ctrl-C saves completed results.
        """
        import json
        import os
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from pathlib import Path

        import librosa
        import numpy as np

        from src.analyzer.scorer import score_track
        from src.analyzer.value_curve_scorer import score_value_curve
        from src.log import get_logger

        log = get_logger("xlight.sweep_matrix")

        # Follow the project convention: song files go under <song_name>/ folder
        audio_p = Path(self._audio_path)
        if self._output_dir:
            output_dir = Path(self._output_dir)
        elif audio_p.parent.name == audio_p.stem:
            # Already in song folder (e.g., highway/highway.mp3)
            output_dir = audio_p.parent / "sweep"
        else:
            # Create song folder (e.g., highway.mp3 → highway/sweep/)
            output_dir = audio_p.parent / audio_p.stem / "sweep"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load audio
        y, sr = librosa.load(self._audio_path, sr=None, mono=True)
        if self._sample_start_ms is not None and self._sample_end_ms is not None:
            s0 = int(self._sample_start_ms / 1000 * sr)
            s1 = int(self._sample_end_ms / 1000 * sr)
            y_segment = y[s0:s1]
            log.info("Segment %dms–%dms (%d samples)", self._sample_start_ms, self._sample_end_ms, len(y_segment))
        else:
            y_segment = y

        # Pre-load stems — check song folder first, then parent
        audio_p = Path(self._audio_path)
        stems_dir = None
        for candidate in [
            audio_p.parent / "stems",                      # song folder convention
            audio_p.parent / audio_p.stem / "stems",       # created from root
            audio_p.parent / ".stems",                     # legacy hidden
        ]:
            if candidate.exists():
                stems_dir = candidate
                break
        if stems_dir is None:
            stems_dir = audio_p.parent / "stems"  # fallback

        stem_cache: dict[str, np.ndarray] = {"full_mix": y_segment}
        for stem_name in {p.stem for p in self._matrix.permutations} - {"full_mix"}:
            stem_file = stems_dir / f"{stem_name}.mp3"
            if stem_file.exists():
                stem_y, _ = librosa.load(str(stem_file), sr=sr, mono=True)
                if self._sample_start_ms is not None and self._sample_end_ms is not None:
                    stem_cache[stem_name] = stem_y[int(self._sample_start_ms / 1000 * sr):int(self._sample_end_ms / 1000 * sr)]
                else:
                    stem_cache[stem_name] = stem_y

        # Pre-load algorithm instances (local only — vamp runs via subprocess)
        from src.analyzer.runner import default_algorithms
        algo_map = {a.name: a for a in default_algorithms()}

        # Determine which algorithms need the vamp subprocess
        from src.analyzer.stem_affinity import AFFINITY_TABLE
        _VAMP_ALGOS = {
            name for name, entry in AFFINITY_TABLE.items()
            if name not in algo_map  # not available in main venv = needs subprocess
        }
        log.info("Vamp subprocess algorithms: %s", sorted(_VAMP_ALGOS))
        log.info("Local algorithms: %d available", len(algo_map))

        # Vamp subprocess setup
        _REPO_ROOT = Path(__file__).resolve().parents[2]
        _VAMP_PYTHON = _REPO_ROOT / ".venv-vamp" / "bin" / "python"
        _VAMP_RUNNER = Path(__file__).with_name("vamp_runner.py")
        vamp_available = _VAMP_PYTHON.exists()

        total = self._matrix.total_count
        results: list[PermutationResult] = []
        algo_results: dict[str, list[dict]] = {}
        lock = threading.Lock()
        completed_count = [0]

        def _run_vamp_subprocess(perm, audio_path_for_stem, params):
            """Run a single vamp algorithm via the .venv-vamp subprocess."""
            import subprocess as _sp
            request = {
                "audio_path": audio_path_for_stem,
                "stem_paths": {},
                "algorithms": [perm.algorithm],
            }
            if params:
                request["parameters"] = {perm.algorithm: params}

            try:
                proc = _sp.run(
                    [str(_VAMP_PYTHON), str(_VAMP_RUNNER)],
                    input=json.dumps(request) + "\n",
                    capture_output=True, text=True, timeout=120,
                )
                for line in proc.stdout.strip().split("\n"):
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("event") == "done":
                        tracks = msg.get("tracks", [])
                        if tracks:
                            return tracks[0]  # first (only) track
                return None
            except Exception as exc:
                log.warning("Vamp subprocess for %s failed: %s", perm.algorithm, exc)
                return None

        def _run_one(perm: Permutation) -> tuple[Permutation, PermutationResult, dict | None]:
            t0 = time.perf_counter()
            result = PermutationResult(
                algorithm=perm.algorithm, stem=perm.stem,
                parameters=perm.parameters, result_type=perm.result_type,
            )
            full_entry = None

            try:
                # Determine audio source
                if perm.algorithm in _VAMP_ALGOS:
                    # Vamp algorithm — run via subprocess with audio file path
                    if not vamp_available:
                        result.status = "skipped"
                        result.error = ".venv-vamp not available"
                        return perm, result, None

                    # Get the audio file path for this stem
                    if perm.stem == "full_mix":
                        audio_file = self._audio_path
                    else:
                        stem_file = stems_dir / f"{perm.stem}.mp3"
                        if not stem_file.exists():
                            result.status = "skipped"
                            result.error = f"Stem {perm.stem} not found"
                            return perm, result, None
                        audio_file = str(stem_file)

                    track_data = _run_vamp_subprocess(perm, audio_file, perm.parameters)
                    if track_data is not None:
                        from src.analyzer.result import TimingMark, TimingTrack
                        marks = [TimingMark(time_ms=m["time_ms"], confidence=None)
                                 for m in track_data.get("marks", [])]
                        track = TimingTrack(
                            name=perm.algorithm,
                            algorithm_name=perm.algorithm,
                            element_type=track_data.get("element_type", "onset"),
                            marks=marks,
                            quality_score=0.0,
                        )
                    else:
                        track = None
                else:
                    # Local algorithm — run in-process
                    audio = stem_cache.get(perm.stem)
                    if audio is None:
                        result.status = "skipped"
                        result.error = f"Stem {perm.stem} not available"
                        return perm, result, None

                    algo = algo_map.get(perm.algorithm)
                    if algo is None:
                        result.status = "skipped"
                        result.error = f"Algorithm {perm.algorithm} not found"
                        return perm, result, None

                    import copy
                    algo_copy = copy.copy(algo)
                    if perm.parameters:
                        algo_copy.parameters = dict(perm.parameters)
                    track = algo_copy.run(audio, sr)

                if track is not None:
                    if perm.result_type == "value_curve" and hasattr(track, "value_curve"):
                        curve = track.value_curve
                        result.quality_score = score_value_curve(curve)
                        result.sample_count = len(curve)
                        result.dynamic_range = (max(curve) - min(curve)) if curve else 0
                    else:
                        result.quality_score = score_track(track)
                        result.mark_count = track.mark_count
                        result.avg_interval_ms = track.avg_interval_ms
                    result.status = "success"

                    full_entry = result.to_dict()
                    full_entry["marks"] = [{"time_ms": m.time_ms} for m in track.marks]
                    if hasattr(track, "value_curve"):
                        full_entry["value_curve"] = track.value_curve
                else:
                    result.status = "failed"
                    result.error = "Algorithm returned None"

            except Exception as exc:
                result.status = "failed"
                result.error = str(exc)[:200]
                log.warning("Permutation %s/%s failed: %s", perm.algorithm, perm.stem, exc)

            result.duration_ms = int((time.perf_counter() - t0) * 1000)
            return perm, result, full_entry

        # Parallel execution
        max_workers = min(os.cpu_count() or 2, 4)
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(_run_one, perm): perm
                    for perm in self._matrix.permutations
                }
                for future in as_completed(futures):
                    perm, result, full_entry = future.result()
                    with lock:
                        results.append(result)
                        if full_entry:
                            algo_results.setdefault(perm.algorithm, []).append(full_entry)
                        completed_count[0] += 1
                    if progress_callback:
                        progress_callback(completed_count[0], total, perm, result)

        except KeyboardInterrupt:
            log.warning("Sweep interrupted — saving %d completed results", len(results))

        # Write unified report (metadata only)
        report = {
            "audio_path": str(Path(self._audio_path).resolve()),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "segment_start_ms": self._sample_start_ms,
            "segment_end_ms": self._sample_end_ms,
            "total_permutations": total,
            "completed": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "results": [r.to_dict() for r in results],
            "best_per_algorithm": {
                algo: r.to_dict()
                for algo, r in auto_select_best(results).items()
            },
        }
        report_path = output_dir / "sweep_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log.info("Wrote unified report: %s (%d results)", report_path, len(results))

        for algo_name, algo_entries in algo_results.items():
            algo_path = output_dir / f"sweep_{algo_name}.json"
            algo_path.write_text(json.dumps({
                "algorithm": algo_name,
                "results": algo_entries,
            }, indent=2), encoding="utf-8")

        return results
