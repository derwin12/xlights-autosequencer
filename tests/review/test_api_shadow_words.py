"""Tests for GET/POST/DELETE /api/v1/songs/<song_id>/shadow-words
(per-song Shadow Text lyric-word tag configuration)."""
from __future__ import annotations


class TestShadowWords:
    SONG = "beef1234cafe0001"

    def test_defaults_to_empty(self, client):
        resp = client.get(f"/api/v1/songs/{self.SONG}/shadow-words")
        assert resp.status_code == 200
        assert resp.get_json()["words"] == []

    def test_add_word(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/shadow-words",
            json={"word": "Fire"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["words"] == ["fire"]

        listed = client.get(f"/api/v1/songs/{self.SONG}/shadow-words").get_json()
        assert listed["words"] == ["fire"]

    def test_add_missing_word_returns_400(self, client):
        resp = client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_word"

    def test_add_duplicate_word_is_idempotent(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire"})
        resp = client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire"})
        assert resp.status_code == 200
        assert resp.get_json()["words"] == ["fire"]

    def test_remove_word(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire"})
        resp = client.delete(f"/api/v1/songs/{self.SONG}/shadow-words/fire")
        assert resp.status_code == 200
        assert resp.get_json()["words"] == []

    def test_remove_unknown_word_returns_404(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/shadow-words/nothere")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"

    def test_preserves_existing_session_fields(self, client):
        from src.review.storage.assignments import load_session, save_full_session

        save_full_session(self.SONG, {"sections": [{"label": "verse"}], "words": []})
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire"})
        session = load_session(self.SONG)
        assert session["sections"] == [{"label": "verse"}]
        assert session["shadow_text_words"] == ["fire"]
