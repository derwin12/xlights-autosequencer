# Implementation Plan: Story Review Flyout Panels

**Branch**: `024-story-review-flyouts` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/024-story-review-flyouts/spec.md`

## Summary

Replace the static right sidebar in the story review UI with a toggle-able tabbed flyout panel. The flyout has three tabs — Details (section character data + stems), Moments (dramatic moments list), and Themes (theme browsing, drag-and-drop assignment, recommendations). The flyout uses a push layout that shifts the timeline left when open. P1 (Details + Moments) has no dependencies. P2/P3 (Themes tab, drag-and-drop, recommendations, bulk actions) depend on feature 026-theme-editor for theme data endpoints.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JS + HTML5 + CSS3 (frontend)
**Primary Dependencies**: Flask 3+ (backend server), HTML5 Drag and Drop API (P2)
**Storage**: JSON files (existing story/edits format — no changes)
**Testing**: pytest (backend), manual browser testing (frontend)
**Target Platform**: Modern browsers (Chrome, Firefox, Safari, Edge)
**Project Type**: Web application (local Flask server + single-page review UI)
**Performance Goals**: Flyout open/close animation under 300ms; tab switching instant; canvas re-render under 50ms
**Constraints**: Single HTML file + single JS file architecture (no build system); all frontend is vanilla JS
**Scale/Scope**: Single-user local tool; 8-15 sections per song; 21 built-in themes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | No changes to audio analysis. Flyout displays existing analysis data. |
| II. xLights Compatibility | PASS | No changes to sequence output. Theme assignments stored in overrides for future use. |
| III. Modular Pipeline | PASS | Changes isolated to review UI layer (story-review.html/js). No pipeline stage coupling. |
| IV. Test-First Development | PASS | Existing tests must not break. Frontend changes tested manually. |
| V. Simplicity First | PASS | No new abstractions. Tab system is minimal DOM manipulation. Theme data deferred to 026. |

**Post-Phase 1 re-check**: All gates still pass. No new dependencies, no pipeline changes, no output format changes.

## Project Structure

### Documentation (this feature)

```text
specs/024-story-review-flyouts/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Frontend state model
├── quickstart.md        # Development setup guide
├── contracts/
│   └── flyout-ui-contract.md  # HTML/CSS/JS interface contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (files modified)

```text
src/review/static/
├── story-review.html    # Layout, CSS, flyout HTML structure
└── story-review.js      # Flyout state, tab switching, render functions, drag-and-drop
```

**Structure Decision**: No new files created. All changes are modifications to the existing two-file review UI (story-review.html and story-review.js). This preserves the single-file architecture.

## Implementation Phases

### Phase 1: Flyout Shell + Details Tab (P1, no dependencies)

Convert the static sidebar into a toggle-able flyout with the Details tab.

**Changes to story-review.html**:
- Replace `<div id="sidebar">` with `<div id="flyout" class="flyout flyout--closed">`
- Add flyout header with tab bar (3 buttons) and close button
- Add flyout body with 3 content containers (details, moments, themes)
- Update CSS: remove fixed `grid-template-columns: 1fr 320px`; add `.flyout-open` / `.flyout-closed` grid classes with transition
- Add flyout styling: tab bar, active tab indicator, close button, content area

**Changes to story-review.js**:
- Add `state.flyoutOpen` (boolean) and `state.activeTab` (string)
- Add `openFlyout()`, `closeFlyout()`, `switchTab(tabName)` functions
- Refactor `renderSectionDetail()` + `renderStemsPanel()` into `renderDetailsTab(idx)`
- Modify `selectSection(idx)`: call `openFlyout()` + render active tab only
- Modify `onTimelineClick()`: close flyout when clicking empty space (no section hit)
- Add close button click handler
- Add `transitionend` listener on `#main` to re-render canvases after grid animation
- Add tab button click handlers

### Phase 2: Moments Tab (P1, no dependencies)

Move moments into the flyout's Moments tab.

**Changes to story-review.js**:
- Refactor `renderMomentsPanel()` into `renderMomentsTab(section, moments)` targeting the flyout content area
- Empty state message when section has no moments
- Preserve existing dismiss/restore functionality (`toggleMomentDismiss()`)
- Tab switching triggers the correct render function based on `state.activeTab`

### Phase 3: Themes Tab — Browse + Filter (P2, requires 026)

Add theme browsing with cards and filters.

**Changes to story-review.js**:
- Add `loadThemes()`: fetch `/story/themes`, cache in `state.themeList` and `state.themePalettes`
- Add `renderThemesTab(section)`: render theme cards with name, mood badge, intent, palette swatches
- Add filter controls (mood dropdown, occasion dropdown) wired to `state.themeFilters`
- Filter logic: client-side filtering of `state.themeList`

**Changes to story-review.html**:
- Add CSS for theme cards, palette swatches, mood badges, filter bar

### Phase 4: Drag-and-Drop Theme Assignment (P2, requires 026)

Enable dragging theme cards onto timeline sections.

**Changes to story-review.js**:
- Add `dragstart` handler on `.theme-card` elements (set `dataTransfer` with theme name)
- Add transparent overlay div on timeline area for drop events (canvas doesn't support native drop)
- Add `dragover` handler: detect which section the cursor is over (using `xToTime()`), highlight it
- Add `drop` handler: POST to `/story/section/overrides` with theme name, update local state
- Add `dragend` handler: clear highlights
- Add `renderPaletteStrip(ctx, section, x, y, w)`: draw 4px palette strip at bottom of section bar in `renderTimeline()`
- Add "click to assign" button on theme cards as fallback for non-drag interaction
- Add theme badge display in Details tab when section has assigned theme
- Add remove/clear button for theme assignments

**Changes to story-review.html**:
- Add CSS for drag states (`.dragging`, `.drop-target`), palette strip positioning
- Add drop overlay element

### Phase 5: Recommendations + Bulk Actions (P3, requires 026)

Add recommended themes and "Apply to Unassigned".

**Changes to story-review.js**:
- Add `loadRecommendations(sectionId)`: fetch `/story/themes/recommend?section_id=X`
- Render recommended themes at top of Themes tab with "Recommended" badge and reason text
- Add "Apply" button on recommended theme cards (same as drag-and-drop assignment)
- Add "Apply to Unassigned" button on each theme card: iterates sections, POSTs override for each without a theme

## Complexity Tracking

No constitution violations. No complexity justifications needed.

## Key Risks

| Risk | Mitigation |
|------|------------|
| Canvas re-render flicker during flyout animation | Use `transitionend` event to re-render only after animation completes; during animation, let CSS handle the squish |
| HTML5 drag-and-drop on canvas elements | Use a transparent overlay div positioned over the timeline canvas for drop target detection |
| P2/P3 blocked on 026-theme-editor | P1 is fully independent and delivers immediate value; theme tab shows "Coming soon" placeholder until 026 is ready |
