# Data Model: Intelligent Effect Rotation

## Entities

### Prop Type Mapping (from 029, merged)

A lookup table in `src/grouper/layout.py` that maps xLights DisplayAs strings to canonical prop suitability keys.

| DisplayAs Value | Prop Type Key | Category |
|----------------|---------------|----------|
| Matrix | matrix | Grid |
| Tree 360, Tree Flat, Tree Ribbon, Tree | tree | Tree |
| Arch, Arches, Candy Cane, Candy Canes | arch | Arch/curved |
| Circle, Spinner, Star, Wreath | radial | Radial/spinner |
| Icicles, Window Frame | vertical | Vertical |
| Single Line, Poly Line, Custom, Channel Block, Image, Cube, Sphere | outline | Linear (default) |

Unknown DisplayAs values default to "outline".

### PowerGroup (extended, from 029, merged)

Existing dataclass in `src/grouper/grouper.py`, extended with one new field.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| name | str | (required) | Group name (existing) |
| tier | int | (required) | Tier number 1-8 (existing) |
| members | list[str] | [] | Prop names (existing) |
| prop_type | str \| None | None | **NEW**: Canonical suitability key derived from member props' DisplayAs values via majority vote |

### Suitability Score Mapping (from 029, merged)

Graduated scoring for the variant scorer's `_score_prop_type` function.

| Rating | Score | Description |
|--------|-------|-------------|
| ideal | 1.0 | Best visual fit for this prop type |
| good | 0.75 | Works well on this prop type |
| possible | 0.25 | Functional but not optimal |
| not_recommended | 0.0 | Poor visual result on this prop type |
| (not in dict) | 0.0 | Unknown prop type |
| (no context) | 0.5 | Neutral — no prop type specified |

### RotationPlan

The complete per-section, per-group variant assignment for a sequence. Pre-computed by the RotationEngine before effect placement.

| Field | Type | Description |
|-------|------|-------------|
| entries | list[RotationEntry] | Ordered list of variant assignments |
| sections_count | int | Number of sections in the plan |
| groups_count | int | Number of groups assigned |
| symmetry_pairs | list[SymmetryGroup] | Detected symmetry pairs used during planning |

### RotationEntry

A single variant assignment for one group in one section.

| Field | Type | Description |
|-------|------|-------------|
| section_index | int | Index into the section list (0-based) |
| section_label | str | Section label (e.g., "verse", "chorus") |
| group_name | str | Power group name (e.g., "06_PROP_CandyCane") |
| group_tier | int | Power group tier (5-8) |
| variant_name | str | Selected variant name |
| base_effect | str | The variant's base effect name |
| score | float | Total weighted score for this assignment |
| score_breakdown | dict[str, float] | Per-dimension scores (prop_type, energy_level, tier_affinity, section_role, scope, genre) |
| source | str | "pool" (from theme effect_pool), "library" (from variant scorer), or "continuity" (forced for transition) |

### SymmetryGroup

A pair of power groups that should receive the same effect with mirrored direction.

| Field | Type | Description |
|-------|------|-------------|
| group_a | str | First group name |
| group_b | str | Second group name (receives mirrored direction) |
| detection_method | str | "name" (pattern match), "spatial" (position-based), or "manual" (override) |
| mirror_direction | bool | Whether to mirror direction parameters for group_b |

### EffectLayer (extended)

Existing dataclass in `src/themes/models.py`, extended with one new field.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| effect | str | (required) | Base effect name (existing) |
| blend_mode | str | "Normal" | Blend mode (existing) |
| parameter_overrides | dict | {} | Parameter overrides (existing) |
| variant_ref | str \| None | None | Single variant reference (existing, from 028) |
| effect_pool | list[str] | [] | **NEW**: List of variant names for intelligent rotation. When non-empty, the rotation engine selects from this pool based on context. |

**Backward compatibility**: When `effect_pool` is empty (default), behavior is identical to today. The `effect` field is always used for tiers 1-4. The `variant_ref` field is used if set and no effect_pool is defined. Priority: effect_pool > variant_ref > effect.

### ScoringContext Mapping

Maps section/group/theme state to the existing `ScoringContext` from `src/variants/scorer.py`.

| ScoringContext field | Source | Mapping |
|---------------------|--------|---------|
| base_effect | variant.base_effect | Direct — filters candidates to matching base effect |
| prop_type | group.prop_type | Direct — from PowerGroup (e.g., "arch", "matrix") |
| energy_level | section.energy_score | 0-33→"low", 34-66→"medium", 67-100→"high" |
| tier_affinity | group.tier | 5→"mid", 6→"mid", 7→"foreground", 8→"hero" |
| section_role | section.label | Direct — "verse", "chorus", "bridge", "intro", "outro", "drop" |
| scope | — | Not set (neutral 0.5) |
| genre | theme.genre | Direct — "any", "rock", "pop", etc. |

## Relationships

```
Theme
  └── layers: list[EffectLayer]
        ├── effect (base effect name)
        ├── variant_ref (single variant, optional)
        └── effect_pool (variant name list, optional) ──┐
                                                         │
RotationEngine                                           │
  ├── inputs: sections, groups, variant_library ─────────┘
  ├── symmetry_pairs: list[SymmetryGroup]
  └── output: RotationPlan
        └── entries: list[RotationEntry]
              ├── references: EffectVariant (from variant library)
              └── consumed by: effect_placer.py → EffectPlacement
```

## State Transitions

### RotationEngine Build Process

```
1. INIT: Receive sections, groups, themes, variant_library, effect_library
   │
2. DETECT_SYMMETRY: Run symmetry detection → SymmetryGroup list
   │
3. FOR EACH section:
   │ a. Build ScoringContext per group from section + group + theme
   │ b. Gather candidates: theme.effect_pool (if set) → scored variants
   │    If pool empty or no pool → full library scored variants
   │ c. Greedy assign: best variant per group, excluding already-used
   │ d. Apply symmetry: copy assignment from group_a to group_b
   │ e. Apply repeat penalty: penalize variants used in previous same-type section
   │ f. Check continuity: ensure ≥1 shared variant with previous section
   │
4. OUTPUT: RotationPlan with all entries
```

## Validation Rules

- `effect_pool` entries must reference variant names that exist in the variant library (warn on missing, don't error)
- `RotationEntry.score` must be ≥ 0.0
- `SymmetryGroup.group_a` and `group_b` must be distinct group names
- `RotationPlan.entries` must cover every group at tiers 5-8 for every section
- Determinism: same inputs must produce same RotationPlan
