# Feature Specification: Theme Editor

**Feature Branch**: `026-theme-editor`
**Created**: 2026-04-01
**Status**: Draft
**Input**: User description: "Full theme editor for creating/editing/managing lighting themes with mood, tone, color, layers. Folder-based storage, standalone access, deep linking, new-tab support."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse and Preview Existing Themes (Priority: P1)

A user wants to explore the full library of available themes (built-in and custom) to understand what's available before creating or modifying anything. They access the theme editor directly — without needing to analyze a song or load a story first. Themes are organized hierarchically by mood, occasion, and genre into collapsible groups, with color palette previews and layer summaries. A text search allows quickly finding themes by name or intent.

**Why this priority**: Users need to see what exists before they can meaningfully create or edit themes. This is the foundation every other story builds on and delivers immediate value by making the theme library browsable and directly accessible.

**Independent Test**: Can be fully tested by navigating directly to the theme editor URL and verifying all built-in themes display with correct metadata, palettes, filtering, and search -- no song data needed.

**Acceptance Scenarios**:

1. **Given** the user navigates directly to the theme editor URL (e.g., `/themes`), **Then** the theme editor opens showing all available themes (built-in and custom) without requiring any song to be loaded or analyzed.
2. **Given** the theme editor is open, **When** the user filters by mood (e.g., "aggressive"), **Then** only themes matching that mood are displayed.
3. **Given** the theme editor is open, **When** the user filters by occasion or genre, **Then** themes are filtered accordingly, and filters can be combined.
4. **Given** the theme editor is open, **Then** themes are organized into collapsible groups (by mood or occasion) so the user does not need to scroll through a flat list of hundreds of themes.
5. **Given** the theme editor is open, **When** the user types in the search box, **Then** themes are filtered in real time by name or intent text.
6. **Given** the theme editor is open, **When** the user selects a theme, **Then** a read-only detail view appears in the right panel showing the theme's mood, occasion, genre, intent description, color palette swatches, accent palette swatches (if present), layer stack with effect names and blend modes, and any variants. An "Edit" button switches the panel to edit mode.

---

### User Story 2 - Create a New Custom Theme (Priority: P2)

A user wants to create a brand-new theme from scratch. They define the theme's mood, occasion, genre, intent description, color palette, accent palette (optional), and layer stack. The new theme is saved as a custom theme JSON file that can be consumed later by sequence generation and other tools.

**Why this priority**: Creating new themes is the core value proposition of the editor. Without this, users are limited to the 21 built-in themes.

**Independent Test**: Can be fully tested by creating a new theme through the editor form, saving it, and verifying the JSON file is written and the theme appears in the editor's theme list.

**Acceptance Scenarios**:

1. **Given** the user is in the theme editor, **When** they click "New Theme", **Then** an empty theme form opens with all required fields (name, mood, occasion, genre, intent, palette, layers) and optional fields (accent palette).
2. **Given** the user is filling out the new theme form, **When** they pick colors for the palette, **Then** they can use a color picker to select colors visually and see a live preview of the palette swatches.
3. **Given** the user has filled out all required fields, **When** they click "Save", **Then** the theme is validated (name unique across ALL themes — built-in and custom, at least 2 palette colors, at least 1 layer with Normal blend on bottom, valid mood/occasion/genre) and saved as a new custom theme JSON file.
4. **Given** the user enters a name that already exists (built-in or custom), **When** they click "Save", **Then** the save is blocked and an error message tells them the name is taken and they must choose a different name.
5. **Given** the user has entered invalid data (e.g., fewer than 2 palette colors, missing name), **When** they click "Save", **Then** they see specific validation error messages indicating what needs to be fixed.
6. **Given** a new theme was just saved, **When** the user returns to the theme list, **Then** the new theme appears with a "Custom" badge distinguishing it from built-in themes.

---

### User Story 3 - Edit an Existing Theme (Priority: P2)

A user wants to modify an existing theme. For built-in themes, this creates a custom override (preserving the original). For custom themes, this edits in place. Changes are reflected immediately in the theme library.

**Why this priority**: Editing is as important as creating -- users often want to tweak an existing theme rather than build from scratch.

**Independent Test**: Can be fully tested by selecting an existing theme, modifying its palette, saving, and verifying the changes persist across page reloads.

**Acceptance Scenarios**:

1. **Given** the user is viewing a theme in the detail panel, **When** they click "Edit", **Then** the detail panel switches to edit mode with all fields editable.
2. **Given** the user selects a built-in theme and enters edit mode, **Then** a notice explains that editing a built-in theme will create a custom override, and the original remains available under "Restore defaults".
3. **Given** the user is editing a theme, **When** they modify the color palette (add, remove, reorder colors), **Then** the palette swatch preview updates in real time.
4. **Given** the user is editing a theme, **When** they add, remove, or reorder layers, **Then** the layer stack display updates to reflect the changes, and blend mode constraints are enforced (bottom layer must be Normal).
5. **Given** the user has made changes, **When** they click "Save", **Then** the modified theme is saved and the theme list reflects the updated version.
6. **Given** the user has overridden a built-in theme, **When** they click "Restore defaults", **Then** the custom override is removed and the original built-in theme is restored.
7. **Given** the user is editing a custom theme, **When** they change the theme name to a new unique name, **Then** the theme is renamed (file updated) and references reflect the new name.
8. **Given** the user has unsaved changes and attempts to navigate away (select another theme, close the editor, or leave the page), **Then** a confirmation prompt asks whether to discard changes or stay and continue editing.

---

### User Story 4 - Duplicate a Theme as Starting Point (Priority: P3)

A user wants to create a new theme based on an existing one. They duplicate a theme, which creates a copy with a new name that they can then customize.

**Why this priority**: Duplication reduces effort when creating themes that are variations of existing ones, which is the most common creation workflow.

**Independent Test**: Can be fully tested by duplicating a theme, verifying the copy has a unique name, modifying it, and saving independently.

**Acceptance Scenarios**:

1. **Given** the user selects any theme, **When** they click "Duplicate", **Then** a new theme form opens pre-filled with all the original theme's data and a suggested name (e.g., "Inferno Copy").
2. **Given** the user has a duplicated theme form, **When** they change the name and modify fields, **Then** the original theme remains unchanged after save.

---

### User Story 5 - Delete a Custom Theme (Priority: P3)

A user wants to remove a custom theme they no longer need. Built-in themes cannot be deleted.

**Why this priority**: Housekeeping capability needed to manage a growing theme library.

**Independent Test**: Can be fully tested by deleting a custom theme and verifying it no longer appears in the library.

**Acceptance Scenarios**:

1. **Given** the user selects a custom theme, **When** they click "Delete", **Then** a confirmation dialog appears warning the action is permanent.
2. **Given** the user confirms deletion, **When** the theme is removed, **Then** it no longer appears in the theme list and the underlying file is removed from storage.
3. **Given** the user selects a built-in theme, **Then** the "Delete" action is not available.

---

### User Story 6 - Deep Link and New-Tab Access (Priority: P2)

A user viewing the story review UI wants to quickly open a theme in the editor. Other pages can link directly to a specific theme. The theme editor URL is bookmarkable.

**Why this priority**: Deep linking connects the theme editor to the rest of the application, making it a natural part of the workflow rather than an isolated tool.

**Independent Test**: Can be fully tested by navigating to a theme editor URL with a theme name parameter and verifying the correct theme is displayed.

**Acceptance Scenarios**:

1. **Given** a URL with a theme identifier (e.g., `/themes/editor?theme=Inferno`), **When** the user navigates to it, **Then** the theme editor opens with that specific theme selected and its details visible.
2. **Given** the user is on the story review page viewing section overrides, **When** they click a theme name, **Then** the theme editor opens in a new browser tab at the deep link URL for that theme.
3. **Given** the user bookmarks a theme editor URL, **When** they return to it later, **Then** the same theme is displayed (assuming it still exists).
4. **Given** a deep link references a theme that no longer exists, **When** the user navigates to it, **Then** the editor opens to the theme list with a notification that the requested theme was not found.

---

### Edge Cases

- What happens when a user tries to create or rename a theme to a name that already exists (built-in or custom)? The save is blocked with a clear error message; the user must choose a unique name. This prevents accidental overrides of built-in themes through the "New Theme" flow.
- What happens when a custom theme was previously created as an override of a built-in (via the Edit flow)? The editor shows it with both a "Custom" badge and a "Restore defaults" option that removes the override and restores the built-in original.
- What happens when the custom themes storage location is not writable? The editor displays a clear error message and disables save/delete actions while still allowing browsing.
- What happens when two browser tabs edit the same theme simultaneously? The last save wins; the editor does not need real-time collaboration but must not corrupt data.
- What happens when a theme has no variants? The variants section is simply not shown in the detail view and editor form.
- What happens when a referenced effect name no longer exists in the effect library? The layer is shown with a warning indicator, and the user is prompted to select a valid effect before saving.
- What happens when the user has unsaved changes and navigates away? A confirmation prompt warns about unsaved changes and offers to discard or stay.
- What happens when a theme is renamed and another page had a deep link to the old name? The deep link shows a "theme not found" notification with the full theme list visible.
- What happens when a user renames a custom theme to the same name as a built-in? The rename is blocked — same uniqueness rules apply as for create.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a standalone theme editor page accessible at a direct URL (e.g., `/themes`) without requiring a song to be loaded or analyzed. No story analysis or song upload is needed to access the editor.
- **FR-002**: System MUST display all available themes (built-in and custom) with their metadata: name, mood, occasion, genre, intent, color palette, accent palette (if present), and layer configuration.
- **FR-003**: System MUST allow filtering themes by mood, occasion, and genre, with filters combinable. System MUST also provide a text search that filters themes by name or intent description in real time.
- **FR-004**: System MUST allow creating new custom themes with required properties (name, mood, occasion, genre, intent, palette with minimum 2 colors, at least one effect layer) and optional properties (accent palette).
- **FR-005**: System MUST validate themes on save: name must be unique across ALL themes (built-in and custom), valid mood/occasion/genre values, minimum 2 palette colors, at least 1 layer, bottom layer with Normal blend mode, all referenced effects must exist in the effect library. If the name is not unique, the save MUST be blocked with an error message requiring the user to choose a different name.
- **FR-006**: System MUST allow editing existing themes. Editing a built-in theme creates a custom override; editing a custom theme modifies it in place.
- **FR-007**: System MUST provide a color picker for selecting palette and accent palette colors.
- **FR-008**: System MUST allow managing the layer stack: add layers, remove layers, reorder layers, set effect name, set blend mode, and configure parameter overrides per layer. When an effect is selected, the editor MUST auto-populate the effect's available parameters with their default values, allowing the user to adjust any parameter without needing to know parameter names.
- **FR-009**: System MUST allow duplicating any theme as a starting point for a new custom theme.
- **FR-010**: System MUST allow deleting custom themes with confirmation. Built-in themes cannot be deleted.
- **FR-011**: System MUST allow restoring a built-in theme to its defaults when a custom override exists.
- **FR-012**: System MUST store each custom theme as an individual JSON file (one file per theme) in a dedicated folder, supporting scalability as the library grows.
- **FR-013**: System MUST support deep linking to a specific theme via URL parameters so that other pages can link directly to a theme in the editor.
- **FR-014**: System MUST support opening the theme editor in a new browser tab from links on other pages (e.g., story review UI theme references).
- **FR-015**: System MUST visually distinguish custom themes from built-in themes in the theme list (e.g., badge or icon).
- **FR-016**: System MUST show a real-time preview of palette color swatches as the user adds, removes, or reorders colors in the editor form.
- **FR-017**: System MUST provide theme variant management: add, edit, and remove alternate layer configurations within a theme.
- **FR-018**: System MUST use a split-panel layout with the theme list on the left and detail/edit panel on the right, consistent with the existing story review UI pattern.
- **FR-019**: The right panel MUST have two modes: a read-only detail view (default when selecting a theme) and an edit mode (activated by clicking "Edit"). The user explicitly switches between view and edit modes.
- **FR-020**: System MUST allow renaming custom themes. Renaming updates the underlying file. The new name must be unique across all themes (built-in and custom). Built-in theme names cannot be changed.
- **FR-021**: System MUST prompt the user to discard or continue editing when they have unsaved changes and attempt to navigate away (selecting another theme, closing the editor, or leaving the page).
- **FR-022**: System MUST organize themes in the list panel into collapsible groups by mood so that users can browse a large library without scrolling through a flat list.
- **FR-023**: Custom themes MUST be written as JSON files to disk so they can be consumed by sequence generation and other tools in future phases. The editor does not need to trigger in-memory reload of other running services.

### Key Entities

- **Theme**: A named collection of visual properties (mood, occasion, genre, intent, palettes, layers, variants) that defines how lighting effects are rendered for a song section. Themes are either built-in (shipped with the application, read-only) or custom (user-created, fully editable).
- **Effect Layer**: A single layer within a theme's layer stack, specifying an effect name, blend mode, and optional parameter overrides. Layers are ordered; the bottom layer must use Normal blend mode.
- **Theme Variant**: An alternate layer configuration within a theme, allowing the same theme identity (name, mood, palette) to produce different visual outputs for variety.
- **Color Palette**: An ordered list of colors (minimum 2) that define the theme's primary color scheme. A separate accent palette (optional) provides secondary colors for highlight effects.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can browse the full theme library and view any theme's details within 3 clicks from any page in the application.
- **SC-002**: Users can create a new custom theme from scratch and save it in under 5 minutes.
- **SC-003**: Users can duplicate an existing theme and modify it into a new theme in under 2 minutes.
- **SC-004**: Deep links to specific themes resolve correctly 100% of the time when the theme exists.
- **SC-005**: The theme editor loads and displays the full theme library within 2 seconds.
- **SC-006**: All custom themes persist across application restarts without data loss.
- **SC-007**: The folder-based storage structure supports at least 100 custom themes without noticeable performance degradation in the editor.
- **SC-008**: Users can access the theme editor without loading or analyzing any song -- it is fully standalone.

## Clarifications

### Session 2026-04-01

- Q: Should spec 026 absorb spec 025 (theme data endpoint placeholder) or remain separate? → A: 026 absorbs 025 — this spec supersedes the placeholder; 025 is retired.
- Q: What layout pattern should the theme editor use? → A: Split panel — theme list on left, detail/edit panel on right (consistent with story review layout).
- Q: How should users configure parameter overrides per layer? → A: Auto-populated from effect — when an effect is selected, show its available parameters with defaults; user adjusts values as needed.

### Adversarial Review 2026-04-01

- "Standalone" means direct URL access to the theme editor without going through story analysis or song upload. Not a global nav shell.
- Sequence generation integration is deferred to a future phase. Themes are written to JSON for later consumption.
- Navigation guards added: unsaved changes prompt before navigating away (FR-021).
- Name uniqueness enforced across ALL themes (built-in + custom). Creating or renaming to an existing name is blocked (FR-005 updated).
- Accent palette is optional in the data model and editor form (FR-004, Key Entities updated).
- "Real-time preview" scoped to palette color swatches only — not effect rendering (FR-016 clarified).
- Right panel has explicit view/edit modes: read-only detail by default, "Edit" button switches to edit mode (FR-019).
- Theme rename supported for custom themes (FR-020). Uniqueness rules apply.
- Text search added (FR-003). Hierarchical grouping by mood/occasion added to prevent flat-list scrolling (FR-022).
- Spec 025 formally retired — this spec supersedes it. Dependency from spec 024 now points to 026.

## Assumptions

- The existing theme data model (mood, occasion, genre, intent, layers, palettes, variants) is sufficient for the editor. No new theme properties are being introduced.
- The existing validation rules from the theme validator define the constraints for valid themes.
- The existing effect library is the source of truth for available effect names in layer configuration.
- The valid blend modes are the 22 modes already supported by the system.
- Custom themes are stored as individual JSON files (one per theme) in the custom themes folder, which is already the current storage pattern.
- The theme editor is a web UI served by the same application that serves the review UI.
- The application runs locally, so there are no multi-user concurrency concerns beyond multiple browser tabs.

## Scope Boundaries

**In scope**:
- Browsing, creating, editing, renaming, duplicating, and deleting themes
- Color picker for palette management
- Layer stack management (effects, blend modes, parameter overrides)
- Variant management
- Folder-based JSON storage (one file per theme)
- Standalone access without song context (direct URL, no analysis required)
- Deep linking and new-tab support
- Text search and hierarchical grouping in theme list
- Navigation guards for unsaved changes
- Formal retirement of spec 025 (theme data endpoint placeholder) — this spec supersedes it

**Out of scope**:
- Theme recommendation engine (may be added as a future enhancement or separate spec)
- Live preview of themes rendered on actual xLights props/models (palette swatch preview is in scope; effect rendering is not)
- Import/export of themes to/from external formats
- Theme sharing between users or installations
- Undo/redo history within the editor
- Theme tagging or custom categorization beyond mood/occasion/genre
- In-memory reload of theme library in other running services (e.g., sequence generator) — themes are written to JSON for later consumption
