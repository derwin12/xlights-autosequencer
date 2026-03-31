# Feature Specification: Layout Group Editor

**Feature Branch**: `022-layout-group-editor`
**Created**: 2026-03-30
**Status**: Draft
**Input**: User description: "UI tool for grouping a layout — assign models to tiers, drag and drop between groups, preserve original grouping, save edits separately, support ungrouped models"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Auto-Generated Grouping (Priority: P1)

A user has an xLights layout file and wants to see how the system automatically grouped their props into tiers. They open the layout group editor, which loads the layout, runs the auto-grouping algorithm, and displays all 8 tiers with their groups and member props. They can see which props are in which groups, expand/collapse tiers, and get an overview of the full grouping before making any changes.

**Why this priority**: Without being able to see the current grouping, users cannot evaluate it or know what to change. This is the foundation that all editing builds on.

**Independent Test**: Can be tested by loading any xLights layout file and verifying all tiers, groups, and props display correctly with accurate membership counts.

**Acceptance Scenarios**:

1. **Given** an xLights layout file, **When** the user opens the layout group editor, **Then** the system displays all 8 tiers with their auto-generated groups and member props.
2. **Given** the editor is open, **When** the user views a tier, **Then** they see all groups in that tier with each group's name and member prop list.
3. **Given** the editor is open, **When** the user views any prop, **Then** they see the prop's name, type, pixel count, and which groups it belongs to across all tiers.
4. **Given** the editor is open, **When** there are props not assigned to any tier-specific group (beyond the Tier 1 base group), **Then** those props appear in a visible "Ungrouped" section.

---

### User Story 2 - Drag-and-Drop Tier Assignment (Priority: P1)

The user sees a prop that was placed in the wrong group or wants to reorganize their layout for a better light show. They select a tier tab to focus on one tier at a time, then drag a prop from one group and drop it into another group within that tier. The interface provides visual feedback during the drag (drop targets highlight), and the change takes effect immediately in the display.

**Why this priority**: Drag-and-drop is the core interaction model the user explicitly requested. Without it, the tool is just a read-only viewer.

**Independent Test**: Can be tested by dragging props between groups and verifying the membership updates are reflected immediately in the display.

**Acceptance Scenarios**:

1. **Given** a prop in Group A, **When** the user drags it to Group B within the same tier, **Then** the prop moves from Group A to Group B and both groups update their member lists.
2. **Given** a prop being dragged, **When** it hovers over a valid drop target, **Then** the drop target highlights to indicate it can accept the prop.
3. **Given** a prop in a group, **When** the user drags it to the "Ungrouped" section for that tier, **Then** the prop is removed from its group and appears in "Ungrouped".
4. **Given** an ungrouped prop, **When** the user drags it to a group, **Then** the prop is added to that group and removed from "Ungrouped".
5. **Given** a multi-select of props, **When** the user drags the selection to a group, **Then** all selected props move together.

---

### User Story 3 - Persist Edits Separately from Original (Priority: P1)

After making changes, the user wants to save their work. The system preserves the original auto-generated grouping untouched and saves only the user's edits (moves, additions, removals) to a separate edit file. This way the user can always see what the algorithm produced versus what they changed, and re-running the auto-grouper doesn't destroy their manual adjustments.

**Why this priority**: The user explicitly requires that original grouping is preserved and edits are stored separately. This is a core architectural requirement.

**Independent Test**: Can be tested by making edits, saving, and verifying two separate files exist: the original grouping and the edits overlay.

**Acceptance Scenarios**:

1. **Given** the user has made changes to group assignments, **When** they click Save, **Then** the edits are written to a separate edit file while the original auto-generated grouping file remains unchanged.
2. **Given** an existing edit file from a previous session, **When** the user opens the editor, **Then** the edits are applied on top of the original grouping so the user sees their previously saved state.
3. **Given** edits have been saved, **When** the user wants to see what changed, **Then** the system can show which props were moved from their original auto-generated positions (visual diff indicator).
4. **Given** edits have been saved, **When** the user wants to discard all manual changes, **Then** they can reset to the original auto-generated grouping.

---

### User Story 4 - Create and Remove Groups (Priority: P2)

The user wants to create a new custom group within a tier (e.g., a hero group for a new focal prop they added this year) or remove a group that doesn't apply to their layout. They can also rename groups to match their mental model.

**Why this priority**: Structural editing (add/remove/rename groups) is the natural next step after being able to move props between existing groups. Valuable but not the minimum viable interaction.

**Independent Test**: Can be tested by creating a new group, adding props to it, renaming it, and verifying it persists correctly in the edit file.

**Acceptance Scenarios**:

1. **Given** a tier, **When** the user creates a new group, **Then** a new empty group appears in that tier with a user-provided name following the tier's naming convention.
2. **Given** a group with no members, **When** the user deletes it, **Then** the group is removed and its former members (if any) appear in "Ungrouped" for that tier.
3. **Given** a group, **When** the user renames it, **Then** the group's display name updates and the rename is recorded in the edit file.
4. **Given** a user-created group, **When** the user saves, **Then** the new group and its members are recorded in the edit file.

---

### User Story 5 - Export Merged Grouping for Sequencing (Priority: P2)

The user is satisfied with their grouping and wants to use it for sequence generation. They export the merged result (original + edits) so the sequence generator can consume the final tier assignments. The export produces the grouping data in the format the generator expects.

**Why this priority**: The grouping editor's value is realized when the edited layout feeds into sequence generation. Without export, edits are stranded.

**Independent Test**: Can be tested by making edits, exporting, and verifying the generator can load and use the exported grouping data.

**Acceptance Scenarios**:

1. **Given** edits have been applied, **When** the user exports, **Then** the system produces a merged grouping file that combines the original auto-generated groups with all user edits applied.
2. **Given** an exported grouping, **When** the sequence generator loads it, **Then** it uses the edited tier assignments instead of re-running the auto-grouper.
3. **Given** the user has not made any edits, **When** they export, **Then** the exported file matches the original auto-generated grouping exactly.

---

### Edge Cases

- What happens when the user loads a layout with no props (empty layout file)? The system should display a message indicating no props were found and disable editing controls.
- What happens when a prop is removed from all groups across all tiers? It should appear in the "Ungrouped" section and remain available for assignment.
- What happens when the user drags a prop to a group where it already exists? The drop should be rejected with a visual indication (no duplicate membership within the same tier).
- What happens when the underlying layout file changes (user adds new props in xLights)? On reload, new props should appear in "Ungrouped" and existing edits for unchanged props should be preserved.
- What happens when the user tries to save but the edit file location is not writable? The system should display an error message indicating the save failed and suggest an alternative location.
- What happens when a group becomes empty after all props are dragged out? The empty group remains visible (not auto-deleted) so the user can drag props back in. Users must explicitly delete empty groups.
- What happens when a prop is removed from the Tier 1 base group and from all other tier groups? The prop is effectively excluded from sequencing. The system should visually indicate fully excluded props so users can confirm this is intentional (e.g., tune-to signs, static displays).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST load an xLights layout file and display all props organized by the 8-tier grouping hierarchy (Canvas, Spatial, Architecture, Rhythm, Fidelity, Prop Type, Compound, Heroes).
- **FR-002**: System MUST run the existing auto-grouping algorithm on the loaded layout and display the resulting groups as the baseline grouping.
- **FR-003**: System MUST display an "Ungrouped" section per tier showing props that are not assigned to any group within that tier.
- **FR-004**: System MUST present a per-tier tabbed view where the user selects one tier at a time to view and edit its groups.
- **FR-004a**: System MUST support drag-and-drop of individual props between groups within the currently selected tier.
- **FR-005**: System MUST support drag-and-drop of multiple selected props (multi-select) between groups.
- **FR-006**: System MUST support dragging props to and from the "Ungrouped" section.
- **FR-007**: System MUST provide visual feedback during drag operations: highlight valid drop targets and indicate invalid drops.
- **FR-008**: System MUST persist user edits to a separate edit file (`<md5>_grouping_edits.json`, keyed by MD5 hash of the layout file content), keeping the original auto-generated grouping unmodified.
- **FR-009**: System MUST load and apply previously saved edits on top of the auto-generated grouping when reopening a layout.
- **FR-010**: System MUST allow users to reset all edits and return to the original auto-generated grouping.
- **FR-011**: System MUST allow users to create new groups within any tier.
- **FR-012**: System MUST allow users to delete groups (moving displaced members to "Ungrouped").
- **FR-013**: System MUST allow users to rename groups.
- **FR-014**: System MUST export a merged grouping (original + edits) as a `_grouping.json` file that the sequence generator reads in place of re-running the auto-grouping algorithm.
- **FR-015**: System MUST visually indicate which props have been moved from their original auto-generated positions (edit indicators).
- **FR-016**: System MUST prevent duplicate prop membership within the same tier (a prop can only belong to one group per tier).
- **FR-017**: System MUST display prop metadata (name, type, pixel count) to help users make informed grouping decisions.
- **FR-018**: When the underlying layout file has changed (new or removed props), the system MUST detect the changes on reload: new props appear in "Ungrouped", removed props are pruned from edits, and existing edits for unchanged props are preserved.
- **FR-019**: All 8 tiers MUST be editable, including Tier 1 (Canvas/Base). Props removed from the Tier 1 base group are excluded from the whole-house wash and effectively excluded from sequencing unless they remain in other tier groups.

### Key Entities

- **Layout**: The complete set of props parsed from an xLights layout file. Identified by the source file path. Contains all props with their positions, types, and attributes.
- **Prop**: An individual lighting model/fixture in the layout. Has a name, display type, pixel count, normalized position, and aspect ratio. A prop can belong to one group per tier.
- **Tier**: One of the 8 hierarchical grouping levels (Canvas, Spatial, Architecture, Rhythm, Fidelity, Prop Type, Compound, Heroes). Each tier serves a distinct purpose in the lighting hierarchy.
- **Group**: A named collection of props within a specific tier. Has a name (following the tier's naming convention), a tier assignment, and a member list.
- **Grouping**: The complete assignment of all props to groups across all 8 tiers. Consists of the auto-generated baseline plus any user edits.
- **Edit File**: A separate record of all user modifications to the auto-generated grouping: prop moves, group creations, group deletions, and renames. Keyed by MD5 hash of the layout file content (stored as `<md5>_grouping_edits.json`), matching the project's existing caching pattern. Layered on top of the baseline to produce the current state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can load a layout and see the complete tier grouping within 3 seconds of opening the editor.
- **SC-002**: Users can reassign a prop to a different group via drag-and-drop in a single gesture (under 2 seconds per prop).
- **SC-003**: Users can complete a full grouping review and edit session (inspecting all tiers, moving 5-10 props) in under 10 minutes for a layout with up to 100 props.
- **SC-004**: The original auto-generated grouping is never modified by user actions — 100% separation between baseline and edits.
- **SC-005**: After saving and reopening, the user sees the exact same grouping state they left — zero data loss across sessions.
- **SC-006**: The exported merged grouping is accepted by the sequence generator with no additional transformation required.
- **SC-007**: Users can identify which props have been manually moved versus auto-assigned at a glance (visual diff indicators present on all edited props).

## Clarifications

### Session 2026-03-30

- Q: How should the editor organize editing across the 8 tiers? → A: Per-tier view — user selects a tier tab and edits one tier at a time.
- Q: What should the export produce? → A: A JSON grouping file (`_grouping.json`) that the generator reads instead of re-running auto-grouping.
- Q: How should the edit file be keyed to its source layout? → A: MD5 hash of layout file content — edit file stored as `<md5>_grouping_edits.json`, matching the existing caching pattern.
- Q: Should Tier 1 (Canvas/Base) be editable or read-only? → A: Fully editable — users need to exclude props that shouldn't be sequenced (e.g., tune-to signs, static displays).

## Assumptions

- The existing auto-grouping algorithm (feature 017) is available and produces the 8-tier PowerGroup structure.
- The existing layout parser can read xLights `xlights_rgbeffects.xml` files and extract prop metadata.
- The existing Flask-based review server pattern can be extended for the layout group editor interface.
- Users have a modern web browser with drag-and-drop support.
- Layouts typically contain between 10 and 200 props — the UI should handle this range comfortably.
- A single user edits the grouping at a time (no concurrent editing).

## Dependencies

- Existing layout parser (`src/grouper/layout.py`) for reading xLights layout files and extracting props.
- Existing auto-grouping algorithm (`src/grouper/grouper.py`) for generating the baseline tier assignments.
- Existing prop classifier (`src/grouper/classifier.py`) for computing pixel counts, aspect ratios, and hero detection.
- Sequence generator (feature 020) must be updated to optionally consume the edited grouping file instead of re-running auto-grouping.

## Scope Boundaries

**In Scope**:
- Browser-based interactive editor for viewing and editing tier group assignments
- Drag-and-drop prop reassignment between groups
- Separate edit file persistence (original grouping preserved)
- "Ungrouped" section for unassigned props
- Group creation, deletion, and renaming
- Export of merged grouping for downstream consumption
- Visual indicators for edited vs. auto-assigned props

**Out of Scope**:
- Modifying the auto-grouping algorithm itself (this tool edits its output, not its logic)
- Editing prop attributes (position, pixel count, display type) — those are defined in xLights
- 2D/3D spatial visualization of props on the layout (this is a list/card-based editor, not a spatial canvas)
- Writing groups back to the xLights XML file directly (export produces a `_grouping.json` file for the generator)
- Multi-user concurrent editing
- Batch editing across multiple layout files
