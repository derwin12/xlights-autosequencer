# API Contract: Theme Editor Endpoints

**Blueprint**: `theme_bp` | **URL Prefix**: `/themes` | **Date**: 2026-04-01

All endpoints return JSON. Error responses use `{"error": "message"}` with appropriate HTTP status codes.

---

## GET /themes

Serve the theme editor HTML page (single-page application).

**Response**: HTML (`theme-editor.html`)

**Query Parameters** (consumed by frontend JS, not by Flask):
- `theme` (optional): Theme name to auto-select on load
- `mode` (optional): `edit` to open directly in edit mode

---

## GET /themes/api/list

Return all themes (built-in and custom) with metadata.

**Response** `200`:

```json
{
  "themes": [
    {
      "name": "Inferno",
      "mood": "aggressive",
      "occasion": "general",
      "genre": "rock",
      "intent": "High-energy fire effects for intense sections",
      "layers": [
        {
          "effect": "Fire",
          "blend_mode": "Normal",
          "parameter_overrides": {"E_SLIDER_Fire_Height": 80}
        },
        {
          "effect": "Shockwave",
          "blend_mode": "Additive",
          "parameter_overrides": {}
        }
      ],
      "palette": ["#FF4400", "#FF8800", "#FFCC00", "#FFFFFF"],
      "accent_palette": ["#FF6600", "#FFAA00"],
      "variants": [
        {
          "layers": [
            {"effect": "Meteors", "blend_mode": "Normal", "parameter_overrides": {}}
          ]
        }
      ],
      "is_custom": false,
      "has_builtin_override": false
    }
  ],
  "moods": ["ethereal", "aggressive", "dark", "structural"],
  "occasions": ["general", "christmas", "halloween"],
  "genres": ["rock", "pop", "classical", "any"]
}
```

**Notes**:
- `is_custom`: true if the theme is from `~/.xlight/custom_themes/`
- `has_builtin_override`: true if a custom theme overrides a built-in (same name exists in both)
- `moods`, `occasions`, `genres`: valid enum values for filter dropdowns and form selects

---

## GET /themes/api/effects

Return all available effects with their parameters (for layer editor auto-populate).

**Response** `200`:

```json
{
  "effects": [
    {
      "name": "Fire",
      "category": "nature",
      "layer_role": "standalone",
      "parameters": [
        {
          "name": "Height",
          "storage_name": "E_SLIDER_Fire_Height",
          "widget_type": "slider",
          "value_type": "int",
          "default": 50,
          "min": 0,
          "max": 100,
          "choices": null
        }
      ]
    }
  ],
  "blend_modes": [
    "Normal", "Additive", "Subtractive", "Layered", "Average",
    "Max", "Min", "Effect 1", "Effect 2",
    "1 is Mask", "2 is Mask", "1 is Unmask", "2 is Unmask",
    "1 is True Unmask", "2 is True Unmask",
    "1 reveals 2", "2 reveals 1",
    "Shadow 1 on 2", "Shadow 2 on 1",
    "Bottom-Top", "Left-Right",
    "Highlight", "Highlight Vibrant", "Brightness"
  ]
}
```

---

## POST /themes/api/save

Create a new custom theme or update an existing custom theme.

**Request Body**:

```json
{
  "theme": {
    "name": "My New Theme",
    "mood": "ethereal",
    "occasion": "general",
    "genre": "any",
    "intent": "Gentle flowing ambient lights",
    "layers": [
      {
        "effect": "Color Wash",
        "blend_mode": "Normal",
        "parameter_overrides": {}
      }
    ],
    "palette": ["#4488FF", "#88CCFF", "#FFFFFF"],
    "accent_palette": [],
    "variants": []
  },
  "original_name": null
}
```

**Fields**:
- `theme`: Complete theme object to save
- `original_name`: If renaming, the previous name (to delete old file). `null` for new themes or in-place edits.

**Response** `200` (success):

```json
{
  "success": true,
  "theme_name": "My New Theme",
  "file_path": "/home/user/.xlight/custom_themes/my-new-theme.json"
}
```

**Response** `400` (validation error):

```json
{
  "error": "Theme name 'Inferno' already exists. Choose a different name.",
  "validation_errors": [
    "Name 'Inferno' conflicts with existing built-in theme"
  ]
}
```

**Response** `400` (other validation errors):

```json
{
  "error": "Theme validation failed",
  "validation_errors": [
    "Palette must have at least 2 colors",
    "Bottom layer must use Normal blend mode"
  ]
}
```

**Validation**:
1. Name uniqueness: checked against ALL themes (built-in + custom). For renames (`original_name` set), the original name is excluded from the check.
2. Theme structure: validated via existing `validate_theme()` from `src/themes/validator.py`.
3. On success: writes JSON file, reloads ThemeLibrary in-process.

---

## POST /themes/api/delete

Delete a custom theme.

**Request Body**:

```json
{
  "name": "My Old Theme"
}
```

**Response** `200`:

```json
{
  "success": true,
  "theme_name": "My Old Theme"
}
```

**Response** `400` (cannot delete built-in):

```json
{
  "error": "Cannot delete built-in theme 'Inferno'. Only custom themes can be deleted."
}
```

**Response** `404` (not found):

```json
{
  "error": "Custom theme 'Nonexistent' not found."
}
```

**Notes**:
- Only custom themes can be deleted. Built-in themes return 400.
- After deletion, ThemeLibrary is reloaded. If the deleted theme was overriding a built-in, the built-in reappears.

---

## POST /themes/api/restore

Restore a built-in theme by deleting its custom override.

**Request Body**:

```json
{
  "name": "Inferno"
}
```

**Response** `200`:

```json
{
  "success": true,
  "theme_name": "Inferno",
  "message": "Custom override removed. Built-in 'Inferno' restored."
}
```

**Response** `400` (no override exists):

```json
{
  "error": "No custom override exists for 'Inferno'. Nothing to restore."
}
```

**Response** `400` (not a built-in):

```json
{
  "error": "'My Theme' is not a built-in theme. Use delete instead."
}
```

---

## POST /themes/api/validate

Validate a theme without saving (for real-time client-side feedback).

**Request Body**:

```json
{
  "theme": { ... },
  "original_name": null
}
```

**Response** `200` (valid):

```json
{
  "valid": true,
  "errors": []
}
```

**Response** `200` (invalid — note: still 200, errors in body):

```json
{
  "valid": false,
  "errors": [
    "Palette must have at least 2 colors",
    "Effect 'NonexistentEffect' not found in effect library"
  ]
}
```

**Notes**: Same validation as `/themes/api/save` but does not write to disk. Useful for debounced validation as the user edits.
