"""Unit tests for the layout group editor module (src/grouper/editor.py)."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.grouper.editor import (
    GroupDef,
    GroupingEdits,
    MergedGrouping,
    PropMove,
    add_group_to_edits,
    apply_edits,
    edits_from_dict,
    edits_path,
    edits_to_dict,
    export_grouping,
    layout_md5,
    load_edits,
    new_edits,
    remove_group_from_edits,
    rename_group_in_edits,
    reset_edits,
    save_edits,
    tier_prefix,
)
from src.grouper.grouper import PowerGroup


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_layout_file(content: bytes = b"<xlights_rgbeffects/>") -> Path:
    """Create a temp XML file with known content and return its Path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def _baseline_groups() -> list[PowerGroup]:
    return [
        PowerGroup(name="01_BASE_All", tier=1, members=["PropA", "PropB", "PropC"]),
        PowerGroup(name="04_BEAT_1", tier=4, members=["PropA", "PropC"]),
        PowerGroup(name="04_BEAT_2", tier=4, members=["PropB"]),
    ]


def _all_prop_names() -> list[str]:
    return ["PropA", "PropB", "PropC"]


# ─── Dataclass field presence ──────────────────────────────────────────────────

def test_grouping_edits_has_required_fields():
    edits = GroupingEdits(
        layout_md5="abc123",
        layout_path="/fake/path.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    assert edits.layout_md5 == "abc123"
    assert edits.moves == []
    assert edits.added_groups == []
    assert edits.removed_groups == []
    assert edits.renamed_groups == {}


def test_prop_move_fields():
    m = PropMove(prop_name="PropA", tier=4, from_group="04_BEAT_1", to_group="04_BEAT_2")
    assert m.prop_name == "PropA"
    assert m.tier == 4
    assert m.from_group == "04_BEAT_1"
    assert m.to_group == "04_BEAT_2"


def test_group_def_fields():
    g = GroupDef(name="08_HERO_Tree", tier=8, members=["BigTree"])
    assert g.name == "08_HERO_Tree"
    assert g.tier == 8
    assert g.members == ["BigTree"]


def test_merged_grouping_fields():
    merged = MergedGrouping(layout_md5="xyz", groups=[], has_edits=False)
    assert merged.layout_md5 == "xyz"
    assert merged.edited_props == set()


# ─── MD5 keying determinism ────────────────────────────────────────────────────

def test_layout_md5_is_deterministic():
    path = _make_layout_file(b"<xlights_rgbeffects/>")
    try:
        md5_a = layout_md5(path)
        md5_b = layout_md5(path)
        assert md5_a == md5_b
        assert len(md5_a) == 32  # hex digest
    finally:
        path.unlink()


def test_layout_md5_differs_for_different_content():
    path_a = _make_layout_file(b"<xlights_rgbeffects/>")
    path_b = _make_layout_file(b"<xlights_rgbeffects version='2'/>")
    try:
        assert layout_md5(path_a) != layout_md5(path_b)
    finally:
        path_a.unlink()
        path_b.unlink()


def test_edits_path_is_sibling_of_layout():
    path = _make_layout_file(b"<xlights_rgbeffects/>")
    try:
        ep = edits_path(path)
        assert ep.parent == path.parent
        assert ep.name.endswith("_grouping_edits.json")
        assert ep.name.startswith(layout_md5(path))
    finally:
        path.unlink()


# ─── JSON round-trip ───────────────────────────────────────────────────────────

def test_edits_roundtrip_empty():
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    data = edits_to_dict(edits)
    restored = edits_from_dict(data)
    assert restored.layout_md5 == edits.layout_md5
    assert restored.moves == []
    assert restored.added_groups == []
    assert restored.removed_groups == []
    assert restored.renamed_groups == {}


def test_edits_roundtrip_with_moves_and_groups():
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        moves=[PropMove("PropA", 4, "04_BEAT_1", "04_BEAT_2")],
        added_groups=[GroupDef("08_HERO_NewTree", 8, ["BigTree"])],
        removed_groups=["04_BEAT_2"],
        renamed_groups={"04_BEAT_1": "04_BEAT_Alpha"},
    )
    data = edits_to_dict(edits)
    restored = edits_from_dict(data)
    assert len(restored.moves) == 1
    assert restored.moves[0].prop_name == "PropA"
    assert restored.moves[0].tier == 4
    assert len(restored.added_groups) == 1
    assert restored.added_groups[0].name == "08_HERO_NewTree"
    assert restored.removed_groups == ["04_BEAT_2"]
    assert restored.renamed_groups == {"04_BEAT_1": "04_BEAT_Alpha"}


# ─── apply_edits ──────────────────────────────────────────────────────────────

def test_apply_edits_no_edits_returns_baseline():
    baseline = _baseline_groups()
    merged = apply_edits(baseline, None, _all_prop_names())
    assert merged.has_edits is False
    assert len(merged.groups) == len(baseline)
    assert merged.edited_props == set()


def test_apply_edits_move_prop():
    baseline = _baseline_groups()
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        moves=[PropMove("PropA", 4, "04_BEAT_1", "04_BEAT_2")],
    )
    merged = apply_edits(baseline, edits, _all_prop_names())
    grp1 = next(g for g in merged.groups if g.name == "04_BEAT_1")
    grp2 = next(g for g in merged.groups if g.name == "04_BEAT_2")
    assert "PropA" not in grp1.members
    assert "PropA" in grp2.members
    assert "PropA" in merged.edited_props


def test_apply_edits_move_to_ungrouped():
    baseline = _baseline_groups()
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        moves=[PropMove("PropA", 4, "04_BEAT_1", None)],
    )
    merged = apply_edits(baseline, edits, _all_prop_names())
    grp1 = next(g for g in merged.groups if g.name == "04_BEAT_1")
    assert "PropA" not in grp1.members
    assert "PropA" in merged.edited_props


def test_apply_edits_add_group():
    baseline = _baseline_groups()
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        added_groups=[GroupDef("08_HERO_BigTree", 8, ["PropA"])],
    )
    merged = apply_edits(baseline, edits, _all_prop_names())
    hero_grp = next((g for g in merged.groups if g.name == "08_HERO_BigTree"), None)
    assert hero_grp is not None
    assert "PropA" in hero_grp.members


def test_apply_edits_remove_group():
    baseline = _baseline_groups()
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        removed_groups=["04_BEAT_2"],
    )
    merged = apply_edits(baseline, edits, _all_prop_names())
    group_names = {g.name for g in merged.groups}
    assert "04_BEAT_2" not in group_names


def test_apply_edits_rename_group():
    baseline = _baseline_groups()
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        renamed_groups={"04_BEAT_1": "04_BEAT_Alpha"},
    )
    merged = apply_edits(baseline, edits, _all_prop_names())
    group_names = {g.name for g in merged.groups}
    assert "04_BEAT_Alpha" in group_names
    assert "04_BEAT_1" not in group_names


def test_apply_edits_prunes_stale_props():
    baseline = _baseline_groups()
    edits = GroupingEdits(
        layout_md5="abc",
        layout_path="/x.xml",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        moves=[PropMove("StaleProp", 4, "04_BEAT_1", "04_BEAT_2")],
    )
    # StaleProp not in all_prop_names
    merged = apply_edits(baseline, edits, _all_prop_names())
    # Should not raise; StaleProp is silently ignored
    grp2 = next(g for g in merged.groups if g.name == "04_BEAT_2")
    assert "StaleProp" not in grp2.members


# ─── Group mutations ──────────────────────────────────────────────────────────

def test_add_group_valid():
    edits = GroupingEdits(layout_md5="abc", layout_path="/fake/x.xml",
                          created_at="", updated_at="")
    add_group_to_edits(edits, "08_HERO_BigTree", 8)
    assert any(g.name == "08_HERO_BigTree" for g in edits.added_groups)


def test_add_group_wrong_prefix():
    edits = GroupingEdits(layout_md5="x", layout_path="/x", created_at="", updated_at="")
    with pytest.raises(ValueError, match="tier prefix"):
        add_group_to_edits(edits, "WrongName", 8)


def test_add_group_duplicate():
    edits = GroupingEdits(layout_md5="x", layout_path="/x", created_at="", updated_at="",
                          added_groups=[GroupDef("08_HERO_BigTree", 8)])
    with pytest.raises(ValueError, match="already exists"):
        add_group_to_edits(edits, "08_HERO_BigTree", 8)


def test_remove_group():
    edits = GroupingEdits(layout_md5="x", layout_path="/x", created_at="", updated_at="")
    remove_group_from_edits(edits, "04_BEAT_2")
    assert "04_BEAT_2" in edits.removed_groups


def test_rename_group_valid():
    edits = GroupingEdits(layout_md5="x", layout_path="/x", created_at="", updated_at="")
    rename_group_in_edits(edits, "04_BEAT_1", "04_BEAT_Alpha")
    assert edits.renamed_groups["04_BEAT_1"] == "04_BEAT_Alpha"


def test_rename_group_wrong_prefix():
    edits = GroupingEdits(layout_md5="x", layout_path="/x", created_at="", updated_at="")
    with pytest.raises(ValueError, match="tier prefix"):
        rename_group_in_edits(edits, "04_BEAT_1", "08_HERO_Wrong")


# ─── Persistence ──────────────────────────────────────────────────────────────

def test_save_and_load_edits():
    path = _make_layout_file(b"<xlights_rgbeffects/>")
    try:
        edits = new_edits(path)
        edits.moves.append(PropMove("PropA", 4, "04_BEAT_1", "04_BEAT_2"))
        save_edits(edits, path)

        loaded = load_edits(path)
        assert loaded is not None
        assert len(loaded.moves) == 1
        assert loaded.moves[0].prop_name == "PropA"
    finally:
        ep = edits_path(path)
        if ep.exists():
            ep.unlink()
        path.unlink()


def test_load_edits_returns_none_when_no_file():
    path = _make_layout_file(b"<xlights_rgbeffects/>")
    try:
        result = load_edits(path)
        assert result is None
    finally:
        path.unlink()


def test_reset_edits_deletes_file():
    path = _make_layout_file(b"<xlights_rgbeffects/>")
    try:
        edits = new_edits(path)
        save_edits(edits, path)
        assert edits_path(path).exists()
        reset_edits(path)
        assert not edits_path(path).exists()
    finally:
        ep = edits_path(path)
        if ep.exists():
            ep.unlink()
        path.unlink()


# ─── Export ───────────────────────────────────────────────────────────────────

def test_export_grouping_produces_valid_json():
    path = _make_layout_file(b"<xlights_rgbeffects/>")
    try:
        baseline = _baseline_groups()
        merged = MergedGrouping(
            layout_md5=layout_md5(path),
            groups=baseline,
            has_edits=False,
        )
        out = export_grouping(merged, path)
        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert all("name" in g and "tier" in g and "members" in g for g in data)
    finally:
        from src.grouper.editor import export_path
        ep = export_path(path)
        if ep.exists():
            ep.unlink()
        path.unlink()
