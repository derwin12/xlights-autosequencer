# CLI Contract: Configurable Quality Scoring

**Branch**: `011-quality-score-config` | **Date**: 2026-03-22

---

## Modified Commands

### `xlight-analyze analyze`

New options:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--scoring-config` | Path | None | Path to a TOML scoring configuration file |
| `--scoring-profile` | String | None | Name of a saved scoring profile |

Behavior:
- If both `--scoring-config` and `--scoring-profile` are provided, error with message: "Cannot use both --scoring-config and --scoring-profile"
- If `--scoring-config` is provided, load and validate the TOML file before running analysis
- If `--scoring-profile` is provided, search project-local `.scoring/` then `~/.config/xlight/scoring/` for `{name}.toml`
- If neither is provided, use built-in default scoring (backward-compatible)
- Invalid config → error with descriptive message, exit code 6, no analysis runs
- Score breakdowns are always computed and included in JSON output
- `--top N` now applies the diversity filter before selecting top tracks

### `xlight-analyze summary`

New options:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--breakdown` | Flag | False | Show per-criterion score breakdown for each track |

Behavior:
- Without `--breakdown`: existing summary table (unchanged)
- With `--breakdown`: after the summary table, print per-track criterion details

`--breakdown` output format:
```
Track: librosa_beats (category: beats)
  Score: 0.82 | Thresholds: PASS
  density        1.00  (2.1 marks/s, target 1.0–4.0, weight 0.25, contribution 0.25)
  regularity     0.85  (0.85, target 0.6–1.0, weight 0.25, contribution 0.21)
  mark_count     0.90  (312 marks, target 100–800, weight 0.15, contribution 0.14)
  coverage       1.00  (0.95, target 0.8–1.0, weight 0.15, contribution 0.15)
  min_gap        0.70  (0.70, target 1.0, weight 0.20, contribution 0.14)
```

When a track was skipped by the diversity filter:
```
Track: madmom_rnn_beats (category: beats)
  Score: 0.78 | SKIPPED: near-identical to librosa_beats (92% match)
```

### `xlight-analyze scoring`

New subcommand group for scoring profile management.

| Subcommand | Description |
|------------|-------------|
| `scoring list` | List all available profiles (project-local + user-global) |
| `scoring show <name>` | Display a profile's configuration with defaults highlighted |
| `scoring save <name> --from <path>` | Save a TOML config as a named profile |
| `scoring defaults` | Print the built-in default configuration as TOML to stdout |

`scoring list` output format:
```
Scoring Profiles:
  NAME            SOURCE       DESCRIPTION
  fast_edm        project      High density weight, low regularity
  ambient         user         Sparse tracks preferred
  (default)       built-in     Standard scoring weights
```

`scoring defaults` outputs a complete, commented TOML file suitable for editing:
```toml
# XLight Scoring Configuration
# Copy this file and modify to create a custom scoring profile.

[weights]
# Criterion weights (all >= 0, must not all be zero)
density = 0.25       # Mark density — marks per second
regularity = 0.25    # Regularity — consistency of inter-mark intervals
mark_count = 0.15    # Mark count — total number of timing marks
coverage = 0.15      # Coverage — fraction of song duration with marks
min_gap = 0.20       # Minimum gap compliance — proportion of intervals >= threshold

[thresholds]
# Optional: tracks outside these bounds are excluded from ranked output
# min_mark_count = 5
# min_coverage = 0.1
# max_density = 20.0

[diversity]
tolerance_ms = 50    # Mark alignment window for similarity comparison
threshold = 0.90     # Proportion of matching marks to consider tracks near-identical

[min_gap]
threshold_ms = 25    # Minimum actionable gap (hardware constraint)

# Category target ranges — override only what you need
# [categories.beats]
# density_min = 1.0
# density_max = 4.0
# regularity_min = 0.6
# regularity_max = 1.0
# mark_count_min = 100
# mark_count_max = 800
# coverage_min = 0.8
# coverage_max = 1.0
```

---

## Exit Codes

| Code | Condition |
|------|-----------|
| 6 | Invalid scoring configuration (bad TOML, unknown criterion, invalid weights) |
| 7 | Scoring profile not found |

---

## JSON Schema Changes

The `score_breakdown` field is added to each track object in the analysis JSON. See `data-model.md` for the full schema. This is a backward-compatible addition — existing JSON files without `score_breakdown` load without error.
