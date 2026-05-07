# Design: tier-layering policy

## Goal

Allow tiers 1 BASE, 2 GEO, and 4 BEAT to *layer* under tier 6 PROP and
tier 8 HERO instead of being mutually exclusive — by routing the right
affinity context to variant scoring and choosing layer index + blend
mode per tier so the lower tiers genuinely sit underneath instead of
visually overwhelming the higher ones.

## Approach

### 1. Extend the tier→affinity map

[`src/generator/rotation.py:107`](../../../src/generator/rotation.py#L107):

```python
tier_map = {
    1: "background",
    2: "background",
    3: "mid",          # provisional; tier 3 still inactive in this change
    4: "mid",
    5: "mid",          # unchanged
    6: "mid",          # unchanged
    7: "foreground",   # unchanged
    8: "hero",         # unchanged
}
```

The starting values for tiers 1, 2, 4 are *seed* values to be tuned
against rendered output (see iteration plan). Decision rationale:

- **1 BASE = "background"** — the canonical "wash under everything"
  tier; should match the 75 background-tagged variants.
- **2 GEO = "background"** — spatial sweeps on bounding-box groups
  read as structural backdrop, not focal motion.
- **4 BEAT = "mid"** — beat punctuation needs to read above BASE/GEO
  but shouldn't compete with PROP detail.

### 2. Extend `_compute_active_tiers`

[`src/generator/effect_placer.py:1980`](../../../src/generator/effect_placer.py#L1980).
Current vs proposed:

| `mood_tier`                       | Current | Proposed   |
|-----------------------------------|---------|------------|
| `ethereal`                        | `{8}`    | `{1, 8}`   |
| `structural` + strong phrases     | `{2, 8}` | `{1, 2, 8}` |
| `structural` (default)            | `{6, 8}` | `{1, 6, 8}` |
| `aggressive`                      | `{4, 8}` | `{1, 4, 6, 8}` |

Notes:

- Tier 1 is added to *every* branch — it is the always-on quiet wash
  the architecture was designed for, and the affinity map will route
  its variant selection toward background-tagged options (Twinkle,
  Liquid, Snowflakes, low-contrast Color Wash, etc.).
- The `aggressive` branch picks up tier 6 alongside tier 4 because the
  current `{4, 8}` produces almost nothing on the bulk of props
  (BEAT_1..BEAT_4 cover ~80 models split four ways → many props get
  dark sections). Adding 6 keeps the prop-family detail.
- Tier 7 COMP and tier 5 TEX remain unaddressed in this change.

### 3. New: inter-tier layer + blend policy — DEFERRED

The original design proposed a `_layer_and_blend_for_tier` helper that
would force tier 1 BASE onto its own xLights layer band with a
`Normal` blend mode (so its wash sits underneath rather than being
additively brightened by itself).

**Scoped out of V1** (decision 2026-05-06, before any code landed).
Reasoning:

- Forcing the helper requires touching ~20 placement-construction
  call sites in `effect_placer.py` to override `layer.blend_mode`
  per tier — non-trivial wire-up.
- The helper's necessity is speculative: we haven't yet seen the
  default policy (with tier_affinity routing toward background
  variants) produce the "BASE additively over-brightened" symptom
  on real renders. Adding it pre-emptively violates "don't
  over-engineer" — solve the problem at hand.
- The iteration loop is the right gate. If a Cher render with the
  V1 policy shows BASE clobbering or over-brightening, we add the
  helper as a small follow-up change with concrete evidence.

V1 ships pieces 1 + 2 only (`tier_map` + `_compute_active_tiers`).
The blend helper is a follow-up change if and only if the iteration
loop produces the symptom that originally motivated it.

### Alternative considered

**Lift the policy to JSON config.** The `tier_map` and the mood→tier-set
table could move to `~/.xlight/tier_policy.json` so users could tune
without touching code. Rejected: the values are software-engineering
defaults, not user preferences, and the iteration loop will be
correcting them in code with version control. Lifting to config trades
a small ergonomic gain for a worse iteration loop and a new file we'd
have to validate, document, and migrate. Revisit only if user-facing
tuning becomes a real ask.

## Files touched

- `src/generator/rotation.py` (modified) — extend `tier_map` dict.
- `src/generator/effect_placer.py` (modified) — extend
  `_compute_active_tiers` and add `_layer_and_blend_for_tier`.
- `tests/unit/test_generator/test_effect_placer.py` (modified) —
  update the four exact-frozenset assertions to the new policy values.
- `tests/unit/test_generator/test_rotation.py` (modified, if exists) —
  update tier_map assertions (need to check).
- `openspec/changes/tier-layering-policy/specs/...` — TBD; this is a
  policy change, may not need a spec delta.

## Regression surface

`_compute_active_tiers` callers (verified via grep across `src/` and
`tests/`):

- [`src/generator/plan.py:313`](../../../src/generator/plan.py#L313) —
  the only production caller. Stores result on `assignment.active_tiers`.
  Already handles arbitrary frozenset content. **No change needed.**
- [`tests/unit/test_generator/test_effect_placer.py:541, 548, 556, 576`](../../../tests/unit/test_generator/test_effect_placer.py)
  — four exact-equality assertions on the returned frozenset.
  **Must update** to match new policy.

`tier_map` in `rotation.py` is module-private (no external callers via
grep). **No external regression surface.**

`_layer_and_blend_for_tier` is brand new — no callers exist yet.

## Historical echoes

- **`.wolf/buglog.json`** — searched for `BASE|tier 1|tier_1`: no entries.
- **`.wolf/cerebrum.md`** — searched: no entries.
- **The in-code historical record** is the comment block in
  `_compute_active_tiers` itself (effect_placer.py:1980-1990) —
  "Previously included Tier 1 (BASE_All) which covered every model and
  drove tier_utilization to ~100% even in silent moments." That past
  decision is the relevant echo. The user (Rob, 2026-05-06) re-examined
  it directly and concluded the symptom was bold-effect-on-BASE, not
  structural overwrite. This change addresses the underlying cause:
  `tier_map[1] = "background"` biases scoring toward quiet variants,
  and `_layer_and_blend_for_tier(1, …) = (band 0, "Normal")` gives BASE
  its own bottom layer band.

If the iteration loop reproduces the "BASE overwhelms" symptom, the
fallback is to ratchet down the seed values (e.g., move tier 1 to a
narrower variant pool) — *not* to revert tier 1 to inactive. The
iteration plan documents what to look for.

## Iteration plan

This is the part that grounds the change in real renders, not just
JSON tuning. The loop is hybrid — automated pre-review on every
iteration, human visual review only when pre-review passes obvious
checks.

### Render pipeline (confirmed working 2026-05-06)

The devcontainer's `xlights-render.sh` SSHs to the macOS host and
invokes the native (non-App-Store) xLights `--render` flag. End-to-end
benchmark for the Cher 3:30 song: **12.5s wall time, 7.5s actual
render** — about 17× realtime. xLights' window appears briefly on the
Mac during render but does not block the workflow.

```
[devcontainer]                                   [Mac host]
  python3 ... microscope run ...   ──┐
  ↓                                   │
  Cher-...xsq (in /home/node/xlights) │
  ↓                                   │
  xlights-render.sh Cher-...xsq  ────┼──→  ssh + native xLights --render
                                      │              ↓
                                      │     Cher-...fseq (mounted dir, visible to both)
  ↓                                   │
  pre-review on .xsq + .fseq    ←────┘
  ↓
  treatment-notes-<slug>.md
```

Required env (all already set in this devcontainer):

- `XLIGHTS_HOST_USER=rob`
- `XLIGHTS_HOST_SHOW_DIR=/Users/rob/xlights`
- SSH key at `/home/node/.ssh-host/id_ed25519` (mounted from `~/.ssh`)
- macOS Remote Login enabled, key in `authorized_keys`

### Songs

Two CC0 contrasting fixtures plus the user's reference:

1. **Cher — DJ Play a Christmas Song** (Rob's reference, already
   analyzed and rendered against the user's real layout). Mid-tempo
   pop / Christmas / `mood_tier == "structural"`. Baseline `.xsq` /
   `.fseq` already exist at `~/xlights/Cher-DJ_Play_a_Christmas_Song.{xsq,fseq}`.
2. **A second fixture with `mood_tier == "aggressive"`** so we
   exercise the `{1, 4, 6, 8}` branch (the most layered combination).
   Candidate: any panel fixture with high tempo / strong drum activity.
3. **A third fixture with `mood_tier == "ethereal"`** so we exercise
   the `{1, 8}` branch where BASE is the *only* non-HERO tier.

### Loop (per song)

For each song, in order:

1. **Baseline** — capture the *current code's* `.xsq` + rendered
   `.fseq` to `~/xlights/<slug>__baseline.{xsq,fseq}`. (For Cher this
   already exists; just rename.)
2. **Treatment** — generate the `.xsq` with the *new policy* and
   render it to `~/xlights/<slug>__treatment.{xsq,fseq}`.
3. **Pre-review (automated, in devcontainer)** — produce
   `treatment-notes-<slug>.md` with these structural diffs:

   - **Active-tier breakdown per section** — observed `active_tiers`
     for each section in baseline vs treatment. Tiers that *should*
     be active per the new policy but are absent are immediate fails.
   - **Layer-stack-per-prop snapshot** — for 3–5 representative props
     across tiers (e.g. `Arch - Right - 1`, `GE Flake A 1`, `Panel
     Matrix`), list every `(tier, effect, blend_mode, layer_index)`
     tuple firing on it during the chorus and during the bridge.
     Confirms BASE actually layers under PROP rather than just being
     scheduled but absent.
   - **Affinity-mismatch report** — count placements where the
     selected variant's `tier_affinity` doesn't match the
     `tier_map[group.tier]` value. A high count on tier 1 means
     scoring isn't routing toward background variants and we need to
     adjust the seed values.
   - **Palette and brightness deltas** — per-section `palette_luminance_mean`,
     `palette_luminance_cv`, `effect_repeat_rate` from the
     microscope-style metric set. Used to spot "BASE is now louder
     than HERO" symptoms.

   The pre-review output is a markdown document with a one-line
   verdict at the top: `PRE-REVIEW: PASS` or `PRE-REVIEW: FAIL —
   <reason>`. If FAIL, the iteration goes back to step 1 with the
   suggested adjustment without bothering the human reviewer.

4. **Visual review (human, only on PASS)** — open both `.xsq` in
   xLights side-by-side. Watch the first 30 seconds, a busy section
   (chorus / drop), and a quiet section (bridge / intro). Append
   observations directly to the same `treatment-notes-<slug>.md`,
   one entry per observation, format:

   ```
   section: chorus 1 (1:14–1:38)
   observation: BASE Twinkle is now visible under the PROP arches —
                reads as a soft glow, doesn't compete. Good.
   adjustment: none
   ```

   ```
   section: bridge (2:08–2:24)
   observation: BASE went to Color Wash (red→green crossfade) during
                the "ethereal" branch. Way too bold for a quiet
                moment — brighter than the HERO Panel Matrix.
   adjustment: Color Wash should not be in the background pool for
                ethereal sections. Either ratchet up the affinity
                weight (currently 0.20 → maybe 0.30) or filter Color
                Wash from ethereal-mood candidates entirely.
   ```

5. **Iterate** — apply adjustments to the policy values, regenerate,
   re-render, re-pre-review. Most iterations should resolve in the
   pre-review step without needing a fresh visual review.

### When this loop ends

Stop iterating when:

- All three fixtures pass automated pre-review (active tiers
  populated, layer stacks coherent, affinity mismatches near zero).
- The most recent visual review pass on each fixture produces zero
  "this is worse than baseline" observations.
- Microscope `tier_placement_breakdown` (now wired to count tier 1, 2,
  4 placements after this change) shows the expected tiers receiving
  placements per the mood policy.
- The notes files contain at least 5–10 visual-review entries per
  song so future changes have a record of what was watched and why
  each adjustment was made.

The notes files become the actual deliverable that grounds the
change. They live colocated with the test renders (not in `docs/`),
because they are diagnostic logs of a specific iteration session — not
permanent documentation.

### Pre-review scripts

Two short scripts to write as part of this change (live under
`scripts/` since they're iteration tooling, not production code):

- `scripts/render_baseline_treatment.sh` — wrapper that takes a song
  slug, regenerates both baseline and treatment `.xsq` (using
  separate git refs or a feature flag), invokes `xlights-render.sh`
  on each, and lays out the `~/xlights/<slug>__{baseline,treatment}.{xsq,fseq}`
  pair. ~30 lines of bash.

- `scripts/pre_review_tier_layering.py` — produces the per-iteration
  markdown report described above. Reads both `.xsq` and (optionally)
  the `.fseq` for pixel-level brightness sanity checks. Pure read-only
  — no mutation of the generator code. ~150 lines.

These scripts are part of the iteration plan, not the production
change. They live in `scripts/` and don't trigger the Design-First
gate (they're not in shared modules).

### What this loop is NOT

- Not a measurement of "is the sequence good." That is a separate
  question (the strategic conversation that started this change). The
  loop only validates that the policy fix doesn't *make things worse*
  and that tiers 1, 2, 4 produce visually coherent output when active.
- Not a substitute for unit tests on the policy's exact return values.
  Both are needed.
- Not a replacement for the user's eyes on rendered motion. The
  pre-review catches structural failures (tier 1 still empty, BASE
  still picking Color Wash 90% of the time, etc.); only the human
  watching the rendered output can catch motion / transition / music
  sync problems.

## Out of scope

- Tier 3 TYPE and tier 5 TEX activation. They are written to the
  layout but unused; addressing them is a separate change.
- Tier 7 COMP rotation entries not surviving into the .xsq. Separate
  bug; surfaced during this investigation but not part of this fix.
- Lifting the tier_map and active-tier-set policies to JSON config.
  Considered and rejected (above).
- Variant-library re-tagging. The 75 background-tagged variants are
  taken at face value; if iteration shows specific variants are
  miscategorised, that's a follow-up data change.
