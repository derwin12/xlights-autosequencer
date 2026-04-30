"""Tests for ``src.microscope.panel``.

Two layers, mirroring ``test_runner.py``:
  * Unit tests use ``monkeypatch`` to replace ``run_song`` with a stub
    so manifest parsing, fixture-resolution, layout validation, and the
    download-fallback path are exercised without invoking the real
    generator.
  * Integration tests (``slow``) drive the actual generator over the
    full reference panel. Auto-skipped when any of the four CC0 MP3s
    isn't downloaded so unit tests stay green on a fresh checkout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.models import Placement, SequenceSummary
from src.microscope import panel as panel_module
from src.microscope.panel import run_panel
from src.microscope.runner import MicroscopeResult


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CC0_DIR = _REPO_ROOT / "tests" / "fixtures" / "cc0_music"
_REFERENCE_LAYOUT = _REPO_ROOT / "tests" / "fixtures" / "reference" / "layout.xml"
_PANEL_MANIFEST = _REPO_ROOT / "tests" / "fixtures" / "reference" / "panel_manifest.json"

_PANEL_SLUGS = ("funshine", "maple_leaf_rag", "nostalgic_piano", "space_ambience")
_HAS_PANEL_FIXTURES = (
    _REFERENCE_LAYOUT.is_file()
    and all((_CC0_DIR / f"{slug}.mp3").is_file() for slug in _PANEL_SLUGS)
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_summary() -> SequenceSummary:
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
                palette_colors=("#FF0000",),
                layer_index=0,
            ),
        ),
        model_names=("MatrixCenter",),
        inferred_prop_types={"MatrixCenter": "matrix"},
    )


def _stub_result(slug: str, output_dir: Path) -> MicroscopeResult:
    return MicroscopeResult(
        slug=slug,
        audio_path=str(output_dir / f"{slug}.mp3"),
        xsq_path=str(output_dir / "microscope" / slug / "sequence.xsq"),
        summary=_stub_summary(),
        metrics={},
        generated_at="2026-04-29T00:00:00Z",
        config_snapshot={"variation_seed": 42},
    )


def _write_manifest(path: Path, slugs: list[str], layout: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "description": "test panel",
                "cc0_manifest": "tests/fixtures/cc0_music/manifest.json",
                "slugs": slugs,
                "layout": layout,
            }
        )
    )


# ---------------------------------------------------------------------------
# Unit tests (mocked run_song + download_all)
# ---------------------------------------------------------------------------


def test_run_panel_loads_manifest_and_iterates_in_order(monkeypatch, tmp_path):
    """Manifest order is preserved and run_song receives the expected
    audio / layout pairs.
    """
    slugs = ["funshine", "maple_leaf_rag"]
    # Pretend the MP3s exist so download_all() is never called.
    for slug in slugs:
        (_CC0_DIR / f"{slug}.mp3").parent.mkdir(parents=True, exist_ok=True)
    # Don't actually create files on the dev host: monkeypatch the
    # resolver to claim everything is present.
    monkeypatch.setattr(
        panel_module,
        "_resolve_slug_paths",
        lambda s: ({slug: _CC0_DIR / f"{slug}.mp3" for slug in s}, []),
    )

    calls: list[tuple[Path, Path, Path, dict | None]] = []

    def fake_run_song(audio, layout, output_dir, overrides):
        calls.append((Path(audio), Path(layout), Path(output_dir), overrides))
        return _stub_result(Path(audio).stem, Path(output_dir))

    monkeypatch.setattr(panel_module, "run_song", fake_run_song)

    manifest_path = tmp_path / "panel.json"
    _write_manifest(manifest_path, slugs, "tests/fixtures/reference/layout.xml")

    results = run_panel(manifest_path, tmp_path)

    assert [r.slug for r in results] == slugs
    assert len(calls) == 2
    assert calls[0][0].name == "funshine.mp3"
    assert calls[1][0].name == "maple_leaf_rag.mp3"
    # Layout resolved against repo root.
    assert calls[0][1] == _REFERENCE_LAYOUT.resolve()


def test_run_panel_forwards_config_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr(
        panel_module,
        "_resolve_slug_paths",
        lambda s: ({slug: _CC0_DIR / f"{slug}.mp3" for slug in s}, []),
    )
    received: list[dict | None] = []

    def fake_run_song(audio, layout, output_dir, overrides):
        received.append(overrides)
        return _stub_result(Path(audio).stem, Path(output_dir))

    monkeypatch.setattr(panel_module, "run_song", fake_run_song)

    manifest_path = tmp_path / "panel.json"
    _write_manifest(manifest_path, ["funshine"], "tests/fixtures/reference/layout.xml")

    overrides = {"variation_seed": 7}
    run_panel(manifest_path, tmp_path, config_overrides=overrides)

    assert received == [overrides]


def test_run_panel_missing_slug_after_download_raises(monkeypatch, tmp_path):
    """When a slug is still absent after download_all() returns, the
    panel raises FileNotFoundError listing the missing slug(s) — it does
    not silently skip.
    """
    # Use a slug that definitely doesn't exist as a CC0 fixture.
    bogus = "definitely_not_a_real_slug_zzz"
    assert not (_CC0_DIR / f"{bogus}.mp3").exists()

    download_calls = {"count": 0}

    def fake_download_all(*args, **kwargs):
        download_calls["count"] += 1
        return []

    # Patch where panel.py imports it. The import is deferred (inside
    # run_panel) so we patch the source module.
    import tests.validation.download_fixtures as dl_module

    monkeypatch.setattr(dl_module, "download_all", fake_download_all)

    manifest_path = tmp_path / "panel.json"
    _write_manifest(manifest_path, [bogus], "tests/fixtures/reference/layout.xml")

    with pytest.raises(FileNotFoundError, match=bogus):
        run_panel(manifest_path, tmp_path)

    assert download_calls["count"] == 1


def test_run_panel_bad_json_raises(tmp_path):
    manifest_path = tmp_path / "panel.json"
    manifest_path.write_text("{not valid json")

    with pytest.raises(json.JSONDecodeError):
        run_panel(manifest_path, tmp_path)


def test_run_panel_missing_layout_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(
        panel_module,
        "_resolve_slug_paths",
        lambda s: ({slug: _CC0_DIR / f"{slug}.mp3" for slug in s}, []),
    )

    manifest_path = tmp_path / "panel.json"
    _write_manifest(manifest_path, ["funshine"], "tests/fixtures/reference/no_such_layout.xml")

    with pytest.raises(FileNotFoundError, match="Layout file not found"):
        run_panel(manifest_path, tmp_path)


def test_run_panel_missing_manifest_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Panel manifest not found"):
        run_panel(tmp_path / "no_such_manifest.json", tmp_path)


# ---------------------------------------------------------------------------
# Integration tests — slow, fixture-gated
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    not _HAS_PANEL_FIXTURES,
    reason="Reference panel CC0 fixtures not all downloaded",
)
def test_integration_panel_sequential(tmp_path):
    results = run_panel(_PANEL_MANIFEST, tmp_path, parallel=False)

    assert len(results) == 4
    assert tuple(r.slug for r in results) == _PANEL_SLUGS
    for r in results:
        assert Path(r.xsq_path).is_file()
        assert r.metrics  # non-empty


@pytest.mark.slow
@pytest.mark.skipif(
    not _HAS_PANEL_FIXTURES,
    reason="Reference panel CC0 fixtures not all downloaded",
)
def test_integration_panel_parallel(tmp_path):
    results = run_panel(_PANEL_MANIFEST, tmp_path, parallel=True)

    assert len(results) == 4
    assert tuple(r.slug for r in results) == _PANEL_SLUGS
    for r in results:
        assert Path(r.xsq_path).is_file()
        assert r.metrics
