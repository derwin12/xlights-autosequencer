# Proposal: pre-write plan variety validator

## Why

Following review of a comparable open-source xLights sequencer
(`Sacx83/sequencer`, 2026-08-02) and the minitree song-seeded-variety change
in this same session: our only checks for "does this generated sequence
show real variety" run **after** a full `.xsq` is written and rendered —
`xlight-evaluate microscope panel`, run manually, well after generation.
There is no check *inside* the generation pipeline itself that catches the
specific, recurring "one effect the whole song" failure class before it
ever reaches disk.

That failure class has recurred multiple times in this codebase's history
even with mined, idiomatic presets in place — not because the mining was
wrong, but because the *selection* mechanism collapsed to one branch for an
entire song:

- bug-197 (arch direction/size locked for a whole song)
- 2026-07-28 Shockwave bounce reroll (a single 65s occurrence rendered one
  static look because bounce was computed once per occurrence, not
  per-beat-block)
- The mirror-overlay aliasing bug (Lightning never reachable on 1999/Prince
  because `(seed // 2) % pool_len` aliased with the song's section stride)
- This session's minitree finding: the OLD fixed `(variation_seed // 2) % 2`
  parity is *identical* for every song, so while no single song shows 0%
  variety, every song shows the *same* variety pattern — a related but
  distinct symptom of the same underlying gap (no plan-level check that
  variety is actually present and actually differs per song).

Each of these was caught by a human noticing a real generated `.xsq` looked
wrong, then root-caused after the fact. A pre-write check would catch the
"one effect the whole song" shape of this bug class automatically, before a
user (or a future mining/recipe change) ships another instance of it.

## What Changes

### New module: `src/generator/plan_validator.py`

```python
@dataclass(frozen=True)
class PlanWarning:
    severity: str        # "info" | "warning"
    code: str             # e.g. "corpus_recipe_monotony"
    group_name: str
    message: str

def validate_plan(assignments: list[SectionAssignment],
                   groups: list[PowerGroup]) -> list[PlanWarning]:
    ...
```

V1 implements exactly one check, **`corpus_recipe_monotony`**: for every
tier-6/8 group matched by `recipe_for_group()` whose recipe has
`alt_effect_name` set (i.e., a family that is *supposed* to show two
effects), collect every placement across every `SectionAssignment.
group_effects[group_name]` in the whole song whose `effect_name` is either
`recipe.effect_name` or `recipe.alt_effect_name` (deliberately ignoring the
On-mask/secondary/overlay layers — this check is about the primary/alt
choice specifically, not every layer on the group). If the group has
**2 or more qualifying occurrences** (fewer than that can't show variety by
construction — not a bug) and **100% of those placements share one
effect_name**, emit a `warning`-severity `PlanWarning`.

Deliberately narrow scope for V1: only the exact failure shape already
proven to recur (one *specific, real* bug class, not a general "is this
plan varied enough" heuristic that would need its own tuning/validation
before it could be trusted). `motion_rotation`-based families (megatree,
matrix) are not checked in V1 — they already have their own occurrence
counter with reachability guarantees; extending this check to them is
noted as future work, not assumed safe to lump in here.

### Wiring: informational only, not blocking

`build_plan()` calls `validate_plan(assignments, groups)` immediately
before constructing the returned `SequencePlan`, and passes the result into
a new field:

```python
warnings: list[PlanWarning] = field(default_factory=list)
```

on `SequencePlan` (`src/generator/models.py`). Each warning is also logged
via the existing `logger` in `plan.py` (`logger.warning(...)`) so it shows
up in server/CLI logs without any caller needing to read `plan.warnings`
at all. **No caller is required to change** — this is purely additive: a
new field with an empty-list default, populated but not acted upon by any
existing consumer.

Explicitly **not** in this change: blocking generation, surfacing warnings
in the review UI, or failing the acceptance gate on a warning. Those are
real follow-ups (the informational plumbing here is what makes them
possible later), but bundling them now would turn a small, safe,
purely-additive change into one that could break existing UI/gate
consumers if the check ever has a false positive — better to let the check
run silently-logged for a while first and confirm it doesn't cry wolf
before anything depends on it.

## Alternatives considered

- **General "variety score" heuristic** (e.g. effect-diversity entropy
  across the whole plan) — rejected for V1: would need its own calibration
  against real generated output before it could be trusted not to flag
  legitimate low-variety songs (e.g. a 2-section song, or a family that
  genuinely only qualifies once). The narrow, proven-failure-shape check
  above needs no calibration — 100% one effect across 2+ occurrences is
  unambiguously the exact bug class already fixed multiple times.
- **Blocking generation on a warning** — rejected for V1, see "Wiring"
  above. Revisit once the check has run informationally for a while with
  no false positives.
- **Extend the check to `motion_rotation` families immediately** —
  deferred: those families' variety comes from a different mechanism
  (pool-cycling with its own reachability fix already shipped for
  matrix/megatree) and would need a different check shape (e.g. "did the
  occurrence count exceed the pool length without covering it"), not the
  same simple "100% one effect" test.
- **Run this as a separate post-hoc script** (like microscope) instead of
  inside `build_plan()` — rejected: the whole point is catching this
  *before* a `.xsq` reaches disk/review, at zero extra cost (the data is
  already fully assembled in `assignments`/`groups` at that point), rather
  than requiring a separate manual step a user has to remember to run.

## Files touched

| File | Change |
|---|---|
| `src/generator/plan_validator.py` | new — `PlanWarning`, `validate_plan()` |
| `src/generator/models.py` | modified — new `SequencePlan.warnings: list[PlanWarning]` field, default `[]` |
| `src/generator/plan.py` | modified — imports `plan_validator`, calls `validate_plan()` before constructing `SequencePlan`, logs each warning |
| `tests/unit/test_generator/test_plan_validator.py` | new — monotony detected at 2+ occurrences, not flagged at 1 occurrence, not flagged when both effects appear, families without `alt_effect_name` never checked, `motion_rotation` families never checked (v1 scope) |
| `tests/unit/test_generator/test_plan.py` | modified — assert `build_plan()`'s returned plan has a `warnings` attribute (empty in the existing fixtures, which don't hit the monotony shape) |
| `docs/segment-classification-changelog.md` | not touched — no segment/classification change |

## Regression surface

- **`SequencePlan`** — new field, default `[]`. Grep: constructed only in
  `plan.py` (the single `return SequencePlan(...)` site) and in test
  fixtures across `tests/unit/test_generator/`, `tests/evaluation/`,
  `tests/review/` — all use keyword args or don't set `warnings` at all, so
  every existing constructor call keeps working unchanged.
- **`build_plan()`** — single return point (verified: only one
  `return SequencePlan(...)` in the whole function). No signature change,
  no new required parameter — safe for all 48 files that reference
  `build_plan`/`write_xsq` across the repo (most are docs/specs, not code;
  actual callers are `generator_runner.py`, `review/api/v1/export.py`,
  `preview.py`).
- **No existing test should change behavior** — the new field defaults to
  `[]` and nothing reads it yet outside the new test file.

## Historical echoes (`.wolf/buglog.json`, `.wolf/cerebrum.md` Do-Not-Repeat)

- **bug-197** (arch direction/size locked for a whole song) — the exact
  failure shape this check targets.
- **2026-07-28 Shockwave bounce reroll** — same failure shape, different
  root cause (once-per-occurrence computation instead of per-beat-block).
  This validator wouldn't have caught the WITHIN-occurrence freeze
  directly (it checks across occurrences), but would catch the simpler
  across-song version of the same class.
- **Mirror-overlay aliasing** (Lightning never reachable on 1999/Prince) —
  same root problem family (a selection mechanism silently collapsing to
  one branch), different mechanism (rotation-pool aliasing vs. fixed
  parity). Not directly covered by this check (motion_rotation families are
  out of scope for V1), noted as the natural next extension.
- **This session's minitree song-seeded-variety change** — the check
  described here is a natural complement: that change fixed cross-song
  sameness for one family; this validator catches within-song monotony
  (the older, more severe failure) across any family with `alt_effect_name`
  set, as a safety net for future recipe changes.
- No matching entries found for `plan_validator` or pre-write validation
  gates beyond the above; stated explicitly per the gate.

## Validation

1. Unit: new `test_plan_validator.py` per the files-touched table above;
   full `pytest tests/unit/test_generator -v`.
2. Manually construct a plan with a deliberately-monotone group (via the
   existing `_place()`-style test helpers) and confirm `validate_plan`
   flags it, then confirm the pre-minitree-fix arch/cane/etc. recipes do
   NOT spuriously flag (they already showed genuine two-effect variety
   within a song via the old parity mechanism, so this is a real
   regression check, not just a happy-path test).
3. Run a real generation (`xlight-evaluate gate --quick` or a manual
   `generate` call) and confirm `plan.warnings` populates as expected and
   the log line appears, with zero warnings on a healthy song.
