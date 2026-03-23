# Data Model: Configurable Quality Scoring

**Branch**: `011-quality-score-config` | **Date**: 2026-03-22

---

## Entities

### ScoringCategory

Defines expected target ranges for a group of algorithms.

| Field | Type | Description |
|-------|------|-------------|
| name | str | Category identifier (e.g., "beats", "bars", "onsets", "segments", "pitch", "harmony", "general") |
| description | str | Human-readable description of what this category represents |
| density_range | tuple[float, float] | Expected marks-per-second range (min, max) |
| regularity_range | tuple[float, float] | Expected regularity range (min, max) |
| mark_count_range | tuple[int, int] | Expected total mark count range (min, max) |
| coverage_range | tuple[float, float] | Expected coverage fraction range (min, max) |

**Identity**: Unique by `name`.

**Relationships**: Each algorithm maps to exactly one ScoringCategory via a built-in lookup table. Unknown algorithms fall back to the "general" category.

---

### CriterionResult

A single criterion's measurement and score for one track.

| Field | Type | Description |
|-------|------|-------------|
| name | str | Criterion identifier ("density", "regularity", "mark_count", "coverage", "min_gap") |
| label | str | Human-readable description (e.g., "Mark density — timing marks per second of audio") |
| measured_value | float | Raw measured value for this track |
| target_min | float | Category target range minimum |
| target_max | float | Category target range maximum |
| weight | float | Configured weight for this criterion |
| score | float | Criterion score (0.0–1.0) based on how well value fits target range |
| contribution | float | weight * score (this criterion's contribution to the overall score) |

**Identity**: Unique within a ScoreBreakdown by `name`.

---

### ScoreBreakdown

The complete scoring result for a single track.

| Field | Type | Description |
|-------|------|-------------|
| track_name | str | Name of the scored track |
| algorithm_name | str | Algorithm that produced this track |
| category | str | Scoring category applied to this track |
| overall_score | float | Final weighted score (0.0–1.0) |
| criteria | list[CriterionResult] | Per-criterion breakdown |
| passed_thresholds | bool | Whether the track passes all configured thresholds |
| threshold_failures | list[str] | Names of thresholds that failed (empty if all passed) |
| skipped_as_duplicate | bool | Whether this track was excluded by the diversity filter |
| duplicate_of | str | None | Name of the selected track this duplicates (if skipped) |

**Identity**: Unique within an analysis result by `track_name`.

**Serialization**: Included in the analysis JSON output as a `score_breakdown` field on each track dict.

---

### ScoringConfig

User-defined scoring configuration.

| Field | Type | Description |
|-------|------|-------------|
| weights | dict[str, float] | Criterion name → weight mapping. All values >= 0, sum > 0 |
| thresholds | dict[str, float] | Optional min/max thresholds. Keys: "min_{criterion}" or "max_{criterion}" |
| diversity_tolerance_ms | int | Mark alignment tolerance for diversity filter (default: 50) |
| diversity_threshold | float | Proportion threshold for near-identical classification (default: 0.90) |
| min_gap_threshold_ms | int | Minimum actionable gap in milliseconds (default: 25) |
| category_overrides | dict[str, dict] | Category name → field overrides for target ranges |

**Validation rules**:
- All weights must be >= 0
- Sum of weights must be > 0 (all-zero rejected)
- Unknown criterion names rejected
- Unknown category names in overrides rejected
- diversity_threshold must be in (0.0, 1.0]
- diversity_tolerance_ms must be > 0
- min_gap_threshold_ms must be > 0

**Loading**: Built from TOML file via `tomllib` (Python 3.11+). Absent fields use built-in defaults.

---

### ScoringProfile

A named, saved ScoringConfig.

| Field | Type | Description |
|-------|------|-------------|
| name | str | Profile name (derived from filename, e.g., "fast_edm" from "fast_edm.toml") |
| path | Path | Filesystem path to the TOML file |
| config | ScoringConfig | The loaded configuration |

**Identity**: Unique by `name` within a search scope (project-local, then user-global).

**Storage**: TOML files in `~/.config/xlight/scoring/` (user-global) or `.scoring/` (project-local).

---

## Category-to-Algorithm Mapping (Built-in Default)

| Category | Algorithm Names |
|----------|----------------|
| beats | qm_bar_beat_beats, beatroot_beats, librosa_beats, madmom_rnn_beats, madmom_rnn_downbeats |
| bars | qm_bar_beat_bars, librosa_bars |
| onsets | qm_onset_broadband, qm_onset_hfc, qm_onset_complex, librosa_onset, librosa_hpss_drums |
| segments | qm_segmenter |
| pitch | pyin_note_events, pyin_pitch_changes |
| harmony | chordino_chord_changes, nnls_chroma_peaks, librosa_hpss_harmonic |
| general | (fallback for unknown algorithms) |

---

## JSON Output Schema Extension

The analysis JSON gains a `score_breakdowns` field at the top level (list of ScoreBreakdown dicts), and each track dict gains a `score_breakdown` reference:

```json
{
  "timing_tracks": [
    {
      "name": "librosa_beats",
      "quality_score": 0.82,
      "score_breakdown": {
        "category": "beats",
        "overall_score": 0.82,
        "passed_thresholds": true,
        "threshold_failures": [],
        "skipped_as_duplicate": false,
        "duplicate_of": null,
        "criteria": [
          {
            "name": "density",
            "label": "Mark density — timing marks per second of audio",
            "measured_value": 2.1,
            "target_min": 1.0,
            "target_max": 4.0,
            "weight": 0.25,
            "score": 1.0,
            "contribution": 0.25
          }
        ]
      }
    }
  ]
}
```
