# Feature Specification: Effect Themes

**Feature Branch**: `019-effect-themes`
**Created**: 2026-03-26
**Status**: Draft
**Reference Design**: `docs/effect-themes-library.md`
**Dependencies**: Feature 018 (Effect Library — provides the individual effect definitions this feature composes from)

## Context

This feature builds the **theme catalog** — a JSON library of named composite "looks" that stack multiple effects from the effect library (018) into layered visual recipes. Each theme defines an effect stack with blend modes, color palette, and parameter overrides that create a specific visual mood.

Themes are tagged by mood, occasion (Christmas, Halloween, general), and genre affinity (rock, pop, classical, any) so that downstream consumers (the sequence generator) can curate which themes to use for a given show.

This is the **data catalog only**. Mood detection, section-to-theme selection, cycling logic, and show profile curation are all sequence generator concerns — not part of this feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Built-in Theme Catalog Exists (Priority: P1)

The system ships with a JSON file containing at least 20 themes organized by mood collection, tagged with occasion and genre affinity. Each theme defines a multi-layer effect stack, color palette, and blend modes — all referencing effects from the effect library (018).

**Why this priority**: The catalog must exist before anything can use it.

**Independent Test**: Load the built-in themes JSON, validate it, confirm 20+ themes present with valid effect references, layer stacks, color palettes, and tags.

**Acceptance Scenarios**:

1. **Given** the built-in themes JSON, **When** it is loaded and validated, **Then** it contains at least 20 theme definitions.
2. **Given** the themes, **When** grouped by mood, **Then** there are at least 4 mood collections (Ethereal, Aggressive, Dark, Structural) with at least 3 themes each.
3. **Given** the themes, **When** filtered by occasion tag, **Then** there are at least 4 Christmas themes, at least 2 Halloween themes, and at least 12 general themes.
4. **Given** any theme, **When** its effect stack is inspected, **Then** every effect name in the stack exists in the effect library (018).
5. **Given** any theme, **When** its color palette is inspected, **Then** it contains at least 2 colors defined as hex RGB values.
6. **Given** any theme with multiple layers, **When** its layers are inspected, **Then** each layer has a valid blend mode, and modifier effects (from the effect library's layer_role) are never on the bottom layer.

---

### User Story 2 - Programmatic Loading and Querying (Priority: P2)

Downstream code can load the theme library, look up themes by name, and query by mood, occasion, or genre affinity.

**Why this priority**: The library is useless if other modules can't consume it.

**Independent Test**: Load the library, look up "Inferno" by name, query all Christmas themes, query all Aggressive themes.

**Acceptance Scenarios**:

1. **Given** the library is loaded, **When** code looks up a theme by name, **Then** the full definition is returned or None if not found.
2. **Given** the library is loaded, **When** code queries by mood (e.g., "aggressive"), **Then** only themes in that mood collection are returned.
3. **Given** the library is loaded, **When** code queries by occasion (e.g., "christmas"), **Then** only themes tagged with that occasion are returned.
4. **Given** the library is loaded, **When** code queries by genre (e.g., "rock"), **Then** themes tagged with that genre or "any" are returned.
5. **Given** the library is loaded, **When** code queries by mood + occasion (e.g., aggressive + christmas), **Then** only themes matching both filters are returned.

---

### User Story 3 - Custom Theme Overrides (Priority: P3)

A user can place custom theme JSON files in a known directory. Custom themes override built-in ones by name, and entirely new themes can be added.

**Why this priority**: Every show designer has preferences. Same pattern as the effect library.

**Independent Test**: Place a custom "Inferno" theme with different colors, load the library, verify the custom version is returned.

**Acceptance Scenarios**:

1. **Given** a custom theme with the same name as a built-in theme, **When** the library loads, **Then** the custom version overrides the built-in one.
2. **Given** a custom theme with a new name, **When** the library loads, **Then** it is added alongside built-in themes.
3. **Given** an invalid custom theme (e.g., referencing a nonexistent effect), **When** the library loads, **Then** it is skipped with a warning.

---

### Edge Cases

- What happens when a theme references an effect not in the effect library? Validation logs a warning. The theme is loaded but flagged as having missing effects.
- What happens when the custom themes directory doesn't exist? Only built-in themes are returned, no error.
- What happens when a theme's bottom layer uses a modifier effect? Validation catches this — modifier effects cannot be on the bottom layer.
- What happens when a theme has only one color in its palette? Validation logs a warning — at least 2 colors are recommended but a single-color theme is still valid.

## Requirements *(mandatory)*

### Functional Requirements

#### Theme Catalog

- **FR-001**: The system MUST ship a built-in JSON catalog of at least 20 themes.
- **FR-002**: Each theme MUST include: unique name, mood label, occasion tag (christmas, halloween, general), genre affinity tag (rock, pop, classical, any), intent description, an ordered list of effect layers, and a color palette.
- **FR-003**: Each effect layer MUST specify: effect name (matching the effect library), blend mode, and parameter overrides (key-value pairs overriding the effect's defaults for this theme's context).
- **FR-004**: Valid blend modes MUST include at least: Normal, Additive, Subtractive, 1 is Mask, 2 is Mask.
- **FR-005**: Color palettes MUST contain at least 2 hex RGB color values.
- **FR-006**: The themes catalog MUST be stored as a JSON file with a documented, versioned schema.
- **FR-007**: The catalog MUST include at least 3 themes per mood collection (Ethereal, Aggressive, Dark, Structural), at least 4 Christmas-specific themes, and at least 2 Halloween-specific themes.

#### Programmatic API

- **FR-008**: The system MUST provide a function to load the theme library, returning structured data.
- **FR-009**: The system MUST provide lookup by theme name (case-insensitive).
- **FR-010**: The system MUST provide queries by mood, occasion, genre, or any combination.
- **FR-011**: The system MUST validate that all effect references in themes exist in the effect library at load time.

#### Customization

- **FR-012**: The system MUST support custom theme overrides from a user-writable directory.
- **FR-013**: Custom themes MUST override built-in themes of the same name.
- **FR-014**: The system MUST validate custom themes at load time, skipping invalid ones with a warning.

### Key Entities

- **Theme**: A named composite "look" — ordered list of effect layers, color palette, and metadata tags (mood, occasion, genre). References effects from the effect library by name.
- **EffectLayer**: One layer in a theme's stack. Specifies effect name, blend mode, and parameter overrides (key-value pairs).
- **ColorPalette**: A list of hex RGB colors associated with a theme.
- **MoodCollection**: A group of themes sharing a mood label (Ethereal, Aggressive, Dark, Structural).
- **ThemeLibrary**: The combined set of built-in + custom themes, queryable by mood, occasion, and genre.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The built-in catalog contains at least 20 themes across 4 mood collections plus holiday-specific themes.
- **SC-002**: Every effect name referenced in every theme exists in the effect library — verified at load time.
- **SC-003**: The library loads and validates in under 1 second.
- **SC-004**: Queries by mood, occasion, and genre return correct subsets — verified by unit tests.
- **SC-005**: A custom theme override replaces the built-in version.
- **SC-006**: At least 4 Christmas themes and 2 Halloween themes are included with appropriate color palettes (reds/greens/golds for Christmas; oranges/purples/blacks for Halloween).

## Assumptions

- The effect library (feature 018) is available and loaded. Theme validation checks effect names against it.
- Mood detection, section-to-theme selection, cycling logic, and show profile curation are NOT part of this feature — they belong to the sequence generator.
- Color palettes in themes are starting suggestions. The sequence generator may override them based on L6 harmonic color analysis.
- Buffer settings (rotation, zoom, blur) may be included in layer parameter overrides using xLights B_ prefix names.
- No CLI tools in v1. Users edit JSON directly for customization.
- Custom themes go in `~/.xlight/custom_themes/`.

## Theme List (planned)

### General / Mood-Based (from design doc)

**Ethereal**: Stellar Wind, Aurora, Bio-Lume
**Aggressive**: Inferno, Molten Metal, Tracer Fire
**Dark**: The Void, Glitch City, The Kraken
**Structural**: Cyber Grid, Scanning Beam, The Zipper

### Christmas

- **Winter Wonderland** (Ethereal) — Snowflakes + Twinkle + Color Wash in cool blues/whites
- **Candy Cane Chase** (Structural) — Single Strand chase in red/white alternating
- **Warm Glow** (Ethereal) — Slow Fire (gold) + Twinkle in warm amber/gold
- **North Star** (Structural) — Pinwheel (white center) + Ripple outward in gold
- **Festive Flash** (Aggressive) — Shockwave (red/green) + Strobe on beats
- **Silent Night** (Ethereal) — Slow Color Wash (deep blue/purple) + Snowflakes

### Halloween

- **Haunted Pulse** (Dark) — Plasma (purple/green) + slow Strobe flickers
- **Jack-o-Lantern** (Aggressive) — Fire (orange) + Shockwave on beats
- **Graveyard Fog** (Dark) — Liquid (grey/green) + Tendril creeping movement
