"""Tests for assignment endpoints — T050."""
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
    run_id = client.post(f"/api/v1/songs/{song_id}/analyze").get_json()["run_id"]
    # A run only persists a session (and the song only becomes 'analyzed')
    # once committed — mirror the client flow: poll commit until the run
    # result is available (404 'Run result not yet available' while running).
    for _ in range(100):
        time.sleep(0.1)
        resp = client.post(
            f"/api/v1/songs/{song_id}/analyze/commit", json={"run_id": run_id},
        )
        if resp.status_code == 200:
            break
    return song_id


class TestGetAssignments:
    def test_unknown_song_404(self, client):
        resp = client.get("/api/v1/songs/deadbeef00000000/assignments")
        assert resp.status_code == 404

    def test_draft_song_409(self, client):
        wav = _make_wav_bytes()
        song_id = client.post(
            "/api/v1/import",
            data={"audio": (io.BytesIO(wav), "test.wav")},
            content_type="multipart/form-data",
        ).get_json()["song"]["song_id"]
        resp = client.get(f"/api/v1/songs/{song_id}/assignments")
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "not_analyzed"

    def test_returns_assignments_list(self, client):
        song_id = _import_and_analyze(client)
        data = client.get(f"/api/v1/songs/{song_id}/assignments").get_json()
        assert "assignments" in data
        assert isinstance(data["assignments"], list)
        assert len(data["assignments"]) >= 1

    def test_song_status_present(self, client):
        song_id = _import_and_analyze(client)
        data = client.get(f"/api/v1/songs/{song_id}/assignments").get_json()
        assert "song_status" in data

    def test_assignment_fields(self, client):
        song_id = _import_and_analyze(client)
        data = client.get(f"/api/v1/songs/{song_id}/assignments").get_json()
        for a in data["assignments"]:
            assert "section_index" in a
            assert "theme_id" in a
            assert "overrides" in a
            assert "user_confirmed" in a


class TestPutAssignment:
    def test_put_assignment_200(self, client):
        song_id = _import_and_analyze(client)
        resp = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "festive-flash"},
        )
        assert resp.status_code == 200

    def test_put_sets_user_confirmed(self, client):
        song_id = _import_and_analyze(client)
        data = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "festive-flash"},
        ).get_json()
        assert data["assignment"]["user_confirmed"] is True

    def test_theme_change_resets_overrides(self, client):
        """FR-032a: changing theme_id resets overrides to defaults."""
        song_id = _import_and_analyze(client)
        # First set custom override
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "festive-flash", "overrides": {"brightness": 0.3}},
        )
        # Now change theme — overrides should reset
        data = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "warm-glow"},
        ).get_json()
        assert data["assignment"]["overrides"]["brightness"] == 1.0

    def test_unknown_section_404(self, client):
        song_id = _import_and_analyze(client)
        resp = client.put(
            f"/api/v1/songs/{song_id}/assignments/999",
            json={"theme_id": "festive-flash"},
        )
        assert resp.status_code == 404

    def test_unknown_theme_404(self, client):
        song_id = _import_and_analyze(client)
        resp = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "nonexistent-theme-id"},
        )
        assert resp.status_code == 404


class TestPutAssignmentOverrides:
    """Regression tests for partial overrides bodies — T115."""

    def test_partial_overrides_only_updates_specified_fields(self, client):
        """PUT with only overrides (no theme_id) patches only the given fields."""
        song_id = _import_and_analyze(client)
        # First assign a theme so the section has a known state
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "warm-glow"},
        )
        # Now send partial override — only brightness
        data = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"overrides": {"brightness": 0.5}},
        ).get_json()
        assert data["assignment"]["overrides"]["brightness"] == 0.5
        # Other fields unchanged from defaults
        assert data["assignment"]["overrides"]["dwell_time"] == 1.0
        assert data["assignment"]["overrides"]["color_shift"] == 0.0

    def test_all_four_override_fields_accepted(self, client):
        """PUT with all four override fields persists all values."""
        song_id = _import_and_analyze(client)
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "warm-glow"},
        )
        data = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"overrides": {"brightness": 0.5, "hit_strength": 1.5, "dwell_time": 0.8, "color_shift": 0.3}},
        ).get_json()
        ov = data["assignment"]["overrides"]
        assert ov["brightness"] == 0.5
        assert ov["hit_strength"] == 1.5
        assert ov["dwell_time"] == 0.8
        assert ov["color_shift"] == 0.3

    def test_theme_change_then_override_uses_defaults_as_base(self, client):
        """FR-032a: after theme change resets overrides, a subsequent PUT patches from defaults."""
        song_id = _import_and_analyze(client)
        # Set custom overrides on initial theme
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "warm-glow", "overrides": {"brightness": 0.2}},
        )
        # Change theme — overrides reset to defaults
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "festive-flash"},
        )
        # Now patch a single field — others should be at defaults, not the old 0.2
        data = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"overrides": {"color_shift": 0.5}},
        ).get_json()
        ov = data["assignment"]["overrides"]
        assert ov["brightness"] == 1.0   # reset to default, not 0.2
        assert ov["color_shift"] == 0.5  # new value applied

    def test_override_with_theme_change_same_request_resets_first(self, client):
        """If theme_id and overrides appear together, overrides from this request
        are applied on top of the reset defaults — not the prior values."""
        song_id = _import_and_analyze(client)
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "warm-glow", "overrides": {"brightness": 0.1}},
        )
        # Change theme and also set brightness in the same request
        data = client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": "festive-flash", "overrides": {"brightness": 0.7}},
        ).get_json()
        ov = data["assignment"]["overrides"]
        # brightness was reset then patched to 0.7 (not leftover 0.1)
        assert ov["brightness"] == 0.7
        # other fields at defaults
        assert ov["dwell_time"] == 1.0


class TestAcceptAll:
    def test_accept_all_flips_to_themed(self, client):
        song_id = _import_and_analyze(client)
        data = client.post(
            f"/api/v1/songs/{song_id}/assignments/accept-all"
        ).get_json()
        assert data["song_status"] == "themed"

    def test_accept_all_confirmed_count(self, client):
        song_id = _import_and_analyze(client)
        # First get section count
        sections = client.get(f"/api/v1/songs/{song_id}/sections").get_json()["sections"]
        data = client.post(
            f"/api/v1/songs/{song_id}/assignments/accept-all"
        ).get_json()
        assert data["confirmed_count"] == len(sections)


class TestResetDefaults:
    def test_reset_discards_manual_pick_and_confirmation(self, client):
        song_id = _import_and_analyze(client)
        themes = client.get("/api/v1/themes").get_json()["themes"]
        # Pick a theme other than whatever section 0 already has, so the
        # override is a real change.
        current = client.get(f"/api/v1/songs/{song_id}/assignments").get_json()
        current_theme_id = current["assignments"][0]["theme_id"]
        other_theme_id = next(
            t["theme_id"] for t in themes if t["theme_id"] != current_theme_id
        )
        client.put(
            f"/api/v1/songs/{song_id}/assignments/0",
            json={"theme_id": other_theme_id},
        )
        client.post(f"/api/v1/songs/{song_id}/assignments/accept-all")

        data = client.post(
            f"/api/v1/songs/{song_id}/assignments/reset-defaults"
        ).get_json()

        assert data["song_status"] == "analyzed"
        assert all(not a["user_confirmed"] for a in data["assignments"])

    def test_reset_flips_status_back_to_analyzed(self, client):
        song_id = _import_and_analyze(client)
        client.post(f"/api/v1/songs/{song_id}/assignments/accept-all")

        client.post(f"/api/v1/songs/{song_id}/assignments/reset-defaults")

        lib = client.get("/api/v1/library").get_json()
        song = next(s for s in lib["songs"] if s["song_id"] == song_id)
        assert song["status"] == "analyzed"

    def test_reset_applies_to_all_sections_not_just_unconfirmed(self, client):
        # User decision (2026-07-18): reset discards EVERY section's manual
        # pick, including ones already confirmed -- not a partial reset.
        song_id = _import_and_analyze(client)
        sections = client.get(f"/api/v1/songs/{song_id}/sections").get_json()["sections"]
        client.post(f"/api/v1/songs/{song_id}/assignments/accept-all")

        data = client.post(
            f"/api/v1/songs/{song_id}/assignments/reset-defaults"
        ).get_json()

        assert len(data["assignments"]) == len(sections)
        assert all(not a["user_confirmed"] for a in data["assignments"])
