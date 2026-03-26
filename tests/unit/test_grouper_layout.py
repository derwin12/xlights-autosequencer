"""Tests for src/grouper/layout.py — parse_layout()."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.grouper.layout import Layout, Prop, parse_layout

FIXTURES = Path(__file__).parent.parent / "fixtures" / "grouper"


class TestParseLayout:
    def test_returns_layout_instance(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assert isinstance(layout, Layout)

    def test_prop_count(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assert len(layout.props) == 8

    def test_prop_name(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        names = [p.name for p in layout.props]
        assert "ArchLeft1" in names
        assert "MatrixCenter" in names

    def test_prop_world_coords(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        arch = next(p for p in layout.props if p.name == "ArchLeft1")
        assert arch.world_x == pytest.approx(50.0)
        assert arch.world_y == pytest.approx(40.0)
        assert arch.world_z == pytest.approx(0.0)

    def test_prop_scale(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        arch = next(p for p in layout.props if p.name == "ArchLeft1")
        assert arch.scale_x == pytest.approx(2.0)
        assert arch.scale_y == pytest.approx(1.0)

    def test_prop_parm1_parm2(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        matrix = next(p for p in layout.props if p.name == "MatrixCenter")
        assert matrix.parm1 == 20
        assert matrix.parm2 == 30

    def test_prop_display_as(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        matrix = next(p for p in layout.props if p.name == "MatrixCenter")
        assert matrix.display_as == "Matrix"

    def test_sub_models_parsed(self):
        layout = parse_layout(FIXTURES / "hero_layout.xml")
        face = next(p for p in layout.props if p.name == "SingingFace")
        assert "Eyes" in face.sub_models
        assert "Mouth" in face.sub_models

    def test_no_sub_models_on_regular_prop(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        arch = next(p for p in layout.props if p.name == "ArchLeft1")
        assert arch.sub_models == []

    def test_source_path_stored(self):
        path = FIXTURES / "simple_layout.xml"
        layout = parse_layout(path)
        assert layout.source_path == Path(path)

    def test_raw_tree_preserved(self):
        import xml.etree.ElementTree as ET
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assert isinstance(layout.raw_tree, ET.ElementTree)

    def test_missing_worldpos_defaults_to_zero(self):
        """Props with no WorldPosX/Y/Z should default to 0.0."""
        import tempfile, textwrap
        xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <xlights_rgbeffects>
                <model name="NoCoords" DisplayAs="Arch" parm1="1" parm2="10" />
            </xlights_rgbeffects>
        """)
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(xml)
            tmp = f.name
        layout = parse_layout(tmp)
        prop = layout.props[0]
        assert prop.world_x == 0.0
        assert prop.world_y == 0.0
        assert prop.world_z == 0.0

    def test_minimal_layout_one_prop(self):
        layout = parse_layout(FIXTURES / "minimal_layout.xml")
        assert len(layout.props) == 1
        assert layout.props[0].name == "SingleArch"
