# API Contracts: Intelligent Effect Rotation

## GET /rotation-report/<plan_hash>

Returns the rotation plan for a generated sequence, showing per-section, per-group variant assignments with scoring metadata.

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| plan_hash | str | The source audio MD5 hash identifying the sequence plan |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| section | str | (all) | Filter entries to a specific section label |
| group | str | (all) | Filter entries to a specific group name |

### Response 200

```json
{
  "rotation_plan": {
    "sections_count": 12,
    "groups_count": 6,
    "symmetry_pairs": [
      {
        "group_a": "06_PROP_Arch_Left",
        "group_b": "06_PROP_Arch_Right",
        "detection_method": "name",
        "mirror_direction": true
      }
    ],
    "entries": [
      {
        "section_index": 0,
        "section_label": "verse",
        "group_name": "06_PROP_CandyCane",
        "group_tier": 6,
        "variant_name": "bars-gentle-sweep",
        "base_effect": "Bars",
        "score": 0.82,
        "score_breakdown": {
          "prop_type": 1.0,
          "energy_level": 0.75,
          "tier_affinity": 0.5,
          "section_role": 1.0,
          "scope": 0.5,
          "genre": 0.5
        },
        "source": "pool"
      }
    ],
    "summary": {
      "unique_variants_used": 18,
      "variety_score": 0.85,
      "continuity_overrides": 3
    }
  }
}
```

### Response 404

```json
{"error": "No rotation plan found for hash '<plan_hash>'"}
```

## GET /themes/<name>/effect-pools

Returns the effect pool configuration for a theme's layers, showing which variant names are available for rotation.

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| name | str | Theme name (case-insensitive) |

### Response 200

```json
{
  "theme": "Ethereal Frost",
  "layers": [
    {
      "index": 0,
      "effect": "Color Wash",
      "effect_pool": [],
      "variant_ref": null
    },
    {
      "index": 1,
      "effect": "Butterfly",
      "effect_pool": ["butterfly-gentle-blue", "butterfly-sparkle-frost", "shimmer-ice-crystal"],
      "variant_ref": null
    }
  ]
}
```

### Response 404

```json
{"error": "Theme 'xyz' not found"}
```
