# Feature Specification: Story Review Flyout Panels

**Feature Branch**: `024-story-review-flyouts`
**Created**: 2026-04-01
**Status**: Draft
**Input**: User description: "Story review flyout panels with section details, moments, and drag-and-drop theme assignment for segments"

## Dependencies

- **[026-theme-editor](../026-theme-editor/spec.md)** (prerequisite) — Provides the theme listing endpoint, theme recommendation endpoint, and theme name validation that the Themes tab (P2) and auto-recommendations (P3) depend on. The P1 stories (Details and Moments tabs) can proceed independently.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse Section Details in a Flyout Panel (Priority: P1)

A user opens the story review UI and clicks on a section in the timeline. A flyout panel slides out from the right edge showing all the numerical details for that section: energy score, tempo, texture, brightness, stem levels, drum style, confidence, and other character data. The user can close the flyout or switch between sections by clicking different segments on the timeline.

**Why this priority**: The details panel is the foundational UI element. Without it, no other flyout content has a home. This replaces the current static sidebar with a more flexible flyout pattern.

**Independent Test**: Can be fully tested by clicking any section and verifying all existing detail fields appear in the flyout panel, and that the flyout opens/closes correctly.

**Acceptance Scenarios**:

1. **Given** a loaded song story, **When** the user clicks a section on the timeline, **Then** a flyout panel slides in from the right showing all section character data (energy, tempo, texture, brightness, stems, drum style, confidence, duration, time range).
2. **Given** an open details flyout, **When** the user clicks a different section, **Then** the flyout updates to show the newly selected section's details without closing and reopening.
3. **Given** an open flyout, **When** the user clicks the close button or clicks outside the flyout, **Then** the flyout slides closed.
4. **Given** the flyout is closed, **When** the user clicks a section, **Then** the flyout opens to the last active tab (details, moments, or themes).

---

### User Story 2 - View Moments in a Separate Flyout Tab (Priority: P1)

A user wants to review the dramatic moments within a section. They click a "Moments" tab in the flyout panel, and the view switches to show the list of moments for the currently selected section. Each moment displays its timestamp, type, description, intensity, and stem source. The user can dismiss or restore moments as they can today.

**Why this priority**: Moments are a core part of the story review workflow. Separating them into their own tab reduces clutter in the details view and gives moments dedicated space.

**Independent Test**: Can be tested by selecting a section, switching to the Moments tab, verifying all moments display correctly, and testing dismiss/restore functionality.

**Acceptance Scenarios**:

1. **Given** a section is selected and the flyout is open, **When** the user clicks the "Moments" tab, **Then** the flyout shows the list of moments for that section with timestamp, type badge, description, and intensity.
2. **Given** the Moments tab is active, **When** the user dismisses a moment, **Then** the moment is visually marked as dismissed and the dismiss action persists.
3. **Given** a section with no moments, **When** the user views the Moments tab, **Then** an empty state message is displayed (e.g., "No dramatic moments detected in this section").

---

### User Story 3 - Browse and Preview Themes (Priority: P2)

A user wants to explore available themes to assign to sections. They click a "Themes" tab in the flyout panel. The tab shows a scrollable list of all available themes. Each theme card displays the theme name, mood, intent description, and a visual color palette swatch showing primary and accent colors. The user can filter themes by mood or occasion.

**Why this priority**: Before users can assign themes, they need to browse and understand them. The theme cards with palette previews and intent descriptions give users the information needed to make informed choices.

**Independent Test**: Can be tested by opening the Themes tab and verifying all 21 built-in themes appear with correct names, moods, intent blurbs, and color swatches.

**Acceptance Scenarios**:

1. **Given** the flyout is open, **When** the user clicks the "Themes" tab, **Then** a scrollable list of theme cards appears, each showing the theme name, mood badge, intent description, and color palette swatches.
2. **Given** the Themes tab is open, **When** the user selects a mood filter (ethereal, aggressive, dark, structural), **Then** only themes matching that mood are displayed.
3. **Given** the Themes tab is open, **When** the user selects an occasion filter (christmas, halloween), **Then** only themes for that occasion are displayed, plus general-occasion themes.
4. **Given** a theme card, **When** the user views it, **Then** the card shows both primary palette colors and accent palette colors as rendered swatches.

---

### User Story 4 - Drag and Drop Themes onto Sections (Priority: P2)

A user finds a theme they like in the Themes tab and drags it from the flyout onto a section in the timeline. The section visually updates to show the assigned theme (color palette indicator on the section bar). The assignment is saved as a section override. The user can also remove an assigned theme by clicking a remove button on the section's theme badge.

**Why this priority**: Theme-to-section assignment is the core creative workflow that enables future sequencing. Drag-and-drop is the most intuitive interaction pattern for this spatial mapping task.

**Independent Test**: Can be tested by dragging a theme card onto a timeline section, verifying the section override is set, and confirming the visual indicator appears on the section.

**Acceptance Scenarios**:

1. **Given** the Themes tab is open, **When** the user drags a theme card, **Then** the timeline sections highlight as valid drop targets.
2. **Given** a theme is being dragged over a timeline section, **When** the user drops the theme, **Then** the section's theme override is set to that theme name, the section bar shows a color palette indicator for the assigned theme, and the change is reflected in the section overrides.
3. **Given** a section has an assigned theme, **When** the user views the section details in the Details tab, **Then** the assigned theme name and palette are shown.
4. **Given** a section has an assigned theme, **When** the user clicks a remove/clear button on the theme assignment, **Then** the theme override is removed and the section returns to its default state.
5. **Given** a theme is dropped on a section, **When** the user saves the story, **Then** the theme assignment persists in the story edits file.

---

### User Story 5 - Auto-Recommended Themes per Section (Priority: P3)

When a user opens the Themes tab, the system shows recommended themes for the currently selected section at the top of the list, clearly marked as "Recommended." Recommendations are based on matching the section's mood (from energy level and trajectory), the song's occasion preference, and the section's role. The user can accept a recommendation with one click or ignore it and choose any other theme.

**Why this priority**: Automation reduces the cognitive load of assigning themes to many sections. However, user choice must always override recommendations, making this an enhancement rather than a core requirement.

**Independent Test**: Can be tested by selecting sections with different energy/mood profiles and verifying that recommended themes change appropriately and are visually distinguished from the rest.

**Acceptance Scenarios**:

1. **Given** a section is selected and the Themes tab is open, **When** the system calculates recommendations, **Then** 2-3 recommended themes appear at the top of the list with a "Recommended" badge and a brief reason (e.g., "Matches high-energy aggressive mood").
2. **Given** recommended themes are shown, **When** the user clicks "Apply" on a recommended theme, **Then** it is assigned to the section as if dragged and dropped.
3. **Given** a section with a low-energy, ethereal character, **When** the user views recommendations, **Then** the recommendations favor ethereal/calm themes (e.g., Warm Glow, Aurora) over aggressive themes (e.g., Inferno, Tracer Fire).
4. **Given** the song has occasion set to "christmas", **When** recommendations are calculated, **Then** christmas-themed themes (Silent Night, Candy Cane Chase, etc.) are prioritized in recommendations.

---

### User Story 6 - Bulk Theme Assignment (Priority: P3)

A user wants to apply the same theme to multiple sections at once. They select multiple sections on the timeline (via shift-click or a selection mode), then drag a theme onto any of the selected sections. The theme is applied to all selected sections. Alternatively, they can click "Apply to Unassigned" from a theme card to assign it to every section that currently has no theme.

**Why this priority**: For songs with many sections, assigning themes one-by-one is tedious. Bulk assignment is a productivity feature that becomes important once the core drag-and-drop workflow is established.

**Independent Test**: Can be tested by selecting 3+ sections, dragging a theme onto one, and verifying all selected sections receive the theme assignment.

**Acceptance Scenarios**:

1. **Given** multiple sections are selected on the timeline, **When** the user drags a theme onto any selected section, **Then** all selected sections receive the theme assignment.
2. **Given** a theme card in the Themes tab, **When** the user clicks "Apply to Unassigned", **Then** the theme is assigned to all sections that do not already have a theme override.
3. **Given** a bulk assignment was made, **When** the user saves the story, **Then** all theme assignments persist.

---

### Edge Cases

- What happens when the user resizes the browser window while a flyout is open? The flyout should remain visible and adjust its position, or collapse if the viewport is too narrow.
- What happens when a section is split or merged while a theme is assigned? The theme assignment should carry forward to the resulting section(s) based on which section retains the original section's identity.
- What happens when themes are dragged but dropped outside any valid section? The drag operation should cancel and no assignment should be made.
- What happens when the user has the flyout open and triggers a re-analysis? The flyout should close or refresh with the new data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST replace the current static right sidebar with a tabbed flyout panel that slides in from the right edge using a push layout (timeline content shifts left to accommodate the panel, preserving full timeline interactivity).
- **FR-002**: The flyout panel MUST have three tabs: "Details", "Moments", and "Themes".
- **FR-003**: The Details tab MUST display all section character data currently shown in the existing sidebar (energy, tempo, texture, brightness, stems, drum style, confidence, duration, time range, accents, active tiers, brightness ceiling).
- **FR-004**: The Moments tab MUST display the list of moments for the selected section with timestamp, type, description, intensity, and dismiss/restore controls.
- **FR-005**: The Themes tab MUST display all available themes as cards showing name, mood, intent description, and rendered color palette swatches (both primary and accent palettes).
- **FR-006**: Users MUST be able to drag a theme card from the Themes tab and drop it onto a timeline section to assign that theme.
- **FR-007**: Theme assignments MUST be stored as section overrides (using the existing overrides.theme field) and persist when the story is saved.
- **FR-008**: The Themes tab MUST show 2-3 recommended themes for the selected section at the top of the list. Recommendations MUST first filter by the song's occasion preference, then rank the filtered themes by mood and energy match to the section.
- **FR-009**: Users MUST be able to filter themes by mood (ethereal, aggressive, dark, structural) and occasion (general, christmas, halloween).
- **FR-010**: Users MUST be able to remove a theme assignment from a section.
- **FR-011**: The flyout MUST remember which tab was last active and reopen to that tab when a new section is selected.
- **FR-012**: Sections with assigned themes MUST display a thin color swatch strip along the bottom edge of their timeline bar, rendering the theme's palette colors. The existing role-based bar color MUST remain unchanged above the strip.
- **FR-013**: Users MUST be able to assign themes to multiple selected sections at once via drag-and-drop or a bulk action.

### Key Entities

- **Flyout Panel**: A slide-in panel anchored to the right edge of the review UI, containing tabbed content views. Replaces the current static sidebar.
- **Theme Card**: A visual representation of a theme displaying its name, mood, intent, and color palettes. Serves as the draggable source for theme assignment.
- **Theme Assignment**: A mapping from a section to a theme, stored in the section's overrides. Represents the user's creative decision about the visual treatment of that section.
- **Theme Recommendation**: A system-generated suggestion matching a theme to a section based on musical and contextual properties. Always overridable by user choice.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view section details, moments, and themes without leaving the timeline view, through a single flyout panel with tabbed navigation.
- **SC-002**: Users can assign a theme to a section via drag-and-drop in under 5 seconds.
- **SC-003**: Theme recommendations match the section's energy and mood profile at least 70% of the time (user does not override the recommendation).
- **SC-004**: All 21 built-in themes are browsable with descriptive information and visual color previews.
- **SC-005**: Theme assignments persist across save/reload cycles with no data loss.
- **SC-006**: Users can assign themes to all sections of a typical song (8-15 sections) in under 3 minutes using recommendations and bulk assignment.

## Clarifications

### Session 2026-04-01

- Q: Should the flyout overlay the timeline or push it left? → A: Push layout — flyout pushes timeline content left, matching current sidebar behavior with slide animation.
- Q: When recommendation criteria conflict (e.g., occasion vs mood), which takes priority? → A: Occasion first — filter themes by occasion, then rank by mood/energy match within the filtered set.
- Q: How should assigned themes be visually indicated on timeline section bars? → A: Palette strip — thin color swatch strip along the bottom edge of the section bar showing the theme's palette colors.

## Assumptions

- The existing overrides.theme field on sections is sufficient for storing theme assignments (no new data model needed).
- The 21 built-in themes provide enough variety for initial use; custom theme creation is out of scope.
- Theme recommendation logic will use simple heuristic matching (mood + energy + occasion) rather than machine learning.
- The flyout panel replaces the current static sidebar entirely — the timeline takes full width when the flyout is closed, and shrinks via push layout when it opens.
- The existing story save/export endpoints will handle theme assignment data without modification since it already supports section overrides. Theme assignments MUST be included in the exported `_story_reviewed.json` to support future sequencing.
- Theme data (listing, filtering, recommendations) is provided by feature 026-theme-editor, which must be implemented before P2/P3 stories.
- Theme names are validated on assignment (via 026) so invalid/nonexistent theme names cannot be stored in overrides.

## Out of Scope

- Creating or editing custom themes (handled by existing theme library feature).
- Generating xLights sequences from theme assignments (future sequencing step).
- Theme preview with animated effect visualization.
- Theme assignment for sub-section time ranges (themes apply to entire sections only).
