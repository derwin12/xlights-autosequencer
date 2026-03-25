# CLI Contract: `sweep-matrix` and `sweep-results` Subcommands

**Branch**: `015-sweep-matrix` | **Date**: 2026-03-24

---

## `sweep-matrix` Command

```
xlight-analyze sweep-matrix <AUDIO_FILE> [OPTIONS]
```

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `AUDIO_FILE` | Path | Yes | Path to the input audio file (MP3 or WAV) |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--algorithms` | string | all | Comma-separated algorithm names to sweep |
| `--stems` | string | affinity | Comma-separated stem names (overrides affinity defaults) |
| `--max-permutations` | int | 500 | Safety cap; warn if matrix exceeds this count |
| `--dry-run` | flag | off | Show the full matrix without executing |
| `--config` | path | None | TOML configuration file |
| `--output-dir` | path | auto | Output directory for results |
| `--sample-start` | int | auto | Override segment start (milliseconds) |
| `--sample-duration` | int | 30000 | Sample segment duration (milliseconds) |
| `--yes` | flag | off | Skip confirmation prompts |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing file, plugin failure, etc.) |
| 2 | Invalid arguments or config |
| 130 | User cancelled (Ctrl-C or declined confirmation) |

### Output

- Unified sweep report: `<output_dir>/sweep_report.json`
- Per-algorithm files: `<output_dir>/sweep_<algorithm>.json`
- Winners (if auto-export confirmed): `<output_dir>/winners/<algo>_<stem>.xtiming` or `.xvc`

---

## `sweep-results` Command

```
xlight-analyze sweep-results <SWEEP_REPORT> [OPTIONS]
```

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `SWEEP_REPORT` | Path | Yes | Path to sweep_report.json |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--algorithm` | string | None | Filter by algorithm name |
| `--stem` | string | None | Filter by stem name |
| `--best` | flag | off | Show only best result per algorithm |
| `--top` | int | None | Show only top N results globally |
| `--type` | choice | all | Filter by result type: `timing`, `value`, or `all` |
| `--export` | flag | off | Export the displayed results as .xtiming/.xvc files |

### Output Table Columns

```
RANK  SCORE  TYPE    ALGORITHM              STEM       MARKS  AVG INT  PARAMETERS
  1   0.92   timing  qm_beats               drums        87   690ms   inputtempo=120, constraintempo=1
  2   0.89   timing  aubio_onset            drums       142   423ms   threshold=0.3
  3   0.87   curve   bbc_energy             full_mix      –     –     (none)
  ...
```
