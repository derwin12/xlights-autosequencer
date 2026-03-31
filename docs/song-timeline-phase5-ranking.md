# Phase 5: Dramatic Moment Ranking

Takes the raw event list from Phase 3 (which can contain hundreds of events, many redundant) and produces a **clean, ranked list** of the most important moments in the song.

## Input

From Phase 3: `raw_events[]` — unsorted, potentially overlapping events of all types

## Step 1: Sort by Time

```
events.sort(key=time)
```

Trivial but necessary for the deduplication step.

## Step 2: Deduplicate Nearby Events of Same Type

**Problem**: A single musical event (e.g., a big drum hit) can trigger multiple detection frames. Phase 3's energy surge detector might fire on 10 consecutive frames as the smoothed energy rises. This creates 10 events where there should be 1.

**Algorithm**:
```
DEDUPLICATE(events, min_gap=1.0):
    deduped = []

    For each event in sorted events:
        if deduped is not empty
           AND last event has same type
           AND time gap < min_gap (1.0 seconds):
            # Same event detected multiple times
            # Keep the one with higher intensity
            if event.intensity > last_event.intensity:
                replace last event with this one
        else:
            append event

    Returns: deduped[]
```

**Why 1.0 second gap?** Events of the same type closer than 1 second apart are almost certainly the same musical event detected at slightly different frames. At 136 BPM, 1 second is about 2.3 beats — two separate hits more than 2 beats apart are genuinely different events.

**Important**: This only merges events of the **same type**. A percussive_impact and an energy_surge at the same timestamp are kept as separate events — they represent different aspects of the same moment, both useful for lighting decisions.

## Step 3: Intensity Normalization

Different event types have different intensity scales:
- `energy_surge/drop`: intensity relative to threshold (~1.0-3.0)
- `percussive_impact`: raw onset strength (~5-20)
- `brightness_spike`: z-score (~2.5-5.0)
- `tempo_change`: BPM difference
- `silence`: duration in seconds
- `texture_shift`: no intensity value

For cross-type ranking, we need comparable scores. The approach used in the current implementation is simple: **rank within type, then merge by time**. A future improvement would be unified scoring:

```
UNIFIED_SCORE(event):
    # Normalize each type to 0-1 scale within its distribution
    type_events = all events of this type
    percentile_rank = rank(event.intensity) / len(type_events)

    # Weight by type importance for light shows
    type_weights = {
        energy_surge: 1.0,    # Most visible in lighting
        energy_drop: 0.9,     # Dramatic but less common
        percussive_impact: 0.8,  # Frequent, drives beat-sync
        brightness_spike: 0.7,   # Subtle but useful for accents
        silence: 1.0,            # Rare and very dramatic
        tempo_change: 0.6,       # Affects speed, not brightness
        shift_to_harmonic: 0.5,  # Gradual texture change
        shift_to_percussive: 0.5,
    }

    return percentile_rank * type_weights[event.type]
```

## Step 4: Top-N Selection for Light Show Programming

For manual light show programming, a human needs the **top 10-20 moments** to program first, with the rest filled in algorithmically. The selection criteria:

```
SELECT_TOP_MOMENTS(events, n=10):
    1. Score all events (Step 3)
    2. Sort by score descending
    3. Enforce minimum temporal spacing:
       For each candidate in score order:
           if no already-selected moment within 3 seconds:
               select this moment
           until n moments selected

    Returns: top_moments[]
```

**The 3-second spacing** ensures the top moments are spread across the song rather than clustering in one chaotic passage. This gives the light programmer a skeletal timeline that covers the whole song.

## What the Ranking Reveals

For **Mad Russian Christmas**, the ranking exposed clear patterns:

### Moment Type Distribution

| Type | Count (raw) | Count (deduped) | What it means |
|------|-------------|-----------------|---------------|
| percussive_impact | ~120 | ~90 | Heavily rhythmic piece, regular strong hits |
| energy_surge | ~80 | ~25 | Many build moments, especially around section transitions |
| energy_drop | ~50 | ~20 | Equally many "pull back" moments — high dynamic range |
| shift_to_harmonic | ~40 | ~15 | Frequent texture oscillation between melodic and rhythmic |
| shift_to_percussive | ~40 | ~15 | (paired with above) |
| brightness_spike | ~15 | ~12 | Concentrated in sections with high strings/brass |
| tempo_change | ~25 | ~20 | Many tempo fluctuations — rubato classical style |
| silence | ~12 | ~12 | Concentrated in intro and breakdown — intentional pauses |

### The "Dramatic Density" Metric

One emergent insight: the **number of dramatic moments per second** in a section is itself a useful metric:

```
dramatic_density = len(section.dramatic_moments) / section.duration
```

| Section Time | Dramatic Density | Interpretation |
|-------------|-----------------|----------------|
| 2:58-3:16 | 3.8 events/sec | Chaotic cadenza — maximum lighting chaos |
| 1:14-1:18 | 12.8 events/sec | The Drop — so many simultaneous changes |
| 3:24-3:36 | 1.1 events/sec | Quiet breakdown — minimal lighting |
| 1:38-1:58 | 1.5 events/sec | Steady power — consistent but not chaotic |

Sections with very high dramatic density need special treatment — rather than trying to react to every event, the lighting should reflect the overall chaos (e.g., random rapid color shifts, maximum speed). Sections with low density should carefully track each individual event.

## Output

```python
dramatic_moments = [
    # Sorted by time, deduplicated
    {"time": 1.14, "type": "energy_surge", "intensity": 1.57, ...},
    {"time": 1.14, "type": "percussive_impact", "strength": 8.68, ...},
    {"time": 1.14, "type": "shift_to_percussive", ...},
    ...
]

top_10_moments = [
    # Sorted by importance, minimum 3s spacing
    {"time": 73.0, "rank": 1, "why": "The Drop — biggest energy transition"},
    {"time": 180.0, "rank": 2, "why": "Percussive hit 16.56 — strongest single accent"},
    {"time": 278.5, "rank": 3, "why": "Energy cliff 2.22 — steepest drop"},
    ...
]
```
