# Tier and Layout Effectiveness — 2026-05-02 Diagnostic

Captured by the `tier_placement_breakdown` and `group_utilization` metrics
(added in PR #155) running across the default and matrix microscope
panels.

## Headline finding

**Five of eight tiers are dead capacity on the reference panel.** The
generator's tiered architecture (BASE → GEO → TYPE → BEAT → TEX → PROP
→ COMP → HERO) collapses in practice to **HERO + occasionally BEAT +
sparingly GEO**. The remaining tiers — `01_BASE`, `03_TYPE`, `05_TEX`,
`06_PROP`, `07_COMP` — never receive any placements on the four-fixture
panel.

This is why the dogfood attempts have produced null results: any change
to `_build_effect_pool` (tier 6/7 PROP rotation), to weighted
suitability scoring at tier 6, or to `_compute_active_tiers` for BASE
sections is invisible to the panel because those tiers don't fire here.

## Per-tier placement counts (sum across 4 fixtures)

| Tier prefix | Default panel | Matrix panel | Notes |
|---|---:|---:|---|
| `08_HERO` | 673 (89%) | 656 (89%) | Single hero per song dominates |
| `04_BEAT` | 66 (9%) | 66 (9%) | nostalgic_piano only |
| `02_GEO` | 2 (0.3%) | 2 (0.3%) | One placement per "side"; call/response barely fires |
| unknown (direct-model `RadialSpinner`) | 17 (2%) | 17 (2%) | Drum-accent path, not a tier |
| `01_BASE`, `03_TYPE`, `05_TEX`, `06_PROP`, `07_COMP` | 0 | 0 | Never activated |

## Per-fixture group utilization

| Fixture | Active tiers | Distinct groups touched | Coverage |
|---|---|---:|---:|
| funshine | GEO + HERO | 3 | 67% |
| maple_leaf_rag | HERO only | 2 | 22% |
| nostalgic_piano | BEAT + HERO | 6 | 100% |
| space_ambience | HERO only | 2 | 22% |

`maple_leaf_rag` and `space_ambience` reach ~20% of the layout —
**8 of 9 layout-defined props sit dark for most of the song.**

## What the data says about the architecture

### 1. Tier activation gating is too narrow

`_compute_active_tiers` (in `effect_placer.py`) admits exactly one
"partition tier" per section from `{2, 4, 6, 7}`, plus tier 1 and/or 8.
The mood-tier branch table:

```
ethereal     → {8}                    (HERO only — quiet sections)
structural   → {2,8} or {6,8}         (GEO call-response OR PROP rotation)
aggressive   → {4,8}                  (BEAT chase)
```

In practice the four panel songs almost never hit "structural without
strong phrase structure" — the only path that would activate tier 6
PROP. Tier 7 COMP is never selected by `_compute_active_tiers` at all
(it's referenced in `selected[tier]` cases but no mood routes
to it).

### 2. The HERO tier swallows everything else

Single-layer themes (most of the panel) place the layer's primary
effect "across all tier families including HERO (8)" via
`_assign_layers_to_tiers`. So even when a non-HERO partition tier
activates, HERO also receives the same effect. That's why every song
shows HERO ≥ 50 placements: the hero gets covered first, and partition
tiers only paint over what HERO already has.

### 3. GEO call-response barely triggers

`_GEO_CALL_SIDE = {02_GEO_Left, 02_GEO_Top}` and
`_GEO_ANSWER_SIDE = {02_GEO_Right, 02_GEO_Bot}` are the only four
spatial bins the placer uses. `02_GEO_Mid` and `02_GEO_Center` are
dead by construction — props that fall there (e.g. `MatrixCenter` in
the default reference layout) are never reached via the tier-2 path.

The call/response code itself only fires when a section has "strong
phrase structure" (per `_has_strong_phrase_structure`). On the panel,
this happens once per song at most — the 2 GEO placements per song
in funshine are a single call+answer pair across the entire song.

### 4. Layout positional classification is the wrong primitive

Models are sorted into spatial bins (Top/Mid/Bot × Left/Center/Right)
by normalized world coordinates. But the **placer's spatial logic
only uses 4 of the 6 bins**, so 1/3 of the layout is invisible to
GEO regardless of the prop's properties. A matrix prop in the layout
center (the natural place for it) cannot get tier-2 placements no
matter how many hero variants reach it.

This is what PR #151's matrix-heavy fixture worked around — placing
matrix props at corners specifically to dodge the dead bins.

## Implications

### What's broken

- **Tiers 1, 3, 5, 6, 7** are unreachable on the panel. Either the
  panel needs much broader fixture/theme coverage to exercise them,
  or the gating logic in `_compute_active_tiers` and
  `_assign_layers_to_tiers` is too restrictive in practice.
- **Center/Mid spatial bins** are by-construction dead. That's a
  design constraint inherited from the call/response framing; props
  positioned centrally have no tier-2 activation path.
- **Hero saturation** means most songs are 90% one model, 10%
  everything else. The "varied multi-tier hierarchy" the architecture
  describes isn't what the panel actually generates.

### What's working

- **HERO + BEAT** combinations on rhythmic songs (`nostalgic_piano`)
  produce 100% coverage and 6 distinct groups — the architecture *can*
  deliver variety; it's just that 3 of 4 panel songs don't trigger
  the path.
- **PR #152's matrix HERO substitution** correctly catches the
  matrix-as-hero case — the most common path matrices take given
  tier 6 PROP rarely activates.

### Decision call: redesign vs. more experiments

The diagnostic surfaces what the dogfood attempts couldn't show
directly: most of the generator's tier hierarchy is unused on the
panel, so panel-driven experiments on those tiers can't move metrics.

Two paths now have evidence behind them:

1. **Redesign the tier activation logic** so tier 6 PROP and tier 7
   COMP can fire on more sections, and so HERO doesn't automatically
   piggyback on every single-layer placement. The panel would then
   see signal from changes to those tiers.

2. **Expand the panel to fixtures that exercise the dormant tiers**.
   Engineer a fixture set where each fixture targets a different
   tier-activation path (one ethereal song for tier 1, one
   structural-without-phrase for tier 6, etc.), then re-baseline.

These aren't mutually exclusive. (2) is a smaller bite that lets us
**verify (1) made things better** if we choose to do (1). I would
start with (2): the cost is one fixture-engineering pass, the payoff
is a panel that can actually measure tier-level changes.

## Raw payloads

The metrics are now part of every panel run; the structured payloads
(per-tier counts and per-group counts) ride along in
`microscope-out/microscope/<slug>/metrics.json` under the
`tier_placement_breakdown` and `group_utilization` keys.
