"""Tests for phoneme analysis: mapping, timing distribution, PhonemeAnalyzer, serialization."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.analyzer.phonemes import (
    LyricsBlock,
    PhonemeMark,
    PhonemeResult,
    PhonemeTrack,
    WordMark,
    WordTrack,
    _ARPABET_TO_PAPAGAYO,
    arpabet_to_papagayo,
    distribute_phoneme_timing,
    word_to_papagayo,
)


# ── T008: ARPAbet → Papagayo mapping ─────────────────────────────────────────

class TestArpabetToPapagayo:
    def test_all_arpabet_codes_mapped(self):
        """Every key in the mapping table maps to a valid Papagayo label."""
        valid = {"AI", "E", "O", "U", "WQ", "L", "MBP", "FV", "etc", "rest"}
        for code, label in _ARPABET_TO_PAPAGAYO.items():
            assert label in valid, f"{code} maps to unknown label {label!r}"

    def test_vowel_aa_maps_ai(self):
        assert arpabet_to_papagayo("AA") == "AI"

    def test_vowel_ae_maps_ai(self):
        assert arpabet_to_papagayo("AE") == "AI"

    def test_vowel_eh_maps_e(self):
        assert arpabet_to_papagayo("EH") == "E"

    def test_vowel_ow_maps_o(self):
        assert arpabet_to_papagayo("OW") == "O"

    def test_consonant_m_maps_mbp(self):
        assert arpabet_to_papagayo("M") == "MBP"

    def test_consonant_f_maps_fv(self):
        assert arpabet_to_papagayo("F") == "FV"

    def test_consonant_l_maps_l(self):
        assert arpabet_to_papagayo("L") == "L"

    def test_consonant_w_maps_wq(self):
        assert arpabet_to_papagayo("W") == "WQ"

    def test_consonant_hh_maps_etc(self):
        assert arpabet_to_papagayo("HH") == "etc"

    def test_stress_digit_stripped(self):
        """Stress digits 0,1,2 must be stripped before lookup."""
        assert arpabet_to_papagayo("AA0") == "AI"
        assert arpabet_to_papagayo("AA1") == "AI"
        assert arpabet_to_papagayo("AA2") == "AI"
        assert arpabet_to_papagayo("EH1") == "E"
        assert arpabet_to_papagayo("OW2") == "O"

    def test_lowercase_input_handled(self):
        assert arpabet_to_papagayo("aa") == "AI"
        assert arpabet_to_papagayo("m") == "MBP"

    def test_unknown_phoneme_maps_etc(self):
        assert arpabet_to_papagayo("XYZ") == "etc"


class TestWordToPapagayo:
    @pytest.fixture()
    def cmu_dict(self):
        """Minimal in-memory cmudict for testing."""
        return {
            "hello": [["HH", "AH0", "L", "OW1"]],
            "world": [["W", "ER1", "L", "D"]],
            "i": [["AY1"]],
        }

    def test_known_word_mapped_correctly(self, cmu_dict):
        result = word_to_papagayo("HELLO", cmu_dict)
        assert result == ["etc", "AI", "L", "O"]

    def test_case_insensitive(self, cmu_dict):
        assert word_to_papagayo("hello", cmu_dict) == word_to_papagayo("HELLO", cmu_dict)

    def test_unknown_word_fallback(self, cmu_dict):
        result = word_to_papagayo("XYZFOO", cmu_dict)
        assert isinstance(result, list)
        assert len(result) > 0
        valid = {"AI", "E", "O", "U", "WQ", "L", "MBP", "FV", "etc", "rest"}
        for lbl in result:
            assert lbl in valid

    def test_unknown_word_vowel_approximation(self, cmu_dict):
        # "A" is a vowel letter → AI
        result = word_to_papagayo("AAA", cmu_dict)
        assert all(lbl == "AI" for lbl in result)

    def test_unknown_word_consonant_approximation(self, cmu_dict):
        # All consonant letters → etc
        result = word_to_papagayo("BBC", cmu_dict)
        assert all(lbl == "etc" for lbl in result)


# ── T009: phoneme timing distribution ────────────────────────────────────────

class TestDistributePhoneme:
    def test_total_duration_exact(self):
        phonemes = ["AI", "L", "O"]
        marks = distribute_phoneme_timing(phonemes, 1000, 2000)
        total = marks[-1].end_ms - marks[0].start_ms
        assert total == 1000

    def test_starts_at_start_ms(self):
        marks = distribute_phoneme_timing(["AI", "L"], 500, 1500)
        assert marks[0].start_ms == 500

    def test_ends_at_end_ms(self):
        marks = distribute_phoneme_timing(["AI", "L"], 500, 1500)
        assert marks[-1].end_ms == 1500

    def test_contiguous_no_gaps(self):
        marks = distribute_phoneme_timing(["AI", "L", "O"], 0, 3000)
        for a, b in zip(marks, marks[1:]):
            assert a.end_ms == b.start_ms

    def test_no_transitions_inserted(self):
        # No transition phonemes — just the actual mouth shapes
        marks = distribute_phoneme_timing(["AI", "L"], 0, 1000)
        labels = [m.label for m in marks]
        assert labels == ["AI", "L"]

    def test_no_transition_between_same_category(self):
        # Two vowels: AI → E, no transition
        marks = distribute_phoneme_timing(["AI", "E"], 0, 1000)
        labels = [m.label for m in marks]
        assert labels == ["AI", "E"]

    def test_no_transition_between_two_consonants(self):
        # L → MBP both consonants
        marks = distribute_phoneme_timing(["L", "MBP"], 0, 1000)
        labels = [m.label for m in marks]
        assert labels == ["L", "MBP"]

    def test_vowels_longer_than_consonants(self):
        marks = distribute_phoneme_timing(["AI", "L"], 0, 1000)
        # Find AI and L (ignoring etc transitions)
        ai_mark = next(m for m in marks if m.label == "AI")
        l_mark = next(m for m in marks if m.label == "L")
        assert (ai_mark.end_ms - ai_mark.start_ms) > (l_mark.end_ms - l_mark.start_ms)

    def test_empty_phonemes_returns_empty(self):
        assert distribute_phoneme_timing([], 0, 1000) == []

    def test_zero_duration_returns_empty(self):
        assert distribute_phoneme_timing(["AI"], 1000, 1000) == []

    def test_single_phoneme_spans_full_duration(self):
        marks = distribute_phoneme_timing(["AI"], 100, 600)
        assert len(marks) == 1
        assert marks[0].start_ms == 100
        assert marks[0].end_ms == 600

    def test_all_marks_are_phoneme_marks(self):
        marks = distribute_phoneme_timing(["AI", "L", "E"], 0, 3000)
        for m in marks:
            assert isinstance(m, PhonemeMark)


# ── T010: PhonemeAnalyzer with mocked WhisperX ───────────────────────────────

class TestPhonemeAnalyzer:
    """Tests using a mock WhisperX to avoid real model downloads."""

    @pytest.fixture()
    def mock_whisperx(self):
        """Patch whisperx module at the phonemes module level."""
        mock_wx = MagicMock()

        # Transcribe result: "HELLO WORLD" timed at 1s–3s
        mock_wx.load_model.return_value.transcribe.return_value = {
            "segments": [{"text": "hello world", "start": 1.0, "end": 3.0}],
            "language": "en",
        }
        # Align result: word-level timestamps
        mock_wx.load_audio.return_value = [0.0] * 160000  # 10s at 16kHz
        mock_wx.load_align_model.return_value = (MagicMock(), MagicMock())
        mock_wx.align.return_value = {
            "word_segments": [
                {"word": "hello", "start": 1.0, "end": 2.0, "score": 0.9},
                {"word": "world", "start": 2.1, "end": 3.0, "score": 0.85},
            ]
        }
        return mock_wx

    @pytest.fixture()
    def analyzer(self, mock_whisperx):
        with patch.dict("sys.modules", {"whisperx": mock_whisperx}):
            from src.analyzer.phonemes import PhonemeAnalyzer
            a = PhonemeAnalyzer(model_name="base")
            # Inject a tiny cmudict
            a._cmu_dict = {
                "hello": [["HH", "AH0", "L", "OW1"]],
                "world": [["W", "ER1", "L", "D"]],
            }
            yield a, mock_whisperx

    def test_analyze_returns_phoneme_result(self, analyzer):
        a, mock_wx = analyzer
        with patch.dict("sys.modules", {"whisperx": mock_wx}):
            result = a.analyze("/fake/vocals.wav", "/fake/song.mp3")
        assert result is not None
        from src.analyzer.phonemes import PhonemeResult
        assert isinstance(result, PhonemeResult)

    def test_word_track_contains_words(self, analyzer):
        a, mock_wx = analyzer
        with patch.dict("sys.modules", {"whisperx": mock_wx}):
            result = a.analyze("/fake/vocals.wav", "/fake/song.mp3")
        assert len(result.word_track.marks) == 2
        labels = [m.label for m in result.word_track.marks]
        assert labels == ["HELLO", "WORLD"]

    def test_word_marks_timing(self, analyzer):
        a, mock_wx = analyzer
        with patch.dict("sys.modules", {"whisperx": mock_wx}):
            result = a.analyze("/fake/vocals.wav", "/fake/song.mp3")
        hello_mark = result.word_track.marks[0]
        assert hello_mark.start_ms == 1000
        assert hello_mark.end_ms == 2000

    def test_phoneme_track_not_empty(self, analyzer):
        a, mock_wx = analyzer
        with patch.dict("sys.modules", {"whisperx": mock_wx}):
            result = a.analyze("/fake/vocals.wav", "/fake/song.mp3")
        assert len(result.phoneme_track.marks) > 0

    def test_phoneme_track_valid_labels(self, analyzer):
        valid = {"AI", "E", "O", "U", "WQ", "L", "MBP", "FV", "etc", "rest"}
        a, mock_wx = analyzer
        with patch.dict("sys.modules", {"whisperx": mock_wx}):
            result = a.analyze("/fake/vocals.wav", "/fake/song.mp3")
        for pm in result.phoneme_track.marks:
            assert pm.label in valid, f"Invalid phoneme label: {pm.label}"

    def test_lyrics_source_auto_by_default(self, analyzer):
        a, mock_wx = analyzer
        with patch.dict("sys.modules", {"whisperx": mock_wx}):
            result = a.analyze("/fake/vocals.wav", "/fake/song.mp3")
        assert result.word_track.lyrics_source == "auto"

    def test_no_vocals_returns_none(self, analyzer):
        a, mock_wx = analyzer
        # Override align to return empty
        mock_wx.align.return_value = {"word_segments": []}
        mock_wx.load_model.return_value.transcribe.return_value = {
            "segments": [], "language": "en"
        }
        with patch.dict("sys.modules", {"whisperx": mock_wx}):
            result = a.analyze("/fake/vocals.wav", "/fake/song.mp3")
        assert result is None

    def test_no_whisperx_raises_runtime_error(self):
        from src.analyzer.phonemes import PhonemeAnalyzer
        a = PhonemeAnalyzer()
        with patch.dict("sys.modules", {"whisperx": None}):
            with pytest.raises((RuntimeError, ImportError)):
                a.analyze("/fake/vocals.wav", "/fake/song.mp3")


# ── T012: JSON serialization / deserialization ────────────────────────────────

class TestPhonemeResultSerialization:
    @pytest.fixture()
    def sample_result(self):
        return PhonemeResult(
            lyrics_block=LyricsBlock(text="HELLO WORLD", start_ms=1000, end_ms=3000),
            word_track=WordTrack(
                name="whisperx-words",
                marks=[
                    WordMark(label="HELLO", start_ms=1000, end_ms=2000),
                    WordMark(label="WORLD", start_ms=2100, end_ms=3000),
                ],
                lyrics_source="auto",
            ),
            phoneme_track=PhonemeTrack(
                name="whisperx-phonemes",
                marks=[
                    PhonemeMark(label="AI", start_ms=1000, end_ms=1500),
                    PhonemeMark(label="etc", start_ms=1500, end_ms=2000),
                ],
            ),
            source_file="/fake/song.mp3",
            language="en",
            model_name="base",
        )

    def test_round_trip_preserves_word_marks(self, sample_result):
        d = sample_result.to_dict()
        restored = PhonemeResult.from_dict(d)
        assert len(restored.word_track.marks) == 2
        assert restored.word_track.marks[0].label == "HELLO"
        assert restored.word_track.marks[0].start_ms == 1000

    def test_round_trip_preserves_phoneme_marks(self, sample_result):
        d = sample_result.to_dict()
        restored = PhonemeResult.from_dict(d)
        assert len(restored.phoneme_track.marks) == 2
        assert restored.phoneme_track.marks[0].label == "AI"

    def test_round_trip_preserves_lyrics_block(self, sample_result):
        d = sample_result.to_dict()
        restored = PhonemeResult.from_dict(d)
        assert restored.lyrics_block.text == "HELLO WORLD"
        assert restored.lyrics_block.start_ms == 1000
        assert restored.lyrics_block.end_ms == 3000

    def test_round_trip_preserves_metadata(self, sample_result):
        d = sample_result.to_dict()
        restored = PhonemeResult.from_dict(d)
        assert restored.language == "en"
        assert restored.model_name == "base"
        assert restored.source_file == "/fake/song.mp3"

    def test_analysis_result_round_trip_with_phonemes(self, sample_result, tmp_path):
        """AnalysisResult round-trips through export.py with phoneme_result."""
        from src.analyzer.result import AnalysisResult
        from src import export as export_mod

        ar = AnalysisResult(
            schema_version="1.0",
            source_file="/fake/song.mp3",
            filename="song.mp3",
            duration_ms=30000,
            sample_rate=44100,
            estimated_tempo_bpm=120.0,
            run_timestamp="2026-03-22T10:00:00",
            algorithms=[],
            timing_tracks=[],
            phoneme_result=sample_result,
        )
        out = tmp_path / "test.json"
        export_mod.write(ar, str(out))
        loaded = export_mod.read(str(out))
        assert loaded.phoneme_result is not None
        assert loaded.phoneme_result.language == "en"
        assert len(loaded.phoneme_result.word_track.marks) == 2

    def test_analysis_result_round_trip_without_phonemes(self, tmp_path):
        """AnalysisResult with phoneme_result=None loads without error."""
        from src.analyzer.result import AnalysisResult
        from src import export as export_mod

        ar = AnalysisResult(
            schema_version="1.0",
            source_file="/fake/song.mp3",
            filename="song.mp3",
            duration_ms=30000,
            sample_rate=44100,
            estimated_tempo_bpm=120.0,
            run_timestamp="2026-03-22T10:00:00",
            algorithms=[],
            timing_tracks=[],
            phoneme_result=None,
        )
        out = tmp_path / "test_none.json"
        export_mod.write(ar, str(out))
        loaded = export_mod.read(str(out))
        assert loaded.phoneme_result is None

    def test_backward_compat_missing_phoneme_result(self, tmp_path):
        """Old JSON without phoneme_result field loads with phoneme_result=None."""
        import json
        old_json = {
            "schema_version": "1.0",
            "source_file": "/fake/song.mp3",
            "filename": "song.mp3",
            "duration_ms": 10000,
            "sample_rate": 44100,
            "estimated_tempo_bpm": 120.0,
            "run_timestamp": "2026-01-01T00:00:00",
            "algorithms": [],
            "timing_tracks": [],
            # No phoneme_result key
        }
        p = tmp_path / "old.json"
        p.write_text(json.dumps(old_json))
        from src import export as export_mod
        loaded = export_mod.read(str(p))
        assert loaded.phoneme_result is None
