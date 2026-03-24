# CLI Contract: `wizard` Subcommand

**Branch**: `014-cli-wizard-pipeline` | **Date**: 2026-03-24

---

## Command Signature

```
xlight-analyze wizard <AUDIO_FILE> [OPTIONS]
```

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `AUDIO_FILE` | Path | Yes | Path to the input audio file (MP3 or MP4) |

### Options (flag parity with wizard selections)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--use-cache` | flag | off | Use existing cache without prompting (skip wizard if valid cache found) |
| `--no-cache` | flag | off | Run fresh analysis, do not read or write cache |
| `--skip-cache-write` | flag | off | Run fresh analysis but do not persist result to cache |
| `--algorithms` | string | "all" | Comma-separated algorithm names or "all" |
| `--no-vamp` | flag | off | Exclude vamp algorithms |
| `--no-madmom` | flag | off | Exclude madmom algorithms |
| `--stems / --no-stems` | flag | --stems | Enable/disable stem separation |
| `--phonemes / --no-phonemes` | flag | --phonemes | Enable/disable phoneme analysis |
| `--phoneme-model` | choice | "base" | Whisper model: tiny, base, small, medium, large-v2 |
| `--structure / --no-structure` | flag | --structure | Enable/disable song structure detection |
| `--genius / --no-genius` | flag | off | Enable/disable Genius lyrics fetch |
| `--output` | path | auto | Output JSON path (default: `<song_dir>/<stem>_analysis.json`) |
| `--non-interactive` | flag | auto | Force non-interactive mode (auto-detected from TTY) |
| `--scoring-config` | path | None | Custom TOML scoring configuration |
| `--scoring-profile` | string | None | Named scoring profile from `~/.xlight/scoring/` |

### Behavior

**Interactive mode** (default when stdin is a TTY):
1. Launch wizard prompt sequence
2. Each wizard step can be pre-filled by the corresponding flag (step is shown but pre-selected)
3. User navigates with arrow keys, confirms with Enter
4. Esc or Ctrl-C at any step cancels cleanly (exit code 130)
5. After confirmation, analysis runs with live multi-track progress display

**Non-interactive mode** (stdin is not a TTY, or `--non-interactive`):
1. Print notice: "Non-interactive mode: using defaults. Use --help for flag options."
2. Apply flag values (or defaults for unspecified flags)
3. Run analysis with standard line-by-line progress output
4. Equivalent to `xlight-analyze analyze` with the same flags (except `wizard` always uses the parallel pipeline)

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Analysis error (algorithm failure, file not found, etc.) |
| 2 | Invalid arguments |
| 130 | User cancelled (Ctrl-C or Esc) |

### Output

Same as existing `analyze` command: JSON analysis result file written to `--output` path (or auto-generated path). The result JSON gains an optional `pipeline_stats` object with execution timing data.

---

## Progress Callback Contract (Internal)

The parallelized runner emits progress events with this signature:

```
callback(step_name: str, status: str, detail: dict)
```

| Field | Type | Values |
|-------|------|--------|
| `step_name` | string | Algorithm name or pipeline phase name |
| `status` | string | "pending", "waiting", "running", "done", "failed", "skipped" |
| `detail.mark_count` | int | Timing marks produced (0 if not applicable) |
| `detail.duration_ms` | int | Step wall-clock duration (0 if still running) |
| `detail.error` | string | Error message (empty if no error) |

This replaces the existing `progress_callback(index, total, name, mark_count)` signature. The old signature is preserved as a compatibility wrapper.
