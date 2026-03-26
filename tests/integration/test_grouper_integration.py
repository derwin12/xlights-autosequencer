"""Integration tests for the full layout grouping pipeline."""
from __future__ import annotations

import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import cli
from src.grouper.classifier import classify_props, normalize_coords
from src.grouper.grouper import generate_groups
from src.grouper.layout import parse_layout
from src.grouper.writer import inject_groups, write_layout

FIXTURES = Path(__file__).parent.parent / "fixtures" / "grouper"
NAME_RE = re.compile(r"^\d{2}_[A-Z]+_\w+$")


def _run_full_pipeline(src_xml: Path, dest_xml: Path, profile=None):
    layout = parse_layout(src_xml)
    normalize_coords(layout.props)
    classify_props(layout.props)
    groups = generate_groups(layout.props, profile=profile)
    inject_groups(layout.raw_tree, groups)
    write_layout(layout, dest_xml)
    return groups


class TestFullRoundTrip:
    def test_output_contains_modelgroup_elements(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        _run_full_pipeline(dest, dest)
        tree = ET.parse(dest)
        groups = tree.getroot().findall("ModelGroup")
        assert len(groups) > 0

    def test_base_all_group_present(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        _run_full_pipeline(dest, dest)
        tree = ET.parse(dest)
        names = [mg.get("name") for mg in tree.getroot().findall("ModelGroup")]
        assert "01_BASE_All" in names

    def test_models_attribute_non_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        groups = _run_full_pipeline(dest, dest)
        tree = ET.parse(dest)
        for mg in tree.getroot().findall("ModelGroup"):
            assert mg.get("models"), f"Empty models on {mg.get('name')}"

    def test_naming_convention_sc002(self):
        """SC-002: All generated group names must match NN_PREFIX_Name pattern."""
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        groups = _run_full_pipeline(dest, dest)
        for g in groups:
            assert NAME_RE.match(g.name), f"Non-conforming name: {g.name!r}"

    def test_idempotency_sc003(self):
        """SC-003: Running twice produces identical XML output."""
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        _run_full_pipeline(dest, dest)
        first_run = dest.read_text(encoding="UTF-8")
        _run_full_pipeline(dest, dest)
        second_run = dest.read_text(encoding="UTF-8")
        assert first_run == second_run

    def test_manual_groups_preserved(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        _run_full_pipeline(dest, dest)
        tree = ET.parse(dest)
        names = [mg.get("name") for mg in tree.getroot().findall("ModelGroup")]
        assert "MyManualGroup" in names

    def test_original_models_untouched(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        _run_full_pipeline(dest, dest)
        tree = ET.parse(dest)
        models = tree.getroot().findall("model")
        assert len(models) == 8

    def test_performance_sc001(self):
        """SC-001: Full pipeline completes in under 5 seconds."""
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        start = time.monotonic()
        _run_full_pipeline(dest, dest)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"Pipeline took {elapsed:.2f}s (limit: 5s)"


class TestHeroLayout:
    def test_hero_groups_in_hero_layout(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "hero_layout.xml", dest)
        groups = _run_full_pipeline(dest, dest)
        names = [g.name for g in groups]
        assert "08_HERO_SingingFace" in names
        assert "08_HERO_MegaTree" in names

    def test_hero_group_contains_submodels(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "hero_layout.xml", dest)
        groups = _run_full_pipeline(dest, dest)
        face_group = next(g for g in groups if g.name == "08_HERO_SingingFace")
        assert "Eyes" in face_group.members
        assert "Mouth" in face_group.members


class TestMinimalLayout:
    def test_single_prop_produces_base_all(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "minimal_layout.xml", dest)
        groups = _run_full_pipeline(dest, dest)
        names = [g.name for g in groups]
        assert "01_BASE_All" in names

    def test_single_prop_no_errors(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "minimal_layout.xml", dest)
        _run_full_pipeline(dest, dest)  # should not raise


class TestCLICommand:
    def test_dry_run_does_not_modify_file(self):
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        original = dest.read_bytes()
        result = runner.invoke(cli, ["group-layout", str(dest), "--dry-run"])
        assert result.exit_code == 0
        assert dest.read_bytes() == original

    def test_dry_run_output_contains_tier_and_group_columns(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["group-layout", str(FIXTURES / "simple_layout.xml"), "--dry-run"])
        assert result.exit_code == 0
        assert "Tier" in result.output
        assert "Group Name" in result.output
        assert "Members" in result.output

    def test_normal_run_writes_groups(self):
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        result = runner.invoke(cli, ["group-layout", str(dest)])
        assert result.exit_code == 0
        tree = ET.parse(dest)
        assert len(tree.getroot().findall("ModelGroup")) > 0

    def test_profile_flag_filters_tiers(self):
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        result = runner.invoke(cli, ["group-layout", str(dest), "--profile", "technical"])
        assert result.exit_code == 0
        tree = ET.parse(dest)
        names = [mg.get("name") for mg in tree.getroot().findall("ModelGroup")]
        assert any(n.startswith("01_BASE_") for n in names if n)
        assert not any(n.startswith("04_BEAT_") for n in names if n)

    def test_missing_file_exits_1(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["group-layout", "/nonexistent/layout.xml"])
        assert result.exit_code == 1

    def test_invalid_xml_exits_2(self):
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write("THIS IS NOT XML <<<")
            tmp = f.name
        result = runner.invoke(cli, ["group-layout", tmp])
        assert result.exit_code == 2

    def test_no_models_exits_3(self):
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write('<?xml version="1.0"?><xlights_rgbeffects/>')
            tmp = f.name
        result = runner.invoke(cli, ["group-layout", tmp])
        assert result.exit_code == 3

    def test_output_option_writes_to_different_path(self):
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            dest = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f2:
            out = Path(f2.name)
        shutil.copy(FIXTURES / "simple_layout.xml", dest)
        original = dest.read_bytes()
        result = runner.invoke(cli, ["group-layout", str(dest), "--output", str(out)])
        assert result.exit_code == 0
        assert dest.read_bytes() == original  # source unchanged
        tree = ET.parse(out)
        assert len(tree.getroot().findall("ModelGroup")) > 0
