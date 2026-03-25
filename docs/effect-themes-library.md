# Composite Effect Library — Thematic Design Spec

**Created**: 2026-03-25
**Status**: Initial catalog — maps song moods/sections to xLights effect recipes

---

## Purpose

This library defines reusable "looks" — composite effect stacks that create a specific visual mood. The sequencer selects from this library based on three inputs:

1. **What is the Prop?** (Matrix vs. Outline → Fidelity tier `05_TEX`)
2. **What is the Mood?** (Aggressive vs. Ethereal → derived from analysis)
3. **What is the Complexity?** (High-intensity Chorus vs. Low-intensity Verse → derived from analysis)

Each recipe maps specific analysis outputs (BPM, energy, onsets, spectral features) to effect parameters, creating reactive lighting that feels connected to the music.

---

## 1. Atmospheric & Ethereal Collection

**Use for**: Intros, soft verses, piano solos, ambient builds.
**Analysis triggers**: Low energy (L5), few onsets (L4), section label = N/unique (L1).

### Stellar Wind (The "Nebula" Look)
- **Intent**: Deep space and slow, infinite movement.
- **Stack**: Slow Butterfly (shifting "gas" background) → Twinkle (depth) → Meteors (occasional shooting stars).
- **Model Logic**: Map Meteor Count to high-frequency piano note onsets (L4).

### Aurora (The "Natural Wonder" Look)
- **Intent**: Shimmering, vertical curtains of the Northern Lights.
- **Stack**: Color Wash (base gradient) → Butterfly (stretched vertically for "curtains" that sway).
- **Model Logic**: Use a slow Sine Wave value curve on Brightness to make it "breathe" (L5 energy curve).

### Bio-Lume (The "Living Organism" Look)
- **Intent**: Pulsing deep-sea creatures or glowing forests.
- **Stack**: Plasma (organic, shifting blobs) → Circles (high Softness = glowing spores).
- **Model Logic**: Link Circle Size to BPM so the "spores" pulse with the beat (L3 beats).

---

## 2. Aggressive & Kinetic Collection

**Use for**: Heavy metal choruses, dubstep drops, fast guitar solos.
**Analysis triggers**: High energy (L5), dense onsets (L4), energy impacts (L0).

### Inferno (The "Raw Power" Look)
- **Intent**: Make the house look like it is literally on fire and exploding.
- **Stack**: Fire (bottom) → high-speed Morph bottom-to-top ("embers") → Shockwaves (on snare).
- **Model Logic**: Link Fire Height to bass energy curve (L5 bass stem). Shockwaves triggered by drum onsets (L4).

### Molten Metal (The "Industrial Heat" Look)
- **Intent**: High-contrast, glowing-hot textures that feel "heavy."
- **Stack**: Fire (Gold/White) → Warp (middle layer = melting/dripping light).
- **Model Logic**: Map Warp Amplitude to spectral flux (L5 bbc_spectral_flux curve).

### Tracer Fire (The "Combat" Look)
- **Intent**: Sharp, fast, directional "bullets" of light.
- **Stack**: High-speed short-tail Meteors (alternating colors every beat) → fast Strobe ("muzzle flash").
- **Model Logic**: Trigger Meteor Direction changes on beats (L3). Color alternation on bars (L2).

---

## 3. Dark & Horror Collection

**Use for**: Spooky themes, minor-key breakdowns, "villain" sections.
**Analysis triggers**: Low-mid energy (L5), gaps/silence (L0), minor key (L6).

### The Void (The "Black Hole" Look)
- **Intent**: "Negative space" where lights feel like they are disappearing.
- **Stack**: Dark Plasma (base) → Liquid with Subtract blend mode (carves holes of darkness).
- **Model Logic**: Increase Subtract intensity during energy drops (L0 drops). Gaps trigger full blackout.

### Glitch City (The "Digital Decay" Look)
- **Intent**: Broken, stuttering aesthetic like a malfunctioning computer.
- **Stack**: Fast-moving Bars → Shader (Glitch) on top (scrambles pixels randomly).
- **Model Logic**: Map Glitch Intensity to high-frequency transient onsets — cymbals/hi-hat (L4 onset density).

### The Kraken (The "Tentacle" Look)
- **Intent**: Organic, writhing movement that feels claustrophobic.
- **Stack**: Liquid (Green/Deep Blue, swampy base) → Tendrils (reach from corners toward center).
- **Model Logic**: Link Tendril Length to bass energy curve (L5 bass stem).

---

## 4. Structural & Geometric Collection

**Use for**: Synth-heavy tracks, pop choruses, rhythmic grooves.
**Analysis triggers**: Steady beat (L3), repeating sections (L1 label A), moderate-high energy (L5).

### Cyber Grid (The "Tron" Look)
- **Intent**: Precise, mathematical beauty.
- **Stack**: Shapes (Squares/Lines in grid) → Kaleidoscope (perfect symmetry = giant snowflake).
- **Model Logic**: Change Kaleidoscope Segment count based on chord (L6 chordino — e.g., 4 for C-Major, 8 for G-Major).

### Scanning Beam (The "Security" Look)
- **Intent**: Sweeping "searchlight" effect that defines the house's shape.
- **Stack**: Single-pixel wide Bars (sweep across models) → Fade (brief "ghost" trail).
- **Model Logic**: Sync Sweep Speed to exactly 1 bar duration (L2 bar interval).

### The Zipper (The "Interlocked" Look)
- **Intent**: Show the relationship between different props (Windows and Eaves).
- **Stack**: Morphs that start on one prop and end on another ("zip" back and forth).
- **Model Logic**: Trigger the "Zip" on off-beat eighth notes for syncopation (L3 beats subdivided).

---

## 5. Selection Matrix

The sequencer selects effects by crossing three dimensions:

```
Prop Type (from layout)     ×  Mood (from analysis)  ×  Section Intensity (from analysis)
─────────────────────────      ────────────────────      ──────────────────────────────────
Matrix / High-density          Ethereal                  Low (verse, intro)
Outline / Low-density          Aggressive                High (chorus, drop)
Arch / Curved                  Dark/Horror               Building (pre-chorus)
Vertical / Straight            Structural/Geometric      Peak (climax, solo)
```

### Mood Detection from Analysis

| Mood | How to Detect | Analysis Levels |
|------|--------------|-----------------|
| **Ethereal** | Low energy, sparse onsets, slow tempo | L5 (energy < 40), L4 (onsets < 1/s), L3 (BPM < 100) |
| **Aggressive** | High energy, dense onsets, fast tempo | L5 (energy > 70), L4 (onsets > 3/s), L0 (frequent impacts) |
| **Dark/Horror** | Minor key, energy drops, gaps | L6 (minor key), L0 (drops + gaps), L5 (low-mid energy) |
| **Structural** | Steady beat, repeating sections, moderate energy | L3 (regular beats), L1 (repeat labels), L5 (40-70 energy) |

### Section Intensity from Analysis

| Intensity | Detection | Drives |
|-----------|-----------|--------|
| **Low** | Energy < 40, non-repeat section (N label) | Ethereal collection, slow effects |
| **Building** | Energy increasing (positive delta from previous section) | Transition effects, ramps |
| **High** | Energy > 60, repeat section (A/B label), all stems active | Aggressive/Structural collection |
| **Peak** | Energy impact (L0) + highest energy in song | Hero overrides, full-house effects |

### Cycling to Prevent Repetition

Even within a mood, the sequencer should **cycle through recipes** within the collection. A 5-minute metal song doesn't just use Inferno — it rotates through Inferno → Molten Metal → Tracer Fire across consecutive high-energy sections to keep the audience engaged.

- **Same section label (A=A=A)**: Use the SAME recipe each time (visual consistency = chorus recognition).
- **Different section labels at same intensity**: Cycle to next recipe in the collection.
- **Unique sections (N labels)**: Pick a recipe not yet used — these are one-time moments.
