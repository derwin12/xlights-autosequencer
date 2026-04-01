# Tasks: Theme Editor

**Input**: Design documents from `/specs/026-theme-editor/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/theme-api.md

**Tests**: Included for backend (pytest). Frontend is vanilla JS (manual browser testing, consistent with existing project pattern).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create project structure, register blueprint, scaffold frontend files

- [x] T001 [P] Create empty frontend files: src/review/static/theme-editor.html (minimal HTML shell with split-panel layout containers), src/review/static/theme-editor.js (empty module), src/review/static/theme-editor.css (empty stylesheet). Link JS and CSS from HTML.
- [x] T002 Create theme routes Flask blueprint in src/review/theme_routes.py. Register as theme_bp with url_prefix="/themes". Add a module-level _library and _effect_library variable (loaded lazily on first request via load_theme_library() and load_effect_library()). Add a helper _reload_library() that re-calls load_theme_library() and updates the module-level reference. Add a root route GET / that serves theme-editor.html from the static folder (this maps to GET /themes since the blueprint prefix is /themes).
- [x] T003 Register theme_bp blueprint in src/review/server.py inside create_app(). Import and register regardless of mode (theme editor is always available). No additional route needed in server.py — the blueprint's root route handles GET /themes.

**Checkpoint**: Server starts, GET /themes serves the empty HTML shell, blueprint is registered.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Tests first (per constitution IV), then API endpoints. ALL user stories depend on these.

**⚠️ CRITICAL**: No user story UI work can begin until these endpoints are complete and tested.

### Tests (write first, confirm they fail)

- [x] T004 [P] Write pytest tests for theme writer in tests/unit/test_theme_writer.py. Test: save_theme() creates JSON file with correct slugified name in a temp dir, delete_theme() removes the file, rename_theme() creates new file and deletes old, save with invalid dir creates it, save overwrites existing, delete nonexistent returns error. Use tmp_path fixture for isolation. Confirm all tests FAIL (module does not exist yet).
- [x] T005 [P] Write pytest tests for theme API routes in tests/unit/test_theme_routes.py. Test: GET /themes/api/list returns all themes with is_custom flags, GET /themes/api/effects returns effects with parameters, 200 status codes. Use Flask test client. Use fixture themes dir with a test custom theme JSON file. Confirm all tests FAIL (endpoints do not exist yet).

### Implementation (make tests pass)

- [x] T006 Create theme writer module with save_theme(), delete_theme(), rename_theme() functions in src/themes/writer.py. Must handle: slugified filenames from theme names, creating ~/.xlight/custom_themes/ directory on first write, atomic JSON writes (write to temp then rename), and returning ThemeWriteResult-style dicts. Use pathlib for all path operations. Slugify: lowercase, replace spaces/special chars with hyphens, strip non-alphanumeric except hyphens. Run T004 tests — they should now PASS.
- [x] T007 Implement GET /themes/api/list endpoint in src/review/theme_routes.py. Load theme library (lazy init). Return JSON with: themes array (each theme serialized with all fields + is_custom boolean + has_builtin_override boolean), moods/occasions/genres enum arrays. Determine is_custom by checking if a file exists in custom_themes dir for that name. Determine has_builtin_override by checking if the name exists in both builtin and custom. Note: Theme dataclass has from_dict() but may need a to_dict() helper or use dataclasses.asdict() plus the extra flags. See contracts/theme-api.md for exact response shape.
- [x] T008 Implement GET /themes/api/effects endpoint in src/review/theme_routes.py. Load effect library (lazy init). Return JSON with: effects array (name, category, layer_role, parameters with name/storage_name/widget_type/value_type/default/min/max/choices for each), blend_modes array (all 22+ valid blend modes from the validator). See contracts/theme-api.md for exact response shape. Run T005 tests — they should now PASS.

**Checkpoint**: All Phase 2 tests pass. API endpoints return correct JSON. Frontend can now fetch theme data.

---

## Phase 3: User Story 1 — Browse and Preview Existing Themes (Priority: P1) 🎯 MVP

**Goal**: Users can navigate to /themes and browse all themes organized by mood groups with search and filtering, then view theme details in a read-only panel.

**Independent Test**: Navigate to /themes — all 21 built-in themes display in collapsible mood groups with palette swatches. Click a theme to see full details in right panel. Type in search box to filter by name/intent. Use mood/occasion/genre dropdowns to filter.

### Implementation for User Story 1

- [x] T009 [US1] Build the theme-editor.html page structure in src/review/static/theme-editor.html. Split-panel layout: left panel (theme list with search input, filter dropdowns for mood/occasion/genre, and a scrollable theme list container with collapsible group sections), right panel (detail view container, initially showing "Select a theme" placeholder). Include a toolbar area at top with "New Theme" button (disabled for now). Link to theme-editor.css and theme-editor.js. Use the same dark theme CSS variables as story-review.css (#1a1a1a background, monospace font, etc).
- [x] T010 [US1] Implement theme list fetching and rendering in src/review/static/theme-editor.js. On page load, fetch GET /themes/api/list. Store themes in state. Render themes grouped by mood into collapsible sections (each mood is a header that toggles visibility of its themes). Each theme item shows: name, occasion badge (if not "general"), genre badge (if not "any"), and a row of small palette color swatches. Mark custom themes with a "Custom" badge. Collapsible groups default to expanded. Sort themes alphabetically within each group.
- [x] T011 [US1] Implement search and filter functionality in src/review/static/theme-editor.js. Text search input filters themes by name or intent (case-insensitive substring match, real-time on input event with debounce). Mood/occasion/genre dropdown filters AND-combine with each other and with search text. When filters are active, hide empty groups. Add a "Clear filters" button that resets all filters.
- [x] T012 [US1] Implement read-only detail view panel in src/review/static/theme-editor.js. When a theme is clicked in the list, render in the right panel: theme name (as heading), mood/occasion/genre labels, intent description, palette swatches (colored rectangles with hex labels), accent palette swatches (if present, with "Accent" label), layer stack (ordered list showing effect name, blend mode, and parameter override count per layer), and variants section (if any variants exist, show each as a collapsible sub-list of layers). Add an "Edit" button at the top of the detail panel (disabled for now — enabled in US3). Highlight the selected theme in the list.
- [x] T013 [US1] Style the theme editor in src/review/static/theme-editor.css. Match the existing story-review dark theme. Style: split-panel layout (left 320px, right 1fr), theme list items with hover state, selected state highlight, palette swatch rectangles (24x24px colored squares inline), collapsible group headers with expand/collapse chevron, filter bar with dropdowns and search input, detail panel sections with clear typography hierarchy, badge styles for Custom/mood/occasion/genre, scrollable list panel. Use CSS custom properties consistent with story-review.css.

**Checkpoint**: Browse all themes at /themes, filter by mood/occasion/genre, search by name/intent, click to view full details in right panel. MVP complete.

---

## Phase 4: User Story 2 — Create a New Custom Theme (Priority: P2)

**Goal**: Users can create a brand-new theme from scratch using a form with color picker, layer stack editor, and validation.

**Independent Test**: Click "New Theme", fill in all fields including colors via picker and at least one layer, click Save. Verify JSON file appears in ~/.xlight/custom_themes/ and theme shows in list with Custom badge.

### Implementation for User Story 2

- [x] T014 [US2] Implement POST /themes/api/save endpoint in src/review/theme_routes.py. Accept JSON body with theme object and optional original_name. Validate name uniqueness across ALL themes (built-in + custom) — if original_name is set (rename case), exclude it from uniqueness check. Run validate_theme() from src/themes/validator.py. On validation failure: return 400 with error message and validation_errors array. On success: call save_theme() from writer.py, then _reload_library(), return 200 with success/theme_name/file_path. See contracts/theme-api.md.
- [x] T015 [P] [US2] Implement POST /themes/api/validate endpoint in src/review/theme_routes.py. Same validation as save but does not write to disk. Returns {valid: bool, errors: []}. Always returns 200 (errors in body). Used for real-time client-side validation.
- [x] T016 [US2] Add pytest tests for save and validate endpoints in tests/unit/test_theme_routes.py. Test: save valid theme returns 200 and creates file, save with duplicate name returns 400, save with invalid palette returns 400 with specific error, validate endpoint returns errors without writing, rename (original_name set) allows reuse of own name.
- [x] T017 [US2] Build the theme edit form UI in src/review/static/theme-editor.js. Create a renderEditForm(theme) function that replaces the right panel content with an editable form. Fields: name (text input), mood (select dropdown), occasion (select dropdown), genre (select dropdown), intent (textarea), palette (color list component — see T018), accent palette (optional color list — same component with "optional" label), layers (layer stack component — see T019), variants (variant list component — see T020). Add "Save" and "Cancel" buttons at bottom. Cancel returns to detail view without saving.
- [x] T018 [US2] Build the color palette editor component in src/review/static/theme-editor.js. Renders an ordered list of color swatches. Each swatch has: a colored rectangle, a hex text input, an <input type="color"> picker button, a remove (×) button. Add an "Add Color" button at the bottom. Support drag reorder via up/down arrow buttons on each swatch. Live preview: as colors change, the swatch rectangles update immediately. For the main palette, enforce minimum 2 colors (disable remove when at 2). For accent palette, allow 0 colors (empty = no accent palette) but if any colors exist enforce minimum 2.
- [x] T019 [US2] Build the layer stack editor component in src/review/static/theme-editor.js. Renders an ordered list of layers. Each layer row has: effect name (select dropdown populated from GET /themes/api/effects), blend mode (select dropdown populated from effects endpoint blend_modes array), up/down reorder buttons, remove (×) button, and an expandable parameter section. When an effect is selected, fetch its parameters from the cached effects data and render each parameter with the appropriate widget: slider (for int/float with min/max), checkbox (for bool), select dropdown (for choice), text input (for string). Pre-fill defaults. Enforce bottom layer blend mode = Normal (auto-set, show notice if user tries to change). Prevent modifier effects on bottom layer (filter them from dropdown or show error). Add "Add Layer" button. Minimum 1 layer (disable remove when at 1).
- [x] T020 [US2] Build the variant editor component in src/review/static/theme-editor.js. Renders a list of variants, each containing its own layer stack editor (reuse the component from T019). Add "Add Variant" button. Each variant has a remove button and a collapsible header ("Variant 1", "Variant 2", etc). Variants are optional — section is hidden if empty, with just an "Add Variant" button.
- [x] T021 [US2] Wire up the "New Theme" button and save flow in src/review/static/theme-editor.js. Enable the "New Theme" button in the toolbar. On click: render an empty edit form with defaults (mood: ethereal, occasion: general, genre: any, empty palette with 2 white swatches, one empty Color Wash layer with Normal blend). On "Save" click: collect form data into a theme object, POST to /themes/api/save. On success: reload theme list (re-fetch /themes/api/list), select the new theme in the list, switch to detail view. On 400 error: display validation errors inline near the relevant fields and as a summary banner at top of form.

**Checkpoint**: Create new themes from scratch with full color picker, layer editor, and validation. Themes persist as JSON files and appear in the browsable list.

---

## Phase 5: User Story 3 — Edit an Existing Theme (Priority: P2)

**Goal**: Users can switch the detail panel to edit mode, modify any field, save changes. Built-in themes create overrides. Custom themes rename supported. Unsaved changes are guarded.

**Independent Test**: Select a built-in theme, click Edit, see override notice, change palette, save. Verify custom override file created. Click "Restore defaults" — override removed, original reappears. Select a custom theme, rename it, verify file renamed on disk.

### Implementation for User Story 3

- [x] T022 [US3] Implement POST /themes/api/restore endpoint in src/review/theme_routes.py. Accept {name: str}. Verify the name is a built-in theme. Verify a custom override exists (custom file with same name). Delete the custom file via delete_theme(). Reload library. Return success message. Return 400 if no override exists or name is not a built-in. Add pytest test in tests/unit/test_theme_routes.py: restore removes override, restore without override returns 400, restore non-builtin returns 400.
- [x] T023 [US3] Enable the "Edit" button in detail view in src/review/static/theme-editor.js. When clicked, call renderEditForm() (from T017) with the current theme data pre-filled. If the theme is built-in (is_custom === false), show a notice banner: "Editing a built-in theme will create a custom override. You can restore the original later." If the theme is a custom override of a built-in (has_builtin_override === true), show a "Restore Defaults" button that POSTs to /themes/api/restore, then reloads the list and selects the restored built-in.
- [x] T024 [US3] Implement rename support in the edit form in src/review/static/theme-editor.js. When saving a theme where the name has changed from the original, pass original_name in the POST body to /themes/api/save. The backend handles: validating the new name is unique (excluding old name), writing the new file, deleting the old file (via the rename flow in writer.py). For built-in themes in edit mode, the name field should be read-only (cannot rename a built-in — the override keeps the same name).
- [x] T025 [US3] Implement unsaved changes guard in src/review/static/theme-editor.js. Track a dirty flag: set to true when any form field changes from its initial value. When dirty and the user tries to: select a different theme from the list, click "New Theme", or navigate away (beforeunload event) — show a confirm dialog: "You have unsaved changes. Discard and continue?" If confirmed, discard and proceed. If cancelled, stay on current edit. Reset dirty flag on successful save or cancel.

**Checkpoint**: Full edit flow works — view mode, edit mode toggle, built-in override with notice, restore defaults, rename custom themes, unsaved changes guard.

---

## Phase 6: User Story 6 — Deep Link and New-Tab Access (Priority: P2)

**Goal**: Theme editor URLs are bookmarkable with query params. Other pages can link to a specific theme in a new tab.

**Independent Test**: Navigate to /themes?theme=Inferno — Inferno is auto-selected. Navigate to /themes?theme=Nonexistent — "not found" notification with full list visible. From story review, click a theme name — opens theme editor in new tab with that theme selected.

### Implementation for User Story 6

- [x] T026 [US6] Implement deep link handling on page load in src/review/static/theme-editor.js. On DOMContentLoaded, after themes are loaded, parse window.location.search for "theme" and "mode" params. If "theme" param exists: find the theme by name (case-insensitive). If found: select it in the list, scroll to it, render detail view. If mode=edit, immediately enter edit mode. If not found: show a notification banner "Theme '[name]' not found" that auto-dismisses after 5 seconds, and display the full theme list.
- [x] T027 [US6] Update URL on theme selection in src/review/static/theme-editor.js. When the user selects a theme, use history.replaceState() to update the URL to /themes?theme=ThemeName (without page reload). When entering edit mode, add &mode=edit. When returning to list view (deselecting), remove query params. This makes the current view bookmarkable at all times.
- [x] T028 [US6] Add theme editor deep links to story review UI in src/review/static/story-review.js. In the preferences panel where the theme lock text input is, add a small link icon/button next to the theme name. When clicked, open /themes?theme=ThemeName&mode=edit in a new tab (window.open with target="_blank"). In the section overrides area, if a section has a theme override, display the theme name as a clickable link that opens the theme editor in a new tab. Only show link if theme name is non-empty.

**Checkpoint**: Deep linking works — URLs resolve to correct themes, story review links open editor in new tabs, URLs update as user navigates.

---

## Phase 7: User Story 4 — Duplicate a Theme (Priority: P3)

**Goal**: Users can duplicate any theme as a starting point for a new custom theme.

**Independent Test**: Select any theme, click Duplicate, verify form opens pre-filled with "ThemeName Copy" as name. Modify and save. Verify original unchanged, new theme created.

### Implementation for User Story 4

- [x] T029 [US4] Add "Duplicate" button to the detail view toolbar in src/review/static/theme-editor.js. When clicked: deep-copy the current theme's data, set name to "{original name} Copy" (if that name exists, append " 2", " 3", etc.), switch to edit mode with the form pre-filled. The original theme remains selected in the list (grayed out) until the duplicate is saved, at which point the new theme is selected. Reuses the edit form from T017 — no new UI components needed.

**Checkpoint**: Duplicate flow works end-to-end. Original theme preserved, copy saved as new custom theme.

---

## Phase 8: User Story 5 — Delete a Custom Theme (Priority: P3)

**Goal**: Users can delete custom themes with confirmation. Built-in themes cannot be deleted.

**Independent Test**: Select a custom theme, click Delete, confirm in dialog. Theme removed from list and file deleted from disk. Select a built-in theme — Delete button not visible.

### Implementation for User Story 5

- [x] T030 [US5] Implement POST /themes/api/delete endpoint in src/review/theme_routes.py. Accept {name: str}. Verify the theme is custom (not built-in only). Call delete_theme() from writer.py. Reload library. Return success. Return 400 if built-in, 404 if not found. Add pytest test in tests/unit/test_theme_routes.py: delete custom theme succeeds, delete built-in returns 400, delete nonexistent returns 404.
- [x] T031 [US5] Add "Delete" button to detail view in src/review/static/theme-editor.js. Only visible when the selected theme is custom (is_custom === true). On click: show a confirm dialog "Delete theme '{name}'? This action cannot be undone." On confirm: POST to /themes/api/delete, reload theme list, clear the right panel to "Select a theme" placeholder. On cancel: do nothing. If the deleted theme was a custom override of a built-in, the built-in reappears in the list automatically (handled by library reload).

**Checkpoint**: Delete flow works. Built-in themes protected. Override deletion restores built-in.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final refinements affecting multiple user stories

- [x] T032 [P] Add keyboard accessibility in src/review/static/theme-editor.js. Ensure all buttons and form controls are keyboard-navigable (tab order). Add Escape key to close edit mode (with unsaved changes guard). Add Enter key on search input to prevent form submission.
- [x] T033 [P] Add loading and error states in src/review/static/theme-editor.js. Show a spinner or "Loading themes..." message while fetching /themes/api/list. Show error banner if fetch fails (e.g., server not running). Show "Saving..." state on save button while POST is in flight (disable button to prevent double-submit). Handle storage-not-writable errors from save/delete endpoints: if the backend returns a write permission error, display a clear message and disable save/delete buttons while keeping browse functional.
- [x] T034 [P] Scale validation for SC-007: write a pytest test in tests/unit/test_theme_routes.py that creates 100 custom theme JSON files in a temp directory, loads the theme library, and verifies GET /themes/api/list returns all themes and completes within 2 seconds.
- [x] T035 Run all pytest tests and verify pass: pytest tests/unit/test_theme_writer.py tests/unit/test_theme_routes.py -v
- [x] T036 Manual end-to-end validation: launch server with xlight-analyze review, navigate to /themes, exercise all 6 user stories per spec acceptance scenarios, verify against quickstart.md.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 Browse (Phase 3)**: Depends on Phase 2 — no other story dependencies
- **US2 Create (Phase 4)**: Depends on Phase 3 (needs list UI and detail view to exist)
- **US3 Edit (Phase 5)**: Depends on Phase 4 (reuses edit form components)
- **US6 Deep Link (Phase 6)**: Depends on Phase 3 (needs list and detail view)
- **US4 Duplicate (Phase 7)**: Depends on Phase 4 (reuses edit form)
- **US5 Delete (Phase 8)**: Depends on Phase 3 (needs list and detail view)
- **Polish (Phase 9)**: Depends on all user story phases

### User Story Dependencies

- **US1 (P1)**: Foundation only — MVP, standalone
- **US2 (P2)**: Depends on US1 (needs browse UI as base)
- **US3 (P2)**: Depends on US2 (reuses edit form components)
- **US6 (P2)**: Depends on US1 (needs browse/detail view); independent of US2/US3
- **US4 (P3)**: Depends on US2 (reuses edit form)
- **US5 (P3)**: Depends on US1 (needs list/detail); independent of US2/US3

### Parallel Opportunities

After Phase 2, these can run in parallel:
- US6 (Deep Link) is independent of US2/US3/US4/US5
- US5 (Delete) only needs US1, can run parallel with US2

After Phase 4 (US2 Create):
- US3 (Edit) and US4 (Duplicate) can run in parallel

### Within Each User Story

- Backend endpoints before frontend integration
- Core rendering before interaction handlers
- Save flow last (depends on form + validation)

---

## Parallel Example: Phase 2 (Tests)

```text
# These test tasks can run in parallel (different files):
T004: pytest tests for writer in tests/unit/test_theme_writer.py
T005: pytest tests for API routes in tests/unit/test_theme_routes.py
```

## Parallel Example: After Phase 3

```text
# These story phases can start in parallel (different concerns):
Phase 6 (US6 Deep Link): Only needs browse UI from Phase 3
Phase 8 (US5 Delete): Only needs list/detail from Phase 3
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T008)
3. Complete Phase 3: US1 Browse (T009-T013)
4. **STOP and VALIDATE**: Navigate to /themes, browse themes, filter, search, view details
5. Demo-ready MVP

### Incremental Delivery

1. Setup + Foundational → API endpoints ready
2. US1 Browse → Theme browser live (MVP!)
3. US2 Create → Users can make new themes
4. US3 Edit → Users can modify existing themes
5. US6 Deep Link → Cross-page integration
6. US4 Duplicate → Convenience workflow
7. US5 Delete → Housekeeping
8. Polish → Accessibility, loading states, E2E validation

### Parallel Team Strategy

With multiple developers after Phase 2:

- Developer A: US1 (browse) → US2 (create) → US3 (edit)
- Developer B: US6 (deep link) → US5 (delete) → US4 (duplicate)
- Both: Phase 9 polish

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently testable once its phase is complete
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Vanilla JS frontend — no build step, no framework, consistent with existing review UI
- All theme validation reuses existing src/themes/validator.py — no duplication
