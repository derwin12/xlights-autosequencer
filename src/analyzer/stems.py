"""Stem separation: StemSet dataclass, StemSeparator, StemCache."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# ── StemSet ───────────────────────────────────────────────────────────────────

@dataclass
class StemSet:
    """Six audio arrays from Demucs htdemucs_6s separation, held in memory."""

    drums: np.ndarray
    bass: np.ndarray
    vocals: np.ndarray
    guitar: np.ndarray
    piano: np.ndarray
    other: np.ndarray
    sample_rate: int

    def get(self, stem_name: str) -> np.ndarray | None:
        """Return the array for *stem_name*, or None if not a valid stem."""
        return getattr(self, stem_name, None)


# ── StemCache ─────────────────────────────────────────────────────────────────

_STEM_NAMES = ["drums", "bass", "vocals", "guitar", "piano", "other"]


class StemCache:
    """
    On-disk cache of WAV stems for a single source audio file.

    Cache layout (adjacent to source file by default):
        <source_dir>/.stems/<md5_hash>/drums.wav
                                       bass.wav
                                       ...
                                       manifest.json

    The MD5 hash of the source file is both the directory name and the
    cache key, so a stale cache is detected simply by recomputing the hash.
    """

    def __init__(self, source_path: Path, cache_root: Path | None = None) -> None:
        self.source_path = source_path.resolve()
        # Follow project convention: store under song folder
        if cache_root:
            self._cache_root = cache_root
        elif source_path.parent.name == source_path.stem:
            self._cache_root = source_path.parent / "stems"
        else:
            self._cache_root = source_path.parent / source_path.stem / "stems"
        self.source_hash = _md5_file(self.source_path)
        self.stem_dir = self._cache_root

    def is_valid(self) -> bool:
        """Return True if the cache directory exists and the manifest is readable."""
        manifest = self.stem_dir / "manifest.json"
        if not manifest.exists():
            return False
        try:
            data = json.loads(manifest.read_text())
            return data.get("source_hash") == self.source_hash
        except Exception:
            return False

    def save(self, stem_set: StemSet) -> None:
        """Write all stems as MP3 files and a manifest.json."""
        self.stem_dir.mkdir(parents=True, exist_ok=True)
        stem_files: dict[str, str] = {}

        for name in _STEM_NAMES:
            arr = getattr(stem_set, name)
            mp3_path = self.stem_dir / f"{name}.mp3"
            _write_mp3(arr, stem_set.sample_rate, mp3_path)
            stem_files[name] = f"{name}.mp3"

        from src.paths import PathContext as _PathContext
        manifest = {
            "source_hash": self.source_hash,
            "source_path": str(self.source_path),
            "created_at": int(time.time() * 1000),
            "stems": stem_files,
        }
        rel = _PathContext().to_relative(str(self.source_path))
        if rel is not None:
            manifest["relative_source_path"] = rel
        (self.stem_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    def load(self) -> StemSet:
        """Load stems from WAV files and return a StemSet."""
        import librosa

        manifest = json.loads((self.stem_dir / "manifest.json").read_text())
        arrays: dict[str, np.ndarray] = {}
        sr: int = 0

        for name in _STEM_NAMES:
            wav_file = manifest["stems"][name]
            wav_path = self.stem_dir / wav_file
            arr, file_sr = librosa.load(str(wav_path), sr=None, mono=True, dtype=np.float32)
            arrays[name] = arr
            sr = int(file_sr)

        return StemSet(**arrays, sample_rate=sr)


# ── StemSeparator ─────────────────────────────────────────────────────────────

class StemSeparator:
    """
    Separates an audio file into six stems using Demucs htdemucs_6s.

    Checks the StemCache before running Demucs. On a cache hit the model
    is not loaded at all.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir  # passed through to StemCache

    def separate(self, audio_path: Path) -> StemSet:
        """
        Return a StemSet for *audio_path*.

        Checks cache first; runs Demucs if no valid cache exists; writes
        result to cache before returning.
        """
        cache = StemCache(audio_path, cache_root=self._cache_dir)

        if cache.is_valid():
            print(f"Stem separation: cache hit ({cache.source_hash[:8]})", file=sys.stderr)
            return cache.load()

        print("Stem separation: checking cache...", file=sys.stderr)
        print("  → No cache found. Separating (this may take 1-2 minutes)...", file=sys.stderr)

        stem_set = self._run_demucs(audio_path, cache.source_hash)

        cache.save(stem_set)
        print(f"  → Stems cached to {cache.stem_dir}/", file=sys.stderr)

        return stem_set

    def _run_demucs(self, audio_path: Path, source_hash: str) -> StemSet:
        """Run Demucs in .venv-vamp subprocess and return a StemSet.

        demucs/torch live in .venv-vamp (not the main venv). We run the
        separation there, write stems to a temp dir, then load them back.
        """
        import subprocess as _sp
        import tempfile

        import os as _os
        repo_root = Path(__file__).resolve().parents[2]
        vamp_python = (
            Path(_os.environ["XLIGHT_VENV_VAMP"])
            if _os.environ.get("XLIGHT_VENV_VAMP")
            else repo_root / ".venv-vamp" / "bin" / "python"
        )
        if not vamp_python.exists():
            raise RuntimeError(
                ".venv-vamp not found — cannot run demucs. Run ./scripts/install.sh"
            )

        # Temp dir for the subprocess to write stems into
        with tempfile.TemporaryDirectory(prefix="xlight_stems_") as tmp_dir:
            script = f'''
import sys, json, os
import numpy as np
import torch, librosa
from demucs.pretrained import get_model
from demucs.apply import apply_model

audio_path = {str(audio_path)!r}
out_dir = {tmp_dir!r}

wav_np, sr = librosa.load(audio_path, sr=None, mono=False, dtype=np.float32)
if wav_np.ndim == 1:
    wav_np = np.stack([wav_np, wav_np])

print("  → htdemucs_6s (drums, bass, vocals, guitar, piano, other)...", file=sys.stderr)
model = get_model("htdemucs_6s")
model.eval()

wav = torch.from_numpy(np.ascontiguousarray(wav_np))
if sr != model.samplerate:
    import torchaudio
    wav = torchaudio.functional.resample(wav, sr, model.samplerate)
if wav.shape[0] == 1:
    wav = wav.repeat(2, 1)
elif wav.shape[0] > 2:
    wav = wav[:2]

with torch.no_grad():
    out = apply_model(model, wav.unsqueeze(0), device="cpu", shifts=0, progress=False)
out = out[0]

stem_names = ["drums", "bass", "vocals", "guitar", "piano", "other"]
result = {{"sample_rate": model.samplerate}}
for i, name in enumerate(model.sources):
    if name in stem_names:
        arr = out[i].mean(dim=0).numpy().astype(np.float32)
        npy_path = os.path.join(out_dir, name + ".npy")
        np.save(npy_path, arr)
        result[name] = npy_path

# Fill missing stems
n_samples = out.shape[-1]
for name in stem_names:
    if name not in result:
        npy_path = os.path.join(out_dir, name + ".npy")
        np.save(npy_path, np.zeros(n_samples, dtype=np.float32))
        result[name] = npy_path

print(json.dumps(result))
'''
            print("  → htdemucs_6s (drums, bass, vocals, guitar, piano, other)...",
                  file=sys.stderr)
            try:
                proc = _sp.run(
                    [str(vamp_python), "-c", script],
                    capture_output=True, text=True, timeout=600,
                )
            except _sp.TimeoutExpired:
                raise RuntimeError(
                    "Demucs stem separation timed out after 10 minutes. "
                    "This may indicate insufficient memory or CPU. "
                    "Try closing other applications and retrying."
                )
            if proc.returncode != 0:
                stderr_snippet = proc.stderr[:1000] if proc.stderr else "(no stderr)"
                raise RuntimeError(
                    f"Demucs stem separation failed (exit code {proc.returncode}):\n"
                    f"{stderr_snippet}"
                )

            # Parse the JSON output (last line of stdout)
            data = json.loads(proc.stdout.strip().split("\n")[-1])
            sr = int(data["sample_rate"])
            arrays: dict[str, np.ndarray] = {}
            for name in _STEM_NAMES:
                npy_path = data.get(name)
                if npy_path and Path(npy_path).exists():
                    arrays[name] = np.load(npy_path)
                else:
                    arrays[name] = np.zeros(1, dtype=np.float32)

            return StemSet(**arrays, sample_rate=sr)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _md5_file(path: Path) -> str:
    """Return the MD5 hex digest of a file's contents."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_ffmpeg() -> str:
    """Return the path to the ffmpeg binary, checking common install locations."""
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "ffmpeg not found. Install via: brew install ffmpeg"
    )


def _write_mp3(arr: np.ndarray, sample_rate: int, path: Path) -> None:
    """Write a float32 mono numpy array to an MP3 file via ffmpeg."""
    import subprocess
    pcm = (arr * 32768.0).clip(-32768, 32767).astype(np.int16)
    subprocess.run(
        [
            _find_ffmpeg(), "-y",
            "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
            "-i", "pipe:0",
            "-q:a", "2",
            str(path),
        ],
        input=pcm.tobytes(),
        check=True,
        capture_output=True,
    )
