# Quickstart: Prop-Type Effect Affinity (041)

## What It Does

Ensures that within any single tier, no two prop groups show the same base effect
simultaneously. A layout with 5 arch groups will show Bars, Wave, Chase, Single Strand,
and Curtain simultaneously rather than 5x Bars. Tree and radial groups continue to
receive their highest-scoring prop-type-ideal effects (Spirals, Pinwheel, Fan) as before,
but now arch groups alongside them also diversify.

Also closes the fallback pool gap: `_build_effect_pool()` now filters out `not_recommended`
effects for the group's prop type when called in the tier 6-7 fallback path.

## Key Files

| File | Change |
|------|--------|
| `src/generator/rotation.py` | Add `used_effects_per_tier` tracking in `build_rotation_plan()` |
| `src/generator/effect_placer.py` | Add `prop_type` param to `_build_effect_pool()`, wire through |
| `tests/unit/test_rotation.py` | New tests for within-tier diversity and prop-type routing |

## Core Algorithm Change (rotation.py)

```python
# Before (current behavior):
for group in groups_in_tier:
    scored = rank_variants(group, section_theme)
    plan[group.name] = scored[0]  # always top-scored, no dedup

# After (with within-tier dedup):
used_effects_per_tier: dict[int, set[str]] = defaultdict(set)
for group in groups_in_tier:
    scored = rank_variants(group, section_theme)
    tier = group.tier
    for variant, score, breakdown in scored:
        if variant.base_effect not in used_effects_per_tier[tier]:
            plan[group.name] = (variant, score, breakdown)
            used_effects_per_tier[tier].add(variant.base_effect)
            break
    else:
        # All effects used — fall back to best-scored (reuse allowed)
        plan[group.name] = scored[0]
```

## Pool Filtering Change (effect_placer.py)

```python
# Before:
def _build_effect_pool(effect_library, exclude=None):
    ...  # static list, no prop_type awareness

# After:
def _build_effect_pool(effect_library, exclude=None, prop_type=None):
    pool = []
    for name in _PROP_EFFECT_POOL:
        if name in (exclude or set()):
            continue
        edef = effect_library.effects.get(name)
        if edef is None:
            continue
        if prop_type:
            rating = edef.prop_suitability.get(prop_type, "possible")
            if rating == "not_recommended":
                continue
        pool.append(edef)
    # Relax if filtering emptied the pool
    if not pool:
        return _build_effect_pool(effect_library, exclude=exclude, prop_type=None)
    return pool
```

## How to Test

```bash
# Unit tests
python3 -m pytest tests/unit/test_rotation.py -v -k "diversity or prop_type"

# Generate and inspect
# Look for variety in tier-6 group assignments within a single section
python3 -c "
from src.generator.plan import build_plan
from src.generator.models import GenerationConfig
import json

config = GenerationConfig(audio_path='/home/node/xlights/mp3/04 - Carol Of The Bells.mp3')
plan = build_plan(config)
section = plan.sections[5]  # pick a mid-song section
tier6_effects = {
    name: placements[0].effect_name
    for name, placements in section.group_effects.items()
    if placements
}
print(json.dumps(tier6_effects, indent=2))
# Expect: different effect names across groups in the same tier
"
```

## Validation Checklist

- [ ] At least 2 distinct base effects present across tier-6 groups in any section with ≥3 groups
- [ ] Tree-typed groups receive tree-ideal effects (Spirals, Pinwheel, Fan, Ripple, Shockwave)
- [ ] No `not_recommended` effect appears on a group via the fallback pool path
- [ ] Single-group tiers still get their highest-scoring variant unchanged
- [ ] `pytest tests/unit/test_rotation.py` passes with no regressions
