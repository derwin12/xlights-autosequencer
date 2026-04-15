# Implementation Plan: Pipeline Decision-Ordering Refactor

**Branch**: `048-pipeline-decision-ordering` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/048-pipeline-decision-ordering/spec.md`

## Summary

Today `build_plan()` passes raw config flags into `place_effects()`, which then re-derives
per-section creative decisions (active tiers, palette trim, duration band, accent gates)
inside its per-tier / per-layer loops. That ordering is illegible to the Brief UI (spec 047)
and impossible to render in isolation for the Preview UI (spec 049).

This refactor pulls those four decisions upstream. `build_plan()` grows a **decision-precompute
pass** between theme selection (step 3) and placement (step 4) that populates new fields on
each `SectionAssignment`: `active_tiers`, `palette_target` (per-tier mapping), `duration_target`,
`accent_policy`, `working_set`, `section_index`. `place_effects()` shrinks from an 11-kwarg
signature to six, reads every decision off the assignment, and never recomputes. The accent
helpers (`_place_drum_accents`, `_place_impact_accent`) read `assignment.accent_policy` and
skip their current inline energy/role/duration gates. `regenerate_sections()` is migrated
to the same assignment-driven path, deleting its duplicated flag-handling block.

Zero user-visible output change. Behavioural equivalence is enforced by a **canonical XML
CI gate** (`xml.etree.ElementTree.canonicalize`, C14N 2.0) against golden `.xsq` fixtures
for ≥3 config permutations.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: No new dependencies — all existing generator pipeline. Uses
`xml.etree.ElementTree.canonicalize()` (Python 3.8+ stdlib, C14N 2.0) for the equivalence gate.
**Storage**: N/A — field additions are in-memory on `SectionAssignment`. `GenerationConfig`
wire format unchanged.
**Testing**: pytest. Golden `.xsq` fixtures stored under `tests/fixtures/xsq/048_golden/`.
**Target Platform**: Linux devcontainer / macOS host
**Project Type**: CLI pipeline stage (generator) — surgical backend refactor.
**Performance Goals**: Zero measurable overhead. The precompute pass runs ≤ O(sections × tiers)
scalar work — trivial next to placement.
**Constraints**: Generated `.xsq` MUST be canonically equal (attribute order sorted,
insignificant whitespace collapsed) before vs after refactor for every fixture permutation.
`GenerationConfig` keeps every existing flag (they become serialised defaults for the Brief).
**Scale/Scope**: Edits concentrated in `src/generator/models.py`, `src/generator/plan.py`,
`src/generator/effect_placer.py`. Two new unit test files plus one integration test.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | No change to analysis pipeline. Decisions still derived from `hierarchy` + `section_energy`; only the *call site* of those derivations moves upstream. Seed computation (section_index, group_index, tier) preserved verbatim (FR-033). |
| II. xLights Compatibility | PASS | `.xsq` output is the acceptance test — canonical XML equality is the merge gate. Zero schema or serializer change. |
| III. Modular Pipeline | PASS | Strengthens modularity. The pipeline gains a clean boundary: producers write decisions to `SectionAssignment`; `place_effects` consumes a read-only recipe. No new stage boundaries; existing ones sharpen. |
| IV. Test-First Development | PASS | New tests land before refactor: golden-fixture capture on pre-refactor `main`, signature-guard test, field-coverage test, isolation test. All three must be red against a naive refactor attempt. |
| V. Simplicity First | PASS | Adds six fields to an existing dataclass and one tiny dataclass (`AccentPolicy`). No new abstractions, no new helpers, no config knobs. Reduces surface area of `place_effects()` from 11 kwargs to 6. |

No violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/048-pipeline-decision-ordering/
├── plan.md              # This file
├── research.md          # Phase 0 output — call-graph audit, canonicalisation tooling decision
├── data-model.md        # Phase 1 output — extended SectionAssignment, AccentPolicy shape
├── quickstart.md        # Phase 1 output — field-coverage & isolation walkthroughs
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (affected files)

```text
src/
└── generator/
    ├── models.py            # +AccentPolicy dataclass; +6 fields on SectionAssignment
    ├── plan.py              # build_plan() grows decision-precompute pass; regenerate_sections() migrated
    └── effect_placer.py     # place_effects() signature 11→6; inline restrain/_compute_active_tiers/compute_duration_target calls removed; accent helpers read policy

tests/
├── unit/
│   ├── test_section_assignment.py      # NEW — field population + per-section overrides + isolation
│   └── test_place_effects_signature.py # NEW — grep/inspect.signature guard for removed kwargs
└── integration/
    └── test_generator_equivalence.py   # NEW — canonical XML diff across ≥3 fixture permutations

tests/fixtures/xsq/048_golden/          # NEW — captured pre-refactor .xsq goldens (committed)
```

No new modules. No new directories outside `tests/fixtures/xsq/048_golden/`.

**Structure Decision**: Surgical in-place refactor. All changes live in three existing
generator files plus three new test files and one golden-fixture directory.

## Implementation Approach

### Phase A — Extend the data model (`src/generator/models.py`)

Add `AccentPolicy`:

```python
@dataclass
class AccentPolicy:
    drum_hits: bool  # spec 042A gate outcome
    impact: bool     # spec 042B gate outcome
```

Extend `SectionAssignment` (existing fields `section`, `theme`, `group_effects`,
`variation_seed` preserved; added fields all have defaults so older callers in tests
continue to construct instances unchanged until migrated):

```python
@dataclass
class SectionAssignment:
    section: SectionEnergy
    theme: Theme
    group_effects: dict[str, list[EffectPlacement]] = field(default_factory=dict)
    variation_seed: int = 0
    # New fields (populated by build_plan before place_effects runs)
    active_tiers: frozenset[int] = field(default_factory=frozenset)
    palette_target: dict[int, int] | None = None   # tier -> target color count; None when restraint off
    duration_target: DurationTarget | None = None  # None when duration_scaling off
    accent_policy: AccentPolicy = field(default_factory=lambda: AccentPolicy(False, False))
    working_set: WorkingSet | None = None          # per-assignment pointer into working_sets[theme_name]
    section_index: int = 0
```

`GenerationConfig` is untouched on the wire (FR-030).

### Phase B — Decision-precompute pass (`src/generator/plan.py`)

Between today's step 3 (theme selection + overrides) and step 4 (place_effects loop),
insert a new loop — one iteration per assignment — that populates the new fields. It
reuses the existing helpers from `effect_placer.py` (FR-021 explicitly keeps them as
internal producers, just called from upstream):

```python
from src.generator.effect_placer import (
    _compute_active_tiers, restrain_palette, compute_duration_target,
    _DRUM_HIT_ENERGY_GATE, _IMPACT_ENERGY_GATE, _IMPACT_QUALIFYING_ROLES,
    _IMPACT_MIN_DURATION_MS,
)

for idx, assignment in enumerate(assignments):
    section = assignment.section
    assignment.section_index = idx

    # Tiers
    if config.tier_selection:
        assignment.active_tiers = _compute_active_tiers(section, idx, hierarchy)
    else:
        assignment.active_tiers = frozenset(range(1, 9))

    # Palette target — per-tier mapping, one entry per active tier.
    # Call `restrain_palette` with a dummy 6-colour palette to read off the cap
    # at (energy, tier); store just the target integer.  Rationale in data-model.md.
    if config.palette_restraint:
        pt: dict[int, int] = {}
        dummy = ["#000000"] * 6
        for tier in assignment.active_tiers:
            pt[tier] = len(restrain_palette(dummy, section.energy_score, tier))
        assignment.palette_target = pt
    else:
        assignment.palette_target = None

    # Duration target
    assignment.duration_target = (
        compute_duration_target(hierarchy.estimated_bpm, section.energy_score)
        if config.duration_scaling else None
    )

    # Accent policy — apply today's gates once, here.
    drum_ok = (
        config.beat_accent_effects
        and section.energy_score >= 60
        and hierarchy.events.get("drums") is not None
    )
    role = (section.label or "").lower()
    impact_ok = (
        config.beat_accent_effects
        and section.energy_score > _IMPACT_ENERGY_GATE
        and (section.end_ms - section.start_ms) >= _IMPACT_MIN_DURATION_MS
        and (not role or role in _IMPACT_QUALIFYING_ROLES)
    )
    assignment.accent_policy = AccentPolicy(drum_hits=drum_ok, impact=impact_ok)

    # Working set already derived per theme above; attach the per-assignment reference.
    assignment.working_set = (
        working_sets.get(assignment.theme.name) if config.focused_vocabulary else None
    )
```

The per-hit energy gate (`_DRUM_HIT_ENERGY_GATE`) remains inside `_place_drum_accents`
— it is a *per-hit* decision, not a *per-section* decision, so it does not belong on
`accent_policy` (spec's FR-013 distinguishes section-level gates from per-hit sampling).

### Phase C — Reduce `place_effects()` (`src/generator/effect_placer.py`)

**Before** (lines 477-491, 11 kwargs):

```python
def place_effects(
    assignment, groups, effect_library, hierarchy,
    tiers=None, variant_library=None, rotation_plan=None,
    section_index=0, working_set=None, focused_vocabulary=False,
    palette_restraint=False, duration_scaling=False, bpm=120.0,
) -> dict[str, list[EffectPlacement]]: ...
```

**After** (6 params):

```python
def place_effects(
    assignment: SectionAssignment,
    groups: list[PowerGroup],
    effect_library: EffectLibrary,
    hierarchy: HierarchyResult,
    variant_library=None,
    rotation_plan: RotationPlan | None = None,
) -> dict[str, list[EffectPlacement]]: ...
```

Inside the body, replace the derivations that today run at lines 557–560, 601–602, and
the `focused_vocabulary`/`working_set`/`bpm`/`section_index` reads throughout:

- `effective_tiers = assignment.active_tiers` (was: `_compute_active_tiers(...)` when `tiers` arg was None)
- `section_index = assignment.section_index` (was: function parameter)
- `working_set = assignment.working_set`; `focused_vocabulary = working_set is not None`
- `bpm = hierarchy.estimated_bpm` (read directly — the only previous consumer of the kwarg)
- Palette trim: replace `if palette_restraint: tier_palette = restrain_palette(...)` at line
  601–602 with `if assignment.palette_target is not None: tier_palette = tier_palette[:assignment.palette_target[tier]] if …`.
  The simplest implementation preserves today's colour-spread logic by calling a small inlined
  helper that reads the target count directly from `assignment.palette_target[tier]` — no call
  to `restrain_palette` from inside placement.
- Duration: `duration_scaling = assignment.duration_target is not None`, passed through to
  `_place_effect_on_group` unchanged. When `None`, the same fallback path runs.

`_compute_active_tiers()`, `restrain_palette()`, and `compute_duration_target()` stay as
module-level functions — they are now called from `plan.py` only. `place_effects()` no longer
imports or calls them.

### Phase D — Accent helpers read policy (`src/generator/effect_placer.py`)

`_place_drum_accents()` (line 1662): add a guard at the top:

```python
if not assignment.accent_policy.drum_hits:
    return {}
```

Remove the implicit section-level gate that today lives in `plan.py` line 199
(`if config.beat_accent_effects:`); that flag is now *only* read during the precompute
pass. The per-hit energy gate (`_DRUM_HIT_ENERGY_GATE`) at line 1776 stays — it is
per-hit, not per-section.

`_place_impact_accent()` (line 1807): replace lines 1820–1828 (the energy/duration/role
gate trio) with:

```python
if not assignment.accent_policy.impact:
    return {}
```

FR-022 requires the removed gates to not be re-evaluated — the policy field carries the
outcome, unconditionally.

### Phase E — Migrate `regenerate_sections()` (`src/generator/plan.py` lines 365–490)

Today's `regenerate_sections()` has its own divergent `place_effects()` call at lines
442–452 with a subset of flags (`tiers_arg`, `palette_restraint=...`, `duration_scaling=...`,
`bpm=...`). Replace with:

1. Run the same Phase B precompute loop over `assignments`.
2. Call `place_effects(assignment, groups, effect_library, hierarchy, variant_library, rotation_plan)` — same signature as `build_plan`.
3. Accent pass is already absent here (regenerate is targeted; accent regeneration was never implemented) — leave it absent.

Net: the duplicated flag-handling block at lines 437–452 deletes; a single loop replaces it.

### Phase F — Regression gate (CI): canonical XML equality

**Tooling decision**: `xml.etree.ElementTree.canonicalize(xml_data=..., strip_text=True)`
(stdlib, C14N 2.0). Chosen because: (a) already a direct dep (xsq_writer uses ET), (b) no
new install, (c) C14N 2.0 guarantees sorted attribute order and collapsed insignificant
whitespace exactly as FR-031 requires. `lxml.etree.c14n` rejected — no lxml in the
project, adding it for a CI gate is gratuitous. A hand-rolled sorter was rejected — C14N
is a standard, hand-rolling would invent edge cases.

**Test location**: `tests/integration/test_generator_equivalence.py`. For each fixture
permutation, generate an `.xsq`, canonicalise it with `ET.canonicalize`, and string-compare
against the pre-captured golden under `tests/fixtures/xsq/048_golden/`. Any diff fails
the test. No per-fixture whitelist.

**Fixture permutations** (≥3, per SC-001):

1. `default` — all flags at documented defaults.
2. `no_focus` — `focused_vocabulary=False`.
3. `no_tier_selection` — `tier_selection=False` (the all-tiers-active path).
4. `no_accents` — `beat_accent_effects=False`.

Four permutations ≥ spec's floor of three. Fixture audio is one of the existing
`10s_*.wav` files under `tests/fixtures/`; layout is `tests/fixtures/generate/mock_layout.xml`.

### Phase G — Unit test guards

- `tests/unit/test_place_effects_signature.py` — asserts via `inspect.signature` that
  `place_effects` has exactly the six parameters listed in FR-020 and none of the
  forbidden kwargs (`tiers`, `section_index`, `working_set`, `focused_vocabulary`,
  `palette_restraint`, `duration_scaling`, `bpm`). Fails if any are reintroduced.
- `tests/unit/test_section_assignment.py` — covers User Story 1 (every Brief-visible
  decision is a field read), User Story 4 (isolation: detach `plan.sections[i]`, call
  `place_effects` alone, assert equality with original), User Story 5 (override
  `palette_target[5] = 2`, re-place, assert trimmed palette).

## Sequencing & Compatibility

- **Can ship parallel to spec 047 (Brief UI)**: 047's first cut scrapes values from
  `group_effects`. Once 048 lands, 047 swaps to direct reads off `SectionAssignment`
  — no blocking dependency.
- **Unblocks spec 049 (Preview)**: 049 benefits from assignment-driven isolation
  (User Story 4) but can live without it via a post-hoc section filter.
- **No migration of on-disk artefacts**: plan-JSON is regenerated each run; `.xsq`
  outputs are canonically equal; no stored data needs migrating.

## Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| Canonical-XML diff flags a real regression buried in floating-point or seed drift | Capture goldens on exact pre-refactor commit of `main`. Every seed tuple preserved verbatim (FR-033). |
| Test code references old `place_effects` kwargs | Sweep in the refactor commit — SC-006 allows signature-driven updates, nothing else. |
| `restrain_palette`'s spread-index algorithm drifts when called from plan instead of placer | Plan calls it with a dummy 6-colour palette purely to read the *target count*. The actual trim still happens inside placement using that count on the real palette with the identical spread-index math. See data-model.md. |
| Accent helper tests mock `config.beat_accent_effects` | Rewrite to mock `assignment.accent_policy` instead; this is the point of the refactor. Covered in SC-006. |
