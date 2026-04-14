# Research: Prop-Type Effect Affinity (041)

## Decision 1: Dedup at base-effect level, not variant level

**Decision**: Track `used_base_effects: set[str]` per tier (e.g., "Spirals"), not
per variant (e.g., "Spirals 3D Fast Spin").

**Rationale**: Two groups showing "Spirals 3D Fast" and "Spirals Dense Slow" still
look redundant from a distance — the viewer sees two spinning-ring effects, not two
distinct animations. Deduplication at the base-effect level ensures visible variety.
Variant-level dedup already exists (the `used_in_section` mechanism from embrace_repetition=False)
and is distinct from what this feature adds.

**Alternatives considered**:
- Variant-level dedup: Already exists; this feature adds a complementary layer.
- Effect-family dedup (e.g., all "circular" effects as one family): Over-engineered for the current need.

---

## Decision 2: Dedup is within-tier, not section-wide

**Decision**: Track used effects per tier independently. Arch groups in tier 6 and
hero groups in tier 8 can both use Bars without conflict.

**Rationale**: Tiers represent visual layers with distinct roles (base wash, architecture,
props, hero). The same base effect on two different tiers reads as intentional layering,
not redundancy. Enforcing uniqueness across tiers would unnecessarily restrict the
effect palette.

**Alternatives considered**:
- Section-wide dedup: Too restrictive; would prevent thematically consistent effects across layers.
- No dedup (current behavior): Causes all groups in the same tier to pile onto the top-scored effect.

---

## Decision 3: Best-effort, not hard guarantee

**Decision**: When the number of groups in a tier exceeds available distinct suitable
effects, reuse is allowed starting from the highest-scored effect.

**Rationale**: Some layouts have many groups of the same prop type (e.g., 12 candy
cane arches). There are not 12 distinct arch-suitable effects. Forcing uniqueness would
require using poor-fit effects to fill the slots, which is worse than reuse.

**Alternatives considered**:
- Hard uniqueness: Would degrade quality when pool is smaller than group count.
- Random selection: Would break reproducibility (Constitution Principle I).

---

## Decision 4: Fallback pool filtering removes only `not_recommended`

**Decision**: Filter `not_recommended` effects from `_build_effect_pool()` when prop_type
is provided. Keep `possible`-rated effects in the pool. Relax to `possible` if `ideal`+`good`
filtering empties the pool.

**Rationale**: `not_recommended` means the effect genuinely looks wrong on that prop shape
(e.g., Plasma on a single-pixel arch). `possible` means "works, not ideal" — acceptable
for a fallback path that is rarely triggered. Filtering only the hard exclusions preserves
pool depth without degrading quality.

**Alternatives considered**:
- Filter both `not_recommended` and `possible`: Too aggressive; could empty the pool.
- No filtering (current behavior): Allows visually wrong effects on incompatible props.

---

## Existing Infrastructure Confirmed

The following already exists and requires no modification:

| Component | File | Status |
|-----------|------|--------|
| `PowerGroup.prop_type` field | `src/grouper/grouper.py` | ✅ Populated from `dominant_prop_type()` |
| `DISPLAY_AS_TO_PROP_TYPE` mapping | `src/grouper/layout.py` | ✅ All xLights DisplayAs values covered |
| `prop_suitability` on all effects | `src/effects/builtin_effects.json` | ✅ All 35+ effects rated |
| `EffectDefinition.prop_suitability` | `src/effects/models.py` | ✅ Dict field |
| RotationEngine prop_type scoring | `src/generator/rotation.py` | ✅ 0.30 weight, already working |
| `_build_effect_pool()` signature | `src/generator/effect_placer.py` | ✅ Needs `prop_type` param only |
