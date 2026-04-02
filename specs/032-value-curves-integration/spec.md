# Feature Specification: Value Curves Integration

**Feature Branch**: `032-value-curves-integration`
**Created**: 2026-04-02
**Status**: Draft
**Input**: User description: "Enable value curves so effect parameters change dynamically over time following the music analysis data — brightness breathes with energy, speed ramps on builds, color shifts with chords."

## Clarifications

### Session 2026-04-02

- Q: Should color-mix curves use harmony/chord data (L6) or energy data (L5)? → A: Both — energy-driven color modulation is the primary driver (always available at 43-47fps), with chord-triggered accent shifts as a secondary layer activated only when chord density >20 events/min and quality >0.4. Decision based on analysis of 4 songs: Holiday Road (23/min, 0.37), Santa Tell Me (25/min, 0.60), Carmina Burana (13/min, 0.30), Mad Russian (41/min, 0.53). Orchestral content like Carmina Burana has too sparse/unreliable chord data for color driving.
- Q: How do users control value curve categories (brightness/speed/color/none)? → A: Both CLI flags and config file, with CLI overriding config. CLI: `--curves all|brightness|speed|color|none`. Config: TOML generation profile setting. CLI takes precedence when both are specified.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Effects Breathe with Music Energy (Priority: P1)

A user generates a sequence for a song. Instead of static brightness across each effect placement, the brightness of every effect rises and falls with the energy of the music. During a quiet verse, effects dim. During a loud chorus drop, effects blaze at full brightness. The visual intensity tracks the audio energy without any manual adjustment.

**Why this priority**: Brightness is the single most impactful parameter for making a light show feel "alive." Static brightness is the #1 complaint about generated sequences — everything looks flat and mechanical. Energy-driven brightness is the minimum viable value curve.

**Independent Test**: Generate a sequence for a song with clear dynamic range (quiet verse, loud chorus). Open the resulting sequence file in xLights. Verify that brightness values change over time within each effect placement, and that the brightness curve visually tracks the energy of the music.

**Acceptance Scenarios**:

1. **Given** a song with a quiet intro and loud chorus, **When** a sequence is generated, **Then** effects placed during the intro have lower brightness values than effects placed during the chorus.
2. **Given** an effect placement spanning 8 seconds that includes a volume swell, **When** the sequence is generated, **Then** the brightness parameter contains a value curve with multiple control points that ramp upward during the swell.
3. **Given** a generated sequence file, **When** opened in xLights, **Then** the value curves render correctly and the effect visually brightens and dims with the music.
4. **Given** a song where all sections have roughly equal energy, **When** a sequence is generated, **Then** brightness curves are relatively flat (no artificial variation is injected where the music is steady).

---

### User Story 2 - Speed Ramps on Builds and Drops (Priority: P2)

A user generates a sequence for an EDM track with clear build-ups and drops. During build sections, effect animation speeds gradually increase — bars sweep faster, meteors accelerate, spirals tighten. At the drop, speed either peaks or resets. This creates a visual tension-and-release that mirrors the musical structure.

**Why this priority**: Speed is the second most visible parameter after brightness. Speed ramps during builds are a hallmark of professional light shows. Builds on P1's infrastructure — once brightness curves work, speed curves use the same pipeline with different analysis data mappings.

**Independent Test**: Generate a sequence for a song with a clear build-to-drop section. Open in xLights and verify that effects during the build section have increasing speed values, and effects during the drop section have either peak or reduced speed.

**Acceptance Scenarios**:

1. **Given** a song with a build section (rising energy over 16+ bars), **When** a sequence is generated, **Then** effect speed parameters during the build contain value curves that trend upward.
2. **Given** an effect with a speed parameter (e.g., Bars, Meteors, Spirals), **When** placed during a build section, **Then** the speed curve follows the energy trajectory of the build.
3. **Given** an effect whose speed parameter does not support value curves, **When** the sequence is generated, **Then** that parameter remains static (no error, no forced curve).

---

### User Story 3 - Color Breathes with Energy, Accents Shift on Chords (Priority: P2)

A user generates a sequence for a pop song. The color mix of effects subtly shifts intensity with the music energy — brighter, more saturated colors during high-energy sections, cooler tones during quiet passages. On songs where chord analysis is dense and reliable (over 20 chord changes per minute, quality score above 0.4), the system also triggers color accent shifts at chord change boundaries, adding harmonic awareness to the visual. On songs with sparse or low-quality chord data (like orchestral pieces), only energy-driven color modulation is used.

**Why this priority**: Color is the third most visible parameter after brightness and speed. Energy-driven color modulation works on every song because energy data is always available at high resolution. Chord-triggered accents are a bonus layer that activates only when the data supports it — no risk of bad output on songs where Chordino struggles.

**Independent Test**: Generate sequences for two songs — one with good chord density (e.g., Santa Tell Me at 25 chords/min, quality 0.60) and one with poor chord data (e.g., Carmina Burana at 13 chords/min, quality 0.30). Verify the first has both energy-driven color modulation and chord-triggered accents. Verify the second has only energy-driven color modulation.

**Acceptance Scenarios**:

1. **Given** any song with energy analysis data, **When** a sequence is generated with color curves enabled, **Then** color-mix parameters contain value curves derived from the energy data.
2. **Given** a song with chord density above 20 events/min and chord quality above 0.4, **When** a sequence is generated, **Then** color-mix curves include accent shifts at chord change boundaries in addition to energy-driven modulation.
3. **Given** a song with chord density below 20 events/min or chord quality below 0.4, **When** a sequence is generated, **Then** color-mix curves are energy-only — no chord-triggered accents are applied.
4. **Given** a song where chord data is entirely missing (no L6 analysis), **When** a sequence is generated, **Then** color-mix curves still work using energy data alone, with no errors.

---

### User Story 4 - Disable or Adjust Value Curves per Generation (Priority: P3)

A user wants to generate a sequence without value curves (for debugging, for a simpler show, or because their xLights version has issues with curves). They can disable value curves entirely, or choose which parameter categories to enable (brightness only, speed only, all).

**Why this priority**: Users need an escape hatch. If value curves cause rendering issues in their xLights version, or they prefer a simpler look, they should be able to turn them off. This also aids development — easier to test static vs dynamic output side by side.

**Independent Test**: Generate a sequence with value curves disabled. Verify the output file contains no value curve data. Then generate with curves enabled and verify curves are present.

**Acceptance Scenarios**:

1. **Given** the user requests generation with value curves disabled, **When** the sequence is generated, **Then** no value curve data appears in the output — all parameters are static.
2. **Given** the user requests only brightness curves (no speed curves), **When** the sequence is generated, **Then** only brightness-related parameters have value curves; speed parameters remain static.
3. **Given** no explicit preference, **When** the sequence is generated, **Then** value curves are enabled by default for all supported parameters.

---

### Edge Cases

- What happens when the analysis data (energy curves) is missing or incomplete for a song section? The system should fall back to static parameter values for that placement.
- What happens when an effect placement is very short (under 1 second)? A value curve with meaningful variation needs some minimum duration. Very short placements should use static values instead of a degenerate curve.
- What happens when the analysis energy is constant (no variation) across an effect's duration? The system should produce a flat curve (effectively static) rather than injecting artificial variation.
- What happens when a parameter's value range is very narrow (e.g., min 40, max 60)? The curve should respect the defined output range and not produce values outside the parameter's bounds.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The sequence generator MUST produce value curves for brightness-related parameters on all effect placements where the underlying effect supports value curves and analysis energy data is available.
- **FR-002**: Value curves MUST be derived from the song's analysis data (energy curves, beat timing) — not from random or arbitrary patterns.
- **FR-003**: The generated value curves MUST be encoded in the output sequence file in a format that renders correctly when opened in xLights.
- **FR-004**: The system MUST support at least four curve shape transforms: linear (proportional), logarithmic (fast start), exponential (slow start), and step (binary threshold).
- **FR-005**: Value curves MUST be limited to a reasonable number of control points (no more than 100 per parameter per effect placement) to avoid performance issues in xLights.
- **FR-006**: The system MUST provide a CLI flag to control value curve generation, accepting at minimum: `all` (default), `brightness`, `speed`, `color`, and `none`.
- **FR-007**: The system MUST support a config file setting for value curve mode in generation profiles, with CLI flags taking precedence when both are specified.
- **FR-008**: The system MUST support energy-driven color-mix value curves on all songs, using L5 energy data to modulate color intensity and saturation.
- **FR-008a**: The system MUST additionally apply chord-triggered color accent shifts when chord analysis density exceeds 20 events per minute AND chord quality score exceeds 0.4.
- **FR-008b**: When chord data is sparse (below 20 events/min), low quality (below 0.4), or entirely missing, the system MUST fall back to energy-only color modulation without error.
- **FR-009**: Effect placements shorter than 1 second MUST use static parameter values instead of generating a degenerate value curve.
- **FR-010**: When analysis data is missing or unavailable for a given time range, the system MUST fall back to static parameter values without error.

### Key Entities

- **Value Curve**: A series of control points (time position, value) that define how a single effect parameter changes over the duration of one effect placement. Time positions are normalized 0.0 to 1.0; values are within the parameter's defined range.
- **Analysis Mapping**: A rule that connects a piece of analysis data (e.g., L5 energy) to an effect parameter (e.g., brightness), defining the input/output ranges and curve shape transform.
- **Curve Shape**: The mathematical transform applied to map analysis data to parameter values — linear, logarithmic, exponential, or step.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Generated sequences produce visually dynamic effects that vary in brightness with the music — no static-looking placements on songs with clear dynamic range.
- **SC-002**: Value curves in the output file render correctly in xLights without errors, crashes, or visual artifacts on at least 3 test songs across different genres.
- **SC-003**: Users can disable value curves and produce a valid sequence with static parameters in a single step (no manual editing of the output required).
- **SC-004**: Effect placements with value curves contain no more than 100 control points per parameter, ensuring xLights renders them without performance degradation.
- **SC-005**: The generation time increase from enabling value curves is less than 20% compared to static-only generation.

## Assumptions

- The existing value curve generation algorithm, curve shape transforms, and xSQ encoding are correct and have passing tests — this feature is primarily about activation, not reimplementation.
- The analysis pipeline reliably produces L5 energy data at 43-47 fps for all songs. L6 chord data (Chordino) varies in density (13-41 events/min) and quality (0.30-0.60) — hence the threshold-based activation for chord-triggered color accents.
- xLights supports inline value curves in the `.xsq` format using the `Active=TRUE|Id=...|Type=Ramp|Values=...` encoding.
- The existing analysis-to-parameter mappings defined in the effect library are reasonable starting points and can be tuned after initial integration.
- The 100-point control limit is sufficient for xLights rendering fidelity while staying within performance bounds.
