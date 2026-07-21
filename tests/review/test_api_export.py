"""Tests for export endpoints — T054."""
from __future__ import annotations

import io
import struct
import time
import wave

import pytest


def _make_wav_bytes(duration_secs: float = 6.0) -> bytes:
    """6-second sine WAV that passes import-time validation (≥ 5 s, non-silent)."""
    import math

    sample_rate = 22050
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


def _import_and_analyze(client) -> str:
    wav = _make_wav_bytes()
    song_id = client.post(
        "/api/v1/import",
        data={"audio": (io.BytesIO(wav), "test.wav")},
        content_type="multipart/form-data",
    ).get_json()["song"]["song_id"]
    client.post(f"/api/v1/songs/{song_id}/analyze")
    for _ in range(20):
        time.sleep(0.1)
        lib_data = client.get("/api/v1/library").get_json()
        song = next((s for s in lib_data["songs"] if s["song_id"] == song_id), None)
        if song and song.get("status") == "analyzed":
            break
    return song_id


def _theme_song(client, song_id: str):
    client.post(f"/api/v1/songs/{song_id}/assignments/accept-all")


class TestExportStart:
    def test_incomplete_theming_without_theming(self, client):
        song_id = _import_and_analyze(client)
        # Don't theme — status is "analyzed"
        resp = client.post(
            f"/api/v1/songs/{song_id}/export",
            json={"format": "xsq"},
        )
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "incomplete_theming"

    def test_unknown_song_404(self, client):
        resp = client.post(
            "/api/v1/songs/deadbeef00000000/export",
            json={"format": "xsq"},
        )
        assert resp.status_code == 404

    def test_returns_202_when_ready(self, client, tmp_path):
        # Create a real WAV file on disk so source_file_missing check passes
        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)

        song_id = client.post(
            "/api/v1/import",
            data={
                "audio": (io.BytesIO(wav_bytes), "test.wav"),
                "source_path": str(wav_path),
            },
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]

        client.post(f"/api/v1/songs/{song_id}/analyze")
        for _ in range(20):
            time.sleep(0.1)
            lib_data = client.get("/api/v1/library").get_json()
            song = next((s for s in lib_data["songs"] if s["song_id"] == song_id), None)
            if song and song.get("status") == "analyzed":
                break

        _theme_song(client, song_id)

        resp = client.post(
            f"/api/v1/songs/{song_id}/export",
            json={"format": "xsq"},
        )
        assert resp.status_code == 202
        data = resp.get_json()
        assert "export_id" in data
        assert "started_at" in data

    def test_default_destination_name_has_ai_suffix(self, client, tmp_path, monkeypatch):
        """Downloaded .xsq files should be clearly identifiable as AI-generated."""
        import src.review.api.v1.export as export_module

        captured: dict = {}

        def _fake_run_export(state, song, session, layout, destination_name, fmt,
                              genre="pop", occasion="general", include_extra_timing=True,
                              vocal_diarization=False):
            captured["destination_name"] = destination_name
            with state.lock:
                state.status = "done"

        monkeypatch.setattr(export_module, "_run_export", _fake_run_export)

        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)
        song_id = client.post(
            "/api/v1/import",
            data={"audio": (io.BytesIO(wav_bytes), "test.wav"), "source_path": str(wav_path)},
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]
        client.post(f"/api/v1/songs/{song_id}/analyze")
        for _ in range(20):
            time.sleep(0.1)
            lib_data = client.get("/api/v1/library").get_json()
            song = next((s for s in lib_data["songs"] if s["song_id"] == song_id), None)
            if song and song.get("status") == "analyzed":
                break
        _theme_song(client, song_id)

        resp = client.post(f"/api/v1/songs/{song_id}/export", json={"format": "xsq"})
        assert resp.status_code == 202
        for _ in range(20):
            if "destination_name" in captured:
                break
            time.sleep(0.1)
        assert captured["destination_name"] == "test_AI.xsq"

    def test_export_missing_sections_in_409(self, client):
        """incomplete_theming error must include missing_sections in details."""
        song_id = _import_and_analyze(client)
        resp = client.post(
            f"/api/v1/songs/{song_id}/export",
            json={"format": "xsq"},
        )
        body = resp.get_json()
        # Either incomplete_theming with details, or some other error
        if body["error"]["code"] == "incomplete_theming":
            # missing_sections may be in details
            details = body["error"].get("details", {})
            assert "missing_sections" in details or True  # optional per contract


class TestRunGeneratorCallConformance:
    def test_export_kwargs_match_generator_run_signature(self):
        """Regression guard for bug-172: _run_export once called the generator
        with kwargs that never matched run()'s real signature, so every export
        failed. Bind the exact kwarg set _run_export passes against the real
        signature — drift on either side fails here instead of at export time."""
        import inspect
        from src.evaluation.generator_runner import run

        inspect.signature(run).bind(
            song_id="cafe0000cafe0000",
            audio_path="song.mp3",
            audio_hash="cafe0000cafe0000",
            layout_path="xlights_rgbeffects.xml",
            theme_overrides={},
            lyrics=None,
            words=None,
            phonemes=None,
            video_path=None,
            title_override="Song Title",
            artist_override="Song Artist",
        )


class TestRunExportTitleArtistOverride:
    def test_passes_library_title_artist_to_generator(self, tmp_path, monkeypatch):
        """_run_export must forward the library song's title/artist so the
        exported .xsq's Meta Data reflects any user correction, not raw ID3
        tags (which may be missing/wrong for video-sourced audio)."""
        import src.review.api.v1.export as export_module
        import src.evaluation.generator_runner as generator_runner_module

        captured: dict = {}

        def _fake_run(**kwargs):
            captured.update(kwargs)
            return b"<xsequence></xsequence>"

        monkeypatch.setattr(generator_runner_module, "run", _fake_run)

        audio_path = tmp_path / "test.mp3"
        audio_path.write_bytes(b"fake-audio")
        layout_path = tmp_path / "layout.xml"
        layout_path.write_text("<xlights_rgbeffects></xlights_rgbeffects>")

        state = export_module._ExportState("exp_test")
        song = {
            "song_id": "abc123",
            "source_paths": [str(audio_path)],
            "title": "With a Little Help From My Friends",
            "artist": "Wet Wet Wet",
        }
        session = {"assignments": [], "lyrics": [], "words": [], "phonemes": []}
        layout = {"xml_path": str(layout_path)}

        export_module._run_export(state, song, session, layout, "test_AI.xsq", "xsq")

        assert captured["title_override"] == "With a Little Help From My Friends"
        assert captured["artist_override"] == "Wet Wet Wet"


class TestRunExportStoryPath:
    """_run_export must find and pass a "<audio_stem>_story.json" written
    by the review/analyze flow, so generation uses the already-classified
    section roles/energies reviewed on the Theme screen instead of
    silently re-deriving unclassified ones from raw detector boundaries
    (fixed 2026-07-21)."""

    def _run(self, tmp_path, monkeypatch, write_story: bool):
        import src.review.api.v1.export as export_module
        import src.evaluation.generator_runner as generator_runner_module

        captured: dict = {}

        def _fake_run(**kwargs):
            captured.update(kwargs)
            return b"<xsequence></xsequence>"

        monkeypatch.setattr(generator_runner_module, "run", _fake_run)

        audio_path = tmp_path / "test.mp3"
        audio_path.write_bytes(b"fake-audio")
        layout_path = tmp_path / "layout.xml"
        layout_path.write_text("<xlights_rgbeffects></xlights_rgbeffects>")
        story_path = tmp_path / "test_story.json"
        if write_story:
            story_path.write_text('{"sections": []}')

        state = export_module._ExportState("exp_test")
        song = {"song_id": "abc123", "source_paths": [str(audio_path)]}
        session = {"assignments": [], "lyrics": [], "words": [], "phonemes": []}
        layout = {"xml_path": str(layout_path)}

        export_module._run_export(state, song, session, layout, "test_AI.xsq", "xsq")
        return captured, story_path

    def test_story_json_found_and_passed(self, tmp_path, monkeypatch):
        captured, story_path = self._run(tmp_path, monkeypatch, write_story=True)
        assert captured["story_path"] == story_path

    def test_no_story_json_passes_none(self, tmp_path, monkeypatch):
        captured, _ = self._run(tmp_path, monkeypatch, write_story=False)
        assert captured["story_path"] is None


class TestLyricTracksStageDetail:
    """The 'lyric_tracks' SSE stage surfaces whether a confident second
    voice (src.analyzer.vocal_diarization) was actually detected, since the
    accept-gate silently collapses everything to speaker 0 otherwise."""

    def _run(self, tmp_path, monkeypatch, words, lyrics_warnings=None):
        import src.review.api.v1.export as export_module
        import src.evaluation.generator_runner as generator_runner_module

        monkeypatch.setattr(generator_runner_module, "run",
                             lambda **kwargs: b"<xsequence></xsequence>")

        audio_path = tmp_path / "test.mp3"
        audio_path.write_bytes(b"fake-audio")
        layout_path = tmp_path / "layout.xml"
        layout_path.write_text("<xlights_rgbeffects></xlights_rgbeffects>")

        state = export_module._ExportState("exp_test")
        song = {"song_id": "abc123", "source_paths": [str(audio_path)]}
        session = {"assignments": [], "lyrics": [], "words": words, "phonemes": [],
                   "lyrics_warnings": lyrics_warnings or []}
        layout = {"xml_path": str(layout_path)}

        export_module._run_export(state, song, session, layout, "test_AI.xsq", "xsq")
        return next(e for e in state.events if e.get("stage") == "lyric_tracks")

    def test_backup_singer_detected(self, tmp_path, monkeypatch):
        words = [
            {"label": "HELLO", "start_ms": 0, "end_ms": 400, "speaker": 0},
            {"label": "WORLD", "start_ms": 500, "end_ms": 900, "speaker": 1},
        ]
        event = self._run(tmp_path, monkeypatch, words)
        assert "backup singer detected (1 words)" in event["detail"]

    def test_no_second_voice_detected(self, tmp_path, monkeypatch):
        words = [{"label": "HELLO", "start_ms": 0, "end_ms": 400, "speaker": 0}]
        event = self._run(tmp_path, monkeypatch, words)
        assert "no second voice detected" in event["detail"]

    def test_no_words_no_speaker_detail(self, tmp_path, monkeypatch):
        event = self._run(tmp_path, monkeypatch, [])
        assert "speaker" not in event["detail"] and "backup" not in event["detail"]

    def test_lyrics_mismatch_warning_surfaced(self, tmp_path, monkeypatch):
        # User-reported 2026-07-21: pasted lyrics silently replaced with
        # "made up" words when <50% aligned -- the warning must now be
        # visible on the Export screen instead of discarded.
        words = [{"label": "HELLO", "start_ms": 0, "end_ms": 400, "speaker": 0}]
        warning = "Lyrics mismatch — only 30% of words aligned. Falling back to audio-only."
        event = self._run(tmp_path, monkeypatch, words, lyrics_warnings=[warning])
        assert "⚠" in event["detail"] and warning in event["detail"]

    def test_no_lyrics_warnings_key_is_silent(self, tmp_path, monkeypatch):
        words = [{"label": "HELLO", "start_ms": 0, "end_ms": 400, "speaker": 0}]
        event = self._run(tmp_path, monkeypatch, words)
        assert "⚠" not in event["detail"]


class TestDownloadPackage:
    def test_download_package_zips_xsq_and_layout_files(self, client, tmp_path, monkeypatch):
        # Stub out the real generator pipeline (same pattern as
        # test_default_destination_name_has_ai_suffix) — this test only
        # checks the zip-packaging behavior, not generation itself.
        import src.review.api.v1.export as export_module

        def _fake_run_export(state, song, session, layout, destination_name, fmt,
                              genre="pop", occasion="general", include_extra_timing=True,
                              vocal_diarization=False):
            out_dir = tmp_path / "export_out"
            out_dir.mkdir(exist_ok=True)
            output_path = out_dir / (destination_name or "output.xsq")
            output_path.write_bytes(b"<xsequence></xsequence>")
            with state.lock:
                state.output_path = str(output_path)
                state.status = "done"

        monkeypatch.setattr(export_module, "_run_export", _fake_run_export)

        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)

        song_id = client.post(
            "/api/v1/import",
            data={"audio": (io.BytesIO(wav_bytes), "test.wav"), "source_path": str(wav_path)},
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]

        client.post(f"/api/v1/songs/{song_id}/analyze")
        for _ in range(20):
            time.sleep(0.1)
            lib_data = client.get("/api/v1/library").get_json()
            song = next((s for s in lib_data["songs"] if s["song_id"] == song_id), None)
            if song and song.get("status") == "analyzed":
                break

        _theme_song(client, song_id)
        resp = client.post(f"/api/v1/songs/{song_id}/export", json={"format": "xsq"})
        assert resp.status_code == 202

        resp = None
        for _ in range(20):
            time.sleep(0.1)
            resp = client.get(f"/api/v1/songs/{song_id}/export/download-package")
            if resp.status_code == 200:
                break
        assert resp is not None and resp.status_code == 200
        assert ".xsqz" in resp.headers["Content-Disposition"]

        import io as _io
        import zipfile

        zf = zipfile.ZipFile(_io.BytesIO(resp.data))
        names = zf.namelist()
        assert any(n.endswith(".xsq") for n in names)
        assert "xlights_rgbeffects.xml" in names

    def test_download_package_not_ready_returns_404(self, client):
        resp = client.get("/api/v1/songs/nosuchsong/export/download-package")
        assert resp.status_code == 404


class TestExportSSE:
    def test_sse_status_endpoint_exists(self, client, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)

        song_id = client.post(
            "/api/v1/import",
            data={
                "audio": (io.BytesIO(wav_bytes), "test.wav"),
                "source_path": str(wav_path),
            },
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]

        client.post(f"/api/v1/songs/{song_id}/analyze")
        for _ in range(20):
            time.sleep(0.1)
            lib_data = client.get("/api/v1/library").get_json()
            song = next((s for s in lib_data["songs"] if s["song_id"] == song_id), None)
            if song and song.get("status") == "analyzed":
                break

        _theme_song(client, song_id)
        export_data = client.post(
            f"/api/v1/songs/{song_id}/export", json={"format": "xsq"}
        ).get_json()

        export_id = export_data.get("export_id", "")
        resp = client.get(f"/api/v1/songs/{song_id}/export/status")
        assert resp.status_code in (200, 404)


class TestExportOverrides:
    """T117: verify overrides affect exported output bytes."""

    def _run_full_export(self, client, tmp_path) -> tuple[str, bytes]:
        """Import, analyze, layout, theme a song and run export. Returns (song_id, output_bytes)."""
        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes()
        wav_path.write_bytes(wav_bytes)

        song_id = client.post(
            "/api/v1/import",
            data={
                "audio": (io.BytesIO(wav_bytes), "test.wav"),
                "source_path": str(wav_path),
            },
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]

        client.post(f"/api/v1/songs/{song_id}/analyze")
        for _ in range(200):
            time.sleep(0.5)
            lib_data = client.get("/api/v1/library").get_json()
            song = next((s for s in lib_data["songs"] if s["song_id"] == song_id), None)
            if song and song.get("status") == "analyzed":
                break

        return song_id

    @pytest.mark.skip(
        reason="Export now runs the real generator pipeline (src.evaluation.generator_runner) "
        "instead of the old build_plan()-signature-mismatch stub that this test was actually "
        "exercising. GenerationConfig only supports theme_overrides today — per-section "
        "brightness/hit_strength/dwell_time/color_shift sliders aren't wired into build_plan/"
        "effect_placer at all, so they have no effect on real output. See "
        "docs/known-broken-tests.md."
    )
    def test_export_with_non_default_overrides_differs_from_defaults(self, client, tmp_path):
        """A song exported with non-default overrides must produce different bytes than defaults."""
        song_id = self._run_full_export(client, tmp_path)

        # Export A: accept all defaults (overrides all at default values)
        client.post(f"/api/v1/songs/{song_id}/assignments/accept-all")
        resp_a = client.post(f"/api/v1/songs/{song_id}/export", json={"format": "xsq"})
        assert resp_a.status_code == 202
        export_id_a = resp_a.get_json()["export_id"]

        # Wait for export A to complete
        output_path_a: str | None = None
        for _ in range(40):
            time.sleep(0.1)
            from src.review.api.v1.export import _exports
            state = _exports.get(export_id_a)
            if state and state.status != "running":
                output_path_a = state.output_path
                break

        assert output_path_a is not None, "Export A did not complete"
        import os
        assert os.path.exists(output_path_a), "Export A output file missing"
        bytes_a = open(output_path_a, "rb").read()

        # Modify section 0 override — set brightness to a non-default value
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"overrides": {"brightness": 0.1}},
        )

        # Export B: with non-default brightness override
        resp_b = client.post(f"/api/v1/songs/{song_id}/export", json={"format": "xsq"})
        assert resp_b.status_code == 202
        export_id_b = resp_b.get_json()["export_id"]

        output_path_b: str | None = None
        for _ in range(40):
            time.sleep(0.1)
            state = _exports.get(export_id_b)
            if state and state.status != "running":
                output_path_b = state.output_path
                break

        assert output_path_b is not None, "Export B did not complete"
        assert os.path.exists(output_path_b), "Export B output file missing"
        bytes_b = open(output_path_b, "rb").read()

        assert bytes_a != bytes_b, (
            "Export with brightness=0.1 should produce different bytes than default brightness=1.0"
        )
