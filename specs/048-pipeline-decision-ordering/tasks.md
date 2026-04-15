# Tasks: Pipeline Decision-Ordering Refactor (048)

**Input**: Design documents from `/specs/048-pipeline-decision-ordering/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Capture the behavioural baseline before any refactor diff lands. Goldens live on disk from the pre-refactor commit so every later phase can diff against them.

- [X] T001 Create directory `tests/fixtures/xsq/048_golden/` (committed empty with a `.gitkeep`) to hold pre-refactor golden `.xsq` outputs
- [X] T002 On the current tip of `main` (pre-refactor commit), generate `.xsq` output for four fixture permutations — `default`, `no_focus` (`focused_vocabulary=False`), `no_tier_selection` (`tier_selection=False`), `no_accents` (`beat_accent_effects=False`) — using `tests/fixtures/beat_120bpm_10s.wav` and `tests/fixtures/generate/mock_layout.xml`; write each to `tests/fixtures/xsq/048_golden/{default,no_focus,no_tier_selection,no_accents}.xsq`
- [X] T003 Commit the captured goldens on the 048 refactor branch as the first commit so every subsequent diff gates against the frozen baseline (per research.md §6)

**Checkpoint**: Goldens captured and committed; refactor work may now begin against a fixed baseline.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the regression harness and the call-site audit tools BEFORE touching any production code. Every later phase is validated against these tests.

### Canonical-XML equivalence gate

- [X] T004 [P] Write `tests/integration/test_generator_equivalence.py` with a `_canon(xsq_path)` helper that calls `xml.etree.ElementTree.canonicalize(xml_data=..., strip_text=True)` and returns the canonicalised string (per research.md §3)
- [X] T005 [P] Add four parametrised equivalence tests in `tests/integration/test_generator_equivalence.py` — one per permutation (`default`, `no_focus`, `no_tier_selection`, `no_accents`) — that regenerate `.xsq` from the same fixture audio+layout, canonicalise, and assert byte-equal to `tests/fixtures/xsq/048_golden/<permutation>.xsq` (SC-001, FR-031)
- [X] T006 [P] Add a `@pytest.mark.capture_only`-gated `capture_goldens` helper in `tests/integration/test_generator_equivalence.py` that writes goldens from current output; default CI run MUST skip it (quickstart.md "Regenerating goldens")

### Signature-guard test

- [X] T007 [P] Write `tests/unit/test_place_effects_signature.py` that uses `inspect.signature(place_effects)` to assert the parameter list is exactly `(assignment, groups, effect_library, hierarchy, variant_library, rotation_plan)` and that NONE of `{tiers, section_index, working_set, focused_vocabulary, palette_restraint, duration_scaling, bpm}` appear as parameters (FR-020, SC-002, SC-004)
- [X] T008 [P] In `tests/unit/test_place_effects_signature.py` add a grep-style check (using `pathlib` + `re` over `src/generator/plan.py`) that no `place_effects(...)` call site passes any of the forbidden kwargs, guarding against future reintroduction (SC-004)

### Baseline run

- [X] T009 Run the harness on pre-refactor `main`: `pytest tests/integration/test_generator_equivalence.py tests/unit/test_place_effects_signature.py -v` — equivalence tests MUST pass (goldens match pre-refactor code); signature test MUST currently fail (proves it meaningfully detects the pre-refactor 11-kwarg signature)

**Checkpoint**: Regression harness in place and behaves correctly against the pre-refactor baseline. Equivalence tests green; signature test red (as expected). Any later step that breaks equivalence will be caught immediately.

---

## Phase 3: User Story 1 — Brief UI Reads Section Decisions Off a Structured Object (Priority: P1) MVP

**Goal**: Every per-section creative decision (active tiers, palette target, duration target, accent policy, working set, section index) is a populated field on `SectionAssignment` after `build_plan()` returns — with NO behavioural change yet (precompute pass runs alongside existing decision sites; `place_effects` still reads flags).

**Independent Test**: Build a plan for a fixture song; iterate `plan.sections` and assert each assignment carries non-null `active_tiers`, non-null `accent_policy`, and `palette_target` matching the old `config.palette_restraint` gate. Equivalence gate stays green throughout.

### Tests for User Story 1

- [X] T010 [P] [US1] Write `tests/unit/test_section_assignment.py` test: after `build_plan()`, every `assignment.active_tiers` is a non-empty `frozenset[int]` with values drawn from `{1..8}` (Acceptance Scenario 1)
- [X] T011 [P] [US1] In `tests/unit/test_section_assignment.py`, test: with `config.palette_restraint=True`, every `assignment.palette_target` is a dict keyed by tier number (one entry per tier in `active_tiers`) with integer values in `[1, 6]` (Acceptance Scenario 2)
- [X] T012 [P] [US1] In `tests/unit/test_section_assignment.py`, test: with `config.palette_restraint=False`, every `assignment.palette_target` is `None` (edge case — see spec "Edge Cases")
- [X] T013 [P] [US1] In `tests/unit/test_section_assignment.py`, test: with `config.duration_scaling=True`, every `assignment.duration_target` is a `DurationTarget` with `min_ms`, `target_ms`, `max_ms` populated; with `config.duration_scaling=False`, it is `None` (Acceptance Scenario 3)
- [X] T014 [P] [US1] In `tests/unit/test_section_assignment.py`, test: every `assignment.accent_policy` is a non-null `AccentPolicy` with `drum_hits` and `impact` booleans reflecting today's gate outcomes (Acceptance Scenario 4, FR-013)
- [X] T015 [P] [US1] In `tests/unit/test_section_assignment.py`, test: `assignment.section_index == i` for every `(i, assignment)` in `enumerate(plan.sections)` (FR-015)

### Implementation for User Story 1

- [X] T016 [US1] Add `AccentPolicy` dataclass to `src/generator/models.py` with `drum_hits: bool` and `impact: bool` fields (FR-001, data-model.md "New: AccentPolicy")
- [X] T017 [US1] Extend `SectionAssignment` in `src/generator/models.py` with six new fields, all defaulted to no-op values: `active_tiers: frozenset[int] = field(default_factory=frozenset)`, `palette_target: dict[int, int] | None = None`, `duration_target: DurationTarget | None = None`, `accent_policy: AccentPolicy = field(default_factory=lambda: AccentPolicy(drum_hits=False, impact=False))`, `working_set: WorkingSet | None = None`, `section_index: int = 0` (FR-002, data-model.md "Extended: SectionAssignment")
- [X] T018 [US1] Import needed helpers at top of `src/generator/plan.py`: `_compute_active_tiers`, `restrain_palette`, `compute_duration_target`, `_IMPACT_ENERGY_GATE`, `_IMPACT_QUALIFYING_ROLES`, `_IMPACT_MIN_DURATION_MS` from `src/generator/effect_placer.py`, and `AccentPolicy` from `src/generator/models.py`
- [X] T019 [US1] In `src/generator/plan.py` `build_plan()`, insert a new **decision-precompute pass** between theme selection (step 3) and `place_effects` invocation (step 4) that iterates `enumerate(assignments)` and populates, per assignment: `section_index = idx`; `active_tiers = _compute_active_tiers(section, idx, hierarchy)` when `config.tier_selection` else `frozenset(range(1, 9))`; `duration_target = compute_duration_target(hierarchy.estimated_bpm, section.energy_score)` when `config.duration_scaling` else `None`; `working_set = working_sets.get(theme.name)` when `config.focused_vocabulary` else `None` (plan.md Phase B)
- [X] T020 [US1] In the same precompute pass in `src/generator/plan.py`, populate `palette_target`: when `config.palette_restraint=True`, for each tier in `active_tiers` call `restrain_palette(["#000000"] * 6, section.energy_score, tier)` and store `{tier: len(result)}`; else store `None` (FR-011, research.md §4, data-model.md "palette_target")
- [X] T021 [US1] In the same precompute pass in `src/generator/plan.py`, populate `accent_policy`: `drum_hits = config.beat_accent_effects AND section.energy_score >= 60 AND hierarchy.events.get("drums") is not None`; `impact = config.beat_accent_effects AND section.energy_score > _IMPACT_ENERGY_GATE AND (section.end_ms - section.start_ms) >= _IMPACT_MIN_DURATION_MS AND (not role OR role in _IMPACT_QUALIFYING_ROLES)` where `role = (section.label or "").lower()` (FR-013, research.md §5)
- [X] T022 [US1] Run US1 tests: `pytest tests/unit/test_section_assignment.py -v`
- [X] T023 [US1] Run canonical-XML equivalence gate: `pytest tests/integration/test_generator_equivalence.py -v` — MUST still be green (precompute pass is additive; no behavioural change yet)

**Checkpoint**: Every Brief-visible decision is a populated field on `SectionAssignment`. Equivalence gate green. `place_effects` still reads flags — signature reduction comes next.

---

## Phase 4: User Story 2 — `place_effects` Consumes a Recipe, Not Config Flags (Priority: P1)

**Goal**: `place_effects()` reads all per-section decisions from `assignment`. Signature reduces from 11 kwargs to 6. Zero behavioural change — equivalence gate must stay green across every commit.

**Independent Test**: `inspect.signature(place_effects)` returns `(assignment, groups, effect_library, hierarchy, variant_library, rotation_plan)`. Canonical-XML gate still matches goldens.

**Sequencing note (per strategy in plan.md "MVP-first"):** land two separate commits — (a) `place_effects` reads from assignment while flags remain accepted and IGNORED, gate green; (b) flag parameters removed from the signature, all call sites updated. This keeps bisect-ability if regression surfaces.

### Tests for User Story 2

- [X] T024 [P] [US2] In `tests/unit/test_section_assignment.py`, test: with an assignment where `active_tiers = frozenset({1, 4, 8})`, `place_effects()` produces placements only for groups whose `group.tier` is in that set (Acceptance Scenario 2)
- [X] T025 [P] [US2] In `tests/unit/test_section_assignment.py`, test: with `palette_target = {5: 2, 6: 3, 7: 4, 8: 5}`, each tier-N placement in the returned `group_effects` has `len(placement.color_palette) <= palette_target[N]` (Acceptance Scenario 3)
- [X] T026 [P] [US2] In `tests/unit/test_section_assignment.py`, test: calling `place_effects()` twice with identical assignments produces identical `group_effects` (no ambient state dependency — User Story 2 independent test)

### Implementation for User Story 2 — Step (a): `place_effects` reads from assignment (flags still accepted, ignored)

- [X] T027 [US2] In `src/generator/effect_placer.py` `place_effects()`, replace the `_compute_active_tiers(...)` call (around line 557–560) with `effective_tiers = assignment.active_tiers` — DO NOT remove the `tiers` kwarg yet; simply stop reading it
- [X] T028 [US2] In `src/generator/effect_placer.py` `place_effects()`, replace reads of the `section_index=` kwarg with `assignment.section_index` — every rotation-plan lookup and seed-tuple construction reads off the assignment (FR-033: seeds remain `(section_index, group_index, tier)` byte-identically)
- [X] T029 [US2] In `src/generator/effect_placer.py` `place_effects()`, replace reads of the `working_set=` / `focused_vocabulary=` kwargs with `assignment.working_set` / `assignment.working_set is not None` respectively (data-model.md "working_set")
- [X] T030 [US2] In `src/generator/effect_placer.py` `place_effects()`, replace reads of `bpm=` kwarg with `hierarchy.estimated_bpm` (the only previous consumer path)
- [X] T031 [US2] In `src/generator/effect_placer.py` `place_effects()`, at the per-tier palette-trim site (around line 601–602), replace `if palette_restraint: tier_palette = restrain_palette(tier_palette, section.energy_score, tier)` with a branch that trims `tier_palette` to `assignment.palette_target[tier]` colours when `assignment.palette_target is not None`, using the same spread-index math — NO call to `restrain_palette` from inside `place_effects` (FR-021, plan.md Phase C risk-table entry)
- [X] T032 [US2] In `src/generator/effect_placer.py` `place_effects()`, replace the `duration_scaling` / `bpm` threading to `_place_effect_on_group` with direct passthrough of `assignment.duration_target` (None when disabled — `_place_effect_on_group` already accepts a `DurationTarget`, per data-model.md "duration_target")
- [X] T033 [US2] Run equivalence gate: `pytest tests/integration/test_generator_equivalence.py -v` — MUST be green at step (a). If any fixture diffs, diagnose before continuing.

### Implementation for User Story 2 — Step (b): remove legacy kwargs from signature

- [X] T034 [US2] Rewrite `place_effects()` signature in `src/generator/effect_placer.py` to the final six-parameter form: `place_effects(assignment, groups, effect_library, hierarchy, variant_library=None, rotation_plan=None) -> dict[str, list[EffectPlacement]]` (FR-020)
- [X] T035 [US2] Remove the now-dead imports of `_compute_active_tiers`, `restrain_palette`, `compute_duration_target` inside `place_effects` scope — they remain module-level functions (still called from `plan.py`) but `place_effects` no longer references them (plan.md Phase C)
- [X] T036 [US2] Update the `build_plan()` call site in `src/generator/plan.py` to invoke the new signature: `place_effects(assignment, groups, effect_library, hierarchy, variant_library=variant_library, rotation_plan=rotation_plan)` — no `tiers=`, `section_index=`, `working_set=`, `focused_vocabulary=`, `palette_restraint=`, `duration_scaling=`, `bpm=` kwargs
- [X] T037 [US2] Run signature-guard test: `pytest tests/unit/test_place_effects_signature.py -v` — MUST now pass (it was red in T009)
- [X] T038 [US2] Run US2 tests: `pytest tests/unit/test_section_assignment.py -v`
- [X] T039 [US2] Run equivalence gate again: `pytest tests/integration/test_generator_equivalence.py -v` — MUST remain green across the signature change

**Checkpoint**: `place_effects` is a pure recipe consumer. Signature is six parameters. Equivalence gate green. SC-002, SC-004 met.

---

## Phase 5: User Story 3 — Behavioural Equivalence on Fixture Songs (Priority: P1)

**Goal**: The canonical-XML gate proves zero user-visible change across every permutation. Accent helpers trust `accent_policy` and do not re-evaluate section-level gates.

**Independent Test**: `pytest tests/integration/test_generator_equivalence.py -v` green on all four permutations after every commit in this phase.

### Tests for User Story 3

- [X] T040 [P] [US3] In `tests/unit/test_section_assignment.py`, test: with `accent_policy.drum_hits=False` set manually on an assignment that would otherwise pass the drum gate, `_place_drum_accents` returns an empty dict (Acceptance Scenario 4, FR-022)
- [X] T041 [P] [US3] In `tests/unit/test_section_assignment.py`, test: with `accent_policy.impact=False` set manually on an assignment that would otherwise pass the impact gate, `_place_impact_accent` returns an empty dict (FR-022)
- [X] T042 [P] [US3] In `tests/unit/test_section_assignment.py`, test: accent helper functions (`_place_drum_accents`, `_place_impact_accent`) contain NO reference to `section.energy_score`, `section.end_ms`, `_IMPACT_ENERGY_GATE`, `_IMPACT_QUALIFYING_ROLES`, `_IMPACT_MIN_DURATION_MS` as gates — verified by reading the function source with `inspect.getsource` and regex (SC-005). The per-hit `_DRUM_HIT_ENERGY_GATE` sample is permitted and expected.

### Implementation for User Story 3

- [X] T043 [US3] In `src/generator/effect_placer.py` `_place_drum_accents()`, add `if not assignment.accent_policy.drum_hits: return {}` as the first statement of the function body (plan.md Phase D)
- [X] T044 [US3] In `src/generator/effect_placer.py` `_place_drum_accents()`, remove the drum-event-track presence check and any section-energy threshold — those gates are now carried by `accent_policy.drum_hits`. Keep the per-hit `_DRUM_HIT_ENERGY_GATE` sampling from `energy_curves["drums"]` at each hit's `time_ms` (research.md §2 "Not moved upstream")
- [X] T045 [US3] In `src/generator/effect_placer.py` `_place_impact_accent()`, replace the energy/duration/role gate trio (around lines 1820–1828) with `if not assignment.accent_policy.impact: return {}` (plan.md Phase D)
- [X] T046 [US3] In `src/generator/plan.py` where `_place_drum_accents` and `_place_impact_accent` are called in the post-pass after `place_effects`, REMOVE the outer `if config.beat_accent_effects:` guard (around line 199) — the policy flags now gate unconditionally (FR-013, FR-022)
- [X] T047 [US3] Run US3 tests: `pytest tests/unit/test_section_assignment.py -v`
- [X] T048 [US3] Run equivalence gate: `pytest tests/integration/test_generator_equivalence.py -v` — MUST remain green across all four permutations, especially `no_accents` (FR-031)
- [X] T049 [US3] Run full test suite: `pytest tests/ -v` — confirm no regression elsewhere (SC-006)

**Checkpoint**: Accent helpers are mechanical. `accent_policy` is the single source of truth for section-level accent gating. SC-005 met. Canonical equivalence proven across four permutations. SC-001 met.

---

## Phase 6: User Story 4 — Preview Can Render One Section in Isolation (Priority: P2)

**Goal**: A caller can take a single populated `SectionAssignment`, detach it from its `SequencePlan`, and re-run `place_effects` on it alone — producing results equal to the original full-song run.

**Independent Test**: quickstart.md Walkthrough 2 — snapshot `plan.sections[2].group_effects`, clear it, call `place_effects` on that one assignment, assert equality.

### Tests for User Story 4

- [X] T050 [P] [US4] In `tests/unit/test_section_assignment.py`, test (Walkthrough 2): build a plan, snapshot `plan.sections[2].group_effects`, clear it, call `place_effects(a, groups, effect_lib, hierarchy, variant_library=variant_lib, rotation_plan=plan.rotation_plan)`, assert the result equals the snapshot (Acceptance Scenario 1)
- [X] T051 [P] [US4] In `tests/unit/test_section_assignment.py`, test: a `SectionAssignment` extracted from `plan.sections[i]` and passed alone to `_place_impact_accent` (with `accent_policy.impact=True`) fires the impact accent as it would in the full pipeline (Acceptance Scenario 2)
- [X] T052 [P] [US4] In `tests/unit/test_section_assignment.py`, test: `place_effects` does not reference `section_index` as a parameter anywhere — it reads `assignment.section_index` — verified by calling `place_effects` on a single assignment whose `section_index=5` without passing that index as a kwarg (Acceptance Scenario 3)

### Implementation for User Story 4

- [X] T053 [US4] Verify (no code change expected) that `place_effects` as refactored in Phase 4 already satisfies isolation: it reads `assignment.section_index`, `assignment.active_tiers`, `assignment.palette_target`, `assignment.duration_target`, `assignment.working_set` and needs only `(assignment, groups, effect_library, hierarchy, variant_library, rotation_plan)`. If any residual per-song ambient lookup remains, fix it.
- [X] T054 [US4] Run US4 tests: `pytest tests/unit/test_section_assignment.py -v -k "isolation or walkthrough_2"`

**Checkpoint**: Spec 049 Preview has a clean attachment point — a single assignment plus the shared layout/hierarchy/libs is enough to render one section end-to-end.

---

## Phase 7: User Story 5 — Decision Overrides Have a Natural Attachment Point (Priority: P2)

**Goal**: A caller can mutate `assignment.palette_target`, `assignment.duration_target`, `assignment.active_tiers`, or `assignment.accent_policy` before re-running `place_effects`; the output respects the override without any other plumbing.

**Independent Test**: quickstart.md Walkthrough 3 — set `assignment.palette_target = {t: 2 for t in active_tiers}`, re-run placement, assert every resulting placement has `len(color_palette) <= 2`.

### Tests for User Story 5

- [X] T055 [P] [US5] In `tests/unit/test_section_assignment.py`, test (Walkthrough 3): mutate `assignment.palette_target` to cap at 2 colours per active tier, re-run `place_effects`, assert every placement's palette is trimmed to at most 2 colours (Acceptance Scenario 1)
- [X] T056 [P] [US5] In `tests/unit/test_section_assignment.py`, test: mutate `assignment.duration_target = DurationTarget(min_ms=400, target_ms=600, max_ms=800)`, re-run `place_effects`, assert placements target the overridden range (Acceptance Scenario 2)
- [X] T057 [P] [US5] In `tests/unit/test_section_assignment.py`, test: mutate `assignment.active_tiers = frozenset({1, 8})`, re-run `place_effects`, assert `group_effects` contains only groups whose `tier` is 1 or 8 (Acceptance Scenario 3)
- [X] T058 [P] [US5] In `tests/unit/test_section_assignment.py`, test: set `assignment.accent_policy = AccentPolicy(drum_hits=False, impact=False)` on a section that originally had accents, re-run the accent pass, assert no accent placements appear for that section while others are unaffected (Acceptance Scenario 4)

### Implementation for User Story 5

- [X] T059 [US5] Verify (no code change expected) that the override path works by construction: mutations to `active_tiers`, `palette_target`, `duration_target`, `accent_policy` on the assignment flow through `place_effects` and the accent helpers without needing any new parameter. If a mutation does NOT propagate (e.g. a cached decision computed inside `place_effects`), remove the cache.
- [X] T060 [US5] Run US5 tests: `pytest tests/unit/test_section_assignment.py -v -k "override"`

**Checkpoint**: Spec 047 Brief UI has its attachment points. SC-007 met.

---

## Phase 8: `regenerate_sections()` Migration

**Purpose**: Eliminate the duplicated flag-handling block in `regenerate_sections()`; both `build_plan` and `regenerate_sections` now use the same `SectionAssignment`-driven path.

### Tests for Phase 8

- [X] T061 [P] In `tests/unit/test_section_assignment.py`, test: `regenerate_sections()` called with the same inputs as `build_plan()` for a given subset of section indices produces `group_effects` byte-equal to the originals (no divergence from the new path — FR-023)
- [X] T062 [P] In `tests/unit/test_place_effects_signature.py`, extend the grep-style check to scan `src/generator/plan.py` for any `place_effects(...)` invocation and assert both call sites (in `build_plan` and `regenerate_sections`) use the exact same six-argument form (SC-004)

### Implementation for Phase 8

- [X] T063 In `src/generator/plan.py` `regenerate_sections()` (lines ~365–490), delete the duplicated flag-handling block at lines 437–452 that threads `tiers_arg`, `palette_restraint=`, `duration_scaling=`, `bpm=` into `place_effects`
- [X] T064 In `src/generator/plan.py` `regenerate_sections()`, run the same Phase B decision-precompute loop over the affected `assignments` subset — identical code as T019–T021 (extract into a private helper `_populate_assignment_decisions(assignments, config, hierarchy, working_sets)` in `plan.py` and call it from both `build_plan` and `regenerate_sections` to avoid duplication)
- [X] T065 In `src/generator/plan.py`, refactor `build_plan()` to call the new `_populate_assignment_decisions` helper instead of its inline loop (consolidates the precompute into a single function used by both entry points)
- [X] T066 In `src/generator/plan.py` `regenerate_sections()`, replace the old `place_effects(...)` call with `place_effects(assignment, groups, effect_library, hierarchy, variant_library=variant_library, rotation_plan=rotation_plan)` — identical to `build_plan`'s call (FR-023)
- [X] T067 Run Phase 8 tests: `pytest tests/unit/test_section_assignment.py tests/unit/test_place_effects_signature.py -v`
- [X] T068 Run equivalence gate again: `pytest tests/integration/test_generator_equivalence.py -v` — MUST still be green (regenerate_sections path is not exercised by the default gate, but verifies nothing in `build_plan` broke during the helper extraction)

**Checkpoint**: Single precompute path, single `place_effects` signature, zero duplication. SC-004 fully met.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T069 Run full test suite: `pytest tests/ -v` — zero regressions, zero test-code modifications beyond the `place_effects` signature / `SectionAssignment` field updates required by the refactor (SC-006)
- [X] T070 Walk through quickstart.md end-to-end (Walkthroughs 1, 2, 3 plus the canonical-XML gate) on a devcontainer shell to confirm every example works as written
- [X] T071 Call-site audit: `grep -rn "place_effects(" src/` returns exactly two call sites (one in `build_plan`, one in `regenerate_sections`), both using the six-parameter form (SC-004)
- [X] T072 Accent-helper audit: read `_place_drum_accents` and `_place_impact_accent` source; confirm they contain no references to `section.energy_score`, `section.end_ms - section.start_ms`, `_IMPACT_ENERGY_GATE`, `_IMPACT_QUALIFYING_ROLES`, or `_IMPACT_MIN_DURATION_MS` as gating conditions (SC-005; per-hit `_DRUM_HIT_ENERGY_GATE` is allowed and expected)
- [X] T073 `GenerationConfig` audit: confirm every flag listed in spec.md FR-030 remains present and accepted by the JSON API with unchanged defaults (no removed field, no renamed field)
- [X] T074 Final canonical-XML gate run: `pytest tests/integration/test_generator_equivalence.py -v` — all four permutations green, closing out SC-001

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — MUST run first on pre-refactor `main` to capture goldens
- **Phase 2 (Foundational)**: Depends on Phase 1 — harness requires goldens
- **Phase 3 (US1 — field population)**: Depends on Phase 2 — needs equivalence gate to prove "additive precompute doesn't regress"
- **Phase 4 (US2 — signature reduction)**: Depends on Phase 3 — cannot reduce signature until assignment carries every decision
- **Phase 5 (US3 — accent helpers + equivalence proof)**: Depends on Phase 4 — accent helpers read `assignment.accent_policy` populated in Phase 3 and gated by the new signature from Phase 4
- **Phase 6 (US4 — isolation)**: Depends on Phase 4 — isolation relies on the six-parameter signature
- **Phase 7 (US5 — overrides)**: Depends on Phase 4 — overrides mutate fields read by the new `place_effects`
- **Phase 8 (regenerate_sections migration)**: Depends on Phase 4 — same signature must exist at both call sites
- **Phase 9 (Polish)**: Depends on all prior phases

### User Story Dependencies

- **US1 (field population)**: Foundational — MUST be done before any signature change
- **US2 (signature reduction)**: Depends on US1 (fields must exist before `place_effects` can read them)
- **US3 (behavioural equivalence + accent helpers)**: Depends on US2 (accent helpers receive the assignment under the new signature)
- **US4 (isolation)**: Depends on US2 (isolation is a property of the reduced signature)
- **US5 (overrides)**: Depends on US2 (overrides mutate fields read by the new signature)

### Parallel Opportunities

- T004, T005, T006, T007, T008 can run in parallel (different tests or independent helpers in two test files)
- T010–T015 can run in parallel (same test file, independent test functions)
- T024, T025, T026 can run in parallel
- T040, T041, T042 can run in parallel
- T050, T051, T052 can run in parallel
- T055, T056, T057, T058 can run in parallel
- T061, T062 can run in parallel

---

## Implementation Strategy

### Byte-equivalence first, then signature reduction

The plan deliberately sequences behavioural equivalence (Phases 1–3) **before** any signature change (Phase 4). Rationale: if the canonical-XML gate ever fails, bisect points unambiguously to the decision that regressed — not to a bundled "moved flags around AND changed signature AND re-wrote accent helpers" commit. Every commit in Phases 3–8 is expected to leave the equivalence gate green.

### MVP ordering inside the refactor

1. **Phase 1–2**: Lock the baseline (goldens + harness).
2. **Phase 3 (US1)**: Populate new fields alongside the existing decision sites. Nothing downstream reads them yet. Equivalence gate green — proves the new code has no side effects.
3. **Phase 4 step (a) (US2)**: `place_effects` starts reading from the assignment while flags are still ACCEPTED AND IGNORED. Equivalence gate green — proves reads-from-assignment is equivalent to reads-from-flags.
4. **Phase 4 step (b) (US2)**: Signature changes. Call sites update. Equivalence gate green — proves the signature change is a pure refactor.
5. **Phase 5 (US3)**: Accent helpers trust policy. Equivalence gate green across all four permutations — proves accent gating on policy is equivalent to the old inline gates. This is the refactor's headline acceptance test (SC-001).
6. **Phase 6–7 (US4–US5)**: Downstream affordances (isolation, overrides) — strictly additive, no further behavioural change.
7. **Phase 8**: Consolidate `regenerate_sections` onto the same path.
8. **Phase 9**: Final audits.

### Incremental Delivery

Each phase checkpoint is a safe stopping point. The refactor could be paused after Phase 3 (assignment fields populated, zero downstream consumer change) and spec 047 could still ship against the populated fields. Phase 4 delivers the signature reduction that specs 047/049 need for clean consumer code. Phases 5–8 are strictly about eliminating the last duplication and proving equivalence.

---

## Notes

- [P] tasks = different files or independent test functions in the same file
- [Story] label maps task to specific user story (US1–US5)
- US1 is the foundation — field population must be complete before any consumer (signature reduction, isolation, overrides) can read them
- US3 is the acceptance test for the whole refactor — the canonical-XML gate across four permutations is the merge gate (SC-001)
- US4 and US5 are downstream affordances for specs 047 (Brief) and 049 (Preview); they validate that the attachment points exist, not that they do useful work yet
- Goldens are captured ONCE on pre-refactor `main` (T002–T003). They are NEVER regenerated during the refactor. The `capture_goldens` helper (T006) is strictly for future intentional behaviour changes gated through a new spec.
- `restrain_palette`, `_compute_active_tiers`, `compute_duration_target` remain module-level helpers in `effect_placer.py` — they are now internal producers called only from `plan.py`, never from `place_effects` itself (plan.md Phase C)
- The per-hit `_DRUM_HIT_ENERGY_GATE` sample inside `_place_drum_accents` STAYS — it is a per-hit decision sampling `energy_curves["drums"]` at each beat's `time_ms`, distinct from the per-section `accent_policy.drum_hits` gate (research.md §2 "Not moved upstream")
