"""Tests for src/grouper/classifier.py — normalize_coords, classify_props, detect_heroes."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.grouper.classifier import classify_props, detect_heroes, normalize_coords
from src.grouper.layout import Prop, parse_layout

FIXTURES = Path(__file__).parent.parent / "fixtures" / "grouper"


def make_prop(name="Prop", world_x=0.0, world_y=0.0, scale_x=1.0, scale_y=1.0,
              parm1=1, parm2=1, sub_models=None) -> Prop:
    return Prop(
        name=name, display_as="Arch",
        world_x=world_x, world_y=world_y, world_z=0.0,
        scale_x=scale_x, scale_y=scale_y,
        parm1=parm1, parm2=parm2,
        sub_models=sub_models or [],
    )


class TestNormalizeCoords:
    def test_full_range_normalized(self):
        props = [
            make_prop("A", world_x=0.0, world_y=0.0),
            make_prop("B", world_x=100.0, world_y=200.0),
            make_prop("C", world_x=50.0, world_y=100.0),
        ]
        normalize_coords(props)
        assert props[0].norm_x == pytest.approx(0.0)
        assert props[1].norm_x == pytest.approx(1.0)
        assert props[2].norm_x == pytest.approx(0.5)
        assert props[0].norm_y == pytest.approx(0.0)
        assert props[1].norm_y == pytest.approx(1.0)
        assert props[2].norm_y == pytest.approx(0.5)

    def test_same_x_defaults_to_midpoint(self):
        props = [
            make_prop("A", world_x=100.0, world_y=0.0),
            make_prop("B", world_x=100.0, world_y=200.0),
        ]
        normalize_coords(props)
        assert props[0].norm_x == pytest.approx(0.5)
        assert props[1].norm_x == pytest.approx(0.5)

    def test_same_y_defaults_to_midpoint(self):
        props = [make_prop("A", world_x=0.0, world_y=50.0),
                 make_prop("B", world_x=100.0, world_y=50.0)]
        normalize_coords(props)
        assert props[0].norm_y == pytest.approx(0.5)

    def test_values_clamped_to_0_1(self):
        props = [make_prop("A", world_x=10.0, world_y=10.0),
                 make_prop("B", world_x=90.0, world_y=90.0)]
        normalize_coords(props)
        for p in props:
            assert 0.0 <= p.norm_x <= 1.0
            assert 0.0 <= p.norm_y <= 1.0

    def test_single_prop_midpoint(self):
        props = [make_prop("A", world_x=999.0, world_y=999.0)]
        normalize_coords(props)
        assert props[0].norm_x == pytest.approx(0.5)
        assert props[0].norm_y == pytest.approx(0.5)


class TestClassifyProps:
    def test_pixel_count_is_parm1_times_parm2(self):
        props = [make_prop("A", parm1=5, parm2=20)]
        classify_props(props)
        assert props[0].pixel_count == 100

    def test_aspect_ratio_scale_y_over_scale_x(self):
        props = [make_prop("A", scale_x=2.0, scale_y=3.0)]
        classify_props(props)
        assert props[0].aspect_ratio == pytest.approx(1.5)

    def test_vertical_classification(self):
        """aspect_ratio >= 1.5 → vertical."""
        props = [make_prop("A", scale_x=1.0, scale_y=2.0)]
        classify_props(props)
        assert props[0].aspect_ratio >= 1.5

    def test_horizontal_classification(self):
        """aspect_ratio < 1.5 → horizontal."""
        props = [make_prop("A", scale_x=2.0, scale_y=1.0)]
        classify_props(props)
        assert props[0].aspect_ratio < 1.5

    def test_zero_scale_x_does_not_crash(self):
        """If scale_x is 0, aspect_ratio should default gracefully."""
        props = [make_prop("A", scale_x=0.0, scale_y=1.0)]
        classify_props(props)  # should not raise


class TestDetectHeroes:
    def test_face_keyword_detected(self):
        props = [make_prop("SingingFace", sub_models=["Eyes", "Mouth"])]
        groups = detect_heroes(props)
        assert len(groups) == 1
        assert groups[0].name == "08_HERO_SingingFace"
        assert "Eyes" in groups[0].members
        assert "Mouth" in groups[0].members

    def test_megatree_keyword_detected(self):
        props = [make_prop("MegaTree", sub_models=[])]
        groups = detect_heroes(props)
        assert len(groups) == 1
        assert groups[0].name == "08_HERO_MegaTree"

    def test_case_insensitive(self):
        props = [make_prop("singingface_01", sub_models=["E", "M"])]
        groups = detect_heroes(props)
        assert len(groups) == 1

    def test_no_match_produces_no_groups(self):
        props = [make_prop("ArchLeft"), make_prop("RooflineRight")]
        groups = detect_heroes(props)
        assert groups == []

    def test_bare_tree_does_not_match(self):
        """'TreeLeft' should NOT be a hero — only 'MegaTree' / 'Face' match."""
        props = [make_prop("TreeLeft"), make_prop("TreeRight")]
        groups = detect_heroes(props)
        assert groups == []

    def test_hero_with_no_submodels_contains_prop_itself(self):
        props = [make_prop("MegaTree01", sub_models=[])]
        groups = detect_heroes(props)
        assert groups[0].members == ["MegaTree01"]

    def test_name_with_spaces_sanitized(self):
        props = [make_prop("Singing Face", sub_models=["Eyes"])]
        groups = detect_heroes(props)
        assert groups[0].name == "08_HERO_Singing_Face"

    def test_hero_layout_fixture(self):
        layout = parse_layout(FIXTURES / "hero_layout.xml")
        classify_props(layout.props)
        groups = detect_heroes(layout.props)
        names = [g.name for g in groups]
        assert "08_HERO_SingingFace" in names
        assert "08_HERO_MegaTree" in names
        # Regular arches should not appear
        assert not any("Arch" in n for n in names)


class TestEdgeCases:
    def test_one_prop_normalizes_to_midpoint(self):
        props = [make_prop("Single", world_x=500.0, world_y=300.0)]
        normalize_coords(props)
        assert props[0].norm_x == pytest.approx(0.5)
        assert props[0].norm_y == pytest.approx(0.5)

    def test_all_same_x_coordinate_beat_groups_still_possible(self):
        """normalize_coords should not error on zero x-range."""
        props = [make_prop(f"P{i}", world_x=100.0, world_y=float(i * 50)) for i in range(4)]
        normalize_coords(props)
        for p in props:
            assert p.norm_x == pytest.approx(0.5)

    def test_missing_coords_default_to_zero(self):
        """Props parsed with missing WorldPos should have world_x/y/z=0.0."""
        import tempfile, textwrap
        xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <xlights_rgbeffects>
                <model name="NoCoordsModel" DisplayAs="Arch" parm1="1" parm2="10" />
            </xlights_rgbeffects>
        """)
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(xml)
            tmp = f.name
        layout = parse_layout(tmp)
        normalize_coords(layout.props)
        assert layout.props[0].norm_x == pytest.approx(0.5)
