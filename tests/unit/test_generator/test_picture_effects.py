"""Tests for the Pictures effect: image library storage + Matrix/Mega Tree placement."""
from __future__ import annotations

from pathlib import Path

from src.effects.library import load_effect_library
from src.generator.effect_placer import (
    _PICTURE_BURST_MS,
    _PICTURE_DIRECTIONS,
    _PICTURE_FADE_MS,
    _PICTURE_LEAD_MS,
    _PICTURE_MIN_GAP_MS,
    _PICTURE_SCALE_PERCENT,
    _PICTURE_SPEED,
    _place_picture_effects,
)
from src.generator.models import GenerationConfig
from src.generator.image_catalog import (
    catalog_images,
    find_unmatched_topics,
    load_image_library,
    save_image_to_library,
    suggest_images_for_words,
)
from src.grouper.grouper import PowerGroup


def _prop(name: str, display_as: str):
    return type("FakeProp", (), {"name": name, "display_as": display_as})()


def _group(name: str, members: list[str], tier: int = 6) -> PowerGroup:
    return PowerGroup(name=name, tier=tier, members=members)


def _match(word: str, start_ms: int, stored_path: str = "/lib/img.gif", duration_ms: int = 500) -> dict:
    return {"word": word, "start_ms": start_ms, "end_ms": start_ms + duration_ms, "stored_path": stored_path}


def _library_entry(tag: str, filename: str = "img.gif", stored_path: str = "/lib/img.gif") -> dict:
    return {"id": "abc123", "tag": tag, "filename": filename, "stored_path": stored_path}


class TestPlacePictureEffects:
    def test_zero_duration_returns_empty(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=0,
            variation_seed=0,
            word_image_matches=[_match("snowman", 0)],
        )
        assert result == {}

    def test_no_matches_returns_empty(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[],
        )
        assert result == {}

    def test_no_matches_argument_omitted_returns_empty(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
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
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert result == {}

    def test_megatree_name_match_included(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Mega Tree", "Custom"), _prop("MegaTree2", "Custom")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert set(result) == {"Mega Tree", "MegaTree2"}

    def test_megatopper_not_matched_by_megatree_tokens(self):
        library = load_effect_library()
        # "Mega Topper" contains "mega" but not "mega tree"/"megatree" -- must
        # not accidentally match, toppers are a separate family (bug-192 era
        # distinction preserved in corpus_recipes.py).
        result = _place_picture_effects(
            props=[_prop("Mega Topper", "Custom")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert result == {}

    def test_lyrics_matrix_excluded_despite_matrix_display_type(self):
        library = load_effect_library()
        # A matrix named for lyric text display (see _place_lyric_text) must
        # not also receive Pictures placements -- it's reserved for the
        # Lyric Track text effect, not image placement.
        result = _place_picture_effects(
            props=[_prop("Lyrics Matrix", "Matrix"), _prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert set(result) == {"Matrix1"}

    def test_burst_redirected_to_enclosing_group_not_raw_model(self):
        library = load_effect_library()
        # bug-184 (2026-07-12): a model's own direct effect covers/overrides
        # whatever its parent Model Group renders onto it in xLights -- group
        # and direct-model content do not blend. Confirmed again 2026-07-15
        # against a real generated .xsq: Pictures placed directly on the raw
        # "Matrix" model blanked out all the "06_PROP_Matrix" group's theme
        # content for that same model. The burst must land on the group.
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[_group("06_PROP_Matrix", members=["Matrix1"])],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert set(result) == {"06_PROP_Matrix"}
        assert result["06_PROP_Matrix"][0].model_or_group == "06_PROP_Matrix"

    def test_burst_prefers_specific_tier_group_over_whole_house_canvas(self):
        library = load_effect_library()
        # bug-243 (2026-07-15): every prop is also a member of the tier-1
        # "01_BASE_All" whole-house canvas group, and that group is always
        # generated (and listed) before any tier-6/8 group. A first-match
        # lookup over `groups` always picked 01_BASE_All, so the burst was
        # written to the file but rendered across the entire display instead
        # of the intended matrix. The tighter, non-tier-1 group must win.
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[
                _group("01_BASE_All", members=["Matrix1", "Arch1", "Tree1"], tier=1),
                _group("06_PROP_Matrix", members=["Matrix1"], tier=6),
            ],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert set(result) == {"06_PROP_Matrix"}

    def test_prop_with_no_enclosing_group_falls_back_to_own_row(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[_group("06_PROP_Matrix", members=["SomeOtherModel"])],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert set(result) == {"Matrix1"}

    def test_burst_placed_below_existing_layers_not_fixed_layer_1(self):
        library = load_effect_library()
        # bug-243 follow-up (2026-07-15): a fixed layer=1 collided with
        # whatever theme layer a group's rotation pool already occupied,
        # clipping 6000ms bursts down to 100-275ms slivers. A first attempt
        # fixed that by moving the burst to the *highest* layer number,
        # under the assumption higher-number-renders-on-top -- confirmed
        # wrong by inspecting a real generated .xsq (landed as the LAST
        # <EffectLayer> child, which xLights renders at the bottom of the
        # stack, hidden behind an opaque "On" layer -- user screenshot).
        # xsq_writer serializes layers in ascending index order and xLights
        # renders the *first* child on top, so the burst must land one
        # layer *below* the lowest (topmost-rendering) index already used.
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[_group("06_PROP_Matrix", members=["Matrix1"])],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
            existing_layers={"06_PROP_Matrix": 0},
        )
        assert result["06_PROP_Matrix"][0].layer == -1

    def test_burst_layer_defaults_to_0_when_target_has_no_existing_layers(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        assert result["Matrix1"][0].layer == 0

    def test_burst_parameters_scale_fade_and_layer(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000, stored_path="/lib/snowman.gif")],
        )
        placement = result["Matrix1"][0]
        assert placement.effect_name == "Pictures"
        assert placement.layer == 0
        assert placement.fade_in_ms == _PICTURE_FADE_MS
        assert placement.fade_out_ms == _PICTURE_FADE_MS
        assert placement.parameters["E_TEXTCTRL_Pictures_Filename"] == "/lib/snowman.gif"
        assert placement.parameters["E_CHECKBOX_Pictures_TransparentBlack"] == "1"
        assert placement.parameters["E_CHOICE_Pictures_Direction"] in _PICTURE_DIRECTIONS
        # Without an explicit scaling mode, xLights' Pictures effect defaults
        # to rendering the image at its native pixel size rather than fit to
        # the buffer -- on a Matrix buffer far larger than a typical library
        # image, that renders it too small to read as an accent (user report,
        # 2026-07-15, screenshot showed the burst present but imperceptible).
        assert placement.parameters["E_CHOICE_Scaling"] == "Scale To Fit"
        assert placement.parameters["E_TEXTCTRL_Pictures_Speed"] == _PICTURE_SPEED
        assert placement.parameters["E_SLIDER_Pictures_StartScale"] == _PICTURE_SCALE_PERCENT
        assert placement.parameters["E_SLIDER_Pictures_EndScale"] == _PICTURE_SCALE_PERCENT

    def test_burst_starts_lead_ms_before_match_start_and_lasts_burst_duration(self):
        library = load_effect_library()
        # bug (2026-07-15): the burst used to start exactly on the matched
        # word's timestamp, popping in right as the lyric was sung instead
        # of already being visible. It must now start _PICTURE_LEAD_MS
        # earlier so it (plus its fade-in) is fully up by the time the word
        # actually hits.
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 5_000)],
        )
        placement = result["Matrix1"][0]
        assert placement.start_ms == 5_000 - _PICTURE_LEAD_MS
        assert placement.end_ms == 5_000 - _PICTURE_LEAD_MS + _PICTURE_BURST_MS

    def test_lead_in_clamped_to_zero_for_early_matches(self):
        library = load_effect_library()
        # A match within the first second of the song has no room for the
        # full lead-in -- clamp to 0 instead of going negative.
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 500)],
        )
        placement = result["Matrix1"][0]
        assert placement.start_ms == 0

    def test_burst_clipped_to_song_duration(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=3_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 1000)],
        )
        placement = result["Matrix1"][0]
        assert placement.start_ms == 0
        assert placement.end_ms == 3_000

    def test_match_at_or_past_song_end_is_skipped(self):
        library = load_effect_library()
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=3_000,
            variation_seed=0,
            word_image_matches=[_match("snowman", 3_000 + _PICTURE_LEAD_MS)],
        )
        assert result == {}

    def test_close_matches_deduped_by_min_gap(self):
        library = load_effect_library()
        # Second match's burst window (starts 2000-1000=1000, per the lead-in)
        # would literally overlap the first burst's window (0-6000) -- two
        # different pictures can't be on screen at once regardless of image,
        # so this must be dropped no matter which files are involved.
        matches = [
            _match("love", 1_000, stored_path="/lib/love.gif"),
            _match("fool", 2_000, stored_path="/lib/fool.gif"),
        ]
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=matches,
        )
        assert len(result["Matrix1"]) == 1
        assert result["Matrix1"][0].parameters["E_TEXTCTRL_Pictures_Filename"] == "/lib/love.gif"

    def test_different_image_fires_soon_after_without_waiting_for_min_gap(self):
        library = load_effect_library()
        # bug (2026-07-15): a word that recurs often in the lyrics (e.g. a
        # repeated chorus line) used to crowd out a rarer, differently-imaged
        # match that fell within _PICTURE_MIN_GAP_MS of it, even though a
        # DIFFERENT picture right after the first doesn't read as flicker.
        # First burst: word_start=1_000 -> placed 0-6_000. Second word_start
        # chosen so its placed start (500ms after the first burst ends) is
        # well inside the old min-gap window but doesn't overlap in time.
        second_word_start = 6_000 + 500 + _PICTURE_LEAD_MS
        matches = [
            _match("love", 1_000, stored_path="/lib/love.gif"),
            _match("fool", second_word_start, stored_path="/lib/fool.gif"),
        ]
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=matches,
        )
        files = [p.parameters["E_TEXTCTRL_Pictures_Filename"] for p in result["Matrix1"]]
        assert files == ["/lib/love.gif", "/lib/fool.gif"]

    def test_same_image_repeat_still_waits_out_the_min_gap(self):
        library = load_effect_library()
        # Same setup as the different-image test above, but both matches
        # point at the same file -- the cooldown must still apply so the
        # identical picture doesn't flicker back on right after it left.
        second_word_start = 6_000 + 500 + _PICTURE_LEAD_MS
        matches = [
            _match("love", 1_000, stored_path="/lib/love.gif"),
            _match("loved", second_word_start, stored_path="/lib/love.gif"),
        ]
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=matches,
        )
        assert len(result["Matrix1"]) == 1

    def test_far_apart_matches_both_fire(self):
        library = load_effect_library()
        first_placed_end = max(0, 1_000 - _PICTURE_LEAD_MS) + _PICTURE_BURST_MS
        second_start = first_placed_end + _PICTURE_LEAD_MS + _PICTURE_MIN_GAP_MS + 1_000
        matches = [
            _match("love", 1_000, stored_path="/lib/love.gif"),
            _match("fool", second_start, stored_path="/lib/fool.gif"),
        ]
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=second_start + 10_000,
            variation_seed=0,
            word_image_matches=matches,
        )
        assert len(result["Matrix1"]) == 2
        files = [p.parameters["E_TEXTCTRL_Pictures_Filename"] for p in result["Matrix1"]]
        assert files == ["/lib/love.gif", "/lib/fool.gif"]

    def test_match_missing_stored_path_is_ignored(self):
        library = load_effect_library()
        matches = [{"word": "snowman", "start_ms": 5_000, "end_ms": 5_500}]
        result = _place_picture_effects(
            props=[_prop("Matrix1", "Matrix")],
            groups=[],
            effect_library=library,
            duration_ms=60_000,
            variation_seed=0,
            word_image_matches=matches,
        )
        assert result == {}

    def test_deterministic_for_same_seed(self):
        library = load_effect_library()
        props = [_prop("Matrix1", "Matrix")]
        matches = [_match("snowman", 1_000, stored_path="/lib/a.gif")]
        first = _place_picture_effects(
            props=props, groups=[], effect_library=library,
            duration_ms=60_000, variation_seed=42, word_image_matches=matches,
        )
        second = _place_picture_effects(
            props=props, groups=[], effect_library=library,
            duration_ms=60_000, variation_seed=42, word_image_matches=matches,
        )
        first_dir = first["Matrix1"][0].parameters["E_CHOICE_Pictures_Direction"]
        second_dir = second["Matrix1"][0].parameters["E_CHOICE_Pictures_Direction"]
        assert first_dir == second_dir


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
        assert result[0]["stored_path"] == "/lib/img.gif"

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
