# Quickstart: Comprehensive Stem×Parameter Sweep Matrix

**Branch**: `015-sweep-matrix` | **Date**: 2026-03-24

## Prerequisites

- Stems separated: `xlight-analyze wizard song.mp3` (with stems enabled)
- Vamp plugins installed in `~/Library/Audio/Plug-Ins/Vamp/`

## Run a Full Sweep

```bash
# Full matrix sweep — all algorithms, all affinity stems, 30s sample segment
xlight-analyze sweep-matrix song.mp3

# Preview the matrix without running (see permutation count)
xlight-analyze sweep-matrix song.mp3 --dry-run

# Filter to specific algorithms
xlight-analyze sweep-matrix song.mp3 --algorithms qm_beats,aubio_onset,bbc_energy

# Filter to specific stems
xlight-analyze sweep-matrix song.mp3 --stems drums,bass,vocals

# Use a custom TOML config
xlight-analyze sweep-matrix song.mp3 --config my_sweep.toml
```

## View Results

```bash
# Show all results ranked by quality score
xlight-analyze sweep-results analysis/sweep/sweep_report.json

# Show only the best result per algorithm
xlight-analyze sweep-results analysis/sweep/sweep_report.json --best

# Filter by algorithm or stem
xlight-analyze sweep-results analysis/sweep/sweep_report.json --algorithm qm_beats
xlight-analyze sweep-results analysis/sweep/sweep_report.json --stem drums

# Show top 10 globally
xlight-analyze sweep-results analysis/sweep/sweep_report.json --top 10

# Show only value curves
xlight-analyze sweep-results analysis/sweep/sweep_report.json --type value

# Export the best results as .xtiming/.xvc files
xlight-analyze sweep-results analysis/sweep/sweep_report.json --best --export
```

## Review UI

```bash
# Open review UI — navigate to "Sweep Results" tab
xlight-analyze review song_analysis.json
```

In the Sweep Results view:
- Click column headers to sort
- Type in the filter box to narrow results
- Check two results and click "Compare" to overlay them on the timeline

## TOML Configuration

Create `sweep.toml`:

```toml
algorithms = ["qm_beats", "qm_onsets_complex", "aubio_onset", "bbc_energy"]
stems = ["drums", "bass", "full_mix"]
max_permutations = 200
sample_duration_s = 30

[params.qm_beats]
inputtempo = [100, 120, 140, 160]
constraintempo = [0, 1]

[params.qm_onsets_complex]
sensitivity = [20, 40, 60, 80]
```

Run: `xlight-analyze sweep-matrix song.mp3 --config sweep.toml`

## Output Files

```
analysis/sweep/
├── sweep_report.json           # Unified results (metadata only, fast to load)
├── sweep_qm_beats.json         # Full data for qm_beats (all stems×params)
├── sweep_aubio_onset.json      # Full data for aubio_onset
├── sweep_bbc_energy.json       # Full data for bbc_energy (value curves)
├── ...
└── winners/
    ├── qm_beats_drums.xtiming  # Best beat track → xLights timing import
    ├── bbc_energy_full_mix.xvc # Best energy curve → xLights value curve
    └── ...
```
