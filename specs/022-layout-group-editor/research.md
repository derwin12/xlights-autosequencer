# Research: Layout Group Editor

**Feature**: 022-layout-group-editor | **Date**: 2026-03-30

## R1: Edit Persistence Model

**Decision**: Overlay/diff model — store only user changes, not the full grouping state.

**Rationale**: The spec requires preserving the original auto-generated grouping separately from edits. An overlay model stores only the delta (prop moves, group additions, group deletions, renames) and merges them at read-time or export-time. This enables:
- Showing visual diff indicators (which props were moved)
- Resetting to baseline without data loss
- Re-applying edits when the auto-grouper is re-run on an updated layout

**Alternatives considered**:
- Full snapshot model (store complete grouping state after edits): Simpler merge but loses diff information. Cannot show "what changed" without comparing to baseline. Rejected because diff visibility is a spec requirement (FR-015).
- Operation log (store each individual edit as an event): Most flexible but complex to replay and compact. Over-engineered for the current need. Rejected per Simplicity First principle.

## R2: Edit File Format and Keying

**Decision**: JSON file keyed by MD5 hash of layout file content, stored as `<md5>_grouping_edits.json` adjacent to the layout file.

**Rationale**: Matches existing caching pattern used by stem separation (`.stems/<md5>/`) and analysis cache (`<md5>_analysis.json`). MD5 of file content is resilient to file moves/renames. Adjacent storage keeps edits discoverable.

**Alternatives considered**:
- Central `~/.xlight/` directory: Would work but separates edits from the layout file, making them harder to discover and share. Rejected.
- Filename-based keying: Fragile — renaming the layout file orphans the edits. Rejected.

## R3: Flask Route Pattern

**Decision**: Register routes directly in `create_app()` within `server.py`, matching the existing monolithic pattern.

**Rationale**: The existing review server registers all routes directly in the app factory function. No blueprints are used. Introducing blueprints for one feature would be inconsistent and add unnecessary complexity.

**Alternatives considered**:
- Flask Blueprint: Cleaner separation but inconsistent with the rest of the codebase. Would require refactoring existing routes to match. Rejected per Simplicity First.

## R4: Frontend Drag-and-Drop Approach

**Decision**: HTML5 native Drag and Drop API with vanilla JS.

**Rationale**: The existing frontend uses vanilla JS with no frameworks (Canvas 2D + Web Audio for the timeline). HTML5 drag-and-drop is natively supported in all modern browsers, requires no dependencies, and is well-suited for list-based card reordering.

**Alternatives considered**:
- Third-party drag library (SortableJS, etc.): More polished UX but adds a dependency. Rejected per no-new-dependency constraint.
- Custom mouse event handling: More control but more code. HTML5 DnD is sufficient for card-between-container moves. Rejected.

## R5: Tier Tab Navigation

**Decision**: Tab bar with 8 tier tabs. Selecting a tab shows that tier's groups and ungrouped section. Only one tier visible at a time.

**Rationale**: With 8 tiers and potentially 40+ groups, showing everything at once would be overwhelming. Per-tier tabs keep the editing context focused. This was confirmed in clarification Q1.

**Alternatives considered**:
- Accordion (all tiers collapsible on one page): Too much scrolling with many groups. Rejected.
- Split view (tier list + detail panel): More complex layout for marginal benefit. Rejected.

## R6: Existing Grouper Integration

**Decision**: Call `parse_layout()`, `normalize_coords()`, `classify_props()`, and `generate_groups()` from existing modules to produce the baseline. The editor module only handles the edit overlay.

**Rationale**: The existing grouper pipeline is well-tested and produces the correct baseline. No need to duplicate or modify it. The editor's job is to let users adjust the output, not replace the algorithm.

**Key integration points**:
- `src/grouper/layout.py`: `parse_layout(path) -> Layout` — returns props + raw XML tree
- `src/grouper/classifier.py`: `normalize_coords(props)` and `classify_props(props)` — mutate props in-place
- `src/grouper/grouper.py`: `generate_groups(props, profile) -> list[PowerGroup]` — returns baseline groups
- `src/grouper/grouper.py`: `PowerGroup(name, tier, members)` — the group data contract

## R7: Export Format

**Decision**: JSON file (`<md5>_grouping.json`) containing the merged grouping (baseline + edits applied). Structure mirrors the PowerGroup list: array of `{name, tier, members}` objects.

**Rationale**: JSON is the standard interchange format in this project. The generator already reads JSON analysis/story files. The format is simple and directly maps to the existing PowerGroup dataclass.

**Alternatives considered**:
- Inject into xLights XML: Would modify the user's layout file, which is risky and out of scope. Rejected.
- Python pickle: Not human-readable, not portable. Rejected.
