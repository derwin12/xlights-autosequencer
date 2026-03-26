# CLI Contract: group-layout Command

**Date**: 2026-03-26
**Branch**: `017-xlights-layout-grouping`

---

## Command Signature

```
xlight-analyze group-layout <LAYOUT_FILE> [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `LAYOUT_FILE` | Yes | Path to `xlights_rgbeffects.xml`. Must exist and be a readable file. |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--profile` | `choice` | *(none — all tiers)* | Show profile: `energetic`, `cinematic`, or `technical`. |
| `--dry-run` | `flag` | `False` | Print group summary to stdout without modifying the file. |
| `--output` | `path` | *(in-place)* | Write output to a different path instead of overwriting input. |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — groups written (or dry-run completed) |
| 1 | Input file not found or not readable |
| 2 | XML parse error — input file is not valid XML |
| 3 | No `<model>` elements found in layout |

---

## Dry-Run Output Format

When `--dry-run` is used, prints a table to stdout:

```
xLights Layout Grouping — Dry Run
Layout:  /path/to/xlights_rgbeffects.xml
Profile: energetic
Props:   24

Tier  Group Name         Members
----  -----------------  -------
01    01_BASE_All        24
02    02_GEO_Top         8
02    02_GEO_Mid         10
02    02_GEO_Bot         6
...
04    04_BEAT_LR_1       4
04    04_BEAT_LR_2       4
...

Total groups: 14
No files modified (dry run).
```

---

## Normal Run Output Format

```
xLights Layout Grouping
Layout:  /path/to/xlights_rgbeffects.xml
Profile: (all)
Props:   24

Generated 18 groups across 6 tiers.
Removed 0 previous auto-groups.
Written: /path/to/xlights_rgbeffects.xml
```

---

## XML Output Contract

Generated groups are injected as `<ModelGroup>` elements in `xlights_rgbeffects.xml`:

```xml
<ModelGroup name="01_BASE_All" models="RooflineLeft,RooflineRight,Arch1,Arch2" />
<ModelGroup name="02_GEO_Top" models="RooflineLeft,RooflineRight" />
<ModelGroup name="04_BEAT_LR_1" models="Arch1,Arch2,GarageLeft,GarageRight" />
```

**Constraints**:
- `name` attribute: conforms to `NN_PREFIX_Label` (no characters rejected by xLights — alphanumeric, underscore, hyphen only)
- `models` attribute: comma-separated list of model names, no spaces
- Groups are inserted as children of the root element, after all `<model>` elements
- Empty groups (no members) are omitted
