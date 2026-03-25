# Automated xLights Grouping Algorithm — Design Spec

**Created**: 2026-03-25
**Status**: Initial design — maps light groups to musical analysis hierarchy

---

## 1. The Core Objective

To create a scalable, layout-agnostic algorithm that ingests any 2D or 3D xLights layout and automatically generates a hierarchical set of "Power Groups." These groups allow for independent control, rhythmic synchronization, and layered visual effects without manual selection.

---

## 2. Tiered Taxonomy (Render Order)

The algorithm assigns every prop to a set of groups organized by Render Order. In xLights, higher-numbered tiers override lower-numbered tiers.

| Tier | Category | Prefix | Purpose |
|------|----------|--------|---------|
| 6 | Heroes | `06_HERO_` | Primary focus elements (Singing Faces, Mega Trees). |
| 5 | Fidelity | `05_TEX_` | High-density vs. Low-density pixels (Matrix vs. Arches). |
| 4 | Rhythm | `04_BEAT_` | Groups of 4 for beat-sync (L-R and Center-Out). |
| 3 | Architecture | `03_TYPE_` | Functional groups (Verticals, Horizontals, Arches). |
| 2 | Spatial | `02_GEO_` | Geographic bins (Top/Mid/Bot, Left/Center/Right). |
| 1 | Canvas | `01_BASE_` | Global groups for whole-house washes. |

---

## 3. Spatial Normalization Logic

To work with any house size, the algorithm must "Normalize" coordinates.

1. **Calculate Bounds**: Find X_min/max, Y_min/max, and Z_min/max for the entire layout.
2. **Normalize**: Every prop is assigned a value from 0.0 to 1.0.
   - Example: A prop at the far left is X=0.0; a prop at the peak of the roof is Y=1.0.
3. **Automatic Spatial Bins**:
   - Horizontal: Top (Y > 0.66), Mid (0.33 < Y < 0.66), Bot (Y < 0.33).
   - Vertical: Left (X < 0.33), Center (0.33 < X < 0.66), Right (X > 0.66).

---

## 4. The "Four-Beat" Rhythmic Algorithm

This logic creates sequences of four props to match a 4/4 musical time signature.

### Method A: Left-to-Right (Linear)
1. Sort all props by their X coordinate.
2. Partition the list into groups of 4: [1,2,3,4], [5,6,7,8]...
3. Optional Overlap: Create "Sliding" groups: [1,2,3,4], [2,3,4,5]... for liquid motion.

### Method B: Center-Out (Symmetrical)
1. Calculate Midpoint = 0.5 (normalized).
2. Calculate Offset = |X - 0.5| for every prop.
3. Sort props by Offset (closest to center first).
4. Group in sets of 4 to create "explosive" outward symmetry.

---

## 5. Functional & Fidelity Classification

The algorithm parses prop names and pixel counts to determine their "Texture."

- **Verticals vs. Horizontals**: Calculates Aspect Ratio (Height/Width). If >1.5, it's a Vertical.
- **High-Res vs. Low-Res**: If pixel count >500 (or a specific density threshold), it's tagged as "High-Density" for complex video/text effects.
- **Sub-Model Detection**: If a prop name contains "Face," the algorithm automatically searches for and groups sub-models (Eyes, Mouths) into their own "Hero" overrides.

---

## 6. The Category Toggle System (The Filter)

To prevent the sequencer from becoming cluttered, the algorithm supports Show Profiles. You select which categories to generate based on the song type.

- **"Energetic" Profile**: Generates all `04_BEAT` and `03_TYPE` groups.
- **"Cinematic" Profile**: Generates only `02_GEO` (Spatial) and `06_HERO` groups for slow, sweeping movements.
- **"Technical" Profile**: Generates `05_TEX` (Density) and `01_BASE` for hardware testing.

---

## 7. Implementation Note

The final output of this algorithm is an **XML Injection**. It reads the `xlights_rgbeffects.xml` file, clears old automated groups, and writes the new `<group>` tags based on the selected Profile.

---

## 8. Mapping: Music Analysis Hierarchy → Light Group Tiers

This section connects the [musical analysis hierarchy](musical-analysis-design.md) to the grouping tiers above. Each analysis level drives effects on specific group tiers.

| Analysis Level | What It Produces | Which Group Tiers It Drives | How |
|----------------|-----------------|----------------------------|-----|
| **L0: Special Moments** | Energy impacts, gaps, novelty peaks | **06_HERO** + **01_BASE** | Impacts trigger hero overrides (flash the mega tree, face reaction). Gaps trigger whole-house blackout/fade on BASE. |
| **L1: Structure** | Segmentino sections (A, B, N) with repeat labels | **01_BASE** + **02_GEO** | Section changes trigger color palette shifts on BASE. Repeat sections (A=A=A) reuse the same palette/effect set. Non-repeat sections (N1, N2) get unique one-time treatments. |
| **L2: Bars & Phrases** | Bar boundaries (~0.5/s) | **04_BEAT** | Bar marks reset chase patterns. Each bar = one cycle of the 4-beat group sequence. |
| **L3: Beats** | Beat positions (~2/s) | **04_BEAT** | Each beat steps to the next prop in the 4-group sequence (L-R or Center-Out). |
| **L4: Instrument Events** | Onset events per stem (drums, guitar, bass, vocals) | **03_TYPE** + **05_TEX** | Drum onsets → flash Verticals. Guitar onsets → pulse Horizontals. Vocal entries → activate Hero faces. High-density props get complex patterns, low-density get simple flashes. |
| **L5: Energy Curves** | Continuous 0-100 value curves (.xvc) | **01_BASE** + **02_GEO** + **03_TYPE** | Energy curves drive brightness/speed/size as continuous automation on any tier. Per-stem curves map to architecture groups (drum energy → Verticals brightness). |
| **L6: Harmonic Color** | Chord changes, key changes | **01_BASE** + **02_GEO** | Chord changes trigger color shifts on spatial groups (left side = warm, right side = cool). Key changes shift the entire BASE palette. |

### Show Profile → Analysis Level Selection

| Profile | Active Tiers | Analysis Levels Used |
|---------|-------------|---------------------|
| **Energetic** | 04_BEAT, 03_TYPE, 06_HERO | L0 (impacts), L2 (bars), L3 (beats), L4 (instrument events) |
| **Cinematic** | 02_GEO, 06_HERO, 01_BASE | L0 (moments), L1 (structure), L5 (energy curves), L6 (color) |
| **Technical** | 05_TEX, 01_BASE | L5 (energy curves) — hardware testing with continuous automation |
