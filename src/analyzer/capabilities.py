"""Capability detection for the hierarchy orchestrator.

Detects which optional analysis tools are installed and available.
"""
from __future__ import annotations

import os


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

    # vamp: package must be importable AND at least one plugin must exist
    try:
        import vamp  # noqa: F401
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
        caps["vamp"] = has_plugins
    except ImportError:
        pass

    try:
        import madmom  # noqa: F401
        caps["madmom"] = True
    except ImportError:
        pass

    try:
        import demucs  # noqa: F401
        import torch  # noqa: F401
        caps["demucs"] = True
    except ImportError:
        pass

    try:
        import whisperx  # noqa: F401
        caps["whisperx"] = True
    except ImportError:
        pass

    try:
        import essentia.standard  # noqa: F401
        caps["essentia"] = True
    except ImportError:
        pass

    caps["genius"] = bool(os.environ.get("GENIUS_API_TOKEN"))

    return caps
