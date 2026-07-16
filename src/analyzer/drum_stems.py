"""Cymbal separation: chain a drumsep checkpoint on the demucs drums stem.

The crash-accent detector (src/analyzer/crash_accents.py) needs a
cymbal-isolated signal: 2026-07-16 validation on Dream On showed the
isolation score ranks all 6 user-confirmed crashes top-6 on a cymbals stem
but fails on the full drum kit (kick/snare/tom transients swamp the
envelope) and on the full mix (vocal sibilance/bright guitar bury the
quieter crashes). See openspec/changes/crash-stem-impact-score/design.html.

The model is drumsep (inagoy/drumsep) — a Hybrid Demucs fine-tune that
splits a drum stem into bombo (kick), redoblante (snare), platillos
(cymbals), and toms. It loads through the existing demucs/torch optional
dependency; the ~167MB checkpoint is downloaded once to
~/.xlight/models/drumsep/ (same spirit as demucs' own torch-hub checkpoint
downloads).

Everything here degrades gracefully: any unavailability (no demucs/torch,
download failure, separation error) returns None and the caller emits no
crash marks. For a rare-by-design feature, zero marks beats wrong marks.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

DRUMSEP_MODEL_NAME = "49469ca8"
_DRUMSEP_GDRIVE_ID = "1-Dm666ScPkg8Gt2-lK3Ua0xOudWHZBGC"
_CYMBALS_SOURCE = "platillos"
_CACHE_FILENAME = "drums_cymbals.mp3"


def default_model_dir() -> Path:
    return Path.home() / ".xlight" / "models" / "drumsep"


def checkpoint_path() -> Path:
    return default_model_dir() / f"{DRUMSEP_MODEL_NAME}.th"


def ensure_checkpoint() -> Path | None:
    """Return the drumsep checkpoint path, downloading it if missing.

    Returns None (never raises) if the download fails — e.g. offline or
    Google Drive quota — so analysis proceeds without crash accents.
    """
    ckpt = checkpoint_path()
    if ckpt.exists():
        return ckpt
    try:
        _download_from_gdrive(_DRUMSEP_GDRIVE_ID, ckpt)
        return ckpt
    except Exception as exc:
        print(f"drumsep checkpoint download failed: {exc}", file=sys.stderr)
        return None


def _download_from_gdrive(file_id: str, dst: Path) -> None:
    """Download a Google Drive file, handling the virus-scan confirm page."""
    import re
    import urllib.parse
    import urllib.request

    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        first = resp.read(4096)
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            # Large files return a confirm form instead of the payload.
            html = (first + resp.read()).decode("utf-8", "replace")
            action_m = re.search(r'action="([^"]+)"', html)
            if not action_m:
                raise RuntimeError("Drive confirm page had no download form")
            fields = dict(re.findall(
                r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html))
            url = action_m.group(1) + "?" + urllib.parse.urlencode(fields)
            req = urllib.request.Request(url, headers=headers)
            body_resp = urllib.request.urlopen(req, timeout=600)
            first = b""
        else:
            body_resp = resp
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".tmp")
        print(f"Downloading drumsep checkpoint to {dst} ...", file=sys.stderr)
        with open(tmp, "wb") as fh:
            fh.write(first)
            while True:
                chunk = body_resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
    if tmp.stat().st_size < 1_000_000:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("downloaded file is implausibly small — not the checkpoint")
    tmp.replace(dst)


def separate_cymbals(
    drums_audio: np.ndarray,
    sample_rate: int,
    cache_dir: Path | None = None,
) -> tuple[np.ndarray, int] | None:
    """Return (cymbals_mono_float32, sample_rate) for a drums-stem array.

    Checks *cache_dir* (the song's existing .stems/<hash>/ directory) for a
    previously separated cymbals file first. Returns None on any failure.
    """
    if drums_audio.size <= 1 or not float(np.abs(drums_audio).max()) > 0.0:
        return None

    cache_file = (cache_dir / _CACHE_FILENAME) if cache_dir else None
    if cache_file is not None and cache_file.exists():
        try:
            import librosa
            arr, sr = librosa.load(str(cache_file), sr=None, mono=True,
                                   dtype=np.float32)
            return arr, int(sr)
        except Exception as exc:
            print(f"cymbals cache load failed ({exc}); re-separating",
                  file=sys.stderr)

    ckpt = ensure_checkpoint()
    if ckpt is None:
        return None

    try:
        cymbals, out_sr = _run_drumsep_inprocess(drums_audio, sample_rate,
                                                 ckpt.parent)
    except ImportError:
        try:
            cymbals, out_sr = _run_drumsep_sidecar(drums_audio, sample_rate,
                                                   ckpt.parent)
        except Exception as exc:
            print(f"drumsep sidecar separation failed: {exc}", file=sys.stderr)
            return None
    except Exception as exc:
        print(f"drumsep separation failed: {exc}", file=sys.stderr)
        return None

    if cache_file is not None:
        try:
            from src.analyzer.stems import _write_mp3
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            _write_mp3(cymbals, out_sr, cache_file)
        except Exception as exc:
            print(f"cymbals cache write failed ({exc})", file=sys.stderr)

    return cymbals, out_sr


def _run_drumsep_inprocess(
    drums_audio: np.ndarray, sample_rate: int, repo_dir: Path,
) -> tuple[np.ndarray, int]:
    """Run the drumsep model in this process (demucs/torch importable here)."""
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = _load_drumsep_model(get_model, repo_dir)
    model.eval()

    wav = torch.from_numpy(np.ascontiguousarray(drums_audio.astype(np.float32)))
    if wav.ndim == 1:
        wav = wav.unsqueeze(0)
    if sample_rate != model.samplerate:
        import torchaudio
        wav = torchaudio.functional.resample(wav, sample_rate, model.samplerate)
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    elif wav.shape[0] > 2:
        wav = wav[:2]

    with torch.no_grad():
        out = apply_model(model, wav.unsqueeze(0), device="cpu", shifts=0,
                          progress=False)[0]
    if _CYMBALS_SOURCE not in model.sources:
        raise RuntimeError(
            f"drumsep model sources {model.sources} lack '{_CYMBALS_SOURCE}'")
    cymbals = out[model.sources.index(_CYMBALS_SOURCE)].mean(dim=0)
    return cymbals.numpy().astype(np.float32), int(model.samplerate)


def _load_drumsep_model(get_model, repo_dir: Path):
    """Load the drumsep checkpoint, allowlisting its pickled model class.

    The 2022 checkpoint pickles the HDemucs class itself, which torch>=2.6
    (weights_only=True default) rejects without an explicit allowlist.
    """
    import torch.serialization
    from demucs.hdemucs import HDemucs

    try:
        ctx = torch.serialization.safe_globals([HDemucs])
    except AttributeError:  # torch < 2.6: no allowlist needed
        return get_model(DRUMSEP_MODEL_NAME, repo=repo_dir)
    with ctx:
        return get_model(DRUMSEP_MODEL_NAME, repo=repo_dir)


def _run_drumsep_sidecar(
    drums_audio: np.ndarray, sample_rate: int, repo_dir: Path,
) -> tuple[np.ndarray, int]:
    """Run drumsep in the .venv-vamp sidecar (demucs not importable here).

    Same handoff pattern as StemSeparator._run_demucs: write the input as
    .npy, run a small script in the sidecar python, read the output .npy.
    """
    import json
    import os
    import subprocess
    import tempfile

    repo_root = Path(__file__).resolve().parents[2]
    vamp_python = (
        Path(os.environ["XLIGHT_VENV_VAMP"])
        if os.environ.get("XLIGHT_VENV_VAMP")
        else repo_root / ".venv-vamp" / "bin" / "python"
    )
    if not vamp_python.exists():
        raise RuntimeError(".venv-vamp not found — cannot run drumsep")

    with tempfile.TemporaryDirectory(prefix="xlight_drumsep_") as tmp_dir:
        in_npy = os.path.join(tmp_dir, "drums.npy")
        out_npy = os.path.join(tmp_dir, "cymbals.npy")
        np.save(in_npy, drums_audio.astype(np.float32))
        script = f'''
import json, sys
import numpy as np
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

drums = np.load({in_npy!r})
from demucs.hdemucs import HDemucs
try:
    _ctx = torch.serialization.safe_globals([HDemucs])
except AttributeError:
    model = get_model({DRUMSEP_MODEL_NAME!r}, repo=__import__("pathlib").Path({str(repo_dir)!r}))
else:
    with _ctx:
        model = get_model({DRUMSEP_MODEL_NAME!r}, repo=__import__("pathlib").Path({str(repo_dir)!r}))
model.eval()
wav = torch.from_numpy(np.ascontiguousarray(drums))
if wav.ndim == 1:
    wav = wav.unsqueeze(0)
if {sample_rate} != model.samplerate:
    import torchaudio
    wav = torchaudio.functional.resample(wav, {sample_rate}, model.samplerate)
if wav.shape[0] == 1:
    wav = wav.repeat(2, 1)
elif wav.shape[0] > 2:
    wav = wav[:2]
with torch.no_grad():
    out = apply_model(model, wav.unsqueeze(0), device="cpu", shifts=0, progress=False)[0]
cymbals = out[model.sources.index({_CYMBALS_SOURCE!r})].mean(dim=0).numpy().astype(np.float32)
np.save({out_npy!r}, cymbals)
print(json.dumps({{"sample_rate": model.samplerate}}))
'''
        proc = subprocess.run(
            [str(vamp_python), "-c", script],
            capture_output=True, text=True, timeout=900,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"drumsep sidecar exit {proc.returncode}: "
                f"{(proc.stderr or '')[:500]}")
        info = json.loads(proc.stdout.strip().split("\n")[-1])
        return np.load(out_npy), int(info["sample_rate"])
