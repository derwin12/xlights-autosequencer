# Tasks: Layout Group Editor

**Input**: Design documents from `/specs/022-layout-group-editor/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api-routes.md ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: User story this task belongs to (US1–US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create all new module files and stubs so later phases can work in parallel without file conflicts.

- [x] T001 Create `src/grouper/editor.py` with module docstring, imports (dataclasses, json, hashlib, pathlib), and empty placeholder functions
- [x] T002 [P] Add `grouper-edit` CLI command stub to `src/cli.py` (click command that accepts a layout path argument and prints "not yet implemented")
- [x] T003 [P] Create `src/review/static/grouper.html` skeleton page (html/head/body with title "Layout Group Editor", empty div#app, script and link tags pointing to grouper.js and grouper.css)
- [x] T004 [P] Create `src/review/static/grouper.js` with module-level comment and empty exported functions matching the routes in contracts/api-routes.md
- [x] T005 [P] Create `src/review/static/grouper.css` with file header comment and empty rule blocks for tier tabs, group cards, prop items, and drop target states

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data model and edit engine that every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T006 Implement `GroupingEdits`, `PropMove`, `GroupDef`, and `MergedGrouping` dataclasses in `src/grouper/editor.py` exactly as defined in `specs/022-layout-group-editor/data-model.md`
- [x] T007 [P] Implement MD5 keying helpers in `src/grouper/editor.py`: `layout_md5(layout_path: Path) -> str` (reads file bytes, returns hex digest) and `edits_path(layout_path: Path) -> Path` (returns sibling `<md5>_grouping_edits.json` path)
- [x] T008 [P] Implement JSON serialization in `src/grouper/editor.py`: `edits_to_dict(edits: GroupingEdits) -> dict` and `edits_from_dict(data: dict) -> GroupingEdits` (round-trips all fields including nested PropMove and GroupDef lists)
- [x] T009 Implement `load_baseline(layout_path: Path) -> tuple[list[PowerGroup], list[str]]` in `src/grouper/editor.py` — calls `parse_layout`, `normalize_coords`, `classify_props`, `generate_groups` and returns (baseline_groups, all_prop_names)
- [x] T010 Implement `apply_edits(baseline: list[PowerGroup], edits: GroupingEdits, all_prop_names: list[str]) -> MergedGrouping` in `src/grouper/editor.py` — applies moves, additions, deletions, renames on top of baseline; computes `edited_props` set; validates no duplicate membership per tier; prunes stale prop names not in `all_prop_names`
- [x] T011 Write unit tests for foundational editor functions in `tests/unit/test_grouper_editor.py`: dataclass field presence, MD5 keying determinism, JSON round-trip, `apply_edits` with moves/adds/deletes/renames, stale prop pruning, duplicate membership rejection
- [x] T012 Register GET `/grouper` route in `src/review/server.py` `create_app()` to serve `grouper.html` from the static folder
- [x] T013 Wire `grouper-edit` CLI command in `src/cli.py` to call `create_app()` and open the browser at `http://localhost:5173/grouper?path=<layout_path>`

**Checkpoint**: `python -m pytest tests/unit/test_grouper_editor.py -v` passes. `xlight-analyze grouper-edit <path>` opens a page in browser (content placeholder ok).

---

## Phase 3: User Story 1 — View Auto-Generated Grouping (Priority: P1) 🎯 MVP

**Goal**: Users can load a layout file and see all 8 tiers with their auto-generated groups and member props, organized in per-tier tabs with an Ungrouped section.

**Independent Test**: `GET /grouper/layout?path=<xml>` returns JSON with all 8 tier objects, each containing groups and ungrouped lists. `grouper.html` renders tier tabs and prop cards without errors.

- [x] T014 [US1] Implement `GET /grouper/layout` route in `src/review/server.py`: call `load_baseline()`, call `load_edits()` (returns None if no edits), call `apply_edits()`, serialize to JSON response matching the schema in `contracts/api-routes.md` (layout_md5, props array, tiers array with groups + ungrouped, has_edits, edited_props)
- [x] T015 [P] [US1] Implement tier tab bar in `src/review/static/grouper.html`: 8 tab buttons (Canvas, Spatial, Architecture, Rhythm, Fidelity, Prop Type, Compound, Heroes) plus a div#tier-content area; active tab highlighted
- [x] T016 [P] [US1] Implement `loadLayout(layoutPath)` in `src/review/static/grouper.js`: fetches `GET /grouper/layout?path=<path>`, stores response in module state, calls `renderTierTab(tierIndex)` to render the active tier's groups and ungrouped section as prop cards
- [x] T017 [P] [US1] Add tier tab styles and group card layout in `src/review/static/grouper.css`: tab bar with active state, group card box with header and prop list, ungrouped section distinct style, edited-prop badge indicator (orange dot)
- [x] T018 [US1] Display prop metadata (name, pixel_count, display_as) on each prop card in `src/review/static/grouper.js` and `src/review/static/grouper.html`

**Checkpoint**: Open editor with a real layout file. All 8 tier tabs visible. Clicking a tab shows groups with prop cards. Ungrouped section shows any unassigned props.

---

## Phase 4: User Story 2 — Drag-and-Drop Tier Assignment (Priority: P1)

**Goal**: Users can drag a prop card from one group (or Ungrouped) and drop it into another group (or Ungrouped) within the current tier. Visual feedback during drag. Multi-select supported.

**Independent Test**: Drag a prop from Group A to Group B. POST `/grouper/move` is called. The UI updates both group member lists immediately. Dragging to Ungrouped also works.

- [x] T019 [US2] Implement `POST /grouper/move` route in `src/review/server.py`: parse `{layout_md5, moves[]}`, validate each prop exists and is not already in the target group, apply moves to in-memory edit state (do not save to disk), return updated tier groups + ungrouped + edited_props per `contracts/api-routes.md`
- [x] T020 [P] [US2] Implement HTML5 drag-and-drop on prop cards in `src/review/static/grouper.js`: set `draggable=true` on prop elements, add `dragstart` handler (stores prop name and source group), `dragover` handler on group containers (preventDefault to allow drop), `drop` handler (calls `POST /grouper/move` and re-renders tier)
- [x] T021 [P] [US2] Implement multi-select in `src/review/static/grouper.js`: click selects/deselects prop cards (toggle `.selected` class), drag of a selected card drags all selected props together (sends multiple moves in one POST)
- [x] T022 [P] [US2] Add drag-and-drop visual feedback styles in `src/review/static/grouper.css`: `.drag-over` highlight on valid drop targets (blue border), `.dragging` opacity on dragged card, `.selected` highlight on selected cards
- [x] T023 [US2] Write unit test for move validation in `tests/unit/test_grouper_editor.py`: move to same group rejected (409), prop not in layout rejected (400), valid move updates from_group and to_group membership

**Checkpoint**: Drag a prop card between two groups. The move is instant. Drop target highlights during hover. Multi-selecting 3 props and dragging moves all 3.

---

## Phase 5: User Story 3 — Persist Edits Separately (Priority: P1)

**Goal**: Users can Save edits to `<md5>_grouping_edits.json` (keeping baseline untouched), reload and see the same state, and Reset to discard all edits.

**Independent Test**: Make edits, click Save, close browser, reopen. The same edits are visible. Click Reset and the original auto-generated grouping is restored.

- [x] T024 [US3] Implement `save_edits(edits: GroupingEdits, layout_path: Path) -> None` in `src/grouper/editor.py`: serializes edits to `edits_to_dict()` and writes to `edits_path(layout_path)` with `updated_at` timestamp
- [x] T025 [P] [US3] Implement `load_edits(layout_path: Path) -> GroupingEdits | None` in `src/grouper/editor.py`: returns None if edit file does not exist, otherwise reads and deserializes; prunes any prop_names not in the current layout (stale after layout changes)
- [x] T026 [P] [US3] Implement `reset_edits(layout_path: Path) -> None` in `src/grouper/editor.py`: deletes the edit file if it exists
- [x] T027 Implement `POST /grouper/save` route in `src/review/server.py`: calls `save_edits()` with current in-memory edits state, returns `{success, edits_path}` per contracts
- [x] T028 [P] [US3] Implement `POST /grouper/reset` route in `src/review/server.py`: calls `reset_edits()`, clears in-memory edits state, returns `{success, message}` per contracts
- [x] T029 [US3] Add Save and Reset buttons to `src/review/static/grouper.html` and wire to `POST /grouper/save` and `POST /grouper/reset` in `src/review/static/grouper.js`; show status feedback ("Saved ✓" / "Reset to original") for 2 seconds after each action
- [x] T030 [P] [US3] Render edited-prop diff indicators in `src/review/static/grouper.js`: props in `edited_props` set get a visible badge (orange dot per T017 css) so users can see what was manually changed vs. auto-assigned
- [x] T031 [US3] Write integration round-trip test in `tests/integration/test_grouper_editor_roundtrip.py`: load layout → apply move via POST /grouper/move → POST /grouper/save → reload via GET /grouper/layout → assert moved prop is in new group and edited_props contains it; then POST /grouper/reset → reload → assert prop is back in original group

**Checkpoint**: Edit, save, reopen. Edits preserved. Reset works. Diff indicators show on moved props.

---

## Phase 6: User Story 4 — Create and Remove Groups (Priority: P2)

**Goal**: Users can create a new named group within a tier, delete an empty or non-empty group (members go to Ungrouped), and rename a group.

**Independent Test**: Create group "08_HERO_TestTree" in Tier 8. Drag a prop into it. Rename it to "08_HERO_FirTree". Delete it — prop appears in Ungrouped. Save and reload — changes persisted.

- [x] T032 [US4] Implement `add_group_to_edits(edits, name, tier)`, `remove_group_from_edits(edits, group_name)`, `rename_group_in_edits(edits, old_name, new_name)` in `src/grouper/editor.py`: validate name starts with correct tier prefix, enforce name uniqueness, move displaced members to Ungrouped on delete
- [x] T033 [P] [US4] Implement `POST /grouper/group/create`, `POST /grouper/group/delete`, and `POST /grouper/group/rename` routes in `src/review/server.py` per schemas in `contracts/api-routes.md`; return updated group list for affected tier
- [x] T034 [P] [US4] Implement create group UI in `src/review/static/grouper.js`: "New Group" button per tier tab opens an inline name input; on confirm calls `POST /grouper/group/create` and re-renders tier
- [x] T035 [P] [US4] Implement delete and rename group UI in `src/review/static/grouper.js`: each group card header has a rename (pencil icon, inline edit on click) and delete (trash icon, confirmation prompt) button; calls respective POST routes and re-renders tier

**Checkpoint**: Full group CRUD works. Renamed groups appear with new name. Deleted group's props appear in Ungrouped.

---

## Phase 7: User Story 5 — Export Merged Grouping (Priority: P2)

**Goal**: Users can export the final merged grouping as `<md5>_grouping.json` so the sequence generator can consume it without re-running auto-grouping.

**Independent Test**: Make edits, click Export. `<md5>_grouping.json` appears adjacent to the layout file. Load it as JSON and verify it contains a list of `{name, tier, members}` objects covering all 8 tiers.

- [x] T036 [US5] Implement `export_grouping(merged: MergedGrouping, layout_path: Path) -> Path` in `src/grouper/editor.py`: serializes `merged.groups` as `[{"name": g.name, "tier": g.tier, "members": g.members}]` to `<md5>_grouping.json` adjacent to the layout file; returns the output path
- [x] T037 [P] [US5] Implement `POST /grouper/export` route in `src/review/server.py`: builds current merged grouping (applies in-memory edits to baseline), calls `export_grouping()`, returns `{success, export_path, group_count, has_edits, edited_prop_count}` per contracts
- [x] T038 [P] [US5] Add Export button to `src/review/static/grouper.html` and wire to `POST /grouper/export` in `src/review/static/grouper.js`; display success banner with export path and group count; display error message on failure
- [x] T039 [US5] Write integration test for export in `tests/integration/test_grouper_editor_roundtrip.py`: load layout → move one prop → export → read `_grouping.json` → assert all 8 tiers present → assert moved prop is in its new group → assert group count matches expected

**Checkpoint**: Export button produces `_grouping.json`. File is valid JSON with all tiers. Sequence generator can read it (manual verify).

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling and end-to-end validation.

- [x] T040 Handle stale prop detection in `src/grouper/editor.py` `load_edits()`: when layout has changed since edits were saved (new or removed props), log a warning listing added/removed props; added props appear in Ungrouped, removed props are pruned from all edit records
- [x] T041 [P] Handle empty layout (zero props) in `GET /grouper/layout` route in `src/review/server.py`: return 200 with `{props: [], tiers: [...empty groups...]}` and display an informational banner in `src/review/static/grouper.js` ("No props found in layout")
- [x] T042 [P] Add fully-excluded prop indicator in `src/review/static/grouper.js`: after applying edits, compute props that appear in no group across all tiers; render them in a collapsible "Excluded from Sequencing" panel with a warning note; props removed from Tier 1 are a common case (e.g., tune-to signs)
- [x] T043 Run quickstart.md end-to-end: launch editor with a real layout, make edits across 3 tiers, save, close, reopen and verify edits, export, confirm `_grouping.json` structure

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; all T001–T005 in parallel
- **Phase 2 (Foundational)**: Depends on Phase 1 — T006–T013 must complete before any user story
- **Phase 3 (US1)**: Depends on Phase 2 — specifically T009, T012, T013
- **Phase 4 (US2)**: Depends on Phase 3 (needs GET /grouper/layout and rendered prop cards)
- **Phase 5 (US3)**: Depends on Phase 4 (save/load must persist the same moves that drag-drop creates)
- **Phase 6 (US4)**: Depends on Phase 5 (group CRUD edits are saved via the same save mechanism)
- **Phase 7 (US5)**: Depends on Phase 5 (export merges baseline + saved edits)
- **Phase 8 (Polish)**: Depends on all user story phases

### Within Each Phase — Parallel Opportunities

**Phase 1**: T001, T002, T003, T004, T005 all in parallel (separate new files)

**Phase 2**: T007, T008 in parallel (different functions in editor.py); T011 after T006–T010; T012, T013 in parallel after T001

**Phase 3**: T015, T016, T017, T018 in parallel after T014

**Phase 4**: T020, T021, T022 in parallel after T019

**Phase 5**: T025, T026, T028, T030 in parallel after T024; T029 after T027, T028

**Phase 6**: T033, T034, T035 in parallel after T032

**Phase 7**: T037, T038 in parallel after T036

---

## Parallel Example: Phase 3 (User Story 1)

```bash
# After T014 (GET /grouper/layout route) is done, launch these in parallel:
Task T015: "Implement tier tab bar in grouper.html"
Task T016: "Implement loadLayout() and renderTierTab() in grouper.js"
Task T017: "Add tier tab styles and group card layout in grouper.css"
Task T018: "Display prop metadata on prop cards in grouper.js"
```

---

## Implementation Strategy

### MVP First (User Stories 1–3 Only)

1. Complete Phase 1: Setup (parallel, ~30 min)
2. Complete Phase 2: Foundational (sequential, critical path)
3. Complete Phase 3: US1 — View grouping
4. Complete Phase 4: US2 — Drag-and-drop
5. Complete Phase 5: US3 — Persist edits
6. **STOP and VALIDATE**: Full edit workflow works end-to-end
7. Demo: open editor, edit tiers, save, reload, verify

### Incremental Delivery

1. Setup + Foundational → Editor loads and shows grouping (US1)
2. Add drag-and-drop (US2) → Props can be moved between groups
3. Add persistence (US3) → Edits survive browser close → **Full MVP**
4. Add group CRUD (US4) → Users can create/delete/rename groups
5. Add export (US5) → Generator can consume edited grouping

---

## Notes

- [P] tasks = different files or independent functions, no shared dependencies
- [Story] label maps each task to a user story for traceability
- No test framework changes needed — pytest already configured
- Vanilla JS only — no npm, no build step, no frameworks
- Server in-memory state: the Flask server holds current edits in a module-level dict keyed by layout_md5; edits are only written to disk on POST /grouper/save
- Prop names are the stable identity key — never use array indices for prop references
