"""Tests for src/grouper/layout.py — parse_layout()."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.grouper.layout import Layout, Prop, dominant_prop_type, parse_layout, prop_type_for_display_as

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prop(name: str = "Prop", display_as: str = "Arch") -> Prop:
    return Prop(
        name=name,
        display_as=display_as,
        world_x=0.0,
        world_y=0.0,
        world_z=0.0,
        scale_x=1.0,
        scale_y=1.0,
        parm1=1,
        parm2=1,
        sub_models=[],
    )


# ---------------------------------------------------------------------------
# T004 — DISPLAY_AS_TO_PROP_TYPE mapping and prop_type_for_display_as()
# ---------------------------------------------------------------------------

class TestPropTypeForDisplayAs:
    """prop_type_for_display_as maps xLights DisplayAs strings to canonical prop types."""

    def test_matrix(self):
        assert prop_type_for_display_as("Matrix") == "matrix"

    def test_arch(self):
        assert prop_type_for_display_as("Arch") == "arch"

    def test_tree_360(self):
        assert prop_type_for_display_as("Tree 360") == "tree"

    def test_candy_cane(self):
        assert prop_type_for_display_as("Candy Cane") == "arch"

    def test_single_line(self):
        assert prop_type_for_display_as("Single Line") == "outline"

    def test_custom(self):
        assert prop_type_for_display_as("Custom") == "outline"

    def test_circle(self):
        assert prop_type_for_display_as("Circle") == "radial"

    def test_icicles(self):
        assert prop_type_for_display_as("Icicles") == "vertical"

    def test_unknown_value_falls_back_to_outline(self):
        assert prop_type_for_display_as("FooBar") == "outline"

    def test_empty_string_falls_back_to_outline(self):
        assert prop_type_for_display_as("") == "outline"


# ---------------------------------------------------------------------------
# T005 — dominant_prop_type()
# ---------------------------------------------------------------------------

class TestDominantPropType:
    """dominant_prop_type picks the most common canonical type among a list of props."""

    def test_majority_arch(self):
        props = [
            _make_prop("Arch1", "Arch"),
            _make_prop("Arch2", "Arch"),
            _make_prop("Arch3", "Arch"),
            _make_prop("Matrix1", "Matrix"),
        ]
        assert dominant_prop_type(props) == "arch"

    def test_tie_breaks_alphabetically(self):
        props = [
            _make_prop("Arch1", "Arch"),
            _make_prop("Arch2", "Arch"),
            _make_prop("Matrix1", "Matrix"),
            _make_prop("Matrix2", "Matrix"),
        ]
        # "arch" < "matrix" alphabetically
        assert dominant_prop_type(props) == "arch"

    def test_empty_list_returns_outline(self):
        assert dominant_prop_type([]) == "outline"

    def test_single_prop_matrix(self):
        props = [_make_prop("Matrix1", "Matrix")]
        assert dominant_prop_type(props) == "matrix"
