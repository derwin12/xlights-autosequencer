# Data Model: Pipeline Decision-Ordering Refactor (048)

All changes are in `src/generator/models.py`. No schema file, no JSON wire change,
no database migration.

## New: `AccentPolicy`

```python
@dataclass
class AccentPolicy:
    drum_hits: bool   # True iff this section will fire per-hit Shockwave on small radial props
    impact: bool      # True iff this section will fire the whole-house white Shockwave at its start
```

**Population site**: `build_plan()` decision-precompute pass (Phase B of plan.md).

**Invariants**:

- Both fields are `False` whenever `config.beat_accent_effects=False`.
- `drum_hits=True` ⇒ `config.beat_accent_effects=True AND section.energy_score >= 60 AND hierarchy.events["drums"]` is present.
- `impact=True` ⇒ `config.beat_accent_effects=True AND section.energy_score > 80 AND (section.end_ms - section.start_ms) >= 4000 AND (section role is unknown OR role ∈ {chorus, drop, climax, build_peak})`.
- Both flags are the *gate outcome* — accent helpers MUST NOT re-evaluate these conditions
  (FR-022). If `impact=True`, `_place_impact_accent` fires unconditionally.

**Future extension path**: When specs 049+ add new accent types (e.g. cymbal-crash flash,
bass-drop wash), they extend this struct with more bool fields. The shape is chosen to
grow additively without forcing UI migrations.

## Extended: `SectionAssignment`

### Before (current, 4 fields)

```python
@dataclass
class SectionAssignment:
    section: SectionEnergy
    theme: Theme
    group_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    variation_seed: int = 0
```

### After (10 fields — 6 added, all with defaults)

```python
@dataclass
class SectionAssignment:
    section: SectionEnergy
    theme: Theme
    group_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    variation_seed: int = 0
    # --- added in 048 ---
    active_tiers: frozenset[int] = field(default_factory=frozenset)
    palette_target: dict[int, int] | None = None
    duration_target: DurationTarget | None = None
    accent_policy: AccentPolicy = field(
        default_factory=lambda: AccentPolicy(drum_hits=False, impact=False)
    )
    working_set: WorkingSet | None = None
    section_index: int = 0
```

All new fields default to safe no-op values so (a) existing test fixtures that construct
`SectionAssignment` directly keep compiling; (b) `regenerate_sections()`'s synthetic
assignment at `plan.py:474` continues to work without touching the new fields.

## Field-by-field contract

### `active_tiers: frozenset[int]`

Set of tier numbers (1–8) that will receive placements in this section. Populated from
`_compute_active_tiers(section, section_index, hierarchy)` when `config.tier_selection=True`,
or `frozenset(range(1, 9))` when `tier_selection=False`.

**Contract with `place_effects`**: `place_effects` iterates over the assignment's
`active_tiers` and never calls `_compute_active_tiers`. Any group whose `group.tier`
is not in this set is skipped.

**Override path (spec 047)**: `assignment.active_tiers = frozenset({1, 8})` — caller
overwrites before re-running placement; the edge case "section selected a tier with no
groups in the layout" silently yields empty `group_effects` (preserved from current
behaviour, see spec edge case list).

### `palette_target: dict[int, int] | None`

- `None` when `config.palette_restraint=False`: no trim; placement passes through the
  tier palette unchanged.
- Otherwise a dict with one entry per tier in `active_tiers`, value ∈ `[1, 6]` — the
  target active-colour count for that tier in this section.

**Population**: call `restrain_palette(dummy_6_color_palette, section.energy_score, tier)`
for each tier in `active_tiers`, store `len(result)`. The actual colour-spread selection
still runs inside `place_effects` at placement time against the *real* per-tier palette
(theme.palette vs accent vs bg), using the stored count as input.

**Why this shape (per spec clarification)**:

- A single `int` cannot represent the per-tier cap divergence (`_TIER_PALETTE_CAP` ranges
  from 3 at tier 1 to 6 at tier 8).
- Per-tier mapping lets spec 047's Brief UI show a "Tier 5: 2 / Tier 8: 5 colours" table
  and let the user override any single entry.
- Storing the *count* rather than the *trimmed palette itself* keeps palette derivation
  (accent vs bg vs theme) where it is today — only the cap moves.

### `duration_target: DurationTarget | None`

- `None` when `config.duration_scaling=False`: placement falls back to the theme layer's
  declared duration (today's behaviour).
- Otherwise the full `DurationTarget(min_ms, target_ms, max_ms)` returned by
  `compute_duration_target(hierarchy.estimated_bpm, section.energy_score)`.

**Contract with `place_effects`**: `place_effects` passes `assignment.duration_target`
through to `_place_effect_on_group` in place of today's (bpm, duration_scaling) pair.
The helper already accepts a `DurationTarget`; its signature does not change.

### `accent_policy: AccentPolicy`

See "New: AccentPolicy" above. Always non-null.

### `working_set: WorkingSet | None`

- `None` when `config.focused_vocabulary=False` or when the theme has no derived working set.
- Otherwise a reference into the per-theme `working_sets[theme.name]` dict that
  `build_plan` already builds at step 3c (`plan.py:160-164`). The reference is shared
  across sections that use the same theme — same object identity as today.

**Contract with `place_effects`**: `focused_vocabulary` is no longer a parameter.
`place_effects` computes `focused_vocabulary := assignment.working_set is not None`
at the top of the function if it needs the boolean at all; otherwise it just branches
on `if assignment.working_set and assignment.working_set.effects:`.

### `section_index: int`

Position within `plan.sections`. Today this is passed as a separate function argument
(`section_index=idx`) and used for (a) rotation plan lookups, (b) random seed derivation.
Carrying it on the assignment means `place_effects` and the accent helpers no longer
need it as a parameter, and User Story 4 (isolation) becomes: "take `plan.sections[2]`,
call `place_effects` on it" — the index rides along.

**Seed contract preserved (FR-033)**: Every seed tuple that today reads
`(section_index, group_index, tier)` continues to read
`(assignment.section_index, group_index, tier)`. Byte-identical seeds.

## Non-changes

- `GenerationConfig` — no field added, no field removed, no default changed (FR-030).
- `SectionEnergy` — unchanged.
- `EffectPlacement` — unchanged.
- `SequencePlan` — unchanged (its `sections` field now contains richer `SectionAssignment`
  instances, but the container is the same).
- `WorkingSet`, `WorkingSetEntry`, `DurationTarget` — unchanged.

## Serialisation (for spec 047 Brief UI)

The Brief reads an assignment via a future JSON serialisation helper (not built in 048).
Target shape:

```json
{
  "section_index": 2,
  "section": {"label": "chorus", "start_ms": 48000, "end_ms": 72000, "energy_score": 82, "mood_tier": "aggressive", "impact_count": 3},
  "theme": {"name": "N5"},
  "active_tiers": [4, 8],
  "palette_target": {"4": 3, "8": 5},
  "duration_target": {"min_ms": 300, "target_ms": 600, "max_ms": 1200},
  "accent_policy": {"drum_hits": true, "impact": true},
  "working_set": null
}
```

Every field visible in the Brief maps 1:1 to a field on the assignment (SC-003). No
derivation from `config` or `hierarchy` at serialisation time.
