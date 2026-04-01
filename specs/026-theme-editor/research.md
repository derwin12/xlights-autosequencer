# Research: Theme Editor

**Feature**: 026-theme-editor | **Date**: 2026-04-01

## R1: Theme File I/O Strategy

**Decision**: Create a `src/themes/writer.py` module for all custom theme file operations (save, delete, rename).

**Rationale**: The existing `library.py` only reads themes. Write operations need to be isolated for testability and to avoid coupling Flask routes to file I/O directly. The writer module handles:
- Saving a theme dict as a JSON file (slugified filename from theme name)
- Deleting a custom theme file by name
- Renaming a theme (write new file, delete old file, update name field)
- Ensuring the `~/.xlight/custom_themes/` directory exists (create on first write)

**Alternatives considered**:
- Adding write methods to ThemeLibrary class — rejected because ThemeLibrary is a read-only query object; mixing read/write violates its design.
- Writing directly in Flask routes — rejected because it makes unit testing harder and couples I/O to HTTP handling.

## R2: Custom Theme File Naming Convention

**Decision**: Slugify the theme name for the filename: lowercase, replace spaces with hyphens, strip non-alphanumeric characters. Example: "My Cool Theme" → `my-cool-theme.json`.

**Rationale**: The existing convention in `~/.xlight/custom_themes/` is `*.json` files loaded via sorted glob. Slugified names are human-readable, filesystem-safe, and sort predictably. The theme `name` field inside the JSON is the canonical identifier; the filename is derived from it.

**Alternatives considered**:
- UUID filenames — rejected because they're not human-readable when browsing the filesystem.
- Exact name as filename — rejected because spaces and special characters cause filesystem issues.

## R3: Theme Library Reload Strategy

**Decision**: Reload the ThemeLibrary in-process after each write operation (save/delete/rename) by calling `load_theme_library()` again and updating the module-level reference.

**Rationale**: The theme editor runs in the same Flask process that serves the API. After a write, the in-memory library must reflect the change for subsequent reads. Since theme count is small (~100 max) and load is fast (<100ms), a full reload is simpler and safer than incremental cache updates. This does NOT reload other running services (e.g., sequence generator) — themes are written to JSON for later consumption.

**Alternatives considered**:
- Incremental update (add/remove single theme from dict) — rejected because it risks drift between in-memory state and disk; full reload is cheap enough.
- No reload (read from disk every request) — rejected because it would be slow and wasteful for list/filter operations.

## R4: Frontend Architecture

**Decision**: Vanilla JS single-page application (`theme-editor.html` + `theme-editor.js` + `theme-editor.css`), consistent with existing review UI pattern.

**Rationale**: Every existing page in the review UI (story-review, upload, library, grouper, sweep) follows this pattern: a single HTML file with inline structure, a single JS file with all logic, a CSS file for styles, and fetch() calls to Flask API endpoints. No build toolchain, no framework. The theme editor follows the same pattern for consistency.

**Alternatives considered**:
- React/Vue/Svelte SPA — rejected because it would introduce a build toolchain inconsistent with the rest of the project.
- Embedding theme editor in story-review.html — rejected because the editor must be standalone (accessible without a song loaded).

## R5: Deep Linking Strategy

**Decision**: Use URL query parameters on the theme editor page. Pattern: `/themes?theme=Inferno` or `/themes?theme=Inferno&mode=edit`.

**Rationale**: Query parameters are simple, bookmarkable, and don't require complex client-side routing. The JS reads `window.location.search` on load, finds the theme by name, and selects it. The `mode=edit` parameter optionally opens edit mode directly. If the theme doesn't exist, a notification is shown and the full list is displayed.

**Alternatives considered**:
- Hash-based routing (`/themes#Inferno`) — rejected because query params are more standard and support multiple parameters.
- Path-based routing (`/themes/Inferno/edit`) — rejected because it requires Flask route changes for every path pattern and is over-engineered for this use case.

## R6: Name Uniqueness Validation

**Decision**: Validate theme name uniqueness across ALL themes (built-in + custom) on every save and rename operation. Validation happens server-side in the API endpoint; the frontend also checks client-side for immediate feedback.

**Rationale**: The spec explicitly requires blocking saves when the name collides with any theme (built-in or custom). Server-side validation is the source of truth; client-side validation is a UX convenience to avoid round-trips.

**Alternatives considered**:
- Client-side only validation — rejected because it could be bypassed and doesn't protect against race conditions between tabs.
- Allow override of built-in names via create — rejected per spec decision (only Edit flow creates overrides).

## R7: Color Picker Approach

**Decision**: Use the native HTML `<input type="color">` element for color selection, paired with a hex text input for manual entry.

**Rationale**: The native color picker is zero-dependency, works in all modern browsers, and provides a familiar OS-native UI. A hex text input alongside it allows precise entry. This is consistent with the project's no-external-dependencies frontend approach.

**Alternatives considered**:
- Third-party color picker library (e.g., Pickr, Spectrum) — rejected because it adds an external dependency inconsistent with the vanilla JS approach.
- Custom canvas-based color picker — rejected as over-engineered for this use case.

## R8: Layer Stack UI Pattern

**Decision**: Render layers as an ordered list with drag handles (or up/down buttons) for reordering, an effect dropdown per layer, a blend mode dropdown, and an expandable parameter section that auto-populates when an effect is selected.

**Rationale**: The layer stack is the most complex part of the editor UI. Each layer needs: effect name (dropdown from effect library), blend mode (dropdown from valid modes list), and parameter overrides (auto-populated from EffectDefinition.parameters with defaults). Up/down buttons are simpler than drag-and-drop and work reliably without a library.

**Alternatives considered**:
- Drag-and-drop with HTML5 drag API — viable but more complex; up/down buttons are sufficient for typical 1-4 layer stacks.
- Freeform JSON editing for layers — rejected because it defeats the purpose of a visual editor.

## R9: Hierarchical Theme List Grouping

**Decision**: Group themes by mood (primary grouping) with collapsible sections. Within each mood group, themes are sorted alphabetically. Custom themes are intermixed with built-in themes but distinguished by a badge.

**Rationale**: The 4 mood categories (ethereal, aggressive, dark, structural) provide a natural grouping that maps to how users think about themes. With 21 built-in + potentially 100+ custom themes, collapsible groups prevent overwhelming scroll. Mood is the most useful grouping because it's the primary selector in theme assignment.

**Alternatives considered**:
- Group by occasion — rejected because most themes are "general" occasion, creating one huge group.
- Group by genre — rejected because most themes are "any" genre, same problem.
- Flat list with filters only — rejected per spec requirement for hierarchical organization.

## R10: Built-in Theme Override via Edit Flow

**Decision**: When a user edits a built-in theme and saves, the system writes a custom theme file with the same name as the built-in. The ThemeLibrary's existing override behavior (custom overrides built-in by name) handles the rest. The "Restore defaults" action deletes the custom override file, revealing the original built-in.

**Rationale**: This reuses the existing override mechanism in `load_theme_library()` with zero changes to the loading logic. The editor UI needs to track which themes have custom overrides (custom file exists with same name as a built-in) to show the "Restore defaults" option.

**Alternatives considered**:
- Separate override storage (e.g., `~/.xlight/theme_overrides/`) — rejected as unnecessary complexity when the existing override-by-name mechanism works.
- Modifying built-in JSON — rejected because built-in themes are read-only (shipped with the application).
