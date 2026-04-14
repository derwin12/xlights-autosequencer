# Data Model: Prop-Type Effect Affinity (041)

No new entities, schemas, or stored data. This feature modifies in-memory generation
logic only.

## Affected Existing Entities

### `PowerGroup` (`src/grouper/models.py`)
No change. The `prop_type: str | None` field already exists and is already populated
by `generate_groups()`. This feature reads `prop_type` but does not modify the entity.

### `EffectDefinition` (`src/effects/models.py`)
No change. The `prop_suitability: dict[str, str]` field already exists with ratings
per canonical prop type key. This feature reads `prop_suitability` but does not modify
the entity.

### `RotationPlan` (`src/generator/rotation.py`)
No schema change. The plan's internal assignment logic gains within-tier base-effect
tracking as a local variable during `build_rotation_plan()` — not persisted to the
plan object.

## In-Memory State Added (not persisted)

**`used_effects_per_tier: dict[int, set[str]]`** — transient dict keyed by tier number,
values are sets of base effect names already assigned in that tier for the current
section. Lives only within the scope of `build_rotation_plan()` for a single section.
Discarded after each section's assignments are complete.
