# Song Timeline Analysis — Algorithm Overview

This document describes the complete methodology for producing a **light-show-ready timeline** from a raw audio file. The pipeline extracts musical structure, identifies dramatic moments, and classifies sections with enough detail to drive automated effect placement.

The analysis is organized as a **pipeline of 6 phases**, each building on the outputs of previous phases. Each phase is documented in its own sub-document with implementation-level detail.

## Pipeline Architecture

```
                         Raw Audio (MP3/WAV)
                               |
                     [Phase 1: Feature Extraction]
                               |
          +--------------------+--------------------+
          |          |         |         |          |
        Beats    Onsets    Energy   Spectral    HPSS
        Tempo              RMS     Chroma     Harmonic
                           Bands   MFCC       Percussive
                               |
                     [Phase 2: Section Detection]
                               |
                    Structural Boundaries
                               |
                     [Phase 3: Event Detection]
                               |
          +--------+--------+--------+--------+
          |        |        |        |        |
       Energy   Tempo   Brightness  Perc.  Silence
       Surges/  Changes  Spikes    Impacts  Regions
       Drops
                               |
                     [Phase 4: Section Profiling]
                               |
                    Per-Section Feature Aggregation
                    (energy, spectral, texture, rhythm,
                     frequency bands, local tempo, key)
                               |
                     [Phase 5: Dramatic Moment Ranking]
                               |
                    Classified + Intensity-Scored Events
                               |
                     [Phase 6: Timeline Assembly]
                               |
                    Human-readable narrative +
                    Machine-readable JSON
```

## Phase Index

| Phase | Document | Purpose |
|-------|----------|---------|
| 1 | [Phase 1: Feature Extraction](song-timeline-phase1-features.md) | Extract raw audio features: beats, onsets, energy, spectral, HPSS, chroma, MFCCs, frequency bands |
| 2 | [Phase 2: Section Detection](song-timeline-phase2-sections.md) | Find structural boundaries using self-similarity on beat-synchronous MFCCs |
| 3 | [Phase 3: Event Detection](song-timeline-phase3-events.md) | Detect dramatic moments: energy surges/drops, tempo changes, brightness spikes, percussive impacts, silence |
| 4 | [Phase 4: Section Profiling](song-timeline-phase4-profiling.md) | Aggregate features per section, classify energy level, brightness, texture character |
| 5 | [Phase 5: Dramatic Moment Ranking](song-timeline-phase5-ranking.md) | Deduplicate, score, and rank all detected events for light-show prioritization |
| 6 | [Phase 6: Timeline Assembly](song-timeline-phase6-assembly.md) | Combine everything into narrative acts and machine-readable output |

## Key Design Decisions

### Why this order?

Feature extraction (Phase 1) is embarrassingly parallel — all features are independent of each other. Section detection (Phase 2) depends on MFCCs and beats from Phase 1. Event detection (Phase 3) depends on energy curves, tempo, and spectral features from Phase 1. Section profiling (Phase 4) needs both section boundaries (Phase 2) and all features (Phase 1). This creates a natural dependency graph:

```
Phase 1 (parallel) → Phase 2 + Phase 3 (parallel) → Phase 4 → Phase 5 → Phase 6
```

### Timestamps are always milliseconds or seconds?

Throughout this pipeline, timestamps are in **floating-point seconds** during computation (because librosa works in seconds). At the final output stage, they are both:
- Stored as float seconds in JSON (for machine consumption)
- Formatted as `MM:SS.mmm` strings (for human reading)

The existing xlight codebase uses **integer milliseconds** — conversion happens at the boundary when feeding into the sequence generator.

### What makes a moment "dramatic"?

A dramatic moment is any point where the audio **changes significantly and rapidly** relative to its local context. This includes:
- Energy changing faster than the 97th percentile of all energy changes
- Tempo shifting by more than the 95th percentile of all tempo changes
- Spectral centroid spiking more than 2.5 standard deviations above the mean
- Percussive onset strength exceeding the 98th percentile
- Near-silence lasting more than 300ms (rare in orchestral music = intentional)

These are **relative thresholds** — they adapt to each song's dynamic range rather than using absolute dB values. A quiet acoustic song and a loud orchestral piece both produce meaningful dramatic moments at their own scale.
