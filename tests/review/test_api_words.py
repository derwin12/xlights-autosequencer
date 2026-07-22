"""Tests for the word-attribution edit endpoints (GET/PUT /songs/<id>/words)."""
from __future__ import annotations

import io
import struct
import wave


def _wav_bytes(duration_secs: float = 6.0) -> bytes:
    import math
    sr = 22050
    n = int(duration_secs * sr)
    samples = [int(8000 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(n)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{n}h", *samples))
    return buf.getvalue()


def _import(client) -> str:
    return client.post(
        "/api/v1/import",
        data={"audio": (io.BytesIO(_wav_bytes()), "test.wav")},
        content_type="multipart/form-data",
    ).get_json()["song"]["song_id"]


def _seed_session(song_id: str):
    from src.review.storage.assignments import save_full_session
    save_full_session(song_id, {
        "sections": [], "assignments": [],
        "words": [
            {"label": "A", "start_ms": 0, "end_ms": 400, "singers": ["Blake"], "backing": False},
            {"label": "B", "start_ms": 500, "end_ms": 900, "singers": ["Gwen"], "backing": False},
        ],
        "phonemes": [
            {"label": "AI", "start_ms": 10, "end_ms": 390, "singers": ["Blake"], "backing": False},
            {"label": "O", "start_ms": 510, "end_ms": 880, "singers": ["Gwen"], "backing": False},
        ],
    })


class TestGetWords:
    def test_404_unknown_song(self, client):
        assert client.get("/api/v1/songs/nope/words").status_code == 404

    def test_returns_seeded_words_and_singers(self, client):
        sid = _import(client)
        _seed_session(sid)
        data = client.get(f"/api/v1/songs/{sid}/words").get_json()
        assert [w["label"] for w in data["words"]] == ["A", "B"]
        assert data["singers"] == ["Blake", "Gwen"]


class TestPutWords:
    def test_relabel_persists_and_propagates_to_phonemes(self, client):
        sid = _import(client)
        _seed_session(sid)
        # Relabel word B to "Both" (Blake & Gwen).
        new_words = [
            {"label": "A", "start_ms": 0, "end_ms": 400, "singers": ["Blake"], "backing": False},
            {"label": "B", "start_ms": 500, "end_ms": 900, "singers": ["Blake", "Gwen"], "backing": False},
        ]
        resp = client.put(f"/api/v1/songs/{sid}/words", json={"words": new_words})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 2
        # Phoneme at 510ms falls inside word B -> inherits both singers.
        ph_b = next(p for p in body["phonemes"] if p["label"] == "O")
        assert set(ph_b["singers"]) == {"Blake", "Gwen"}
        # Persisted: GET reflects the edit.
        again = client.get(f"/api/v1/songs/{sid}/words").get_json()
        wb = next(w for w in again["words"] if w["label"] == "B")
        assert set(wb["singers"]) == {"Blake", "Gwen"}

    def test_set_backing(self, client):
        sid = _import(client)
        _seed_session(sid)
        new_words = [
            {"label": "A", "start_ms": 0, "end_ms": 400, "singers": [], "backing": True},
            {"label": "B", "start_ms": 500, "end_ms": 900, "singers": ["Gwen"], "backing": False},
        ]
        body = client.put(f"/api/v1/songs/{sid}/words", json={"words": new_words}).get_json()
        wa = next(w for w in body["words"] if w["label"] == "A")
        assert wa["backing"] is True and wa["singers"] == []

    def test_400_when_words_missing(self, client):
        sid = _import(client)
        _seed_session(sid)
        assert client.put(f"/api/v1/songs/{sid}/words", json={}).status_code == 400

    def test_409_when_no_session(self, client):
        sid = _import(client)  # imported but no session seeded
        assert client.put(f"/api/v1/songs/{sid}/words", json={"words": []}).status_code == 409
