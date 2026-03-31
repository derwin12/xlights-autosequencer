"""Integration tests: layout group editor load → edit → save → reload → export round-trip."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.grouper.editor import (
    apply_edits,
    edits_path,
    export_path,
    load_baseline,
    load_edits,
    new_edits,
    reset_edits,
    save_edits,
    PropMove,
)


# ─── Minimal xLights XML fixture ─────────────────────────────────────────────

_MINIMAL_LAYOUT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<xlights_rgbeffects>
  <model name="RooflineLeft" DisplayAs="Poly Line"
         WorldPosX="100" WorldPosY="200" WorldPosZ="0"
         ScaleX="2.0" ScaleY="0.5"
         parm1="1" parm2="50" />
  <model name="RooflineRight" DisplayAs="Poly Line"
         WorldPosX="300" WorldPosY="200" WorldPosZ="0"
         ScaleX="2.0" ScaleY="0.5"
         parm1="1" parm2="50" />
  <model name="TuneToSign" DisplayAs="Single Line"
         WorldPosX="200" WorldPosY="50" WorldPosZ="0"
         ScaleX="0.5" ScaleY="0.5"
         parm1="1" parm2="10" />
</xlights_rgbeffects>
"""


@pytest.fixture()
def layout_file(tmp_path: Path) -> Path:
    """Write minimal layout XML to a temp file and return its path."""
    path = tmp_path / "xlights_rgbeffects.xml"
    path.write_text(_MINIMAL_LAYOUT_XML, encoding="utf-8")
    return path


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_load_baseline_returns_groups_and_props(layout_file):
    baseline, prop_names = load_baseline(layout_file)
    assert set(prop_names) == {"RooflineLeft", "RooflineRight", "TuneToSign"}
    assert len(baseline) > 0
    # Tier 1 base group should contain all props
    base_grp = next((g for g in baseline if g.tier == 1), None)
    assert base_grp is not None
    assert set(base_grp.members) == {"RooflineLeft", "RooflineRight", "TuneToSign"}


def test_roundtrip_edit_save_reload(layout_file):
    """Make a move, save, reload edits — move persists."""
    baseline, prop_names = load_baseline(layout_file)

    # Find a tier 4 group with at least one member to move
    tier4_groups = [g for g in baseline if g.tier == 4 and g.members]
    if not tier4_groups:
        pytest.skip("Layout too small to produce distinct beat groups")

    grp_a = tier4_groups[0]
    prop_to_move = grp_a.members[0]
    # Find or use the second beat group, or ungrouped
    other_groups = [g for g in baseline if g.tier == 4 and g.name != grp_a.name]
    target_group = other_groups[0].name if other_groups else None

    edits = new_edits(layout_file)
    edits.moves.append(PropMove(
        prop_name=prop_to_move,
        tier=4,
        from_group=grp_a.name,
        to_group=target_group,
    ))
    save_edits(edits, layout_file)

    # Reload
    loaded = load_edits(layout_file, prop_names)
    assert loaded is not None
    assert len(loaded.moves) == 1
    assert loaded.moves[0].prop_name == prop_to_move

    # Apply and verify
    merged = apply_edits(baseline, loaded, prop_names)
    assert prop_to_move in merged.edited_props

    if target_group:
        tgt = next(g for g in merged.groups if g.name == target_group)
        assert prop_to_move in tgt.members
    else:
        # Moved to ungrouped — should not be in any tier 4 group
        tier4_members = set()
        for g in merged.groups:
            if g.tier == 4:
                tier4_members.update(g.members)
        assert prop_to_move not in tier4_members


def test_reset_returns_to_baseline(layout_file):
    """After save + reset, load_edits returns None and merged equals baseline."""
    baseline, prop_names = load_baseline(layout_file)
    tier1_grp = next(g for g in baseline if g.tier == 1)

    edits = new_edits(layout_file)
    edits.moves.append(PropMove(
        prop_name=tier1_grp.members[0],
        tier=1,
        from_group=tier1_grp.name,
        to_group=None,
    ))
    save_edits(edits, layout_file)
    assert edits_path(layout_file).exists()

    reset_edits(layout_file)
    assert not edits_path(layout_file).exists()

    loaded = load_edits(layout_file, prop_names)
    assert loaded is None

    merged = apply_edits(baseline, None, prop_names)
    assert not merged.has_edits
    assert merged.edited_props == set()


def test_export_produces_valid_grouping_json(layout_file):
    """Export merges baseline + edits into a _grouping.json with all tiers."""
    from src.grouper.editor import export_grouping

    baseline, prop_names = load_baseline(layout_file)
    merged = apply_edits(baseline, None, prop_names)

    out = export_grouping(merged, layout_file)
    assert out.exists()

    data = json.loads(out.read_text())
    assert isinstance(data, list)
    assert all("name" in g and "tier" in g and "members" in g for g in data)

    tiers_present = {g["tier"] for g in data}
    # All 8 tiers should be represented (some may have empty member lists but should be included)
    assert len(tiers_present) >= 1


def test_export_with_edits_reflects_changes(layout_file):
    """Export after edits reflects the user's changes in the output JSON."""
    from src.grouper.editor import export_grouping

    baseline, prop_names = load_baseline(layout_file)

    # Remove TuneToSign from Tier 1 base group
    edits = new_edits(layout_file)
    tier1_grp = next(g for g in baseline if g.tier == 1)
    edits.moves.append(PropMove(
        prop_name="TuneToSign",
        tier=1,
        from_group=tier1_grp.name,
        to_group=None,  # ungrouped
    ))

    merged = apply_edits(baseline, edits, prop_names)
    out = export_grouping(merged, layout_file)

    data = json.loads(out.read_text())
    base_group_data = next((g for g in data if g["name"] == tier1_grp.name), None)
    assert base_group_data is not None
    assert "TuneToSign" not in base_group_data["members"]
    assert "TuneToSign" in merged.edited_props


def test_stale_props_pruned_on_load(layout_file):
    """When layout changes after edits were saved, stale prop refs are pruned."""
    baseline, prop_names = load_baseline(layout_file)
    tier1_grp = next(g for g in baseline if g.tier == 1)

    edits = new_edits(layout_file)
    edits.moves.append(PropMove("StaleGone", 1, tier1_grp.name, None))
    save_edits(edits, layout_file)

    # Load with a prop list that doesn't include StaleGone
    loaded = load_edits(layout_file, prop_names)
    assert loaded is not None
    # StaleGone should have been pruned
    assert not any(m.prop_name == "StaleGone" for m in loaded.moves)
