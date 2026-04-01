# Timing Tracks Guide

Overview of all timing data produced by the analysis pipeline, what's currently
used by the sequence generator, and what's available for future use.

## Grid Levels (Rhythmic)

| Level | Name | Rate | Source | In XSQ? | Generator Uses? | Best For |
|-------|------|------|--------|---------|-----------------|----------|
| L2 | Bars | ~0.4-0.5/s | QM, librosa, madmom | Yes | Yes | Section washes, slow color transitions |
| L2.5 | Half-bars | ~0.8-1/s | Derived from bars | No | No | Medium-speed chases, wave effects |
| L3 | Beats | ~1.5-2.2/s | QM, BeatRoot, librosa, madmom | Yes | Yes | Beat-synced strobes, flash effects |
| L3.5 | Eighth-notes | ~3-4.5/s | Derived from beats | No | No | Fast chases, rapid flicker in high-energy sections |

**Quality**: Beat regularity is excellent across tested songs (CV 0.8%–5.2%).
Implied BPM matches estimated BPM in every case. The selector picks the best
algorithm per song from 4 candidates.

**Gap**: Generator only uses bars and beats. Half-bars and eighth-notes are
computed but unused. Effect speed should scale with section energy — low energy
sections use bar grid, high energy use eighth-note grid.

## Structural

| Data | Source | In XSQ? | Generator Uses? | Story Uses? |
|------|--------|---------|-----------------|-------------|
| L1 Sections | Segmentino + QM + Genius | Yes | Yes (theme boundaries) | Yes (core) |
| L6 Chords | Chordino (Vamp) | Yes | Partially (brightness modulation) | Yes |
| L6 Key changes | QM key detector | No | No | No |

## Per-Stem Events (L4)

| Data | Source | In XSQ? | Generator Uses? |
|------|--------|---------|-----------------|
| Drum onsets | Aubio (Vamp) on drums stem | 1 stem only | Yes (one-shots) |
| Bass onsets | Aubio on bass stem | No | No |
| Vocal onsets | Aubio on vocals stem | No | No |
| Guitar onsets | Aubio on guitar stem | No | No |
| Piano onsets | Aubio on piano stem | No | No |
| Other onsets | Aubio on other stem | No | No |
| Full-mix onsets | Aubio on full mix | Yes (exported) | Yes |

**Gap**: Only one onset track exported to XSQ. Per-stem onsets available in
hierarchy but not used. Drum/bass/vocal onsets would enable stem-specific
effect layers.

## Stem Accents (NEW — from story profiler)

Outlier peaks on each stem's energy curve — dramatic moments that stand out
from the normal beat pattern. Detected via percentile-based outlier analysis.

| Stem | What It Captures | Typical Count |
|------|------------------|---------------|
| Drums | Dramatic fills, crashes, accent hits | 0-20 per song |
| Bass | Sub-bass drops, bass fills | 0-17 per song |
| Vocals | Vocal entries, sustained high notes, shouts | 0-8 per song |
| Guitar | Power chord accents, riff peaks, solo climaxes | 0-35 per song |
| Piano | Dramatic chord strikes, runs | 0-5 per song |
| Other | Synth stabs, orchestral swells, FX hits | 0-5 per song |

Each accent has `time_ms` (onset-snapped) and `intensity` (0-100).

**Status**: Computed in story JSON per section. Visible in review UI (togglable
accent layers on the timeline). NOT yet exported to XSQ or consumed by generator.

## Special Moments (L0)

| Data | Source | In XSQ? | Generator Uses? |
|------|--------|---------|-----------------|
| Energy impacts | Derived from energy curves | No | No |
| Energy drops | Derived from energy curves | No | No |
| Silence gaps | Derived from energy curves | No | No |

**Gap**: These are the highest-impact lighting moments — a cymbal crash gets a
flash, a drop gets a blackout-to-burst, silence gets a full blackout. All
detected but none wired to the generator.

## Continuous Data (L5)

| Data | Source | In XSQ? | Generator Uses? |
|------|--------|---------|-----------------|
| Full-mix energy curve | BBC/librosa | No | Yes (section energy scores) |
| Per-stem energy curves | BBC/librosa per stem | No | No (only via story profiler) |
| Spectral flux | BBC Vamp | No | No |

## Interaction Data

| Data | Source | In XSQ? | Generator Uses? |
|------|--------|---------|-----------------|
| Leader track | Derived (dominant stem over time) | No | No |
| Handoffs | Derived (stem leadership changes) | No | No |
| Tightness | Derived (drums+bass alignment) | No | No |
| Solos | Derived (per-stem prominence) | No | No |

## Priority for Wiring to Generator

1. **Stem accents** → per-stem accent effects at exact timestamps
2. **L0 impacts/drops/gaps** → one-shot dramatic effects
3. **Per-stem onsets** (L4) → separate effect layers per instrument
4. **Half-bars / eighth-notes** → energy-adaptive grid selection
5. **Solos** → spotlight effects during solo regions
6. **Key changes** → color palette shifts at key modulations
