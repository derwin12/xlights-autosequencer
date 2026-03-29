# Cross-Song Parameter Tuning Guide

## Overview

The parameter tuning framework finds optimal default values for algorithm
parameters by sweeping across multiple songs and aggregating results. Parameters
are tested in prioritized batches so that the most impactful parameters are
locked in first, creating a stable foundation for subsequent batches.

## Quick Start

```bash
# Run full tuning across songs (all 4 batches, sequential)
xlight-analyze tune song1.mp3 song2.mp3 song3.mp3

# Run only batch 1 (onset detection)
xlight-analyze tune *.mp3 --batch 1

# Resume from a previous session
xlight-analyze tune *.mp3 --resume tuning_results/tuning_session.json

# Check tuning status
xlight-analyze tune-status tuning_results/tuning_session.json

# Review what optimal defaults would change
xlight-analyze tune-apply tuning_results/optimal_defaults.json --dry-run
```

## Parameter Batches

Parameters are grouped into 4 batches, ordered from most to least impactful:

### Batch 1: Onset Detection (Highest Priority)

These control how sensitively onset detectors fire. They affect 6 algorithms
(3 QM onset detectors + Aubio onset) which are the most widely-used timing
track producers for xLights sequencing.

| Parameter   | Algorithms                                         | Range       | Default | Description                           |
|-------------|---------------------------------------------------|-------------|---------|---------------------------------------|
| sensitivity | qm_onsets_complex, qm_onsets_hfc, qm_onsets_phase | 0-100       | 50      | QM onset detector sensitivity         |
| threshold   | aubio_onset                                        | 0.0-1.0     | 0.3     | Aubio onset threshold (lower=more)    |
| silence     | aubio_onset                                        | -90 to -20  | -70 dB  | Silence gate threshold                |

**Why first?** Onset detection drives most per-beat effects in light shows.
Getting clean, well-timed onsets is the foundation everything else builds on.

### Batch 2: Beat & Tempo

Controls tempo estimation and inter-onset spacing for beat/bar trackers.

| Parameter      | Algorithms          | Range     | Default | Description                      |
|---------------|---------------------|-----------|---------|----------------------------------|
| inputtempo    | qm_beats, qm_bars   | 60-180    | 120 BPM | Tempo hint for QM trackers       |
| constraintempo| qm_beats, qm_bars   | 0 or 1    | 0       | Force use of inputtempo hint     |
| minioi        | aubio_onset          | 0.0-0.1   | 0.02 s  | Min inter-onset interval         |

**Why second?** Beat tracking quality determines bar grouping accuracy, which
affects section-level effects and choreography alignment.

### Batch 3: Pitch & Melody

Controls pitch detection for vocal/melodic tracks and amplitude envelope.

| Parameter      | Algorithms                        | Range   | Default | Description                     |
|---------------|----------------------------------|---------|---------|--------------------------------|
| threshdistr   | pyin_notes, pyin_pitch_changes    | 0-7     | 2       | Pitch threshold distribution    |
| outputunvoiced| pyin_notes, pyin_pitch_changes    | 0-2     | 0       | Unvoiced frame handling         |
| attack        | amplitude_follower                | 0.001-0.5| 0.01 s | Envelope attack time            |

### Batch 4: Envelope & Percussion

Fine-tunes amplitude envelope and percussion onset detection.

| Parameter       | Algorithms          | Range   | Default | Description                    |
|----------------|---------------------|---------|---------|-------------------------------|
| release        | amplitude_follower   | 0.001-0.5| 0.01 s | Envelope release time          |
| threshold      | percussion_onsets    | 0.0-1.0 | 0.5     | Percussion detection threshold |
| sensitivity    | percussion_onsets    | 0-100   | 50      | Percussion sensitivity         |

## How It Works

### 1. Per-Song Sweeping

For each song, the tuner:
- Loads a 30-second sample (configurable offset/duration)
- Loads available stems (drums, bass, vocals, etc.)
- For each parameter in the batch, tests all sweep values
- Scores each result using the quality scoring system
- Records quality_score, mark_count, and avg_interval_ms

### 2. Cross-Song Aggregation

For each parameter:
- **Per-song optimal**: Find the value that maximizes mean quality across
  algorithms for that song
- **Cross-song vote**: Each song "votes" for its best value; the value with
  the highest composite score (vote_fraction * mean_score) wins
- **Agreement score**: Fraction of songs that agree on the optimal value
  (1.0 = unanimous, 0.5 = half agree)

### 3. Locking

After each batch, parameters with positive improvement or agreement >= 50%
are "locked in" and used as fixed values for subsequent batches. This ensures
later batches are tuned in the context of already-optimized earlier parameters.

### 4. Final Output

The framework produces:
- `tuning_session.json` - Full session state (resumable)
- `batch_N_<name>.json` - Per-batch detailed reports
- `optimal_defaults.json` - Final recommended defaults

## Interpreting Results

### Agreement Score

| Score     | Meaning                                          |
|-----------|--------------------------------------------------|
| >= 0.8    | Strong consensus - songs agree, confident result |
| 0.5 - 0.8| Moderate - most songs agree, reasonable default  |
| < 0.5    | Low - songs need different values, genre-specific|

### Improvement Percentage

| Range    | Meaning                                            |
|----------|----------------------------------------------------|
| > 5%     | Significant improvement, strongly recommend change |
| 1-5%     | Marginal improvement, consider changing             |
| ~0%      | Default is already optimal                          |
| < 0%     | Default is better than tested alternatives          |

## Tuning Notes Template

Use this template to document tuning runs for future reference:

```
## Tuning Run: [DATE]

### Songs Tested
1. [Song name] - [Genre] - [BPM] - [Duration]
2. ...

### Environment
- Stems available: [yes/no, which model]
- Sample: [offset]s + [duration]s
- Hardware: [CPU/RAM for timing reference]

### Batch 1 Results (Onset Detection)
- sensitivity: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- threshold: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- silence: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]

### Batch 2 Results (Beat & Tempo)
- inputtempo: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- constraintempo: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- minioi: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]

### Batch 3 Results (Pitch & Melody)
- threshdistr: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- outputunvoiced: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- attack: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]

### Batch 4 Results (Envelope & Percussion)
- release: [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- threshold (perc): [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]
- sensitivity (perc): [default] -> [optimal] ([improvement]%, [agreement])
  - Notes: [observations]

### Key Observations
- [What patterns emerged across songs?]
- [Were there genre-specific differences?]
- [Did any parameters show no impact?]

### Recommended Defaults
[Copy from optimal_defaults.json or tune-apply output]

### Open Questions
- [Parameters that need more testing?]
- [Genre-specific profiles to create?]
```

## Song Selection Guidelines

For reliable cross-song tuning, select songs that:

1. **Cover genre diversity** - Include rock, pop, electronic, orchestral if
   your show mixes genres
2. **Vary in tempo** - Slow ballads (70-90 BPM), mid-tempo (100-130 BPM),
   and fast tracks (140+ BPM)
3. **Differ in instrumentation** - Some drum-heavy, some vocal-focused,
   some with prominent bass
4. **Represent your actual show** - Use the songs you'll actually sequence

Minimum: 3 songs. Recommended: 5-8 songs for robust results.

## Advanced Usage

### Custom Sample Windows

Different parts of a song may give different results:

```bash
# Sample from the chorus (60s in, 30s long)
xlight-analyze tune *.mp3 --sample-start 60 --sample-duration 30

# Sample from the intro (start, 20s)
xlight-analyze tune *.mp3 --sample-start 0 --sample-duration 20
```

### Per-Batch Tuning with Manual Review

For careful tuning, run one batch at a time and review before proceeding:

```bash
# Run batch 1
xlight-analyze tune *.mp3 --batch 1

# Review results
xlight-analyze tune-status tuning_results/tuning_session.json

# If satisfied, continue with batch 2
xlight-analyze tune *.mp3 --batch 2 --resume tuning_results/tuning_session.json
```

### Applying Results

After tuning:

```bash
# See what would change
xlight-analyze tune-apply tuning_results/optimal_defaults.json --dry-run

# The output shows per-algorithm parameter updates
# Apply by updating algorithm defaults in code or via sweep configs
```
