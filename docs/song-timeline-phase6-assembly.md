# Phase 6: Timeline Assembly

Combines all previous phases into the final output: a **human-readable narrative timeline** and a **machine-readable JSON** that can drive automated sequence generation.

## Input

From Phase 1: Global stats, energy timeline (sampled every 0.5s), beat details
From Phase 2: Section boundaries
From Phase 3+5: Ranked dramatic moments
From Phase 4: Section profiles

## Step 1: Narrative Act Detection

The section profiles from Phase 4 give us 20-40 sections. For human consumption, we group these into **acts** — larger narrative arcs that correspond to the emotional journey of the song.

**Algorithm**:
```
DETECT_ACTS(sections):
    1. Compute energy arc: map each section to its average energy level
       energy_arc = [s.energy.average for s in sections]

    2. Identify act boundaries by finding major energy inflection points:
       - Act boundary where energy changes direction (build→plateau, plateau→drop)
       - Act boundary at silence regions (dramatic pauses = act breaks)
       - Act boundary where texture character changes persistently
         (harmonic→percussive for 3+ consecutive sections)

    3. Name acts by their energy/texture pattern:
       - "Intro" — first act, energy building from low
       - "Explosion/Drop" — act beginning with a major energy surge
       - "Power/Sustain" — act with sustained high energy
       - "Breakdown" — act with high dramatic density + energy volatility
       - "Quiet/Bridge" — act with low energy + harmonic texture
       - "Return/Reprise" — act that reprises earlier energy patterns
       - "Coda" — final act, energy declining to zero

    Returns: acts[] with names, section ranges, and descriptions
```

**This is currently done by human interpretation**, but could be automated using the energy arc shape classification. The key patterns:

```
Energy Shape          Act Type         Light Strategy
────────────         ─────────        ───────────────
     _____
    /     \          Build→Peak       Ramp up brightness/speed
___/       \___


███████████████      Sustained        Maintain maximum, vary color


████
    ▄▄▄▄             Step Down        Reduce one tier at a time
        ▁▁▁▁

▁▁▁▁▁▁▁▁▁▁▁▁       Quiet Hold       Single ambient effect


    ████
▁▁▁/    \▁▁▁        Spike            Flash on entry, quick fade


████░░░░████         Dip and Return   Brief dim then full restore
```

## Step 2: Energy Timeline Sampling

For the machine-readable output, we sample all features at regular 0.5-second intervals. This provides a continuous view that's easy to interpolate for any target frame rate.

```
BUILD_ENERGY_TIMELINE(features, duration, step=0.5):
    t = 0
    while t < duration:
        frame = time_to_frames(t)
        window = frames[frame-5 : frame+5]  # ~230ms context

        entry = {
            time: t,
            rms: mean(rms[window]),
            rms_db: mean(rms_db[window]),
            centroid_hz: mean(centroid[window]),
            harmonic_rms: mean(rms_harmonic[window]),
            percussive_rms: mean(rms_percussive[window]),
        }

        # Add per-band energies
        for band in bands:
            entry[band] = mean(band_energy[window])

        timeline.append(entry)
        t += step

    Returns: timeline[]
```

**Why 0.5s sampling?** This matches the typical xLights timing resolution (50ms minimum effect length, but most effects are placed at 250ms-1000ms granularity). 0.5s gives smooth interpolation without bloating the JSON. For a 5-minute song, this is ~580 entries — manageable.

**Why a 10-frame window (±5 frames)?** Smooths out individual frame noise while preserving ~500ms resolution. A single frame at 23ms can be dominated by a transient; the window gives a stable reading.

## Step 3: Beat Detail Enrichment

Each detected beat gets a profile for fine-grained beat-synced effects:

```
BUILD_BEAT_DETAILS(beat_times, rms, sr, hop_length):
    For each beat at time t:
        frame = time_to_frames(t)
        strength = rms[frame]
        is_downbeat = (beat_index % 4 == 0)  # estimated

    Returns: beat_details[]
```

**The downbeat estimate** (`index % 4 == 0`) assumes 4/4 time, which is wrong for many songs (Mad Russian Christmas has passages in 3/4, 6/8, and free time). A better approach would be to use the onset strength contour to identify metrically strong beats (downbeats have stronger onsets than upbeats).

## Step 4: JSON Assembly

The final JSON structure:

```json
{
    "song": "Song Title",
    "duration_seconds": 289.45,
    "global_tempo_bpm": 136.0,
    "total_beats": 606,
    "total_onsets": 865,
    "total_sections": 35,
    "total_dramatic_moments": 372,

    "key_regions": [...],      // Phase 1G output
    "sections": [...],         // Phase 4 output
    "dramatic_moments": [...], // Phase 5 output
    "beats": [...],            // Step 3 output
    "energy_timeline": [...],  // Step 2 output
    "silence_regions": [...],  // Phase 3E output

    "global_stats": {
        "energy_mean": 0.134,
        "energy_max": 0.302,
        "harmonic_percussive_ratio": 2.45,
        "centroid_mean_hz": 1580,
        ...
    }
}
```

## How the Output Feeds Into Sequence Generation

The sequence generator (feature 020) can use this timeline at multiple levels:

### Level 1: Section-level decisions
- **Which theme/palette?** Based on `section.energy.level`, `section.spectral.brightness`, `section.texture.character`, `section.dominant_note`
- **Which effects?** Based on `section.texture.character` and `section.rhythm.onset_density_per_sec`
- **Effect speed?** Based on `section.local_tempo_bpm`

### Level 2: Beat-level placement
- **Where to place effects?** At `beats[].time` positions
- **How strong?** Scaled by `beats[].strength`
- **Downbeat emphasis?** Stronger/different effect on `beats[].is_downbeat_estimate`

### Level 3: Dramatic moment accents
- **Energy surges**: Trigger all-on or brightness ramp at surge point
- **Energy drops**: Trigger blackout or rapid dim at drop point
- **Percussive impacts**: Layer a flash/strobe effect on top of current effects
- **Brightness spikes**: Add a brief white overlay
- **Silences**: Kill all effects, fade to black
- **Tempo changes**: Adjust chase/cycle speed of active effects

### Level 4: Continuous curves (from energy_timeline)
- **Brightness curve**: Map `rms` → master brightness (0-100%)
- **Color temperature**: Map `centroid_hz` → warm↔cool
- **Effect complexity**: Map `onset_density` → simple↔complex
- **Band-specific groups**: Map individual `band_*` values → per-group brightness

## Accuracy and Limitations

### What works well
- **Energy curves** are highly reliable — RMS is straightforward physics
- **Percussive impacts** detected via HPSS are clean and musically meaningful
- **Section boundaries** from self-similarity work well for songs with clear structure
- **Silence detection** is nearly perfect — silence is unambiguous

### What needs improvement
- **Tempo tracking** is noisy for classical music with rubato — octave errors and frame-level jitter
- **Key estimation** is approximate — the Krumhansl-Kessler profiles assume well-tempered Western harmony and struggle with chromatic passages, modal music, or atonal sections
- **Section labels** are not detected — we know *where* sections change but not *what* they are (verse, chorus, bridge)
- **Dynamic tempo** is per-frame when it should be per-phrase — a median filter or beat-interval approach would be more stable
- **Downbeat detection** assumes 4/4 time — a meter detection algorithm would be valuable

### What's missing entirely
- **Melody contour tracking** — rising vs falling melodic lines could drive sweep direction
- **Instrument identification** — knowing "this is a violin solo" vs "full orchestra" would enable instrument-specific lighting presets
- **Lyrics/vocal detection** — vocal presence could trigger spotlight or face-lighting effects
- **Musical tension modeling** — harmonic tension (dissonance) and rhythmic tension (syncopation) are powerful dramatic predictors not captured by energy alone
