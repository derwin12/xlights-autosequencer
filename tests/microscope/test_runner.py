"""Tests for ``src.microscope.runner``.

Two layers:
  * Unit tests with ``generate_sequence`` and ``parse`` monkeypatched —
    fast, no audio fixture required, exercise config wiring +
    ``to_dict`` JSON shape + ``config_overrides`` validation.
  * Integration tests (marked ``slow``) that drive the real generator
    over a CC0 fixture. Auto-skipped when the fixture isn't downloaded
    so the unit tests still run on a fresh checkout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.models import Placement, SequenceSummary
from src.microscope import runner as runner_module
from src.microscope.runner import MicroscopeResult, run_song


# ---------------------------------------------------------------------------
# Fixture detection
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FUNSHINE_MP3 = _REPO_ROOT / "tests" / "fixtures" / "cc0_music" / "funshine.mp3"
_REFERENCE_LAYOUT = _REPO_ROOT / "tests" / "fixtures" / "reference" / "layout.xml"

_HAS_INTEGRATION_FIXTURES = _FUNSHINE_MP3.is_file() and _REFERENCE_LAYOUT.is_file()


# ---------------------------------------------------------------------------
# Unit tests (mocked generator + parser)
# ---------------------------------------------------------------------------


def _make_summary() -> SequenceSummary:
    return SequenceSummary(
        song_id="",
        source_label="ours",
        duration_ms=10_000,
        placements=(
            Placement(
                start_ms=0,
                end_ms=5_000,
                effect_type="Plasma",
                model_name="MatrixCenter",
                palette_colors=("#FF0000", "#00FF00"),
                layer_index=0,
            ),
            Placement(
                start_ms=5_000,
                end_ms=10_000,
                effect_type="Bars",
                model_name="ArchLeft",
                palette_colors=("#0000FF",),
                layer_index=0,
            ),
        ),
        model_names=("MatrixCenter", "ArchLeft"),
        inferred_prop_types={"MatrixCenter": "matrix", "ArchLeft": "arch"},
    )


@pytest.fixture
def mocked_runner(monkeypatch, tmp_path):
    """Patch ``generate_sequence`` and ``parse`` so unit tests don't
    require audio fixtures or a real layout. The fake XSQ is a stub
    file written to ``tmp_path`` — its existence is what the test
    asserts on, not its contents.
    """
    captured: dict = {}

    def fake_generate_sequence(config):
        captured["config"] = config
        config.output_dir.mkdir(parents=True, exist_ok=True)
        xsq = config.output_dir / "sequence.xsq"
        xsq.write_bytes(b"<xsq/>")
        return xsq

    def fake_parse(
        path,
        song_id="",
        source_label="ours",
        layout_path=None,
        layout_group_members=None,
    ):
        captured["parsed_path"] = Path(path)
        captured["parsed_layout_path"] = (
            Path(layout_path) if layout_path is not None else None
        )
        captured["parsed_layout_group_members"] = layout_group_members
        return _make_summary()

    def fake_derive_layout_group_members(layout_path):
        captured["derived_layout_path"] = Path(layout_path)
        return {"08_HERO_FAKE": ("FakeProp",)}

    monkeypatch.setattr(runner_module, "generate_sequence", fake_generate_sequence)
    monkeypatch.setattr(runner_module, "parse", fake_parse)
    monkeypatch.setattr(
        runner_module,
        "_derive_layout_group_members",
        fake_derive_layout_group_members,
    )
    return captured


def test_run_song_uses_default_variation_seed(mocked_runner, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")

    result = run_song(audio, layout, tmp_path)

    assert isinstance(result, MicroscopeResult)
    assert result.slug == "song"
    assert result.config_snapshot["variation_seed"] == 42
    # Production-parity defaults are pinned in _build_config.
    assert result.config_snapshot["transition_mode"] == "subtle"
    assert result.config_snapshot["curves_mode"] == "none"
    assert result.config_snapshot["genre"] == "pop"
    assert result.config_snapshot["occasion"] == "general"


def test_run_song_output_dir_layout(mocked_runner, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")

    result = run_song(audio, layout, tmp_path)

    expected_dir = tmp_path / "microscope" / "song"
    assert expected_dir.is_dir()
    assert Path(result.xsq_path).parent == expected_dir.resolve()


def test_run_song_applies_overrides(mocked_runner, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")

    result = run_song(
        audio,
        layout,
        tmp_path,
        config_overrides={"variation_seed": 99, "genre": "rock"},
    )

    assert result.config_snapshot["variation_seed"] == 99
    assert result.config_snapshot["genre"] == "rock"


def test_run_song_rejects_unknown_overrides(mocked_runner, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown GenerationConfig field"):
        run_song(
            audio,
            layout,
            tmp_path,
            config_overrides={"bogus_field": 1},
        )


def test_run_song_coerces_path_overrides(mocked_runner, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")
    custom_story = tmp_path / "story.json"

    # Pass story_path as a string; runner should coerce to Path.
    result = run_song(
        audio,
        layout,
        tmp_path,
        config_overrides={"story_path": str(custom_story)},
    )

    config = mocked_runner["config"]
    assert isinstance(config.story_path, Path)
    assert config.story_path == custom_story
    # story_path is a path field — excluded from config_snapshot.
    assert "story_path" not in result.config_snapshot


def test_run_song_metrics_dict_populated(mocked_runner, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")

    result = run_song(audio, layout, tmp_path)

    # Sanity: registry is non-empty after _import_all_metrics, and at
    # least the new microscope metrics resolved without raising.
    assert "palette_luminance_mean" in result.metrics
    assert "distinct_effect_count" in result.metrics
    assert result.metrics["distinct_effect_count"].value == 2


def test_to_dict_is_json_serializable(mocked_runner, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")

    result = run_song(audio, layout, tmp_path)
    payload = result.to_dict()

    # Round-trips through json.dumps without raising.
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["slug"] == "song"
    assert decoded["config_snapshot"]["variation_seed"] == 42
    assert "summary" not in decoded
    # Metric entries have the documented shape.
    sample_metric = next(iter(decoded["metrics"].values()))
    assert set(sample_metric.keys()) == {"value", "kind", "reliability", "payload"}


# ---------------------------------------------------------------------------
# Integration tests (real generator) — slow, fixture-gated
# ---------------------------------------------------------------------------


_pytestmark_integration = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not _HAS_INTEGRATION_FIXTURES,
        reason="CC0 fixture tests/fixtures/cc0_music/funshine.mp3 not downloaded",
    ),
]


@pytest.mark.slow
@pytest.mark.skipif(
    not _HAS_INTEGRATION_FIXTURES,
    reason="CC0 fixture tests/fixtures/cc0_music/funshine.mp3 not downloaded",
)
def test_integration_funshine_basic(tmp_path):
    result = run_song(_FUNSHINE_MP3, _REFERENCE_LAYOUT, tmp_path)

    assert result.slug == "funshine"
    assert Path(result.xsq_path).is_file()
    assert result.metrics  # non-empty
    assert result.config_snapshot["variation_seed"] == 42


@pytest.mark.slow
@pytest.mark.skipif(
    not _HAS_INTEGRATION_FIXTURES,
    reason="CC0 fixture tests/fixtures/cc0_music/funshine.mp3 not downloaded",
)
def test_integration_funshine_deterministic_same_seed(tmp_path):
    a = run_song(_FUNSHINE_MP3, _REFERENCE_LAYOUT, tmp_path / "a")
    b = run_song(_FUNSHINE_MP3, _REFERENCE_LAYOUT, tmp_path / "b")

    common = set(a.metrics) & set(b.metrics)
    scalar_diffs = []
    for name in common:
        va = a.metrics[name].value
        vb = b.metrics[name].value
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            if abs(va - vb) > 1e-9:
                scalar_diffs.append((name, va, vb))
    assert not scalar_diffs, f"Non-deterministic metrics: {scalar_diffs}"


@pytest.mark.slow
@pytest.mark.skipif(
    not _HAS_INTEGRATION_FIXTURES,
    reason="CC0 fixture tests/fixtures/cc0_music/funshine.mp3 not downloaded",
)
def test_integration_funshine_seed_has_effect(tmp_path):
    """The variation_seed must produce some observable change in the
    generated XSQ. We compare at the placement level, not the metric
    level: empirically on ``funshine`` the seed perturbs ~3% of the
    68 placements, which is below the resolution of every scalar
    metric currently registered (none of them move by ≥ 1e-3). The
    spec's intent — "the seed has an effect" — is satisfied as long
    as the underlying SequenceSummary shifts; the metric-level
    probe is the responsibility of the §9 sensitivity gate, which
    can use a different fixture or larger seed delta.
    """
    a = run_song(_FUNSHINE_MP3, _REFERENCE_LAYOUT, tmp_path / "a")
    b = run_song(
        _FUNSHINE_MP3,
        _REFERENCE_LAYOUT,
        tmp_path / "b",
        config_overrides={"variation_seed": 9999},
    )

    diffs = 0
    for pa, pb in zip(a.summary.placements, b.summary.placements):
        if (
            pa.effect_type != pb.effect_type
            or pa.model_name != pb.model_name
            or pa.palette_colors != pb.palette_colors
        ):
            diffs += 1
    assert diffs > 0, (
        "Flipping variation_seed (42 → 9999) produced no placement-level "
        "differences in the generated XSQ — the seed is not threading to "
        "the placer (Phase 1 plumbing regression)"
    )


def test_run_song_passes_layout_path_to_parser(mocked_runner, tmp_path):
    """OpenSpec ``microscope-placement-coverage`` §4.1: the runner must
    forward its ``layout_path`` argument into ``parse()`` so the parsed
    summary carries ``layout_model_names``."""
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    layout = tmp_path / "layout.xml"
    layout.write_text("<layout/>", encoding="utf-8")

    run_song(audio, layout, tmp_path)

    assert mocked_runner["parsed_layout_path"] == Path(layout), (
        "run_song must forward its layout_path into parse() so the parsed "
        "summary carries layout_model_names"
    )


@pytest.mark.slow
@pytest.mark.skipif(
    not _HAS_INTEGRATION_FIXTURES,
    reason="CC0 fixture tests/fixtures/cc0_music/funshine.mp3 not downloaded",
)
def test_integration_layout_universe_populated(tmp_path):
    """End-to-end check: the parsed summary's layout universe contains every
    model defined in the reference layout XML, regardless of placement."""
    result = run_song(_FUNSHINE_MP3, _REFERENCE_LAYOUT, tmp_path)
    assert "MatrixCenter" in result.summary.layout_model_names
    assert "MegaTree" in result.summary.layout_model_names
    assert len(result.summary.layout_model_names) == 9
