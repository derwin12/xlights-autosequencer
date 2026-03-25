# Research: Comprehensive Stem×Parameter Sweep Matrix

**Branch**: `015-sweep-matrix` | **Date**: 2026-03-24

## R1: New Vamp Algorithm Integration

**Decision**: Add 13 new algorithm wrappers for installed Vamp plugins that are not currently used.

**Rationale**: Testing all 122 installed plugins revealed 13 that produce xLights-relevant output (timing events, energy curves, segmentation, key detection). These cover capabilities the current 22 algorithms miss: percussion-specific onset detection, structural segmentation (Segmentino), key detection, polyphonic transcription, energy/spectral envelopes, and tempo variation curves.

**New algorithms to add**:

| Algorithm Name | Plugin Key | Output Type | Produces |
|---------------|------------|-------------|----------|
| aubio_onset | vamp-aubio:aubioonset | timing | Onset events (5 detection methods) |
| aubio_tempo | vamp-aubio:aubiotempo | timing | Beat positions |
| aubio_notes | vamp-aubio:aubionotes | timing | Note events (onset+pitch+duration) |
| percussion_onsets | vamp-example-plugins:percussiononsets | timing | Percussion-specific onsets |
| segmentino | segmentino:segmentino | timing | Structural segmentation (verse/chorus grouping) |
| qm_key | qm-vamp-plugins:qm-keydetector | timing | Key detection (key change events) |
| qm_transcription | qm-vamp-plugins:qm-transcription | timing | Polyphonic note transcription |
| silvet_notes | silvet:silvet | timing | Polyphonic transcription with velocity |
| bbc_energy | bbc-vamp-plugins:bbc-energy | value_curve | RMS energy envelope |
| bbc_spectral_flux | bbc-vamp-plugins:bbc-spectral-flux | value_curve | Spectral change rate |
| bbc_peaks | bbc-vamp-plugins:bbc-peaks | value_curve | Amplitude peak/trough detection |
| bbc_rhythm | bbc-vamp-plugins:bbc-rhythm | timing | Rhythmic feature events |
| amplitude_follower | vamp-example-plugins:amplitudefollower | value_curve | Continuous amplitude envelope |

**Alternatives considered**:
- ua-vamp-plugins:onsetsua — rejected: fires every 46ms, not musical onsets
- expressive-means:onsets — rejected: fires every 6ms, frame-level not event-level
- mvamp:marsyas_ibt — rejected: crashes (segfault)
- qm-tonalchange — rejected: errors on collect
- vamp-libxtract (47 plugins) — rejected: too low-level (raw spectral features)

## R2: Representative Segment Selection Strategy

**Decision**: Use librosa's RMS energy to find the highest-energy 30-second window, avoiding the first and last 10% of the song.

**Rationale**: The sweep needs a segment that contains the musical content most representative of the song's primary character — typically a chorus or energetic verse. Intros, outros, and fade-outs produce unrepresentative results. RMS energy is a reliable proxy for "musically active" content and is fast to compute (~50ms for a 4-minute song).

**Algorithm**:
1. Compute RMS energy with hop_length=2048 (~46ms frames)
2. Exclude first/last 10% of frames (avoid intro/outro)
3. Apply a rolling mean over 30-second windows
4. Select the window with the highest mean energy
5. Return start_ms and end_ms of the selected segment

**Alternatives considered**:
- Fixed position (20% in) — rejected: doesn't adapt to song structure
- Use song structure segments from Genius/segmentino — considered but adds a dependency; energy is simpler and always available
- User-specified only — rejected: default should work without manual input

## R3: Value Curve Scoring Strategy

**Decision**: Score value curves by dynamic range and temporal variation. A good value curve for xLights has high dynamic range (uses the full 0-100 range) and varies meaningfully over time (not flat, not random noise).

**Rationale**: Timing tracks are scored by mark density, regularity, and alignment with detected beats. Value curves need a different scoring approach since they have no discrete marks. The key quality indicators for xLights use are: (a) sufficient dynamic range to drive visible light changes, (b) temporal structure that correlates with musical events rather than noise.

**Metrics**:
- Dynamic range: `max - min` of normalized values (target: ≥60 of the 0-100 range)
- Temporal autocorrelation at musical frame rate: high = structured, low = noise
- Combined score: `0.5 * range_score + 0.5 * structure_score`

**Alternatives considered**:
- Reuse timing track scorer — rejected: fundamentally different data shape
- No scoring (just show all curves) — rejected: user needs ranking to find useful curves

## R4: Stem Affinity Design

**Decision**: Maintain a documented affinity table mapping each algorithm to its preferred stems, with audio engineering rationale per entry. The table is used as the default sweep scope but is overridable.

**Rationale**: Not all algorithm×stem combinations are meaningful. Running a key detector on the drums stem produces noise. Running a beat tracker on the vocals stem is usually wrong. Affinity lists encode domain knowledge to focus compute on productive combinations.

**Document structure**: A markdown file (`stem-affinity-rationale.md`) with a table of all ~35 algorithms, their affinity stems, and a one-line rationale for each.

## R5: Parallel Sweep Execution

**Decision**: Use `concurrent.futures.ThreadPoolExecutor` for local (librosa) algorithms and spawn separate subprocesses per permutation for vamp/madmom algorithms. Max workers = `min(cpu_count, 4)` by default.

**Rationale**: The existing ParallelRunner from feature 014 uses ThreadPoolExecutor for local algorithms. The sweep can reuse this pattern. Vamp/madmom already run in subprocesses for ABI isolation — the sweep spawns one subprocess per permutation (each with its own stdin/stdout) to avoid conflicts.

**Alternatives considered**:
- ProcessPoolExecutor — rejected: vamp subprocess isolation already provides process-level parallelism; adding another layer of processes would complicate resource management
- asyncio — rejected: CPU-bound audio processing doesn't benefit from async IO

## R6: TOML Sweep Configuration Format

**Decision**: Follow the existing scoring config TOML conventions. Top-level keys: `algorithms`, `stems`, `max_permutations`, `sample_duration_s`. Per-algorithm parameter overrides under `[params.<algorithm_name>]`.

**Example**:
```toml
algorithms = ["qm_beats", "qm_onsets_complex", "aubio_onset"]
stems = ["drums", "bass", "full_mix"]
max_permutations = 200
sample_duration_s = 30

[params.qm_beats]
inputtempo = [100, 120, 140, 160]
constraintempo = [0, 1]

[params.qm_onsets_complex]
sensitivity = [20, 40, 60, 80]
```

**Alternatives considered**:
- JSON config — rejected: TOML is more readable and already used in the project for scoring configs
- YAML — rejected: not used elsewhere in the project; TOML is simpler for flat key-value structures
