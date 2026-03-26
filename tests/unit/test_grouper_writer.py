"""Tests for src/grouper/writer.py — inject_groups, write_layout."""
from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.grouper.grouper import PowerGroup
from src.grouper.layout import parse_layout
from src.grouper.writer import AUTO_PREFIXES, inject_groups, write_layout

FIXTURES = Path(__file__).parent.parent / "fixtures" / "grouper"


def _parse_tree(xml_str: str) -> ET.ElementTree:
    return ET.ElementTree(ET.fromstring(xml_str))


class TestInjectGroups:
    def test_appends_new_modelgroup_elements(self):
        tree = _parse_tree("<xlights_rgbeffects><model name='A'/></xlights_rgbeffects>")
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["A"])]
        inject_groups(tree, groups)
        mg = tree.getroot().findall("ModelGroup")
        assert len(mg) == 1
        assert mg[0].get("name") == "01_BASE_All"

    def test_models_attribute_comma_separated(self):
        tree = _parse_tree("<xlights_rgbeffects/>")
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["PropA", "PropB", "PropC"])]
        inject_groups(tree, groups)
        mg = tree.getroot().find("ModelGroup")
        assert mg.get("models") == "PropA,PropB,PropC"

    def test_removes_existing_auto_groups(self):
        xml = """<xlights_rgbeffects>
            <ModelGroup name="01_BASE_All" models="OldProp"/>
            <ModelGroup name="02_GEO_Top" models="OldProp"/>
            <ModelGroup name="MyManualGroup" models="OldProp"/>
        </xlights_rgbeffects>"""
        tree = _parse_tree(xml)
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["NewProp"])]
        inject_groups(tree, groups)
        mg_names = [mg.get("name") for mg in tree.getroot().findall("ModelGroup")]
        assert "MyManualGroup" in mg_names
        assert "01_BASE_All" in mg_names
        assert mg_names.count("01_BASE_All") == 1
        assert "02_GEO_Top" not in mg_names

    def test_manual_groups_preserved(self):
        xml = """<xlights_rgbeffects>
            <ModelGroup name="MyManual" models="A,B"/>
            <ModelGroup name="01_BASE_All" models="A"/>
        </xlights_rgbeffects>"""
        tree = _parse_tree(xml)
        groups = [PowerGroup(name="01_BASE_All", tier=1, members=["A"])]
        inject_groups(tree, groups)
        names = [mg.get("name") for mg in tree.getroot().findall("ModelGroup")]
        assert "MyManual" in names

    def test_empty_groups_omitted(self):
        tree = _parse_tree("<xlights_rgbeffects/>")
        groups = [
            PowerGroup(name="01_BASE_All", tier=1, members=["PropA"]),
            PowerGroup(name="02_GEO_Top", tier=2, members=[]),
        ]
        inject_groups(tree, groups)
        names = [mg.get("name") for mg in tree.getroot().findall("ModelGroup")]
        assert "01_BASE_All" in names
        assert "02_GEO_Top" not in names

    def test_mutates_in_place(self):
        tree = _parse_tree("<xlights_rgbeffects/>")
        assert inject_groups(tree, []) is None


class TestWriteLayout:
    def test_writes_valid_xml_file(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            tmp = f.name
        write_layout(layout, tmp)
        tree = ET.parse(tmp)
        assert tree.getroot() is not None

    def test_written_file_contains_models(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            tmp = f.name
        write_layout(layout, tmp)
        tree = ET.parse(tmp)
        models = tree.getroot().findall("model")
        assert len(models) == 8
