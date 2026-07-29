"""Tests for GET/POST/DELETE /api/v1/songs/<song_id>/moving-head-keywords
(per-song Moving Head lyric-keyword trigger configuration)."""
from __future__ import annotations


class TestMovingHeadKeywords:
    SONG = "beef1234cafe0000"

    def test_defaults_to_shake_spin_bounce(self, client):
        resp = client.get(f"/api/v1/songs/{self.SONG}/moving-head-keywords")
        assert resp.status_code == 200
        assert resp.get_json()["keywords"] == {"shake": "shake", "spin": "spin", "bounce": "bounce"}

    def test_add_custom_word_with_valid_motion(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/moving-head-keywords",
            json={"word": "Explode", "motion": "bounce"},
        )
        assert resp.status_code == 200
        keywords = resp.get_json()["keywords"]
        assert keywords["explode"] == "bounce"
        # Built-ins survive the addition.
        assert keywords["shake"] == "shake"

        listed = client.get(f"/api/v1/songs/{self.SONG}/moving-head-keywords").get_json()
        assert listed["keywords"]["explode"] == "bounce"

    def test_add_custom_word_with_flash_motion(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/moving-head-keywords",
            json={"word": "sky", "motion": "flash"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["keywords"]["sky"] == "flash"

    def test_add_rejects_invalid_motion(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/moving-head-keywords",
            json={"word": "explode", "motion": "wiggle"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_motion"

    def test_add_missing_word_returns_400(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/moving-head-keywords",
            json={"motion": "shake"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_word"

    def test_remove_disables_a_built_in(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/moving-head-keywords/shake")
        assert resp.status_code == 200
        keywords = resp.get_json()["keywords"]
        assert "shake" not in keywords
        assert keywords == {"spin": "spin", "bounce": "bounce"}

    def test_remove_unknown_word_returns_404(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/moving-head-keywords/nothere")
        assert resp.status_code == 404

    def test_add_then_remove_custom_word(self, client):
        client.post(
            f"/api/v1/songs/{self.SONG}/moving-head-keywords",
            json={"word": "jump", "motion": "spin"},
        )
        resp = client.delete(f"/api/v1/songs/{self.SONG}/moving-head-keywords/jump")
        assert resp.status_code == 200
        assert "jump" not in resp.get_json()["keywords"]

    def test_preserves_existing_session_fields(self, client):
        from src.review.storage.assignments import load_session, save_full_session

        save_full_session(self.SONG, {"sections": [{"label": "verse"}], "words": []})
        client.post(
            f"/api/v1/songs/{self.SONG}/moving-head-keywords",
            json={"word": "explode", "motion": "bounce"},
        )
        session = load_session(self.SONG)
        assert session["sections"] == [{"label": "verse"}]
        assert session["moving_head_keyword_motions"]["explode"] == "bounce"
