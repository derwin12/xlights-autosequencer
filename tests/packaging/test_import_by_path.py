"""T065 — /api/v1/import/by-path endpoint (packaged-app path-based import).

Verifies:
  - Endpoint refuses when not running in bundled mode (403).
  - Happy path: reads file from disk, returns a created Song with the
    absolute path stored in source_paths[0].
  - Rejects non-existent paths (404) and unsupported extensions (400).
  - De-duplicates by content hash on a second call.

Status: the endpoint was specced (T065) but never implemented. The Tauri
frontend's native open-file dialog (src/review/frontend/src/lib/nativeDialog.ts)
calls /api/v1/import/by-path but the backend route is missing — Tauri builds
quietly fall back to upload-via-multipart for now. These tests are skipped
until the endpoint is implemented; once it lands, drop the skip marker.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.review.server import create_app

pytestmark = pytest.mark.skip(
    reason="T065 endpoint /api/v1/import/by-path is specced but not implemented. "
           "Tauri uses upload-via-multipart fallback. Drop this skip when the "
           "route lands in src/review/api/v1/import_.py.",
)


def _mp3_bytes(content: bytes = b"\xff\xfb\x90\x00" * 256) -> bytes:
    """A few KB of "mp3 frame header"-ish bytes. The endpoint only hashes
    and stores; duration parsing will fail gracefully (returns 0)."""
    return content


@pytest.fixture()
def client_bundled(tmp_path, monkeypatch):
    monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("XLIGHT_PACKAGED", "1")
    app = create_app(testing=True)
    app.config["TESTING"] = True
    yield app.test_client()


@pytest.fixture()
def client_dev(tmp_path, monkeypatch):
    monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("XLIGHT_PACKAGED", raising=False)
    app = create_app(testing=True)
    app.config["TESTING"] = True
    yield app.test_client()


def test_refuses_when_not_bundled(client_dev, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(_mp3_bytes())
    resp = client_dev.post("/api/v1/import/by-path", json={"path": str(audio)})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"]["code"] == "not_bundled"


def test_happy_path(client_bundled, tmp_path):
    audio = tmp_path / "test.mp3"
    audio.write_bytes(_mp3_bytes())
    resp = client_bundled.post(
        "/api/v1/import/by-path", json={"path": str(audio)}
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["created"] is True
    song = body["song"]
    assert "song_id" in song
    assert song["source_paths"][0] == str(audio.resolve())


def test_missing_path_404(client_bundled):
    resp = client_bundled.post(
        "/api/v1/import/by-path", json={"path": "/nowhere/does-not-exist.mp3"}
    )
    assert resp.status_code == 404


def test_missing_body_field_400(client_bundled):
    resp = client_bundled.post("/api/v1/import/by-path", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "missing_path"


def test_unsupported_extension_400(client_bundled, tmp_path):
    audio = tmp_path / "not-audio.txt"
    audio.write_bytes(b"hello")
    resp = client_bundled.post(
        "/api/v1/import/by-path", json={"path": str(audio)}
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "unsupported_format"


def test_dedup_on_second_call(client_bundled, tmp_path):
    audio = tmp_path / "dupe.mp3"
    audio.write_bytes(_mp3_bytes())

    first = client_bundled.post(
        "/api/v1/import/by-path", json={"path": str(audio)}
    ).get_json()
    second = client_bundled.post(
        "/api/v1/import/by-path", json={"path": str(audio)}
    ).get_json()

    assert first["created"] is True
    assert second["created"] is False
    assert first["song"]["song_id"] == second["song"]["song_id"]
