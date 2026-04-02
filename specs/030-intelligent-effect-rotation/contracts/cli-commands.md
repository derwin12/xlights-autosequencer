# CLI Contracts: Intelligent Effect Rotation

## `xlight-analyze rotation-report <plan-json>`

Display the rotation plan showing which effect variant was assigned to each group in each section, with scoring rationale.

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| plan-json | path | yes | Path to the sequence plan JSON (output of `generate`) |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| --section | str | (all) | Filter to a specific section label (e.g., "chorus") |
| --group | str | (all) | Filter to a specific group name |
| --format | choice | table | Output format: "table" or "json" |

### Output (table format)

```
Section        Group                  Effect Variant        Score  Top Factors
─────────────  ─────────────────────  ────────────────────  ─────  ──────────────────────
Verse 1        06_PROP_CandyCane      bars-gentle-sweep     0.82   prop=1.0, energy=0.75
Verse 1        06_PROP_Arch           single-strand-chase   0.79   prop=1.0, energy=0.75
Verse 1        07_COMP_WindowFrame    shimmer-soft          0.71   tier=1.0, energy=0.50
Verse 1        08_HERO_MegaTree       spirals-dramatic      0.85   tier=1.0, prop=1.0
Chorus 1       06_PROP_CandyCane      meteors-rain-fast     0.88   energy=1.0, prop=0.75
...

Symmetry pairs: Arch_Left ↔ Arch_Right (name), Tree_L ↔ Tree_R (spatial)
Sections: 12 | Groups: 6 | Unique variants used: 18
```

### Output (json format)

```json
{
  "rotation_plan": {
    "sections_count": 12,
    "groups_count": 6,
    "symmetry_pairs": [
      {"group_a": "06_PROP_Arch_Left", "group_b": "06_PROP_Arch_Right", "method": "name"}
    ],
    "entries": [
      {
        "section_index": 0,
        "section_label": "verse",
        "group_name": "06_PROP_CandyCane",
        "variant_name": "bars-gentle-sweep",
        "base_effect": "Bars",
        "score": 0.82,
        "score_breakdown": {"prop_type": 1.0, "energy_level": 0.75, "tier_affinity": 0.5, "section_role": 1.0, "scope": 0.5, "genre": 0.5},
        "source": "pool"
      }
    ]
  }
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Plan file not found or invalid |
| 2 | No rotation data in plan (pre-feature sequences) |
