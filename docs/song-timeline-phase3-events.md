# Phase 3: Event Detection

Detects individual **dramatic moments** — specific timestamps where something musically significant happens. These are the moments that should trigger visible lighting changes.

## Input

From Phase 1:
- `rms_smooth[]` — 2-second smoothed energy curve
- `rms[]` — raw RMS energy
- `rms_times[]` — timestamps for energy frames
- `dtempo[]` — dynamic per-frame tempo estimates
- `spectral_centroid[]` — brightness curve
- `perc_onset_env[]` — onset strength of percussive component only
- `rms_harmonic[]`, `rms_percussive[]` — separated energy curves

## Sub-Algorithms

Each detector runs independently and produces a list of `{time, type, intensity, description}` events. All events are merged and deduplicated in Phase 5.

---

### 3A. Energy Surge/Drop Detection

**Purpose**: Find moments where the song gets suddenly louder or quieter. These correspond to structural transitions (verse→chorus = surge, chorus→bridge = drop), dynamic accents, and tension/release patterns.

**Algorithm**:
```
DETECT_ENERGY_CHANGES(rms_smooth, rms_times):
    1. Compute frame-to-frame energy difference:
       rms_diff[i] = rms_smooth[i+1] - rms_smooth[i]

    2. Compute adaptive threshold:
       surge_threshold = percentile(|rms_diff|, 97)
       (top 3% of all energy changes are "dramatic")

    3. For each frame:
       if rms_diff[i] > surge_threshold:
           emit ENERGY_SURGE event
           intensity = rms_diff[i] / surge_threshold
       elif rms_diff[i] < -surge_threshold:
           emit ENERGY_DROP event
           intensity = |rms_diff[i]| / surge_threshold

    Returns: events[]
```

**Why 97th percentile?** This is empirically tuned. At 97th percentile with ~43fps and a 5-minute song, you get roughly 400 candidate frames, which after deduplication yields 10-30 meaningful energy change events. Lower percentiles produce too many false positives; higher percentiles miss subtle but important changes.

**Why use smoothed RMS?** The raw RMS has per-beat pulses that would flood the detector with every beat. The 2-second smoothing reveals only changes that persist across multiple beats — these are the structurally meaningful ones.

**Interpretation for light shows**:
- `intensity > 2.0`: Extreme — all-lights-on moment or blackout
- `intensity 1.5-2.0`: Major — section transition, significant mood change
- `intensity 1.0-1.5`: Moderate — notable dynamic shift within a section

---

### 3B. Tempo Change Detection

**Purpose**: Find moments where the tempo shifts. Ritardando (slowing) and accelerando (speeding up) are powerful expressive tools that should be reflected in effect speed.

**Algorithm**:
```
DETECT_TEMPO_CHANGES(dtempo, tempo_times):
    1. Compute frame-to-frame tempo difference:
       tempo_diff[i] = |dtempo[i+1] - dtempo[i]|

    2. Compute adaptive threshold:
       threshold = percentile(tempo_diff, 95)

    3. For each frame where tempo_diff > threshold:
       emit TEMPO_CHANGE event
       from_bpm = dtempo[i]
       to_bpm = dtempo[i+1]

    Returns: events[]
```

**Caveats**:
- Dynamic tempo estimation is noisy. The per-frame tempo from `librosa.feature.tempo(aggregate=None)` can jump between harmonically related tempos (e.g., 120 BPM and 60 BPM are often confused). Large jumps like 96→185 BPM may be octave errors rather than real tempo changes.
- Real tempo changes in classical music (ritardando, fermata) produce gradual changes over multiple frames, not single-frame jumps. Single-frame jumps are more likely estimation artifacts.

**Improvement**: Apply a median filter to dtempo before differencing to suppress octave-jump artifacts. Or only flag tempo changes where the new tempo is sustained for at least 4 beats.

---

### 3C. Brightness (Spectral) Spike Detection

**Purpose**: Find moments where the sound becomes dramatically brighter — typically cymbal crashes, high brass entries, string harmonics, or other high-frequency events that create visual "flash" moments.

**Algorithm**:
```
DETECT_BRIGHTNESS_SPIKES(spectral_centroid, spec_times):
    1. Z-score normalize the centroid:
       centroid_z = (centroid - mean(centroid)) / std(centroid)

    2. Find peaks in centroid_z:
       - Height threshold: 2.5 standard deviations above mean
       - Minimum distance: 0.5 seconds between peaks

    3. For each peak:
       emit BRIGHTNESS_SPIKE event
       centroid_hz = raw centroid value at peak
       intensity = centroid_z value at peak

    Returns: events[]
```

**Why z-score?** The absolute centroid value varies hugely between songs. A dark cello piece might have centroid 500-1500 Hz; a bright pop track might be 2000-5000 Hz. Z-scoring makes the threshold relative to the song's own spectral range.

**Why 2.5 sigma?** This catches the top ~0.6% of brightness values. In a 5-minute song at 43fps, that's roughly 80 candidate frames before distance-based deduplication. After dedup, you typically get 10-30 brightness events.

**What this tells the light show**: Map to white/cool-white flash overlays on top of the current color palette. The intensity value scales the flash brightness.

---

### 3D. Percussive Impact Detection

**Purpose**: Find the strongest individual percussive hits — drum accents, orchestral stabs, pizzicato attacks, etc. These are the backbone of beat-synced lighting.

**Algorithm**:
```
DETECT_IMPACTS(perc_onset_env, sr):
    1. Compute onset strength envelope of percussive component only
       (using y_percussive from HPSS, not the full mix)

    2. Compute adaptive threshold:
       threshold = percentile(perc_onset_env, 98)
       (top 2% of all percussive onset frames)

    3. Find all frames exceeding threshold
    4. Convert to timestamps

    5. Cluster nearby impacts (within 150ms):
       - Group consecutive timestamps with gaps < 150ms
       - Replace each cluster with its mean timestamp
       - Keep the maximum onset strength from the cluster

    Returns: events[] with strength values
```

**Why use the percussive component?** In the full mix, sustained harmonic content (strings, pads) creates a "floor" in the onset strength that makes it harder to detect individual hits. The HPSS-separated percussive signal gives much cleaner transient detection.

**Why 150ms clustering?** A single drum hit often triggers multiple detection peaks due to the initial attack and subsequent resonance. 150ms is long enough to merge these into a single event but short enough to distinguish consecutive 16th notes at moderate tempos (at 120 BPM, 16th notes are 125ms apart).

**Interpretation for light shows**:
- `strength > 15`: Extreme impact — cymbal crash, full orchestra stab
- `strength 10-15`: Strong hit — snare accent, strong downbeat
- `strength 8-10`: Normal percussive event — regular beat pulse

---

### 3E. Silence/Near-Silence Detection

**Purpose**: Find moments of quiet or silence. In orchestral and arranged music, intentional silences are among the most powerful dramatic devices — a pause before a big entry, a fermata, a section break.

**Algorithm**:
```
DETECT_SILENCE(rms, rms_times):
    1. Compute silence threshold:
       threshold = percentile(rms, 5) * 2
       (2x the quietest 5% of the song — accounts for noise floor)

    2. Scan for contiguous regions below threshold:
       Track state: in_silence (bool), silence_start (frame)

       For each frame:
           if rms < threshold and not in_silence:
               in_silence = True, record start
           elif rms >= threshold and in_silence:
               in_silence = False
               duration = current_time - start_time
               if duration > 0.3 seconds:
                   emit SILENCE event

    Returns: events[] with duration values
```

**Why 300ms minimum?** Shorter silences are usually just natural gaps between notes or articulations — not intentional dramatic pauses. 300ms is roughly the threshold where a listener perceives a deliberate pause rather than normal phrasing.

**What this tells the light show**: Silence = blackout or near-blackout. The duration determines whether it's a brief blink (0.3-0.5s) or a sustained dramatic pause (>1s). Silence followed by an energy surge = the "blackout before the drop" pattern, one of the most effective light show techniques.

---

### 3F. Harmonic/Percussive Texture Shift Detection

**Purpose**: Find moments where the musical texture fundamentally changes character — from melodic to rhythmic or vice versa. These indicate arrangement changes (drums drop out, strings take over) that should change the *type* of lighting effect, not just its intensity.

**Algorithm**:
```
DETECT_TEXTURE_SHIFTS(rms_harmonic, rms_percussive, rms_times, smooth_window):
    1. Compute HP ratio per frame:
       hp_ratio = rms_harmonic / (rms_percussive + epsilon)

    2. Smooth the ratio (same 2-second window as energy):
       hp_smooth = convolve(hp_ratio, uniform_kernel)

    3. Compute frame-to-frame changes:
       hp_diff = diff(hp_smooth)

    4. Threshold at 97th percentile:
       For each frame:
           if hp_diff > threshold:
               emit SHIFT_TO_HARMONIC event
           elif hp_diff < -threshold:
               emit SHIFT_TO_PERCUSSIVE event

    Returns: events[]
```

**What this tells the light show**:
- Shift to harmonic → switch to smooth, flowing effects (color wash, twinkle, slow fade)
- Shift to percussive → switch to impact effects (strobe, chase, flash-on-beat)
- The transition point is where you crossfade between effect types

## Output of Phase 3

All event types are collected into a single list:

```python
events = [
    {"time": 1.14, "type": "energy_surge", "intensity": 1.57, "description": "..."},
    {"time": 3.00, "type": "percussive_impact", "strength": 16.56, "description": "..."},
    {"time": 4.38, "type": "energy_drop", "intensity": 2.22, "description": "..."},
    ...
]
```

This list is unsorted and may contain overlapping/duplicate events (e.g., a percussive impact and an energy surge at the same moment). Phase 5 handles deduplication and ranking.
