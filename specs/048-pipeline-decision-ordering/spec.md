# Feature Specification: Pipeline Decision-Ordering Refactor

**Feature Branch**: `048-pipeline-decision-ordering`
**Created**: 2026-04-14
**Status**: Draft
**Input**: Phase 4 of the web-UI UX overhaul strategy (`greedy-splashing-chipmunk.md`). Corollary to principle #6 — *"Precompute section decisions before placement."* Creative decisions that shape the feel of a section (active tiers, palette restraint, duration target, accent policy, theme) are currently decided *inside* per-tier/per-layer loops in `place_effects()`. That makes them illegible to the new Brief UI (spec 047) and impossible to render in isolation for the Preview UI (spec 049). This refactor pulls those decisions up into `build_plan()`, stores them once per section on a `SectionAssignment`, and passes that assignment to `place_effects()` as a read-only recipe.

## Background

The generator pipeline grew organically across specs 036-044. Each new creative knob (`focused_vocabulary`, `palette_restraint`, `duration_scaling`, `beat_accent_effects`, `tier_selection`) added a boolean to `GenerationConfig` and an inline conditional inside `place_effects()` — usually deep inside a tier loop or a per-layer branch. The resulting call graph looks like:

```
build_plan(config, ...)
  └─ for assignment in assignments:              # one per section
       └─ place_effects(assignment, ..., config_flags...)
            ├─ _compute_active_tiers(section, section_index, hierarchy)       # per-section, but computed here
            ├─ for layer in theme.layers:
            │    └─ for tier in target_tiers:
            │         ├─ restrain_palette(tier_palette, energy_score, tier)   # per-tier, but inputs are section-level
            │         ├─ compute_duration_target(bpm, energy_score)           # per-placement, but result is section-level
            │         └─ ...
            └─ (returns group_effects dict)
  └─ (post-pass) _place_drum_accents(...)        # accent policy evaluated here
  └─ (post-pass) _place_impact_accent(...)       # accent policy evaluated here
```

Three problems follow from this ordering:

1. **Illegible to callers.** The Brief UI (spec 047) wants to show the user *what was decided for this section* — active tiers, color count, effect length band, whether accents will fire. Today those facts only exist as transient local variables inside `place_effects()`; there is no object to render.
2. **Illegible to overrides.** Spec 047's Brief tab needs per-section overrides (e.g. "force 4 colours here", "use snappy duration on this chorus"). Today the only knobs are global booleans in `GenerationConfig`. There is nowhere to attach a section-scoped override.
3. **Not rendering-isolable.** The Preview feature (spec 049) wants to render one representative section end-to-end without running the whole song. That requires section-level decisions to be addressable independently. Today they are re-derived from `(section, section_index, hierarchy)` every call, with implicit dependencies on global config.

This is a **backend-only refactor**. User-visible output (the generated `.xsq` file) must be byte-for-byte identical after the refactor for the same inputs. The point is to make the decision graph legible, not to change it.

---

## Clarifications

### Session 2026-04-14

- Q: What shape does `SectionAssignment.palette_target` take, given palette restraint depends on both section energy and tier? → A: **Per-tier mapping** `{tier: int}` precomputed in `build_plan()` for every tier in `active_tiers`. Placement reads the value for its tier with no helper call and no recomputation. Maximises flexibility for future per-tier overrides (Brief, Preview) and keeps placement mechanical.
- Q: How is behavioural equivalence enforced in CI — byte-for-byte XSQ diff, canonical XML comparison, or plan-JSON diff? → A: **Canonical XML comparison.** `.xsq` outputs are normalised (attribute order sorted, insignificant whitespace collapsed) before diffing. Canonical equality is the merge gate. Byte-for-byte drift that survives canonicalisation is a true regression; pre-canonical noise (ET serializer attribute order, EOL differences) is never a failure. No separate whitelist is maintained.

---

## User Scenarios & Testing

The "user" in these stories is primarily the developer integrating the Brief UI (spec 047) or Preview UI (spec 049), and the regression-testing harness that proves behavioural equivalence. End-user of the web app has no observable change.

### User Story 1 — Brief UI Reads Section Decisions Off a Structured Object (Priority: P1)

As the Brief UI (spec 047), I want to fetch the per-section creative decisions — active tiers, palette colour count, duration band, accent policy, theme — as plain fields on a `SectionAssignment`, so that I can render them in the Brief table without re-running or instrumenting the generator.

**Why this priority**: This is the reason the refactor exists. Without it, spec 047 has to either (a) scrape values out of the already-rendered `EffectPlacement` list (lossy — many decisions leave no trace) or (b) duplicate the decision logic in the UI layer (drift-prone). A structured `SectionAssignment` makes the Brief a simple read from a JSON serialisation.

**Independent Test**: After building a plan for a fixture song, iterate `plan.sections` and assert that each `SectionAssignment` carries non-null fields for `active_tiers`, `palette_target`, `duration_target`, `accent_policy`, and `theme`. Serialise one section to JSON and confirm every decision visible in the Brief has a corresponding field.

**Acceptance Scenarios**:

1. **Given** a plan built with default config, **When** I read `assignment.active_tiers` for every section, **Then** each contains a non-empty frozenset of ints drawn from `{1..8}`.
2. **Given** a plan built with default config, **When** I read `assignment.palette_target` for every section, **Then** each is either `None` (restraint disabled) or a dict keyed by tier number with integer values in the range `[1, 6]` (the per-tier cap range), with one entry per tier in `active_tiers`.
3. **Given** a plan built with default config, **When** I read `assignment.duration_target`, **Then** each section carries a `DurationTarget` with `min_ms`, `target_ms`, `max_ms` populated from `compute_duration_target(bpm, energy)`.
4. **Given** a plan built with default config, **When** I read `assignment.accent_policy`, **Then** each section carries a struct listing which accents (drum-hit, whole-house impact) are eligible to fire for that section based on the energy/role/duration gates.
5. **Given** the Brief UI renders from `assignment`-level fields, **When** the user reloads the Brief tab, **Then** every visible decision in the UI maps 1:1 to a field on `SectionAssignment` with no UI-side derivation.

---

### User Story 2 — Place_effects Consumes a Recipe, Not Config Flags (Priority: P1)

As the author of `place_effects()`, I want to receive a fully-populated `SectionAssignment` (tiers, palette target, duration target, accent policy already decided) rather than a pile of config booleans and ambient state, so that my job reduces to *mechanical application of a recipe* and stops re-deciding things per-tier.

**Why this priority**: Today `place_effects()` takes eleven keyword arguments (`tiers`, `variant_library`, `rotation_plan`, `section_index`, `working_set`, `focused_vocabulary`, `palette_restraint`, `duration_scaling`, `bpm`, `hierarchy`, …) and branches on several of them inline. Consolidating those decisions onto the assignment both (a) shrinks the function signature and (b) removes the "did I pass the right combination of flags?" class of bug at the call site in `regenerate_sections()`.

**Independent Test**: Inspect the post-refactor `place_effects()` signature. It should take `assignment`, `groups`, `effect_library`, `hierarchy`, `variant_library`, `rotation_plan` — no loose booleans that duplicate what's on `assignment`. Call it twice from a test harness with identical assignments and confirm no ambient state (config flags, module-level globals) can change the result.

**Acceptance Scenarios**:

1. **Given** `place_effects()` is invoked with a prepared `SectionAssignment`, **When** no config booleans are passed alongside, **Then** the function completes successfully and produces the same `group_effects` as the pre-refactor pipeline.
2. **Given** an assignment has `active_tiers = {1, 4, 8}`, **When** `place_effects()` runs, **Then** only groups in those tiers receive placements — and the function does NOT call `_compute_active_tiers()` (that decision was already made upstream).
3. **Given** an assignment has `palette_target = {5: 2, 6: 3, 7: 4, 8: 5}`, **When** `place_effects()` builds a tier-5 palette, **Then** the palette is trimmed to exactly 2 colours using `palette_target[5]` — without reading `config.palette_restraint` (the flag lives in `build_plan` only; `place_effects` sees only the outcome).
4. **Given** an assignment has `accent_policy.drum_hits = False`, **When** `build_plan()` runs the accent pass, **Then** `_place_drum_accents()` is skipped for that section even if `config.beat_accent_effects=True` globally.
5. **Given** `place_effects()`'s new signature, **When** I read it, **Then** there is no `focused_vocabulary`, `palette_restraint`, `duration_scaling`, or `tiers` keyword argument — those decisions live on `assignment`.

---

### User Story 3 — Behavioural Equivalence on Fixture Songs (Priority: P1)

As the maintainer, I want every fixture song to produce a byte-for-byte identical `.xsq` output before and after the refactor (modulo any changes that are explicitly documented in the changelog), so that I can merge this refactor with confidence that no end-user will notice.

**Why this priority**: This is a backend refactor that claims zero user-visible change. That claim is only credible with a regression gate that *proves* it. Without this, the refactor has no acceptance test — every future bug reported on the generator could plausibly have been introduced here.

**Independent Test**: A regression test that pins the generated `.xsq` (or a canonicalised representation of it — sorted effect tuples per group) for 3+ fixture songs. The test runs on the pre-refactor code to capture the golden output, then on the post-refactor code to compare. CI fails if any fixture diffs.

**Acceptance Scenarios**:

1. **Given** three fixture songs with stored pre-refactor golden outputs, **When** the post-refactor pipeline generates each, **Then** the generated `.xsq` is canonically equal to the golden (attribute order normalised, insignificant whitespace collapsed). Any diff that survives canonicalisation fails the gate.
2. **Given** a fixture song that exercises `focused_vocabulary=True`, **When** generated pre- and post-refactor, **Then** the same variant is chosen on each tier-5-8 group in each section.
3. **Given** a fixture song where `tier_selection=True` selects `{1, 2, 8}` for section 0 pre-refactor, **When** generated post-refactor, **Then** section 0 still activates `{1, 2, 8}` and no other tiers.
4. **Given** a fixture song with drum and impact accents firing in chorus sections, **When** generated post-refactor, **Then** accent placements are emitted at the same timestamps, on the same groups, with the same variants as pre-refactor.
5. **Given** `tier_selection=False` (the user-override path), **When** generated post-refactor, **Then** the "all tiers 1-8 active" fallback still applies and matches pre-refactor output.

---

### User Story 4 — Preview Can Render One Section in Isolation (Priority: P2)

As the Preview feature (spec 049), I want to render one section end-to-end by passing a single `SectionAssignment` into an isolated placement routine, without needing the full song's assignments, so that the 10-20 second preview loop is cheap enough to iterate on the Brief.

**Why this priority**: Spec 049 depends on this. Today, running `place_effects` on one section still implicitly reads hierarchy state for that section and re-derives tiers/durations from global BPM. A prepared `SectionAssignment` makes the preview a pure function of the assignment plus the layout — no whole-song context required. This is P2 because spec 049 is downstream and can be implemented after 048 ships.

**Independent Test**: Given a populated `SectionAssignment` and a layout, call `place_effects()` with just that one assignment and verify it returns the same `group_effects` for that section as appeared in the full `plan.sections[i].group_effects` when the whole song was built.

**Acceptance Scenarios**:

1. **Given** a fully-built `SequencePlan`, **When** I extract `plan.sections[2]` and feed it alone to `place_effects()` with the same layout, **Then** the returned `group_effects` equals `plan.sections[2].group_effects`.
2. **Given** a `SectionAssignment` with `accent_policy.impact=True`, **When** the preview code runs the accent pass on that one section, **Then** the impact accent fires as it would in the full pipeline.
3. **Given** a `SectionAssignment` detached from its original `SequencePlan`, **When** rendered in isolation, **Then** no lookup by `section_index` is required (the index and any section-index-dependent decisions are carried on the assignment itself).

---

### User Story 5 — Decision Overrides Have a Natural Attachment Point (Priority: P2)

As the Brief UI (spec 047), I want to apply a per-section override ("use 3 colours for this chorus", "snappy duration for this bridge") by mutating the `SectionAssignment` before generation, so that the override flows through the pipeline without needing new plumbing.

**Why this priority**: The strategy doc calls out per-section overrides as the killer feature of the Brief. This refactor doesn't build the overrides themselves (that's spec 047) — it just ensures there is a clean target for them. P2 because the overrides themselves land in a different spec; this story proves only that the hook exists.

**Independent Test**: Mutate `assignment.palette_target = 2` after `build_plan` populates it, re-run `place_effects` on that assignment, and confirm the resulting tier-5 placements use exactly 2 colours instead of the auto-derived value.

**Acceptance Scenarios**:

1. **Given** a populated `SectionAssignment`, **When** a caller overrides `assignment.palette_target = {5: 2, 6: 2, 7: 2, 8: 2}` and re-runs placement, **Then** the emitted palettes for that section respect the per-tier overrides.
2. **Given** a populated `SectionAssignment`, **When** a caller overrides `assignment.duration_target = DurationTarget(min_ms=400, target_ms=600, max_ms=800)`, **Then** placements for that section target the overridden range.
3. **Given** a populated `SectionAssignment`, **When** a caller overrides `assignment.active_tiers = frozenset({1, 8})`, **Then** only tier 1 and tier 8 groups receive placements for that section.
4. **Given** a populated `SectionAssignment` with `accent_policy.drum_hits = True`, **When** a caller sets it to `False`, **Then** the accent pass skips drum-hit placement for that section without affecting others.

---

### Edge Cases

- **`config.tier_selection = False` (user override)**: `build_plan` must still populate `assignment.active_tiers`, but set it to `frozenset(range(1, 9))`. The downstream `place_effects` behaviour is unchanged — it simply sees "all tiers active" as a decision already made.
- **`config.palette_restraint = False`**: `build_plan` sets `assignment.palette_target = None` (or sentinel value), and `place_effects` treats `None` as "no trim — pass palette through unchanged".
- **`config.duration_scaling = False`**: `assignment.duration_target = None`, and `place_effects` falls back to the theme-layer's declared duration.
- **`config.beat_accent_effects = False`**: `assignment.accent_policy.drum_hits = False` and `assignment.accent_policy.impact = False` for every section; the accent-pass loop in `build_plan` becomes a no-op.
- **`regenerate_sections()` partial-regeneration path**: today this function has its own slightly-divergent call to `place_effects()` with a subset of config flags. It must be migrated to the same `SectionAssignment`-driven path — no separate inline flag handling.
- **Section with zero groups in any active tier**: `assignment.active_tiers` may resolve to a set where no layout groups exist (e.g. a show with no hero models but the section selected tier 8). Today this silently yields an empty `group_effects`; behaviour must be preserved.
- **Accent policy with role = "unknown"**: `_IMPACT_QUALIFYING_ROLES` gate today checks role presence. The precomputed `accent_policy.impact` must apply the same gate during `build_plan`'s decision step, not re-check it inside `_place_impact_accent`.

---

## Requirements

### Functional Requirements — Data Model

- **FR-001**: A new dataclass `AccentPolicy` MUST be added to `src/generator/models.py` with at least these fields:
  - `drum_hits: bool` — whether drum-hit Shockwave accents fire on small radial props in this section
  - `impact: bool` — whether the whole-house white Shockwave impact accent fires at this section's start
- **FR-002**: `SectionAssignment` MUST be extended with the following fields, all populated by `build_plan()` before `place_effects()` is called:
  - `active_tiers: frozenset[int]` — the set of tiers that will receive placements for this section (result of `_compute_active_tiers` or the user override)
  - `palette_target: dict[int, int] | None` — per-tier mapping of tier number → target active-colour count for this section (one entry per tier in `active_tiers`), or `None` when palette restraint is disabled
  - `duration_target: DurationTarget | None` — the duration band for placements in this section, or `None` when duration scaling is disabled
  - `accent_policy: AccentPolicy` — whether each accent mechanism will fire for this section
  - `section_index: int` — position within the song, needed by rotation and reproducibility seeds (today this is passed as a separate argument)
  - `working_set: WorkingSet | None` — the per-theme working set used during placement when `focused_vocabulary=True`, already derived in `build_plan`
- **FR-003**: `SectionAssignment.theme` is already present but MUST be formalised as the authoritative theme for the section — any theme override from `config.theme_overrides` or story review is applied *before* `place_effects` sees the assignment, and nothing inside `place_effects` re-resolves the theme.

### Functional Requirements — Decision Precomputation in `build_plan`

- **FR-010**: Tier selection MUST happen in `build_plan()`, once per section, and write `assignment.active_tiers`. When `config.tier_selection=False`, write `frozenset(range(1, 9))`. Otherwise call the existing `_compute_active_tiers(section, section_index, hierarchy)` and store the result.
- **FR-011**: Palette target MUST be computed in `build_plan()` from `(section.energy_score, tier)` pairs and stored as `assignment.palette_target: dict[int, int] | None` — a mapping of tier → target active-colour count, precomputed for every tier in `active_tiers`. When `config.palette_restraint=False`, `palette_target` MUST be `None`. Placement reads `palette_target[tier]` directly; no helper call, no recomputation from `energy_score`.
- **FR-012**: Duration target MUST be computed in `build_plan()` by calling `compute_duration_target(bpm, section.energy_score)` once per section and storing on `assignment.duration_target`. When `config.duration_scaling=False`, store `None`.
- **FR-013**: Accent policy MUST be computed in `build_plan()` by evaluating the same gates currently inside `_place_drum_accents()` and `_place_impact_accent()`:
  - `accent_policy.drum_hits = config.beat_accent_effects AND section.energy_score >= 60 AND drum-event-track-present`
  - `accent_policy.impact = config.beat_accent_effects AND section.energy_score > 80 AND role in _IMPACT_QUALIFYING_ROLES AND section_duration >= 4000ms`
  - The accent placement helpers MUST then trust the policy flag and skip re-evaluating the gate.
- **FR-014**: Working set derivation MUST happen in `build_plan()` (it already partially does, via `working_sets[theme_name]`) and MUST be stored on each assignment as `assignment.working_set` so `place_effects` can read it directly rather than taking it as a separate argument.
- **FR-015**: Section index MUST be stored on `assignment.section_index` so downstream code (rotation, preview) no longer needs to know the assignment's position in a list.

### Functional Requirements — `place_effects` Signature & Behaviour

- **FR-020**: `place_effects()` MUST be refactored to the reduced signature:
  ```
  place_effects(
      assignment: SectionAssignment,
      groups: list[PowerGroup],
      effect_library: EffectLibrary,
      hierarchy: HierarchyResult,
      variant_library,
      rotation_plan: RotationPlan | None = None,
  ) -> dict[str, list[EffectPlacement]]
  ```
  with NO separate keyword arguments for `tiers`, `section_index`, `working_set`, `focused_vocabulary`, `palette_restraint`, `duration_scaling`, or `bpm` — each of these MUST be read from the assignment (or, for `bpm`, from the hierarchy).
- **FR-021**: `place_effects()` MUST NOT call `_compute_active_tiers()`, `compute_duration_target()`, or `restrain_palette()` directly — those are decisions, already made upstream. Instead it reads `assignment.active_tiers`, `assignment.duration_target`, `assignment.palette_target` and applies them mechanically. (Note: `restrain_palette()` may still exist as a helper called from `build_plan`, but no longer from `place_effects`.)
- **FR-022**: Accent placement (`_place_drum_accents`, `_place_impact_accent`) MUST read `assignment.accent_policy` and early-return without work when the corresponding flag is `False`. The energy/role/duration gates that today live inside these helpers MUST be removed (the policy carries the gate decision).
- **FR-023**: `regenerate_sections()` MUST use the same `SectionAssignment`-driven placement path as `build_plan()`. The duplicated flag-handling block inside `regenerate_sections()` MUST be removed.

### Functional Requirements — Non-Regression

- **FR-030**: Every existing field of `GenerationConfig` MUST remain present and accepted by the JSON API — they become the *serialised form* of the Brief's defaults, not the UI surface. Removing any flag is out of scope.
- **FR-031**: The generated `.xsq` files for a canonical set of fixture songs (≥3 songs exercising different config permutations — default, `focused_vocabulary=False`, `tier_selection=False`, `beat_accent_effects=False`) MUST be **canonically equal** before and after the refactor. Canonicalisation MUST normalise attribute order (lexicographic sort within each element) and collapse insignificant whitespace; element order within a parent MUST be preserved. Any diff that survives canonicalisation is a merge-blocking regression. No per-fixture whitelist is maintained.
- **FR-032**: The `group_effects` dict emitted by `place_effects()` for any given section MUST contain the same keys and, per key, the same list of `EffectPlacement` objects (equal after field-by-field comparison) before and after the refactor.
- **FR-033**: Random seeds used in rotation and working-set sampling MUST continue to derive from `(section_index, group_index, tier)` tuples exactly as today — the refactor MUST NOT change seed computation.

### Key Entities

- **SectionAssignment (extended)**: The single object carrying everything about one section. Today it has `section`, `theme`, `group_effects`, `variation_seed`. After this refactor it also carries `active_tiers`, `palette_target`, `duration_target`, `accent_policy`, `working_set`, `section_index`. `group_effects` remains the output of `place_effects()` and is populated after the decision fields are read.
- **AccentPolicy**: A small struct holding `drum_hits: bool` and `impact: bool` (and future accent types when specs 049+ add them). Per-section; computed in `build_plan` from config, section energy, role, duration, and drum-track presence.
- **GenerationConfig (unchanged on the wire)**: Still carries every existing flag. Inside `build_plan`, flags are consulted once to populate the `SectionAssignment` fields; they are NOT passed onward into `place_effects`.

---

## Success Criteria

- **SC-001**: For at least 3 fixture songs covering default config, `focused_vocabulary=False`, `tier_selection=False`, and `beat_accent_effects=False`, the post-refactor pipeline produces `.xsq` files **canonically equal** (attribute order normalised, insignificant whitespace collapsed, element order preserved) to the pre-refactor pipeline.
- **SC-002**: `place_effects()`'s call signature after the refactor has at most 6 parameters, none of which are booleans duplicating `GenerationConfig` flags.
- **SC-003**: Serialising `plan.sections[i]` to JSON exposes every decision the Brief UI needs to render — `active_tiers`, `palette_target`, `duration_target`, `accent_policy`, `theme.name`, `section.label`, `section.energy_score` — without any value being derived at serialisation time from `config` or `hierarchy`.
- **SC-004**: `grep place_effects` across the codebase finds exactly one call site inside `build_plan()` and one inside `regenerate_sections()` (both using the new signature). No call site passes config flags alongside the assignment.
- **SC-005**: The accent helper functions (`_place_drum_accents`, `_place_impact_accent`) contain no energy/role/duration gate logic — only mechanical placement driven by `assignment.accent_policy`.
- **SC-006**: The existing unit and integration test suites pass with zero modifications to test code, except for updates required by the new `place_effects` signature or `SectionAssignment` field names.
- **SC-007**: Given a populated `SectionAssignment`, a caller can overwrite `active_tiers` / `palette_target` / `duration_target` / `accent_policy` and re-run `place_effects()` in isolation, producing placements consistent with the overrides — demonstrating the attachment points the Brief (spec 047) and Preview (spec 049) will use.
- **SC-008**: No new user-visible behaviour exists. Dashboard screenshots, generated sequences, and Brief UI rendering (if already shipped) show no observable differences on identical inputs.

---

## Out of Scope

- New creative features (tier heuristics, palette rules, accent types) — those are specs 045-049.
- Changes to `GenerationConfig`'s JSON wire format or removal of any flag.
- Rewriting `_compute_active_tiers`, `compute_duration_target`, or `restrain_palette` — these helpers are reused as-is; only the *call site* moves upstream.
- Restructuring `theme_selector.select_themes()` — theme assignment is already precomputed; this spec only formalises the flow, no logic change.
- UI work — the Brief tab (spec 047) and Preview tab (spec 049) consume the new attachment points but are built separately.
- Migration of old plan-JSON files written by the pre-refactor generator; plan-JSON diagnostics are regenerated every run, so no on-disk migration is required.

---

## Sequencing & Dependencies

- **Phase 3 (spec 047 — Brief)** can ship before this refactor. It will temporarily either scrape values from `group_effects` or duplicate a subset of decision logic client-side. Phase 4 cleanup lands shortly after and replaces those scrape/duplicate paths with direct reads off `SectionAssignment`.
- **Phase 5 (spec 049 — Preview)** benefits directly: preview becomes "given one `SectionAssignment` and the layout, render just this section". Without the refactor, preview has to reconstruct the full pipeline for one section, dragging in global flags and section-index dependencies.
- Upstream helpers — `derive_section_energies` (`src/generator/energy.py`), `energy_to_mood` (`src/generator/models.py`), `select_themes` (`src/generator/theme_selector.py`), `derive_working_set` (`src/generator/effect_placer.py`) — are unchanged. They are the producers that `build_plan` already composes; this spec just adds four more producers (tiers, palette, duration, accent policy) into the same precompute pass.

---

## Verification Strategy

Since this refactor claims no user-visible change, verification is dominated by **behavioural equivalence** testing:

1. **Golden-file regression (canonical XML)**: Capture `.xsq` outputs for fixture songs on `main` before merging. A CI check canonicalises both sides (attribute order normalised, insignificant whitespace collapsed) and diffs. Any surviving diff fails the gate; no per-fixture whitelist.
2. **Call-site audit**: A grep-based check in CI (or a pytest assertion) verifies that no internal caller passes `tiers=`, `focused_vocabulary=`, `palette_restraint=`, `duration_scaling=`, `working_set=`, `section_index=`, or `bpm=` to `place_effects`. These kwargs are removed; tests fail if reintroduced.
3. **Field-coverage test**: A unit test iterates every field on the Brief's read-model and asserts each maps to an attribute on `SectionAssignment`, not to a derivation from `config` or `hierarchy`.
4. **Isolation test**: A unit test that takes a populated `SectionAssignment`, detaches it from its `SequencePlan`, and re-runs `place_effects` on it — asserting the result equals `assignment.group_effects` from the original full-song run.

---

## Key Files

- `src/generator/models.py` — add `AccentPolicy`; extend `SectionAssignment` with `active_tiers`, `palette_target`, `duration_target`, `accent_policy`, `working_set`, `section_index`.
- `src/generator/plan.py` — `build_plan()` grows a decision-precompute pass between theme selection (step 3) and effect placement (step 4). `regenerate_sections()` is migrated to the same path.
- `src/generator/effect_placer.py` — `place_effects()` signature reduction; removal of inline `_compute_active_tiers`, `compute_duration_target`, `restrain_palette` calls from within the per-tier/per-layer loops; `_place_drum_accents`/`_place_impact_accent` read `assignment.accent_policy`.
- `src/generator/energy.py` — unchanged (producer only).
- `src/generator/theme_selector.py` — unchanged (producer only).
- `tests/integration/test_generator_equivalence.py` — new test file: golden-file diff across fixture songs for multiple config permutations.
- `tests/unit/test_section_assignment.py` — new test file: assignment-field population, override behaviour, isolation rendering.
- `tests/unit/test_place_effects_signature.py` — new test file: guards that no legacy kwargs are reintroduced on `place_effects()`.
