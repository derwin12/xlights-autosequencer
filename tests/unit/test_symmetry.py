"""Tests for src/grouper/symmetry — symmetry pair detection."""
from __future__ import annotations

import pytest

from src.grouper.symmetry import SymmetryGroup, detect_symmetry_pairs
from src.grouper.grouper import PowerGroup
from src.grouper.layout import Prop


def _make_group(name: str, tier: int, members: list[str] | None = None) -> PowerGroup:
    return PowerGroup(name=name, tier=tier, members=members or [name])


def _make_prop(name: str, norm_x: float = 0.5, norm_y: float = 0.5) -> Prop:
    p = Prop(
        name=name,
        display_as="Single Line",
        world_x=0.0,
        world_y=0.0,
        world_z=0.0,
        scale_x=1.0,
        scale_y=1.0,
        parm1=1,
        parm2=1,
        sub_models=[],
    )
    p.norm_x = norm_x
    p.norm_y = norm_y
    return p


class TestDetectSymmetryPairs:
    def test_name_left_right(self):
        """Groups differing only by Left/Right suffix are detected as a pair."""
        groups = [
            _make_group("06_PROP_Arch_Left", tier=6),
            _make_group("06_PROP_Arch_Right", tier=6),
        ]
        pairs = detect_symmetry_pairs(groups)
        assert len(pairs) == 1
        assert pairs[0].detection_method == "name"
        assert {pairs[0].group_a, pairs[0].group_b} == {
            "06_PROP_Arch_Left",
            "06_PROP_Arch_Right",
        }

    def test_name_1_2(self):
        """Groups differing only by 1/2 suffix are detected as a pair."""
        groups = [
            _make_group("06_PROP_CandyCane_1", tier=6),
            _make_group("06_PROP_CandyCane_2", tier=6),
        ]
        pairs = detect_symmetry_pairs(groups)
        assert len(pairs) == 1
        assert pairs[0].detection_method == "name"
        assert {pairs[0].group_a, pairs[0].group_b} == {
            "06_PROP_CandyCane_1",
            "06_PROP_CandyCane_2",
        }

    def test_name_a_b(self):
        """Groups differing only by A/B suffix are detected as a pair."""
        groups = [
            _make_group("06_PROP_Tree_A", tier=6),
            _make_group("06_PROP_Tree_B", tier=6),
        ]
        pairs = detect_symmetry_pairs(groups)
        assert len(pairs) == 1
        assert pairs[0].detection_method == "name"
        assert {pairs[0].group_a, pairs[0].group_b} == {
            "06_PROP_Tree_A",
            "06_PROP_Tree_B",
        }

    def test_no_false_positive(self):
        """Groups with different base names are NOT paired."""
        groups = [
            _make_group("06_PROP_Arch", tier=6),
            _make_group("06_PROP_CandyCane", tier=6),
        ]
        pairs = detect_symmetry_pairs(groups)
        assert len(pairs) == 0

    def test_manual_override(self):
        """Manual overrides create pairs with method='manual'."""
        groups = [
            _make_group("GroupX", tier=6),
            _make_group("GroupY", tier=6),
        ]
        pairs = detect_symmetry_pairs(groups, overrides=[("GroupX", "GroupY")])
        assert len(pairs) == 1
        assert pairs[0].detection_method == "manual"
        assert pairs[0].group_a == "GroupX"
        assert pairs[0].group_b == "GroupY"

    def test_spatial_mirror(self):
        """Groups at same tier with mirrored X positions are paired spatially."""
        prop_left = _make_prop("ArchL", norm_x=0.2, norm_y=0.5)
        prop_right = _make_prop("ArchR", norm_x=0.8, norm_y=0.5)
        groups = [
            _make_group("06_PROP_Foo", tier=6, members=["ArchL"]),
            _make_group("06_PROP_Bar", tier=6, members=["ArchR"]),
        ]
        pairs = detect_symmetry_pairs(
            groups, props=[prop_left, prop_right],
        )
        assert len(pairs) == 1
        assert pairs[0].detection_method == "spatial"
        assert {pairs[0].group_a, pairs[0].group_b} == {
            "06_PROP_Foo",
            "06_PROP_Bar",
        }
