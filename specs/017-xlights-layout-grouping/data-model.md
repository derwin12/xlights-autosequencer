# Data Model: xLights Layout Grouping

**Date**: 2026-03-26
**Branch**: `017-xlights-layout-grouping`

---

## Core Entities

### `Prop`
A single light model parsed from `xlights_rgbeffects.xml`.

| Field | Type | Source in XML | Description |
|-------|------|---------------|-------------|
| `name` | `str` | `model[@name]` | Unique model name |
| `display_as` | `str` | `model[@DisplayAs]` | Model type string (e.g., "Tree 360", "Arch", "Matrix") |
| `world_x` | `float` | `model[@WorldPosX]` | Raw world X coordinate |
| `world_y` | `float` | `model[@WorldPosY]` | Raw world Y coordinate |
| `world_z` | `float` | `model[@WorldPosZ]` | Raw world Z coordinate (default 0.0) |
| `scale_x` | `float` | `model[@ScaleX]` | X scale factor (used for aspect ratio) |
| `scale_y` | `float` | `model[@ScaleY]` | Y scale factor (used for aspect ratio) |
| `parm1` | `int` | `model[@parm1]` | Number of strings (model-type dependent) |
| `parm2` | `int` | `model[@parm2]` | Lights per string (model-type dependent) |
| `sub_models` | `list[str]` | `model/subModel[@name]` | Names of child sub-models |
| `pixel_count` | `int` | computed: `parm1 * parm2` | Estimated total node count |
| `norm_x` | `float` | computed | Normalized X position [0.0, 1.0] |
| `norm_y` | `float` | computed | Normalized Y position [0.0, 1.0] |
| `aspect_ratio` | `float` | computed: `scale_y / scale_x` | Height-to-width ratio |

---

### `SpatialBounds`
Bounding box used for coordinate normalization.

| Field | Type | Description |
|-------|------|-------------|
| `x_min`, `x_max` | `float` | Horizontal extents across all props |
| `y_min`, `y_max` | `float` | Vertical extents across all props |

Normalization formula: `norm_x = (world_x - x_min) / (x_max - x_min)` (clamped to [0, 1]; if range is 0, default to 0.5).

---

### `PowerGroup`
A named collection of props assigned to a tier.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Full group name with tier prefix (e.g., `04_BEAT_LR_1`) |
| `tier` | `int` | Tier number 1–6 |
| `members` | `list[str]` | Prop names included in this group (order matters for render) |

**Naming convention**: `{tier:02d}_{PREFIX}_{Label}` where prefix and label come from the tier definitions table in the design doc.

---

### `ShowProfile`
Controls which tiers are generated.

| Profile | Active Tiers |
|---------|-------------|
| `energetic` | 3 (Architecture), 4 (Rhythm), 6 (Prop Type), 8 (Heroes) |
| `cinematic` | 1 (Canvas), 2 (Spatial), 7 (Compound), 8 (Heroes) |
| `technical` | 1 (Canvas), 5 (Fidelity) |
| *(none / all)* | 1, 2, 3, 4, 5, 6, 7, 8 |

---

### `Layout`
The parsed in-memory representation of `xlights_rgbeffects.xml`.

| Field | Type | Description |
|-------|------|-------------|
| `props` | `list[Prop]` | All models parsed from the file |
| `source_path` | `Path` | Absolute path to the source XML file |
| `raw_tree` | `ET.ElementTree` | Full parsed XML tree (for round-trip writing) |

---

## Tier Definitions

| Tier | Category | Name Prefix | Generation Rule |
|------|----------|-------------|-----------------|
| 1 | Canvas | `01_BASE_` | One group containing all props |
| 2 | Spatial | `02_GEO_` | Six groups by coordinate bin (Top/Mid/Bot × Left/Center/Right) |
| 3 | Architecture | `03_TYPE_` | Two groups: Vertical (aspect ≥ 1.5) and Horizontal |
| 4 | Rhythm | `04_BEAT_` | N groups of 4 by L-R sort; N groups of 4 by Center-Out sort |
| 5 | Fidelity | `05_TEX_` | Two groups: HiDens (pixel_count > 500) and LoDens |
| 6 | Prop Type | `06_PROP_` | All props of the same kind (by root name extraction) |
| 7 | Compound | `07_COMP_` | Multi-piece fixtures (shared name prefix before last ` - `) |
| 8 | Heroes | `08_HERO_` | Keyword match + pixel outlier gap + explicit `--hero` picks |

---

## State Transitions

```
xlights_rgbeffects.xml
        │
        ▼
   parse_layout()     → Layout (with raw_tree preserved)
        │
        ▼
   normalize_coords() → Prop.norm_x, Prop.norm_y set on all props
        │
        ▼
   classify_props()   → aspect_ratio, pixel_count computed
        │
        ▼
   generate_groups()  → list[PowerGroup] (filtered by ShowProfile)
        │
        ▼
   inject_groups()    → raw_tree updated (old auto-groups removed, new inserted)
        │
        ▼
   write_layout()     → updated xlights_rgbeffects.xml
```

---

## Auto-Group Identification

Groups are identified as auto-generated (and therefore safe to remove on re-run) if their `name` attribute starts with any of: `01_BASE_`, `02_GEO_`, `03_TYPE_`, `04_BEAT_`, `05_TEX_`, `06_PROP_`, `07_COMP_`, `08_HERO_`.

Manual groups (no auto prefix) are never touched.
