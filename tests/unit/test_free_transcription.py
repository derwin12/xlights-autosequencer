"""Unit tests for src.analyzer.free_transcription."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from src.analyzer.free_transcription import derive_vocal_regions, transcribe_free
from src.analyzer.phonemes import WordMark


# ── transcribe_free ────────────────────────────────────────────────────────────


def test_transcribe_free_raises_on_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.wav"
    with pytest.raises(FileNotFoundError):
        transcribe_free(str(missing))


def _install_fake_whisperx(monkeypatch, segments, word_segments) -> dict:
    """Stub whisperx in sys.modules so transcribe_free runs without real audio."""
    calls: dict = {"load_model": [], "load_align_model": [], "align": [], "load_audio": []}

    fake = types.ModuleType("whisperx")

    def load_audio(path):
        calls["load_audio"].append(path)
        return b"audio-bytes"

    class FakeModel:
        def transcribe(self, audio, batch_size=8):
            return {"segments": list(segments)}

    def load_model(name, device, compute_type=None, language=None):
        calls["load_model"].append((name, device, compute_type, language))
        return FakeModel()

    def load_align_model(language_code=None, device=None, model_name=None):
        calls["load_align_model"].append((language_code, device, model_name))
        return ("align-model", {"meta": "data"})

    def align(segs, model, metadata, audio, device):
        calls["align"].append({"n_segs": len(list(segs)), "device": device})
        return {"word_segments": list(word_segments)}

    fake.load_audio = load_audio
    fake.load_model = load_model
    fake.load_align_model = load_align_model
    fake.align = align

    monkeypatch.setitem(sys.modules, "whisperx", fake)
    return calls


def test_transcribe_free_returns_wordmarks(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"")

    segments = [{"start": 0.0, "end": 1.5, "text": "hello world"}]
    word_segments = [
        {"word": "hello", "start": 0.10, "end": 0.45},
        {"word": "world", "start": 0.55, "end": 0.95},
    ]
    _install_fake_whisperx(monkeypatch, segments, word_segments)

    marks = transcribe_free(str(audio), duration_s=2.0)

    assert len(marks) == 2
    assert all(isinstance(m, WordMark) for m in marks)
    assert [m.label for m in marks] == ["HELLO", "WORLD"]
    assert marks[0].start_ms == 100
    assert marks[0].end_ms == 450
    assert marks[1].start_ms == 550
    assert marks[1].end_ms == 950


def test_transcribe_free_skips_words_without_timestamps(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"")

    word_segments = [
        {"word": "ok", "start": 0.0, "end": 0.2},
        {"word": "no_start", "end": 1.0},
        {"word": "no_end", "start": 1.5},
        {"word": "", "start": 2.0, "end": 2.1},
        {"word": "good", "start": 3.0, "end": 3.4},
    ]
    _install_fake_whisperx(monkeypatch, [{"start": 0.0, "end": 4.0}], word_segments)

    marks = transcribe_free(str(audio), duration_s=4.0)
    assert [m.label for m in marks] == ["OK", "GOOD"]


def test_transcribe_free_returns_empty_on_no_segments(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"")
    _install_fake_whisperx(monkeypatch, [], [])

    marks = transcribe_free(str(audio), duration_s=4.0)
    assert marks == []


def test_transcribe_free_passes_language_to_model(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"")
    calls = _install_fake_whisperx(
        monkeypatch,
        [{"start": 0.0, "end": 1.0}],
        [{"word": "hi", "start": 0.0, "end": 0.3}],
    )

    transcribe_free(str(audio), language="es", device="cuda", duration_s=1.0)

    assert calls["load_model"][0][3] == "es"
    assert calls["load_model"][0][1] == "cuda"
    assert calls["load_align_model"][0][0] == "es"


def test_transcribe_free_sorts_words_by_start(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"")
    word_segments = [
        {"word": "second", "start": 1.0, "end": 1.4},
        {"word": "first", "start": 0.1, "end": 0.5},
        {"word": "third", "start": 2.0, "end": 2.3},
    ]
    _install_fake_whisperx(monkeypatch, [{"start": 0.0, "end": 3.0}], word_segments)

    marks = transcribe_free(str(audio), duration_s=3.0)
    assert [m.label for m in marks] == ["FIRST", "SECOND", "THIRD"]


# ── derive_vocal_regions ───────────────────────────────────────────────────────


def _wm(start_ms: int, end_ms: int, label: str = "X") -> WordMark:
    return WordMark(label=label, start_ms=start_ms, end_ms=end_ms)


def test_derive_vocal_regions_empty() -> None:
    assert derive_vocal_regions([]) == []


def test_derive_vocal_regions_single_word() -> None:
    regions = derive_vocal_regions([_wm(100, 400)])
    assert regions == [(0.1, 0.4)]


def test_derive_vocal_regions_groups_within_gap() -> None:
    regions = derive_vocal_regions([_wm(0, 500), _wm(1500, 2000)])
    assert regions == [(0.0, 2.0)]


def test_derive_vocal_regions_splits_on_large_gap() -> None:
    regions = derive_vocal_regions([_wm(0, 500), _wm(5500, 6000)])
    assert regions == [(0.0, 0.5), (5.5, 6.0)]


def test_derive_vocal_regions_custom_gap() -> None:
    words = [_wm(0, 500), _wm(2000, 2500)]
    assert derive_vocal_regions(words, gap_s=1.0) == [(0.0, 0.5), (2.0, 2.5)]
    assert derive_vocal_regions(words, gap_s=2.0) == [(0.0, 2.5)]
