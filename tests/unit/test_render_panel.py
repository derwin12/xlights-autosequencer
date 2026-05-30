"""Unit tests for the render_panel harness helpers.

Only the pure-logic helpers are covered here — the full render chain needs
xLights + Xvfb + ffmpeg and is exercised manually (see
tools/render_panel/README.md). These tests guard the two helpers that have
real branching logic and that broke once already:

* ``_tile`` must handle a single image (ffmpeg xstack rejects 1 input).
* ``_count_model_placements`` must distinguish a lit sequence from a
  timing-only (unlit) one — the silent-empty-sequence failure mode.
"""
from __future__ import annotations

import shutil

import pytest

from tools.render_panel.run import _count_model_placements, _tile


def _write_xsq(path, *, model_names: list[str]) -> None:
    """Minimal XSQ with the given model elements under <ElementEffects>."""
    model_els = "\n".join(
        f'      <Element type="model" name="{n}"><EffectLayer/></Element>'
        for n in model_names
    )
    path.write_text(
        '<?xml version="1.0"?>\n'
        "<xsequence>\n"
        "  <DisplayElements/>\n"
        "  <ElementEffects>\n"
        '    <Element type="timing" name="Beats"><EffectLayer/></Element>\n'
        f"{model_els}\n"
        "  </ElementEffects>\n"
        "</xsequence>\n"
    )


def test_count_placements_zero_for_timing_only(tmp_path):
    """A sequence with only timing tracks counts as 0 model placements."""
    xsq = tmp_path / "timing_only.xsq"
    _write_xsq(xsq, model_names=[])
    assert _count_model_placements(xsq) == 0


def test_count_placements_counts_models(tmp_path):
    """Model elements under <ElementEffects> are counted; timing ignored."""
    xsq = tmp_path / "lit.xsq"
    _write_xsq(xsq, model_names=["Mega Tree", "Arch", "Window"])
    assert _count_model_placements(xsq) == 3


def test_count_placements_no_element_effects(tmp_path):
    """A file with no <ElementEffects> block counts as 0, not an error."""
    xsq = tmp_path / "bare.xsq"
    xsq.write_text('<?xml version="1.0"?>\n<xsequence></xsequence>\n')
    assert _count_model_placements(xsq) == 0


def _solid_jpg(path, color: tuple[int, int, int]) -> None:
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image", reason="pillow required")
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[:, :] = color
    Image.fromarray(arr).save(path)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_tile_single_image_is_copied(tmp_path):
    """xstack rejects a single input, so n=1 must fall back to a copy."""
    frame = tmp_path / "f0.jpg"
    _solid_jpg(frame, (200, 0, 0))
    out = tmp_path / "sheet.jpg"
    _tile([frame], out, cols=1)
    assert out.exists() and out.stat().st_size > 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_tile_multiple_images(tmp_path):
    """Multiple frames tile into one sheet via xstack."""
    frames = []
    for i, color in enumerate([(200, 0, 0), (0, 200, 0), (0, 0, 200)]):
        f = tmp_path / f"f{i}.jpg"
        _solid_jpg(f, color)
        frames.append(f)
    out = tmp_path / "sheet.jpg"
    _tile(frames, out, cols=2)
    assert out.exists() and out.stat().st_size > 0
