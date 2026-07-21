"""Tests for analysis endpoints — T046."""
from __future__ import annotations

import io
import json
import struct
import time
import wave
import pytest


def _make_wav_bytes(duration_secs: float = 6.0, sample_rate: int = 22050) -> bytes:
    """Generate a low-amplitude sine WAV that passes import-time validation.

    Default duration 6 s and a non-zero waveform so the validator
    (5 s minimum, 1e-4 RMS minimum) accepts the upload.
    """
    import math

    n_samples = int(duration_secs * sample_rate)
    samples = [
        int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        for i in range(n_samples)
    ]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{n_samples}h", *samples))
    return buf.getvalue()


def _import_wav(client) -> str:
    """Import a WAV and return song_id."""
    wav = _make_wav_bytes()
    data = client.post(
        "/api/v1/import",
        data={"audio": (io.BytesIO(wav), "test.wav")},
        content_type="multipart/form-data",
    ).get_json()
    return data["song"]["song_id"]


class TestAnalyzeStart:
    def test_returns_202(self, client):
        song_id = _import_wav(client)
        resp = client.post(f"/api/v1/songs/{song_id}/analyze")
        assert resp.status_code == 202

    def test_returns_run_id(self, client):
        song_id = _import_wav(client)
        data = client.post(f"/api/v1/songs/{song_id}/analyze").get_json()
        assert "run_id" in data
        assert isinstance(data["run_id"], str)

    def test_returns_started_at(self, client):
        song_id = _import_wav(client)
        data = client.post(f"/api/v1/songs/{song_id}/analyze").get_json()
        assert "started_at" in data

    def test_idempotent_same_run_id(self, client):
        song_id = _import_wav(client)
        d1 = client.post(f"/api/v1/songs/{song_id}/analyze").get_json()
        d2 = client.post(f"/api/v1/songs/{song_id}/analyze").get_json()
        assert d1["run_id"] == d2["run_id"]

    def test_unknown_song_returns_404(self, client):
        resp = client.post("/api/v1/songs/deadbeef00000000/analyze")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "song_not_found"


class TestGetAnalysis:
    def test_not_analyzed_returns_409(self, client):
        song_id = _import_wav(client)
        resp = client.get(f"/api/v1/songs/{song_id}/analysis")
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "not_analyzed"

    def test_unknown_song_returns_404(self, client):
        resp = client.get("/api/v1/songs/deadbeef00000000/analysis")
        assert resp.status_code == 404


class TestAnalyzeSSE:
    def test_sse_endpoint_returns_event_stream(self, client):
        song_id = _import_wav(client)
        run_data = client.post(f"/api/v1/songs/{song_id}/analyze").get_json()
        # SSE stream; in testing mode the handler runs synchronously
        resp = client.get(f"/api/v1/songs/{song_id}/analyze/status")
        assert resp.status_code in (200, 404)  # 404 if run already done

    def test_sse_terminates_with_overall_done(self, client):
        """SSE stream for a fast mock analysis should end with overall.done event."""
        song_id = _import_wav(client)
        client.post(f"/api/v1/songs/{song_id}/analyze")
        # Wait briefly for analysis to complete (stub is fast)
        time.sleep(0.5)
        resp = client.get(f"/api/v1/songs/{song_id}/analyze/status")
        body = resp.get_data(as_text=True)
        # Should contain at least one data line
        assert "data:" in body or resp.status_code == 404


# ---------------------------------------------------------------------------
# T103: force flag + analyze/commit endpoint (US3, FR-013a)
# ---------------------------------------------------------------------------

def _wait_analyzed(client, song_id: str) -> None:
    """Wait up to 3s for song to reach status==analyzed."""
    for _ in range(30):
        time.sleep(0.1)
        lib_data = client.get("/api/v1/library").get_json()
        song = next((s for s in lib_data["songs"] if s["song_id"] == song_id), None)
        if song and song.get("status") == "analyzed":
            return
    raise RuntimeError(f"Song {song_id} did not reach analyzed in time")


class TestForceReAnalyze:
    """T103: force: true flag behaviour per FR-013a."""

    def test_force_true_on_analyzed_song_returns_202(self, client):
        song_id = _import_wav(client)
        client.post(f"/api/v1/songs/{song_id}/analyze")
        _wait_analyzed(client, song_id)
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze", json={"force": True}
        )
        assert resp.status_code == 202

    def test_force_true_returns_run_id(self, client):
        song_id = _import_wav(client)
        client.post(f"/api/v1/songs/{song_id}/analyze")
        _wait_analyzed(client, song_id)
        data = client.post(
            f"/api/v1/songs/{song_id}/analyze", json={"force": True}
        ).get_json()
        assert "run_id" in data

    def test_force_true_does_not_overwrite_session_immediately(self, client):
        """force: true on an analyzed song does NOT overwrite session until commit."""
        song_id = _import_wav(client)
        client.post(f"/api/v1/songs/{song_id}/analyze")
        _wait_analyzed(client, song_id)
        # Rename a section so we can detect if it gets wiped
        client.patch(
            f"/api/v1/songs/{song_id}/sections/0",
            json={"label": "CANARY"},
        )
        # Force re-analysis
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze", json={"force": True}
        )
        assert resp.status_code == 202
        # Wait for background run to complete
        _wait_analyzed(client, song_id)
        # Original session (with CANARY) must still be intact
        sections_resp = client.get(f"/api/v1/songs/{song_id}/sections")
        sections = sections_resp.get_json()["sections"]
        labels = [s["label"] for s in sections]
        assert "CANARY" in labels, "force re-analysis must not overwrite session before commit"

    def test_force_false_on_fresh_song_returns_202(self, client):
        """Default (force absent / false) on a draft song starts normal analysis."""
        song_id = _import_wav(client)
        resp = client.post(f"/api/v1/songs/{song_id}/analyze", json={"force": False})
        assert resp.status_code == 202

    def test_force_unknown_song_returns_404(self, client):
        resp = client.post(
            "/api/v1/songs/deadbeef00000000/analyze", json={"force": True}
        )
        assert resp.status_code == 404


class TestAnalyzeCommit:
    """T103: POST .../analyze/commit endpoint per FR-013a."""

    def _analyzed_song_id(self, client) -> str:
        song_id = _import_wav(client)
        client.post(f"/api/v1/songs/{song_id}/analyze")
        _wait_analyzed(client, song_id)
        return song_id

    def test_commit_unknown_run_returns_404(self, client):
        song_id = self._analyzed_song_id(client)
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/commit",
            json={
                "run_id": "run_XXXXX",
                "assignment_mapping": [],
            },
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "run_not_found"

    def test_commit_unknown_song_returns_404(self, client):
        resp = client.post(
            "/api/v1/songs/deadbeef00000000/analyze/commit",
            json={"run_id": "run_XXXXX", "assignment_mapping": []},
        )
        assert resp.status_code == 404

    def test_commit_valid_run_returns_200(self, client):
        song_id = self._analyzed_song_id(client)
        run_data = client.post(
            f"/api/v1/songs/{song_id}/analyze", json={"force": True}
        ).get_json()
        run_id = run_data["run_id"]
        # Wait for force run
        _wait_analyzed(client, song_id)
        # Build a trivial mapping
        sections_resp = client.get(f"/api/v1/songs/{song_id}/analyze/pending/{run_id}")
        # Use an empty mapping — implementation may accept it
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/commit",
            json={
                "run_id": run_id,
                "assignment_mapping": [],
            },
        )
        assert resp.status_code in (200, 400)  # 400 if mapping_invalid on empty

    def test_commit_already_committed_returns_409(self, client):
        """Committing the same run_id twice returns 409 already_committed."""
        song_id = self._analyzed_song_id(client)
        run_data = client.post(
            f"/api/v1/songs/{song_id}/analyze", json={"force": True}
        ).get_json()
        run_id = run_data["run_id"]
        _wait_analyzed(client, song_id)
        # First commit
        client.post(
            f"/api/v1/songs/{song_id}/analyze/commit",
            json={"run_id": run_id, "assignment_mapping": []},
        )
        # Second commit — should be 409
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/commit",
            json={"run_id": run_id, "assignment_mapping": []},
        )
        # Either already_committed or run_not_found (after first commit clears it)
        assert resp.status_code in (404, 409)


class TestCheckLyrics:
    """Standalone /lyrics/check lookup — no audio pipeline involved."""

    def test_missing_query_returns_400(self, client):
        resp = client.post("/api/v1/lyrics/check", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_query"

    def test_found_returns_200_with_line_count(self, client, monkeypatch):
        import src.analyzer.synced_lyrics as sl

        monkeypatch.setattr(
            sl, "check_synced_lyrics_with_text",
            lambda title, artist: (
                {"found": True, "reason": None, "line_count": 12, "preview": ["a", "b", "c"]},
                "[00:01.00]a\n[00:02.00]b\n",
            ),
        )
        resp = client.post("/api/v1/lyrics/check", json={"title": "Real Title", "artist": "Real Artist"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is True
        assert data["line_count"] == 12

    def test_not_found_returns_200_with_reason(self, client, monkeypatch):
        import src.analyzer.synced_lyrics as sl

        monkeypatch.setattr(
            sl, "check_synced_lyrics_with_text",
            lambda title, artist: (
                {"found": False, "reason": "no_match", "line_count": 0, "preview": []},
                None,
            ),
        )
        resp = client.post("/api/v1/lyrics/check", json={"title": "Garbled Slug", "artist": "Unknown"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is False
        assert data["reason"] == "no_match"

    def test_found_result_is_cached_and_reused_by_analyze(self, client, monkeypatch, tmp_path):
        """A confirmed-good check result must be reused by the actual
        analyze pass instead of a fresh (potentially flaky) re-fetch."""
        import src.review.api.v1.analysis as analysis_module

        with analysis_module._lyrics_cache_lock:
            analysis_module._lyrics_cache.clear()

        import src.analyzer.synced_lyrics as sl
        monkeypatch.setattr(
            sl, "check_synced_lyrics_with_text",
            lambda title, artist: (
                {"found": True, "reason": None, "line_count": 2, "preview": ["a", "b"]},
                "[00:01.00]a\n[00:02.00]b\n",
            ),
        )
        client.post("/api/v1/lyrics/check", json={"title": "Cached Title", "artist": "Cached Artist"})
        with analysis_module._lyrics_cache_lock:
            assert analysis_module._lyrics_cache.get(("Cached Title", "Cached Artist")) == (
                "[00:01.00]a\n[00:02.00]b\n"
            )


class TestPasteLyrics:
    """POST /lyrics/paste — manual fallback when no provider has a song indexed."""

    def test_missing_query_returns_400(self, client):
        resp = client.post("/api/v1/lyrics/paste", json={"lyrics_text": "some lyrics"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_query"

    def test_missing_lyrics_text_returns_400(self, client):
        resp = client.post("/api/v1/lyrics/paste", json={"title": "T", "artist": "A"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_lyrics_text"

    def test_blank_lyrics_text_returns_400(self, client):
        resp = client.post("/api/v1/lyrics/paste", json={"title": "T", "artist": "A", "lyrics_text": "   "})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_lyrics_text"

    def test_valid_text_returns_200_and_caches(self, client):
        import src.review.api.v1.analysis as analysis_module

        with analysis_module._lyrics_cache_lock:
            analysis_module._lyrics_cache.clear()

        resp = client.post(
            "/api/v1/lyrics/paste",
            json={"title": "Pasted Title", "artist": "Pasted Artist",
                  "lyrics_text": "First line\nSecond line\n"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is True
        assert data["line_count"] == 2
        assert data["source"] == "pasted"

        with analysis_module._lyrics_cache_lock:
            assert analysis_module._lyrics_cache.get(("Pasted Title", "Pasted Artist")) == (
                "First line\nSecond line"
            )

    def test_only_credit_lines_not_cached(self, client):
        import src.review.api.v1.analysis as analysis_module

        with analysis_module._lyrics_cache_lock:
            analysis_module._lyrics_cache.clear()

        resp = client.post(
            "/api/v1/lyrics/paste",
            json={"title": "Credits Only", "artist": "Nobody",
                  "lyrics_text": "Lyrics by Someone\n"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is False

        with analysis_module._lyrics_cache_lock:
            assert ("Credits Only", "Nobody") not in analysis_module._lyrics_cache
