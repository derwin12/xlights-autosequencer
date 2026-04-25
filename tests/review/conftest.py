import os
import json
import tempfile
import pytest

from src.review.server import create_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Flask test-client app wired to a fresh temp library dir."""
    monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
    # Use the fast stub analysis pipeline in tests so they don't time out
    # waiting for the full vamp/demucs/madmom pipeline.
    monkeypatch.setenv("XLIGHT_STUB_ANALYSIS", "1")

    # Clear module-level analysis run state. `_runs` is a dict that
    # accumulates across test invocations because the analysis module
    # isn't reloaded between tests. Without this, tests that import the
    # same WAV bytes (→ same song_id) see stale state from prior runs
    # and /analyze responses can omit run_id when the prior run is
    # still cached.
    from src.review.api.v1 import analysis as _analysis_module
    with _analysis_module._runs_lock:
        _analysis_module._runs.clear()

    application = create_app(testing=True)
    application.config["TESTING"] = True
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_song():
    """Minimal Song dict matching data-model.md."""
    return {
        "song_id": "aabbccddeeff0011",
        "title": "Highway Star",
        "artist": "Deep Purple",
        "duration_ms": 370_000,
        "bpm": 148.0,
        "key": "E minor",
        "time_signature": [4, 4],
        "status": "draft",
        "source_paths": ["/tmp/highway.mp3"],
        "folder_id": "unfiled",
        "imported_at": "2026-04-21T00:00:00Z",
        "last_opened_at": None,
    }
