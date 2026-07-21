"""Tests for phoneme_align.align_words_and_phonemes' reference-text
selection (lyric_lines vs. lyrics_text vs. free transcription) -- the
actual WhisperX alignment itself is exercised by test_phonemes_lyrics.py
against PhonemeAnalyzer directly."""
from __future__ import annotations

from pathlib import Path

import src.analyzer.phoneme_align as phoneme_align


def _capture_run_in_process(monkeypatch, tmp_path):
    """Monkeypatch _run_in_process to record the lyrics_path it receives
    and, if present, that file's contents at call time -- captured before
    align_words_and_phonemes' finally-block deletes it."""
    captured: dict = {}

    def _fake_run_in_process(audio_path, lyrics_path):
        captured["lyrics_path"] = lyrics_path
        captured["content"] = Path(lyrics_path).read_text(encoding="utf-8") if lyrics_path else None
        return [], [], []

    monkeypatch.setattr(phoneme_align, "_run_in_process", _fake_run_in_process)
    monkeypatch.setattr(phoneme_align, "_discover_vocals_stem", lambda audio_path: None)
    return captured


class TestReferenceTextSelection:
    def test_no_lines_no_text_means_free_transcription(self, monkeypatch, tmp_path):
        captured = _capture_run_in_process(monkeypatch, tmp_path)
        phoneme_align.align_words_and_phonemes("song.mp3")
        assert captured["lyrics_path"] is None

    def test_lyric_lines_alone_forces_alignment(self, monkeypatch, tmp_path):
        captured = _capture_run_in_process(monkeypatch, tmp_path)
        lines = [{"t_ms": 0, "duration_ms": 1000, "text": "first line"},
                 {"t_ms": 1000, "duration_ms": 1000, "text": "second line"}]
        phoneme_align.align_words_and_phonemes("song.mp3", lines)
        assert captured["lyrics_path"] is not None
        assert captured["content"] == "first line\nsecond line"

    def test_lyrics_text_alone_forces_alignment(self, monkeypatch, tmp_path):
        # The bug this fixes: a user-pasted lyrics fallback has no timed
        # lyric_lines (plain text produces no per-line timing), so before
        # this fix it fell through to free transcription -- garbage words
        # (user-confirmed, 2026-07-21) despite real lyrics being available.
        captured = _capture_run_in_process(monkeypatch, tmp_path)
        pasted_text = "verse line one\nverse line two\nchorus line here"
        phoneme_align.align_words_and_phonemes("song.mp3", None, pasted_text)
        assert captured["lyrics_path"] is not None
        assert captured["content"] == pasted_text

    def test_empty_lyric_lines_falls_back_to_lyrics_text(self, monkeypatch, tmp_path):
        captured = _capture_run_in_process(monkeypatch, tmp_path)
        phoneme_align.align_words_and_phonemes("song.mp3", [], "pasted text")
        assert captured["content"] == "pasted text"

    def test_lyric_lines_take_priority_over_lyrics_text(self, monkeypatch, tmp_path):
        captured = _capture_run_in_process(monkeypatch, tmp_path)
        lines = [{"t_ms": 0, "duration_ms": 1000, "text": "timed line"}]
        phoneme_align.align_words_and_phonemes("song.mp3", lines, "should not be used")
        assert captured["content"] == "timed line"

    def test_blank_lyrics_text_means_free_transcription(self, monkeypatch, tmp_path):
        captured = _capture_run_in_process(monkeypatch, tmp_path)
        phoneme_align.align_words_and_phonemes("song.mp3", None, "   \n  ")
        assert captured["lyrics_path"] is None


class TestWarningsPropagation:
    """PhonemeAnalyzer's lyrics-mismatch warning must reach the caller
    instead of being silently discarded (user-reported 2026-07-21: pasted
    lyrics replaced with 'made up' words with no explanation)."""

    def test_warnings_from_run_in_process_are_returned(self, monkeypatch):
        monkeypatch.setattr(phoneme_align, "_discover_vocals_stem", lambda audio_path: None)
        monkeypatch.setattr(
            phoneme_align, "_run_in_process",
            lambda audio_path, lyrics_path: (
                [], [], ["Lyrics mismatch — only 30% of words aligned. Falling back to audio-only."]
            ),
        )
        _, _, warnings = phoneme_align.align_words_and_phonemes("song.mp3", None, "pasted text")
        assert warnings == ["Lyrics mismatch — only 30% of words aligned. Falling back to audio-only."]

    def test_no_warnings_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(phoneme_align, "_discover_vocals_stem", lambda audio_path: None)
        monkeypatch.setattr(
            phoneme_align, "_run_in_process",
            lambda audio_path, lyrics_path: ([], [], []),
        )
        _, _, warnings = phoneme_align.align_words_and_phonemes("song.mp3")
        assert warnings == []
