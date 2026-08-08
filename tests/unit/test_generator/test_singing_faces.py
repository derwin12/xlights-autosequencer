"""Tests for singing-face and lyric-text placement (effect_placer helpers)."""
from __future__ import annotations

from src.generator.effect_placer import (
    _best_face_definition,
    _lightest_color,
    _place_lyric_text,
    _place_singing_faces,
    _vocal_regions,
)
from src.grouper.layout import Prop


def _prop(name: str, display_as: str = "Custom", *,
          faces: list[str] | None = None, pixels: int = 0) -> Prop:
    return Prop(
        name=name,
        display_as=display_as,
        world_x=0.0, world_y=0.0, world_z=0.0,
        scale_x=1.0, scale_y=1.0,
        parm1=1, parm2=1,
        sub_models=[],
        pixel_count=pixels,
        face_definitions=faces or [],
    )


WORDS = [
    {"label": "HELLO", "start_ms": 1000, "end_ms": 1400},
    {"label": "WORLD", "start_ms": 1600, "end_ms": 2000},
    # > 5s gap — second vocal region
    {"label": "AGAIN", "start_ms": 9000, "end_ms": 9500},
]


class TestVocalRegions:
    def test_merges_close_words_and_splits_on_gap(self):
        assert _vocal_regions(WORDS) == [(1000, 2000), (9000, 9500)]

    def test_empty(self):
        assert _vocal_regions(None) == []
        assert _vocal_regions([]) == []

    def test_unsorted_input(self):
        shuffled = [WORDS[2], WORDS[0], WORDS[1]]
        assert _vocal_regions(shuffled) == [(1000, 2000), (9000, 9500)]


class TestPlaceSingingFaces:
    def test_places_per_region_on_face_props_only(self):
        props = [
            _prop("Singing Face", faces=["SingingFace"]),
            _prop("Arch1", display_as="Arch"),
        ]
        result = _place_singing_faces(props, WORDS)
        assert set(result) == {"Singing Face"}
        placements = result["Singing Face"]
        assert len(placements) == 2
        assert all(p.effect_name == "Faces" for p in placements)
        assert placements[0].parameters["E_CHOICE_Faces_FaceDefinition"] == "SingingFace"
        assert placements[0].parameters["E_CHOICE_Faces_TimingTrack"] == "Lyrics"
        # Frame-aligned to the first vocal region
        assert placements[0].start_ms == 1000
        assert placements[0].end_ms == 2000

    def test_no_words_no_placements(self):
        props = [_prop("Singing Face", faces=["SingingFace"])]
        assert _place_singing_faces(props, None) == {}
        assert _place_singing_faces(props, []) == {}

    def test_no_face_props_no_placements(self):
        assert _place_singing_faces([_prop("Arch1", display_as="Arch")], WORDS) == {}

    def test_face_definition_matched_to_prop_name(self):
        # A model can carry several definitions ("Singing Tree Male" holds
        # both genders' faces) — the one matching the prop name wins.
        prop = _prop("Singing Tree Male", faces=["Female Face", "Male Face"])
        result = _place_singing_faces([prop], WORDS)
        params = result["Singing Tree Male"][0].parameters
        assert params["E_CHOICE_Faces_FaceDefinition"] == "Male Face"

    def test_matrix_with_image_faces_excluded(self):
        # Layout parser leaves face_definitions empty for Matrix-type
        # (image) faces — such props must not receive Faces placements.
        props = [_prop("Big Matrix", display_as="Matrix", pixels=4800)]
        assert _place_singing_faces(props, WORDS) == {}


class TestPlaceLyricText:
    def test_text_on_largest_matrix(self):
        props = [
            _prop("Matrix Small", display_as="Matrix", pixels=512),
            _prop("Matrix Big", display_as="Matrix", pixels=4800),
            _prop("Singing Face", faces=["SingingFace"]),
        ]
        result = _place_lyric_text(props, WORDS)
        assert set(result) == {"Matrix Big"}
        placements = result["Matrix Big"]
        assert len(placements) == 2  # one per vocal region
        assert all(p.effect_name == "Text" for p in placements)
        assert placements[0].parameters["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words"
        assert placements[0].layer == 0

    def test_lyric_named_matrix_preferred(self):
        props = [
            _prop("Matrix Big", display_as="Matrix", pixels=4800),
            _prop("Lyrics Matrix", display_as="Matrix", pixels=512),
        ]
        result = _place_lyric_text(props, WORDS)
        assert set(result) == {"Lyrics Matrix"}

    def test_no_matrix_no_placements(self):
        assert _place_lyric_text([_prop("Arch1", display_as="Arch")], WORDS) == {}

    def test_no_words_no_placements(self):
        props = [_prop("Matrix Big", display_as="Matrix", pixels=4800)]
        assert _place_lyric_text(props, None) == {}

    def test_multiple_lyric_named_matrices_all_get_placements(self):
        # 2026-07-18: previously only the single largest matrix ever got
        # placements; a second lyrics-display prop ("Lyrics Matrix Small")
        # must get the same treatment, not be silently dropped.
        props = [
            _prop("Lyrics Matrix", display_as="Matrix", pixels=4800),
            _prop("Lyrics Matrix Small", display_as="Matrix", pixels=512),
            _prop("Matrix Unrelated", display_as="Matrix", pixels=9999),
        ]
        result = _place_lyric_text(props, WORDS)
        assert set(result) == {"Lyrics Matrix", "Lyrics Matrix Small"}
        assert len(result["Lyrics Matrix"]) == 2  # one per vocal region
        assert len(result["Lyrics Matrix Small"]) == 3  # one per word (2026-07-28)

    def test_small_named_matrix_gets_per_word_placements(self):
        # 2026-07-28: a "small"-named target renders one Text effect per
        # word, sized to that word's own timing, instead of one effect per
        # vocal region using LyricTrack mode.
        props = [
            _prop("Lyrics Matrix", display_as="Matrix", pixels=4800),
            _prop("Lyrics Matrix Small", display_as="Matrix", pixels=512),
        ]
        result = _place_lyric_text(props, WORDS)
        big = result["Lyrics Matrix"]
        small = result["Lyrics Matrix Small"]

        # Non-small target unchanged: region-based, LyricTrack mode.
        assert len(big) == 2
        assert big[0].parameters["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words"
        assert "E_TEXTCTRL_Text" not in big[0].parameters

        # Small target: one placement per word, sized to the word itself,
        # driven by the LyricTrack (not literal text) -- see
        # test_small_named_matrix_scrolls_long_words for why.
        assert len(small) == 3
        assert [p.start_ms for p in small] == [1000, 1600, 9000]
        assert [p.end_ms for p in small] == [1400, 2000, 9500]
        assert all(p.parameters["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words" for p in small)
        assert all("E_TEXTCTRL_Text" not in p.parameters for p in small)
        assert all(p.parameters["E_CHOICE_Text_Font"] == "5-5x5 Mono" for p in small)

    def test_small_named_matrix_scrolls_long_words(self):
        # MORNING (7 letters, the shortest scrolling word) and AMORNING
        # (8 letters) are the user-verified reference points: each extra
        # letter shifts XStart +3 / XEnd -3 (2026-07-28).
        long_words = [
            {"label": "HELLO", "start_ms": 1000, "end_ms": 1400},
            {"label": "MORNING", "start_ms": 1600, "end_ms": 2400},
            {"label": "AMORNING", "start_ms": 2600, "end_ms": 3400},
        ]
        props = [_prop("Lyrics Matrix Small", display_as="Matrix", pixels=512)]
        result = _place_lyric_text(props, long_words)
        placements = result["Lyrics Matrix Small"]

        short = placements[0].parameters
        assert short["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words"
        assert "E_CHOICE_Text_Dir" not in short

        long = placements[1].parameters
        assert long["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words"
        assert long["E_CHOICE_Text_Dir"] == "vector"
        assert long["E_NOTEBOOK"] == "Start Position"
        assert long["E_CHECKBOX_Text_PixelOffsets"] == "1"
        assert long["E_SLIDER_Text_XStart"] == "3"
        assert long["E_SLIDER_Text_XEnd"] == "-2"

        longer = placements[2].parameters
        assert longer["E_SLIDER_Text_XStart"] == "6"
        assert longer["E_SLIDER_Text_XEnd"] == "-5"

    def test_defaults_to_white_without_theme_palette(self):
        props = [_prop("Lyrics Matrix", display_as="Matrix", pixels=4800),
                 _prop("Lyrics Matrix Small", display_as="Matrix", pixels=512)]
        result = _place_lyric_text(props, WORDS)
        assert result["Lyrics Matrix"][0].color_palette == ["#FFFFFF"]
        assert result["Lyrics Matrix Small"][0].color_palette == ["#FFFFFF"]

    def test_uses_lightest_theme_color(self):
        # Darkest first to make sure it's not just picking palette[0].
        palette = ["#101010", "#804020", "#FFCC66"]
        props = [_prop("Lyrics Matrix", display_as="Matrix", pixels=4800),
                 _prop("Lyrics Matrix Small", display_as="Matrix", pixels=512)]
        result = _place_lyric_text(props, WORDS, theme_palette=palette)
        assert result["Lyrics Matrix"][0].color_palette == ["#FFCC66"]
        assert result["Lyrics Matrix Small"][0].color_palette == ["#FFCC66"]


class TestLightestColor:
    def test_picks_highest_lightness_entry(self):
        assert _lightest_color(["#101010", "#804020", "#FFCC66"]) == "#FFCC66"

    def test_empty_palette_falls_back_to_white(self):
        assert _lightest_color([]) == "#FFFFFF"

    def test_unparseable_entries_skipped(self):
        assert _lightest_color(["not-a-color", "#00FF00"]) == "#00FF00"


DUET_WORDS = [
    {"label": "HELLO", "start_ms": 1000, "end_ms": 1400, "speaker": 0},
    {"label": "WORLD", "start_ms": 1600, "end_ms": 2000, "speaker": 0},
    # > 5s gap — second vocal region, sung by the backup voice
    {"label": "AGAIN", "start_ms": 9000, "end_ms": 9500, "speaker": 1},
]


class TestSingingFacesDiarization:
    def test_backup_speaker_routes_to_second_face_prop(self):
        props = [
            _prop("Lead Face", faces=["Female Face"]),
            _prop("Backup Face", faces=["Male Face"]),
        ]
        result = _place_singing_faces(props, DUET_WORDS, vocal_diarization=True)
        assert set(result) == {"Lead Face", "Backup Face"}
        lead = result["Lead Face"]
        backup = result["Backup Face"]
        assert len(lead) == 1 and lead[0].start_ms == 1000 and lead[0].end_ms == 2000
        assert lead[0].parameters["E_CHOICE_Faces_TimingTrack"] == "Lyrics"
        assert len(backup) == 1 and backup[0].start_ms == 9000 and backup[0].end_ms == 9500
        assert backup[0].parameters["E_CHOICE_Faces_TimingTrack"] == "Lyrics - Backup"

    def test_flag_off_ignores_speaker_tag(self):
        # Same tagged words, but the generator hasn't opted in yet -- every
        # face prop gets every word, same as before diarization existed.
        props = [_prop("Lead Face", faces=["Female Face"]),
                 _prop("Backup Face", faces=["Male Face"])]
        result = _place_singing_faces(props, DUET_WORDS, vocal_diarization=False)
        assert len(result["Lead Face"]) == 2
        assert len(result["Backup Face"]) == 2

    def test_single_face_prop_degrades_to_all_words(self):
        # No second prop to route the backup voice to -- render everything
        # on the one prop rather than silently dropping speaker-1 words.
        props = [_prop("Only Face", faces=["Face"])]
        result = _place_singing_faces(props, DUET_WORDS, vocal_diarization=True)
        assert len(result["Only Face"]) == 2

    def test_no_backup_words_degrades_to_all_words(self):
        result = _place_singing_faces(
            [_prop("Lead Face", faces=["Face1"]), _prop("Backup Face", faces=["Face2"])],
            WORDS, vocal_diarization=True,
        )
        assert len(result["Lead Face"]) == 2
        assert len(result["Backup Face"]) == 2


class TestLyricTextDiarization:
    def test_small_target_never_becomes_backup_and_gets_every_word(self):
        # A "*Small*" target is a size variant of the primary lyric display,
        # not a second singer's display -- with only one non-small target,
        # there's no backup_target at all, so both targets render every
        # word (2026-08-07 user report: this pair previously split one
        # continuous vocal track in half between the two displays).
        props = [
            _prop("Lyrics Matrix", display_as="Matrix", pixels=4800),
            _prop("Lyrics Matrix Small", display_as="Matrix", pixels=512),
        ]
        result = _place_lyric_text(props, DUET_WORDS, vocal_diarization=True)
        # Neither target is backup -- "Lyrics Matrix" gets both regions.
        assert len(result["Lyrics Matrix"]) == 2
        assert all(
            p.parameters["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words"
            for p in result["Lyrics Matrix"]
        )
        # "Lyrics Matrix Small" gets one per-word placement per word,
        # covering the whole song via the primary (non-backup) track.
        small = result["Lyrics Matrix Small"]
        assert len(small) == 3
        assert all(
            p.parameters["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words"
            for p in small
        )
        assert "E_TEXTCTRL_Text" not in small[0].parameters

    def test_backup_speaker_routes_to_second_non_small_matrix(self):
        # Two non-small lyric matrices (a genuine same-size duet display
        # pair) still split lead/backup by diarization.
        props = [
            _prop("Lyrics Matrix", display_as="Matrix", pixels=4800),
            _prop("Lyrics Matrix Backup", display_as="Matrix", pixels=4800),
        ]
        result = _place_lyric_text(props, DUET_WORDS, vocal_diarization=True)
        assert len(result["Lyrics Matrix"]) == 1
        assert result["Lyrics Matrix"][0].parameters["E_CHOICE_Text_LyricTrack"] == "Lyrics - Words"
        backup = result["Lyrics Matrix Backup"]
        assert len(backup) == 1 and backup[0].start_ms == 9000 and backup[0].end_ms == 9500
        assert backup[0].parameters["E_CHOICE_Text_LyricTrack"] == "Lyrics - Backup - Words"

    def test_single_target_degrades_to_all_words(self):
        props = [_prop("Matrix Big", display_as="Matrix", pixels=4800)]
        result = _place_lyric_text(props, DUET_WORDS, vocal_diarization=True)
        assert len(result["Matrix Big"]) == 2
