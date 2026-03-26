# Feature Specification: xLights Layout Grouping

**Feature Branch**: `017-xlights-layout-grouping`
**Created**: 2026-03-26
**Status**: Draft
**Reference Design**: `docs/xlight-grouping-design.md`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate Power Groups from Layout (Priority: P1)

A light show designer runs the grouping command against their `xlights_rgbeffects.xml` layout file and receives an updated XML file with all props automatically organized into hierarchical Power Groups. The groups appear in the xLights sequence editor with meaningful names and tier prefixes, ready to receive effects.

**Why this priority**: This is the core deliverable — without this, none of the other stories exist. Every other story is an enhancement on top of this foundation.

**Independent Test**: Run the CLI command against any valid `xlights_rgbeffects.xml` file containing at least 4 props; confirm the output file contains new `<ModelGroup>` elements using the `01_BASE_` through `08_HERO_` prefix conventions.

**Acceptance Scenarios**:

1. **Given** a valid `xlights_rgbeffects.xml` layout file with props that have X/Y coordinates, **When** the grouping command is run with default settings, **Then** the output XML contains at least a `01_BASE_All` group containing every prop, and spatial groups (`02_GEO_`) populated based on normalized coordinates.
2. **Given** a layout with previously generated automated groups (any with `01_BASE_` through `08_HERO_` prefixes), **When** the grouping command is run again, **Then** old automated groups are removed and replaced by freshly computed ones — no duplicates.
3. **Given** a layout with fewer than 4 props total, **When** the grouping command is run, **Then** the algorithm gracefully produces whatever groups are possible and reports the prop count rather than erroring.

---

### User Story 2 - Select a Show Profile (Priority: P2)

A designer working on a fast, energetic rock song selects the "Energetic" profile so that only beat-sync and functional groups are generated, keeping the sequence editor uncluttered. A designer working on a slow holiday song selects "Cinematic" to get only spatial and hero groups.

**Why this priority**: Different song types need different group sets. Profile selection prevents cluttered timelines while ensuring the right groups exist for the musical analysis hierarchy.

**Independent Test**: Run the command with `--profile energetic`, `--profile cinematic`, and `--profile technical` against the same layout file; verify each produces a different, profile-appropriate subset of group tiers.

**Acceptance Scenarios**:

1. **Given** a layout file, **When** the command is run with `--profile energetic`, **Then** the output contains `04_BEAT_`, `03_TYPE_`, and `08_HERO_` groups (if hero props exist) and does NOT contain `02_GEO_` or `05_TEX_` groups.
2. **Given** a layout file, **When** the command is run with `--profile cinematic`, **Then** the output contains `02_GEO_` and `08_HERO_` groups and does NOT contain `04_BEAT_` groups.
3. **Given** a layout file, **When** the command is run with `--profile technical`, **Then** the output contains `05_TEX_` and `01_BASE_` groups only.
4. **Given** no `--profile` flag, **When** the command is run, **Then** all tiers are generated (equivalent to generating everything).

---

### User Story 3 - Rhythmic Beat Groups (Priority: P3)

A designer wants props to step in sets of four to match the 4/4 time signature of the song. They want both a left-to-right linear chase and a center-out symmetrical explosion available as separate named groups.

**Why this priority**: Four-beat groups are the core mechanism connecting musical analysis (L2 bars, L3 beats) to lighting. Without them, the beat-sync pipeline cannot function.

**Independent Test**: Run the command on a layout with at least 8 props spread across the horizontal axis; verify `04_BEAT_LR_1`, `04_BEAT_LR_2`, and `04_BEAT_CO_1` groups appear with exactly 4 prop members each.

**Acceptance Scenarios**:

1. **Given** a layout with 8 horizontally distributed props, **When** grouping runs, **Then** two non-overlapping left-to-right beat groups (`04_BEAT_LR_1`, `04_BEAT_LR_2`) are created, each containing 4 props sorted by X coordinate.
2. **Given** a layout with 8 props, **When** grouping runs, **Then** center-out beat groups (`04_BEAT_CO_*`) are created by sorting props by distance from the horizontal midpoint (0.5 normalized).
3. **Given** a layout where prop count is not divisible by 4, **When** grouping runs, **Then** the final beat group contains the remaining 1–3 props and is still created (not discarded).

---

### User Story 4 - Hero and Sub-Model Detection (Priority: P4)

A designer has a singing face prop with sub-models (Eyes, Mouth) in their layout. The grouping algorithm automatically identifies the face prop and bundles its sub-models into a `08_HERO_Face` group without requiring manual configuration.

**Why this priority**: Hero detection drives vocal and special-moment effects (L0, L4 in the analysis hierarchy). It is critical but only relevant for layouts containing face/tree props.

**Independent Test**: Run the command on a layout containing a prop whose name includes "Face" and at least two sub-model children; verify a `08_HERO_` group is created containing those sub-models.

**Acceptance Scenarios**:

1. **Given** a prop named `SingingFace` with sub-models `SingingFace/Eyes` and `SingingFace/Mouth`, **When** grouping runs, **Then** a `08_HERO_SingingFace` group is created containing both sub-models.
2. **Given** a layout with no props containing "Face" or "Tree" in their name, **When** grouping runs, **Then** no `08_HERO_` groups are created (no false positives).

---

### User Story 5 - CLI Dry-Run and Preview (Priority: P5)

A designer wants to preview what groups will be created before modifying their layout file. They run the command with a `--dry-run` flag and see a summary of groups that would be generated, without any file being written.

**Why this priority**: Modifying `xlights_rgbeffects.xml` is destructive if something goes wrong. A dry-run provides safety before committing changes.

**Independent Test**: Run with `--dry-run`; confirm no files are modified and output shows a human-readable list of group names with member counts.

**Acceptance Scenarios**:

1. **Given** a layout file and `--dry-run`, **When** the command runs, **Then** the source XML file is unchanged and a summary table is printed to stdout showing each group name, tier, and number of members.
2. **Given** a `--dry-run` run followed by a normal run, **When** both complete, **Then** the full run produces exactly the groups previewed in the dry-run.

---

### Edge Cases

- What happens when a layout has only 1 prop? Algorithm should produce a `01_BASE_All` group with that single prop and skip tiers that require multiple props.
- What happens when all props share identical X coordinates (e.g., a single vertical strand)? Beat groups should still be created; spatial Left/Center/Right bins may all contain the same props.
- What happens when a prop has no coordinate data (X=0, Y=0)? The prop is still included in `01_BASE_All` and treated as position (0,0) for spatial calculations.
- What happens when `xlights_rgbeffects.xml` contains no `<model>` elements at all? The command exits with a clear error message and does not write an empty groups section.
- What happens when the input file is not valid XML? The command fails fast with a clear parse error and does not modify the file.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST read prop definitions (name, X/Y coordinates, pixel count, sub-models) from a standard `xlights_rgbeffects.xml` file.
- **FR-002**: The system MUST normalize all prop coordinates to a 0.0–1.0 scale based on the bounding box of all props in the layout.
- **FR-003**: The system MUST assign every prop to `01_BASE_All` (the whole-house canvas group).
- **FR-004**: The system MUST assign props to spatial bins (`02_GEO_Top`, `02_GEO_Mid`, `02_GEO_Bot`, `02_GEO_Left`, `02_GEO_Center`, `02_GEO_Right`) using normalized thresholds: Top Y>0.66, Mid 0.33<Y<0.66, Bot Y<0.33; Left X<0.33, Center 0.33<X<0.66, Right X>0.66.
- **FR-005**: The system MUST classify props into `03_TYPE_Vertical` (aspect ratio ≥ 1.5) or `03_TYPE_Horizontal` (aspect ratio < 1.5) based on their bounding height-to-width ratio.
- **FR-006**: The system MUST create left-to-right beat groups (`04_BEAT_LR_*`) by sorting props by X coordinate and partitioning into groups of 4.
- **FR-007**: The system MUST create center-out beat groups (`04_BEAT_CO_*`) by sorting props by distance from horizontal midpoint (0.5 normalized) and partitioning into groups of 4.
- **FR-008**: The system MUST classify props into `05_TEX_HiDens` (pixel count > 500) or `05_TEX_LoDens` (pixel count ≤ 500).
- **FR-009**: The system MUST detect hero props by searching for "Face", "MegaTree", or "Tree" (case-insensitive) in prop names and create `08_HERO_` groups for them, including any sub-models.
- **FR-010**: The system MUST remove all previously auto-generated groups (identified by `01_BASE_` through `08_HERO_` tier prefixes) before writing new ones, to prevent duplication.
- **FR-011**: The system MUST write generated groups back into `xlights_rgbeffects.xml` as valid `<ModelGroup>` XML elements compatible with xLights.
- **FR-012**: The system MUST support a `--profile` option accepting `energetic`, `cinematic`, or `technical` to filter which tiers are generated, per the Show Profile definitions in the design doc.
- **FR-013**: The system MUST support a `--dry-run` flag that prints a preview of groups to stdout without modifying any files.
- **FR-014**: The system MUST be invokable as: `xlight-analyze group-layout <path-to-xlights_rgbeffects.xml> [--profile PROFILE] [--dry-run]`.

### Key Entities

- **Prop**: A single light model in the layout. Has a name, X/Y/Z world position, pixel count, aspect ratio, and optionally sub-models.
- **PowerGroup**: A named collection of props assigned to a tier. Has a tier number (1–8), name (with tier prefix), and a list of member prop names.
- **Layout**: The parsed representation of `xlights_rgbeffects.xml` — all props with their coordinates and existing group definitions.
- **ShowProfile**: A named filter (Energetic/Cinematic/Technical) that specifies which group tiers to generate.
- **SpatialBounds**: The computed min/max X, Y, Z values used to normalize all prop coordinates to 0.0–1.0.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given any valid xLights layout with 4+ props, the grouping command completes and produces a modified XML in under 5 seconds.
- **SC-002**: All generated group names conform to the `NN_PREFIX_Name` naming convention — zero non-conforming group names in output.
- **SC-003**: Re-running the command on already-grouped output produces identical results — idempotent behavior verified by file diff.
- **SC-004**: Each `04_BEAT_LR_*` group contains exactly 4 props (except the last group, which may contain 1–4), verified across 3 different layouts.
- **SC-005**: The generated XML loads in xLights without errors, and all generated groups appear in the Groups panel — validated on at least one real layout.
- **SC-006**: Running with no profile produces a superset of all groups produced by any individual profile — show profile filtering is lossless.

## Assumptions

- `xlights_rgbeffects.xml` is the standard xLights project file and contains `<model>` elements with world position coordinate attributes (`WorldPosX`, `WorldPosY` or equivalent).
- Pixel count per prop is available in the XML via standard xLights model attributes.
- Aspect ratio can be computed from the model's bounding box dimensions available in the XML.
- The high-density pixel threshold of 500 from the design doc is the default; it may need tuning against real-world layouts.
- Sub-models are defined as `<subModel>` child elements within their parent `<model>` element in the XML. The slash-name convention (e.g., `SingingFace/Eyes`) is the display name xLights shows in the sequence editor, not a separate top-level model entry.
- The output file is written in-place (overwrites the input). Backup strategy is an implementation decision for the plan phase.
