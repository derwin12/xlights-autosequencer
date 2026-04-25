## ADDED Requirements

### Requirement: Frame-level algorithms declare element_type as value_curve

Algorithms producing frame-level continuous values (scalar or vector) at a fixed frame rate SHALL register `element_type = "value_curve"`, SHALL NOT emit per-frame data through `TimingTrack.marks` (which represents discrete timing events), and SHALL attach curve data via `TimingTrack.value_curve`.

#### Scenario: BBC Rhythm registers as value_curve

- **WHEN** the analyzer runner inspects `BBCRhythmAlgorithm.element_type`
- **THEN** the value SHALL be `"value_curve"` (not `"onset"`)

#### Scenario: NNLS Chroma registers as value_curve

- **WHEN** the analyzer runner inspects `NNLSChromaAlgorithm.element_type`
- **THEN** the value SHALL be `"value_curve"` (not `"harmonic"`)

#### Scenario: Curve algorithms attach payload via value_curve, not marks

- **WHEN** a `value_curve` algorithm completes a `_run`
- **THEN** the returned `TimingTrack.marks` SHALL be empty
- **AND** `TimingTrack.value_curve` SHALL hold a `ValueCurve` (scalar) or
  `ChromaCurve` (12-dim) instance

### Requirement: ChromaCurve dataclass represents per-frame multi-dimensional chroma

The system SHALL provide a `ChromaCurve` dataclass parallel to `ValueCurve`
but with `values: list[list[int]]` — twelve normalized 0–100 integers per
frame, one per pitch class (C, C#, D, …, B in canonical pitch-class
order). `ChromaCurve` SHALL expose the same `name`, `stem_source`, `fps`,
and `duration_ms` interface as `ValueCurve`, plus `to_dict` /
`from_dict` round-trip serialization.

#### Scenario: ChromaCurve serializes losslessly

- **WHEN** a `ChromaCurve` is serialized via `to_dict` and then
  deserialized via `from_dict`
- **THEN** the result SHALL be value-equal to the original

#### Scenario: ChromaCurve duration matches frame count

- **WHEN** a `ChromaCurve` has N frames at fps F
- **THEN** `duration_ms` SHALL equal `int(N * 1000 / F)`

### Requirement: HierarchyResult carries chroma_curve as an optional L6 field

The `HierarchyResult` dataclass SHALL include
`chroma_curve: Optional[ChromaCurve] = None` as an L6 (Harmonic Color)
field, parallel to the existing `chords` and `key_changes` tracks. When
the analyzer runs and `nnls_chroma` produces output, the orchestrator
SHALL populate this field. When `nnls_chroma` is unavailable (plugin not
installed, algorithm errored), the field SHALL remain `None`.

#### Scenario: chroma_curve populated when nnls_chroma runs

- **WHEN** the analyzer runs on a song where the NNLS Chroma vamp plugin
  is available and produces ≥1 frame of chroma output
- **THEN** `HierarchyResult.chroma_curve` SHALL hold a `ChromaCurve`
  instance with non-empty `values`

#### Scenario: chroma_curve None when nnls_chroma unavailable

- **WHEN** the analyzer runs on a system where the NNLS Chroma vamp
  plugin is not installed
- **THEN** `HierarchyResult.chroma_curve` SHALL be `None`
- **AND** the analyzer warnings list SHALL note the absence

### Requirement: Energy curves are smoothed with rhythm strength when both signals available

`HierarchyResult.energy_curves[stem]` SHALL hold the per-frame mean of `bbc_energy` and `bbc_rhythm` ValueCurves when both are available for that stem at the same fps, and SHALL hold the unmodified `bbc_energy` curve when `bbc_rhythm` is absent.

#### Scenario: Smoothed curve is the mean when both available

- **WHEN** both curves exist with matching fps and frame counts
- **THEN** the resulting curve's value at frame i SHALL equal
  `int(round((energy_values[i] + rhythm_values[i]) / 2))`

#### Scenario: Energy curve unchanged when rhythm missing

- **WHEN** `bbc_energy` is available for a stem but `bbc_rhythm` is not
- **THEN** `HierarchyResult.energy_curves[stem]` SHALL equal the raw
  `bbc_energy` curve

#### Scenario: Frame count mismatch falls back to shorter length

- **WHEN** `bbc_energy` and `bbc_rhythm` exist with the same fps but
  different frame counts
- **THEN** the resulting curve SHALL have `min(len(energy), len(rhythm))`
  frames computed as the per-frame mean
- **AND** a warning SHALL be appended to `HierarchyResult.warnings`
  noting the frame-count mismatch

### Requirement: Chord color resolution falls back to chroma between distant chord events

The `chord_color_for_time(t_ms, chords, chroma_curve)` helper SHALL return Chordino-derived color when a Chordino chord event covers `t_ms` or is within 4000 ms before, SHALL return a chroma-derived color from the dominant pitch class at `t_ms` when the gap exceeds 4000 ms and `chroma_curve` is not None, and SHALL return the most recent Chordino chord's color when `chroma_curve` is None regardless of gap.

#### Scenario: Chordino covers timestamp — chroma not consulted

- **WHEN** `t_ms` falls within 4000 ms of a Chordino chord event
- **THEN** the returned color SHALL match
  `chord_to_color(latest_chord_label)` from the existing
  `chord_colors.py` mapping
- **AND** the chroma curve SHALL NOT be consulted for that timestamp

#### Scenario: Long gap with chroma — chroma drives color

- **WHEN** the most recent Chordino chord event is more than 4000 ms
  before `t_ms` AND `chroma_curve` is not None
- **THEN** the returned color SHALL be derived from the pitch class with
  the highest value at the frame nearest `t_ms` in `chroma_curve`

#### Scenario: Long gap without chroma — Chordino color held

- **WHEN** the most recent Chordino chord event is more than 4000 ms
  before `t_ms` AND `chroma_curve` is None
- **THEN** the returned color SHALL match the most recent Chordino
  chord's color (existing behavior preserved)

### Requirement: Analyzer baseline SHALL reflect post-reclassification track shapes

`tests/golden/analyzer/baseline.json` SHALL be regenerated as part of
this change to reflect: (a) `bbc_rhythm` and `nnls_chroma` tracks with
`element_type="value_curve"`, (b) `bbc_rhythm` carrying a `value_curve`
payload, (c) `nnls_chroma` carrying a `chroma_curve` payload (or its
serialization equivalent on the track), (d) the new
`HierarchyResult.chroma_curve` field present in each fixture's snapshot.

#### Scenario: Baseline matches post-change shape

- **WHEN** `xlight-evaluate snapshot-analyzer` is run against the CC0
  fixtures after the change is implemented
- **THEN** the regenerated baseline SHALL show `element_type="value_curve"`
  for both `bbc_rhythm` and `nnls_chroma` tracks
- **AND** every fixture's `HierarchyResult` snapshot SHALL include a
  `chroma_curve` field (populated or `null` per plugin availability)

#### Scenario: Baseline regeneration is deterministic across runs

- **WHEN** `xlight-evaluate snapshot-analyzer` is run twice in succession
  on the same fixtures with the same code
- **THEN** the two regenerated baselines SHALL be byte-identical for the
  curve fields introduced by this change (qm_segments / segmentino
  non-determinism remains gated by the existing `skip_check` flag)
