"""Tests for GET/POST /api/v1/images (global image library for Pictures effects)."""
from __future__ import annotations

import io


class TestUploadImage:
    def test_returns_201_on_new_image(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"gif-bytes"), "snowman.gif"), "tag": "snowman"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201

    def test_entry_has_tag_and_filename(self, client):
        data = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"gif-bytes"), "snowman.gif"), "tag": "snowman"},
            content_type="multipart/form-data",
        ).get_json()
        assert data["image"]["tag"] == "snowman"
        assert data["image"]["filename"] == "snowman.gif"

    def test_missing_file_returns_400(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"tag": "snowman"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_file"

    def test_missing_tag_returns_400(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"gif-bytes"), "snowman.gif")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_tag"

    def test_unsupported_extension_returns_400(self, client):
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"not an image"), "notes.txt"), "tag": "notes"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "unsupported_format"


class TestReplaceImage:
    """PUT /api/v1/images/<id> overwrites an existing entry's bytes in
    place, keeping its id -- unlike POST, which always creates a new,
    separate entry."""

    def _upload(self, client, tag: str, filename: str = "a.gif", data: bytes = b"original") -> dict:
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(data), filename), "tag": tag},
            content_type="multipart/form-data",
        )
        return resp.get_json()["image"]

    def test_returns_200_and_updated_entry(self, client):
        entry = self._upload(client, "fool", "fool.png", b"old bytes")
        resp = client.put(
            f"/api/v1/images/{entry['id']}",
            data={"image": (io.BytesIO(b"new bytes"), "fool_v2.png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["replaced"] is True
        assert body["image"]["id"] == entry["id"]
        assert body["image"]["filename"] == "fool_v2.png"

    def test_library_entry_count_unchanged(self, client):
        entry = self._upload(client, "fool")
        client.put(
            f"/api/v1/images/{entry['id']}",
            data={"image": (io.BytesIO(b"new bytes"), "fool.png")},
            content_type="multipart/form-data",
        )
        assert len(client.get("/api/v1/images").get_json()["images"]) == 1

    def test_unknown_id_returns_404(self, client):
        resp = client.put(
            "/api/v1/images/does-not-exist",
            data={"image": (io.BytesIO(b"data"), "x.png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "image_not_found"

    def test_missing_file_returns_400(self, client):
        entry = self._upload(client, "fool")
        resp = client.put(f"/api/v1/images/{entry['id']}", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_file"

    def test_unsupported_extension_returns_400(self, client):
        entry = self._upload(client, "fool")
        resp = client.put(
            f"/api/v1/images/{entry['id']}",
            data={"image": (io.BytesIO(b"data"), "notes.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "unsupported_format"


class TestListImages:
    def test_empty_library_returns_empty_list(self, client):
        resp = client.get("/api/v1/images")
        assert resp.status_code == 200
        assert resp.get_json()["images"] == []

    def test_uploaded_images_appear_in_list(self, client):
        client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"a"), "a.gif"), "tag": "snowman"},
            content_type="multipart/form-data",
        )
        client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"b"), "b.png"), "tag": "rocker"},
            content_type="multipart/form-data",
        )
        data = client.get("/api/v1/images").get_json()
        tags = {img["tag"] for img in data["images"]}
        assert tags == {"snowman", "rocker"}


class TestIgnoredImages:
    SONG = "cafe0123deadbeef"

    def test_empty_by_default(self, client):
        resp = client.get(f"/api/v1/songs/{self.SONG}/ignored-images")
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == []

    def test_ignore_adds_occurrence_word_lowercased(self, client):
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/ignored-images",
            json={"word": "Snowman", "start_ms": 1000},
        )
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == [{"word": "snowman", "start_ms": 1000}]
        listed = client.get(f"/api/v1/songs/{self.SONG}/ignored-images").get_json()
        assert listed["occurrences"] == [{"word": "snowman", "start_ms": 1000}]

    def test_ignore_is_idempotent(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman", "start_ms": 1000})
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman", "start_ms": 1000})
        listed = client.get(f"/api/v1/songs/{self.SONG}/ignored-images").get_json()
        assert listed["occurrences"] == [{"word": "snowman", "start_ms": 1000}]

    def test_ignoring_one_occurrence_leaves_other_occurrences_of_same_word(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman", "start_ms": 1000})
        resp = client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman", "start_ms": 2000})
        occurrences = resp.get_json()["occurrences"]
        assert {"word": "snowman", "start_ms": 1000} in occurrences
        assert {"word": "snowman", "start_ms": 2000} in occurrences
        assert len(occurrences) == 2

    def test_missing_word_returns_400(self, client):
        resp = client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"start_ms": 1000})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_word"

    def test_missing_start_ms_returns_400(self, client):
        resp = client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_start_ms"

    def test_restore_removes_only_that_occurrence(self, client):
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman", "start_ms": 1000})
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman", "start_ms": 2000})
        resp = client.delete(f"/api/v1/songs/{self.SONG}/ignored-images/snowman/1000")
        assert resp.status_code == 200
        listed = client.get(f"/api/v1/songs/{self.SONG}/ignored-images").get_json()
        assert listed["occurrences"] == [{"word": "snowman", "start_ms": 2000}]

    def test_restore_unknown_occurrence_returns_404(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/ignored-images/nothere/1000")
        assert resp.status_code == 404

    def test_ignore_preserves_existing_session_fields(self, client):
        from src.review.storage.assignments import load_session, save_full_session

        save_full_session(self.SONG, {"sections": [{"label": "verse"}], "words": []})
        client.post(f"/api/v1/songs/{self.SONG}/ignored-images", json={"word": "snowman", "start_ms": 1000})
        session = load_session(self.SONG)
        assert session["sections"] == [{"label": "verse"}]
        assert session["ignored_image_occurrences"] == [{"word": "snowman", "start_ms": 1000}]

    def test_ignore_clears_a_standing_override_on_the_same_occurrence(self, client):
        # A per-occurrence override always wins over an ignore at export
        # time (image_catalog.suggest_images_for_words), so unmapping must
        # clear any override left over from a previous "Choose image" pick
        # -- otherwise the row shows "unmapped" but the overridden image
        # still fires at export (2026-08-09 user report).
        upload = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"bytes"), "face.png"), "tag": "face"},
            content_type="multipart/form-data",
        )
        image_id = upload.get_json()["image"]["id"]
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "face", "start_ms": 46675, "image_id": image_id},
        )
        resp = client.post(
            f"/api/v1/songs/{self.SONG}/ignored-images",
            json={"word": "face", "start_ms": 46675},
        )
        assert resp.status_code == 200
        assert resp.get_json()["overrides"] == []
        overrides = client.get(f"/api/v1/songs/{self.SONG}/image-overrides").get_json()["overrides"]
        assert overrides == []

    def test_ignore_leaves_overrides_on_other_occurrences_alone(self, client):
        upload = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"bytes"), "face.png"), "tag": "face"},
            content_type="multipart/form-data",
        )
        image_id = upload.get_json()["image"]["id"]
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "face", "start_ms": 5000, "image_id": image_id},
        )
        client.post(
            f"/api/v1/songs/{self.SONG}/ignored-images",
            json={"word": "face", "start_ms": 46675},
        )
        overrides = client.get(f"/api/v1/songs/{self.SONG}/image-overrides").get_json()["overrides"]
        assert overrides == [{"word": "face", "start_ms": 5000, "image_id": image_id}]


class TestImageOverrides:
    SONG = "cafe0123deadbeef"

    def _upload(self, client, tag: str, filename: str = "a.gif") -> str:
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"bytes"), filename), "tag": tag},
            content_type="multipart/form-data",
        )
        return resp.get_json()["image"]["id"]

    def test_empty_by_default(self, client):
        resp = client.get(f"/api/v1/songs/{self.SONG}/image-overrides")
        assert resp.status_code == 200
        assert resp.get_json()["overrides"] == []

    def test_set_adds_override_word_lowercased(self, client):
        image_id = self._upload(client, "sing")
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "Sing", "start_ms": 2000, "image_id": image_id},
        )
        assert resp.status_code == 200
        assert resp.get_json()["overrides"] == [{"word": "sing", "start_ms": 2000, "image_id": image_id}]
        listed = client.get(f"/api/v1/songs/{self.SONG}/image-overrides").get_json()
        assert listed["overrides"] == [{"word": "sing", "start_ms": 2000, "image_id": image_id}]

    def test_set_replaces_existing_override_for_same_occurrence(self, client):
        first_id = self._upload(client, "sing", "first.gif")
        second_id = self._upload(client, "sing", "second.gif")
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 2000, "image_id": first_id},
        )
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 2000, "image_id": second_id},
        )
        overrides = resp.get_json()["overrides"]
        assert overrides == [{"word": "sing", "start_ms": 2000, "image_id": second_id}]

    def test_setting_one_occurrence_leaves_other_occurrences_of_same_word(self, client):
        image_id = self._upload(client, "sing")
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 2000, "image_id": image_id},
        )
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 3000, "image_id": image_id},
        )
        overrides = resp.get_json()["overrides"]
        assert {"word": "sing", "start_ms": 2000, "image_id": image_id} in overrides
        assert {"word": "sing", "start_ms": 3000, "image_id": image_id} in overrides
        assert len(overrides) == 2

    def test_missing_word_returns_400(self, client):
        image_id = self._upload(client, "sing")
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"start_ms": 2000, "image_id": image_id},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_word"

    def test_missing_start_ms_returns_400(self, client):
        image_id = self._upload(client, "sing")
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "image_id": image_id},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_start_ms"

    def test_missing_image_id_returns_400(self, client):
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 2000},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_image_id"

    def test_unknown_image_id_returns_404(self, client):
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 2000, "image_id": "does-not-exist"},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "image_not_found"

    def test_clear_removes_only_that_occurrence(self, client):
        image_id = self._upload(client, "sing")
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 2000, "image_id": image_id},
        )
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 3000, "image_id": image_id},
        )
        resp = client.delete(f"/api/v1/songs/{self.SONG}/image-overrides/sing/2000")
        assert resp.status_code == 200
        listed = client.get(f"/api/v1/songs/{self.SONG}/image-overrides").get_json()
        assert listed["overrides"] == [{"word": "sing", "start_ms": 3000, "image_id": image_id}]

    def test_clear_unknown_occurrence_returns_404(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/image-overrides/nothere/1000")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_overridden"

    def test_set_preserves_existing_session_fields(self, client):
        from src.review.storage.assignments import load_session, save_full_session

        image_id = self._upload(client, "sing")
        save_full_session(self.SONG, {"sections": [{"label": "verse"}], "words": []})
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "sing", "start_ms": 2000, "image_id": image_id},
        )
        session = load_session(self.SONG)
        assert session["sections"] == [{"label": "verse"}]
        assert session["image_occurrence_overrides"] == [{"word": "sing", "start_ms": 2000, "image_id": image_id}]


class TestManualPictureOccurrences:
    """Pictures at an explicit mm:ss timestamp, independent of any lyric word."""

    SONG = "cafe0123deadbeef"

    def _upload(self, client, tag: str, filename: str = "a.gif") -> str:
        resp = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"bytes"), filename), "tag": tag},
            content_type="multipart/form-data",
        )
        return resp.get_json()["image"]["id"]

    def test_empty_by_default(self, client):
        resp = client.get(f"/api/v1/songs/{self.SONG}/image-manual-occurrences")
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == []

    def test_set_adds_occurrence(self, client):
        image_id = self._upload(client, "manual")
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"start_ms": 46675, "image_id": image_id},
        )
        assert resp.status_code == 200
        assert resp.get_json()["occurrences"] == [{"start_ms": 46675, "image_id": image_id}]
        listed = client.get(f"/api/v1/songs/{self.SONG}/image-manual-occurrences").get_json()
        assert listed["occurrences"] == [{"start_ms": 46675, "image_id": image_id}]

    def test_set_replaces_existing_entry_at_same_timestamp(self, client):
        first_id = self._upload(client, "manual", "first.gif")
        second_id = self._upload(client, "manual", "second.gif")
        client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"start_ms": 5000, "image_id": first_id},
        )
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"start_ms": 5000, "image_id": second_id},
        )
        assert resp.get_json()["occurrences"] == [{"start_ms": 5000, "image_id": second_id}]

    def test_missing_start_ms_returns_400(self, client):
        image_id = self._upload(client, "manual")
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"image_id": image_id},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_start_ms"

    def test_missing_image_id_returns_400(self, client):
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"start_ms": 1000},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_image_id"

    def test_unknown_image_id_returns_404(self, client):
        resp = client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"start_ms": 1000, "image_id": "nope"},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "image_not_found"

    def test_clear_removes_only_that_timestamp(self, client):
        image_id = self._upload(client, "manual")
        client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"start_ms": 1000, "image_id": image_id},
        )
        client.put(
            f"/api/v1/songs/{self.SONG}/image-manual-occurrences",
            json={"start_ms": 2000, "image_id": image_id},
        )
        resp = client.delete(f"/api/v1/songs/{self.SONG}/image-manual-occurrences/1000")
        assert resp.status_code == 200
        listed = client.get(f"/api/v1/songs/{self.SONG}/image-manual-occurrences").get_json()
        assert listed["occurrences"] == [{"start_ms": 2000, "image_id": image_id}]

    def test_clear_unknown_timestamp_returns_404(self, client):
        resp = client.delete(f"/api/v1/songs/{self.SONG}/image-manual-occurrences/9999")
        assert resp.status_code == 404


class TestImageMatches:
    """GET /image-matches recomputes suggestions/topics live against the
    current library instead of trusting the analyze-time session snapshot
    (2026-08-09) -- a word uploaded an image for after analyzing must show
    up against every one of its occurrences, not just future analyses."""

    SONG = "cafe0123deadbeef"

    def _set_words(self, client, words: list[dict]) -> None:
        from src.review.storage.assignments import save_full_session

        save_full_session(self.SONG, {"sections": [{"label": "verse"}], "words": words})

    def test_empty_words_returns_empty_lists(self, client):
        self._set_words(client, [])
        resp = client.get(f"/api/v1/songs/{self.SONG}/image-matches")
        assert resp.status_code == 200
        assert resp.get_json() == {"suggestions": [], "topics": []}

    def test_no_library_match_surfaces_as_topic(self, client):
        self._set_words(client, [{"label": "TACOS", "start_ms": 1000, "end_ms": 1500}])
        resp = client.get(f"/api/v1/songs/{self.SONG}/image-matches").get_json()
        assert resp["suggestions"] == []
        assert [t["word"] for t in resp["topics"]] == ["TACOS"]

    def test_library_upload_reflects_immediately_without_reanalyzing(self, client):
        # This is the actual bug: uploading an image must make ALL matching
        # occurrences show up on the next /image-matches call, not just the
        # occurrence present when the song was originally analyzed.
        words = [
            {"label": "TACOS", "start_ms": 1000, "end_ms": 1500},
            {"label": "TACOS", "start_ms": 46000, "end_ms": 46500},
            {"label": "TACOS", "start_ms": 87000, "end_ms": 87500},
        ]
        self._set_words(client, words)
        before = client.get(f"/api/v1/songs/{self.SONG}/image-matches").get_json()
        assert before["suggestions"] == []
        assert len(before["topics"]) == 1

        client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"gif-bytes"), "tacos.gif"), "tag": "tacos"},
            content_type="multipart/form-data",
        )

        after = client.get(f"/api/v1/songs/{self.SONG}/image-matches").get_json()
        assert after["topics"] == []
        assert sorted(s["start_ms"] for s in after["suggestions"]) == [1000, 46000, 87000]

    def test_respects_ignored_occurrences_and_overrides(self, client):
        upload = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"bytes"), "tacos.gif"), "tag": "tacos"},
            content_type="multipart/form-data",
        ).get_json()
        other_image = client.post(
            "/api/v1/images",
            data={"image": (io.BytesIO(b"bytes2"), "special.gif"), "tag": "special"},
            content_type="multipart/form-data",
        ).get_json()

        words = [
            {"label": "TACOS", "start_ms": 1000, "end_ms": 1500},
            {"label": "TACOS", "start_ms": 2000, "end_ms": 2500},
            {"label": "TACOS", "start_ms": 3000, "end_ms": 3500},
        ]
        self._set_words(client, words)
        client.post(
            f"/api/v1/songs/{self.SONG}/ignored-images",
            json={"word": "tacos", "start_ms": 1000},
        )
        client.put(
            f"/api/v1/songs/{self.SONG}/image-overrides",
            json={"word": "tacos", "start_ms": 2000, "image_id": other_image["image"]["id"]},
        )

        resp = client.get(f"/api/v1/songs/{self.SONG}/image-matches").get_json()
        by_start = {s["start_ms"]: s for s in resp["suggestions"]}
        assert 1000 not in by_start  # ignored occurrence stays absent
        assert by_start[2000]["image_id"] == other_image["image"]["id"]  # override wins
        assert by_start[3000]["image_id"] == upload["image"]["id"]  # normal fuzzy match
