# Stem Affinity Rationale

**Purpose**: Documents why each algorithm is assigned to specific stems, with audio engineering reasoning. Used by the sweep matrix to determine default stem sets per algorithm.

**Convention**: Stems are listed in preference order (best first). `full_mix` is always included as a fallback. KEEP and REVIEW stems are eligible; SKIP stems are excluded.

## Beat & Tempo Tracking

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| qm_beats | qm-vamp-plugins:qm-barbeattracker | drums, bass, full_mix | timing | inputtempo, constraintempo | Beat trackers perform best on rhythmic stems with strong transients. Drums have the clearest beat impulses. Bass reinforces the downbeat. Full mix is the fallback when stems aren't available. |
| qm_bars | qm-vamp-plugins:qm-barbeattracker | drums, bass, full_mix | timing | inputtempo, constraintempo | Bar boundaries follow the same rhythmic structure as beats. Drums provide the clearest bar-level pattern (kick on 1, snare on 2/4). |
| qm_tempo | qm-vamp-plugins:qm-tempotracker | drums, bass, full_mix | timing | (none) | Tempo estimation is most accurate on rhythmically stable stems. Drums are the tempo reference in most popular music. |
| beatroot_beats | beatroot-vamp:beatroot | drums, bass, full_mix | timing | (none) | BeatRoot uses autocorrelation-based beat tracking that works best on percussive content. |
| librosa_beats | (librosa) | drums, bass, full_mix | timing | (none) | librosa's beat_track uses onset strength envelope — strongest on transient-rich stems. |
| librosa_bars | (librosa) | drums, bass, full_mix | timing | (none) | Bar grouping from librosa beat positions. Same stem preference as beat tracking. |
| aubio_tempo | vamp-aubio:aubiotempo | drums, bass, full_mix | timing | (none) | Aubio's tempo tracker uses energy-based beat detection, best on percussive stems. |
| madmom_beats | (madmom) | drums, bass, full_mix | timing | (none) | madmom RNN+DBN beat tracker trained primarily on drum patterns. |
| madmom_downbeats | (madmom) | drums, bass, full_mix | timing | (none) | Downbeat detection uses rhythmic hierarchy — clearest in drums. |

## Onset Detection

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| qm_onsets_complex | qm-vamp-plugins:qm-onsetdetector | drums, guitar, bass, vocals, full_mix | timing | sensitivity, dftype | Complex domain onset detection responds to both spectral and phase changes. Works across all instrument types. Drums first because transients are strongest. |
| qm_onsets_hfc | qm-vamp-plugins:qm-onsetdetector | drums, guitar, full_mix | timing | sensitivity, dftype | HFC (High Frequency Content) onset detection emphasizes high-frequency transients — best on drums (cymbals, hi-hat) and guitar (pick attack). |
| qm_onsets_phase | qm-vamp-plugins:qm-onsetdetector | bass, vocals, guitar, full_mix | timing | sensitivity, dftype | Phase deviation onset detection captures tonal onsets that HFC misses. Better for bass note changes and vocal entries. |
| librosa_onsets | (librosa) | drums, guitar, bass, vocals, full_mix | timing | (none) | librosa onset_detect uses spectral flux — general-purpose, works on all stems. |
| aubio_onset | vamp-aubio:aubioonset | drums, guitar, bass, vocals, full_mix | timing | threshold, silence, minioi | Aubio onset uses multiple detection functions. Threshold parameter controls sensitivity. Works on all stem types. |
| percussion_onsets | vamp-example-plugins:percussiononsets | drums | timing | threshold, sensitivity | Purpose-built for broadband percussive onsets. Only meaningful on the drums stem — other stems don't have percussive transients. |
| bbc_rhythm | bbc-vamp-plugins:bbc-rhythm | drums, bass, full_mix | timing | (none) | BBC rhythm features detect rhythmic patterns and onset events. Strongest on rhythmic stems. |

## Pitch & Melody

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| pyin_notes | pyin:pyin | vocals, guitar, piano, full_mix | timing | threshdistr, outputunvoiced | pYIN tracks monophonic pitch. Vocals are the most common monophonic source. Guitar and piano melodies work when isolated by stems. |
| pyin_pitch_changes | pyin:pyin | vocals, guitar, piano, full_mix | timing | threshdistr, outputunvoiced | Pitch change events from pYIN. Same stem logic as note detection. |
| aubio_notes | vamp-aubio:aubionotes | vocals, guitar, piano, full_mix | timing | (none) | Aubio note tracker combines onset + pitch. Best on monophonic melodic stems. |

## Harmony & Key

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| chordino_chords | nnls-chroma:chordino | guitar, piano, full_mix | timing | (none) | Chordino uses NNLS chroma features for chord transcription. Guitar and piano carry the harmonic content. Full mix works when chords are prominent. |
| nnls_chroma | nnls-chroma:nnls-chroma | guitar, piano, full_mix | timing | (none) | Chroma peak detection. Same harmonic reasoning as Chordino. |
| qm_key | qm-vamp-plugins:qm-keydetector | guitar, piano, full_mix | timing | (none) | Key detection analyzes the overall tonal center. Guitar/piano carry the harmonic foundation. Full mix provides complete harmonic context. |

## Segmentation & Structure

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| qm_segments | qm-vamp-plugins:qm-segmenter | full_mix, vocals, drums | timing | (none) | Structural segmentation works on the full mix to capture overall song structure. Vocals stem may reveal vocal-based structure (verse/chorus). Drums may reveal rhythm-based sections. |
| segmentino | segmentino:segmentino | full_mix, vocals, drums | timing | (none) | Alternative segmenter that groups repeated sections (Verse A, Chorus B). Full mix gives the most complete picture. |

## Polyphonic Transcription

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| qm_transcription | qm-vamp-plugins:qm-transcription | piano, guitar, full_mix | timing | (none) | Polyphonic note detection. Piano and guitar have the clearest polyphonic content. Full mix is dense but still useful. |
| silvet_notes | silvet:silvet | piano, guitar, full_mix | timing | (none) | Silvet uses a shift-invariant latent variable model for transcription. Best on harmonic instruments. |

## Energy & Spectral (Value Curves)

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| bbc_energy | bbc-vamp-plugins:bbc-energy | drums, bass, vocals, guitar, piano, other, full_mix | value_curve | (none) | Energy envelope is useful for ALL stems — each stem's energy drives a different lighting dimension (drums → flash intensity, vocals → spotlight brightness, guitar → color saturation). |
| bbc_spectral_flux | bbc-vamp-plugins:bbc-spectral-flux | drums, bass, vocals, guitar, piano, other, full_mix | value_curve | (none) | Spectral change rate detects timbral transitions on every stem. Useful for color/effect change triggers. |
| bbc_peaks | bbc-vamp-plugins:bbc-peaks | drums, bass, guitar, full_mix | value_curve | (none) | Amplitude peaks — most useful on transient-rich stems for flash/strobe effects. |
| amplitude_follower | vamp-example-plugins:amplitudefollower | drums, bass, vocals, guitar, piano, other, full_mix | value_curve | attack, release | Continuous amplitude envelope. Like bbc_energy but with configurable attack/release. Useful for smooth brightness following on all stems. |
| tempogram | tempogram:tempogram | drums, bass, full_mix | value_curve | (none) | Tempo variation over time. Most meaningful on rhythmic stems where tempo changes are audible. |

## Frequency Band Analysis (librosa)

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| bass (20-250 Hz) | (librosa) | bass, drums, full_mix | timing | (none) | Low frequency band energy. Bass stem is the primary source. Drums have kick drum energy in this range. |
| mid (250-4000 Hz) | (librosa) | vocals, guitar, piano, full_mix | timing | (none) | Mid frequency band. Vocals, guitar, and piano all live primarily in this range. |
| treble (4000-20000 Hz) | (librosa) | drums, guitar, full_mix | timing | (none) | High frequency band. Cymbals and hi-hat (drums), pick attack and brightness (guitar). |

## HPSS (librosa)

| Algorithm | Plugin | Preferred Stems | Output | Tunable Params | Rationale |
|-----------|--------|----------------|--------|----------------|-----------|
| drums (HPSS) | (librosa) | full_mix | timing | (none) | HPSS separates percussive from harmonic content internally. Only meaningful on full mix (stem separation already does this). |
| harmonic_peaks | (librosa) | full_mix | timing | (none) | Harmonic component peak detection. Only meaningful on full mix for the same reason. |
