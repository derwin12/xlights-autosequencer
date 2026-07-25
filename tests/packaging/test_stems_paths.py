"""T006 — stems cache-root writable-fallback behavior."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

from src.packaging.stems_paths import resolve_cache_root, _user_fallback_root


def test_prefers_source_adjacent_when_writable(tmp_path: Path) -> None:
    song_dir = tmp_path / "MySong"
    song_dir.mkdir()
    source = song_dir / "MySong.mp3"
    source.touch()

    result = resolve_cache_root(source)

    assert result == song_dir / "stems"


def test_uses_named_subdir_when_parent_name_differs(tmp_path: Path) -> None:
    source = tmp_path / "track.mp3"
    source.touch()

    result = resolve_cache_root(source)

    assert result == tmp_path / "track" / "stems"


def test_falls_back_to_application_support_when_parent_unwritable_macos(
    tmp_path: Path, monkeypatch,
) -> None:
    # Mock os.access directly rather than chmod: on Windows, setting a
    # directory's read-only attribute does not reliably block file/subdir
    # creation inside it (NTFS treats the folder flag as largely cosmetic),
    # so a chmod-based probe silently never exercises the fallback branch
    # on that platform. Mocking the access check itself is reliable on any
    # host OS and lets this test also pin the macOS-shaped expected path
    # regardless of which platform actually runs the test.
    song_dir = tmp_path / "readonly"
    song_dir.mkdir()
    source = song_dir / "readonly.mp3"
    source.touch()

    monkeypatch.setattr("src.packaging.stems_paths.os.access", lambda *a, **k: False)
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "darwin")
    fake_home = tmp_path / "fake_home"
    with mock.patch("src.packaging.platform_paths.Path.home", return_value=fake_home):
        result = resolve_cache_root(source)

    expected = (
        fake_home
        / "Library"
        / "Application Support"
        / "XLight"
        / "stems"
        / "readonly"
        / "stems"
    )
    assert result == expected
    assert result.is_dir()


def test_falls_back_to_application_support_when_parent_unwritable_windows(
    tmp_path: Path, monkeypatch,
) -> None:
    song_dir = tmp_path / "readonly"
    song_dir.mkdir()
    source = song_dir / "readonly.mp3"
    source.touch()

    monkeypatch.setattr("src.packaging.stems_paths.os.access", lambda *a, **k: False)
    monkeypatch.setattr("src.packaging.platform_paths.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    result = resolve_cache_root(source)

    expected = (
        tmp_path
        / "AppData"
        / "Local"
        / "XLight"
        / "stems"
        / "readonly"
        / "stems"
    )
    assert result == expected
    assert result.is_dir()


def test_user_fallback_root_shape() -> None:
    root = _user_fallback_root()
    assert root.name == "stems"
    assert root.parent.name == "XLight"
