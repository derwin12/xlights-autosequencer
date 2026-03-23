"""
Subprocess entry point for Vamp and madmom algorithms.

Runs inside a separate virtual environment (.venv-vamp) that has numpy<2,
vamp, and madmom installed — isolating those compiled extensions from the
main environment which requires numpy>=2 for whisperx/pyannote.

Protocol
--------
stdin  : one JSON line
  {
    "audio_path": "/abs/path/to/song.mp3",
    "stem_paths": {"drums": "/path/drums.mp3", ...},   # optional
    "algorithms": ["qm_beats", "madmom_beats", ...]
  }

stdout : newline-delimited JSON, one object per line
  {"event": "progress", "idx": 1, "total": 14, "name": "qm_beats", "mark_count": 210}
  {"event": "warn",     "name": "qm_beats",   "message": "..."}
  {"event": "done",     "tracks": [...],       "algorithms": [...]}
  {"event": "error",    "message": "fatal error string"}
"""
from __future__ import annotations

import json
import os
import sys

# ── Add the repo root to sys.path so src.* imports work ──────────────────────
# This file lives at src/analyzer/vamp_runner.py → repo root is 2 levels up.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def _build_algo_map() -> dict:
    """Return {name: AlgorithmClass} for every available vamp/madmom algorithm."""
    algo_map: dict = {}

    try:
        from src.analyzer.algorithms.vamp_beats import (
            QMBeatAlgorithm, QMBarAlgorithm, BeatRootAlgorithm,
        )
        algo_map.update({
            "qm_beats": QMBeatAlgorithm,
            "qm_bars": QMBarAlgorithm,
            "beatroot": BeatRootAlgorithm,
        })
    except Exception as exc:
        print(f"WARNING: vamp_beats unavailable: {exc}", file=sys.stderr)

    try:
        from src.analyzer.algorithms.vamp_onsets import (
            QMOnsetComplexAlgorithm, QMOnsetHFCAlgorithm, QMOnsetPhaseAlgorithm,
        )
        algo_map.update({
            "qm_onsets_complex": QMOnsetComplexAlgorithm,
            "qm_onsets_hfc": QMOnsetHFCAlgorithm,
            "qm_onsets_phase": QMOnsetPhaseAlgorithm,
        })
    except Exception as exc:
        print(f"WARNING: vamp_onsets unavailable: {exc}", file=sys.stderr)

    try:
        from src.analyzer.algorithms.vamp_structure import (
            QMSegmenterAlgorithm, QMTempoAlgorithm,
        )
        algo_map.update({
            "qm_segments": QMSegmenterAlgorithm,
            "qm_tempo": QMTempoAlgorithm,
        })
    except Exception as exc:
        print(f"WARNING: vamp_structure unavailable: {exc}", file=sys.stderr)

    try:
        from src.analyzer.algorithms.vamp_pitch import (
            PYINNotesAlgorithm, PYINPitchChangesAlgorithm,
        )
        algo_map.update({
            "pyin_notes": PYINNotesAlgorithm,
            "pyin_pitch_changes": PYINPitchChangesAlgorithm,
        })
    except Exception as exc:
        print(f"WARNING: vamp_pitch unavailable: {exc}", file=sys.stderr)

    try:
        from src.analyzer.algorithms.vamp_harmony import (
            ChordinoAlgorithm, NNLSChromaAlgorithm,
        )
        algo_map.update({
            "chordino_chords": ChordinoAlgorithm,
            "nnls_chroma": NNLSChromaAlgorithm,
        })
    except Exception as exc:
        print(f"WARNING: vamp_harmony unavailable: {exc}", file=sys.stderr)

    try:
        from src.analyzer.algorithms.madmom_beat import (
            MadmomBeatAlgorithm, MadmomDownbeatAlgorithm,
        )
        algo_map.update({
            "madmom_beats": MadmomBeatAlgorithm,
            "madmom_downbeats": MadmomDownbeatAlgorithm,
        })
    except Exception as exc:
        print(f"WARNING: madmom unavailable: {exc}", file=sys.stderr)

    return algo_map


def main() -> None:
    # Read request from stdin
    try:
        line = sys.stdin.readline()
        request = json.loads(line)
    except Exception as exc:
        _emit({"event": "error", "message": f"Bad input: {exc}"})
        return

    audio_path: str = request["audio_path"]
    stem_paths: dict = request.get("stem_paths", {})
    algo_names: list[str] = request["algorithms"]

    # Load full-mix audio
    try:
        import librosa
        import numpy as np
        audio, sr = librosa.load(audio_path, sr=None, mono=True)
    except Exception as exc:
        _emit({"event": "error", "message": f"Failed to load audio: {exc}"})
        return

    # Load any stem audio provided
    stem_audio: dict[str, np.ndarray] = {}
    for stem_name, stem_path in stem_paths.items():
        try:
            arr, _ = librosa.load(stem_path, sr=sr, mono=True)
            stem_audio[stem_name] = arr
        except Exception:
            pass

    algo_map = _build_algo_map()

    tracks: list[dict] = []
    algorithms_meta: list[dict] = []
    total = len(algo_names)

    for idx, name in enumerate(algo_names):
        algo_cls = algo_map.get(name)
        if algo_cls is None:
            _emit({"event": "warn", "name": name, "message": f"Unknown algorithm: {name}"})
            _emit({"event": "progress", "idx": idx + 1, "total": total,
                   "name": name, "mark_count": 0})
            continue

        algo = algo_cls()

        # Use stem audio when available and preferred
        use_audio = audio
        if algo.preferred_stem != "full_mix" and algo.preferred_stem in stem_audio:
            use_audio = stem_audio[algo.preferred_stem]

        track = algo.run(use_audio, sr)

        if track is not None:
            from src.analyzer.scorer import score_track
            track.quality_score = score_track(track)
            tracks.append(track.to_dict())
            algorithms_meta.append(algo.metadata().to_dict())

        _emit({
            "event": "progress",
            "idx": idx + 1,
            "total": total,
            "name": name,
            "mark_count": track.mark_count if track else 0,
        })

    _emit({"event": "done", "tracks": tracks, "algorithms": algorithms_meta})


if __name__ == "__main__":
    main()
