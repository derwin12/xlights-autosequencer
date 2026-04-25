## Why

PR #81 (`docs/analysis-pipeline-improvements-2026-04.md`) added multi-source
boundary-agreement scoring and three improvements to the analysis pipeline,
and explicitly listed four follow-ups as "out-of-scope-for-now":

1. Expose per-section agreement score in `_story.json` so the review UI
   can highlight low-confidence sections
2. Track mean agreement score as a regression metric across the library
3. Snap-to-cluster boundary refinement on the Genius path
4. Tune the SSM (self-similarity matrix) threshold and add it as a
   validation signal for Genius-labeled Chorus sections

PR #84 ("Section confidence scores + Genius snap-to-cluster (Batch 1)")
has since shipped follow-ups #1 and #3 and the *prototype* of #2:

- `src/analyzer/boundary_cluster.py` — productionized clustering module
- `src/story/builder.py` — Genius snap-to-cluster + per-section
  `agreement_score` field in `_story.json`
- `scripts/library_fidelity.py` — per-song / library-wide score report

What is **not yet shipped** from the four follow-ups, and is the scope of
this change:

- **Frontend surfacing.** `_story.json` carries `agreement_score`, but
  `src/review/api/v1/analysis.py` does not propagate it into the section
  payload sent to the Analyze screen, so the React frontend can't
  highlight low-confidence sections. The data is in the file; nothing
  reads it.
- **Library fidelity as a gate metric.** `scripts/library_fidelity.py`
  exists but is a manual run-it-yourself diagnostic. It is not wired
  into `src/evaluation/acceptance_gate.py`, so a regression that
  silently lowers the library mean score will not fail CI or the local
  gate. The metric is computable but un-tracked.
- **SSM threshold tuning + Chorus validation.**
  `scripts/self_similarity_prototype.py` recovers structural repetitions
  but uses a hard-coded threshold and produces zero groups on at least
  one test song (*Believe*). It is not productionized, not in
  `src/analyzer/`, and not consulted when classifying Genius Chorus
  sections.

Closing these three gaps finishes what PR #81 set out to do: the agreement
signal becomes visible to humans (UI), defended against regression (gate),
and used to validate the highest-value section role (Chorus, via SSM).

## What Changes

- **Surface `agreement_score` to the frontend.** Extend
  `src/review/api/v1/analysis.py` so each section in the analyze-step
  payload carries its `agreement_score`. Extend the Analyze screen's
  `Section` type and section list to render a low-confidence indicator
  for sections with score 0–1.
- **Wire library fidelity into the acceptance gate as a fourth suite.**
  Move the scoring math from `scripts/library_fidelity.py` into
  `src/evaluation/section_fidelity.py` (importable). Add a
  `run_section_fidelity_suite` that computes mean agreement over the
  acceptance corpus's stories, compares it to a snapshotted baseline,
  and contributes to the gate's exit code. `scripts/library_fidelity.py`
  becomes a thin CLI wrapper around the new module (no behavior change
  for existing manual users).
- **Productionize the SSM as `src/analyzer/self_similarity.py`.** Move
  the matrix math out of the prototype, with a tuned auto-threshold.
  Compute repetition groups during analysis, store them on
  `HierarchyResult` (new `repetition_groups` field, optional). Use them
  in `src/story/builder.py` as a *validator* for Genius Chorus
  sections: when a Genius-labeled Chorus has no SSM repetition support
  (no other Chorus section in the same repetition group, and no
  self-similar peer within the song), append a warning to the section
  and flag it on the section dict for the UI.

**Out of scope:**

- Implementation. This change is **design-only**. A separate PR will
  follow with code, tests, and baseline updates.
- Re-running PR #81's QM segmenter sweep with a better fitness function
  (still listed as open in the source doc, but not one of the four
  named follow-ups).
- Re-classifying section roles based on SSM. SSM stays a *validator*;
  Genius and `section_classifier.py` remain the source of truth for
  role labels. Score-driven role correction is a separate proposal.
- Changing the snap-to-cluster algorithm itself (already shipped).
- Changing what counts as a source in the cluster (already locked in
  `src/analyzer/boundary_cluster.py`).

## Capabilities

### New Capabilities

- `story-section-agreement`: Defines the contract for the per-section
  agreement signal end-to-end — what `agreement_score` means in
  `_story.json`, how it must propagate through the analyze-step API into
  the frontend, how the library-wide mean is computed and gated, and
  how the SSM validator interacts with Genius Chorus sections.

### Modified Capabilities

<!-- No existing spec at openspec/specs/ governs section-agreement
     surfacing, gate suites beyond analyzer/generator/UI, or SSM. The
     three published specs (analyzer-value-curves, design-gate,
     pre-mortem-review) are orthogonal to this change. No delta files
     required. -->

## Impact

**Code changes (planned for the implementation PR — not this PR):**

- `src/review/api/v1/analysis.py` — analyze-step section payload includes
  `agreement_score`; new `low_confidence` derived flag for the UI
- `src/review/frontend/src/screens/Analyze.tsx` — `Section` interface
  gains `agreement_score: number`; visual indicator on the section list
- `src/evaluation/section_fidelity.py` (new) — pure scoring module
  imported by both `scripts/library_fidelity.py` and the gate suite
- `src/evaluation/acceptance_gate.py` — new `run_section_fidelity_suite`,
  added to `run_gate`'s suite dict; baseline file
  `tests/golden/section_fidelity/baseline.json`
- `src/analyzer/self_similarity.py` (new) — productionized from
  `scripts/self_similarity_prototype.py`, with auto-threshold
- `src/analyzer/result.py` — `HierarchyResult` gains optional
  `repetition_groups: list[RepetitionGroup]` field
- `src/analyzer/orchestrator.py` — invoke SSM during L6/structure pass;
  populate `repetition_groups`
- `src/story/builder.py` — read `repetition_groups`; for each
  Genius-labeled Chorus, set a `chorus_ssm_supported: bool` flag on
  the section dict
- `tests/golden/analyzer/baseline.json` — re-snapshot for the new
  `repetition_groups` field
- `scripts/library_fidelity.py` — slim down to CLI wrapper

**Shared modules touched:** `src/analyzer/` (86 importers), `src/story/`
via `builder.py` (32+ importers per session-context), `src/review/`
(32 importers). Full Design-First Gate applies; regression surface in
`design.md`.

**Schema change to `_story.json`.** The `chorus_ssm_supported` flag is
the only new field; `agreement_score` is already present (PR #84).
Backward compatibility for older `_story.json` files on disk:
consumers MUST default the flag to `True` (no SSM evidence ≠ unsupported)
when the field is absent. Stale files without `agreement_score` already
default to `0` per `scripts/library_fidelity.py:46`; that behavior
extends to the API consumer.

**No new external dependencies.** SSM uses `librosa.segment.recurrence_matrix`
which is already a project dep.

**No version bump on `_story.json`.** Both new fields are additive and
optional with documented defaults; no consumer breaks on absence.
