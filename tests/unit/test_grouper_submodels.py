"""Tests for tier-6 radial sub-group promotion in src/grouper/grouper.py."""
from __future__ import annotations

from src.grouper.classifier import classify_props, normalize_coords
from src.grouper.grouper import generate_groups
from src.grouper.layout import Prop, SubModel


def _flake(name: str, sub_model_names: list[str]) -> Prop:
    """Build a Custom prop with the given subModel names (pixel indices stubbed).

    Pixel count (parm1*parm2 = 800) is set above _RADIAL_PARENT_MIN_PIXELS=400
    so radial subgroups are promoted. The pixel-count gate itself has its own
    coverage in tests/unit/test_grouper_groups.py::TestRadialSubPropPixelGate.
    """
    return Prop(
        name=name,
        display_as="Custom",
        world_x=0.0, world_y=0.0, world_z=0.0,
        scale_x=1.0, scale_y=1.0,
        parm1=20, parm2=40,
        sub_models=[SubModel(name=n, pixel_indices=(1, 2, 3)) for n in sub_model_names],
    )


def _classify(props: list[Prop]) -> None:
    normalize_coords(props)
    classify_props(props)


class TestRadialSubgroups:
    def test_rings_become_chase_group(self):
        props = [_flake("Snowflake", ["Ring 1", "Ring 2", "Ring 3"])]
        _classify(props)
        groups = generate_groups(props)

        radial = [g for g in groups if g.prop_type == "radial"]
        assert len(radial) == 1
        ring_group = radial[0]
        assert ring_group.tier == 6
        assert ring_group.name == "06_PROP_Snowflake_Rings"
        # Members are fully-qualified Parent/SubModel addresses, sorted by
        # the integer suffix so chase order is inner→outer.
        assert ring_group.members == [
            "Snowflake/Ring 1",
            "Snowflake/Ring 2",
            "Snowflake/Ring 3",
        ]

    def test_spokes_separate_group_from_rings(self):
        props = [_flake(
            "Snowflake",
            ["Ring 1", "Ring 2", "Ring 3", "Spoke 1", "Spoke 2", "Spoke 3"],
        )]
        _classify(props)
        groups = generate_groups(props)

        names = sorted(g.name for g in groups if g.prop_type == "radial")
        assert names == ["06_PROP_Snowflake_Rings", "06_PROP_Snowflake_Spokes"]

    def test_numeric_sort_not_lexicographic(self):
        # 1, 2, 10 must not become 1, 10, 2.
        props = [_flake(
            "Big",
            [f"Spoke {i}" for i in [10, 2, 1, 11, 3]],
        )]
        _classify(props)
        groups = generate_groups(props)

        spokes = [g for g in groups if g.name.endswith("_Spokes")][0]
        assert spokes.members == [
            "Big/Spoke 1",
            "Big/Spoke 2",
            "Big/Spoke 3",
            "Big/Spoke 10",
            "Big/Spoke 11",
        ]

    def test_single_ring_skipped(self):
        # A pattern with fewer than 2 matching subModels is just a flash —
        # don't promote it.
        props = [_flake("OnlyOne", ["Ring 1"])]
        _classify(props)
        groups = generate_groups(props)
        assert not any(g.prop_type == "radial" for g in groups)

    def test_no_submodels_no_radial_group(self):
        props = [_flake("Plain", [])]
        _classify(props)
        groups = generate_groups(props)
        assert not any(g.prop_type == "radial" for g in groups)

    def test_non_radial_submodel_names_skipped(self):
        # Eyes / Mouth are subModels but not radial — must not produce a
        # radial group.
        props = [_flake("SingingFace", ["Eyes", "Mouth"])]
        _classify(props)
        groups = generate_groups(props)
        assert not any(g.prop_type == "radial" for g in groups)

    def test_radial_group_coexists_with_horizontal_prop_type_group(self):
        # Two flakes ⇒ existing tier-6 horizontal group "06_PROP_Snowflake"
        # collects them.  Each flake also contributes its own radial group.
        props = [
            _flake("Snowflake 1", ["Ring 1", "Ring 2", "Ring 3"]),
            _flake("Snowflake 2", ["Ring 1", "Ring 2", "Ring 3"]),
        ]
        _classify(props)
        groups = generate_groups(props)

        names = {g.name for g in groups if g.tier == 6}
        # Horizontal group: name-pattern across both flakes (existing
        # _tier6_prop_type behaviour).
        assert any("06_PROP_Snowflake" in n and "Rings" not in n for n in names)
        # Two new radial groups, one per flake.
        assert "06_PROP_Snowflake_1_Rings" in names
        assert "06_PROP_Snowflake_2_Rings" in names

    def test_arms_pattern_matches(self):
        props = [_flake("Star", ["Arm 1", "Arm 2", "Arm 3", "Arm 4", "Arm 5"])]
        _classify(props)
        groups = generate_groups(props)
        radial = [g for g in groups if g.prop_type == "radial"]
        assert len(radial) == 1
        assert radial[0].name == "06_PROP_Star_Arms"
        assert len(radial[0].members) == 5
