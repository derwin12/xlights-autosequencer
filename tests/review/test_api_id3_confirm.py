"""Tests for the v1 ID3 confirmation endpoints (OpenSpec
``lyric-anchored-boundary-refinement`` §6a). Covers both invocation paths:

- Pre-flight (Path A): GET /api/v1/songs/<id>/id3-tags + extended POST
  /api/v1/songs/<id>/analyze body fields.
- SSE-blocking (Path B): POST /api/v1/songs/<id>/analyze/id3-confirm
  unblocks a thread waiting on ``state.wait_for_id3_response``.
"""
from __future__ import annotations

import io
import struct
import wave


def _make_wav_bytes(duration_secs: float = 6.0, sample_rate: int = 22050) -> bytes:
    import math

    n = int(duration_secs * sample_rate)
    samples = [int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(n)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{n}h", *samples))
    return buf.getvalue()


def _import_wav(client) -> str:
    data = client.post(
        "/api/v1/import",
        data={"audio": (io.BytesIO(_make_wav_bytes()), "test.wav")},
        content_type="multipart/form-data",
    ).get_json()
    return data["song"]["song_id"]


# ── GET /id3-tags ─────────────────────────────────────────────────────────────

class TestGetId3Tags:
    def test_returns_title_and_artist(self, client, monkeypatch):
        song_id = _import_wav(client)
        # Stub the read so we don't depend on real mutagen/ID3 on disk.
        monkeypatch.setattr(
            "src.review.server.read_id3_metadata",
            lambda _path: ("Hello", "Adele"),
        )
        resp = client.get(f"/api/v1/songs/{song_id}/id3-tags")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body == {"title": "Hello", "artist": "Adele"}

    def test_unreadable_tags_return_empty_strings(self, client, monkeypatch):
        song_id = _import_wav(client)
        monkeypatch.setattr(
            "src.review.server.read_id3_metadata",
            lambda _path: ("", ""),
        )
        resp = client.get(f"/api/v1/songs/{song_id}/id3-tags")
        assert resp.status_code == 200
        assert resp.get_json() == {"title": "", "artist": ""}

    def test_unknown_song_returns_404(self, client):
        resp = client.get("/api/v1/songs/deadbeef00000000/id3-tags")
        assert resp.status_code == 404


# ── POST /analyze body extensions ─────────────────────────────────────────────

class TestAnalyzeBodyId3Fields:
    def test_override_title_artist_accepted(self, client):
        song_id = _import_wav(client)
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze",
            json={"override_title": "Real Title", "override_artist": "Real Artist"},
        )
        assert resp.status_code == 202

    def test_skip_genius_accepted(self, client):
        song_id = _import_wav(client)
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze",
            json={"skip_genius": True},
        )
        assert resp.status_code == 202

    def test_prompt_id3_accepted(self, client):
        song_id = _import_wav(client)
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze",
            json={"prompt_id3": True},
        )
        assert resp.status_code == 202


# ── POST /analyze/id3-confirm ─────────────────────────────────────────────────

class TestAnalyzeId3Confirm:
    def test_no_active_run_returns_400(self, client):
        # Import only — no analyze yet, so no _runs entry.
        song_id = _import_wav(client)
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/id3-confirm",
            json={"response": "confirm"},
        )
        assert resp.status_code == 400

    def test_invalid_response_returns_400(self, client):
        song_id = _import_wav(client)
        # Seed a fake running state directly so the route gets past the
        # "no active run" guard. The stub-backed POST /analyze flips the
        # state to "done" too quickly to race against.
        from src.review.api.v1 import analysis as _a
        from src.review.api.v1.analysis import _RunState
        with _a._runs_lock:
            _a._runs[song_id] = _RunState("run_x", song_id)

        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/id3-confirm",
            json={"response": "nonsense"},
        )
        assert resp.status_code == 400
        assert "response must be one of" in resp.get_json()["error"]["message"]

    def test_correct_without_title_or_artist_returns_400(self, client):
        song_id = _import_wav(client)
        from src.review.api.v1 import analysis as _a
        from src.review.api.v1.analysis import _RunState
        with _a._runs_lock:
            _a._runs[song_id] = _RunState("run_x", song_id)

        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/id3-confirm",
            json={"response": "correct"},
        )
        assert resp.status_code == 400

    def test_confirm_unblocks_run_state(self, client):
        song_id = _import_wav(client)
        from src.review.api.v1 import analysis as _a
        from src.review.api.v1.analysis import _RunState
        state = _RunState("run_x", song_id)
        with _a._runs_lock:
            _a._runs[song_id] = state

        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/id3-confirm",
            json={"response": "confirm"},
        )
        assert resp.status_code == 200
        assert state.id3_response == "confirm"
        assert state._id3_event.is_set()

    def test_correct_records_title_artist_and_write_back(self, client):
        song_id = _import_wav(client)
        from src.review.api.v1 import analysis as _a
        from src.review.api.v1.analysis import _RunState
        state = _RunState("run_x", song_id)
        with _a._runs_lock:
            _a._runs[song_id] = state

        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/id3-confirm",
            json={
                "response": "correct",
                "title": "Right Title",
                "artist": "Right Artist",
                "write_back": True,
            },
        )
        assert resp.status_code == 200
        assert state.id3_response == "correct"
        assert state.id3_corrected_title == "Right Title"
        assert state.id3_corrected_artist == "Right Artist"
        assert state.id3_write_back is True

    def test_skip_records_response(self, client):
        song_id = _import_wav(client)
        from src.review.api.v1 import analysis as _a
        from src.review.api.v1.analysis import _RunState
        state = _RunState("run_x", song_id)
        with _a._runs_lock:
            _a._runs[song_id] = state

        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/id3-confirm",
            json={"response": "skip"},
        )
        assert resp.status_code == 200
        assert state.id3_response == "skip"


# ── Run-state prompt machinery ────────────────────────────────────────────────

class TestRunStatePromptMachinery:
    def test_prompt_emits_event_and_clears_wait(self):
        from src.review.api.v1.analysis import _RunState
        state = _RunState("run_x", "song_x")
        # Pre-set the event so we can prove prompt_id3_confirm clears it.
        state._id3_event.set()
        state.prompt_id3_confirm("Hello", "Adele")
        assert not state._id3_event.is_set()
        assert state.events[-1] == {
            "id3_confirm_prompt": True,
            "id3_title": "Hello",
            "id3_artist": "Adele",
        }

    def test_submit_releases_wait(self):
        from src.review.api.v1.analysis import _RunState
        state = _RunState("run_x", "song_x")
        state.prompt_id3_confirm("X", "Y")

        # Spawn a waiter that times out only if submit_id3_response fails.
        import threading
        result: list[str | None] = []
        def _wait():
            result.append(state.wait_for_id3_response(timeout=2.0))
        t = threading.Thread(target=_wait)
        t.start()
        state.submit_id3_response(
            "correct", title="T", artist="A", write_back=True,
        )
        t.join(timeout=3.0)
        assert result == ["correct"]
        assert state.id3_corrected_title == "T"
        assert state.id3_corrected_artist == "A"
        assert state.id3_write_back is True
