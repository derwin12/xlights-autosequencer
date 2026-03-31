# API Routes Contract: Layout Group Editor

**Feature**: 022-layout-group-editor | **Date**: 2026-03-30

## Base URL

`http://localhost:5173` (same as existing review server)

## Routes

### GET `/grouper`

Serves the layout group editor HTML page.

**Response**: `text/html` — `grouper.html`

---

### GET `/grouper/layout`

Returns the current layout with baseline grouping and any saved edits applied.

**Query Parameters**:
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| path | string | Yes | Absolute path to xLights layout XML file |

**Response** (200):
```json
{
  "layout_md5": "a1b2c3d4...",
  "layout_path": "/path/to/xlights_rgbeffects.xml",
  "props": [
    {
      "name": "RooflineLeft",
      "display_as": "Poly Line",
      "pixel_count": 250,
      "norm_x": 0.35,
      "norm_y": 0.92
    }
  ],
  "tiers": [
    {
      "tier": 1,
      "label": "Canvas",
      "prefix": "01_BASE_",
      "groups": [
        {
          "name": "01_BASE_All",
          "members": ["RooflineLeft", "RooflineRight", "..."],
          "is_user_created": false
        }
      ],
      "ungrouped": ["TuneToSign"]
    }
  ],
  "has_edits": true,
  "edited_props": ["TuneToSign", "GarageLeft"]
}
```

**Error** (400): `{"error": "Layout file not found"}`

---

### POST `/grouper/move`

Move one or more props between groups within a tier.

**Request Body**:
```json
{
  "layout_md5": "a1b2c3d4...",
  "moves": [
    {
      "prop_name": "GarageLeft",
      "tier": 4,
      "from_group": "04_BEAT_1",
      "to_group": "04_BEAT_2"
    }
  ]
}
```

- `from_group` is `null` if moving from Ungrouped.
- `to_group` is `null` if moving to Ungrouped.

**Response** (200):
```json
{
  "success": true,
  "tier": 4,
  "groups": [ /* updated groups for this tier */ ],
  "ungrouped": [ /* updated ungrouped for this tier */ ],
  "edited_props": ["GarageLeft"]
}
```

**Error** (400): `{"error": "Prop 'X' not found in layout"}`
**Error** (409): `{"error": "Prop 'X' already in group 'Y'"}`

---

### POST `/grouper/group/create`

Create a new user group within a tier.

**Request Body**:
```json
{
  "layout_md5": "a1b2c3d4...",
  "tier": 8,
  "name": "08_HERO_NewTree"
}
```

**Response** (200):
```json
{
  "success": true,
  "group": {
    "name": "08_HERO_NewTree",
    "tier": 8,
    "members": [],
    "is_user_created": true
  }
}
```

**Error** (400): `{"error": "Group name must start with tier prefix '08_HERO_'"}`
**Error** (409): `{"error": "Group 'X' already exists"}`

---

### POST `/grouper/group/delete`

Delete a group. Members move to Ungrouped for that tier.

**Request Body**:
```json
{
  "layout_md5": "a1b2c3d4...",
  "group_name": "08_HERO_NewTree"
}
```

**Response** (200):
```json
{
  "success": true,
  "displaced_props": ["NewTree"],
  "tier": 8,
  "ungrouped": ["NewTree"]
}
```

---

### POST `/grouper/group/rename`

Rename an existing group.

**Request Body**:
```json
{
  "layout_md5": "a1b2c3d4...",
  "old_name": "08_HERO_OldName",
  "new_name": "08_HERO_NewName"
}
```

**Response** (200):
```json
{
  "success": true,
  "group": { "name": "08_HERO_NewName", "tier": 8, "members": ["..."] }
}
```

**Error** (400): `{"error": "New name must keep tier prefix '08_HERO_'"}`

---

### POST `/grouper/save`

Persist current edits to the edit file.

**Request Body**:
```json
{
  "layout_md5": "a1b2c3d4..."
}
```

**Response** (200):
```json
{
  "success": true,
  "edits_path": "/path/to/a1b2c3d4_grouping_edits.json"
}
```

---

### POST `/grouper/reset`

Discard all edits and return to baseline auto-generated grouping.

**Request Body**:
```json
{
  "layout_md5": "a1b2c3d4..."
}
```

**Response** (200):
```json
{
  "success": true,
  "message": "All edits discarded. Showing baseline grouping."
}
```

---

### POST `/grouper/export`

Export the merged grouping (baseline + edits) as a `_grouping.json` file.

**Request Body**:
```json
{
  "layout_md5": "a1b2c3d4..."
}
```

**Response** (200):
```json
{
  "success": true,
  "export_path": "/path/to/a1b2c3d4_grouping.json",
  "group_count": 24,
  "has_edits": true,
  "edited_prop_count": 3
}
```
