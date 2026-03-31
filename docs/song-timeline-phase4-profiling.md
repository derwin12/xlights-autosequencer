# Phase 4: Section Profiling

Takes the section boundaries from Phase 2 and the features from Phase 1, and computes a **complete profile** for each section. Each profile is a structured summary that tells the sequence generator what kind of lighting this section needs.

## Input

From Phase 1: All feature arrays (RMS, spectral, HPSS, chroma, bands, beats, onsets)
From Phase 2: `section_boundary_times[]`
From Phase 3: `dramatic_moments[]`

## Algorithm

```
PROFILE_SECTIONS(boundaries, features, dramatic_moments):
    # Create intervals from boundaries + song start/end
    intervals = zip([0] + boundaries, boundaries + [duration])

    For each interval (start, end):
        # Compute frame range for this section
        start_frame = time_to_frames(start)
        end_frame = time_to_frames(end)

        profile = {
            energy:    PROFILE_ENERGY(rms, start_frame, end_frame),
            spectral:  PROFILE_SPECTRAL(centroid, bandwidth, rolloff, flatness, start_frame, end_frame),
            texture:   PROFILE_TEXTURE(rms_harmonic, rms_percussive, start_frame, end_frame),
            rhythm:    PROFILE_RHYTHM(beat_times, onset_times, start, end),
            harmony:   PROFILE_HARMONY(chroma, start_frame, end_frame),
            bands:     PROFILE_BANDS(band_energies, rms, start_frame, end_frame),
            tempo:     PROFILE_TEMPO(beat_times, start, end),
            dramatic:  FILTER_MOMENTS(dramatic_moments, start, end),
        }

    Returns: sections[]
```

## Sub-Algorithms

### 4A. Energy Profiling

```
PROFILE_ENERGY(rms, start_frame, end_frame, global_rms):
    section_rms = rms[start_frame:end_frame]

    average = mean(section_rms)
    peak = max(section_rms)
    variance = var(section_rms)  # high variance = dynamic section
    db_avg = 20 * log10(average / max(global_rms))

    # Classify relative to global distribution
    level = "high"   if average > percentile(global_rms, 75)
            "low"    if average < percentile(global_rms, 25)
            "medium" otherwise

    Returns: {average, peak, variance, db_avg, level}
```

**Energy level classification** uses global percentiles (the whole song's RMS distribution), not absolute dB. This means:
- A "high" section in a quiet acoustic song might be -20 dB
- A "high" section in a loud rock song might be -3 dB
- Both correctly trigger intense lighting relative to their song's dynamic range

**Variance** is an underrated metric: high energy variance means the section is internally dynamic (building, pulsing, call-and-response). Low variance + high average = "wall of sound" that needs sustained lighting. Low variance + low average = quiet sustained passage (ambient wash).

### 4B. Spectral Profiling

```
PROFILE_SPECTRAL(centroid, bandwidth, rolloff, flatness, start_frame, end_frame, global_centroid):
    section_centroid = centroid[start_frame:end_frame]

    brightness = "bright"  if mean(section_centroid) > percentile(global_centroid, 70)
                 "dark"    if mean(section_centroid) < percentile(global_centroid, 30)
                 "neutral" otherwise

    Returns: {
        brightness,
        centroid_mean_hz,   # absolute frequency for reference
        bandwidth_mean_hz,  # how wide the spectrum is
        rolloff_mean_hz,    # where the energy tops out
        flatness_mean,      # 0=tonal, 1=noisy
    }
```

**Mapping to light show parameters**:

| Spectral Property | Light Parameter |
|-------------------|-----------------|
| brightness=bright | Cool white / blue-white tint, higher LED brightness |
| brightness=dark | Warm amber / deep red tint, lower overall brightness |
| High bandwidth | Multiple simultaneous effects, wide color spread |
| Low bandwidth | Single focused effect, narrow color palette |
| High flatness | Noisy/chaotic effects (random twinkle, shimmer/strobe) |
| Low flatness | Clean/smooth effects (solid color wash, clean chase) |

### 4C. Texture Profiling

```
PROFILE_TEXTURE(rms_harmonic, rms_percussive, start_frame, end_frame):
    h_mean = mean(rms_harmonic[start_frame:end_frame])
    p_mean = mean(rms_percussive[start_frame:end_frame])
    ratio = h_mean / (p_mean + epsilon)

    character = "harmonic"   if ratio > 1.5
                "percussive" if ratio < 0.67
                "balanced"   otherwise

    Returns: {character, harmonic_rms, percussive_rms, hp_ratio}
```

**Mapping to effect selection**:

| Texture | Effect Types | Why |
|---------|-------------|-----|
| harmonic | Color Wash, Ripple, Wave, Spirals, Butterfly | Smooth flowing effects match sustained tones |
| percussive | Strobe, On/Off, Bars, Marquee, Single Strand | Sharp/discrete effects match transient hits |
| balanced | Chase, Fire, Meteors, Twinkle | Medium complexity, responsive to both components |

### 4D. Rhythm Profiling

```
PROFILE_RHYTHM(beat_times, onset_times, start, end):
    section_beats = beat_times where start <= t < end
    section_onsets = onset_times where start <= t < end

    beat_count = len(section_beats)
    onset_density = len(section_onsets) / (end - start)

    Returns: {beat_count, onset_density_per_sec}
```

**Onset density interpretation**:

| Density | Musical Character | Effect Speed |
|---------|------------------|--------------|
| < 1.0/sec | Very sparse, sustained notes | Slow: 1-2 second effect cycles |
| 1.0-2.5/sec | Normal melodic content | Medium: 0.5-1 second cycles |
| 2.5-4.0/sec | Busy, active passages | Fast: 0.25-0.5 second cycles |
| > 4.0/sec | Virtuosic runs, rapid-fire | Very fast: beat-synced, < 0.25s |

### 4E. Harmony Profiling

```
PROFILE_HARMONY(chroma, start_frame, end_frame):
    section_chroma = chroma[:, start_frame:end_frame]
    chroma_avg = mean(section_chroma, axis=time)
    dominant_note = NOTE_NAMES[argmax(chroma_avg)]

    Returns: {dominant_note}
```

The dominant note (most energetic pitch class) is a simplified summary. For more sophisticated use, the full chroma average could drive a 12-color mapping where each pitch class has an associated hue.

### 4F. Frequency Band Profiling

```
PROFILE_BANDS(band_energies, rms, start_frame, end_frame):
    For each band:
        section_energy = band_energies[band][start_frame:end_frame]

        mean_energy = mean(section_energy)
        max_energy = max(section_energy)
        relative_energy = mean_energy / (mean(rms[start_frame:end_frame]^2) + epsilon)

    Returns: {band_name: {mean, max, relative}}
```

**Relative energy** normalizes for overall loudness. A section might have high absolute bass energy just because it's loud. Relative energy tells you whether bass *dominates* this section compared to other frequency ranges.

**Mapping to prop groups**:
- Dominant sub_bass/bass → drive floor-level props, low-frequency color schemes
- Dominant low_mid/mid → drive mid-height props, vocal-range color schemes
- Dominant upper_mid/presence/brilliance → drive overhead/accent props, sparkling effects

### 4G. Local Tempo Estimation

```
PROFILE_TEMPO(beat_times, start, end, global_tempo):
    section_beats = beat_times where start <= t < end

    if len(section_beats) > 1:
        local_tempo = 60.0 / mean(diff(section_beats))
    else:
        local_tempo = global_tempo

    Returns: local_tempo_bpm
```

This captures tempo changes that the dynamic tempo estimator in Phase 1 might miss or misestimate, because it's grounded in actual detected beat positions.

## Output

Each section gets a complete profile:

```json
{
    "index": 15,
    "start": 138.569,
    "end": 157.772,
    "duration": 19.2,
    "local_tempo_bpm": 140.5,
    "dominant_note": "F#",
    "energy": {"average": 0.196, "peak": 0.272, "variance": 0.001, "level": "medium", "db_avg": -3.8},
    "spectral": {"brightness": "neutral", "centroid_mean_hz": 1692, ...},
    "texture": {"character": "harmonic", "hp_ratio": 2.00, ...},
    "rhythm": {"beat_count": 45, "onset_density_per_sec": 4.6},
    "frequency_bands": {"bass": {"mean": 736, "max": 1200, "relative": 0.65}, ...},
    "dramatic_moments": [...]
}
```
