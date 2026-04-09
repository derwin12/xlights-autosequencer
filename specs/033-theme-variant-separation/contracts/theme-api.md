# Theme API Contract Changes

**Feature**: 033-theme-variant-separation

## GET /themes/api/list

Response shape unchanged. Theme objects now serialize with:
- `layers[].variant` (string) instead of `layers[].effect` + `layers[].parameter_overrides`
- `alternates[]` instead of `variants[]`

## GET /themes/api/effects

Unchanged — still returns effect names and blend modes for reference.

## GET /themes/api/effect-pools/{name}

Response changes:
- `layers[].variant` replaces `layers[].effect` + `layers[].variant_ref`
- No `parameter_overrides` in response

## POST /themes/api/save

Request body changes:
- `layers[].variant` (required string) — variant name
- `layers[].blend_mode` (string, default "Normal")
- `layers[].effect_pool` (optional list of strings)
- No `effect` or `parameter_overrides` fields accepted
- `alternates[]` replaces `variants[]`

## GET /variants?effect={name}

Unchanged — still returns variants for a given effect. Used by the theme editor's variant picker.

## New: GET /variants/api/list-grouped

Returns all variants grouped by base_effect for the variant picker dropdown:
```json
{
  "groups": [
    {
      "effect": "Butterfly",
      "variants": [
        {"name": "Butterfly Classic", "description": "..."},
        {"name": "Butterfly Classic 2-Chunk", "description": "..."}
      ]
    }
  ]
}
```
