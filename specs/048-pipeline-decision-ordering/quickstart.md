# Quickstart: Verifying the 048 Refactor

Three walkthroughs, each exercising one acceptance guarantee from spec 048. Runs
against a fixture song — no real analysis needed.

## Setup

```bash
cd /workspace
pytest tests/integration/test_generator_equivalence.py -x  # precondition: gate is green
```

Fixture song: `tests/fixtures/beat_120bpm_10s.wav`
Fixture layout: `tests/fixtures/generate/mock_layout.xml`
Pre-captured golden `.xsq` outputs: `tests/fixtures/xsq/048_golden/{default,no_focus,no_tier_selection,no_accents}.xsq`

## Walkthrough 1 — Every Brief-visible decision is a field read

Goal: confirm User Story 1. After `build_plan()` runs, the assignment carries the
complete decision record; nothing has to be re-derived.

```python
from pathlib import Path
import json

from src.analyzer.orchestrator import run_orchestrator
from src.generator.models import GenerationConfig
from src.generator.plan import build_plan
from src.grouper.layout import parse_layout
from src.grouper.classifier import classify_props, normalize_coords
from src.grouper.grouper import generate_groups
from src.effects.library import load_effect_library
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library

config = GenerationConfig(
    audio_path=Path("tests/fixtures/beat_120bpm_10s.wav"),
    layout_path=Path("tests/fixtures/generate/mock_layout.xml"),
)
hierarchy = run_orchestrator(str(config.audio_path))
layout = parse_layout(config.layout_path)
normalize_coords(layout.props)
classify_props(layout.props)
groups = generate_groups(layout.props)
effect_lib = load_effect_library()
variant_lib = load_variant_library(effect_library=effect_lib)
theme_lib = load_theme_library(effect_library=effect_lib, variant_library=variant_lib)

plan = build_plan(config, hierarchy, layout.props, groups, effect_lib, theme_lib)

a = plan.sections[0]
brief_view = {
    "section_index": a.section_index,
    "section_label": a.section.label,
    "energy_score": a.section.energy_score,
    "theme": a.theme.name,
    "active_tiers": sorted(a.active_tiers),
    "palette_target": a.palette_target,
    "duration_target": (
        None if a.duration_target is None
        else {"min_ms": a.duration_target.min_ms,
              "target_ms": a.duration_target.target_ms,
              "max_ms": a.duration_target.max_ms}
    ),
    "accent_policy": {
        "drum_hits": a.accent_policy.drum_hits,
        "impact": a.accent_policy.impact,
    },
}
print(json.dumps(brief_view, indent=2))
```

**Expected**: every value above is a direct field read on `a`. No `config.*` or
`hierarchy.*` lookup appears on the right-hand side of any assignment. This is the
contract spec 047's Brief UI will consume.

## Walkthrough 2 — Section rendered in isolation (User Story 4)

Goal: confirm that detaching a single assignment reproduces its `group_effects` without
any whole-song context.

```python
from src.generator.effect_placer import place_effects

a = plan.sections[2]                   # any non-trivial section
original = dict(a.group_effects)       # snapshot
a.group_effects = {}                   # clear

redone = place_effects(
    a, groups, effect_lib, hierarchy,
    variant_library=variant_lib,
    rotation_plan=plan.rotation_plan,
)
assert redone == original, "isolation render diverged — decision is not fully on the assignment"
```

**Expected**: assertion passes. The new six-parameter signature means every per-section
decision rides on `a` — no `section_index=`, no `focused_vocabulary=`, no `bpm=` needed.

## Walkthrough 3 — Per-section override (User Story 5)

Goal: confirm that mutating the assignment before placement flows through without new
plumbing.

```python
# Before: whatever palette_target build_plan populated
a = plan.sections[1]
print("was:", a.palette_target)

# Force 2 colours on every active tier in this section
a.palette_target = {t: 2 for t in a.active_tiers}
a.group_effects = {}
a.group_effects = place_effects(
    a, groups, effect_lib, hierarchy,
    variant_library=variant_lib, rotation_plan=plan.rotation_plan,
)

# Every placement in this section now has at most 2 colours
for _, placements in a.group_effects.items():
    for p in placements:
        assert len(p.color_palette) <= 2, (p.model_or_group, p.color_palette)
```

**Expected**: assertion passes for every placement. The Brief UI (spec 047) will mutate
`palette_target`, `duration_target`, `active_tiers`, or `accent_policy` through exactly
this path.

## Canonical-XML gate (CI check)

```bash
pytest tests/integration/test_generator_equivalence.py -v
```

What it does:

1. Regenerates `.xsq` for each of four fixture permutations
   (`default`, `no_focus`, `no_tier_selection`, `no_accents`).
2. Runs each through `xml.etree.ElementTree.canonicalize(strip_text=True)` (C14N 2.0).
3. Compares byte-for-byte against the canonicalised golden under
   `tests/fixtures/xsq/048_golden/*.xsq`.

Any surviving diff is a merge-blocking regression. No whitelist.

**Regenerating goldens** (only after an intentional behaviour change — NOT during this
refactor):

```bash
pytest tests/integration/test_generator_equivalence.py::capture_goldens \
  --capture-only
```

The `capture_only` marker is skipped by default CI; it writes goldens from whatever the
current code produces. During the 048 refactor itself, goldens are captured exactly
once, on the pre-refactor `main` commit, and are read-only thereafter.

## Signature guard

```bash
pytest tests/unit/test_place_effects_signature.py -v
```

Asserts via `inspect.signature(place_effects)` that the parameter list is exactly:

```
assignment, groups, effect_library, hierarchy, variant_library, rotation_plan
```

— and rejects any reintroduction of `tiers`, `section_index`, `working_set`,
`focused_vocabulary`, `palette_restraint`, `duration_scaling`, or `bpm`. Fails closed
if a future change adds a legacy kwarg by accident.
