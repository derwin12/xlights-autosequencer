# Proposal: matrix motion variety from mined vendor presets

## Why

User report (2026-07-18, "1999" Prince, `06_PROP_Matrix`): the sustained
Spirals layer repeats one identical look for the whole song — 96 placements,
all `Count=1, Rotation=30, Thickness=30, Movement=1, 3D`, the only variation
being the alternating Flip Horizontal transform added in bug-256. This is the
**second** user complaint about the same layer (bug-256 was the first; the
flip transform was a partial fix).

Re-mining the vendor reference packages (the 14 unique sequences in the
reference show folder — vendor name deliberately not recorded, per the
cerebrum privacy rule) shows the pros get their variety from **many distinct
mined parameter combinations per effect**, which our recipe collapsed into
single modal presets:

| Effect    | Vendor placements | Vendor distinct settings | Ours (1999.xsq) |
|-----------|------------------:|-------------------------:|----------------:|
| Shockwave | 3,742             | 15                       | 3               |
| Pinwheel  | 1,425             | 27                       | 3               |
| Ripple    | 1,298             | 7                        | 3               |
| Lightning | 1,243             | 6                        | **0 — never fired** |
| Spirals   | 873               | 52                       | 4 (one preset ± flip) |

Individual vendor songs use 5–25 distinct Spirals looks each. The single most
common vendor Spirals look on matrices is a **thin twin-spiral pair**
(`Count=2, Thickness=7, Rotation=+20, Movement=0.7` alternating with its
mirror `-20/-0.7`) — not our thick single 3D spiral (which is real, but just
one of many).

**Verified bug found along the way**: Lightning is in the matrix recipe's
`motion_rotation` pool (index 2 of 4) but never fired in 1999.xsq. Root
cause: `_place_corpus_recipe` picks `idx = (variation_seed // 2) % 4`, and
`variation_seed` is the **global section index** — when a song's qualifying
sections land at a regular stride, the index sequence aliases and skips
slots. Observed in the actual 1999 output: rotation walked
`0, 1, 0, 3, 0, 1, 0, 3` — slot 2 (Lightning) is unreachable for this song's
structure. Same failure family as bug-182 (seed parity locked the alternate
in) and bug-188 (Lightning silently never firing).

## What Changes

Four parts, all in the generator (shared module — full design gate):

### 1. Fix rotation aliasing: occurrence counter instead of seed arithmetic

`place_effects` keeps a per-group count of successful corpus-recipe
placements (next to the existing `corpus_recipe_done` per-section set) and
passes it to `_place_corpus_recipe` as `occurrence_index`. The
`motion_rotation` branch uses `occurrence_index % len(pool)` so every
qualifying occurrence advances the pool by exactly one — every slot is
reachable regardless of song structure. The two-effect primary/alt parity
(`(seed // 2) % 2`, bug-182's fix) is **left untouched** for families
without a rotation pool.

### 2. Mined preset pools in `motion_rotation` (no type change)

`motion_rotation` already accepts repeated effect names with different
parameters — the type stays `tuple[tuple[str, params], ...]`. The matrix
recipe's pool grows from 4 entries (one preset each) to ~7 entries
(2–3 mined presets per effect), interleaved so consecutive occurrences
change effect, not just preset:

- Shockwave: burst End_Radius=30/Width=20 (existing); full-screen
  End_Radius=100/Width=62; mid End_Radius=50/Width=30 (Scale=0)
- Pinwheel: 2-arm/speed-15/no-twist 3D-Inverted (existing);
  8-arm/speed-10/Twist=20 3D
- Ripple: Implode/Thickness=12/Cycles=0.2 (existing);
  Explode/Thickness=3/Cycles=1
- Lightning: **removed from the rotation** (goes to part 4)

Every value comes from the top vendor combos mined 2026-07-18 — full
combinations only, never independently re-mixed per parameter (independent
sampling could produce combos no vendor ever shipped, e.g. mismatched
thickness/count pairs).

### 3. New `secondary_rotation` pool for the sustained layer

New field on `PropFamilyRecipe`:

```python
secondary_rotation: tuple[tuple[tuple[str, str], ...], ...] = ()
```

— a pool of parameter-override tuples for `secondary_effect_name`, selected
per qualifying occurrence (same counter as part 1, `% len`). Empty `()` →
existing single-preset behavior, so all other recipes are untouched. The
existing per-placement Flip Horizontal alternation (bug-254/256) keeps
running within whichever preset is active.

Matrix pool (5 mined Spirals presets):

1. Thin twin: `Count=2, Rotation=20, Thickness=7, Movement=0.7, 3D=0`
   (the #1 vendor look, 152 placements incl. mirror)
2. Thick 3D single: `Count=1, Rotation=30, Thickness=35, Movement=1, 3D=1`
   (current preset, corrected Thickness 30→35 to match the mined mode)
3. Fast tight flat: `Count=1, Rotation=-100, Thickness=20, Movement=1, 3D=0`
4. Reverse 3D: `Count=1, Rotation=-32, Thickness=33, Movement=-2, 3D=1`
5. Multi-spiral: `Count=4, Rotation=-100, Thickness=20, Movement=1, 3D=0`

### 4. Lightning moves to the crash-accent pass

`_place_crash_accents` (currently: Shockwave on `01_BASE_All_FADES` at each
`hierarchy.crash_accents` mark, with the Moving Head punch placed at the same
marks from `plan.py`) additionally places a Lightning burst on each tier-6
matrix group (`match_tokens ("matrix",)`, `exclude ("lyric",)`) using the
same window (`_CRASH_LEAD_MS` build + `_CRASH_EFFECT_DURATION_MS`), same
vocal-word and fade exclusions. Preset: the unanimous vendor flicker
(`Direction=Up, WIDTH=1, Number_Bolts=10, Number_Segments=5`), alternating
occurrences add `B_CHOICE_BufferTransform="Rotate CC 90"` (the second-most
common vendor Lightning variant, 366 placements). Layer: a dedicated layer
**above** the recipe layers — per bug-248, xLights renders the FIRST
`<EffectLayer>` on top, so the accent uses a layer index below the group's
existing minimum.

This matches vendor behavior better than keeping Lightning in the rotation:
vendors use matrix Lightning in only 2 of 14 songs, as a burst accent — not
as a section-filling texture — and it pairs naturally with the existing
whole-house + Moving Head crash choreography.

## Alternatives considered

- **Per-parameter jitter (independently sample each slider from its mined
  value distribution)** — rejected: can generate combinations no vendor ever
  used (e.g. `Thickness=7` with `Count=1` never appears); full mined combos
  are guaranteed-good looks.
- **Keep seed-based rotation but multiply by a stride coprime to pool
  length** — rejected: still aliasable for other pool lengths/section
  spacings, and harder to reason about than a plain occurrence counter.
- **Rotate the secondary effect itself (Plasma/Fire/etc.), not just Spirals
  presets** — deferred: the mined sustained-under-layer idiom on matrices is
  overwhelmingly Spirals; Plasma/Warp/Shader appear in vendor matrices via
  different (often shader-based) stacks we don't replicate yet. Revisit if
  the Spirals pool still reads as repetitive.
- **Leave Lightning in the rotation and fix only the aliasing** — rejected:
  even fixed, a per-beat white Lightning texture across a whole chorus is
  not what vendors do (2/14 songs, accent-style usage); the crash pass
  matches the mined role and the user's explicit suggestion.

## Files touched

| File | Change |
|---|---|
| `src/generator/corpus_recipes.py` | modified — new `secondary_rotation` field; matrix recipe: expanded `motion_rotation` (7 mined entries, Lightning removed), `secondary_rotation` pool (5 mined Spirals presets); new module-level preset constants |
| `src/generator/effect_placer.py` | modified — occurrence counter in `place_effects` (4 call sites), `_place_corpus_recipe` gains `occurrence_index` param + `secondary_rotation` selection; `_place_crash_accents` gains matrix Lightning placement |
| `src/generator/plan.py` | unchanged (crash pass already routes through `_place_crash_accents`; verify only) |
| `tests/unit/test_generator/test_corpus_recipes.py` | modified — update pinned matrix preset assertions; new tests: rotation reaches every pool slot; secondary pool cycles per occurrence; empty `secondary_rotation` keeps old behavior |
| `tests/unit/test_generator/test_crash_accents_placement.py` | modified — new tests: matrix Lightning at crash marks, rotated variant on alternate occurrences, layer sits above recipe layers, exclusion rules honored |
| `docs/segment-classification-changelog.md` | not touched — no segment/classification change |

## Regression surface

- **`PropFamilyRecipe`** — new field with default `()`; constructed only in
  `src/generator/corpus_recipes.py` (grep: no other constructors in `src/`
  or `tests/`). No caller breaks.
- **`_place_corpus_recipe`** — private; called from exactly 4 sites in
  `effect_placer.py` (lines ~872, ~985, ~1055, ~1176), all updated together.
  Grep across `tests/`: **no test calls it directly** — tests go through
  `place_effects`, whose public signature is unchanged
  (`test_place_effects_signature.py` guards this).
- **`_place_crash_accents`** — called only from `plan.py:339`; signature
  gains no required params (matrix groups are derivable from the `groups`
  arg it already receives). `tests/unit/test_generator/test_crash_accents_placement.py`
  (10 references) exercises current behavior — existing assertions must
  still pass (additive change: new placements on matrix groups only).
- **Rotation-order change (part 1)** — any test asserting *which* effect a
  specific `variation_seed` produces via `motion_rotation` will shift.
  Grep of `test_corpus_recipes.py`: matrix tests assert effect *sets* and
  preset *values*, not seed→effect mapping, except tests that pin
  `_SPIRALS_MATRIX` values (lines ~719–739, ~1074) — updated as part of
  part 3. Non-rotation families (all others) keep bit-identical behavior.
- **Golden/microscope baselines** — generated matrix output changes by
  design. `xlight-evaluate microscope panel` + the matrix-heavy panel
  (`panel_manifest_matrix.json`) must be re-run; baselines re-promoted only
  after `microscope sensitivity` passes (per CLAUDE.md promotion rule).

## Historical echoes (`.wolf/buglog.json`, `.wolf/cerebrum.md` Do-Not-Repeat)

- **bug-182** — seed parity locked the corpus alternate in for whole songs;
  fixed with `seed // 2`. Part 1 is the same aliasing family one level up;
  the occurrence counter removes the arithmetic entirely for rotation pools.
  The `seed // 2` primary/alt path is deliberately left untouched.
- **bug-188** — Lightning silently never fired (missing from catalog).
  Lightning is now confirmed present in `builtin_effects.json`; this time it
  never fired for a *different* silent reason (aliasing). Lesson applied:
  the new rotation test asserts every pool slot is reachable.
- **bug-197** — "single repeated effect for the whole song" on arches; fix
  added per-occurrence direction/size rotation. Same complaint shape here;
  this design extends the same occurrence-rotation philosophy to preset
  pools.
- **bug-254 / bug-256** — the flip-transform alternation on Spirals
  (primary, then secondary layer). Kept as-is; preset pools compose with it.
- **bug-248 (cerebrum)** — xLights renders the FIRST `EffectLayer` on top;
  the crash Lightning layer must use an index *below* existing layers to
  render above them. Applied in part 4.
- **bug-159 (docstring in `_place_corpus_recipe`)** — return `None` (never
  `[]`) when placement is impossible so callers fall back. Preserved.
- **Cerebrum privacy rule (2026-07-18, tightened)** — no vendor name/prefix
  in this change dir, code comments, commit messages, or tests. This
  proposal says "vendor packages" only.
- **Cerebrum (2026-07-18)** — never emit `T_CHECKBOX_Canvas`; none of the
  mined presets here include it (verified against the mined combos).
- No matching entries found for `secondary_rotation` or occurrence-counter
  regressions beyond the above; stated explicitly per the gate.

## Validation

1. Unit: new + updated tests above; full `pytest tests/unit/test_generator -v`.
2. Regenerate 1999 (Prince) and verify in the .xsq: ≥4 distinct Spirals
   setting strings from the pool, all 7 motion_rotation slots reachable
   across a synthetic 8+-chorus fixture, Lightning present iff
   `crash_accents` marks exist.
3. `xlight-evaluate microscope panel` (default + matrix manifest) against
   current baselines; expect variety metrics to move — review diff, re-run
   sensitivity, re-promote.
