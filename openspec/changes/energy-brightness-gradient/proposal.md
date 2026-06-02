# Proposal: energy-continuous brightness gradient

> **WITHDRAWN 2026-05-31 — DO NOT IMPLEMENT.** The motivating evidence was an
> artifact of the diagnostic harness, not a real generator defect. The
> measured "r = −0.59 inversion" came from feeding **un-normalized** per-section
> energy scores into the generator. The real pipeline normalizes section energy
> across the song (`src/story/builder.py:550`, min→0 / max→100). When the same
> songs are re-measured with normalized scores (what production actually
> produces), the inversion disappears:
>
> | Song | raw scores (flawed test) | normalized (real pipeline) |
> |---|---|---|
> | Maple Leaf Rag | — | **r = +0.89** (brightness tracks energy well) |
> | Nostalgic Piano | −0.59 | **r = −0.17** (uncorrelated; confounded by silence-fragment "sections" and a genuinely compressed dynamic range appropriate to a quiet piano piece) |
>
> Conclusion: the generator's energy→brightness mapping is **sound** on songs
> with a real dynamic arc. There is no systematic inversion to fix. The
> `design.html` was removed so it can't be acted on. The text below is retained
> verbatim as a record of what was investigated and why it was dropped.
>
> If the quiet-song weakness is ever revisited, do it on the **real
> vamp/madmom analyzer** (production energy + sections), not the librosa proxy
> used here, and across several songs — not a single fixture.

## Problem

Render-grounded diagnostics on two songs (Maple Leaf Rag — synthetic story;
Nostalgic Piano — real librosa sections + RMS energy) show that **rendered
brightness does not track section energy**. On Nostalgic Piano the
energy↔brightness correlation across sections was **r = −0.59**: the
highest-energy section (energy 64) rendered dimmest (~28/255) while a
lower-energy section (energy 41) rendered brightest (~104/255).

Root cause, traced in `effect_placer.py` + `models.py`:

1. Section energy reaches brightness **only** through `energy_to_mood`
   (`models.py:20`), a 3-bucket step function (≤33 ethereal / ≤66
   structural / >66 aggressive).
2. `_compute_active_tiers` (`effect_placer.py:2108`) keys purely off
   `mood_tier`, returning a fixed tier set per mood. More tiers ≈ brighter.
3. Most real songs sit entirely in the 34–66 "structural" band, so every
   body section collapses to one mood → one tier set → **flat brightness
   budget**. The energy arc is quantized away.
4. The only fine-grained per-section brightness lever is
   `adjust_palette_brightness` (`chord_colors.py:391`), driven by **harmonic
   tension** — independent of section energy. This noise fills the vacuum and
   happened to land negative.

Notably, the **other** energy dimensions are already continuous:
`compute_duration_target` (speed), `restrain_palette` (color boldness),
`compute_music_sparkles` (sparkle), and the density filter all scale smoothly
with `energy_score`. **Brightness is the lone lagging dimension.**

This is distinct from PR #125 (`dim-section-real-cause`), which raised the
*floor* (low-energy structural sections were pathologically dim due to sparse
variant dedup) but deliberately stayed within the structural band and added
no energy→brightness *gradient*. This change is complementary: #125 ensured
sections aren't dim by accident; this ensures brightness *varies with energy
on purpose*.

## Goal

Make rendered brightness rise monotonically with section `energy_score` — so
a higher-energy section reads brighter than a lower-energy one — by giving
brightness the same continuous-energy treatment its sibling dimensions
(speed, color, sparkle, density) already have, **without** flattening the
floor #125 established.

## Approach

Add a continuous **energy brightness multiplier** applied to each section's
palette value (HSV V), composed with — not replacing — the existing tension
multiplier.

- New pure helper `energy_brightness_multiplier(energy_score: int) -> float`
  in `effect_placer.py`, mapping energy 0→100 to a bounded multiplier
  (proposed 0.80→1.20, so the effect is a gentle gradient, not a blowout).
- Apply it where palettes are finalized per section, alongside the existing
  `adjust_palette_brightness(tension)` call, so brightness =
  `base_palette_V × tension_mult × energy_mult`, both clamped.
- Multiplier bounds chosen so the **floor stays at or above #125's level**
  (min 0.80, never below) — the gradient only *adds* headroom for
  high-energy sections; it cannot re-introduce the dim-section regression.

Energy still flows through `mood_tier` for tier *selection* (unchanged); this
change adds an orthogonal brightness gradient *within* whatever tier set the
mood selects.

## Alternative considered

**Re-bucket or widen `energy_to_mood` (more mood tiers).** Rejected: it would
change which *tiers fire* (placement structure, group counts) for many
sections — a far larger blast radius touching `_compute_active_tiers`,
`_select_groups_for_layer`, the rotation plan, and every tier-coverage test —
to fix what is fundamentally a brightness-scaling gap. The palette-V
multiplier is a minimal, orthogonal lever that doesn't perturb placement.

**Also scale speed/color/boldness harder with energy.** Rejected as
already-implemented: `compute_duration_target`, `restrain_palette`, and
`compute_music_sparkles` already scale continuously with `energy_score`.
Duplicating that would over-correct. This change deliberately closes only the
brightness gap and leaves the working dimensions alone.

## Scope

- **In scope:**
  - `src/generator/effect_placer.py` — new `energy_brightness_multiplier`
    helper + its application at the per-section palette-finalization site
    (the existing `adjust_palette_brightness` call path).
- **Out of scope:**
  - Changing `energy_to_mood` buckets or tier selection.
  - Emitting an xLights `Brightness`/value-curve parameter (this generator
    encodes brightness as palette V; no schema change needed).
  - Re-tuning #125's density brackets or dense-fill set.

## Verification expectation

Multi-dimensional, via the render loop (`tools/render_panel`) — **not
brightness alone**, since speed/density/color already carry energy and a
brightness-only check could mask over-correction:

- Per-section energy↔brightness correlation goes from −0.59 to **strongly
  positive (target r ≥ +0.5)** on Nostalgic Piano.
- Floor preserved: minimum per-section brightness does **not** drop below the
  pre-change value (guards against re-introducing #125's dim regression).
- No drop in `lit_mean` / placement counts (tier selection unchanged).
- Eyeball a before/after contact sheet of the highest- and lowest-energy
  sections to confirm the high-energy section now visibly reads brighter.

If correlation doesn't move positive, or the floor drops, the change is
misdiagnosed and reverted.
