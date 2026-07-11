# Iteration backlog

Living document. Captures observations from real-render iteration sessions
that haven't yet been addressed. Each item has enough context for an agent
to pick it up cold.

**How to use this doc:**
- Cluster items by file overlap so we know what can parallelize.
- Pick up items by appending your initials to the line and creating a branch.
- Move items to `docs/iteration-backlog-shipped.md` when their PR merges.
- Add new items as they're observed — keep them concrete, not aspirational.

Last updated: 2026-07-11 (added Cluster F after external comparison against helix-sequencer).

---

## Cluster A — BASE depth

**File overlap:** `src/generator/effect_placer.py`. Items A1, A2, A3 all touch
`_assign_layers_to_tiers` or its callers — should be implemented serially in
one branch. A4 is the bigger schema change and depends on A1 landing first.

| ID | Item | Size | Status |
|---|---|---|---|
| A1 | Multi-layer BASE composition. Extend `_assign_layers_to_tiers` so theme layer 1 also lands on tier 1 (currently only layer 0 does). 2-layer themes (19 of 22) gain depth on BASE. | S (3 lines + tests) | Ready — design above the line in conversation |
| A2 | "Complementary" pairing concept. After A1, BASE shows two effects layered. Investigate whether parameter overrides per layer (e.g. direction reversal: Wave-right on layer 0, Wave-left on layer 1) read as intentional pairing vs. visual noise. | S investigation, M change | Needs investigation in worktree |
| A3 | Variant tier_affinity audit — Wave specifically, broader sweep secondary. Wave variants tagged `"background"` get picked for BASE but render as "boring sine wave" per real-render review (Rob, 2026-05-06). Audit `src/variants/builtins/Wave.json` background-tagged variants against actual rendered output; re-tag misclassified ones. | M data + light investigation | Independent of effect_placer.py — can be its own worktree |
| A4 | Per-tier theme layer stacks. Schema extension: themes specify "tier 1 layers: [A, B]; tier 6 layers: [X]; tier 8 layers: [Y]" rather than today's flat `layers` list interpreted via `_assign_layers_to_tiers`. Cleaner long-term answer than A1. | L | Needs OpenSpec design — not yet ready |

---

## Cluster B — Tier-4 BEAT improvements

**File overlap:** `src/generator/effect_placer.py` (`_place_chase_across_groups`,
`_substitute_*` helpers). One branch.

| ID | Item | Size | Status |
|---|---|---|---|
| B1 | Effect substitution for tier-4 chase. Generator places Plasma on tier 4; user prefers punchy effects (Shockwave / Strobe / Lightning) for beat punctuation. Add `_substitute_beat_chase_effect` mirroring `_substitute_bounding_box_effect` and `_substitute_matrix_effect` patterns. | S | Ready |
| B2 | Aggressive-mood detection sensitivity. Cher rarely fires tier 4 even though it has clear drum-driven sections. The mood classifier may be undercalling "aggressive". Investigate `_compute_active_tiers` triggers for the aggressive branch on songs with stems-data. | M investigation | Needs investigation |

---

## Cluster C — Section structure / classification

**File overlap:** `src/story/`, `src/analyzer/orchestrator.py`. Independent of
clusters A and B — can be its own worktree.

| ID | Item | Size | Status |
|---|---|---|---|
| C1 | Subsections from `qm_boundary` markers. The raw segmenter's qm_boundary markers fall inside role-labelled sections and represent real audio change-points (drums entering, energy build, etc.). Schema extension: `sections[i].subsections: list`. Generator change to refresh effects per subsection. | L | Needs OpenSpec design |
| C2 | Section boundary alignment. Some Cher sections don't align with perceptual boundaries (e.g. intro ends at 15.7s but Rob hears the change at 16.5s — half-bar offset). Investigate `boundary_refinement.py` post-processing — does it pull boundaries to lyric anchors at the cost of musical-downbeat alignment? | M investigation | Diagnostic only first |
| C3 | Transition crossfades between sections. Today effects cut hard at section boundaries. A 500ms crossfade would soften the transition. Mentioned in CLAUDE.md "Section Transition Boundary Cleanup". | M | Independent — could parallel-worktree |

---

## Cluster D — Generator polish (small, independent)

**File overlap:** various, mostly in `src/generator/`. Can mostly parallelize
across separate worktrees if each touches a different sub-file.

| ID | Item | Size | Status |
|---|---|---|---|
| D1 | End-of-song fade out. Songs that end with gradual energy decrease should fade out the lights, not cut. Brightness value curve on the final `_drop` section across all active tiers. CLAUDE.md "End-of-Song Fade Out" entry. | S | Ready |
| D2 | Effect rotation weighted by section energy. Today round-robin via rotation engine. High-energy sections should bias toward Meteors/Shockwave/Strobe; low-energy toward Ripple/Spirals/Wave. | M | Needs design — variant_seed integration |
| D3 | QM segmenter boundary merging by energy. Currently uses 2-second-min-gap heuristic; weight by energy delta across boundary instead. CLAUDE.md "QM Segmenter Boundary Merging" entry. | M | Diagnostic-driven |
| D4 | Prefix-stripping in `_tier6_prop_type` for Left/Right/Top/Bottom direction prefixes. Today the prop-type aggregator strips trailing numbers and single-letter variants, but not leading direction words. So `Left Small Star` and `Right Small Star` end up as two distinct type names with one member each, fail the `>=2` aggregation gate, and never get a `06_PROP_Small_Star` group. Same for `Left/Right Small Tree`. Likely affects other shows with paired props named `Left X` / `Right X`. Fix in `src/grouper/grouper.py:_type_name`. | S (5 lines + tests) | Ready |

---

## Cluster E — Variant library data

**File overlap:** `src/variants/builtins/*.json`. Pure data work, fully
independent of code changes. Excellent parallelization candidate.

| ID | Item | Size | Status |
|---|---|---|---|
| E1 | Audit all `tier_affinity: "background"` variants against actual visual brightness. Today 75 variants tagged background across 20 base effects; uncertain how many actually read as quiet wash vs. competing-with-foreground. Spawn one agent per base effect, render a 10s test sequence per variant, classify as keep / re-tag / consider removing. | L (data) | Highly parallelizable |
| E2 | Audit duration_behavior tags. Some effects may be misclassified (`Color Wash` is `standard` today but the comment says it should always span full sections). | S | Independent |

---

## Cluster F — Ideas from external comparison (helix-sequencer, 2026-07-11)

**File overlap:** none yet — these are investigation/design items, not code
changes. Surfaced by reviewing `H:\Github\helix-sequencer`, a separate
Python audio→xLights `.xsq` generator with a similar library stack
(librosa/madmom/demucs/essentia, direct XML template-clone output, no
xLights automation API). Most of its architecture doesn't suggest anything
we're missing (its theme/effect selection is actually more rigid than ours —
a single deterministic rule table per style preset, vs. our
variant-pool + `variation_seed` selection; its AI/LLM bridge modules are
intentionally stubbed and unused). One idea stood out as a real difference
worth a look.

| ID | Item | Size | Status |
|---|---|---|---|
| F1 | Iterative self-scoring convergence loop. helix has `autonomous_masterpiece_evaluator.py` / `iterative_quality_convergence.py` that score a *candidate* generated sequence against quality rubrics (density, palette discipline, motif memory) and re-render/adjust before settling on final output — i.e. scoring is part of generation, not a separate after-the-fact pass. Today our `microscope` tool (`src/evaluation/metrics/`) is developer-facing only: generate once, measure, diff against a baseline manually. Investigate whether a cheap subset of microscope's metrics (e.g. `tier_utilization`, `repetition_avoidance`) could run inline during `build_plan()` to reject/retry a bad section-level effect pick before committing to it, rather than only surfacing the problem after a full render. | L investigation + design | Needs OpenSpec design — not yet scoped, no code read to confirm feasibility of running metrics mid-generation vs. only post-render |

---

## Out of scope (here for visibility, not for execution)

- 3D model awareness / `WorldPosZ` directional effects
- Buffer transforms (rotation, zoom, blur per layer)
- Custom per-song theme support
- Advanced effects exploration (Kaleidoscope, Warp, Spirograph)
- Value curves integration (CLAUDE.md TODO)
- Per-prop-type suitability matrix beyond current heuristics
- Devcontainer renders without host-Mac SSH (Hetzner amd64 VPS)

These are real but bigger / less-validated items. Keep them in CLAUDE.md
"Future Work" for now; promote to this backlog when a real iteration
session surfaces concrete pain.

---

## Suggested first parallel pass

After this backlog is reviewed/groomed, I'd dispatch the following in parallel
worktrees:

- **Worktree 1:** Item A1 — multi-layer BASE composition (`src/generator/effect_placer.py`)
- **Worktree 2:** Item A3 — Wave variant audit (`src/variants/builtins/Wave.json`, fully independent file)
- **Worktree 3:** Item D1 — end-of-song fade (touches different code path from A1)
- **Worktree 4:** Item D4 — prefix-stripping in `_tier6_prop_type` (`src/grouper/grouper.py`, fully independent file)

Item B1 (tier-4 chase substitution) deferred to next pass — also touches
`effect_placer.py` and would conflict with A1.

Four parallel streams, all touching different files. Wall-clock ~60 min
instead of ~3 hours sequential.
