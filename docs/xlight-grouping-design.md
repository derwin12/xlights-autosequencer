# Automated xLights Grouping Algorithm — Design Spec

**Created**: 2026-03-25
**Updated**: 2026-03-26 — expanded from 6 to 8 tiers after testing against real layouts
**Status**: Implemented — `xlight-analyze group-layout` command

---

## 1. The Core Objective

To create a scalable, layout-agnostic algorithm that ingests any 2D or 3D xLights layout and automatically generates a hierarchical set of "Power Groups." These groups allow for independent control, rhythmic synchronization, and layered visual effects without manual selection.

---

## 2. Tiered Taxonomy (Render Order)

The algorithm assigns every prop to a set of groups organized by Render Order. In xLights, higher-numbered tiers override lower-numbered tiers.

| Tier | Category | Prefix | Purpose |
|------|----------|--------|---------|
| 8 | Heroes | `08_HERO_` | Primary focus elements — auto-detected by pixel outlier gap + keyword matching, plus manual `--hero` picks. |
| 7 | Compound | `07_COMP_` | Multi-piece fixtures kept together (e.g., the 4 sides of one window frame, the left-side candy canes). |
| 6 | Prop Type | `06_PROP_` | All props of the same kind (e.g., all candy canes, all windows, all flakes). |
| 5 | Fidelity | `05_TEX_` | High-density vs. Low-density pixels (Matrix vs. Arches). |
| 4 | Rhythm | `04_BEAT_` | Groups of 4 for beat-sync (Left-to-Right and Center-Out). |
| 3 | Architecture | `03_TYPE_` | Orientation groups (Verticals vs. Horizontals). |
| 2 | Spatial | `02_GEO_` | Geographic bins (Top/Mid/Bot, Left/Center/Right). |
| 1 | Canvas | `01_BASE_` | Global group for whole-house washes. |

### Tiers 6 and 7 — Prop Type vs. Compound

These two tiers serve different levels of the same hierarchy:

- **Prop Type (06)**: "All candy canes" — groups every prop of the same kind. Useful for flashing all arches at once, or color-shifting all windows together.
- **Compound (07)**: "The left-side candy canes" or "the 2nd floor right window" — groups the individual pieces of one multi-piece fixture. Useful for chases within a single fixture or keeping a window frame lit as one unit.

A prop can appear in both. For example, `Candy Cane - Left - 3` belongs to:
- `06_PROP_Candy_Cane` (all 8 candy canes)
- `07_COMP_Candy_Cane___Left` (the 4 left-side canes)
- Plus any spatial, rhythm, or fidelity groups based on its position and pixel count.

---

## 3. Spatial Normalization Logic

To work with any house size, the algorithm normalizes coordinates.

1. **Calculate Bounds**: Find X_min/max and Y_min/max for the entire layout.
2. **Normalize**: Every prop is assigned a value from 0.0 to 1.0.
   - Example: A prop at the far left is X=0.0; a prop at the peak of the roof is Y=1.0.
   - If all props share the same X (or Y), they default to 0.5 (center bin).
3. **Automatic Spatial Bins**:
   - Vertical zones: Top (Y > 0.66), Mid (0.33 < Y < 0.66), Bot (Y < 0.33).
   - Horizontal zones: Left (X < 0.33), Center (0.33 < X < 0.66), Right (X > 0.66).
   - Empty bins (no props in that zone) are omitted from output.

---

## 4. The "Four-Beat" Rhythmic Algorithm

This logic creates sequences of four props to match a 4/4 musical time signature.

### Method A: Left-to-Right (Linear)
1. Sort all props by their normalized X coordinate.
2. Partition the list into groups of 4: [1,2,3,4], [5,6,7,8]...
3. The final group may contain 1–3 props (remainder is kept, not discarded).

### Method B: Center-Out (Symmetrical)
1. Calculate distance from midpoint: |X - 0.5| for every prop.
2. Sort props by distance (closest to center first).
3. Group in sets of 4 to create "explosive" outward symmetry.

Both methods run independently over the same prop list, producing two complete sets of beat groups (`04_BEAT_LR_*` and `04_BEAT_CO_*`).

---

## 5. Classification

### Architecture (Tier 3): Vertical vs. Horizontal

- For **Single Line / Poly Line** models: uses `X2`/`Y2` endpoint offsets from the XML. If `|Y2| > |X2|`, it's Vertical.
- For all other models: uses `ScaleY / ScaleX` aspect ratio. If ≥ 1.5, it's Vertical.
- Everything else is classified as Horizontal.

### Fidelity (Tier 5): Pixel Density

- **High-Density** (`05_TEX_HiDens`): pixel count > 500.
- **Low-Density** (`05_TEX_LoDens`): pixel count ≤ 500.
- For **Custom models** (e.g., GE Flakes, Gingerbread Men), pixel count is the number of non-empty cells in the `CustomModel` CSV grid — NOT `parm1 × parm2`, which is just the grid dimensions and vastly overcounts.

### Prop Type (Tier 6): Name-Based Grouping

Extracts the broadest category from each prop name by stripping:
- Everything after the first ` - ` separator
- Trailing numbers and single-letter variants (e.g., `GE Flake I 3` → `GE Flake`)

Props sharing the same category name are grouped together. Groups with only one member are omitted.

### Compound (Tier 7): Multi-Piece Fixture Grouping

Detects props that share a name prefix before the last ` - ` separator. For example:
- `Window - 2nd Floor Right - Top`, `- Left`, `- Right`, `- Bottom 1`, `- Bottom 2` → one `07_COMP_Window___2nd_Floor_Right` group.

### Heroes (Tier 8): Focus Elements

Hero detection combines three sources:

1. **Keyword matching**: Props with "face", "megatree", or "mega tree" (case-insensitive) in their name.
2. **Pixel outlier detection**: Examines the top 10 props by pixel count and finds the largest ratio gap between adjacent counts. Props above the gap are auto-heroes. This catches high-pixel-count props like panel matrices without needing keyword matches.
3. **Explicit `--hero` flags**: User can manually add any prop by name.

The `--no-auto-heroes` flag disables the pixel outlier detection, leaving only keyword + explicit picks.

---

## 6. The Category Toggle System (Show Profiles)

To prevent the sequencer from becoming cluttered, the algorithm supports Show Profiles via `--profile`.

| Profile | Active Tiers | Best For |
|---------|-------------|----------|
| **Energetic** | Architecture (3), Rhythm (4), Prop Type (6), Heroes (8) | Rock, pop, upbeat dance |
| **Cinematic** | Canvas (1), Spatial (2), Compound (7), Heroes (8) | Slow ballads, holiday, instrumental |
| **Technical** | Canvas (1), Fidelity (5) | Hardware testing, calibration |
| *(no flag)* | All 8 tiers | First-time setup, full exploration |

---

## 7. Implementation

### CLI Command

```bash
xlight-analyze group-layout <LAYOUT_FILE> [--profile PROFILE] [--dry-run] [--output PATH]
                                          [--hero "Prop Name"] [--no-auto-heroes]
```

### XML Format Support

The algorithm handles both xLights XML formats:
- **Modern** (`<xrgb><models><model .../></models><modelGroups><modelGroup .../></modelGroups></xrgb>`)
- **Legacy** (`<xlights_rgbeffects><model .../><ModelGroup .../></xlights_rgbeffects>`)

Auto-generated groups are identified by their tier prefix (`01_BASE_` through `08_HERO_`). On re-run, old auto-groups are removed and replaced; manual groups are never touched.

A `.xml.bak` backup is created on the first in-place write.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | File not found |
| 2 | XML parse error |
| 3 | No `<model>` elements found |

---

## 8. Mapping: Music Analysis Hierarchy → Light Group Tiers

This section connects the [musical analysis hierarchy](hierarchy.md) to the grouping tiers above. Each analysis level drives effects on specific group tiers.

| Analysis Level | What It Produces | Which Group Tiers It Drives | How |
|----------------|-----------------|----------------------------|-----|
| **L0: Special Moments** | Energy impacts, gaps, novelty peaks | **08_HERO** + **01_BASE** | Impacts trigger hero overrides (flash the mega tree, face reaction). Gaps trigger whole-house blackout/fade on BASE. |
| **L1: Structure** | Sections (verse, chorus, bridge) with repeat labels | **01_BASE** + **02_GEO** | Section changes trigger color palette shifts on BASE. Repeat sections reuse the same palette/effect set. Non-repeat sections get unique treatments. |
| **L2: Bars & Phrases** | Bar boundaries (~0.5/s) | **04_BEAT** | Bar marks reset chase patterns. Each bar = one cycle of the 4-beat group sequence. |
| **L3: Beats** | Beat positions (~2/s) | **04_BEAT** | Each beat steps to the next prop in the 4-group sequence (L-R or Center-Out). |
| **L4: Instrument Events** | Onset events per stem (drums, guitar, bass, vocals) | **03_TYPE** + **05_TEX** + **06_PROP** | Drum onsets → flash Verticals. Guitar onsets → pulse Horizontals. Vocal entries → activate Hero faces. Per-prop-type effects (all candy canes flash on snare). High-density props get complex patterns, low-density get simple flashes. |
| **L5: Energy Curves** | Continuous 0-100 value curves (.xvc) | **01_BASE** + **02_GEO** + **03_TYPE** | Energy curves drive brightness/speed/size as continuous automation. Per-stem curves map to architecture groups (drum energy → Verticals brightness). |
| **L6: Harmonic Color** | Chord changes, key changes | **01_BASE** + **02_GEO** + **07_COMP** | Chord changes trigger color shifts on spatial groups (left = warm, right = cool). Key changes shift the entire BASE palette. Compound groups can have per-fixture color treatments. |

### Show Profile → Analysis Level Selection

| Profile | Active Tiers | Analysis Levels Used |
|---------|-------------|---------------------|
| **Energetic** | 03_TYPE, 04_BEAT, 06_PROP, 08_HERO | L0 (impacts), L2 (bars), L3 (beats), L4 (instrument events) |
| **Cinematic** | 01_BASE, 02_GEO, 07_COMP, 08_HERO | L0 (moments), L1 (structure), L5 (energy curves), L6 (color) |
| **Technical** | 01_BASE, 05_TEX | L5 (energy curves) — hardware testing with continuous automation |
