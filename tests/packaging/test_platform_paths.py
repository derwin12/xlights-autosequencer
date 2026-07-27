"""app_support_root() resolves the correct Application Support root per OS."""
from __future__ import annotations

from pathlib import Path

from src.packaging.platform_paths import app_support_root


def test_macos_uses_library_application_support(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "darwin")
    monkeypatch.setattr("src.packaging.platform_paths.Path.home", lambda: tmp_path)

    root = app_support_root()

    assert root == tmp_path / "Library" / "Application Support" / "xLightsAI"


def test_windows_uses_localappdata_env_var(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    root = app_support_root()

    assert root == tmp_path / "AppData" / "Local" / "xLightsAI"


def test_windows_falls_back_to_home_when_localappdata_unset(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr("src.packaging.platform_paths.Path.home", lambda: tmp_path)

    root = app_support_root()

    assert root == tmp_path / "AppData" / "Local" / "xLightsAI"


def test_linux_uses_local_share(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "linux")
    monkeypatch.setattr("src.packaging.platform_paths.Path.home", lambda: tmp_path)

    root = app_support_root()

    assert root == tmp_path / ".local" / "share" / "xLightsAI"
