"""Tests for src/grouper/grouper.py — generate_groups, ShowProfile filtering, beat groups."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.grouper.classifier import classify_props, normalize_coords
from src.grouper.grouper import PowerGroup, generate_groups
from src.grouper.layout import Prop, parse_layout

FIXTURES = Path(__file__).parent.parent / "fixtures" / "grouper"


def make_prop(name="P", world_x=0.0, world_y=0.0, scale_x=1.0, scale_y=1.0,
              parm1=1, parm2=1, sub_models=None) -> Prop:
    p = Prop(
        name=name, display_as="Arch",
        world_x=world_x, world_y=world_y, world_z=0.0,
        scale_x=scale_x, scale_y=scale_y,
        parm1=parm1, parm2=parm2,
        sub_models=sub_models or [],
    )
    return p


def _prepared_props_from_fixture(filename: str) -> list[Prop]:
    layout = parse_layout(FIXTURES / filename)
    normalize_coords(layout.props)
    classify_props(layout.props)
    return layout.props


# ─── Tier 1: Canvas ──────────────────────────────────────────────────────────

class TestCanvasGroup:
    def test_base_all_contains_every_prop(self):
        props = _prepared_props_from_fixture("simple_layout.xml")
        groups = generate_groups(props)
        base = next((g for g in groups if g.name == "01_BASE_All"), None)
        assert base is not None
        assert set(base.members) == {p.name for p in props}

    def test_base_all_tier_number(self):
        props = _prepared_props_from_fixture("simple_layout.xml")
        groups = generate_groups(props)
        base = next(g for g in groups if g.name == "01_BASE_All")
        assert base.tier == 1


# ─── Tier 2: Spatial ─────────────────────────────────────────────────────────

class TestSpatialGroups:
    def test_spatial_group_names_use_02_geo_prefix(self):
        props = _prepared_props_from_fixture("simple_layout.xml")
        groups = generate_groups(props)
        geo_groups = [g for g in groups if g.name.startswith("02_GEO_")]
        assert len(geo_groups) > 0

    def test_top_threshold_y_above_066(self):
        props = [make_prop("High", world_x=50.0, world_y=100.0),
                 make_prop("Low", world_x=50.0, world_y=0.0)]
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        top = next((g for g in groups if g.name == "02_GEO_Top"), None)
        assert top is not None
        assert "High" in top.members
        assert "Low" not in top.members

    def test_bot_threshold_y_below_033(self):
        props = [make_prop("High", world_x=50.0, world_y=100.0),
                 make_prop("Low", world_x=50.0, world_y=0.0)]
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        bot = next((g for g in groups if g.name == "02_GEO_Bot"), None)
        assert bot is not None
        assert "Low" in bot.members

    def test_left_threshold_x_below_033(self):
        props = [make_prop("Left", world_x=0.0, world_y=50.0),
                 make_prop("Right", world_x=100.0, world_y=50.0)]
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        left = next((g for g in groups if g.name == "02_GEO_Left"), None)
        assert left is not None
        assert "Left" in left.members

    def test_empty_spatial_bins_omitted(self):
        """Bins with no props should not appear in the output."""
        props = [make_prop("Only", world_x=50.0, world_y=50.0)]
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        geo_groups = [g for g in groups if g.name.startswith("02_GEO_")]
        for g in geo_groups:
            assert len(g.members) > 0


# ─── Tier 3: Architecture ────────────────────────────────────────────────────

class TestArchitectureGroups:
    def test_vertical_group_for_aspect_gte_15(self):
        props = [make_prop("TallProp", scale_x=1.0, scale_y=2.0)]
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        vert = next((g for g in groups if g.name == "03_TYPE_Vertical"), None)
        assert vert is not None
        assert "TallProp" in vert.members

    def test_horizontal_group_for_aspect_lt_15(self):
        props = [make_prop("WideProp", scale_x=2.0, scale_y=1.0)]
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        horiz = next((g for g in groups if g.name == "03_TYPE_Horizontal"), None)
        assert horiz is not None
        assert "WideProp" in horiz.members


# ─── Tier 5: Fidelity ────────────────────────────────────────────────────────

class TestFidelityGroups:
    def test_hidens_for_pixel_count_above_500(self):
        props = [make_prop("BigMatrix", parm1=20, parm2=30)]  # 600 pixels
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        hi = next((g for g in groups if g.name == "05_TEX_HiDens"), None)
        assert hi is not None
        assert "BigMatrix" in hi.members

    def test_lodens_for_pixel_count_at_or_below_500(self):
        props = [make_prop("SmallArch", parm1=1, parm2=50)]  # 50 pixels
        normalize_coords(props)
        classify_props(props)
        groups = generate_groups(props)
        lo = next((g for g in groups if g.name == "05_TEX_LoDens"), None)
        assert lo is not None
        assert "SmallArch" in lo.members


# ─── Show Profiles (US2) ─────────────────────────────────────────────────────

class TestShowProfiles:
    def _group_names(self, profile: str | None) -> set[str]:
        props = _prepared_props_from_fixture("simple_layout.xml")
        return {g.name for g in generate_groups(props, profile=profile)}

    def test_energetic_includes_architecture_rhythm_proptype_heroes(self):
        names = self._group_names("energetic")
        assert any(n.startswith("03_TYPE_") for n in names)
        assert any(n.startswith("04_BEAT_") for n in names)
        assert any(n.startswith("06_PROP_") for n in names)

    def test_energetic_excludes_spatial_fidelity_compound(self):
        names = self._group_names("energetic")
        assert not any(n.startswith("02_GEO_") for n in names)
        assert not any(n.startswith("05_TEX_") for n in names)
        assert not any(n.startswith("07_COMP_") for n in names)

    def test_cinematic_includes_canvas_spatial_compound_heroes(self):
        names = self._group_names("cinematic")
        assert any(n.startswith("01_BASE_") for n in names)
        assert any(n.startswith("02_GEO_") for n in names)

    def test_cinematic_excludes_rhythm(self):
        names = self._group_names("cinematic")
        assert not any(n.startswith("04_BEAT_") for n in names)

    def test_technical_includes_canvas_fidelity(self):
        names = self._group_names("technical")
        assert any(n.startswith("01_BASE_") for n in names)
        assert any(n.startswith("05_TEX_") for n in names)

    def test_technical_excludes_architecture_rhythm(self):
        names = self._group_names("technical")
        assert not any(n.startswith("03_TYPE_") for n in names)
        assert not any(n.startswith("04_BEAT_") for n in names)

    def test_no_profile_generates_all_tiers(self):
        names = self._group_names(None)
        for prefix in ("01_BASE_", "02_GEO_", "03_TYPE_", "04_BEAT_", "05_TEX_", "06_PROP_"):
            assert any(n.startswith(prefix) for n in names)

    def test_no_profile_is_superset_of_all_profiles(self):
        """SC-006: no-profile produces superset of every individual profile."""
        all_names = self._group_names(None)
        for profile in ("energetic", "cinematic", "technical"):
            profile_names = self._group_names(profile)
            assert profile_names.issubset(all_names), (
                f"Profile '{profile}' produced groups not in no-profile run: "
                f"{profile_names - all_names}"
            )


# ─── Tier 4: Rhythmic Beat Groups (US3) ──────────────────────────────────────

class TestBeatGroups:
    def _beat_groups(self, props: list[Prop]) -> list[PowerGroup]:
        return [g for g in generate_groups(props) if g.name.startswith("04_BEAT_")]

    def test_lr_groups_sorted_by_norm_x(self):
        props = [make_prop(f"P{i}", world_x=float(i * 100), world_y=100.0) for i in range(8)]
        normalize_coords(props)
        classify_props(props)
        beat = self._beat_groups(props)
        lr = sorted([g for g in beat if "LR" in g.name], key=lambda g: g.name)
        assert lr[0].members == ["P0", "P1", "P2", "P3"]
        assert lr[1].members == ["P4", "P5", "P6", "P7"]

    def test_lr_group_count_for_8_props(self):
        props = [make_prop(f"P{i}", world_x=float(i * 100), world_y=100.0) for i in range(8)]
        normalize_coords(props)
        classify_props(props)
        lr = [g for g in generate_groups(props) if "LR" in g.name]
        assert len(lr) == 2

    def test_co_groups_sorted_by_distance_from_center(self):
        # 4 props symmetrically placed around center
        props = [
            make_prop("L2", world_x=0.0, world_y=100.0),
            make_prop("L1", world_x=200.0, world_y=100.0),
            make_prop("R1", world_x=400.0, world_y=100.0),
            make_prop("R2", world_x=600.0, world_y=100.0),
        ]
        normalize_coords(props)
        classify_props(props)
        co = [g for g in generate_groups(props) if "CO" in g.name]
        assert len(co) == 1
        # CO_1 should contain the two center-most props
        co1 = co[0]
        assert set(co1.members) == {"L1", "R1", "L2", "R2"}

    def test_remainder_group_not_discarded(self):
        props = [make_prop(f"P{i}", world_x=float(i * 100), world_y=100.0) for i in range(6)]
        normalize_coords(props)
        classify_props(props)
        lr = [g for g in generate_groups(props) if "LR" in g.name]
        member_counts = [len(g.members) for g in lr]
        # Should have groups of 4 and 2 (remainder kept)
        assert 2 in member_counts

    def test_lr_and_co_are_independent(self):
        props = [make_prop(f"P{i}", world_x=float(i * 100), world_y=100.0) for i in range(8)]
        normalize_coords(props)
        classify_props(props)
        lr = [g for g in generate_groups(props) if "LR" in g.name]
        co = [g for g in generate_groups(props) if "CO" in g.name]
        assert len(lr) == 2
        assert len(co) == 2
