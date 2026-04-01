# Research: 024-story-review-flyouts

**Date**: 2026-04-01 | **Branch**: `024-story-review-flyouts`

## R1: Current Sidebar Layout Architecture

**Decision**: Replace the fixed CSS grid column (`grid-template-columns: 1fr 320px`) with a dynamic layout that toggles between `1fr` (flyout closed) and `1fr 360px` (flyout open).

**Rationale**: The current sidebar is a permanent 320px column containing three vertically stacked panels (#section-detail, #stems-panel, #moments-panel) plus a togglable #prefs-panel. Replacing this with a flyout requires:
- Changing the CSS grid from fixed to dynamic column sizing
- Adding a flyout open/close state to the JS `state` object
- Animating the grid column width transition (CSS `transition` on `grid-template-columns`)
- Re-rendering the timeline canvas on resize (canvas width changes when flyout toggles)

**Alternatives considered**:
- Absolute-positioned overlay: rejected per clarification (push layout chosen)
- Keeping sidebar always visible: rejected (user wants toggle-able flyout)

## R2: Tab System Implementation

**Decision**: Build a simple tab system using a tab bar with 3 buttons and content containers that show/hide based on active tab state.

**Rationale**: No tab system exists in the current UI. The three panels are always rendered vertically. The new flyout needs:
- A tab bar at the top of the flyout with "Details", "Moments", "Themes" buttons
- Only one content area visible at a time
- `state.activeTab` to track which tab is shown (persists across section changes per FR-011)
- The Details tab combines current #section-detail and #stems-panel content
- The Moments tab uses current #moments-panel content
- The Themes tab is entirely new (depends on 026-theme-editor for data)

**Alternatives considered**:
- Separate flyout per tab type: rejected (more complex, no UX benefit)
- Accordion/collapsible panels: rejected (tabs are more standard for this pattern)

## R3: Section Selection and Flyout Interaction

**Decision**: Clicking a section on the timeline opens the flyout (if closed) and updates its content. Clicking the flyout close button or empty timeline space (non-section areas) closes it.

**Rationale**: The current `onTimelineClick()` (line 638) calls `selectSection(idx)` which renders all three panels. The new flow:
- `selectSection(idx)` sets `state.flyoutOpen = true` and calls the active tab's render function
- A close button (`×`) in the flyout header sets `state.flyoutOpen = false` and triggers layout recalculation
- Clicking non-section timeline space closes the flyout (the `onTimelineClick` handler already detects when no section is hit at line 657 — `if (idx >= 0)`)
- Clicking a different section while flyout is open just updates content (no close/reopen animation)

**Alternatives considered**:
- Click-outside-anywhere to close: rejected because timeline clicks are functional (seek audio, select section) and would cause confusing close-then-open behavior

## R4: Canvas Rendering for Theme Palette Strip

**Decision**: Add a 4px palette strip at the bottom of each section bar in `renderTimeline()` when that section has an `overrides.theme` set.

**Rationale**: Section bars are drawn in `renderTimeline()` (lines 356-382). Currently they render:
- A 4px color bar at the top (role color, full opacity)
- A semi-transparent fill for the section body
- A selected section outline

The palette strip would:
- Render at the bottom of the section bar area (y = section_bottom - 4, height = 4)
- Divide the strip width equally among the theme's palette colors
- Only render when `section.overrides.theme` is set AND theme palette data is available
- Theme palette data must be loaded from the 026-theme-editor endpoint and cached in `state.themePalettes`

**Alternatives considered**:
- Full bar tint: rejected per clarification
- Text badge: rejected per clarification

## R5: Theme Data Availability (Dependency on 026)

**Decision**: P2/P3 stories are blocked on feature 026-theme-editor providing theme data endpoints. P1 stories proceed independently.

**Rationale**: The frontend currently has zero access to theme data. Required from 026:
- `GET /story/themes` — returns all themes with name, mood, occasion, intent, palette, accent_palette
- `GET /story/themes/recommend?section_id=s01` — returns 2-3 recommended themes for a section
- Theme name validation on `POST /story/section/overrides` when `theme` field is set

The Themes tab, drag-and-drop, recommendations, and palette strip rendering all depend on this data. The Details and Moments tabs do not.

**Alternatives considered**:
- Embedding theme JSON directly in the HTML page: rejected (themes may be user-customizable, endpoint is cleaner)
- Loading builtin_themes.json as a static file: partial solution but wouldn't support recommendations or validation

## R6: Overrides Persistence

**Decision**: Use the existing `/story/section/overrides` endpoint and `merge_story_with_edits()` export path. No backend changes needed for P1.

**Rationale**: Confirmed in code:
- `SectionOverrides.theme` field exists as `Optional[str]` (models.py line 292)
- `/story/section/overrides` endpoint (story_routes.py line 886) accepts `theme` in the overrides dict and merges it
- `merge_story_with_edits()` (builder.py line 688) applies override action edits including theme
- Exported `_story_reviewed.json` includes all section overrides

No backend changes required for theme assignment persistence. Theme name validation is the only backend addition (deferred to 026).

## R7: Multi-Section Selection (P3 Scope Concern)

**Decision**: Descope multi-select drag-and-drop from initial implementation. Keep only "Apply to Unassigned" as the bulk action mechanism.

**Rationale**: The current UI has no multi-select capability. `state.currentSectionIdx` tracks a single integer. Building multi-select requires:
- New `state.selectedSections` set
- Shift-click / ctrl-click handlers
- Visual indicators for multi-selected sections on the canvas
- Modified drag-and-drop to apply to all selected sections

This is significant new interaction design work for a P3 story. The "Apply to Unassigned" button achieves the most common bulk use case (initial theme assignment) with zero new selection mechanics.

**Alternatives considered**:
- Full multi-select with shift/ctrl-click: deferred to future iteration if users request it
