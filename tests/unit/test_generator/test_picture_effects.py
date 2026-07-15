"""Tests for effect_placer._place_picture_effects (catalog images on matrix/tree props)."""
from __future__ import annotations

from pathlib import Path

from src.effects.library import load_effect_library
from src.generator.effect_placer import _PICTURE_SEGMENT_MS, _place_picture_effects
from src.generator.models import GenerationConfig
from src.generator.image_catalog import catalog_images, suggest_images_for_words


def _prop(name: str, display_as: str):
    return type("FakeProp", (), {"name": name, "display_as": display_as})()


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
            image_catalog=["Images/a.gif"],
            effect_library=library,
            duration_ms=0,
            variation_seed=0,
        )
        assert result == {}

    def test_not_recommended_prop_type_excluded(self):
        library = load_effect_library()
        # Arch models classify as display_as "Arches" -> prop_type "arch",
        # rated not_recommended for Pictures in builtin_effects.json.
        result = _place_picture_effects(
            props=[_prop("Arch1", "Arches")],
            image_catalog=["Images/a.gif"],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
        )
        assert result == {}

    def test_matrix_prop_gets_placements(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            image_catalog=["Images/a.gif", "Images/b.gif"],
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
            assert p.parameters["E_FILEPICKER_Pictures_Filename"] in {
                "Images/a.gif", "Images/b.gif"
            }

    def test_multiple_props_can_get_different_offsets(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix"), _prop("Tree1", "Tree")],
            image_catalog=["Images/a.gif", "Images/b.gif", "Images/c.gif"],
            effect_library=library,
            duration_ms=_PICTURE_SEGMENT_MS,
            variation_seed=0,
        )
        assert set(result) == {"Matrix1", "Tree1"}
        # Each prop gets exactly one segment spanning the whole (short) duration.
        assert len(result["Matrix1"]) == 1
        assert len(result["Tree1"]) == 1

    def test_deterministic_for_same_seed(self):
        library = load_effect_library()
        props = [_prop("Matrix1", "Matrix")]
        catalog = ["Images/a.gif", "Images/b.gif", "Images/c.gif"]
        first = _place_picture_effects(
            props=props, image_catalog=catalog, effect_library=library,
            duration_ms=60_000, variation_seed=42,
        )
        second = _place_picture_effects(
            props=props, image_catalog=catalog, effect_library=library,
            duration_ms=60_000, variation_seed=42,
        )
        first_files = [p.parameters["E_FILEPICKER_Pictures_Filename"] for p in first["Matrix1"]]
        second_files = [p.parameters["E_FILEPICKER_Pictures_Filename"] for p in second["Matrix1"]]
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


class TestCatalogImages:
    def test_no_show_dir_returns_empty(self):
        assert catalog_images(show_dir=None) == []

    def test_missing_images_subdir_returns_empty(self, tmp_path):
        assert catalog_images(show_dir=tmp_path) == []

    def test_finds_images_recursively(self, tmp_path):
        images_dir = tmp_path / "Images"
        (images_dir / "sub").mkdir(parents=True)
        (images_dir / "top.gif").write_bytes(b"gif")
        (images_dir / "sub" / "nested.png").write_bytes(b"png")
        (images_dir / "notes.txt").write_bytes(b"not an image")

        result = catalog_images(show_dir=tmp_path)
        assert result == ["Images/sub/nested.png", "Images/top.gif"]


class TestSuggestImagesForWords:
    def test_no_words_returns_empty(self):
        assert suggest_images_for_words(None, ["Images/snowman.gif"]) == []
        assert suggest_images_for_words([], ["Images/snowman.gif"]) == []

    def test_no_catalog_returns_empty(self):
        words = [{"label": "snowman", "start_ms": 1000, "end_ms": 1500}]
        assert suggest_images_for_words(words, []) == []

    def test_exact_word_match(self):
        words = [{"label": "Snowman", "start_ms": 1000, "end_ms": 1500}]
        result = suggest_images_for_words(words, ["Images/snowman.gif"])
        assert len(result) == 1
        assert result[0]["matched_file"] == "Images/snowman.gif"
        assert result[0]["word"] == "Snowman"
        assert result[0]["start_ms"] == 1000
        assert result[0]["score"] == 1.0

    def test_short_word_skipped(self):
        words = [{"label": "the", "start_ms": 0, "end_ms": 200}]
        result = suggest_images_for_words(words, ["Images/the.gif"])
        assert result == []

    def test_unmatched_word_produces_no_suggestion(self):
        words = [{"label": "helicopter", "start_ms": 0, "end_ms": 500}]
        result = suggest_images_for_words(words, ["Images/snowman.gif"])
        assert result == []

    def test_close_variant_matches_via_fuzzy_ratio(self):
        words = [{"label": "snowmen", "start_ms": 0, "end_ms": 500}]
        result = suggest_images_for_words(words, ["Images/snowman.gif"])
        assert len(result) == 1
        assert result[0]["matched_file"] == "Images/snowman.gif"
