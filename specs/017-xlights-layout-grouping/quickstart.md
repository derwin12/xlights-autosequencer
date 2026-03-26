# Quickstart: xLights Layout Grouping

**Date**: 2026-03-26
**Branch**: `017-xlights-layout-grouping`

---

## What This Does

The `group-layout` command reads your `xlights_rgbeffects.xml` file, analyzes all your prop positions and types, and automatically generates hierarchical "Power Groups" that match the musical analysis hierarchy used by the sequencer.

---

## Basic Usage

```bash
# Generate all groups (all 6 tiers) — writes in-place
xlight-analyze group-layout ~/myshow/xlights_rgbeffects.xml

# Preview what groups would be created, without changing anything
xlight-analyze group-layout ~/myshow/xlights_rgbeffects.xml --dry-run

# Generate only groups useful for a fast rock/pop song
xlight-analyze group-layout ~/myshow/xlights_rgbeffects.xml --profile energetic

# Generate only groups useful for a slow holiday song
xlight-analyze group-layout ~/myshow/xlights_rgbeffects.xml --profile cinematic

# Write to a separate file instead of overwriting
xlight-analyze group-layout ~/myshow/xlights_rgbeffects.xml --output ~/myshow/grouped_layout.xml
```

---

## Show Profiles

| Profile | Tiers Generated | Best For |
|---------|----------------|----------|
| *(none)* | All 6 tiers | First-time setup; lets you see everything |
| `energetic` | Architecture (03), Rhythm (04), Heroes (06) | Rock, pop, upbeat dance |
| `cinematic` | Canvas (01), Spatial (02), Heroes (06) | Slow ballads, holiday, instrumental |
| `technical` | Canvas (01), Fidelity (05) | Hardware testing, calibration |

---

## Re-Running Is Safe

The command removes all previously auto-generated groups (identified by their `01_BASE_` through `06_HERO_` prefixes) before writing new ones. Your manually-created groups are never touched.

---

## After Running

1. Open xLights
2. File → Open Project → select your `xlights_rgbeffects.xml`
3. Go to the **Model Groups** tab — you'll see all the new `01_BASE_*`, `02_GEO_*`, etc. groups
4. These groups are now available as targets in your sequence editor

---

## What Gets Generated

For a typical 20-prop residential display:

| Tier | Example Groups Created |
|------|----------------------|
| 01 Canvas | `01_BASE_All` |
| 02 Spatial | `02_GEO_Top`, `02_GEO_Mid`, `02_GEO_Bot`, `02_GEO_Left`, `02_GEO_Center`, `02_GEO_Right` |
| 03 Architecture | `03_TYPE_Vertical`, `03_TYPE_Horizontal` |
| 04 Rhythm | `04_BEAT_LR_1` … `04_BEAT_LR_5`, `04_BEAT_CO_1` … `04_BEAT_CO_5` |
| 05 Fidelity | `05_TEX_HiDens`, `05_TEX_LoDens` |
| 06 Heroes | `06_HERO_SingingFace` (if you have a singing face) |
