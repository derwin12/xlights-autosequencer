# Threshold and Parameter Reference

All tunable parameters used in the Song Timeline Analysis pipeline, collected in one place for calibration and experimentation.

## Phase 1: Feature Extraction Parameters

| Parameter | Value | Where Used | Rationale |
|-----------|-------|------------|-----------|
| Sample rate | 22050 Hz | Audio loading | Half of 44.1kHz, sufficient for music analysis up to ~11kHz |
| hop_length | 512 samples (~23ms) | All frame-based features | Standard compromise between time resolution and compute |
| n_mfcc | 13 | MFCC extraction | First 13 capture musical timbre; beyond 13 is speaker identity |
| Smooth window | 2.0 seconds | Energy smoothing | Removes per-beat fluctuation, reveals section-level dynamics |
| Key window | 4.0 seconds | Key estimation | Long enough for stable pitch class distribution |
| Key step | 2.0 seconds (50% overlap) | Key estimation | Catches transitions between windows |

## Phase 2: Section Detection Parameters

| Parameter | Value | Where Used | Rationale |
|-----------|-------|------------|-----------|
| Beat-sync aggregation | median | Beat-synchronous features | Robust to outlier transients within a beat |
| Recurrence metric | cosine | Self-similarity matrix | Scale-invariant — loud and quiet versions of the same section match |
| Recurrence mode | affinity (Gaussian kernel) | Self-similarity matrix | Soft similarity gives smoother novelty curves than hard thresholds |
| Checkerboard kernel size | 8 beats | Novelty detection | ~3.5s context at 136 BPM; catches section changes, ignores momentary shifts |
| Novelty threshold | 1.5 * median(positive novelty) | Peak picking | Adaptive to song complexity; songs with clear structure have higher novelty peaks |
| Minimum section distance | 8 beats | Peak picking | Prevents micro-sections from fills or brief texture changes |

### How to tune section detection

**Too many sections?** Increase kernel size (try 12-16) and/or increase novelty threshold multiplier (try 2.0-2.5). Larger kernels need longer consistency to trigger a boundary.

**Too few sections?** Decrease kernel size (try 4-6) and/or decrease threshold multiplier (try 1.0-1.2). Also consider adding energy-based novelty as a second signal.

**Missing repetition-based boundaries?** The current approach uses only the diagonal of the recurrence matrix. For songs where sections repeat (ABAB), using off-diagonal structure (spectral clustering on the Laplacian of R) can identify repeated sections even when the checkerboard detector misses a boundary.

## Phase 3: Event Detection Thresholds

### Energy Surges/Drops
| Parameter | Value | Effect of Increase | Effect of Decrease |
|-----------|-------|-------|-------|
| Percentile threshold | 97th | Fewer, more extreme events | More events, includes moderate changes |
| Input signal | rms_smooth (2s) | N/A — this is the signal, not a parameter | N/A |

### Tempo Changes
| Parameter | Value | Effect of Increase | Effect of Decrease |
|-----------|-------|-------|-------|
| Percentile threshold | 95th | Fewer tempo change events | More events, includes minor fluctuations |

### Brightness Spikes
| Parameter | Value | Effect of Increase | Effect of Decrease |
|-----------|-------|-------|-------|
| Z-score threshold | 2.5 sigma | Fewer, only extreme brightness events | More events, catches subtle brightness shifts |
| Minimum peak distance | 0.5 seconds | Fewer closely-spaced spikes | Catches rapid successive brightness events |

### Percussive Impacts
| Parameter | Value | Effect of Increase | Effect of Decrease |
|-----------|-------|-------|-------|
| Percentile threshold | 98th | Only the hardest 2% of hits | More hits, includes normal beat pulses |
| Cluster window | 150ms | Merges hits further apart | Tighter clustering, may split double-hits |

### Silence Detection
| Parameter | Value | Effect of Increase | Effect of Decrease |
|-----------|-------|-------|-------|
| Threshold multiplier | 2x the 5th percentile of RMS | Higher floor = fewer silence events | Lower floor = catches quieter passages |
| Minimum duration | 300ms | Only catches longer pauses | Catches brief note gaps (usually not intentional pauses) |

### Texture Shifts
| Parameter | Value | Effect of Increase | Effect of Decrease |
|-----------|-------|-------|-------|
| Percentile threshold | 97th | Only the most extreme texture changes | More events, catches gradual transitions |

## Phase 5: Deduplication Parameters

| Parameter | Value | Effect of Increase | Effect of Decrease |
|-----------|-------|-------|-------|
| Same-type merge window | 1.0 second | More aggressive merging, fewer events | Tighter — may keep duplicates |
| Top-N selection spacing | 3.0 seconds | Events more spread across song | Allows clustering of top events |

## Universal Design Principles

### Why percentile-based thresholds?

Every threshold in this pipeline is **relative to the song's own distribution**, not absolute. This means:

- A quiet classical piece with -40dB peaks will still detect energy surges at its own scale
- A loud rock song with -3dB peaks will detect the same relative changes
- No manual calibration needed per song

The specific percentile values (95th, 97th, 98th) were chosen to produce approximately these event counts for a typical 4-5 minute song:

| Event Type | Target Count | Percentile Used |
|-----------|-------------|-----------------|
| Energy surges | 15-30 | 97th |
| Energy drops | 15-30 | 97th |
| Tempo changes | 10-25 | 95th |
| Brightness spikes | 10-20 | 2.5 sigma |
| Percussive impacts | 30-60 | 98th |
| Silences | 5-15 | 5th percentile * 2 |
| Texture shifts | 10-20 | 97th |

### Tempo-adaptive parameters

The current implementation uses fixed frame/beat counts. Some parameters should ideally scale with tempo:

| Parameter | Current (fixed) | Better (tempo-adaptive) |
|-----------|----------------|------------------------|
| Checkerboard kernel | 8 beats | 2 bars (8 beats at 4/4, 6 at 3/4) |
| Min section distance | 8 beats | 2 bars |
| Cluster window | 150ms | 1/3 of beat interval |
| Brightness peak distance | 0.5s | 1 beat interval |
| Smooth window | 2.0s | 4 beats |

This would make the analysis more robust across different tempos and time signatures. Implementation: compute `beat_interval = 60 / global_tempo` and use it as a scaling factor.

## Recommended Experiments for New Songs

When calibrating for a different genre or style:

1. **Run with defaults** and inspect the output
2. **Count dramatic moments per section** — if any section has > 5 events/second, the thresholds are too sensitive
3. **Check silence detection** — if vocal gaps are detected as silence, increase the minimum duration to 500ms
4. **Check section boundaries** — if short intros/outros are merged with the first/last real section, decrease the kernel size
5. **Check percussive impacts** — if every beat is flagged, increase the percentile to 99th; if only a few hits are found, decrease to 95th

The pipeline is designed for **orchestral/arranged music** where dynamics, tempo changes, and textural variety are the primary dramatic drivers. For **electronic/pop music**, the energy-based detectors will be most useful and the tempo/texture detectors less so (since tempo and texture tend to be more constant).
