"""Layout group editor — overlay/diff model for user edits on top of auto-generated grouping.

Edit persistence:
  - Baseline grouping: generated fresh from parse_layout + generate_groups on each load
  - Edits: stored as <md5>_grouping_edits.json adjacent to the layout file (overlay only)
  - Merged: baseline + edits applied, used for display and export

File naming (keyed by MD5 of layout file content):
  - Edit file:   <md5>_grouping_edits.json
  - Export file: <md5>_grouping.json
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class PropMove:
    """Records a single prop reassignment within a tier."""
    prop_name: str
    tier: int
    from_group: str | None  # None = was ungrouped
    to_group: str | None    # None = moved to ungrouped


@dataclass
class GroupDef:
    """Definition of a user-created group."""
    name: str
    tier: int
    members: list[str] = field(default_factory=list)


@dataclass
class GroupingEdits:
    """Overlay of user modifications on top of auto-generated baseline grouping."""
    layout_md5: str
    layout_path: str
    created_at: str
    updated_at: str
    moves: list[PropMove] = field(default_factory=list)
    added_groups: list[GroupDef] = field(default_factory=list)
    removed_groups: list[str] = field(default_factory=list)
    renamed_groups: dict[str, str] = field(default_factory=dict)


@dataclass
class MergedGrouping:
    """Result of applying edits to the baseline grouping."""
    layout_md5: str
    groups: list  # list[PowerGroup] — avoid circular import
    has_edits: bool
    edited_props: set[str] = field(default_factory=set)


# ─── File keying ──────────────────────────────────────────────────────────────

def layout_md5(layout_path: Path) -> str:
    """Return MD5 hex digest of the layout file content."""
    return hashlib.md5(layout_path.read_bytes()).hexdigest()


def edits_path(layout_path: Path) -> Path:
    """Return path for the edit file adjacent to the layout file."""
    md5 = layout_md5(layout_path)
    return layout_path.parent / f"{md5}_grouping_edits.json"


def export_path(layout_path: Path) -> Path:
    """Return path for the merged export file adjacent to the layout file."""
    md5 = layout_md5(layout_path)
    return layout_path.parent / f"{md5}_grouping.json"


# ─── Serialization ────────────────────────────────────────────────────────────

def edits_to_dict(edits: GroupingEdits) -> dict:
    """Serialize GroupingEdits to a JSON-compatible dict."""
    return {
        "layout_md5": edits.layout_md5,
        "layout_path": edits.layout_path,
        "created_at": edits.created_at,
        "updated_at": edits.updated_at,
        "moves": [
            {
                "prop_name": m.prop_name,
                "tier": m.tier,
                "from_group": m.from_group,
                "to_group": m.to_group,
            }
            for m in edits.moves
        ],
        "added_groups": [
            {
                "name": g.name,
                "tier": g.tier,
                "members": g.members,
            }
            for g in edits.added_groups
        ],
        "removed_groups": edits.removed_groups,
        "renamed_groups": edits.renamed_groups,
    }


def edits_from_dict(data: dict) -> GroupingEdits:
    """Deserialize GroupingEdits from a JSON-compatible dict."""
    return GroupingEdits(
        layout_md5=data["layout_md5"],
        layout_path=data["layout_path"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        moves=[
            PropMove(
                prop_name=m["prop_name"],
                tier=m["tier"],
                from_group=m["from_group"],
                to_group=m["to_group"],
            )
            for m in data.get("moves", [])
        ],
        added_groups=[
            GroupDef(
                name=g["name"],
                tier=g["tier"],
                members=g.get("members", []),
            )
            for g in data.get("added_groups", [])
        ],
        removed_groups=data.get("removed_groups", []),
        renamed_groups=data.get("renamed_groups", {}),
    )


# ─── Persistence ──────────────────────────────────────────────────────────────

def save_edits(edits: GroupingEdits, layout_path: Path) -> None:
    """Persist edits to <md5>_grouping_edits.json adjacent to layout file."""
    edits.updated_at = datetime.now(timezone.utc).isoformat()
    path = edits_path(layout_path)
    path.write_text(json.dumps(edits_to_dict(edits), indent=2), encoding="utf-8")


def load_edits(layout_path: Path, all_prop_names: list[str] | None = None) -> GroupingEdits | None:
    """Load edits from disk. Returns None if no edit file exists.

    If all_prop_names is provided, prunes stale prop references from moves
    and added_group members (props removed from the layout since edits were saved).
    """
    path = edits_path(layout_path)
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    edits = edits_from_dict(data)

    if all_prop_names is not None:
        _prune_stale_props(edits, set(all_prop_names))

    return edits


def reset_edits(layout_path: Path) -> None:
    """Delete the edit file for this layout, returning to baseline grouping."""
    path = edits_path(layout_path)
    if path.exists():
        path.unlink()


# ─── Baseline loading ─────────────────────────────────────────────────────────

def load_baseline(layout_path: Path) -> tuple[list, list[str]]:
    """Parse layout and generate baseline groups.

    Returns (baseline_groups: list[PowerGroup], all_prop_names: list[str]).
    Calls parse_layout, normalize_coords, classify_props, generate_groups
    from existing grouper modules.
    """
    from src.grouper.classifier import classify_props, normalize_coords
    from src.grouper.grouper import generate_groups
    from src.grouper.layout import parse_layout

    layout = parse_layout(layout_path)
    normalize_coords(layout.props)
    classify_props(layout.props)
    groups = generate_groups(layout.props)
    prop_names = [p.name for p in layout.props]
    return groups, prop_names


# ─── Edit application ─────────────────────────────────────────────────────────

def apply_edits(
    baseline: list,
    edits: GroupingEdits | None,
    all_prop_names: list[str],
) -> MergedGrouping:
    """Apply user edits on top of baseline groups.

    Returns a MergedGrouping with the final group list and the set of
    prop names that differ from the baseline (for UI diff indicators).

    Constraints enforced:
    - A prop can belong to at most one group per tier.
    - Moving a prop to a group it already belongs to is a no-op.
    - Stale prop names (not in all_prop_names) are ignored.
    """
    from src.grouper.grouper import PowerGroup

    if edits is None:
        return MergedGrouping(
            layout_md5="",
            groups=list(baseline),
            has_edits=False,
            edited_props=set(),
        )

    valid_props = set(all_prop_names)
    edited_props: set[str] = set()

    # Deep copy baseline groups into mutable dicts keyed by name
    groups_by_name: dict[str, PowerGroup] = {}
    for g in baseline:
        from src.grouper.grouper import PowerGroup as PG
        groups_by_name[g.name] = PG(
            name=g.name,
            tier=g.tier,
            members=list(g.members),
        )

    # Apply renames first (so subsequent operations use new names)
    for old_name, new_name in edits.renamed_groups.items():
        if old_name in groups_by_name:
            grp = groups_by_name.pop(old_name)
            grp.name = new_name
            groups_by_name[new_name] = grp

    # Apply group removals (displaced members go to ungrouped — tracked separately)
    for removed_name in edits.removed_groups:
        if removed_name in groups_by_name:
            del groups_by_name[removed_name]

    # Apply user-created groups
    for gdef in edits.added_groups:
        if gdef.name not in groups_by_name:
            from src.grouper.grouper import PowerGroup as PG
            groups_by_name[gdef.name] = PG(
                name=gdef.name,
                tier=gdef.tier,
                members=[m for m in gdef.members if m in valid_props],
            )

    # Build per-tier membership map for duplicate detection
    # tier -> prop_name -> group_name
    tier_membership: dict[int, dict[str, str]] = {}
    for grp in groups_by_name.values():
        tm = tier_membership.setdefault(grp.tier, {})
        for member in grp.members:
            tm[member] = grp.name

    # Apply prop moves
    for move in edits.moves:
        if move.prop_name not in valid_props:
            continue  # stale prop

        tier = move.tier
        tm = tier_membership.setdefault(tier, {})

        # Remove from current group
        current_group_name = tm.get(move.prop_name)
        if current_group_name and current_group_name in groups_by_name:
            grp = groups_by_name[current_group_name]
            if move.prop_name in grp.members:
                grp.members.remove(move.prop_name)
        if move.prop_name in tm:
            del tm[move.prop_name]

        # Add to target group
        if move.to_group is not None:
            if move.to_group not in groups_by_name:
                # Target group was deleted — treat as move to ungrouped
                pass
            else:
                target = groups_by_name[move.to_group]
                if move.prop_name not in target.members:
                    target.members.append(move.prop_name)
                    tm[move.prop_name] = move.to_group

        edited_props.add(move.prop_name)

    # Compute layout_md5 from edits record
    merged_md5 = edits.layout_md5

    return MergedGrouping(
        layout_md5=merged_md5,
        groups=list(groups_by_name.values()),
        has_edits=True,
        edited_props=edited_props,
    )


# ─── Export ───────────────────────────────────────────────────────────────────

def export_grouping(merged: MergedGrouping, layout_path: Path) -> Path:
    """Export merged grouping as <md5>_grouping.json adjacent to layout file.

    Produces a list of {name, tier, members} objects covering all tiers.
    Returns the path of the exported file.
    """
    out = export_path(layout_path)
    data = [
        {"name": g.name, "tier": g.tier, "members": list(g.members)}
        for g in sorted(merged.groups, key=lambda g: (g.tier, g.name))
    ]
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


# ─── Group mutations (for CRUD routes) ────────────────────────────────────────

_TIER_PREFIXES = {
    1: "01_BASE_",
    2: "02_GEO_",
    3: "03_TYPE_",
    4: "04_BEAT_",
    5: "05_TEX_",
    6: "06_PROP_",
    7: "07_COMP_",
    8: "08_HERO_",
}

_TIER_LABELS = {
    1: "Canvas",
    2: "Spatial",
    3: "Architecture",
    4: "Rhythm",
    5: "Fidelity",
    6: "Prop Type",
    7: "Compound",
    8: "Heroes",
}


def tier_prefix(tier: int) -> str:
    return _TIER_PREFIXES.get(tier, f"0{tier}_")


def add_group_to_edits(edits: GroupingEdits, name: str, tier: int) -> None:
    """Add a new user-created group. Raises ValueError on validation failure."""
    prefix = tier_prefix(tier)
    if not name.startswith(prefix):
        raise ValueError(f"Group name must start with tier prefix '{prefix}'")
    # Check uniqueness across existing added groups
    for g in edits.added_groups:
        if g.name == name:
            raise ValueError(f"Group '{name}' already exists")
    edits.added_groups.append(GroupDef(name=name, tier=tier))


def remove_group_from_edits(edits: GroupingEdits, group_name: str) -> None:
    """Mark a group for removal. Members will move to Ungrouped when edits are applied."""
    if group_name not in edits.removed_groups:
        edits.removed_groups.append(group_name)
    # Remove from added_groups if it was user-created
    edits.added_groups = [g for g in edits.added_groups if g.name != group_name]


def rename_group_in_edits(edits: GroupingEdits, old_name: str, new_name: str) -> None:
    """Record a group rename. Raises ValueError on validation failure."""
    # Infer tier from old name prefix
    tier = None
    for t, prefix in _TIER_PREFIXES.items():
        if old_name.startswith(prefix):
            tier = t
            break
    if tier is None:
        raise ValueError(f"Cannot determine tier for group '{old_name}'")
    prefix = tier_prefix(tier)
    if not new_name.startswith(prefix):
        raise ValueError(f"New name must keep tier prefix '{prefix}'")
    edits.renamed_groups[old_name] = new_name


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _prune_stale_props(edits: GroupingEdits, valid_props: set[str]) -> None:
    """Remove references to props that no longer exist in the layout."""
    edits.moves = [m for m in edits.moves if m.prop_name in valid_props]
    for gdef in edits.added_groups:
        gdef.members = [m for m in gdef.members if m in valid_props]


def new_edits(layout_path: Path) -> GroupingEdits:
    """Create a fresh empty GroupingEdits for the given layout file."""
    md5 = layout_md5(layout_path)
    now = datetime.now(timezone.utc).isoformat()
    return GroupingEdits(
        layout_md5=md5,
        layout_path=str(layout_path),
        created_at=now,
        updated_at=now,
    )
