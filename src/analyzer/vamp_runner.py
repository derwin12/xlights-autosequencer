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

# ── Restore deprecated numpy aliases for madmom 0.16.1 compatibility ─────────
# Madmom's compiled Cython extensions reference np.float/np.int which were
# removed in numpy 1.24+. Monkey-patching before any madmom import fixes this.
import numpy as _np  # noqa: E402
for _alias, _target in [("float", _np.float64), ("int", _np.int64),
                         ("bool", _np.bool_), ("complex", _np.complex128)]:
    if not hasattr(_np, _alias):
        setattr(_np, _alias, _target)

# ── Restore collections aliases removed in Python 3.10 ───────────────────────
# madmom 0.16.1's processors.py does `from collections import MutableSequence`,
# which moved to collections.abc in 3.10. Restore it before any madmom import.
import collections as _collections  # noqa: E402
import collections.abc as _collections_abc  # noqa: E402
if not hasattr(_collections, "MutableSequence"):
    _collections.MutableSequence = _collections_abc.MutableSequence

# ── Add the repo root to sys.path so src.* imports work ──────────────────────
# This file lives at src/analyzer/vamp_runner.py → repo root is 2 levels up.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def _build_algo_map() -> dict:
    """Return {name: AlgorithmClass} for every available vamp/madmom algorithm."""
    from src.analyzer.algorithms.registry import get_algorithm_map
    return get_algorithm_map(libraries={"vamp", "madmom"})


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

    for idx, raw_name in enumerate(algo_names):
        # Support "algo_name:stem_override" format for per-stem runs
        if ":" in raw_name:
            name, stem_override = raw_name.split(":", 1)
        else:
            name, stem_override = raw_name, None

        algo_cls = algo_map.get(name)
        if algo_cls is None:
            _emit({"event": "warn", "name": raw_name, "message": f"Unknown algorithm: {name}"})
            _emit({"event": "progress", "idx": idx + 1, "total": total,
                   "name": raw_name, "mark_count": 0})
            continue

        algo = algo_cls()

        # Apply stem override if specified (e.g. "bbc_energy:drums")
        if stem_override:
            algo.preferred_stem = stem_override
            algo.name = f"{name}_{stem_override}"

        # Use stem audio when available and preferred
        use_audio = audio
        if algo.preferred_stem != "full_mix" and algo.preferred_stem in stem_audio:
            use_audio = stem_audio[algo.preferred_stem]

        track = algo.run(use_audio, sr)

        if track is not None:
            from src.analyzer.scorer import score_track
            track.quality_score = score_track(track)
            if stem_override:
                track.stem_source = stem_override
                if hasattr(track, "value_curve") and track.value_curve is not None:
                    track.value_curve.stem_source = stem_override
            tracks.append(track.to_dict())
            algorithms_meta.append(algo.metadata().to_dict())

        has_curve = track is not None and getattr(track, "value_curve", None) is not None
        _emit({
            "event": "progress",
            "idx": idx + 1,
            "total": total,
            "name": raw_name,
            "mark_count": track.mark_count if track else 0,
            "has_curve": has_curve,
        })

    _emit({"event": "done", "tracks": tracks, "algorithms": algorithms_meta})


if __name__ == "__main__":
    main()
