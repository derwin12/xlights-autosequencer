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


def test_run_pipeline_threads_seed_and_prefs_into_config(monkeypatch, tmp_path):
    """_run_pipeline must stamp the audio-hash seed into
    GenerationConfig.variation_seed (per-song theme/effect variety) and
    thread genre/occasion through to theme selection."""
    from types import SimpleNamespace

    captured: dict = {}

    monkeypatch.setattr("src.analyzer.orchestrator.run_orchestrator",
                        lambda *a, **k: object())
    monkeypatch.setattr("src.grouper.layout.parse_layout",
                        lambda p: SimpleNamespace(props=[]))
    monkeypatch.setattr("src.grouper.classifier.normalize_coords", lambda props: None)
    monkeypatch.setattr("src.grouper.classifier.classify_props", lambda props: None)
    monkeypatch.setattr("src.grouper.grouper.generate_groups", lambda props: [])
    monkeypatch.setattr("src.effects.library.load_effect_library", lambda: object())
    monkeypatch.setattr("src.variants.library.load_variant_library",
                        lambda **k: object())
    monkeypatch.setattr("src.themes.library.load_theme_library", lambda **k: object())

    def fake_build_plan(config, *a, **k):
        captured["config"] = config
        return object()

    def fake_write_xsq(plan, output_path, **k):
        Path(output_path).write_bytes(b"<xsequence/>")

    monkeypatch.setattr("src.generator.plan.build_plan", fake_build_plan)
    monkeypatch.setattr("src.generator.xsq_writer.write_xsq", fake_write_xsq)

    from src.evaluation.generator_runner import _run_pipeline

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    layout = tmp_path / "l.xml"
    layout.write_bytes(b"<x/>")

    result = _run_pipeline(audio, layout, seed=0xAABBCCDD,
                           genre="rock", occasion="christmas")

    assert result == b"<xsequence/>"
    config = captured["config"]
    assert config.variation_seed == 0xAABBCCDD
    assert config.genre == "rock"
    assert config.occasion == "christmas"


def test_run_pipeline_threads_video_path_into_config(monkeypatch, tmp_path):
    """bug-192: video_path from the song record must reach GenerationConfig
    (and therefore _place_video_effect), not silently drop between
    export.py._run_export and the generator pipeline."""
    from types import SimpleNamespace

    captured: dict = {}

    monkeypatch.setattr("src.analyzer.orchestrator.run_orchestrator",
                        lambda *a, **k: object())
    monkeypatch.setattr("src.grouper.layout.parse_layout",
                        lambda p: SimpleNamespace(props=[]))
    monkeypatch.setattr("src.grouper.classifier.normalize_coords", lambda props: None)
    monkeypatch.setattr("src.grouper.classifier.classify_props", lambda props: None)
    monkeypatch.setattr("src.grouper.grouper.generate_groups", lambda props: [])
    monkeypatch.setattr("src.effects.library.load_effect_library", lambda: object())
    monkeypatch.setattr("src.variants.library.load_variant_library",
                        lambda **k: object())
    monkeypatch.setattr("src.themes.library.load_theme_library", lambda **k: object())

    def fake_build_plan(config, *a, **k):
        captured["config"] = config
        return object()

    def fake_write_xsq(plan, output_path, **k):
        Path(output_path).write_bytes(b"<xsequence/>")

    monkeypatch.setattr("src.generator.plan.build_plan", fake_build_plan)
    monkeypatch.setattr("src.generator.xsq_writer.write_xsq", fake_write_xsq)

    from src.evaluation.generator_runner import _run_pipeline

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    layout = tmp_path / "l.xml"
    layout.write_bytes(b"<x/>")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    _run_pipeline(audio, layout, seed=1, video_path=video)

    config = captured["config"]
    assert config.video_path == video


def test_run_pipeline_threads_story_path_into_config(monkeypatch, tmp_path):
    """story_path (the already-classified section roles/energies written by
    the review/analyze flow) must reach GenerationConfig so build_plan()
    uses it instead of re-deriving unclassified section energies from raw
    detector boundaries (fixed 2026-07-21 -- this was the root cause of
    "Sections" showing raw segmentino/QM labels like N1/A_1/qm_boundary
    instead of verse/chorus in the exported .xsq)."""
    from types import SimpleNamespace

    captured: dict = {}

    monkeypatch.setattr("src.analyzer.orchestrator.run_orchestrator",
                        lambda *a, **k: object())
    monkeypatch.setattr("src.grouper.layout.parse_layout",
                        lambda p: SimpleNamespace(props=[]))
    monkeypatch.setattr("src.grouper.classifier.normalize_coords", lambda props: None)
    monkeypatch.setattr("src.grouper.classifier.classify_props", lambda props: None)
    monkeypatch.setattr("src.grouper.grouper.generate_groups", lambda props: [])
    monkeypatch.setattr("src.effects.library.load_effect_library", lambda: object())
    monkeypatch.setattr("src.variants.library.load_variant_library",
                        lambda **k: object())
    monkeypatch.setattr("src.themes.library.load_theme_library", lambda **k: object())

    def fake_build_plan(config, *a, **k):
        captured["config"] = config
        return object()

    def fake_write_xsq(plan, output_path, **k):
        Path(output_path).write_bytes(b"<xsequence/>")

    monkeypatch.setattr("src.generator.plan.build_plan", fake_build_plan)
    monkeypatch.setattr("src.generator.xsq_writer.write_xsq", fake_write_xsq)

    from src.evaluation.generator_runner import _run_pipeline

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    layout = tmp_path / "l.xml"
    layout.write_bytes(b"<x/>")
    story = tmp_path / "a_story.json"
    story.write_text('{"sections": []}')

    _run_pipeline(audio, layout, seed=1, story_path=story)

    config = captured["config"]
    assert config.story_path == story


def test_run_pipeline_passes_layout_into_build_plan(monkeypatch, tmp_path):
    """build_plan's layout kwarg must receive the parsed Layout object, not
    the default None -- Moving Head placement is gated on
    `config.moving_head_effects and layout is not None` (src/generator/
    plan.py), so a dropped layout arg silently skips Moving Head effects
    even when the imported layout has a valid MH group."""
    from types import SimpleNamespace

    captured: dict = {}
    fake_layout = SimpleNamespace(props=[])

    monkeypatch.setattr("src.analyzer.orchestrator.run_orchestrator",
                        lambda *a, **k: object())
    monkeypatch.setattr("src.grouper.layout.parse_layout",
                        lambda p: fake_layout)
    monkeypatch.setattr("src.grouper.classifier.normalize_coords", lambda props: None)
    monkeypatch.setattr("src.grouper.classifier.classify_props", lambda props: None)
    monkeypatch.setattr("src.grouper.grouper.generate_groups", lambda props: [])
    monkeypatch.setattr("src.effects.library.load_effect_library", lambda: object())
    monkeypatch.setattr("src.variants.library.load_variant_library",
                        lambda **k: object())
    monkeypatch.setattr("src.themes.library.load_theme_library", lambda **k: object())

    def fake_build_plan(config, *a, **k):
        captured["layout"] = k.get("layout")
        return object()

    def fake_write_xsq(plan, output_path, **k):
        Path(output_path).write_bytes(b"<xsequence/>")

    monkeypatch.setattr("src.generator.plan.build_plan", fake_build_plan)
    monkeypatch.setattr("src.generator.xsq_writer.write_xsq", fake_write_xsq)

    from src.evaluation.generator_runner import _run_pipeline

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    layout_path = tmp_path / "l.xml"
    layout_path.write_bytes(b"<x/>")

    _run_pipeline(audio, layout_path, seed=1)

    assert captured["layout"] is fake_layout


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


def test_variation_seed_override_reproduces_deterministically():
    """An explicit variation_seed must reproduce the same output on repeat,
    independent of the audio_hash-derived default (the "reroll" feature)."""
    from src.evaluation.generator_runner import run

    first = run(
        song_id="test-song", audio_path=_FIXTURE_WAV, audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT, variation_seed=123,
    )
    second = run(
        song_id="test-song", audio_path=_FIXTURE_WAV, audio_hash=_FAKE_HASH,
        layout_path=_FIXTURE_LAYOUT, variation_seed=123,
    )
    assert first == second


def test_variation_seed_override_reaches_generation_config(monkeypatch, tmp_path):
    """run() must pass an explicit variation_seed through to _run_pipeline's
    seed param instead of always deriving it from audio_hash."""
    from types import SimpleNamespace
    import src.evaluation.generator_runner as gr

    captured: dict = {}

    def fake_run_pipeline(audio_path, layout_path, seed, **kwargs):
        captured["seed"] = seed
        return b"<xsequence/>"

    monkeypatch.setattr(gr, "_run_pipeline", fake_run_pipeline)

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    layout = tmp_path / "l.xml"
    layout.write_bytes(b"<x/>")

    gr.run(song_id="s", audio_path=audio, audio_hash=_FAKE_HASH,
           layout_path=layout, variation_seed=999)
    assert captured["seed"] == 999
