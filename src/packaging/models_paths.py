"""Paths for downloaded model weights (demucs htdemucs_6s).

Lives under the platform's Application Support root (see platform_paths.py)
so the cache survives reinstalls and is isolated from the small-JSON config
in `~/.xlight/`.
"""
from __future__ import annotations

from pathlib import Path

from src.packaging.platform_paths import app_support_root


def get_model_cache_root() -> Path:
    """Root directory for all downloaded model assets."""
    root = app_support_root() / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_torch_home() -> Path:
    """Directory to set as `TORCH_HOME` so demucs/torch caches here.

    Matches torch.hub layout: `<TORCH_HOME>/hub/checkpoints/<model>.th`.
    """
    torch_home = get_model_cache_root() / "torch-hub"
    (torch_home / "hub" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return torch_home


def get_download_state_path() -> Path:
    """Location of `.download-state.json` for resumable downloads."""
    return get_model_cache_root() / ".download-state.json"
