## Context

PR #81 (`docs/analysis-pipeline-improvements-2026-04.md`) introduced
multi-source boundary-agreement scoring as a diagnostic
(`scripts/qm_segmenter_sweep.py`, `scripts/boundary_confidence_map.py`,
`scripts/self_similarity_prototype.py`) and listed four follow-ups as
out-of-scope.

PR #84 (`docs/section-confidence-snap-to-cluster-2026-04.md`)
productionized the clustering math and shipped two of the four:

- `src/analyzer/boundary_cluster.py` — `Boundary`, `AgreementCluster`,
  `cluster_boundaries`, `build_clusters_for_hierarchy`,
  `snap_to_cluster`, `agreement_score_at`. Source extractors for
  segmentino, QM segmenter, key changes, energy events, chord-density
  spikes, stem entries.
- `src/story/builder.py:383` — Genius section starts snap to clusters
  with score ≥ 3 within ±1 bar; previous section's end follows.
- `src/story/builder.py:669` — every emitted section carries an integer
  `agreement_score` field.
- `scripts/library_fidelity.py` — manual per-song / library-wide report.

Three gaps remain:

1. **The score does not reach the UI.**
   `src/review/api/v1/analysis.py:325-331` constructs the analyze-step
   sections payload from `_story.json` and copies `role` + start/end ms
   only. `agreement_score` is present in the source dict but not in the
   API output. The React frontend's `Section` interface
   (`src/review/frontend/src/screens/Analyze.tsx:39-44`) has no field
   for it. Reviewers cannot see which sections need attention without
   inspecting JSON on disk.

2. **`scripts/library_fidelity.py` is not gated.**
   `src/evaluation/acceptance_gate.py:74-93` runs three suites
   (analyzer, generator, UI) and aggregates exit codes. There is no
   section-fidelity suite. A regression that lowers the library-mean
   `agreement_score` (e.g., a future change to clustering tolerance or
   to a source extractor) will not surface until someone runs the
   manual script.

3. **The SSM exists only as a script.**
   `scripts/self_similarity_prototype.py` computes a beat-synchronous
   chroma+MFCC recurrence matrix, enhances diagonal stripes, and
   produces repetition groups. It is run manually, has a hard-coded
   threshold, and produces zero groups on *Believe* (per PR #81's
   "what we didn't ship" section). It is not in `src/analyzer/`, no
   orchestrator step calls it, and no consumer uses its output.

This change closes those three gaps.

## Goals / Non-Goals

**Goals:**

- Surface `agreement_score` end-to-end so the Analyze screen can
  visually mark low-confidence sections (score ≤ 1) without changing
  what the score means.
- Add a fourth suite to the acceptance gate that defends the
  library-mean against silent regression. Keep the math and the
  manual-script entry point byte-compatible with PR #84's output.
- Productionize the SSM as `src/analyzer/self_similarity.py` with a
  tuned auto-threshold (the threshold is the open question PR #81
  flagged), and use its output as a *validator* for Genius Chorus
  sections — never as a source of truth for role labels.

**Non-Goals:**

- Implementation. This is the design proposal. Code lands in a
  follow-up PR.
- Changing `snap_to_cluster` or `agreement_score_at` in
  `src/analyzer/boundary_cluster.py` (PR #84's contract is preserved
  exactly — the score consumed by the UI and by the gate is the
  *same* score the file already records).
- Re-classifying section roles based on SSM. SSM cannot promote a
  Verse to a Chorus or vice-versa in this change. It can only flag
  Genius-labeled Choruses as "no SSM peer found" for human review.
- Adding new sources to the cluster mix. The seven sources already in
  `boundary_cluster.py` (segmentino, qm_segmenter, energy_impact,
  energy_drop, chord_density_spike, key_change, stem_entry:*) stay
  exactly as they are.
- Versioning `_story.json`. No breaking schema change.
- Performance work on the SSM. We accept its current ~5–15s cost per
  song; if it crosses 30s on the largest acceptance fixture, the
  implementation PR may add a `--skip-ssm` analyzer flag.

## Decisions

### D1. SSM is a *validator*, not a source

Three options were considered for what SSM contributes:

- **(A) Add SSM as an 8th cluster source.** Each detected repetition
  boundary becomes a `Boundary(source="ssm_repetition", time_ms=...)`,
  feeding directly into `cluster_boundaries`. Rejected: would silently
  shift every snap decision, every per-section `agreement_score`, and
  every gated library-mean. PR #84's measured corpus would no longer
  match. We'd be re-tuning two things at once (snap + SSM) with no
  control case.
- **(B) Use SSM to re-label sections.** If two Genius-Verses are in
  the same SSM repetition group and a Genius-Chorus is not, swap
  labels. Rejected: SSM detects musical similarity, not lyric
  function. A song's two Verses and its Chorus can be musically
  identical (same chord progression, same backing); SSM cannot
  distinguish them. Re-labelling on similarity alone produces wrong
  labels in the songs we most rely on Genius for.
- **(C) SSM as a Chorus validator only.** When a Genius section is
  labeled `chorus`, check whether at least one other section also
  labeled `chorus` falls into the same SSM repetition group, OR
  whether *any* SSM repetition group contains this section's
  time-span. If neither, set `chorus_ssm_supported: false`. The flag
  surfaces in the UI as a "verify this Chorus" hint. Selected.

Choosing (C) keeps SSM advisory. The role label remains Genius's call;
SSM only adds a soft signal that humans can act on. This matches the
"low-confidence sections for human attention" framing PR #84 used for
`agreement_score`.

When `repetition_groups` is empty (SSM threshold produced no groups,
e.g. at-risk songs like *Believe* in PR #81), every section's
`chorus_ssm_supported` defaults to **true** — absence of evidence is
not evidence of absence, and we do not want SSM-broken songs to
flag every Chorus as suspect. The implementation PR documents the
default behavior in code.

### D2. Library fidelity is a fourth gate suite, not a metric inside the analyzer suite

Two options were considered:

- **(A) Extend `run_analyzer_suite`.** Have the analyzer suite emit
  per-song `agreement_score` stats as part of its baseline check.
  Rejected: the analyzer suite operates per-fixture and compares
  fields against a per-fixture baseline. Library-mean is a
  cross-fixture aggregate; conflating per-fixture and aggregate
  baselines blurs the failure mode (one bad fixture vs. a real
  regression).
- **(B) New suite `section_fidelity`.** Mirrors the existing analyzer/
  generator/UI pattern: own baseline file, own `SuiteResult`,
  contributes to the gate's exit-code aggregation per the existing
  rules. Selected.

Suite contract:

- Baseline path: `tests/golden/section_fidelity/baseline.json`.
- Records: `library_mean`, `library_median`, `n_zero_pct`, plus a
  per-fixture breakdown (so the report shows *which* fixture
  regressed, not just that *something* did).
- Tolerance: library_mean must stay within `−0.10` of baseline (about
  10% drop on a typical 1.5–2.5 score range). Hard-coded for now;
  revisit if too tight.
- A snapshot subcommand (`xlight-evaluate snapshot-section-fidelity`)
  generates the baseline, parallel to the existing
  `snapshot-analyzer`.

When the analyzer suite has no `_story.json` (i.e., the story step
never ran for a fixture), the fidelity suite SKIPS that fixture
without failing — the analyzer suite already covers
"hierarchy missing" cases.

### D3. Frontend signals score via a derived `low_confidence` boolean, not the raw integer

Two options:

- **(A) Send the raw integer to the frontend.** Lets the UI choose its
  own visual treatment per score. Rejected: the score's exact value is
  diagnostic data; treating "is this a 1 or a 2" differently in the UI
  pretends a precision the score does not have (it counts independent
  sources within ±1 bar of the boundary — saturation kicks in at 4–5).
- **(B) Send `low_confidence: bool` derived as `agreement_score <= 1`,
  alongside the raw `agreement_score`.** Selected. The boolean is the
  thing the UI renders against; the integer remains for tooltip /
  inspector display. The threshold (≤1) is documented; if it needs
  tuning the spec change is local to `analysis.py`.

Score 0 = "no other source corroborates" (purely lyric-distinguished
sections, e.g. Chorus → Post-Chorus on identical music) is the
designed-low case; score 1 = "single corroborator" is borderline.
Either is a reasonable review prompt.

### D4. SSM threshold is auto-tuned per song, not configured globally

PR #81 flagged "Threshold tuning is needed before wiring it into the
pipeline" but did not pick an approach. Three were considered:

- **(A) Single hard-coded threshold across the corpus.** Rejected: the
  prototype already shows it produces 0 groups on *Believe* and good
  groups on *Candy Cane Lane*. A single value is wrong by construction.
- **(B) Per-song config in `~/.xlight/`.** Rejected: shifts the
  problem to humans (every new song needs a config) and breaks the
  zero-flag orchestrator contract (feature 016).
- **(C) Auto-threshold from the song's own recurrence-matrix
  statistics.** Selected. Use a percentile of the off-diagonal
  similarity distribution (e.g., top 10% of matrix values) as the
  per-song threshold. The exact percentile is the implementation PR's
  one tunable; default 90th percentile per `librosa.segment` examples
  is the starting point.

If auto-threshold still produces zero groups on a song, the analyzer
records `repetition_groups: []` and the validator gives every Chorus
the benefit of the doubt (D1 default).

### D5. Implementation PR will *not* change PR #84's measured library mean

The current PR #84 baseline (per
`docs/section-confidence-snap-to-cluster-2026-04.md` "Measured results"
table) is the snapshot for D2. The implementation PR runs the new
gate suite once *before* any code change, captures the baseline file,
and *only then* lands the SSM-validator wiring. This isolates "did we
break the score" from "did SSM-Chorus-validation work as intended" as
two separate verifiable steps. The order in `tasks.md` enforces this.

## Risks / Trade-offs

**[R1] SSM produces zero groups on some songs (per PR #81 evidence).**
→ Mitigation: D1's "default to supported when no groups" rule keeps
the validator inert on broken-SSM songs. The auto-threshold (D4)
should reduce zero-group cases. The acceptance-fixture corpus must
include at least one song where SSM is known to work (e.g., *Candy
Cane Lane*'s pre-chorus → chorus → post-chorus block) and one where
it currently does not (per PR #81: *Believe*) so the implementation PR
verifies both paths.

**[R2] The new gate suite regresses on first run because the baseline
captures whatever PR #84 + main produce, including any pre-existing
regressions.**
→ Mitigation: D5's two-step (snapshot, then change) ensures the
baseline reflects current-main behavior, not aspirational behavior.
The `tolerance: −0.10` window absorbs noise from non-deterministic
WhisperX/pyannote runs (per PR #84's "Known session non-determinism"
section).

**[R3] Frontend changes ripple into snapshot UI tests.**
→ Mitigation: the analyze-step payload gains *additional* fields
(`agreement_score`, `low_confidence`); existing fields and ordering
stay. The Section interface widens additively. UI snapshot tests
that compare exact JSON should be reviewed; the implementation PR
must update them or assert against subsets, not whole-payload.

**[R4] `_story.json` files written before this change land have no
`chorus_ssm_supported` flag.**
→ Mitigation: the consumer (frontend + any future reader) MUST default
absent → true (per D1). This matches PR #84's pattern of
`agreement_score = 0` default for stale files. No re-analysis is
required for old songs to remain functional; old songs simply show no
SSM hint until re-analyzed.

**[R5] SSM cost on long songs (10+ minute orchestral tracks).**
→ Mitigation: the orchestrator wraps SSM in the same try/except as
other vamp/madmom optional steps. If it errors or exceeds an internal
timeout, `repetition_groups` is `[]` and a warning is appended.
Specific budget: SSM must complete within 30s for the largest CC0
fixture; the implementation PR measures and adds a flag if not.

**[R6] Shared module change: `src/analyzer/` (86 importers),
`src/story/` widely imported, `src/review/` (32 importers).**
→ Mitigation: full Design-First Gate per CLAUDE.md. Regression surface
section enumerates every modified public symbol with grep'd callers.

## Regression surface

Per CLAUDE.md "Design-First Gate" — every public symbol modified, with
caller status. Greps run against `src/` and `tests/`.

- **`HierarchyResult`** (in `src/analyzer/result.py`) — gains
  `repetition_groups: list[RepetitionGroup] | None = None` (additive,
  optional). Callers that read existing fields are unaffected.
  Serialization (`to_dict` / `from_dict`) gains a new key; consumers
  that ignore unknown keys remain compatible. `grep -rn 'HierarchyResult'
  src/ tests/` returns ~40 hits across analyzer, story, review,
  evaluation modules — none read with strict-key checks.

- **`run_orchestrator`** (in `src/analyzer/orchestrator.py`) —
  signature unchanged. Internal behavior gains an SSM step, gated on
  fixture availability and try/except like other optional algorithms.
  Callers (CLI, review server, evaluation harness) unaffected.

- **`build_song_story`** (in `src/story/builder.py`) — signature
  unchanged. Behavior change: each section dict in the returned
  story may carry a new `chorus_ssm_supported: bool` key. Existing
  consumers (review API, library route, generator) read by `.get()`
  and are unaffected by additive keys; verified by
  `grep -rn 'build_song_story\b' src/ tests/`.

- **`_story.json` schema** — additive: `chorus_ssm_supported` per
  Chorus section. `agreement_score` already shipped in PR #84. No
  consumer reads with strict-key validation; the file is parsed via
  `json.loads` and field-accessed via `.get()` everywhere
  (`src/review/api/v1/analysis.py`, `src/review/server.py`,
  `src/cli_old.py`, `scripts/library_fidelity.py`).

- **Analyze API payload (`/api/v1/analyze` SSE stream / final state
  in `src/review/api/v1/analysis.py`)** — section dicts gain
  `agreement_score: int` and `low_confidence: bool`. Frontend type
  `Section` widens to read them. The Analyze screen
  (`src/review/frontend/src/screens/Analyze.tsx:206`) reads sections
  with optional-chaining (`data?.detected_sections ?? data?.sections
  ?? data?.song_story?.sections`); already tolerant of varying field
  sets. Tests that assert exact payload shape need to widen — listed
  in `tasks.md`.

- **`xlight-evaluate gate` exit code** — adds the section-fidelity
  suite to the aggregation. Per existing rules, regression in *any*
  suite produces exit 6; missing baseline produces exit 4. New
  baseline file is bundled with the implementation PR; first PR-CI
  run after merge cannot exit 4 unless the baseline file is missing
  from disk (which the PR adds). `grep -rn 'run_gate\|GateOptions'
  src/ tests/` returns 8 hits — all in `src/evaluation/` and
  `src/cli.py` invocation; none assert the suite count.

- **`scripts/library_fidelity.py`** — public `summarize_song`,
  `load_stories`, `print_report` move into
  `src/evaluation/section_fidelity.py`. The script remains as a thin
  wrapper. External callers: none in `src/` or `tests/` (verified by
  grep). Manual users invoke the script unchanged.

## Historical echoes

`grep` of `.wolf/buglog.json` for `agreement`, `cluster`,
`section_source`, `_story.json`, `boundary_confidence`,
`self_similar`, `library_fidelity`:

- **bug-089** — `scripts/boundary_confidence_map.py` had wrong
  literal (`"section_source"` vs. `"global"`). Fixed in PR #84 era.
  Direct echo: any new code reading `_story.json` global keys must
  use `story.get("global", {}).get("section_source", ...)` — not
  `story.get("section_source")`. The implementation PR's frontend /
  fidelity-suite code reads from `story["global"]` for the
  `section_source` field per this lesson.
- **bug-071** — `scripts/boundary_confidence_map.py` significant
  refactor (3 lines replaced/restructured). Tagged refactor, not a
  bug in the strict sense; relevant only as historical record that
  this code area has been touched recently. The implementation PR
  preserves the import contract from PR #84 (`from
  src.analyzer.boundary_cluster import …`).
- **bug-079, bug-080, bug-083** — all `src/analyzer/genius_segments.py`
  refactor entries. Tangential — the Genius path is upstream of the
  fields this proposal surfaces. No call signature change here.
- No other matches.

`.wolf/cerebrum.md` Do-Not-Repeat:

- **[2026-04-19] "Shipped changes that broke previously-working
  behavior because modified public symbols weren't audited for
  callers."** Applies directly. Caller audit captured in *Regression
  surface* above for `HierarchyResult`, `build_song_story`, the
  Analyze API payload, and the gate exit code.
- **[2026-04-19] "Applied symptom fixes instead of root-cause
  fixes."** Applies to D1: SSM as validator, not source. The
  temptation in implementation will be to special-case Choruses with
  no SSM peer (e.g., "if Believe-class song, ignore SSM"). Resist;
  the auto-threshold (D4) and the absent-default rule (D1) are the
  root-cause fixes.
- **[2026-04-19] "Did more or less than what was asked — scope
  drift."** Applies to the temptation to also re-tune snap-to-cluster
  thresholds or add new cluster sources while implementing this
  change. Out of scope by `proposal.md`.
- **[2026-04-25] "Marked failing tests xfail/skip/--ignore instead of
  fixing."** Applies if the new gate suite trips on first run.
  Resolution: fix the regression or update the baseline with a
  written rationale; do not skip the suite to ship.
- **[2026-04-25] "Tests inherited state from prior runs because
  module-level dicts accumulate across test invocations."** Applies
  to `src/evaluation/section_fidelity.py` — keep it pure-functional
  (no module-level cache).
- **Shared-infrastructure-modules entry:** `src/analyzer/` (86
  importers), `src/story/` (32+), `src/review/` (32). Full gate
  applies; this design is the gate artifact.

## Migration Plan

This proposal is design-only. The migration plan describes the
**implementation PR** that will follow.

1. Run `xlight-evaluate snapshot-section-fidelity` once on
   current-main to capture the baseline. Commit the baseline file.
2. Refactor `scripts/library_fidelity.py` → import from
   `src/evaluation/section_fidelity.py`. No behavior change; verify
   the manual script's output diff against PR #84's recorded numbers
   is empty.
3. Add `run_section_fidelity_suite` to
   `src/evaluation/acceptance_gate.py`. Wire into `run_gate`. Run
   `xlight-evaluate gate --skip-ui` and confirm the new suite passes
   against the baseline captured in step 1.
4. Extend `src/review/api/v1/analysis.py` to copy `agreement_score`
   and add `low_confidence`. Update the React `Section` interface
   and add the visual indicator. Update / widen any UI snapshot
   tests.
5. Add `src/analyzer/self_similarity.py` (productionized from
   `scripts/self_similarity_prototype.py`) with the auto-threshold.
   Add `RepetitionGroup` + `repetition_groups` to `HierarchyResult`.
   Wire orchestrator. Re-snapshot `tests/golden/analyzer/baseline.json`.
6. Wire SSM into `src/story/builder.py` as a Chorus validator. Add
   `chorus_ssm_supported` to section dicts.
7. Run `xlight-evaluate gate` (full Tier B local) and confirm exit
   code 0. Update the section-fidelity baseline only if a deliberate
   change in clustering math justifies it (it should not, in this
   PR).
8. Open implementation PR with reference back to this design.

**Rollback strategy:** revert the implementation PR. The design lives
in `openspec/changes/agreement-score-operationalization/` until the
implementation PR archives it. Reverting code is independent of the
proposal artifact. No on-disk data depends on the new fields except
the new gate baseline (which is regenerated on revert via
`snapshot-section-fidelity`).

## Open Questions

- **Q1.** The `low_confidence` threshold (`agreement_score <= 1`)
  is the obvious starting heuristic but unmeasured. The
  implementation PR should observe how many sections per song trip
  the flag on the acceptance corpus and adjust if the false-positive
  rate is high. Acceptable to land with `<=1` and tune later.
- **Q2.** SSM auto-threshold percentile (D4): 90th percentile is the
  starting point per `librosa.segment` examples, but the right
  value depends on the matrix's similarity-value distribution
  (different per song). The implementation PR could fall back to a
  more elaborate auto-threshold (e.g., Otsu's method on the
  similarity histogram) if 90th percentile is unstable. Land with
  90th; revisit on evidence.
- **Q3.** `RepetitionGroup` data shape — minimal: a list of
  `(start_ms, end_ms)` time-spans plus a group id. Should it also
  carry a similarity score, or per-pair similarity? The validator
  only needs membership, so the minimal shape is preferred. The
  implementation PR may add fields if a downstream consumer
  emerges.
- **Q4.** Whether to also flag *non-Chorus* sections that have an
  unusually high SSM peer count (a Verse that repeats four times
  may merit a Chorus-review hint). Out of scope here per the "SSM
  validates Chorus only" decision (D1-C); reconsider in a follow-up
  if the Chorus-only validator under-fires.
- **Q5.** Tolerance window for the gate's library-mean (D2:
  `−0.10`). 0.10 corresponds to ~5% of typical mean-score range.
  Too strict → flaky CI. Too loose → silent regression. Calibrate
  during implementation by running 3 successive gate runs on
  current-main and observing the noise floor.
