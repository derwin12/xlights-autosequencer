# Proposal: tier-layering policy

## Why

Investigation traced from a real-render review of the Cher fixture
(`Cher-DJ_Play_a_Christmas_Song`, 2026-05-06) showed that of the eight
tiers the generator synthesises into the layout XML, **only tiers 5–8
ever receive effect placements**. Tiers 1 BASE, 2 GEO, 3 TYPE, and 4
BEAT are written to disk and then ignored.

The gate is two small hardcoded policies in shared modules:

1. [`src/generator/rotation.py:107`](../../../src/generator/rotation.py#L107)
   maps only tiers 5–8 to a `tier_affinity` value
   (`{5: "mid", 6: "mid", 7: "foreground", 8: "hero"}`). When tiers
   1–4 are scored the affinity context is `None`, so the variant
   scorer cannot bias toward background-tagged variants.

2. [`src/generator/effect_placer.py:1980`](../../../src/generator/effect_placer.py#L1980)
   `_compute_active_tiers` returns at most one of `{2, 4, 6}` plus
   `{8}` per section, never including 1, 3, 5, or 7. The function's
   docstring justifies this with a "silent overwrite" claim — that
   activating multiple partition tiers makes the higher one clobber
   the lower on shared props. Empirical check (Rob, 2026-05-06) found
   this isn't true: xLights composes layers correctly. The actual past
   incident was tier 1 BASE running bold effects (e.g. `Color Wash`)
   that *visually* overwhelmed the upper tiers — the symptom was
   misdiagnosed as structural overwrite.

The pieces to fix this are already in place:

- The variant library has **75 variants tagged `"background"`** across
  20 base effects (`Plasma×10, Bars×9, Color Wash×8, Liquid×4,
  Spirals×4, Twinkle×5, …`).
- The scorer applies tier_affinity as a soft 0.20-weighted bias with
  adjacency relaxation — not a hard filter — so background-leaning
  selection coexists with the other scoring axes.
- All 22 themes already use `Normal` + `Additive` blend modes per
  layer; the layer-composition discipline is already tuned.

What's missing is the *policy* that turns tiers 1–4 on and routes the
right affinity context to the scorer when they are.

## What Changes

### V1 core (already implemented in commit 08b74f7b)

- Extend the `tier_map` in `rotation.py` to cover tiers 1–4.
- Extend `_compute_active_tiers` in `effect_placer.py` so each mood
  branch returns a richer set that layers BASE (tier 1) under the
  partition tier, with optional GEO and BEAT layering above.
- Update the `_compute_active_tiers` and `TestTierSelectionByMood`
  unit tests to match the new policy.

### V1 expanded scope (2026-05-06, from iteration-1 observations)

After validating V1 on the Cher fixture, hand-edits in xLights revealed
five additional issues that the iteration session identified as part of
the same "tiers actually working" goal. Bundling here for momentum.

- **Tier-1 duration override.** Tier 1 BASE today produces ~10 short
  per-bar placements per section. Should produce one section-spanning
  placement so BASE reads as a continuous wash, not bar-aligned
  pulses.
- **Sub-prop placement discipline.** Generator places effects on every
  individual flake arm / flake spoke / spinner spoke etc., producing
  ~2900 sub-prop placements on the user's layout. Visually
  overwhelming. Sub-prop work should be opt-in / deliberate, not
  default.
- **`04_BEAT_4` group missing.** Cher is in 4/4 time; layout has only
  3 BEAT groups (BEAT_1..BEAT_3). Beat-group derivation produces N-1
  groups instead of N. Off-by-one bug.
- **Multi-layer BASE composition.** Single Wave on tier 1 reads as a
  sine wave, not depth. Themes need a way to specify a layer stack
  for the BASE tier (e.g. ambient + section-spanning + sparkle).
- **Tier-4 BEAT chase underused.** Generator produces 6 Plasma effects
  on tier 4 instead of a beat-rotated chase. Chase mechanism exists
  in `_place_chase_across_groups` but variant-scoring isn't picking
  rotation-friendly variants like Shockwave.

## What Does NOT Change

- The variant library's `tier_affinity` tags. Already correct;
  iteration-1 surfaced a Wave-tagged-background concern but
  re-tagging is library-data work, separate change.
- The scorer's `_score_tier` function. Already correct.
- Tiers 3 (TYPE) and 5 (TEX). Currently unused; staying unused for
  this change.
- Section detection / boundary alignment. Iteration-1 noted some
  sections didn't align with the music — that's section-classifier
  work, orthogonal to this change.

## Validation

This change is grounded in a **render-watch-tweak iteration loop on
real sequences**, not unit tests alone. See the iteration plan in
[design.md](./design.md#iteration-plan). Microscope panel coverage
(metric: `tier_placement_breakdown`) will track tiers 1, 2, 4
appearing in placements as a regression guard, but the truth source
is what the render looks like in xLights.
