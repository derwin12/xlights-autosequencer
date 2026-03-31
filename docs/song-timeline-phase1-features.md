# Phase 1: Feature Extraction

Extracts all raw audio features from the input file. Every sub-algorithm in this phase is **independent** — they can all run in parallel on the same loaded audio array.

## Input

- Audio file path (MP3 or WAV)
- Sample rate: 22050 Hz (standard for music analysis — sufficient frequency resolution up to ~11 kHz, half the compute of 44.1 kHz)

## Loading

```
y, sr = load_audio(path, sr=22050, mono=True)
duration = len(y) / sr
```

Mono downmix is fine for structural analysis. Stereo information (panning) is not used for timing or energy analysis. Loading at 22050 Hz discards content above ~11 kHz, which is acceptable — musical content relevant to light shows (beats, melody, harmony, energy) is well below this.

## Sub-Algorithms

### 1A. Beat and Tempo Tracking

**Purpose**: Find the rhythmic pulse of the song — where the beats fall, what the tempo is, and how tempo changes over time.

**Algorithm**:
```
BEAT_TRACK(y, sr):
    1. Compute onset strength envelope (see 1B)
    2. Run dynamic programming beat tracker (librosa.beat.beat_track)
       - Estimates global tempo via autocorrelation of onset envelope
       - Places beats at onset envelope peaks that best fit the estimated tempo
    3. Convert beat frame indices to timestamps

    Returns: beat_times[] (seconds), global_tempo (BPM)
```

**Dynamic tempo estimation**:
```
DYNAMIC_TEMPO(onset_envelope, sr):
    1. For each frame position, compute local tempo estimate
       using windowed autocorrelation of the onset envelope
    2. librosa.feature.tempo(aggregate=None) returns per-frame estimates

    Returns: tempo_curve[] (BPM at each frame), tempo_times[] (seconds)
```

**Parameters**:
- `hop_length`: 512 samples (~23ms at 22050 Hz). This is the time resolution for all frame-based features.
- Beat tracker uses the onset envelope, not raw audio — this makes it more robust to sustained notes.

**What this tells the light show**: Where to place beat-synced effects (strobes, chases, flashes). Tempo changes indicate ritardando/accelerando passages that need speed-adaptive effects.

---

### 1B. Onset Detection

**Purpose**: Find every distinct musical event — note attacks, drum hits, plucks, bows, etc. More granular than beats (a beat is every Nth onset).

**Algorithm**:
```
DETECT_ONSETS(y, sr):
    1. Compute onset strength envelope:
       - Take STFT of audio
       - Compute spectral flux (frame-to-frame increase in energy per frequency bin)
       - Aggregate across frequency bands
       - Apply adaptive thresholding (local median + offset)
    2. Find peaks in onset strength envelope above threshold
    3. Backtrack each peak to the nearest preceding local minimum
       (finds the actual start of the note, not the peak)

    Returns: onset_times[], onset_strengths[]
```

**Parameters**:
- Backtracking enabled — gives more accurate onset positions for light sync
- Peak picking uses librosa defaults (wait=1 frame, pre_max/post_max for local peak detection)

**What this tells the light show**: Onset density per second is a proxy for musical complexity. High onset density = fast passages that need rapid-fire effects. Low onset density = sustained notes that need slow/sweeping effects.

---

### 1C. Energy / RMS Envelope

**Purpose**: Track the loudness of the song over time. This is the most important single feature for light shows — it directly maps to brightness and intensity.

**Algorithm**:
```
COMPUTE_ENERGY(y, sr, hop_length=512):
    1. Compute RMS energy in sliding windows:
       - Window size = hop_length (512 samples, ~23ms)
       - Slide by hop_length (no overlap)
       - RMS = sqrt(mean(samples^2)) per window
    2. Convert to dB scale: dB = 20 * log10(rms / max(rms))
    3. Compute smoothed energy for section-level analysis:
       - Convolution with uniform kernel, width = 2 seconds
       - This removes per-beat fluctuation, reveals section-level dynamics

    Returns: rms[], rms_db[], rms_smooth[], rms_times[]
```

**Why two energy curves?**
- **Raw RMS**: captures every beat pulse, useful for beat-level effect triggering
- **Smoothed RMS** (2-second window): captures section-level dynamics, used for detecting energy surges/drops that represent structural changes (verse→chorus, bridge→drop)

**What this tells the light show**: Direct brightness mapping. The dB curve tells you the relative loudness at every moment. Smoothed energy identifies the "energy arc" of the song — builds, peaks, valleys.

---

### 1D. Spectral Features

**Purpose**: Characterize the *timbral quality* of the sound — is it bright or dark? Noisy or tonal? Narrow or wide-band?

**Features extracted**:

| Feature | What it measures | Light show use |
|---------|-----------------|----------------|
| Spectral centroid | "Center of mass" of the frequency spectrum (Hz) | Higher = brighter, more treble. Maps to color temperature (cool/warm) |
| Spectral bandwidth | Width of the spectrum around the centroid (Hz) | Higher = more complex/full sound. Maps to effect complexity |
| Spectral rolloff | Frequency below which 85% of energy lies (Hz) | Practical upper bound of where the sound lives |
| Spectral contrast | Energy difference between peaks and valleys per band | Higher contrast = more tonal (instruments). Lower = noisier (cymbals) |
| Spectral flatness | How noise-like vs tonal (0=pure tone, 1=white noise) | Distinguishes tonal passages from percussive/noise sections |
| Zero crossing rate | How often the waveform crosses zero | Proxy for noisiness, correlates with percussive content |

**Algorithm** (same for all):
```
SPECTRAL_FEATURES(y, sr, hop_length=512):
    For each frame (hop_length window):
        1. Compute STFT magnitude spectrum
        2. Derive each feature from the magnitude spectrum

    Returns: feature_curve[], feature_times[]
```

**Key insight for light shows**: The spectral centroid is the most useful single spectral feature. A sudden spike in centroid means a bright, high-frequency event (cymbal crash, high violin note, brass hit). These map naturally to white/bright flashes in lighting.

---

### 1E. Frequency Band Energy Decomposition

**Purpose**: Break the spectrum into meaningful musical bands and track energy in each independently. This lets you drive different light groups from different frequency ranges.

**Band definitions**:

| Band | Frequency Range | Musical Content |
|------|----------------|-----------------|
| Sub-bass | 20-60 Hz | Kick drum fundamental, bass drops |
| Bass | 60-250 Hz | Bass guitar, cello, tuba, kick drum body |
| Low-mid | 250-500 Hz | Lower vocal range, guitar body, warmth |
| Mid | 500-2000 Hz | Vocal presence, guitar attack, snare body |
| Upper-mid | 2000-4000 Hz | Vocal clarity, trumpet brightness, snare crack |
| Presence | 4000-6000 Hz | Sibilance, cymbal shimmer, attack transients |
| Brilliance | 6000-11025 Hz | Air, sparkle, cymbal wash |

**Algorithm**:
```
BAND_ENERGY(y, sr, hop_length=512):
    1. Compute STFT magnitude spectrogram S
    2. Compute frequency axis: freqs = sr * bin_index / fft_size
    3. For each band (lo_hz, hi_hz):
       a. Create frequency mask: mask = (freqs >= lo) & (freqs < hi)
       b. Band energy per frame = mean(S[mask, :]^2, axis=frequency)
          (mean rather than sum to normalize for band width)

    Returns: band_energies{name: curve[]}, band_times[]
```

**What this tells the light show**: Different prop groups can react to different bands. Bass energy drives floor-level props. Mid energy drives mid-height props. Treble drives overhead/accent props. This creates natural visual separation.

---

### 1F. Harmonic/Percussive Source Separation (HPSS)

**Purpose**: Separate the audio into harmonic content (sustained tones — strings, vocals, pads) and percussive content (transient hits — drums, plucks, staccato). This is critical for understanding the *texture* of each moment.

**Algorithm**:
```
HPSS(y):
    1. Compute STFT magnitude spectrogram
    2. Apply median filtering in two directions:
       - Horizontal median filter (across time) → captures harmonics
         (harmonics are constant across time, so they survive time-averaging)
       - Vertical median filter (across frequency) → captures percussives
         (percussive events are broadband spikes, so they survive freq-averaging)
    3. Create soft masks from the two filtered spectrograms
    4. Apply masks to original STFT to get separated signals
    5. Inverse STFT to get time-domain signals

    Returns: y_harmonic[], y_percussive[]
```

**Derived features**:
```
    rms_harmonic = RMS(y_harmonic)
    rms_percussive = RMS(y_percussive)
    hp_ratio = rms_harmonic / rms_percussive  (per-frame)
```

**Interpretation**:
- hp_ratio > 1.5 → "harmonic" texture (melodic passage, sustained chords)
- hp_ratio < 0.67 → "percussive" texture (drum break, staccato passage)
- Between → "balanced" (typical full-band music)

**What this tells the light show**: Harmonic sections suit smooth effects (color wash, fade, twinkle). Percussive sections suit impact effects (strobe, flash, chase). The ratio tracks this continuously. Note: Shimmer in xLights is a rapid on/off flash, not a subtle effect — it belongs with the percussive/impact category despite its name.

---

### 1G. Chroma and Key Estimation

**Purpose**: Track the harmonic content — which notes and keys are present at each moment. Key changes often align with section boundaries and mood shifts.

**Algorithm**:
```
CHROMA(y, sr, hop_length=512):
    1. Compute Constant-Q Transform (CQT) — like STFT but with
       logarithmic frequency resolution (matches musical pitch)
    2. Fold all octaves into 12 bins (C, C#, D, ..., B)
    3. Normalize per frame

    Returns: chroma[12, n_frames], chroma_times[]
```

**Key estimation** (per window):
```
ESTIMATE_KEY(chroma_window):
    1. Average chroma across the window (e.g. 4 seconds)
    2. For each of 12 possible root notes (C through B):
       a. Rotate chroma so this root is index 0
       b. Correlate with Krumhansl-Kessler major key profile:
          [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
       c. Correlate with Krumhansl-Kessler minor key profile:
          [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
       d. Keep the (root, mode) with highest correlation
    3. Track key changes over time

    Returns: key_regions[{time, key, confidence}]
```

**What this tells the light show**: Key changes suggest color palette changes. Major keys → warm colors (gold, red, orange). Minor keys → cool colors (blue, purple, green). The confidence score indicates how clear the tonality is — low confidence often means transitional or chromatic passages.

---

### 1H. MFCCs (Timbre Fingerprint)

**Purpose**: Mel-Frequency Cepstral Coefficients capture the overall "shape" of the spectrum in a compact form. They're not directly interpretable as individual features, but they're excellent for **comparing timbral similarity between different moments** — which is exactly what section detection needs.

**Algorithm**:
```
MFCC(y, sr, n_mfcc=13, hop_length=512):
    1. Compute mel-scaled spectrogram (40 mel bands)
    2. Take log of mel energies
    3. Apply Discrete Cosine Transform (DCT) to get 13 coefficients

    Returns: mfcc[13, n_frames]
```

**Why 13 coefficients?** The first coefficient captures overall energy (like RMS). Coefficients 2-5 capture broad spectral shape (bright vs dark). Coefficients 6-13 capture finer spectral detail (specific instrument timbres). Beyond 13, you're modeling speaker/instrument identity rather than musical characteristics.

**What this tells the light show**: MFCCs aren't used directly for light parameters. They feed into Phase 2 (section detection) where timbral similarity determines structural boundaries.

---

## Output of Phase 1

All features are computed as time-aligned arrays at the same frame rate (hop_length=512, ~43 frames/second at 22050 Hz). This makes them trivially combinable in later phases.

| Feature Set | Shape | Frame Rate |
|------------|-------|------------|
| Beats | variable length (N beats) | event-based |
| Onsets | variable length (N onsets) | event-based |
| RMS energy | (1, T) | ~43 fps |
| Spectral centroid | (1, T) | ~43 fps |
| Spectral bandwidth | (1, T) | ~43 fps |
| Spectral rolloff | (1, T) | ~43 fps |
| Spectral contrast | (7, T) | ~43 fps |
| Spectral flatness | (1, T) | ~43 fps |
| Zero crossing rate | (1, T) | ~43 fps |
| Frequency bands | (7, T) | ~43 fps |
| RMS harmonic | (1, T) | ~43 fps |
| RMS percussive | (1, T) | ~43 fps |
| Chroma | (12, T) | ~43 fps |
| MFCCs | (13, T) | ~43 fps |
| Dynamic tempo | (1, T') | ~43 fps |

Total compute time: ~15-30 seconds for a 5-minute song on a modern machine. HPSS is the bottleneck (~40% of total time).
