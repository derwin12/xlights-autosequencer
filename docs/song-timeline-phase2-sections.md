# Phase 2: Section Detection

Finds **structural boundaries** in the song — where sections begin and end. A "section" is a contiguous region where the musical texture stays relatively consistent (same instrumentation, same energy level, same rhythmic pattern).

## Input

From Phase 1:
- `mfcc[13, T]` — timbre features at every frame
- `beat_frames[]` — frame indices of detected beats

## Algorithm: Beat-Synchronous Self-Similarity with Checkerboard Novelty

This is a 4-step process:

### Step 1: Beat-Synchronous Feature Aggregation

**Problem**: Raw MFCC frames are at ~43fps — far too noisy for structural analysis. Individual frames fluctuate with every note.

**Solution**: Average (median) features within each beat interval. This gives one feature vector per beat, which is the natural time scale for musical structure.

```
BEAT_SYNC(mfcc, beat_frames):
    For each beat i:
        start_frame = beat_frames[i]
        end_frame = beat_frames[i+1]  (or last frame)
        mfcc_sync[:, i] = median(mfcc[:, start_frame:end_frame], axis=time)

    Returns: mfcc_sync[13, N_beats]
```

**Why median instead of mean?** Median is robust to outliers. A single loud transient within a beat won't skew the feature vector.

### Step 2: Recurrence (Self-Similarity) Matrix

**Purpose**: Compute how similar every beat is to every other beat. This reveals the repetition structure of the song — verse1 beats will be similar to verse2 beats, chorus1 to chorus2, etc.

```
RECURRENCE_MATRIX(mfcc_sync):
    R[i, j] = affinity(mfcc_sync[:, i], mfcc_sync[:, j])

    Where affinity is based on cosine distance:
        cos_dist(a, b) = 1 - dot(a, b) / (|a| * |b|)
        affinity = exp(-cos_dist / sigma)  (Gaussian kernel)

    Returns: R[N_beats, N_beats]  (symmetric, values 0-1)
```

**What the matrix looks like**: A block-diagonal structure. Beats within the same section are similar to each other (bright blocks along the diagonal). Beats in repeated sections are similar across sections (bright off-diagonal blocks).

```
    Verse1   Chorus1   Verse2   Chorus2
V1 [#####    ..        ####     ..      ]
C1 [..       #####     ..       #####   ]
V2 [####     ..        #####    ..      ]
C2 [..       #####     ..       #####   ]
```

### Step 3: Checkerboard Kernel Novelty Detection

**Purpose**: Find the boundaries between blocks — these are the section boundaries.

**Key insight**: At a section boundary, the recurrence matrix transitions from one block to another. A checkerboard pattern detector finds exactly these transitions.

```
CHECKERBOARD_NOVELTY(R, kernel_size=8):
    1. Build checkerboard kernel K of size (2*kernel_size+1)^2:
       K = [+1  -1]    (quadrant pattern)
           [-1  +1]

       Specifically:
       - Top-left and bottom-right quadrants = +1
       - Top-right and bottom-left quadrants = -1

    2. Slide kernel along the diagonal of R:
       For each beat position i:
           patch = R[i-k:i+k+1, i-k:i+k+1]
           novelty[i] = sum(patch * K)

    3. Rectify: novelty = max(novelty, 0)
       (we only care about boundaries, not anti-boundaries)

    Returns: novelty[N_beats]
```

**Why a checkerboard?** At a section boundary, the recurrence matrix looks like:
```
    [same  diff]
    [diff  same]
```
The checkerboard kernel has exactly this pattern (+1 where "same", -1 where "diff"), so the dot product is maximized at boundaries.

**Kernel size = 8 beats**: This means the detector looks at ~8 beats on each side of the candidate boundary. At 136 BPM, 8 beats ≈ 3.5 seconds — enough to establish a stable texture, short enough to catch rapid section changes.

### Step 4: Peak Picking for Boundaries

```
FIND_BOUNDARIES(novelty, beat_times):
    1. Compute threshold = 1.5 * median(novelty[novelty > 0])
       (adaptive to the song's novelty range)
    2. Find peaks above threshold with minimum distance of 8 beats
       (~3.5 seconds minimum section length)
    3. Map peak indices back to timestamps via beat_times

    Returns: section_boundary_times[]
```

**Minimum distance = 8 beats** prevents detecting "micro-sections" from momentary texture changes (e.g., a single drum fill shouldn't create a section boundary).

## Output

- `section_boundary_times[]` — array of timestamps where sections change
- Combined with song start (0.0) and end (duration) to create complete section intervals

## Limitations and Improvements

**Current limitations**:
- Fixed kernel size doesn't adapt to tempo (fast songs should use more beats per kernel)
- MFCCs capture timbre but not rhythm pattern changes — two sections with the same instruments but different rhythms may not be detected as separate
- No hierarchical section detection (intro/verse/chorus labels)

**Potential improvements**:
- Use a multi-scale approach: run multiple kernel sizes and combine novelty curves
- Add spectral contrast or rhythmic pattern features alongside MFCCs
- Use the Laplacian of the recurrence matrix for spectral clustering (gives hierarchical sections)
- Incorporate energy-based novelty: compute an energy novelty curve separately and combine with the timbral novelty curve
- Apply a Hidden Markov Model to assign section labels (A, B, A, B, C, ...) based on recurrence structure
