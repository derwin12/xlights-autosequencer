# Tunable Parameters Reference

This document catalogs all hardcoded numeric constants across the codebase that
represent tunable analysis parameters. Use this as a reference when adjusting
behavior for different genres, hardware setups, or quality targets.

---

## High Priority — Core Analysis Parameters

These directly impact analysis accuracy and output quality.

### Energy Detection (`src/analyzer/derived.py`)

| Constant | Value | Description |
|----------|-------|-------------|
| `_IMPACT_RATIO` | `1.8` | Energy increase multiplier to trigger an impact event |
| `_DROP_RATIO` | `0.55` | Energy decrease multiplier to trigger a drop event |
| `_GAP_THRESHOLD` | `5` | Normalized energy level (0–100) below which silence is detected |
| `_GAP_MIN_MS` | `300` | Minimum duration (ms) for a gap to be reported |
| `_WINDOW_MS` | `1000` | Analysis window size (ms) for energy impacts/drops |

### Drum Classification (`src/analyzer/drum_classifier.py`)

| Constant | Value | Description |
|----------|-------|-------------|
| `_KICK_MAX` | `200` | Upper frequency boundary (Hz) for kick drum detection |
| `_HIHAT_MIN` | `8000` | Lower frequency boundary (Hz) for hihat detection |
| `_WINDOW_MS` | `60` | Analysis window (ms) around each drum onset |
| kick ratio threshold | `0.60` | Low-frequency ratio above which an onset is classified as kick |
| hihat ratio threshold | `0.20` | High-frequency ratio above which an onset is classified as hihat |

### Interaction Analysis (`src/analyzer/interaction.py`)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `hold_ms` | `250` | Minimum hold duration (ms) before allowing a stem switch |
| `delta_db` | `6.0` | Minimum dB difference to force a stem switch in leader track |
| RMS weight | `0.7` | RMS component weight in leader track scoring |
| spectral flux weight | `0.3` | Spectral flux component weight in leader track scoring |
| tightness: unison | `0.7` | Correlation above which kick-bass relationship = "unison" |
| tightness: independent | `0.3` | Correlation below which kick-bass relationship = "independent" |
| sidechain depth | `0.4` | Gain reduction proportion at drum onsets |
| sidechain release_frames | `3` | Frames for exponential recovery after sidechain |
| drum threshold factor | `0.3` | Drum onset threshold = 30% of max drum energy |
| handoff max_gap_ms | `500` | Maximum allowed gap (ms) between melodic stem handoffs |
| handoff energy threshold | `0.1` | 10% of max energy for stem activity detection |

### Scoring Weights (`src/analyzer/scoring_config.py`)

| Weight | Value | Description |
|--------|-------|-------------|
| density | `0.25` | Weight for mark density in overall quality score |
| regularity | `0.25` | Weight for inter-mark regularity |
| mark_count | `0.15` | Weight for total mark count |
| coverage | `0.15` | Weight for song duration coverage |
| min_gap | `0.20` | Weight for minimum gap compliance |
| `diversity_threshold` | `0.90` | Proportion of matching marks to flag tracks as duplicates |
| `min_gap_threshold_ms` | `25` | Minimum actionable inter-mark gap (hardware constraint) |

### Scoring Category Ranges (`src/analyzer/scoring_config.py`)

| Category | density | regularity | mark_count | coverage |
|----------|---------|------------|------------|----------|
| beats | 1.0–4.0 | 0.6–1.0 | 100–800 | 0.8–1.0 |
| bars | 0.2–1.0 | 0.6–1.0 | 20–200 | 0.7–1.0 |
| onsets | 1.0–8.0 | 0.0–0.6 | 100–2000 | 0.7–1.0 |
| segments | 0.01–0.1 | 0.0–0.5 | 4–30 | 0.5–1.0 |
| pitch | 0.5–4.0 | 0.1–0.7 | 50–500 | 0.5–1.0 |
| harmony | 0.2–2.0 | 0.1–0.6 | 20–400 | 0.5–1.0 |
| general | 0.1–5.0 | 0.0–1.0 | 10–1000 | 0.3–1.0 |

### Phoneme Distribution (`src/analyzer/phonemes.py`)

| Constant | Value | Description |
|----------|-------|-------------|
| `_VOWEL_WEIGHT` | `1.5` | Duration weight multiplier for vowels |
| `_CONSONANT_WEIGHT` | `0.75` | Duration weight multiplier for consonants |

### Generator Mood Tiers (`src/generator/models.py`)

| Tier | Energy Range | Description |
|------|-------------|-------------|
| ethereal | 0–33 | Low energy: fades, sparkles, gentle effects |
| structural | 34–66 | Mid energy: chases, waves, patterns |
| aggressive | 67–100 | High energy: strobes, fire, full brightness |

| Constant | Value | Description |
|----------|-------|-------------|
| `FRAME_INTERVAL_MS` | `25` | Default frame interval for xLights sequences |

### Effect Placement (`src/generator/effect_placer.py`)

| Parameter | Value | Description |
|-----------|-------|-------------|
| chord weight max | `0.50` | Maximum chord influence on color blending |
| chord count divisor | `80.0` | Unique chords needed for maximum chord weight |

---

## Medium Priority — Signal Processing Parameters

These control timing resolution and computational cost.

### STFT / Hop Length

| File | Constant | Value | Description |
|------|----------|-------|-------------|
| `librosa_bands.py` | `_HOP_LENGTH` | `512` | STFT hop for frequency band analysis |
| `librosa_bands.py` | `_N_FFT` | `2048` | FFT window size |
| `librosa_hpss.py` | `_HOP_LENGTH` | `512` | Hop for HPSS percussion/harmonic |
| `librosa_onset.py` | `_HOP_LENGTH` | `512` | Hop for full-spectrum onset detection |
| `librosa_beats.py` | `hop_length` | `512` | Beat tracking hop size |

### Frequency Band Boundaries (`src/analyzer/algorithms/librosa_bands.py`)

| Band | fmin (Hz) | fmax (Hz) |
|------|-----------|-----------|
| Bass | 20 | 250 |
| Mid | 250 | 4,000 |
| Treble | 4,000 | 20,000 |

### Frame Rates

| File | Context | fps | Description |
|------|---------|-----|-------------|
| `interaction.py` | leader track | `20` | Frames/sec for interaction analysis |
| `interaction.py` | tightness | `20` | Frames/sec for kick-bass analysis |
| `interaction.py` | sidechain | `20` | Frames/sec for sidechain effect |
| `interaction.py` | handoffs | `20` | Frames/sec for handoff detection |
| `pipeline.py` | default | `20` | Default analysis frame rate |
| `madmom_beat.py` | RNN processor | `100` | madmom beat processor frame rate |
| `vamp_extra.py` | amplitude | `50ms` | Frame interval for amplitude marks |
| `vamp_extra.py` | tempogram | `50ms` | Frame interval for tempogram marks |

### Dynamic Range Scaling (`src/generator/energy.py`)

| Dynamics | Floor | Ceiling | Condition |
|----------|-------|---------|-----------|
| compressed | 45 | 85 | complexity < 2 |
| moderate | 25 | 100 | complexity 2–5 |
| wide | 10 | 100 | complexity > 5 |

| Constant | Value | Description |
|----------|-------|-------------|
| `_REFERENCE_LUFS` | `-14.0` | Reference loudness (Spotify streaming target) |

---

## Low Priority — Fixed / Architectural

| File | Constant | Value | Description |
|------|----------|-------|-------------|
| `librosa_beats.py` | `beats_per_bar` | `4` | Beats per bar for bar grouping |
| `madmom_beat.py` | `beats_per_bar` | `[3, 4]` | Allowed meters for downbeat tracking |
| `pipeline.py` | sample rate | `22050` | librosa default resampling rate |
| `scorer.py` | `threshold_ms` | `25` | Hardware minimum inter-mark interval |
| `pipeline.py` | `top_n` | `5` | Max top-scoring tracks to retain |
| `vamp_onsets.py` | `dftype` values | `0, 2, 3` | QM onset detector modes (HFC, Phase, Complex) |
