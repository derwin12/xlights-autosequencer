"""Tests for src.evaluation.xsq_reader — written before the implementation exists."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from src.evaluation.xsq_reader import parse, parse_bytes
from src.evaluation.models import SequenceSummary

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "minimal_xsq"
TINY_XSQ = FIXTURE_DIR / "tiny.xsq"


def test_parse_tiny_xsq():
    result = parse(TINY_XSQ)

    assert isinstance(result, SequenceSummary)
    assert result.duration_ms == 10000
    assert len(result.placements) == 3

    # Arch01 layer 0: Marquee, 0–1000
    arch_layer0 = next(
        p for p in result.placements
        if p.model_name == "Arch01" and p.layer_index == 0
    )
    assert arch_layer0.start_ms == 0
    assert arch_layer0.end_ms == 1000
    assert arch_layer0.effect_type == "Marquee"
    assert "#FF0000" in arch_layer0.palette_colors
    assert "#0000FF" in arch_layer0.palette_colors

    # MiniTree01 layer 0: Marquee, 500–2500
    tree_layer0 = next(
        p for p in result.placements
        if p.model_name == "MiniTree01" and p.layer_index == 0
    )
    assert tree_layer0.start_ms == 500
    assert tree_layer0.end_ms == 2500
    assert tree_layer0.effect_type == "Marquee"

    assert "Arch01" in result.model_names
    assert "MiniTree01" in result.model_names

    assert result.inferred_prop_types["Arch01"] == "arch"
    assert result.inferred_prop_types["MiniTree01"] == "tree"


def test_parse_xsqz():
    xsq_bytes = TINY_XSQ.read_bytes()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("tiny.xsq", xsq_bytes)
    xsqz_bytes = buf.getvalue()

    result = parse_bytes(xsqz_bytes, filename="tiny.xsqz")

    assert isinstance(result, SequenceSummary)
    assert result.duration_ms == 10000
    assert len(result.placements) == 3
    assert "Arch01" in result.model_names
    assert "MiniTree01" in result.model_names


def test_palette_colors_have_hash_prefix():
    result = parse(TINY_XSQ)
    for placement in result.placements:
        for color in placement.palette_colors:
            assert color.startswith("#"), f"Color missing # prefix: {color!r}"


def test_malformed_xml_raises():
    malformed = b"<xsequence><head><sequenceDuration>NOT CLOSED"
    with pytest.raises(Exception):
        parse_bytes(malformed, filename="bad.xsq")


def test_unknown_effect_type():
    minimal_xsq = b"""<?xml version="1.0" encoding="UTF-8"?>
<xsequence>
  <head>
    <sequenceDuration>5000</sequenceDuration>
  </head>
  <ColorPalettes/>
  <EffectDB>
    <Effect settings="SOME_OTHER_KEY=Value"/>
  </EffectDB>
  <ElementEffects>
    <Element type="model" name="Arch01">
      <EffectLayer>
        <Effect startTime="0" endTime="1000" label="" ref="0" palette="0"/>
      </EffectLayer>
    </Element>
  </ElementEffects>
</xsequence>"""

    result = parse_bytes(minimal_xsq, filename="unknown_effect.xsq")
    assert len(result.placements) == 1
    assert result.placements[0].effect_type == "Unknown"


def test_source_label():
    result = parse(TINY_XSQ, song_id="test-song", source_label="pro:xatw")
    assert result.song_id == "test-song"
    assert result.source_label == "pro:xatw"
