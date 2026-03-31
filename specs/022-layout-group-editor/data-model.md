# Data Model: Layout Group Editor

**Feature**: 022-layout-group-editor | **Date**: 2026-03-30

## Entities

### Prop (existing — `src/grouper/layout.py`)

Represents a single lighting model/fixture parsed from the xLights layout XML.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| name | str | XML `name` attr | Unique within layout |
| display_as | str | XML `DisplayAs` attr | e.g., "Poly Line", "Tree 360" |
| world_x | float | XML `WorldPosX` | Raw 3D position |
| world_y | float | XML `WorldPosY` | Raw 3D position |
| world_z | float | XML `WorldPosZ` | Raw 3D position |
| scale_x | float | XML `ScaleX` | Scale factor |
| scale_y | float | XML `ScaleY` | Scale factor |
| parm1 | int | XML `parm1` | Strings count |
| parm2 | int | XML `parm2` | Lights per string |
| sub_models | list[str] | XML `<subModel>` children | Named sub-model parts |
| pixel_count | int | Computed | `parm1 * parm2` or custom grid count |
| norm_x | float | Computed | Normalized [0.0, 1.0] |
| norm_y | float | Computed | Normalized [0.0, 1.0] |
| aspect_ratio | float | Computed | `scale_y / scale_x` |

**Identity**: `name` (unique within a layout file)

### Layout (existing — `src/grouper/layout.py`)

Container for all props parsed from a single xLights layout file.

| Field | Type | Notes |
|-------|------|-------|
| props | list[Prop] | All models found in XML |
| source_path | Path | Absolute path to XML file |
| raw_tree | ET.ElementTree | Parsed XML for round-trip |

**Identity**: `source_path` (one layout per file)

### PowerGroup (existing — `src/grouper/grouper.py`)

A named group of props within a specific tier.

| Field | Type | Notes |
|-------|------|-------|
| name | str | e.g., "04_BEAT_1", "08_HERO_MegaTree" |
| tier | int | 1-8 |
| members | list[str] | Prop names |

**Identity**: `name` (unique across all tiers)
**Constraint**: A prop can appear in at most one group per tier.

### GroupingEdits (new — `src/grouper/editor.py`)

Overlay of user modifications on top of the auto-generated baseline grouping. Keyed by MD5 hash of the layout file content.

| Field | Type | Notes |
|-------|------|-------|
| layout_md5 | str | MD5 hex digest of layout file content |
| layout_path | str | Original layout file path (informational) |
| created_at | str | ISO 8601 timestamp of first edit |
| updated_at | str | ISO 8601 timestamp of last save |
| moves | list[PropMove] | Props moved between groups |
| added_groups | list[GroupDef] | User-created groups |
| removed_groups | list[str] | Names of deleted groups |
| renamed_groups | dict[str, str] | Old name → new name mappings |

**Identity**: `layout_md5`
**Persistence**: `<md5>_grouping_edits.json` adjacent to layout file

### PropMove (new — `src/grouper/editor.py`)

Records a single prop reassignment within a tier.

| Field | Type | Notes |
|-------|------|-------|
| prop_name | str | Name of the moved prop |
| tier | int | Tier where the move occurred |
| from_group | str or None | Original group name (None if was ungrouped) |
| to_group | str or None | Target group name (None if moved to ungrouped) |

### GroupDef (new — `src/grouper/editor.py`)

Definition of a user-created group.

| Field | Type | Notes |
|-------|------|-------|
| name | str | Group name (must follow tier prefix convention) |
| tier | int | Tier assignment |
| members | list[str] | Prop names added to this group |

### MergedGrouping (new — `src/grouper/editor.py`)

The result of applying edits to the baseline. Used for export and display.

| Field | Type | Notes |
|-------|------|-------|
| layout_md5 | str | Source layout hash |
| groups | list[PowerGroup] | Final merged group list |
| has_edits | bool | Whether any user edits were applied |
| edited_props | set[str] | Prop names that differ from baseline (for UI indicators) |

**Persistence**: `<md5>_grouping.json` (export only)

## Relationships

```
Layout (1) ──── contains ──── (*) Prop
Layout (1) ──── generates ──── (*) PowerGroup [baseline]
Layout (1) ──── has ──── (0..1) GroupingEdits [user overlay]
PowerGroup (*) ──── contains ──── (*) Prop [within same tier: 1 group per prop]
GroupingEdits (1) ──── produces ──── (1) MergedGrouping [baseline + edits]
```

## State Transitions

### GroupingEdits Lifecycle

```
[No edits file] ──(user makes first edit)──> [Draft]
[Draft] ──(user saves)──> [Saved]
[Saved] ──(user makes more edits)──> [Unsaved changes]
[Unsaved changes] ──(user saves)──> [Saved]
[Saved] ──(user resets)──> [No edits file]
[Saved] ──(user exports)──> [Exported] (creates _grouping.json)
```

## Validation Rules

1. **Unique membership per tier**: A prop can belong to at most one group within a single tier. Moving a prop to a new group in that tier automatically removes it from the previous group.
2. **Group name uniqueness**: Group names must be unique across all tiers (enforced by the tier prefix convention).
3. **Tier prefix convention**: Group names must start with the tier prefix (e.g., `01_BASE_`, `02_GEO_`, etc.) to maintain sort order and identification.
4. **Prop existence**: All prop names in edits must correspond to props that exist in the current layout. Stale references to removed props are pruned on load.
5. **Non-empty export**: The exported `_grouping.json` must contain at least the Tier 1 base group (even if empty after user edits, to signal intentional exclusion).
