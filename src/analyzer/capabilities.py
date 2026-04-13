"""Capability detection for the hierarchy orchestrator.

Detects which optional analysis tools are installed and available.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

# Path to the .venv-vamp Python interpreter.
# Prefer XLIGHT_VENV_VAMP env var (set by devcontainer to /home/node/.venv-vamp/bin/python)
# so it survives the workspace bind mount. Falls back to repo-relative path for local dev.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VAMP_PYTHON = (
    Path(os.environ["XLIGHT_VENV_VAMP"])
    if os.environ.get("XLIGHT_VENV_VAMP")
    else _REPO_ROOT / ".venv-vamp" / "bin" / "python"
)


def _probe_venv_vamp() -> dict[str, bool]:
    """Ask .venv-vamp whether vamp/madmom/demucs are importable there."""
    if not _VAMP_PYTHON.exists():
        return {}
    script = (
        "import json, sys\n"
        "r = {}\n"
        "try:\n"
        "    import vamp; r['vamp_pkg'] = True\n"
        "except ImportError:\n"
        "    r['vamp_pkg'] = False\n"
        "try:\n"
        "    import numpy as _np\n"
        "    for a,t in [('float',_np.float64),('int',_np.int64),"
        "('bool',_np.bool_),('complex',_np.complex128)]:\n"
        "        setattr(_np, a, t) if not hasattr(_np, a) else None\n"
        "    import madmom; r['madmom'] = True\n"
        "except ImportError:\n"
        "    r['madmom'] = False\n"
        "try:\n"
        "    import demucs, torch; r['demucs'] = True\n"
        "except ImportError:\n"
        "    r['demucs'] = False\n"
        "try:\n"
        "    import whisperx; r['whisperx'] = True\n"
        "except ImportError:\n"
        "    r['whisperx'] = False\n"
        "print(json.dumps(r))\n"
    )
    try:
        out = subprocess.check_output(
            [str(_VAMP_PYTHON), "-c", script],
            timeout=15,
            stderr=subprocess.DEVNULL,
        )
        return json.loads(out.decode())
    except Exception:
        return {}


def detect_capabilities() -> dict[str, bool]:
    """Detect installed optional analysis tools.

    Returns a dict mapping capability name to availability bool.
    Checks: vamp (package + plugins), madmom, demucs, whisperx, genius.
    """
    caps: dict[str, bool] = {
        "vamp": False,
        "madmom": False,
        "demucs": False,
        "essentia": False,
        "whisperx": False,
        "genius": False,
    }

    # vamp/madmom/demucs live in .venv-vamp (separate virtualenv with numpy<2).
    # Try direct import first; if that fails (common when running from the main
    # venv), probe .venv-vamp via a short subprocess call.
    _venv_caps: dict[str, bool] | None = None

    def _venv_cap(key: str) -> bool:
        nonlocal _venv_caps
        if _venv_caps is None:
            _venv_caps = _probe_venv_vamp()
        return bool(_venv_caps.get(key))

    # vamp: package must be importable AND at least one plugin must exist
    plugin_dirs = [
        os.path.expanduser("~/Library/Audio/Plug-Ins/Vamp"),  # macOS
        os.path.expanduser("~/.local/lib/vamp"),  # Linux user-local
        "/usr/local/lib/vamp",
        "/usr/lib/vamp",
    ]
    # Also honour VAMP_PATH environment variable
    vamp_path = os.environ.get("VAMP_PATH", "")
    if vamp_path:
        plugin_dirs = vamp_path.split(os.pathsep) + plugin_dirs
    has_plugins = any(
        os.path.isdir(d) and any(
            f.endswith(".dylib") or f.endswith(".so")
            for f in os.listdir(d)
        )
        for d in plugin_dirs
        if os.path.isdir(d)
    )

    vamp_pkg = False
    try:
        import vamp  # noqa: F401
        vamp_pkg = True
    except ImportError:
        vamp_pkg = _venv_cap("vamp_pkg")
    caps["vamp"] = vamp_pkg and has_plugins

    try:
        # madmom 0.16.1 needs deprecated numpy aliases restored before import
        import numpy as _np
        _np.float = _np.float64   # type: ignore[attr-defined]
        _np.int = _np.int64       # type: ignore[attr-defined]
        _np.bool = _np.bool_      # type: ignore[attr-defined]
        _np.complex = _np.complex128  # type: ignore[attr-defined]
        import madmom  # noqa: F401
        caps["madmom"] = True
    except (ImportError, AttributeError):
        caps["madmom"] = _venv_cap("madmom")

    try:
        import demucs  # noqa: F401
        import torch  # noqa: F401
        caps["demucs"] = True
    except ImportError:
        caps["demucs"] = _venv_cap("demucs")

    try:
        import whisperx  # noqa: F401
        caps["whisperx"] = True
    except ImportError:
        caps["whisperx"] = _venv_cap("whisperx")

    try:
        import essentia.standard  # noqa: F401
        caps["essentia"] = True
    except ImportError:
        pass

    caps["genius"] = bool(os.environ.get("GENIUS_API_TOKEN"))

    return caps
