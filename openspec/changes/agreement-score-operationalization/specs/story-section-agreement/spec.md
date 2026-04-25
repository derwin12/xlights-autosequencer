## ADDED Requirements

### Requirement: Per-section agreement_score is propagated end-to-end to the analyze-step API

The analyze-step API payload SHALL include the per-section integer `agreement_score` for every section emitted by the story builder, and SHALL include a derived boolean `low_confidence` field equal to `agreement_score <= 1`. When `_story.json` carries `agreement_score` it SHALL be copied verbatim; when the field is absent (legacy file written before PR #84) the API SHALL substitute `0` and set `low_confidence` to `true`.

#### Scenario: Story with agreement_score is propagated unchanged

- **WHEN** the analyze-step API builds its sections payload from a
  `_story.json` whose section has `agreement_score: 4`
- **THEN** the corresponding section in the API payload SHALL have
  `agreement_score: 4` and `low_confidence: false`

#### Scenario: Score 0 or 1 sets low_confidence true

- **WHEN** a section's `agreement_score` is `0` or `1`
- **THEN** the API SHALL set `low_confidence: true` for that section

#### Scenario: Score 2 or higher sets low_confidence false

- **WHEN** a section's `agreement_score` is `2`, `3`, `4`, or higher
- **THEN** the API SHALL set `low_confidence: false` for that section

#### Scenario: Legacy story without agreement_score defaults to 0

- **WHEN** the analyze-step API reads a `_story.json` written before
  PR #84 (no `agreement_score` field on the section)
- **THEN** the API SHALL emit `agreement_score: 0` and
  `low_confidence: true` for that section
- **AND** the API SHALL NOT raise on the missing field

### Requirement: The Analyze frontend Section type carries agreement_score and low_confidence

The frontend `Section` interface in `src/review/frontend/src/screens/Analyze.tsx` SHALL declare `agreement_score: number` and `low_confidence: boolean`, and the section list rendered by the Analyze screen SHALL display a visual indicator (icon, color, or badge — exact treatment is implementation-detail) for sections where `low_confidence` is true.

#### Scenario: Frontend Section interface includes the new fields

- **WHEN** the Analyze screen receives sections from the API
- **THEN** each `Section` SHALL have a numeric `agreement_score` and a
  boolean `low_confidence`

#### Scenario: Low-confidence sections are visually distinguished

- **WHEN** a section in the list has `low_confidence: true`
- **THEN** the rendered section row SHALL include a visual marker that
  is not present on sections with `low_confidence: false`

#### Scenario: High-confidence sections render without the marker

- **WHEN** every section in the list has `low_confidence: false`
- **THEN** no section row SHALL render the low-confidence marker

### Requirement: A section_fidelity suite participates in the acceptance gate

The acceptance gate (`src/evaluation/acceptance_gate.py`) SHALL include a fourth suite named `section_fidelity` alongside the existing `analyzer`, `generator`, and `ui` suites. The suite SHALL compute the library-mean `agreement_score` over the resolved corpus's `_story.json` files, compare it against a baseline at `tests/golden/section_fidelity/baseline.json`, and contribute to the aggregated exit code per the gate's existing rules (regression → 6, no-baseline → 4, infrastructure failure → 8, all pass → 0).

#### Scenario: Library mean within tolerance returns pass

- **WHEN** the section_fidelity suite runs against a corpus whose
  computed library-mean is within `0.10` of the baseline value
- **THEN** the suite's `SuiteResult.status` SHALL be `"pass"`
- **AND** the suite SHALL contribute exit-code `0`

#### Scenario: Library mean below tolerance returns regression

- **WHEN** the computed library-mean drops more than `0.10` below the
  baseline value
- **THEN** the suite's `SuiteResult.status` SHALL be `"fail"`
- **AND** the gate's aggregated exit code SHALL be `6`

#### Scenario: Missing baseline file returns no-baseline

- **WHEN** the suite runs and `tests/golden/section_fidelity/baseline.json`
  does not exist
- **THEN** the suite's `SuiteResult.status` SHALL be `"no-baseline"`
- **AND** the gate's aggregated exit code SHALL be `4` (unless a
  higher-priority code from another suite supersedes per existing
  rules)

#### Scenario: Fixture without _story.json is skipped without failure

- **WHEN** a corpus fixture has a hierarchy but no `_story.json` (the
  story step never ran)
- **THEN** the suite SHALL omit that fixture from the library-mean
  computation
- **AND** the suite's status SHALL NOT regress on that basis alone

### Requirement: scripts/library_fidelity.py and the gate suite share one scoring module

The scoring math SHALL live in `src/evaluation/section_fidelity.py` as a pure module with no I/O coupling to the gate or to the script, and both `scripts/library_fidelity.py` and `src/evaluation/acceptance_gate.py` SHALL import from it. The script's printed report SHALL remain byte-compatible with PR #84's output (same column order, same totals lines) so existing manual users see no diff.

#### Scenario: Script and gate produce identical library-mean for the same corpus

- **WHEN** `scripts/library_fidelity.py` and the gate suite are run
  against the same set of `_story.json` files
- **THEN** both SHALL report the same `library_mean` value to four
  decimal places

#### Scenario: Script's stdout format is unchanged from PR #84

- **WHEN** `scripts/library_fidelity.py` is invoked with the same
  arguments and corpus that produced the table in
  `docs/section-confidence-snap-to-cluster-2026-04.md` "Measured
  results"
- **THEN** the printed columns and totals SHALL match the recorded
  output (modulo non-deterministic source rows from the underlying
  story builder)

### Requirement: HierarchyResult carries optional repetition_groups from SSM

`HierarchyResult` SHALL include an optional field `repetition_groups: list[RepetitionGroup] | None` defaulting to `None`. When the analyzer's SSM step succeeds, the orchestrator SHALL populate it with the detected repetition groups. When SSM produces zero groups (no diagonals exceed the auto-threshold), the field SHALL be `[]`. When SSM errors or is unavailable, the field SHALL remain `None` and a warning SHALL be appended to `HierarchyResult.warnings`.

#### Scenario: SSM produces groups → field populated

- **WHEN** the analyzer runs SSM on a song with detectable repetitions
  (e.g., a verse-chorus-verse-chorus structure)
- **THEN** `HierarchyResult.repetition_groups` SHALL be a non-empty
  list of `RepetitionGroup` instances

#### Scenario: SSM produces zero groups → empty list

- **WHEN** the auto-threshold yields no diagonals on a song
- **THEN** `HierarchyResult.repetition_groups` SHALL equal `[]`
- **AND** the field SHALL NOT be `None`

#### Scenario: SSM unavailable or errored → None plus warning

- **WHEN** the SSM step raises or is skipped (e.g., feature flag,
  budget exceeded, missing dependency)
- **THEN** `HierarchyResult.repetition_groups` SHALL be `None`
- **AND** `HierarchyResult.warnings` SHALL contain a string noting
  the SSM skip / failure cause

### Requirement: SSM auto-threshold derives from the song's own recurrence-matrix distribution

The SSM threshold SHALL be derived per song from the recurrence-matrix's similarity-value distribution rather than a global constant. The default derivation SHALL be the 90th percentile of off-diagonal matrix values; the threshold SHALL be settable per-call only by callers inside `src/analyzer/self_similarity.py` and is not user-configurable through the public analyzer API in this change.

#### Scenario: Threshold is per-song

- **WHEN** SSM runs on two different songs A and B
- **THEN** the threshold computed for A SHALL depend only on A's
  matrix values, not on B's

#### Scenario: Default threshold is the 90th percentile

- **WHEN** SSM is invoked with no threshold argument
- **THEN** the threshold used SHALL equal the 90th percentile of the
  matrix's off-diagonal values

#### Scenario: Public analyzer API does not expose the threshold

- **WHEN** an external caller invokes the orchestrator
- **THEN** there SHALL be no public flag, kwarg, or config field for
  setting the SSM threshold from outside the analyzer module

### Requirement: SSM validates Genius Chorus sections without changing their roles

The story builder SHALL set a boolean `chorus_ssm_supported` field on each section dict whose role is `"chorus"`. The flag SHALL be `true` when at least one other `"chorus"`-labeled section in the same song falls into the same `RepetitionGroup` as this one, OR when this section's time-span overlaps any `RepetitionGroup` containing two or more members. The flag SHALL default to `true` when `repetition_groups` is `None` or empty. The story builder SHALL NOT change a section's `role` based on SSM evidence.

#### Scenario: Chorus with SSM peer → supported true

- **WHEN** two sections both labeled `"chorus"` fall into the same
  `RepetitionGroup`
- **THEN** both SHALL have `chorus_ssm_supported: true`

#### Scenario: Chorus with no SSM peer → supported false

- **WHEN** a Chorus section's time-span overlaps no `RepetitionGroup`
  with two or more members AND no other Chorus shares any group with
  it
- **THEN** that section SHALL have `chorus_ssm_supported: false`

#### Scenario: SSM unavailable defaults to supported

- **WHEN** `HierarchyResult.repetition_groups` is `None` or `[]`
- **THEN** every Chorus section SHALL have `chorus_ssm_supported: true`

#### Scenario: SSM does not change role labels

- **WHEN** SSM evidence suggests a Verse and a Chorus belong to the
  same repetition group
- **THEN** the story builder SHALL leave both `role` fields untouched
- **AND** SHALL only set `chorus_ssm_supported` on the Chorus

### Requirement: _story.json schema changes are additive and backward compatible

The `_story.json` schema SHALL gain only additive fields in this change (`chorus_ssm_supported` per Chorus section; `agreement_score` is already shipped in PR #84). Consumers reading `_story.json` files written before this change SHALL continue to function without errors, treating absent `chorus_ssm_supported` as `true` and absent `agreement_score` as `0`. No `_story.json` field SHALL be removed, renamed, or have its type narrowed.

#### Scenario: Legacy story file without new fields parses cleanly

- **WHEN** any consumer (`src/review/api/v1/analysis.py`,
  `src/review/server.py`, `src/cli_old.py`,
  `scripts/library_fidelity.py`, `src/evaluation/section_fidelity.py`)
  reads a `_story.json` lacking `chorus_ssm_supported` or
  `agreement_score`
- **THEN** parsing SHALL succeed without exception
- **AND** the consumer SHALL apply the documented defaults
  (`chorus_ssm_supported = true`, `agreement_score = 0`)

#### Scenario: No field is removed or type-narrowed

- **WHEN** comparing the post-change `_story.json` schema to the
  pre-change schema
- **THEN** every field present pre-change SHALL still be present
- **AND** no field's type SHALL become more restrictive

### Requirement: Agreement-score baseline reflects current-main pre-change behavior

`tests/golden/section_fidelity/baseline.json` SHALL be captured by running `xlight-evaluate snapshot-section-fidelity` against the acceptance corpus on current-main (after PR #84 has merged but before any code from this change lands), so the gate suite's first run on the implementation PR is comparing apples to apples.

#### Scenario: Baseline captured before SSM wiring lands

- **WHEN** the implementation PR is opened
- **THEN** the baseline file SHALL have been generated against the
  pre-change pipeline
- **AND** the implementation PR's first gate run SHALL pass without
  needing to update the baseline as the same PR's first action

#### Scenario: Baseline regeneration is documented

- **WHEN** a future change deliberately shifts the library mean (e.g.,
  retuning clustering tolerance)
- **THEN** the baseline SHALL be regenerated in that change's PR
- **AND** the rationale SHALL be recorded in that change's design.md
