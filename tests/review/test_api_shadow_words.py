"""Tests for GET/POST/DELETE /api/v1/songs/<song_id>/shadow-words
(per-song, per-occurrence Shadow Text lyric tag configuration)."""
from __future__ import annotations


class TestShadowWords:
    SONG = "beef1234cafe0001"

    def test_defaults_to_empty(self, client):
        resp = client.get(f"/api/v1/songs/{self.SONG}/shadow-words")
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == []

    def test_add_occurrence(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/shadow-words",
            json={"word": "Fire", "start_ms": 1000},
        )
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == [{"word": "fire", "start_ms": 1000}]

        listed = client.get(f"/api/v1/songs/{self.SONG}/shadow-words").get_json()
        assert listed["occurrences"] == [{"word": "fire", "start_ms": 1000}]

    def test_add_missing_word_returns_400(self, client):
        resp = client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"start_ms": 1000})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_word"

    def test_add_missing_start_ms_returns_400(self, client):
        resp = client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_start_ms"

    def test_add_duplicate_occurrence_is_idempotent(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire", "start_ms": 1000})
        resp = client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire", "start_ms": 1000})
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == [{"word": "fire", "start_ms": 1000}]

    def test_adding_second_occurrence_of_same_word_keeps_both(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire", "start_ms": 1000})
        resp = client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire", "start_ms": 2000})
        occurrences = resp.get_json()["occurrences"]
        assert {"word": "fire", "start_ms": 1000} in occurrences
        assert {"word": "fire", "start_ms": 2000} in occurrences
        assert len(occurrences) == 2

    def test_remove_only_that_occurrence(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire", "start_ms": 1000})
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire", "start_ms": 2000})
        resp = client.delete(f"/api/v1/songs/{self.SONG}/shadow-words/fire/1000")
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == [{"word": "fire", "start_ms": 2000}]

    def test_remove_unknown_occurrence_returns_404(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/shadow-words/nothere/1000")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"

    def test_preserves_existing_session_fields(self, client):
        from src.review.storage.assignments import load_session, save_full_session

        save_full_session(self.SONG, {"sections": [{"label": "verse"}], "words": []})
        client.post(f"/api/v1/songs/{self.SONG}/shadow-words", json={"word": "fire", "start_ms": 1000})
        session = load_session(self.SONG)
        assert session["sections"] == [{"label": "verse"}]
        assert session["shadow_text_occurrences"] == [{"word": "fire", "start_ms": 1000}]
