# Feature Specification: xLights Effect Library

**Feature Branch**: `018-effect-themes-library`
**Created**: 2026-03-26
**Status**: Draft
**Reference**: xLights effect list (56 built-in effects), `docs/effect-themes-library.md` (for downstream theme context)

## Clarifications

### Session 2026-03-26

- Q: How are effect parameter names, types, and ranges populated? → A: Hybrid — scrape the xLights manual for initial data, then hand-tweak for accuracy and completeness.
- Q: How detailed should analysis-to-parameter mappings be? → A: Structured mappings with concrete analysis field paths, parameter names, and mapping types (direct, inverted, threshold-trigger) — no formula language.
- Q: Should the CLI include category-based filtering? → A: No — skip category filtering. Categories exist as organizational labels in the data only.
- Q: How does the user interact with this? → A: v1 is the data catalog only — JSON schema, built-in definitions, programmatic loading/validation. CLI browse/export/import tools deferred to a later feature. Users edit JSON directly if they want to customize.

## Context

This feature builds the **foundational effect catalog** — a JSON file describing individual xLights effects, their parameters, which prop types they work best on, and how analysis data (L0–L6) can drive their parameters. This is the building-block layer that a separate Themes feature will later compose into named "looks" (Inferno, Aurora, etc.).

The primary consumers of this library are **other code modules** (themes engine, sequence generator), not end users directly. Users can read and edit the JSON if they want, but no CLI tools for browsing or customization are included in v1.

This is NOT about composite stacks or mood selection. It is about: "What does each xLights effect do, how do you configure it, and what analysis data can make it reactive?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Built-in Effect Catalog Exists (Priority: P1)

The system ships with a JSON file containing definitions for at least 35 xLights effects. Each definition includes the effect's parameters, prop-type suitability, and analysis-to-parameter mappings. The file conforms to a documented schema.

**Why this priority**: Nothing downstream (themes, sequence generator) can work without this data existing. This is the foundation.

**Independent Test**: Load the built-in JSON file, validate it against the schema, and confirm all 35+ effects are present with complete definitions.

**Acceptance Scenarios**:

1. **Given** the built-in library JSON, **When** it is loaded and validated, **Then** it contains at least 35 effect definitions matching the documented schema.
2. **Given** any effect definition in the library, **When** its fields are inspected, **Then** it has a name, category, description, intent, at least 3 parameters with type/default/range, and prop-type suitability for all 5 prop types.
3. **Given** the library, **When** reactive effects are counted, **Then** at least 20 effects have one or more analysis-to-parameter mappings.

---

### User Story 2 - Programmatic Loading and Querying (Priority: P2)

Downstream code (themes engine, sequence generator) can load the effect library, look up effects by name, and query their parameters and analysis mappings programmatically.

**Why this priority**: The library is useless if other modules can't consume it. This is the API layer.

**Independent Test**: Write code that loads the library, looks up "Fire" by name, reads its parameters, and reads its analysis mappings — all returning structured data.

**Acceptance Scenarios**:

1. **Given** the library is loaded, **When** code looks up an effect by name, **Then** the full definition is returned or a clear "not found" result if the name doesn't exist.
2. **Given** a loaded effect definition, **When** code reads its analysis mappings, **Then** each mapping has a parameter name, analysis level, field path, mapping type, and description.
3. **Given** the library is loaded, **When** code queries for effects suitable for a prop type (e.g., "matrix"), **Then** only effects rated Ideal or Good for that prop type are returned.
4. **Given** the library, **When** code requests coverage stats, **Then** it returns the count of cataloged effects and a list of uncatalogued xLights effect names.

---

### User Story 3 - Custom Overrides via JSON (Priority: P3)

A user can place custom effect definition JSON files in a known directory. When the library loads, custom definitions override built-in ones of the same name. No CLI tooling required — users edit JSON directly.

**Why this priority**: Customization is important but the mechanism is simple (file on disk). No tooling needed for v1.

**Independent Test**: Place a custom Fire definition in the custom directory, load the library, and confirm the custom version is returned instead of the built-in one.

**Acceptance Scenarios**:

1. **Given** a custom effect JSON in the custom directory, **When** the library loads, **Then** the custom definition overrides the built-in one of the same name.
2. **Given** a custom effect JSON with invalid fields, **When** the library loads, **Then** it is skipped with a warning and the built-in version is used instead.
3. **Given** no custom directory exists, **When** the library loads, **Then** only built-in definitions are returned with no errors.

---

### Edge Cases

- What happens when the built-in JSON file is missing or corrupted? The system raises a clear error at load time — this is a fatal condition since downstream features depend on it.
- What happens when a custom definition references an xLights effect name not in the known set of 56? It is accepted — users may be running a newer xLights version with additional effects.
- What happens when a custom definition has a parameter with min > max? Validation logs a warning and skips the invalid definition.
- What happens when xLights adds new effects? Users add custom definitions. The built-in catalog is updated in future releases.

## Requirements *(mandatory)*

### Functional Requirements

#### Data Catalog

- **FR-001**: The system MUST ship a built-in JSON catalog of individual xLights effect definitions, covering at least: On, Off, Color Wash, Fill, Shimmer, Strobe, Twinkle, Bars, Butterfly, Circles, Curtain, Fan, Marquee, Pinwheel, Plasma, Ripple, Shape, Shockwave, Spirals, Wave, Fire, Fireworks, Liquid, Meteors, Snowflakes, Tree, Tendril, Single Strand (Chase), Morph, Warp, Music, VU Meter, Text, Pictures, Kaleidoscope.
- **FR-002**: Each effect definition MUST include: effect name (matching xLights internal name), category label, brief description, intent (when to use it), a list of configurable parameters with name/type/default/min/max/description, and prop-type suitability ratings.
- **FR-003**: Prop-type suitability MUST be rated for at least these prop types: Matrix/High-density, Outline/Low-density, Arch/Curved, Vertical/Straight, Tree/Wrapped. Ratings are: Ideal, Good, Possible, Not Recommended.
- **FR-004**: Each effect definition MUST include zero or more analysis-to-parameter mappings, each specifying: the parameter name, the analysis level (L0–L6), the specific analysis field path, the mapping type (direct, inverted, or threshold-trigger), and a description of the recommended mapping behavior.
- **FR-005**: The library MUST be stored as a JSON file with a documented, versioned schema.
- **FR-006**: Effect parameter data MUST be initially sourced by scraping xLights C++ source code from the GitHub repository, then hand-reviewed and corrected for accuracy.

#### Programmatic API

- **FR-007**: The system MUST provide a function to load the built-in library from its JSON file, returning structured data.
- **FR-008**: The system MUST provide lookup by effect name, returning the full definition or a not-found result.
- **FR-009**: The system MUST provide a query for effects suitable for a given prop type (filtering by Ideal or Good suitability).
- **FR-010**: The system MUST provide a coverage query returning cataloged vs. uncatalogued xLights effect names.

#### Custom Overrides

- **FR-011**: The system MUST check a user-writable directory for custom effect definition JSON files at load time.
- **FR-012**: Custom definitions MUST override built-in definitions of the same name.
- **FR-013**: The system MUST validate custom definitions at load time, skipping invalid ones with a warning.

### Key Entities

- **EffectDefinition**: A single xLights effect described for use in sequencing. Has a name, category, description, intent, parameter list, prop-type suitability ratings, and analysis mappings.
- **EffectParameter**: A configurable property of an effect. Has a name, type (numeric, color, choice, boolean), default value, min/max range, and description.
- **AnalysisMapping**: A structured rule linking an effect parameter to an analysis level. Specifies the parameter name, analysis level (L0–L6), analysis field path, mapping type (direct, inverted, threshold-trigger), and a behavior description. Concrete enough for downstream tools to auto-wire without a formula language.
- **PropSuitability**: A rating of how well an effect works on a given prop type. Prop types: Matrix, Outline, Arch, Vertical, Tree. Ratings: Ideal, Good, Possible, Not Recommended.
- **EffectLibrary**: The combined set of built-in + custom definitions, with custom overriding built-in by name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The built-in catalog contains at least 35 individual effect definitions covering the effects listed in FR-001.
- **SC-002**: Every cataloged effect has at least 3 defined parameters with valid type, default, and range.
- **SC-003**: At least 20 effects have one or more structured analysis-to-parameter mappings defined.
- **SC-004**: Every cataloged effect has prop-type suitability ratings for all 5 prop types.
- **SC-005**: The library JSON loads and validates in under 1 second.
- **SC-006**: A downstream module can load the library, look up an effect by name, and read its parameters in a single function call.
- **SC-007**: At least 30 of the 56 xLights effects are used across all definitions; uncovered effects are documented.

## Assumptions

- xLights effect names and parameter names are stable across versions. The library schema includes a `target_xlights_version` field for tracking.
- The built-in library ships as a read-only JSON file bundled with the tool. Custom definitions go in `~/.xlight/custom_effects/`.
- Effect parameter types and ranges are initially scraped from xLights C++ source code on GitHub, then hand-tweaked for accuracy. Some parameters may need further refinement after testing against real xLights sequences.
- This feature does NOT include composite effect stacks (themes), mood-based selection, or section-to-effect mapping. Those are a separate Themes feature that will consume this library.
- This feature does NOT include CLI tools for browsing, exporting, or importing effects. Users edit JSON directly for customization. CLI tooling is a future feature.
- Faces, DMX, Moving Head, and Servo effects are out of scope — Faces will be a separate feature; DMX/hardware effects are layout-specific.

## Not Covered in Built-in Catalog (v1)

The following xLights effects are not included in the v1 built-in catalog. Users can add them via custom JSON definitions:

- **Faces** — separate singing-face feature planned
- **DMX / Moving Head / Servo** — hardware-specific, too layout-dependent
- **Adjust** — layer modification utility, not a standalone visual effect
- **Duplicate** — model mirroring, not an effect to sequence
- **State** — prop-specific state control, too layout-dependent
- **Glediator** — legacy import format
- **Life** — cellular automaton, novelty
- **Spirograph** — mathematical curves, niche
- **Guitar** — guitar tablature visualization, niche
- **Shader** — requires GLSL programming, may be added as an advanced option later
- **Piano** — piano visualization, niche
- **Video** — requires external media files
- **Candle** — may be added in a future "Warm" category
- **Lightning** — may be added in a future update
- **Snow Storm** — may be added alongside Snowflakes
- **Galaxy** — may be added in a future update
- **Garlands** — may be added in a future update
- **Lines** — may be added in a future update
- **Sketch** — SVG-based, too specialized
