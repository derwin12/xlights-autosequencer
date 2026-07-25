"""T016: AnalysisRunner — orchestrates all algorithm runs for a single audio file."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np

from src.analyzer.audio import AudioFile, load
from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import AnalysisAlgorithm, AnalysisResult, TimingTrack
from src.analyzer.scorer import score_track
from src.analyzer.stems import StemSet

# Libraries whose compiled extensions require numpy<2 and, in the
# devcontainer dev-mode layout, only exist in a separate .venv-vamp
# virtualenv (to avoid ABI conflicts with the main venv's numpy>=2,
# required by whisperx/pyannote). The packaged desktop app bundles
# everything into one executable with numpy<2 pinned throughout, so these
# import directly there -- checked per-run via _importable_inprocess()
# rather than assumed, so algorithms only fall back to the .venv-vamp
# subprocess when the library genuinely isn't importable here.
_SUBPROCESS_LIBS: frozenset[str] = frozenset({"vamp", "madmom"})

# Path to the repo root (src/analyzer/runner.py → ../../)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VAMP_PYTHON = Path(os.environ["XLIGHT_VENV_VAMP"]) if os.environ.get("XLIGHT_VENV_VAMP") else _REPO_ROOT / ".venv-vamp" / "bin" / "python"
_VAMP_RUNNER = Path(__file__).with_name("vamp_runner.py")


def _importable_inprocess(library: str) -> bool:
    """Return True if *library* ("vamp" or "madmom") can be imported directly
    in this process, without needing the .venv-vamp subprocess sidecar.

    bug found 2026-07-25 (packaged app): madmom_beats/madmom_downbeats were
    unconditionally routed to the .venv-vamp subprocess, which doesn't exist
    in the packaged app (everything bundles into one executable) -- so every
    madmom algorithm silently produced zero marks regardless of
    capabilities.py correctly reporting madmom as available, cascading into
    "no beats/bars produced" and the story builder collapsing to one flat
    section. Same fix pattern as stems.py's _run_demucs: try in-process
    first, only fall back to the sidecar subprocess when the import
    genuinely fails (the dev-mode main-venv case).
    """
    try:
        if library == "madmom":
            from src.analyzer.capabilities import patch_madmom_compat
            patch_madmom_compat()
            import madmom  # noqa: F401
        elif library == "vamp":
            import vamp  # noqa: F401
        else:
            return False
    except ImportError:
        return False
    return True


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

        # Split algorithms into in-process (librosa, plus vamp/madmom when
        # importable directly here) and subprocess (vamp/madmom that truly
        # need the .venv-vamp sidecar).
        _inprocess_libs = {lib for lib in _SUBPROCESS_LIBS if _importable_inprocess(lib)}
        local_algos = [
            a for a in self._algorithms
            if a.library not in _SUBPROCESS_LIBS or a.library in _inprocess_libs
        ]
        sub_algos = [
            a for a in self._algorithms
            if a.library in _SUBPROCESS_LIBS and a.library not in _inprocess_libs
        ]

        # ── In-process algorithms (librosa) — run in parallel ────────────────
        # Cache resampled stems to avoid redundant librosa.resample calls
        _resample_cache: dict[str, np.ndarray] = {}

        def _run_one(algo: Algorithm) -> tuple[Algorithm, TimingTrack | None]:
            algo_audio, algo_sr = _select_audio(algo, audio, sr, stems, _resample_cache)
            return algo, algo.run(algo_audio, algo_sr)

        with ThreadPoolExecutor(max_workers=min(4, len(local_algos) or 1)) as pool:
            futures = {pool.submit(_run_one, a): i for i, a in enumerate(local_algos)}
            results_by_idx: dict[int, tuple[Algorithm, TimingTrack | None]] = {}
            for future in as_completed(futures):
                idx = futures[future]
                results_by_idx[idx] = future.result()

        for idx in sorted(results_by_idx):
            algo, track = results_by_idx[idx]
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
                    "INFO: .venv-vamp not found — vamp/madmom algorithms skipped.\n"
                    "  To enable: run ./scripts/install.sh or set XLIGHT_VENV_VAMP "
                    "to the path of a Python with vamp/madmom installed.",
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
    # Build stem_paths dict for algorithms that prefer a specific stem.
    # Match StemCache convention: {parent}/{stem}/stems/ (primary),
    # falling back to {parent}/stems/ and {parent}/.stems/ for legacy layouts.
    stem_paths: dict[str, str] = {}
    if stems is not None:
        audio_p = Path(audio_path)
        if audio_p.parent.name == audio_p.stem:
            # MP3 is already inside its own folder (e.g. songs/MySong/MySong.mp3)
            stems_dir = audio_p.parent / "stems"
        else:
            stems_dir = audio_p.parent / audio_p.stem / "stems"
        if not stems_dir.exists():
            stems_dir = audio_p.parent / "stems"
        if not stems_dir.exists():
            stems_dir = audio_p.parent / ".stems"
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

    dropped_lines: list[str] = []

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            dropped_lines.append(line[:200])
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

        else:
            dropped_lines.append(line[:200])

    proc.wait()
    stderr_out = proc.stderr.read()
    if stderr_out:
        print(f"[vamp subprocess stderr]\n{stderr_out}", file=sys.stderr)

    if dropped_lines:
        print(
            f"WARNING: {len(dropped_lines)} non-protocol line(s) from vamp subprocess "
            f"(first: {dropped_lines[0]!r})",
            file=sys.stderr,
        )
    if proc.returncode and proc.returncode != 0 and not tracks:
        print(
            f"WARNING: vamp subprocess exited with code {proc.returncode} "
            f"and produced no tracks",
            file=sys.stderr,
        )

    return tracks, algo_meta


def _select_audio(
    algo: Algorithm,
    full_mix: np.ndarray,
    full_mix_sr: int,
    stems: StemSet | None,
    resample_cache: dict[str, np.ndarray] | None = None,
) -> tuple[np.ndarray, int]:
    """
    Return the (audio, sample_rate) pair the algorithm should use.

    When stems is None or the algorithm prefers "full_mix", returns the full-mix
    array. Otherwise returns the matching stem array, resampled to full_mix_sr
    when the stem sample rate differs. Resampled arrays are cached in
    *resample_cache* to avoid redundant computation across algorithms.
    """
    if stems is None or algo.preferred_stem == "full_mix":
        return full_mix, full_mix_sr

    stem_arr = stems.get(algo.preferred_stem)
    if stem_arr is None:
        return full_mix, full_mix_sr

    stem_sr = stems.sample_rate
    if stem_sr != full_mix_sr:
        cache_key = algo.preferred_stem
        if resample_cache is not None and cache_key in resample_cache:
            stem_arr = resample_cache[cache_key]
        else:
            import librosa as _librosa
            stem_arr = _librosa.resample(stem_arr, orig_sr=stem_sr, target_sr=full_mix_sr)
            if resample_cache is not None:
                resample_cache[cache_key] = stem_arr
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
    from src.analyzer.algorithms.registry import get_algorithms
    return get_algorithms(include_vamp=include_vamp, include_madmom=include_madmom)
