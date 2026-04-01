# Tasks: Story Review Flyout Panels

**Input**: Design documents from `/specs/024-story-review-flyouts/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/flyout-ui-contract.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Prepare the flyout state model and initial HTML/CSS structure

- [x] T001 Add flyout state fields (flyoutOpen, activeTab) to the state object in src/review/static/story-review.js
- [x] T002 Replace the #sidebar HTML element with the #flyout structure (header with tab bar + close button, body with 3 content containers) in src/review/static/story-review.html

---

## Phase 2: Foundational (CSS Layout + Flyout Toggle)

**Purpose**: Core flyout open/close mechanism that ALL user stories depend on

- [x] T003 Replace the fixed `grid-template-columns: 1fr 320px` CSS with `.flyout-open` (1fr 360px) and `.flyout-closed` (1fr) grid classes, add grid transition animation (0.25s ease), and style the flyout panel (tab bar, active tab indicator, close button, content area, scrollable body) in src/review/static/story-review.html
- [x] T004 Implement `openFlyout()` function that sets state.flyoutOpen=true, adds flyout-open class to #main, removes flyout-closed class in src/review/static/story-review.js
- [x] T005 Implement `closeFlyout()` function that sets state.flyoutOpen=false, adds flyout-closed class to #main, removes flyout-open class in src/review/static/story-review.js
- [x] T006 Implement `switchTab(tabName)` function that sets state.activeTab, toggles hidden attribute on flyout-content divs, updates active class on tab buttons, and calls the appropriate render function for the newly active tab in src/review/static/story-review.js
- [x] T007 Add transitionend listener on #main element that re-renders timeline and stem track canvases after the grid column animation completes in src/review/static/story-review.js
- [x] T008 Wire up click handlers: tab buttons call switchTab(), close button calls closeFlyout() in src/review/static/story-review.js

**Checkpoint**: Flyout opens/closes with animation, tabs switch content areas, canvases resize correctly

---

## Phase 3: User Story 1 — Section Details in Flyout (Priority: P1)

**Goal**: Display all section character data in the flyout's Details tab, replacing the old static sidebar panels

**Independent Test**: Click any section on the timeline — flyout slides in showing energy, tempo, texture, brightness, stems, drum style, confidence, duration, time range, accents, active tiers, brightness ceiling. Click close — flyout slides out and timeline fills full width.

### Implementation for User Story 1

- [x] T009 [US1] Refactor `renderSectionDetail()` and `renderStemsPanel()` into a single `renderDetailsTab(idx)` function that renders section character data + stem level bars into the flyout details content container in src/review/static/story-review.js
- [x] T010 [US1] Modify `selectSection(idx)` to call `openFlyout()` and render only the active tab (instead of rendering all 3 old panels) in src/review/static/story-review.js
- [x] T011 [US1] Modify `onTimelineClick()` to close the flyout when clicking empty timeline space (no section found at click position) in src/review/static/story-review.js
- [x] T012 [US1] Remove the old #sidebar, #section-detail, #stems-panel, and #prefs-panel HTML elements and their associated CSS styles from src/review/static/story-review.html
- [x] T013 [US1] Migrate the preferences panel toggle (prefs-btn) into the flyout — add a gear icon button in the flyout header that toggles preferences display within the Details tab in src/review/static/story-review.html and src/review/static/story-review.js
- [x] T014 [US1] Verify the flyout remembers the last active tab: when flyout is closed and user clicks a new section, it reopens to state.activeTab (not always "details") in src/review/static/story-review.js

**Checkpoint**: Details tab fully replaces the old sidebar. All section data visible. Open/close animation works. Tab memory works.

---

## Phase 4: User Story 2 — Moments Tab (Priority: P1)

**Goal**: Display section moments in a dedicated Moments tab with dismiss/restore functionality

**Independent Test**: Select a section, click Moments tab — see all moments with timestamps, type badges, descriptions. Dismiss a moment — it shows as dismissed. Switch sections — moments update. Section with no moments shows empty state.

### Implementation for User Story 2

- [x] T015 [US2] Refactor `renderMomentsPanel()` into `renderMomentsTab(section, moments)` that renders moments into the flyout moments content container, including the empty state message for sections with no moments in src/review/static/story-review.js
- [x] T016 [US2] Update `switchTab()` to call `renderMomentsTab()` when switching to the moments tab, passing the current section and state.story.moments in src/review/static/story-review.js
- [x] T017 [US2] Verify `toggleMomentDismiss()` still works correctly with the new flyout DOM structure (dismiss button event handlers, re-render after dismiss/restore) in src/review/static/story-review.js
- [x] T018 [US2] Remove the old #moments-panel HTML element and its associated CSS styles from src/review/static/story-review.html

**Checkpoint**: Moments tab shows correct moments per section, dismiss/restore works, empty state displays correctly

---

## Phase 5: User Story 3 — Browse and Preview Themes (Priority: P2, requires 026)

**Goal**: Display all available themes as browsable cards with filtering by mood and occasion

**Independent Test**: Open Themes tab — see all 21 themes with name, mood badge, intent, palette swatches. Filter by mood — only matching themes shown. Filter by occasion — only matching themes plus general themes shown.

**Dependency**: Requires feature 026-theme-editor to provide `/story/themes` endpoint

### Implementation for User Story 3

- [x] T019 [US3] Add theme state fields to state object: themeList (array), themePalettes (object), themeFilters ({mood: null, occasion: null}) in src/review/static/story-review.js
- [x] T020 [US3] Implement `loadThemes()` function that fetches GET /themes/api/list, caches results in state.themeList and builds state.themePalettes lookup (theme name → palette array) in src/review/static/story-review.js
- [x] T021 [US3] Implement `renderThemesTab(section)` that renders a filter bar (mood dropdown + occasion dropdown) and a scrollable list of theme cards, each showing theme name, mood badge, intent text, primary palette swatches, and accent palette swatches in src/review/static/story-review.js
- [x] T022 [US3] Implement client-side filter logic: mood filter shows only themes matching selected mood; occasion filter shows matching occasion plus general; both filters combine (AND logic); empty result shows "No themes match filters" message in src/review/static/story-review.js
- [x] T023 [US3] Add CSS for theme cards (.theme-card), palette swatches (.palette-swatch), mood badges (.theme-mood-badge with mood-specific colors), filter bar (.theme-filters), and scrollable container in src/review/static/story-review.css
- [x] T024 [US3] Add a "Loading themes..." placeholder message that displays while themes are being fetched in src/review/static/story-review.js

**Checkpoint**: All 21 themes browsable with palette previews. Mood and occasion filters work. Graceful fallback when 026 is not available.

---

## Phase 6: User Story 4 — Drag and Drop Theme Assignment (Priority: P2, requires 026)

**Goal**: Enable dragging theme cards onto timeline sections to assign themes, with visual palette strip indicator

**Independent Test**: Drag a theme card from the flyout onto a section — section bar shows a palette strip at the bottom. Check Details tab — assigned theme name shown. Click remove — palette strip disappears. Save — reload — assignment persists.

**Dependency**: Requires feature 026-theme-editor and User Story 3 (T019-T024)

### Implementation for User Story 4

- [x] T025 [US4] Add dragstart handler on .theme-card elements that sets dataTransfer data to the theme name and adds a .dragging class in src/review/static/story-review.js
- [x] T026 [US4] Add a transparent drop-overlay div dynamically created over the timeline canvas area, invisible but interactive during drag operations in src/review/static/story-review.js
- [x] T027 [US4] Add dragover handler on the drop-overlay that determines which section the cursor is over (using xToTime() coordinate mapping), highlights the target section by re-rendering the timeline with a drop-target indicator in src/review/static/story-review.js
- [x] T028 [US4] Add drop handler on the drop-overlay that reads the theme name from dataTransfer, calls POST /story/section/overrides with {section_id, overrides: {theme: name}}, updates the local state.story section overrides, and re-renders the timeline in src/review/static/story-review.js
- [x] T029 [US4] Add dragend handler that removes the .dragging class and clears any drop-target highlights in src/review/static/story-review.js
- [x] T030 [US4] Render a 4px multi-color palette strip at the bottom of each section bar in renderTimeline(), dividing the width equally among the theme's palette colors from state.themePalettes in src/review/static/story-review.js
- [x] T031 [US4] Palette strip renders within renderTimeline() for each section that has overrides.theme set and a matching entry in state.themePalettes in src/review/static/story-review.js
- [x] T032 [US4] Add "Assign" click button on each theme card as a fallback alternative to drag-and-drop (calls the same override POST) in src/review/static/story-review.js
- [x] T033 [US4] Show assigned theme name and palette in the Themes tab when the selected section has overrides.theme set, with a "Remove" button that POSTs overrides with {theme: null} in src/review/static/story-review.js
- [x] T034 [US4] Add CSS for drag states (.theme-card.dragging opacity, drop-target section highlight, theme-assigned display) in src/review/static/story-review.css

**Checkpoint**: Drag-and-drop assigns themes. Palette strip visible on assigned sections. Click-to-assign fallback works. Remove clears assignment. Assignments persist through save.

---

## Phase 7: User Story 5 — Auto-Recommended Themes (Priority: P3, requires 026)

**Goal**: Show 2-3 recommended themes at the top of the Themes tab with reasons, matching section mood/energy/occasion

**Independent Test**: Select a high-energy section — recommendations favor aggressive themes. Select a low-energy section — recommendations favor ethereal themes. Set occasion to christmas — christmas themes appear in recommendations.

**Dependency**: Requires feature 026-theme-editor recommendation endpoint and User Story 3 (T019-T024)

### Implementation for User Story 5

- [x] T035 [US5] Implement `_recommendThemes(section)` function that scores themes client-side by mood/energy/occasion match (no server endpoint needed) in src/review/static/story-review.js
- [x] T036 [US5] Update `renderThemesTab(section)` to show a "Recommended" section at the top of the theme list with 2-3 recommended theme cards with reason text (e.g., "high-energy section, aggressive mood") in src/review/static/story-review.js
- [x] T037 [US5] Add "Assign" button on all theme cards (including recommended) that assigns the theme to the current section in src/review/static/story-review.js
- [x] T038 [US5] Add CSS for the recommended section header (.theme-rec-header), reason text (.theme-rec-reason), mood badges in src/review/static/story-review.css

**Checkpoint**: Recommendations appear at top of Themes tab. Recommendations change per section. Apply button works. Recommendations respect occasion preference.

---

## Phase 8: User Story 6 — Bulk Theme Assignment (Priority: P3, requires 026)

**Goal**: Enable assigning a theme to all unassigned sections at once

**Independent Test**: With some sections having no theme, click "Apply to Unassigned" on a theme card — all unassigned sections receive that theme. Previously assigned sections are unchanged. Save — all assignments persist.

**Dependency**: Requires User Story 4 (T025-T034) for theme assignment infrastructure

### Implementation for User Story 6

- [x] T039 [US6] Add "Apply recommended to unassigned" button in the Themes tab that iterates all sections, finds those without overrides.theme, and POSTs /story/section/overrides for each with the first recommended theme name in src/review/static/story-review.js
- [x] T040 [US6] After bulk assignment, update local state for all affected sections, re-render the timeline (palette strips appear on newly assigned sections), and show a toast message ("Applied X to N sections") in src/review/static/story-review.js
- [x] T041 [US6] Add CSS for the "Apply to Unassigned" button (.theme-apply-unassigned-btn) and toast in src/review/static/story-review.css

**Checkpoint**: Bulk assignment works for all unassigned sections. Existing assignments preserved. Visual feedback shown.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases and refinements across all stories

- [x] T042 Handle browser resize while flyout is open — re-render canvases on window resize event in src/review/static/story-review.js
- [x] T043 Handle section split/merge while theme is assigned — theme overrides are preserved server-side by the existing merge_story_with_edits() logic in builder.py
- [x] T044 Ensure existing pytest tests still pass with no regressions (run pytest tests/ -v)
- [x] T045 Keyboard accessibility: add Escape key to close flyout, Tab key navigation between flyout tabs in src/review/static/story-review.js

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1 Details)**: Depends on Phase 2 — core flyout with details content
- **Phase 4 (US2 Moments)**: Depends on Phase 2 — can run in parallel with Phase 3
- **Phase 5 (US3 Theme Browse)**: Depends on Phase 2 + feature 026-theme-editor
- **Phase 6 (US4 Drag-and-Drop)**: Depends on Phase 5 (US3)
- **Phase 7 (US5 Recommendations)**: Depends on Phase 5 (US3) + 026 recommendation endpoint
- **Phase 8 (US6 Bulk)**: Depends on Phase 6 (US4)
- **Phase 9 (Polish)**: Depends on all desired user stories being complete

### User Story Dependencies

```
Phase 1 → Phase 2 (Foundational)
              ├── Phase 3 (US1 Details)  ←── P1, no external deps
              ├── Phase 4 (US2 Moments)  ←── P1, no external deps (parallel with US1)
              └── Phase 5 (US3 Theme Browse)  ←── P2, requires 026
                    ├── Phase 6 (US4 Drag-Drop)  ←── P2, requires US3
                    │     └── Phase 8 (US6 Bulk)  ←── P3, requires US4
                    └── Phase 7 (US5 Recommendations)  ←── P3, requires US3 + 026
```

### Parallel Opportunities

- **US1 + US2** can be implemented in parallel (both are P1, both modify story-review.js but touch different functions)
- **US5 + US6** can be implemented in parallel after their dependencies complete (US5 depends on US3, US6 depends on US4)
- Within each phase, tasks modifying HTML ([P] on separate file) can parallel with JS tasks

---

## Parallel Example: User Stories 1 & 2

```bash
# These two stories can be worked on simultaneously after Phase 2:
# Agent A: User Story 1 (Details Tab)
Task: T009 - Refactor renderSectionDetail + renderStemsPanel into renderDetailsTab
Task: T010 - Modify selectSection to use openFlyout
Task: T011 - Modify onTimelineClick for close behavior

# Agent B: User Story 2 (Moments Tab)
Task: T015 - Refactor renderMomentsPanel into renderMomentsTab
Task: T016 - Update switchTab for moments rendering
Task: T017 - Verify toggleMomentDismiss with new DOM
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T008)
3. Complete Phase 3: US1 Details Tab (T009-T014)
4. Complete Phase 4: US2 Moments Tab (T015-T018)
5. **STOP and VALIDATE**: Flyout with Details + Moments tabs fully functional
6. This is a shippable MVP — all existing sidebar functionality preserved in flyout form

### Incremental Delivery (after 026-theme-editor)

7. Complete Phase 5: US3 Theme Browse (T019-T024)
8. Complete Phase 6: US4 Drag-and-Drop (T025-T034)
9. Complete Phase 7: US5 Recommendations (T035-T038)
10. Complete Phase 8: US6 Bulk Assignment (T039-T041)
11. Complete Phase 9: Polish (T042-T045)

---

## Notes

- All changes are in 2 files: `src/review/static/story-review.html` and `src/review/static/story-review.js`
- No backend changes needed — existing `/story/section/overrides` endpoint already handles theme assignments
- P2/P3 phases (US3-US6) are blocked on feature 026-theme-editor providing theme data endpoints
- The Themes tab shows a "Coming soon" placeholder until 026 is available (T024)
- Multi-section selection (shift-click) was descoped — "Apply to Unassigned" covers the primary bulk use case
