"""T008 — model cache paths under the platform's Application Support root."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

from src.packaging.models_paths import (
    get_download_state_path,
    get_model_cache_root,
    get_torch_home,
)


def test_torch_home_layout_macos(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "darwin")
    with mock.patch("src.packaging.platform_paths.Path.home", return_value=tmp_path):
        torch_home = get_torch_home()

    assert torch_home == (
        tmp_path
        / "Library"
        / "Application Support"
        / "xLightsAI"
        / "models"
        / "torch-hub"
    )
    assert (torch_home / "hub" / "checkpoints").is_dir()


def test_torch_home_layout_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    torch_home = get_torch_home()

    assert torch_home == (
        tmp_path
        / "AppData"
        / "Local"
        / "xLightsAI"
        / "models"
        / "torch-hub"
    )
    assert (torch_home / "hub" / "checkpoints").is_dir()


def test_model_cache_root_created(tmp_path: Path) -> None:
    with mock.patch("src.packaging.platform_paths.Path.home", return_value=tmp_path):
        root = get_model_cache_root()

    assert root.is_dir()
    assert root.name == "models"


def test_download_state_path_location(tmp_path: Path) -> None:
    with mock.patch("src.packaging.platform_paths.Path.home", return_value=tmp_path):
        state = get_download_state_path()
        cache_root = get_model_cache_root()

    assert state.parent == cache_root
    assert state.name == ".download-state.json"
