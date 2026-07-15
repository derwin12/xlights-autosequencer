"""Tests for the Pictures effect: image library storage + Matrix/Mega Tree placement."""
from __future__ import annotations

from pathlib import Path

from src.effects.library import load_effect_library
from src.generator.effect_placer import _PICTURE_SEGMENT_MS, _place_picture_effects
from src.generator.models import GenerationConfig
from src.generator.image_catalog import (
    catalog_images,
    find_unmatched_topics,
    load_image_library,
    save_image_to_library,
    suggest_images_for_words,
)


def _prop(name: str, display_as: str):
    return type("FakeProp", (), {"name": name, "display_as": display_as})()


def _library_entry(tag: str, filename: str = "img.gif", stored_path: str = "/lib/img.gif") -> dict:
    return {"id": "abc123", "tag": tag, "filename": filename, "stored_path": stored_path}


class TestPlacePictureEffects:
    def test_empty_catalog_returns_empty(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            image_catalog=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
        )
        assert result == {}

    def test_zero_duration_returns_empty(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            image_catalog=["/lib/a.gif"],
            effect_library=library,
            duration_ms=0,
            variation_seed=0,
        )
        assert result == {}

    def test_non_matrix_non_megatree_prop_excluded(self):
        library = load_effect_library()
        # Eligibility is deliberately narrow (Matrix display type or a Mega
        # Tree name match) -- reviewing the reference corpus (2026-07-15)
        # showed every other prop family that had any Pictures placement at
        # all just repeated one shared decorative image, not real content.
        result = _place_picture_effects(
            props=[_prop("Arch1", "Arches"), _prop("Snowflake1", "Star"), _prop("Tree1", "Tree")],
            image_catalog=["/lib/a.gif"],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
        )
        assert result == {}

    def test_megatree_name_match_included(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Mega Tree", "Custom"), _prop("MegaTree2", "Custom")],
            image_catalog=["/lib/a.gif"],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
        )
        assert set(result) == {"Mega Tree", "MegaTree2"}

    def test_megatopper_not_matched_by_megatree_tokens(self):
        library = load_effect_library()
        # "Mega Topper" contains "mega" but not "mega tree"/"megatree" -- must
        # not accidentally match, toppers are a separate family (bug-192 era
        # distinction preserved in corpus_recipes.py).
        result = _place_picture_effects(
            props=[_prop("Mega Topper", "Custom")],
            image_catalog=["/lib/a.gif"],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
        )
        assert result == {}

    def test_matrix_prop_gets_placements(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            image_catalog=["/lib/a.gif", "/lib/b.gif"],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
        )
        assert set(result) == {"Matrix1"}
        placements = result["Matrix1"]
        assert all(p.effect_name == "Pictures" for p in placements)
        assert all(p.model_or_group == "Matrix1" for p in placements)
        # 60s / 20s segments = 3 segments, covering the whole duration
        assert len(placements) == 3
        assert placements[0].start_ms == 0
        assert placements[-1].end_ms == 60_000
        for p in placements:
            assert p.parameters["E_TEXTCTRL_Pictures_Filename"] in {"/lib/a.gif", "/lib/b.gif"}

    def test_multiple_props_can_get_different_offsets(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix"), _prop("Mega Tree", "Custom")],
            image_catalog=["/lib/a.gif", "/lib/b.gif", "/lib/c.gif"],
            effect_library=library,
            duration_ms=_PICTURE_SEGMENT_MS,
            variation_seed=0,
        )
        assert set(result) == {"Matrix1", "Mega Tree"}
        # Each prop gets exactly one segment spanning the whole (short) duration.
        assert len(result["Matrix1"]) == 1
        assert len(result["Mega Tree"]) == 1

    def test_deterministic_for_same_seed(self):
        library = load_effect_library()
        props = [_prop("Matrix1", "Matrix")]
        catalog = ["/lib/a.gif", "/lib/b.gif", "/lib/c.gif"]
        first = _place_picture_effects(
            props=props, image_catalog=catalog, effect_library=library,
            duration_ms=60_000, variation_seed=42,
        )
        second = _place_picture_effects(
            props=props, image_catalog=catalog, effect_library=library,
            duration_ms=60_000, variation_seed=42,
        )
        first_files = [p.parameters["E_TEXTCTRL_Pictures_Filename"] for p in first["Matrix1"]]
        second_files = [p.parameters["E_TEXTCTRL_Pictures_Filename"] for p in second["Matrix1"]]
        assert first_files == second_files


class TestPictureEffectsConfigFlag:
    def test_flag_defaults_to_true(self):
        config = GenerationConfig(
            audio_path=Path("/fake/song.mp3"),
            layout_path=Path("/fake/layout.xml"),
        )
        assert config.picture_effects is True

    def test_flag_can_be_disabled(self):
        config = GenerationConfig(
            audio_path=Path("/fake/song.mp3"),
            layout_path=Path("/fake/layout.xml"),
            picture_effects=False,
        )
        assert config.picture_effects is False


class TestImageLibraryStorage:
    def test_empty_library_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
        assert load_image_library() == []
        assert catalog_images() == []

    def test_save_and_load_round_trips(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
        entry = save_image_to_library(
            tag="snowman", filename="snowman.gif", data=b"gif-bytes",
            uploaded_at="2026-07-15T00:00:00Z",
        )
        assert entry["tag"] == "snowman"
        assert Path(entry["stored_path"]).read_bytes() == b"gif-bytes"

        library = load_image_library()
        assert len(library) == 1
        assert library[0]["id"] == entry["id"]

        assert catalog_images() == [entry["stored_path"]]

    def test_multiple_uploads_accumulate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path))
        save_image_to_library(tag="snowman", filename="a.gif", data=b"1", uploaded_at="t1")
        save_image_to_library(tag="rocker", filename="b.gif", data=b"2", uploaded_at="t2")
        assert len(load_image_library()) == 2
        assert len(catalog_images()) == 2


class TestSuggestImagesForWords:
    def test_no_words_returns_empty(self):
        library = [_library_entry("snowman")]
        assert suggest_images_for_words(None, library) == []
        assert suggest_images_for_words([], library) == []

    def test_no_library_returns_empty(self):
        words = [{"label": "snowman", "start_ms": 1000, "end_ms": 1500}]
        assert suggest_images_for_words(words, []) == []

    def test_exact_word_match(self):
        words = [{"label": "Snowman", "start_ms": 1000, "end_ms": 1500}]
        library = [_library_entry("snowman", filename="snowman.gif")]
        result = suggest_images_for_words(words, library)
        assert len(result) == 1
        assert result[0]["matched_file"] == "snowman.gif"
        assert result[0]["matched_tag"] == "snowman"
        assert result[0]["word"] == "Snowman"
        assert result[0]["start_ms"] == 1000
        assert result[0]["score"] == 1.0

    def test_short_word_skipped(self):
        words = [{"label": "the", "start_ms": 0, "end_ms": 200}]
        library = [_library_entry("the")]
        assert suggest_images_for_words(words, library) == []

    def test_unmatched_word_produces_no_suggestion(self):
        words = [{"label": "helicopter", "start_ms": 0, "end_ms": 500}]
        library = [_library_entry("snowman")]
        assert suggest_images_for_words(words, library) == []

    def test_close_variant_matches_via_fuzzy_ratio(self):
        words = [{"label": "snowmen", "start_ms": 0, "end_ms": 500}]
        library = [_library_entry("snowman", filename="snowman.gif")]
        result = suggest_images_for_words(words, library)
        assert len(result) == 1
        assert result[0]["matched_file"] == "snowman.gif"


class TestFindUnmatchedTopics:
    def test_no_words_returns_empty(self):
        assert find_unmatched_topics(None, []) == []

    def test_matched_word_excluded(self):
        words = [{"label": "snowman", "start_ms": 0, "end_ms": 500}]
        library = [_library_entry("snowman")]
        assert find_unmatched_topics(words, library) == []

    def test_unmatched_real_word_included(self):
        words = [{"label": "rocker", "start_ms": 0, "end_ms": 500}]
        assert find_unmatched_topics(words, []) == [
            {"word": "rocker", "start_ms": 0, "end_ms": 500}
        ]

    def test_stopword_excluded(self):
        words = [{"label": "with", "start_ms": 0, "end_ms": 200}]
        assert find_unmatched_topics(words, []) == []

    def test_short_word_excluded(self):
        words = [{"label": "the", "start_ms": 0, "end_ms": 200}]
        assert find_unmatched_topics(words, []) == []

    def test_dedupes_repeated_word_keeping_first_occurrence(self):
        words = [
            {"label": "rocker", "start_ms": 5000, "end_ms": 5500},
            {"label": "rocker", "start_ms": 1000, "end_ms": 1500},
        ]
        result = find_unmatched_topics(words, [])
        assert len(result) == 1
        assert result[0]["start_ms"] == 5000
