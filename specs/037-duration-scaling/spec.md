# Feature Specification: Duration Scaling

**Feature Branch**: `037-duration-scaling`
**Created**: 2026-04-09
**Status**: Draft
**Input**: Phase 2 of the Sequence Quality Refinement plan (035). Effect durations should match song energy and tempo, based on reference sequence analysis of 5 community .xsq files.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fast Songs Get Short Effects (Priority: P1)

As a user generating a sequence for an upbeat song (BPM above 120), I want the
majority of effect durations to be under 1 second, so that the light show feels
energetic and beat-driven -- matching how skilled sequencers use beat-level timing
for fast pop songs like "Light of Christmas" (48% at 0.5-1s, 30% at 0.25-0.5s).

**Why this priority**: This is the most visible mismatch in current output. Fast
songs with slow, bar-length effects look sluggish and disconnected from the music.
Fixing this single case produces the largest perceptible improvement.

**Independent Test**: Generate a sequence for a song with BPM above 120. Run the
reference analyzer on the output. Verify the median effect duration is under 1 second
and the duration distribution is dominated by the 0.25-1s range.

**Acceptance Scenarios**:

1. **Given** a song with detected BPM above 120, **When** a sequence is generated,
   **Then** the median effect duration across all placements is under 1 second.
2. **Given** a song with detected BPM above 120, **When** the duration distribution
   is analyzed, **Then** at least 60% of effect placements fall in the 0.25-1s range.
3. **Given** a high-BPM song with a low-energy section (e.g., a bridge at energy 25),
   **When** effects are placed in that section, **Then** durations lengthen toward
   1-2s for that section while the rest of the song stays under 1s.

---

### User Story 2 - Slow Songs Get Long Effects (Priority: P1)

As a user generating a sequence for a gentle or slow song (BPM below 80), I want
effect durations in the 1.5-4s range with zero sub-250ms effects, so that the
light show breathes with the music -- matching how "Away In A Manger" uses 41%
at 2-4s and 25% at 4-8s with nothing under 250ms.

**Why this priority**: Equally important as US1. Short, rapid effects on a slow
hymn look frantic and inappropriate. The absence of sub-250ms effects in slow
reference sequences is a hard rule, not a soft preference.

**Independent Test**: Generate a sequence for a song with BPM below 80. Run the
reference analyzer. Verify the median duration is between 1.5 and 4 seconds and
zero effects are under 250ms.

**Acceptance Scenarios**:

1. **Given** a song with detected BPM below 80, **When** a sequence is generated,
   **Then** the median effect duration is between 1.5 and 4 seconds.
2. **Given** a song with detected BPM below 80, **When** the duration distribution
   is analyzed, **Then** zero effect placements are shorter than 250ms.
3. **Given** a slow song with a high-energy section (e.g., a climax at energy 85),
   **When** effects are placed in that section, **Then** durations shorten toward
   1-2s but do not drop below 500ms.

---

### User Story 3 - Mid-Tempo Songs Get Intermediate Durations (Priority: P1)

As a user generating a sequence for a mid-tempo song (BPM 80-120), I want effect
durations that fall between the fast and slow extremes, so that songs like
"Christmas Just Ain't Christmas" (50% at 1-2s, 27% at 2-4s) get appropriate
timing without being forced into either the beat-level or bar-level pattern.

**Why this priority**: Most songs fall in this range. Without explicit handling,
mid-tempo songs risk defaulting to one extreme or the other. The interpolated
behavior must feel natural, not like an arbitrary cutoff.

**Independent Test**: Generate a sequence for a song with BPM between 80 and 120.
Verify the median duration falls between 1 and 2.5 seconds.

**Acceptance Scenarios**:

1. **Given** a song with detected BPM between 80 and 120, **When** a sequence is
   generated, **Then** the median effect duration is between 1 and 2.5 seconds.
2. **Given** two songs at BPM 85 and BPM 115 respectively, **When** sequences are
   generated for both, **Then** the BPM-115 song has a shorter median duration
   than the BPM-85 song (duration scales continuously, not in discrete buckets).

---

### User Story 4 - Energy Modulates Duration Within a Song (Priority: P2)

As a user, I want effect durations to vary across sections of the same song based
on section energy, so that high-energy choruses have tighter, shorter effects and
low-energy verses have longer, more sustained effects -- creating dynamic contrast
within a single sequence.

**Why this priority**: BPM sets the baseline, but energy refines it per section.
Without energy modulation, every section of a song would have identical timing,
which contradicts how human sequencers adapt to musical dynamics.

**Independent Test**: Generate a sequence for a song with clear verse/chorus energy
contrast. Compare median durations in low-energy sections versus high-energy sections.

**Acceptance Scenarios**:

1. **Given** a song with sections ranging from energy 20 to energy 90, **When** a
   sequence is generated, **Then** the median effect duration in sections with
   energy above 70 is at least 30% shorter than in sections with energy below 40.
2. **Given** a mid-tempo song (BPM 100), **When** a section has energy 90, **Then**
   the effect durations trend toward the beat-level range (0.5-1s) rather than
   the bar-level range.
3. **Given** a mid-tempo song (BPM 100), **When** a section has energy 20, **Then**
   the effect durations trend toward the bar-level range (2-4s) rather than
   beat-level.

---

### User Story 5 - Fade Timing Matches Duration Scale (Priority: P2)

As a user, I want effect fade-in and fade-out times to be proportional to effect
duration, so that short beat-level effects have crisp transitions (zero or minimal
fade) while longer bar-level effects have gentle fades -- matching the "gentle
fadein/fadeout (0.2-2s)" seen in slow reference sequences and the hard cuts in
fast ones.

**Why this priority**: Fade times that mismatch duration destroy the visual impact.
A 250ms fade on a 300ms effect makes it invisible; a 0ms fade on a 4-second effect
creates jarring hard cuts on a slow hymn.

**Independent Test**: Generate sequences for a fast and slow song. Verify that
fade times scale with effect duration: near-zero for sub-500ms effects, 200-500ms
for 1-2s effects, and up to 1-2s for effects lasting 4s or more.

**Acceptance Scenarios**:

1. **Given** an effect placement with duration under 500ms, **When** fades are
   calculated, **Then** both fade-in and fade-out are zero.
2. **Given** an effect placement with duration between 1 and 4 seconds, **When**
   fades are calculated, **Then** fade values are between 100ms and 500ms.
3. **Given** an effect placement with duration above 4 seconds, **When** fades
   are calculated, **Then** fade values are between 200ms and 2000ms.
4. **Given** any effect placement, **When** fades are calculated, **Then** the
   combined fade-in plus fade-out never exceeds 40% of the total effect duration.

---

### User Story 6 - Duration Scaling Is Independently Toggleable (Priority: P2)

As a user, I want the duration scaling behavior to be independently toggleable,
so that I can enable or disable it without affecting other sequence quality
improvements -- allowing A/B comparison and safe rollback.

**Why this priority**: Required by the parent refinement plan (FR-008 in 035).
Each phase must be testable in isolation.

**Independent Test**: Generate the same sequence twice -- once with duration
scaling enabled and once disabled. Verify the disabled version produces identical
output to the pre-feature baseline.

**Acceptance Scenarios**:

1. **Given** duration scaling is disabled, **When** a sequence is generated,
   **Then** the output is identical to the baseline (pre-feature) output.
2. **Given** duration scaling is enabled while all other refinement phases are
   disabled, **When** a sequence is generated, **Then** only duration-related
   metrics change; effect vocabulary and model activation remain unchanged.

---

### User Story 7 - Bimodal Duration for Mixed-Character Songs (Priority: P3)

As a user, I want the system to support bimodal duration distributions for songs
that mix short accent effects with long sustained holds, so that songs like
"Baby Shark" (short 0.5-1s accents alongside 8-16s holds) or "Shut Up and Dance"
(short On flashes plus sustained VU Meter) are handled correctly rather than
forced into a single duration target.

**Why this priority**: This is an advanced case. Most songs are well-served by the
BPM+energy scaling from US1-US4. Bimodal behavior is an enhancement for specific
song styles and can be deferred without blocking the core value.

**Independent Test**: Generate a sequence for a song with sections that alternate
between high-energy accent moments and sustained holds. Verify the distribution
shows two distinct peaks rather than a single Gaussian.

**Acceptance Scenarios**:

1. **Given** an effect whose definition indicates sustained hold behavior (e.g.,
   On, Color Wash, VU Meter), **When** placed in a section, **Then** its duration
   is allowed to exceed the section's baseline duration target (up to full section
   length for On/Color Wash).
2. **Given** an effect whose definition indicates accent/hit behavior (e.g.,
   Shockwave, short On flash), **When** placed in a section, **Then** its duration
   follows the beat-level baseline regardless of BPM.

---

### Edge Cases

- What happens when BPM detection fails or returns an extreme value (e.g., 40 BPM
  or 220 BPM)? Duration targets must clamp to reasonable bounds -- minimum 250ms,
  maximum 8 seconds for non-sustained effects.
- What happens when a section has zero energy score (fully silent or unanalyzed)?
  Duration should default to bar-level (safe fallback) rather than producing
  undefined behavior.
- What happens when a song has no detected sections (e.g., ambient/drone music)?
  The entire song is treated as a single section and BPM alone drives duration.
- What happens when a song's BPM is detected as a half-time or double-time variant
  (e.g., 65 BPM when the perceived tempo is 130)? The system should use detected BPM
  as-is; half-time correction is out of scope for this phase.
- What happens when the effect definition specifies a fixed duration_type (e.g.,
  "section" for Faces/lip-sync)? Fixed duration_type effects override the scaling
  system -- lip-sync must always span the full section.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST determine a target duration range for each section
  based on the song's detected BPM and the section's energy score.
- **FR-002**: For songs with BPM above 120, the system MUST produce a median effect
  duration under 1 second, with the majority of placements in the 0.25-1s range.
- **FR-003**: For songs with BPM below 80, the system MUST produce a median effect
  duration between 1.5 and 4 seconds, with zero placements under 250ms.
- **FR-004**: For songs with BPM between 80 and 120, the system MUST produce
  durations that scale continuously between the fast and slow targets.
- **FR-005**: Section energy MUST modulate the BPM-derived baseline. High-energy
  sections (energy above 70) shift durations shorter; low-energy sections (energy
  below 40) shift durations longer.
- **FR-006**: The combined effect of BPM and energy MUST be continuous (no hard
  cutoffs at BPM boundaries) and monotonic (higher BPM and higher energy always
  produce shorter durations, all else being equal).
- **FR-007**: Effect fade-in and fade-out times MUST scale proportionally with
  effect duration: near-zero for sub-500ms effects, 100-500ms for 1-4s effects,
  and up to 2s for effects above 4s. Combined fades MUST NOT exceed 40% of total
  effect duration.
- **FR-008**: Effects with a fixed duration_type (section-spanning effects like
  Faces/lip-sync) MUST be exempt from duration scaling and retain their current
  behavior.
- **FR-009**: Duration scaling MUST be independently toggleable. When disabled,
  generator output MUST be identical to the pre-feature baseline.
- **FR-010**: Duration targets MUST be clamped to safe bounds: minimum 250ms
  (configurable per effect), maximum 8 seconds for non-sustained effects.
- **FR-011**: The system MUST support per-effect duration behavior hints (e.g.,
  "sustained", "accent", "standard") to allow bimodal distributions where sustained
  effects can exceed the section baseline.

### Key Entities

- **DurationStrategy**: Encapsulates the mapping from BPM and energy to a target
  duration range (minimum, target, maximum milliseconds) for a given section. This
  is the core calculation that replaces fixed duration_type behavior.
- **DurationBehavior**: A per-effect classification (standard, sustained, accent)
  that modifies how the DurationStrategy is applied. "Standard" effects follow
  the strategy directly. "Sustained" effects are allowed to extend beyond the
  target up to section length. "Accent" effects always use the short end of the
  range.
- **FadeProfile**: A derived entity from DurationStrategy that calculates
  appropriate fade-in and fade-out times based on the resolved effect duration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For songs with BPM above 120, generated sequences have a median
  effect duration under 1 second (reference benchmark: Light of Christmas median
  approximately 0.7s).
- **SC-002**: For songs with BPM below 80, generated sequences have a median
  effect duration between 1.5 and 4 seconds with zero sub-250ms placements
  (reference benchmark: Away In A Manger median approximately 3s).
- **SC-003**: For songs with BPM 80-120, the median duration falls between the
  fast and slow targets, scaling continuously with BPM.
- **SC-004**: Within any generated sequence, sections with energy above 70 have
  at least 30% shorter median duration than sections with energy below 40.
- **SC-005**: Fade times are proportional to duration: the ratio of (fade-in +
  fade-out) to total duration stays between 0% and 40% across all placements.
- **SC-006**: When duration scaling is disabled, generated output is byte-identical
  to the pre-feature baseline for the same input and seed.
- **SC-007**: No regression in the existing test suite when duration scaling is
  disabled.
- **SC-008**: The reference analyzer tool, when run on generated output, reports
  duration distributions that fall within the ranges observed in the corresponding
  BPM category of the 5 reference sequences.

## Assumptions

- The existing audio analysis pipeline reliably detects song BPM. Half-time and
  double-time detection errors are out of scope for this phase.
- Section energy scores (0-100) from the analysis hierarchy are available and
  meaningful for all sections. Sections without energy data default to energy 50.
- The existing beat and bar timing marks from the analysis hierarchy are accurate
  enough to derive beat-level and bar-level placement boundaries.
- Effect definitions in the theme/effect catalog will be extended with a duration
  behavior hint (standard/sustained/accent) as part of this phase. Effects without
  a hint default to "standard".
- The reference analyzer tool (`analyze_reference_xsq.py`) can measure duration
  distributions on generated output with the same methodology used on reference
  sequences.

## Relationship to Other Phases

This is **Phase 2 of 5** in the Sequence Quality Refinement plan (spec 035).

| Phase | Feature | Spec | Dependency |
|-------|---------|------|------------|
| Phase 1 | Focused Effects and Repetition | 036 | Independent |
| **Phase 2** | **Duration Scaling** | **037 (this spec)** | **Independent, but benefits from Phase 1's focused vocabulary** |
| Phase 3 | Palette Restraint | TBD | Independent |
| Phase 4 | Dynamic Model Activation | TBD | Benefits from Phases 1-2 |
| Phase 5 | MusicSparkles and Value Curves | TBD | Benefits from Phases 1-3 |

Duration scaling can be implemented independently of Phase 1. However, the two
phases complement each other: Phase 1 reduces the number of distinct effects
(reducing visual noise), while Phase 2 ensures those effects have appropriate
timing. When both are active, the result is a focused set of effects with
musically appropriate durations -- the two biggest structural improvements
identified in the reference analysis.

Phase 4 (Dynamic Model Activation) benefits from duration scaling being in place
because model activation changes at section boundaries will be more impactful when
the underlying effect durations already match the musical character of each section.
