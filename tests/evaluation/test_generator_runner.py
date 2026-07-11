"""Tests for src.evaluation.generator_runner — written before the implementation exists."""
from __future__ import annotations

import pytest
from pathlib import Path


# ── Module structure tests (always run) ─────────────────────────────────────


def test_module_is_importable():
    """generator_runner must be importable from src.evaluation."""
    import src.evaluation.generator_runner  # noqa: F401


def test_generator_error_exists():
    """GeneratorError must be a public exception class in the module."""
    from src.evaluation.generator_runner import GeneratorError

    assert issubclass(GeneratorError, Exception)


def test_run_is_callable():
    """run() must exist and be callable with (song_id, audio_path, audio_hash) args."""
    from src.evaluation import generator_runner

    assert callable(generator_runner.run)


def test_derive_seed_strips_prefix():
    """_derive_seed must strip 'md5:' prefix and parse first 8 hex chars."""
    from src.evaluation.generator_runner import _derive_seed

    # md5: + 3f4b1a2c... → int("3f4b1a2c", 16)
    assert _derive_seed("md5:3f4b1a2cdeadbeef") == int("3f4b1a2c", 16)


def test_derive_seed_short_hash():
    """_derive_seed must handle hashes shorter than 8 chars after prefix."""
    from src.evaluation.generator_runner import _derive_seed

    # Only 4 hex chars after prefix → parse those 4
    assert _derive_seed("md5:abcd") == int("abcd", 16)


def test_run_raises_generator_error_on_missing_audio(tmp_path):
    """run() must raise GeneratorError when audio_path does not exist."""
    from src.evaluation.generator_runner import GeneratorError, run

    missing = tmp_path / "nonexistent.mp3"
    with pytest.raises(GeneratorError, match="audio_path does not exist"):
        run("song-id", missing, "md5:deadbeef00000000")


# ── Deterministic / integration tests (skipped without prerequisites) ────────

_FIXTURE_WAV = Path(__file__).parent.parent / "fixtures" / "beat_120bpm_10s.wav"
_FIXTURE_LAYOUT = Path(__file__).parent.parent / "fixtures" / "generate" / "mock_layout.xml"
_FAKE_HASH = "md5:aabbccdd11223344"

_SKIP_INTEGRATION = pytest.mark.skipif(
    not (_FIXTURE_WAV.exists() and _FIXTURE_LAYOUT.exists()),
    reason="Integration fixtures not available (beat_120bpm_10s.wav or mock_layout.xml missing)",
)


@_SKIP_INTEGRATION
def test_run_returns_bytes():
    """run() must return bytes (the .xsq XML content) for a real audio file."""
    from src.evaluation.generator_runner import run

    result = run(
        song_id="test-song",
        audio_path=_FIXTURE_WAV,
        audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT,
    )
    assert isinstance(result, bytes)
    assert len(result) > 0


@_SKIP_INTEGRATION
def test_run_returns_xml_bytes():
    """run() must return valid XML .xsq bytes."""
    from src.evaluation.generator_runner import run

    result = run(
        song_id="test-song",
        audio_path=_FIXTURE_WAV,
        audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT,
    )
    # xsq files start with an XML declaration or <xsequence
    text = result.decode("utf-8")
    assert "xsequence" in text


@_SKIP_INTEGRATION
def test_run_with_lyrics_embeds_lyrics_timing_track():
    """run(..., lyrics=[...]) must thread lyric lines into the .xsq as a
    "Lyrics" timing track — the Export screen's actual bug report."""
    from src.evaluation.generator_runner import run

    lyrics = [
        {"t_ms": 1000, "duration_ms": 2000, "text": "la la placeholder line one"},
    ]
    result = run(
        song_id="test-song",
        audio_path=_FIXTURE_WAV,
        audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT,
        lyrics=lyrics,
    )
    text = result.decode("utf-8")
    assert 'name="Lyrics"' in text
    assert "la la placeholder line one" in text


@_SKIP_INTEGRATION
def test_run_without_lyrics_has_no_lyrics_track():
    """run() with no lyrics arg must not emit a Lyrics timing track."""
    from src.evaluation.generator_runner import run

    result = run(
        song_id="test-song",
        audio_path=_FIXTURE_WAV,
        audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT,
    )
    text = result.decode("utf-8")
    assert 'name="Lyrics"' not in text


@_SKIP_INTEGRATION
def test_deterministic_run_same_bytes():
    """Two calls with the same audio_hash must produce byte-identical .xsq bytes."""
    from src.evaluation.generator_runner import run

    first = run(
        song_id="test-song",
        audio_path=_FIXTURE_WAV,
        audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT,
    )
    second = run(
        song_id="test-song",
        audio_path=_FIXTURE_WAV,
        audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT,
    )
    assert first == second, (
        "Two runs with the same audio_hash produced different .xsq bytes. "
        "Seed or non-deterministic state leak detected."
    )
