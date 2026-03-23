# Tasks: Analysis Cache and Song Library

**Input**: Design documents from `/specs/010-analysis-cache-library/`
**Prerequisites**: plan.md, data-model.md, contracts/cli.md, research.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project structure required — all new files slot into existing layout.

- [x] T001 Confirm `src/cache.py`, `src/library.py`, `src/review/static/library.html`, `src/review/static/library.js` do not yet exist (pre-flight check before writing)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `source_hash` must exist on `AnalysisResult` and round-trip through JSON before any user story can be implemented.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Add `source_hash: str | None = None` field to `AnalysisResult` dataclass in `src/analyzer/result.py`
- [x] T003 Update `export.py` to write `source_hash` to analysis JSON and read it back (missing field deserializes to `None` for backward compatibility)

**Checkpoint**: `AnalysisResult.source_hash` exists and survives a write/read round-trip through `export.write()` / `export.read()`.

---

## Phase 3: User Story 1 — Analysis Caching (Priority: P1) MVP

**Goal**: `analyze song.mp3` is a cache hit (< 3 s) when output JSON exists with matching MD5. `--no-cache` forces a fresh run.

**Independent Test**: Run `analyze song.mp3` twice; second run prints "Cache hit" and returns in < 3 s. Run with `--no-cache`; all algorithms execute regardless.

### Tests for User Story 1

> **Write these tests FIRST — verify they FAIL before implementation**

- [x] T004 [P] [US1] Write unit tests for `AnalysisCache` in `tests/unit/test_cache.py`: `is_valid()` returns False when output missing, False when MD5 mismatch, True on match; `load()` returns `AnalysisResult`; `save()` writes `source_hash` into output JSON

### Implementation for User Story 1

- [x] T005 [US1] Implement `AnalysisCache` class in `src/cache.py`: `__init__(audio_path, output_path)`, `is_valid() -> bool` (MD5 of audio vs `source_hash` in output JSON), `load() -> AnalysisResult`, `save(result) -> None` (sets `result.source_hash` before writing)
- [x] T006 [US1] Add `--no-cache` flag to `analyze` command in `src/cli.py`; insert cache check before runner: if `AnalysisCache.is_valid()` and not `--no-cache`, call `cache.load()` and print cache-hit message; otherwise run algorithms then call `cache.save()`

**Checkpoint**: US1 fully functional — `analyze` with cache hit skips algorithms; `--no-cache` forces re-run.

---

## Phase 4: User Story 2 — Song Library Registration (Priority: P2)

**Goal**: Every successful `analyze` run upserts a `LibraryEntry` in `~/.xlight/library.json`. Library is created on first use.

**Independent Test**: Analyze a file; inspect `~/.xlight/library.json` — entry present with correct fields. Analyze again; `analyzed_at` updates, only one entry per hash.

### Tests for User Story 2

> **Write these tests FIRST — verify they FAIL before implementation**

- [x] T007 [P] [US2] Write unit tests for `Library` in `tests/unit/test_library.py`: `upsert()` adds entry; `upsert()` again replaces (one entry per hash); `all_entries()` sorted newest-first; `find_by_hash()` returns entry or None; index file auto-created; backward-compat with no `version` field

### Implementation for User Story 2

- [x] T008 [P] [US2] Implement `LibraryEntry` dataclass and `Library` class in `src/library.py`: `__init__(index_path=DEFAULT_LIBRARY_PATH)`, `upsert(entry)` (replace existing by `source_hash`), `all_entries() -> list[LibraryEntry]` (sorted by `analyzed_at` desc), `find_by_hash(source_hash) -> LibraryEntry | None`; auto-create `~/.xlight/` dir on first write
- [x] T009 [US2] After `cache.save()` in the `analyze` command in `src/cli.py`, build a `LibraryEntry` from the result metadata and call `Library().upsert(entry)`

**Checkpoint**: US2 fully functional — library file auto-created and updated after each analyze run, independent of US1 cache logic.

---

## Phase 5: User Story 3 — Review UI Library Browser (Priority: P3)

**Goal**: `xlight-analyze review` (no args) opens a library page listing all analyzed songs. Clicking a row loads the timeline without re-analysis.

**Independent Test**: Open review UI with no args; library page loads in < 1 s; all entries from `~/.xlight/library.json` appear; clicking a row loads the analysis timeline. Songs with missing source file show a warning badge.

### Implementation for User Story 3

- [x] T010 [P] [US3] Add `GET /library` route to `src/review/server.py`: reads `~/.xlight/library.json` via `Library.all_entries()`, computes `source_file_exists` at request time, returns JSON sorted newest-first; returns `{"version": "1.0", "entries": []}` if library missing
- [x] T011 [P] [US3] Add `GET /analysis?hash=<md5>` route to `src/review/server.py`: looks up entry by hash via `Library.find_by_hash()`, reads and returns the analysis JSON from `entry.analysis_path`; 404 with `{"error": "..."}` if not found
- [x] T012 [US3] Update the home route `/` in `src/review/server.py` to serve `library.html` instead of the current upload-only page (upload form remains present on the library page)
- [x] T013 [US3] Create `src/review/static/library.html`: table of library entries (filename, duration, BPM, tracks, stem flag, date), missing-file warning badge, "Analyze new file" upload section below the table (reuse existing upload UI)
- [x] T014 [US3] Create `src/review/static/library.js`: fetch `GET /library` on load, render rows into table, on row click fetch `GET /analysis?hash=` and navigate to the existing timeline view with that analysis data; show warning badge when `source_file_exists` is false

**Checkpoint**: US3 fully functional — library browser page loads and navigates to timeline; upload section still works.

---

## Phase 6: User Story 4 — `review` with Audio File Path (Priority: P4)

**Goal**: `xlight-analyze review song.mp3` resolves the audio path via library and opens the cached analysis directly.

**Independent Test**: Run `review song.mp3` after analyzing it; timeline opens without re-analysis. Run `review unanalyzed.mp3`; clear error message printed.

### Implementation for User Story 4

- [x] T015 [US4] Extend the `review` command in `src/cli.py`: if argument is not a `.json` file, compute MD5 of the path, call `Library().find_by_hash(md5)`, open `entry.analysis_path` if found; print clear error and exit if not found ("No cached analysis found — run 'analyze song.mp3' first.")

**Checkpoint**: US4 functional — `review song.mp3` opens cached analysis; `review unanalyzed.mp3` prints helpful error.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Integration test + quickstart validation.

- [x] T016 [P] Write end-to-end cache pipeline integration test in `tests/integration/test_cache_pipeline.py`: analyze a fixture WAV; verify `source_hash` written; analyze again and verify cache hit (no algorithm output); analyze with `--no-cache` and verify re-run; verify library entry present after each run
- [x] T017 Run quickstart.md validation: execute all three `analyze` scenarios (first run, cache hit, `--no-cache`) and both `review` scenarios (no args, audio file) against a real test file; confirm output matches contracts/cli.md expected console output

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational
- **US2 (Phase 4)**: Depends on Foundational; can run in parallel with US1 (different files: `library.py` vs `cache.py`)
- **US3 (Phase 5)**: Depends on US2 (needs library data)
- **US4 (Phase 6)**: Depends on US2 (needs `Library.find_by_hash`); can run in parallel with US3
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **US1**: Foundational complete → independent
- **US2**: Foundational complete → independent (parallel with US1)
- **US3**: US2 complete (needs Library)
- **US4**: US2 complete (needs Library.find_by_hash); parallel with US3

### Within Each User Story

- Tests written and FAILING before implementation
- `AnalysisCache` / `Library` implemented before CLI integration
- Models/dataclasses before services before CLI wiring

### Parallel Opportunities

- T004 (test_cache.py) and T007 (test_library.py) can run in parallel — different files
- T008 (library.py) and T005 (cache.py) can run in parallel — different files
- T010 (/library route) and T011 (/analysis?hash= route) can run in parallel — same file but non-conflicting additions
- T013 (library.html) and T014 (library.js) can run in parallel — different files
- US3 and US4 can proceed in parallel once US2 is complete

---

## Parallel Example: US1 + US2 (after Foundational)

```bash
# Run US1 and US2 in parallel (different files, no conflicts):
Task T004: Write tests/unit/test_cache.py
Task T007: Write tests/unit/test_library.py

# Then implement in parallel:
Task T005: Implement src/cache.py
Task T008: Implement src/library.py

# Then wire into CLI sequentially (both touch src/cli.py):
Task T006: --no-cache flag + cache logic in src/cli.py
Task T009: library upsert after analyze in src/cli.py
```

---

## Implementation Strategy

### MVP First (US1 + US2 only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 — Analysis Caching
4. Complete Phase 4: US2 — Library Registration
5. **STOP and VALIDATE**: cache hit works; library file populated
6. Continue to US3/US4 for full library browser

### Incremental Delivery

1. Foundational → `source_hash` in all future analysis files
2. US1 → fast repeat analysis (developer productivity win)
3. US2 → library auto-populated in background
4. US3 → library browser replaces upload-only home
5. US4 → `review song.mp3` shortcut

---

## Notes

- [P] tasks = different files, no in-flight dependencies
- No new Python dependencies — MD5 via `hashlib` (stdlib), JSON via `json` (stdlib)
- `src/cli.py` is modified in T006 (US1) and T009 (US2) and T015 (US4): do these sequentially to avoid conflicts
- Stem cache (`--stems` flag) is unaffected by `--no-cache` per Decision 6 in research.md
- Missing `source_hash` in existing JSON files → cache miss, not an error (backward compatible)
- `source_file_exists` is computed at request time in `/library` route, never stored in `library.json`
