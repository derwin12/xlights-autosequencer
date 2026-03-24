"""T016: AnalysisRunner — orchestrates all algorithm runs for a single audio file."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np

from src.analyzer.audio import AudioFile, load
from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import AnalysisAlgorithm, AnalysisResult, TimingTrack
from src.analyzer.scorer import score_track
from src.analyzer.stems import StemSet

# Libraries whose compiled extensions require numpy<2 and must run in a
# subprocess using the .venv-vamp virtual environment.
_SUBPROCESS_LIBS: frozenset[str] = frozenset({"vamp", "madmom"})

# Path to the repo root (src/analyzer/runner.py → ../../)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VAMP_PYTHON = _REPO_ROOT / ".venv-vamp" / "bin" / "python"
_VAMP_RUNNER = Path(__file__).with_name("vamp_runner.py")


def _vamp_venv_available() -> bool:
    return _VAMP_PYTHON.exists()


class AnalysisRunner:
    """
    Runs a list of Algorithm instances against a single audio file.

    Algorithms whose `library` is "vamp" or "madmom" are dispatched to a
    subprocess running in .venv-vamp (numpy<2) to avoid ABI conflicts with
    the main environment (numpy>=2, required by whisperx/pyannote).

    Usage:
        runner = AnalysisRunner(algorithms=default_algorithms())
        result = runner.run("path/to/song.mp3")
    """

    def __init__(self, algorithms: list[Algorithm]) -> None:
        self._algorithms = algorithms

    def run(
        self,
        audio_path: str,
        progress_callback=None,
        stems: StemSet | None = None,
    ) -> AnalysisResult:
        """
        Load audio once, run all algorithms, score tracks, assemble result.

        progress_callback: optional callable(index, total, name, mark_count)
        stems: optional StemSet from stem separation; when provided, algorithms
               are routed to their preferred_stem array. Falls back to full-mix
               when preferred_stem is "full_mix" or the stem is absent.
        """
        audio, sr, meta = load(audio_path)

        # Estimate overall tempo for metadata
        try:
            tempo_arr, _ = librosa.beat.beat_track(y=audio, sr=sr, hop_length=512)
            estimated_bpm = float(np.atleast_1d(tempo_arr)[0])
        except Exception:
            estimated_bpm = 0.0

        tracks: list[TimingTrack] = []
        used_algorithms: list[AnalysisAlgorithm] = []
        total = len(self._algorithms)

        # Split algorithms into in-process (librosa) and subprocess (vamp/madmom)
        local_algos = [a for a in self._algorithms if a.library not in _SUBPROCESS_LIBS]
        sub_algos   = [a for a in self._algorithms if a.library in _SUBPROCESS_LIBS]

        # ── In-process algorithms (librosa) ──────────────────────────────────
        for idx, algo in enumerate(local_algos):
            algo_audio, algo_sr = _select_audio(algo, audio, sr, stems)
            track = algo.run(algo_audio, algo_sr)
            if track is not None:
                track.quality_score = score_track(track)
                track.stem_source = algo.preferred_stem if stems is not None else "full_mix"
                tracks.append(track)
                used_algorithms.append(algo.metadata())
            if progress_callback:
                progress_callback(idx + 1, total, algo.name,
                                  track.mark_count if track else 0)

        # ── Subprocess algorithms (vamp / madmom) ─────────────────────────────
        if sub_algos:
            sub_offset = len(local_algos)
            if _vamp_venv_available():
                sub_tracks, sub_algos_meta = _run_subprocess_batch(
                    audio_path=audio_path,
                    stems=stems,
                    algorithms=sub_algos,
                    offset=sub_offset,
                    total=total,
                    progress_callback=progress_callback,
                )
                tracks.extend(sub_tracks)
                used_algorithms.extend(sub_algos_meta)
            else:
                print(
                    "INFO: .venv-vamp not found — vamp/madmom algorithms skipped. "
                    "See README for setup instructions.",
                    file=sys.stderr,
                )
                for i, algo in enumerate(sub_algos):
                    if progress_callback:
                        progress_callback(sub_offset + i + 1, total, algo.name, 0)

        stem_cache_str: str | None = None
        if stems is not None:
            for _sd_name in ("stems", ".stems"):
                stems_dir = Path(meta.path).parent / _sd_name
                if stems_dir.exists():
                    stem_cache_str = str(stems_dir)
                    break

        return AnalysisResult(
            schema_version="1.0",
            source_file=meta.path,
            filename=meta.filename,
            duration_ms=meta.duration_ms,
            sample_rate=meta.sample_rate,
            estimated_tempo_bpm=round(estimated_bpm, 2),
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            algorithms=used_algorithms,
            timing_tracks=tracks,
            stem_separation=stems is not None,
            stem_cache=stem_cache_str,
        )


def _run_subprocess_batch(
    audio_path: str,
    stems: StemSet | None,
    algorithms: list[Algorithm],
    offset: int,
    total: int,
    progress_callback,
) -> tuple[list[TimingTrack], list[AnalysisAlgorithm]]:
    """
    Invoke vamp_runner.py in .venv-vamp, stream NDJSON progress, return tracks.
    """
    # Build stem_paths dict for algorithms that prefer a specific stem
    stem_paths: dict[str, str] = {}
    if stems is not None:
        stems_dir = Path(audio_path).parent / "stems"
        if not stems_dir.exists():
            stems_dir = Path(audio_path).parent / ".stems"
        for stem_name in ("drums", "bass", "vocals", "guitar", "piano", "other"):
            p = stems_dir / f"{stem_name}.mp3"
            if p.exists():
                stem_paths[stem_name] = str(p)

    request = {
        "audio_path": audio_path,
        "stem_paths": stem_paths,
        "algorithms": [a.name for a in algorithms],
    }

    try:
        proc = subprocess.Popen(
            [str(_VAMP_PYTHON), str(_VAMP_RUNNER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.close()
    except Exception as exc:
        print(f"WARNING: Failed to start vamp subprocess: {exc}", file=sys.stderr)
        return [], []

    tracks: list[TimingTrack] = []
    algo_meta: list[AnalysisAlgorithm] = []
    proc_idx = 0

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        event = msg.get("event")

        if event == "progress":
            proc_idx += 1
            if progress_callback:
                progress_callback(
                    offset + proc_idx,
                    total,
                    msg.get("name", ""),
                    msg.get("mark_count", 0),
                )

        elif event == "warn":
            print(f"WARNING: {msg.get('name', '')}: {msg.get('message', '')}", file=sys.stderr)

        elif event == "done":
            for t_dict in msg.get("tracks", []):
                tracks.append(TimingTrack.from_dict(t_dict))
            for a_dict in msg.get("algorithms", []):
                algo_meta.append(AnalysisAlgorithm.from_dict(a_dict))

        elif event == "error":
            print(f"WARNING: vamp subprocess error: {msg.get('message', '')}", file=sys.stderr)

    proc.wait()
    if proc.returncode != 0:
        stderr_out = proc.stderr.read()
        if stderr_out:
            print(f"WARNING: vamp subprocess stderr: {stderr_out[:500]}", file=sys.stderr)

    return tracks, algo_meta


def _select_audio(
    algo: Algorithm,
    full_mix: np.ndarray,
    full_mix_sr: int,
    stems: StemSet | None,
) -> tuple[np.ndarray, int]:
    """
    Return the (audio, sample_rate) pair the algorithm should use.

    When stems is None or the algorithm prefers "full_mix", returns the full-mix
    array. Otherwise returns the matching stem array, resampled to full_mix_sr
    when the stem sample rate differs.
    """
    if stems is None or algo.preferred_stem == "full_mix":
        return full_mix, full_mix_sr

    stem_arr = stems.get(algo.preferred_stem)
    if stem_arr is None:
        return full_mix, full_mix_sr

    stem_sr = stems.sample_rate
    if stem_sr != full_mix_sr:
        import librosa as _librosa
        stem_arr = _librosa.resample(stem_arr, orig_sr=stem_sr, target_sr=full_mix_sr)
        stem_sr = full_mix_sr

    return stem_arr, stem_sr


def default_algorithms(
    include_vamp: bool = True,
    include_madmom: bool = True,
) -> list[Algorithm]:
    """
    Return the full list of algorithm instances.
    Algorithms that require unavailable libraries are silently omitted.
    """
    algorithms: list[Algorithm] = []

    # --- librosa algorithms (always available) ---
    from src.analyzer.algorithms.librosa_beats import LibrosaBeatAlgorithm, LibrosaBarAlgorithm
    from src.analyzer.algorithms.librosa_bands import (
        LibrosaBassAlgorithm,
        LibrosaMidAlgorithm,
        LibrosaTrebleAlgorithm,
    )
    from src.analyzer.algorithms.librosa_hpss import LibrosaDrumsAlgorithm, LibrosaHarmonicAlgorithm
    from src.analyzer.algorithms.librosa_onset import LibrosaOnsetAlgorithm

    algorithms += [
        LibrosaBeatAlgorithm(),
        LibrosaBarAlgorithm(),
        LibrosaOnsetAlgorithm(),
        LibrosaBassAlgorithm(),
        LibrosaMidAlgorithm(),
        LibrosaTrebleAlgorithm(),
        LibrosaDrumsAlgorithm(),
        LibrosaHarmonicAlgorithm(),
    ]

    # --- madmom algorithms (optional) ---
    if include_madmom:
        try:
            from src.analyzer.algorithms.madmom_beat import (
                MadmomBeatAlgorithm,
                MadmomDownbeatAlgorithm,
            )
            algorithms += [MadmomBeatAlgorithm(), MadmomDownbeatAlgorithm()]
        except ImportError:
            print(
                "INFO: madmom not available — madmom_beats and madmom_downbeats skipped.",
                file=sys.stderr,
            )

    # --- Vamp algorithms (optional) ---
    if include_vamp:
        try:
            from src.analyzer.algorithms.vamp_beats import QMBeatAlgorithm, QMBarAlgorithm, BeatRootAlgorithm
            from src.analyzer.algorithms.vamp_onsets import (
                QMOnsetComplexAlgorithm,
                QMOnsetHFCAlgorithm,
                QMOnsetPhaseAlgorithm,
            )
            from src.analyzer.algorithms.vamp_structure import QMSegmenterAlgorithm, QMTempoAlgorithm
            from src.analyzer.algorithms.vamp_pitch import PYINNotesAlgorithm, PYINPitchChangesAlgorithm
            from src.analyzer.algorithms.vamp_harmony import ChordinoAlgorithm, NNLSChromaAlgorithm

            algorithms += [
                QMBeatAlgorithm(),
                QMBarAlgorithm(),
                BeatRootAlgorithm(),
                QMOnsetComplexAlgorithm(),
                QMOnsetHFCAlgorithm(),
                QMOnsetPhaseAlgorithm(),
                QMSegmenterAlgorithm(),
                QMTempoAlgorithm(),
                PYINNotesAlgorithm(),
                PYINPitchChangesAlgorithm(),
                ChordinoAlgorithm(),
                NNLSChromaAlgorithm(),
            ]
        except ImportError:
            print(
                "INFO: vamp Python package not available — Vamp plugin algorithms skipped.",
                file=sys.stderr,
            )

    return algorithms
