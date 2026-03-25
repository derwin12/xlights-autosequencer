# Data Model: Comprehensive Stem×Parameter Sweep Matrix

**Branch**: `015-sweep-matrix` | **Date**: 2026-03-24

## Entities

### SweepMatrixConfig

Configuration for a sweep matrix run, either auto-derived or loaded from TOML.

| Field | Type | Description |
|-------|------|-------------|
| algorithms | list[str] | Algorithm names to sweep (default: all ~35) |
| stems | list[str] | Stem names to include (default: affinity-determined per algorithm) |
| max_permutations | int | Safety cap (default: 500) |
| sample_duration_s | float | Duration of representative segment (default: 30.0) |
| sample_start_ms | int or None | User override for segment start (default: auto-detected) |
| param_overrides | dict[str, dict[str, list]] | Per-algorithm parameter ranges (overrides auto-derived) |
| output_dir | str or None | Output directory (default: `<audio_dir>/analysis/sweep/`) |
| dry_run | bool | If True, compute matrix but don't execute |

### SweepMatrix

The computed cross-product of algorithms × stems × parameter permutations.

| Field | Type | Description |
|-------|------|-------------|
| permutations | list[Permutation] | All permutations to run |
| total_count | int | Total number of permutations |
| segment_start_ms | int | Start of representative segment |
| segment_end_ms | int | End of representative segment |
| segment_energy | float | Mean RMS energy of selected segment |

### Permutation

A single algorithm×stem×params combination to execute.

| Field | Type | Description |
|-------|------|-------------|
| algorithm | str | Algorithm name |
| stem | str | Stem name |
| parameters | dict[str, any] | Parameter values for this run |
| result_type | str | "timing_track" or "value_curve" |

### PermutationResult

Result of executing a single permutation.

| Field | Type | Description |
|-------|------|-------------|
| algorithm | str | Algorithm name |
| stem | str | Stem name |
| parameters | dict[str, any] | Parameters used |
| result_type | str | "timing_track" or "value_curve" |
| quality_score | float | Score from quality scorer (timing) or curve scorer (value) |
| mark_count | int | Number of timing marks (timing tracks only) |
| sample_count | int | Number of value samples (value curves only) |
| avg_interval_ms | int | Average interval between marks (timing tracks only) |
| dynamic_range | float | Max-min of normalized values (value curves only) |
| status | str | "success", "failed", or "skipped" |
| error | str | Error message if failed |
| duration_ms | int | Wall-clock execution time for this permutation |

### SweepReport (unified, metadata only)

| Field | Type | Description |
|-------|------|-------------|
| audio_path | str | Absolute path to source audio |
| audio_hash | str | MD5 hash of source audio |
| timestamp | str | ISO 8601 timestamp of sweep start |
| segment_start_ms | int | Representative segment start |
| segment_end_ms | int | Representative segment end |
| total_permutations | int | Total permutations attempted |
| completed | int | Successfully completed |
| failed | int | Failed permutations |
| wall_clock_ms | int | Total wall-clock duration |
| results | list[PermutationResult] | All results (metadata only, no marks/curves) |
| best_per_algorithm | dict[str, PermutationResult] | Auto-selected winners |

### AlgorithmResultFile (per-algorithm, full data)

| Field | Type | Description |
|-------|------|-------------|
| algorithm | str | Algorithm name |
| results | list[FullPermutationResult] | All stem×param results with full timing marks or value curve data |

### FullPermutationResult

Extends PermutationResult with full data.

| Field | Type | Description |
|-------|------|-------------|
| (all PermutationResult fields) | | |
| timing_marks | list[TimingMark] | Full marks (timing tracks only) |
| value_curve | list[int] | Normalized 0-100 values at target frame rate (value curves only) |

### StemAffinityEntry

One row in the stem affinity rationale document.

| Field | Type | Description |
|-------|------|-------------|
| algorithm | str | Algorithm name |
| preferred_stems | list[str] | Ordered list of preferred stems (best first) |
| rationale | str | Audio engineering reasoning for the assignment |
| output_type | str | "timing_track" or "value_curve" |
| has_tunable_params | bool | Whether this algorithm has sweepable parameters |
| param_names | list[str] | Names of tunable parameters (empty if none) |

## Relationships

```
SweepMatrixConfig ──builds──▶ SweepMatrix
SweepMatrix.permutations ──contains──▶ Permutation[]
Permutation ──executes──▶ PermutationResult
PermutationResult[] ──aggregates──▶ SweepReport
PermutationResult + timing data ──extends──▶ FullPermutationResult
FullPermutationResult[] ──groups by algorithm──▶ AlgorithmResultFile
SweepReport.best_per_algorithm ──selects from──▶ PermutationResult[]
StemAffinityEntry[] ──determines default stems for──▶ Permutation.stem
```

## File Layout

```
<audio_dir>/analysis/sweep/
├── sweep_report.json              # SweepReport (unified metadata)
├── sweep_qm_beats.json            # AlgorithmResultFile (full data)
├── sweep_qm_onsets_complex.json   # AlgorithmResultFile
├── sweep_aubio_onset.json         # AlgorithmResultFile
├── sweep_bbc_energy.json          # AlgorithmResultFile
├── ...                            # One per algorithm
└── winners/                       # Auto-selected best results
    ├── qm_beats_drums.xtiming     # Exported timing track
    ├── bbc_energy_full_mix.xvc    # Exported value curve
    └── ...
```
