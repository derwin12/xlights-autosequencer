# Tasks: Song Library Sequence Generation

**Input**: Design documents from `/specs/034-library-sequence-gen/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included per constitution Principle IV (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create shared test fixtures needed by all user stories

- [X] T001 Create tests/fixtures/generate/ directory and write a minimal valid xLights layout XML fixture at tests/fixtures/generate/mock_layout.xml containing at least 2 model elements (sufficient for parse_layout + generate_groups to run without error)
- [X] T002 [P] Create tests/fixtures/generate/mock_settings.json fixture: `{"layout_path": "<abs-path-to-mock_layout.xml>"}` — using an absolute path referencing the fixture file

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `src/settings.py` must exist before any generate route can call `get_layout_path()`. Unit tests must fail before implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Write unit tests for src/settings.py in tests/unit/test_settings.py: test `load_settings()` returns `{}` when file missing; test `save_settings({"layout_path": "/a/b"})` creates the file; test round-trip save+load preserves all keys; test `get_layout_path()` returns `Path` when set and `None` when unset — ensure ALL tests FAIL before T004
- [X] T004 Implement src/settings.py with three functions: `load_settings() -> dict` (reads `~/.xlight/settings.json`, returns `{}` if missing); `save_settings(updates: dict) -> None` (merges updates into settings file, creates `~/.xlight/` dir if needed); `get_layout_path() -> Path | None` (returns Path from `settings["layout_path"]` if key present and non-null, else `None`)

**Checkpoint**: `src/settings.py` tested and working. `python -c "from src.settings import get_layout_path; print(get_layout_path())"` runs without error.

---

## Phase 3: User Story 1 — Generate a Sequence from the Song Library (Priority: P1) 🎯 MVP

**Goal**: User opens a song's detail panel, clicks Generate, and receives a downloadable `.xsq` file. Layout must be configured; song must be analyzed. Progress is shown while running.

**Independent Test**: With a real analyzed song in the library and `settings.json` pointing to a valid layout XML with grouper edits, open the song's detail panel, click Generate, wait for completion, and a `.xsq` file downloads automatically.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation (T009+)**

- [X] T005 [P] [US1] Write unit tests for `GenerationJob` dataclass and `_sanitize_error()` in tests/unit/test_generate_routes.py: test all status values; test `_sanitize_error()` returns human-readable string for `FileNotFoundError` (layout missing), `ValueError` (bad config), and generic `Exception` — never exposing a raw traceback
- [X] T006 [P] [US1] Write unit tests for `POST /generate/<source_hash>` in tests/unit/test_generate_routes.py: test 404 when source_hash not in library; test 400 when `analysis_exists == False`; test 409 with `"setup_required": true` when `get_layout_path()` returns `None`; test 202 with `job_id` returned when all preconditions met (mock `_run_generation` to avoid real generation)
- [X] T007 [P] [US1] Write unit tests for `GET /generate/<source_hash>/status` in tests/unit/test_generate_routes.py: test 404 for unknown job_id; test each status value (`pending`, `running`, `complete`, `failed`) returned correctly; test `error` field present on failed jobs
- [X] T008 [P] [US1] Write unit tests for `GET /generate/<source_hash>/download/<job_id>` in tests/unit/test_generate_routes.py: test 404 when job not found; test 404 when job status is not `complete`; test 200 with file content when job is complete and output_path exists

### Implementation for User Story 1

- [X] T009 [US1] Create src/review/generate_routes.py: define `GenerationJob` dataclass (fields: `job_id`, `source_hash`, `status`, `output_path`, `error_message`, `genre`, `occasion`, `transition_mode`, `created_at`); create module-level `_jobs: dict[str, GenerationJob] = {}`; create `_temp_dir: Path = Path(tempfile.mkdtemp(prefix="xlight_gen_"))`; add `generate_bp = Blueprint("generate", __name__)`
- [X] T010 [US1] Implement `_sanitize_error(e: Exception) -> str` and `_run_generation(job: GenerationJob, config: GenerationConfig) -> None` in src/review/generate_routes.py: `_sanitize_error` maps `FileNotFoundError` → "Layout file not found — reconfigure in the grouper", `ValueError` → message string, generic → "Sequence generation failed — check your layout configuration"; `_run_generation` sets `job.status = "running"`, calls `generate_sequence(config)`, sets `job.output_path` and `job.status = "complete"`, catches all exceptions and sets `job.error_message` + `job.status = "failed"`
- [X] T011 [US1] Implement `POST /generate/<source_hash>` in src/review/generate_routes.py: look up `source_hash` in library (use `Library().find_by_hash(source_hash)`, 404 if missing); check `Path(entry.analysis_path).exists()` (400 if not); check `get_layout_path()` is not None and exists (409 with `{"error": "...", "setup_required": true}` if not); parse JSON body for `genre`, `occasion`, `transition_mode` with defaults; build `GenerationConfig(audio_path=entry.source_file, layout_path=layout_path, output_dir=_temp_dir, genre=genre, occasion=occasion, transition_mode=transition_mode)`; create `GenerationJob`, store in `_jobs[job_id]`; start daemon thread; return `{"job_id": job_id, "status": "pending"}` with 202
- [X] T012 [US1] Implement `GET /generate/<source_hash>/status` in src/review/generate_routes.py: require `job_id` query param; return 404 if not in `_jobs`; return JSON with all `GenerationJob` fields (serialise `output_path` as string, `created_at` as float)
- [X] T013 [US1] Implement `GET /generate/<source_hash>/download/<job_id>` in src/review/generate_routes.py: look up job in `_jobs`; return 404 if not found or `status != "complete"` or `output_path` is None; serve file with `send_file(job.output_path, as_attachment=True, download_name=f"{source_hash}.xsq")`
- [X] T014 [US1] Implement `GET /generate/settings` in src/review/generate_routes.py: return `{"layout_path": str(p) if p else None, "layout_configured": p is not None and p.exists()}` using `get_layout_path()`
- [X] T015 [US1] Register `generate_bp` in src/review/server.py: add `from src.review.generate_routes import generate_bp` and `app.register_blueprint(generate_bp, url_prefix="/generate")` in `create_app()`
- [X] T016 [US1] Update the grouper save handler in src/review/server.py (`POST /grouper/save`, around line 1495): after the existing `save_edits(edits, layout_path)` call, add `from src.settings import save_settings; save_settings({"layout_path": str(layout_path)})` so the layout path is persisted for generation
- [X] T017 [US1] Add "Generate" tab button to src/review/static/story-review.html: add `<button class="flyout-tab" data-tab="generate">Generate</button>` alongside the existing Details/Moments/Themes tab buttons; add `<div class="flyout-content" data-tab-content="generate" hidden></div>` in the flyout-body
- [X] T018 [US1] Implement `renderGenerateTab(song)` in src/review/static/story-review.js: (1) fetch `GET /generate/settings`; if `layout_configured == false`, render disabled state with message "No layout groups configured" and link to `/grouper`; (2) if `!song.analysis_exists`, render disabled state "Analysis required — run analysis first"; (3) otherwise render form with `<select id="gen-genre">` (options: any/pop/rock/classical), `<select id="gen-occasion">` (options: general/christmas/halloween), `<select id="gen-transition">` (options: subtle/none/dramatic); a "Generate Sequence" button; and a status area `<div id="gen-status"></div>`
- [X] T019 [US1] Implement the generate-and-poll flow in src/review/static/story-review.js: on "Generate Sequence" button click: (1) disable button, show spinner in `#gen-status`; (2) `POST /generate/<song.source_hash>` with `{genre, occasion, transition_mode}` from selects; (3) on 409 response show "Set up layout groups first" with grouper link; (4) on 202, store `job_id`, start `setInterval` polling `GET /generate/<hash>/status?job_id=<id>` every 2000ms; (5) on `status == "complete"` clear interval, trigger download via `window.location = "/generate/<hash>/download/<job_id>"`, re-enable button, update status text; (6) on `status == "failed"` clear interval, show `error` message from response, re-enable button
- [X] T020 [US1] Add the "generate" case to `renderActiveTab()` in src/review/static/story-review.js: `case "generate": renderGenerateTab(currentSong); break;` — wire it so the tab is rendered when the song changes or the tab is switched

**Checkpoint**: With a configured layout, a user can open the song detail panel → Generate tab → click Generate → see spinner → receive .xsq download.

---

## Phase 4: User Story 2 — Configure Generation Options (Priority: P2)

**Goal**: Genre select is pre-populated from song metadata (ID3 or hierarchy). Changing options and regenerating produces a sequence reflecting those choices.

**Independent Test**: Open a song with known genre metadata. The genre select shows the detected genre pre-selected. Change occasion to "christmas" and generate — sequence produces without error.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before T023**

- [X] T021 [P] [US2] Write unit tests for genre pre-population logic in tests/unit/test_generate_routes.py: test that `POST /generate/<hash>` passes `genre="rock"` to `GenerationConfig` when client sends `genre="rock"`; test that `genre="any"` is accepted and passed through; test that an invalid `occasion` value returns 400 with a clear error message

### Implementation for User Story 2

- [X] T022 [US2] Add input validation to `POST /generate/<source_hash>` in src/review/generate_routes.py: validate `genre` is one of `["any", "pop", "rock", "classical"]`; validate `occasion` is one of `["general", "christmas", "halloween"]`; validate `transition_mode` is one of `["none", "subtle", "dramatic"]`; return 400 with `{"error": "Invalid <field>: <value>"}` for any invalid value
- [X] T023 [US2] Pre-populate the genre select in `renderGenerateTab()` in src/review/static/story-review.js: use `song.genre` from the library entry (already present in the API response) to pre-select the matching `<option>` in `#gen-genre`; if `song.genre` doesn't match a known value (or is null), default to `"any"`

**Checkpoint**: Form controls are pre-populated from song data. Genre/occasion selection is validated server-side.

---

## Phase 5: User Story 3 — View and Re-download Past Generations (Priority: P3)

**Goal**: After generating, the detail panel shows prior generation results with timestamps and re-download links. These remain available for the server session.

**Independent Test**: Generate a sequence, navigate away (switch to another song), return to the same song's detail panel, and see the prior generation listed with a working re-download link.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before T025**

- [X] T024 [P] [US3] Write unit tests for `GET /generate/<source_hash>/history` in tests/unit/test_generate_routes.py: test empty list when no jobs for hash; test only `complete` jobs are returned (failed/running excluded); test multiple jobs are sorted newest-first; test each job entry includes `job_id`, `genre`, `occasion`, `transition_mode`, `created_at`

### Implementation for User Story 3

- [X] T025 [US3] Implement `GET /generate/<source_hash>/history` in src/review/generate_routes.py: filter `_jobs` by `source_hash` and `status == "complete"`; sort by `created_at` descending; return `{"jobs": [...]}` with each job serialised as `{job_id, genre, occasion, transition_mode, created_at}`
- [X] T026 [US3] Add history section to `renderGenerateTab()` in src/review/static/story-review.js: after the form, fetch `GET /generate/<hash>/history`; if response has jobs, render a `<section class="gen-history">` with one row per job showing formatted timestamp (e.g. "Today 14:32"), genre/occasion labels, and a "Re-download" link pointing to `/generate/<hash>/download/<job_id>`; if no history, render nothing (no empty state clutter)

**Checkpoint**: Prior generations are listed and re-downloadable. History persists across tab switches within the same browser session.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Integration test, CSS polish, error case hardening

- [X] T027 [P] Write integration test for the happy path in tests/integration/test_generate_integration.py: using the mock_layout.xml fixture and a real (small) analyzed hierarchy fixture, call the Flask test client to `POST /generate/<hash>` → poll status → assert `status == "complete"` and output_path `.xsq` file exists on disk — mock `generate_sequence()` to return a temp file path to avoid full pipeline execution
- [X] T028 [P] Add CSS for the Generate tab in src/review/static/story-review.css: style the generation form (select alignment, button sizing), spinner animation, error/success state colors, and history rows — matching the existing flyout panel visual style
- [X] T029 Run full test suite (`pytest tests/ -v`) and fix any failures across all touched files
- [X] T030 Validate quickstart.md scenarios manually: (1) happy path download; (2) no-layout error message shows; (3) unanalyzed song shows disabled state; (4) history re-download works

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (fixture paths used in tests)
- **US1 (Phase 3)**: Depends on Phase 2 (`src/settings.py` must exist)
- **US2 (Phase 4)**: Depends on US1 completion (form must exist before pre-population)
- **US3 (Phase 5)**: Depends on US1 completion (generate endpoint must exist)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Foundational only — core generation and UI
- **User Story 2 (P2)**: DEPENDS on US1 — form fields must exist to pre-populate; can run in parallel with US3
- **User Story 3 (P3)**: DEPENDS on US1 — history endpoint depends on `_jobs` populated by US1 endpoint; can run in parallel with US2

### Within Each User Story

- Tests MUST be written and FAIL before implementation begins
- `generate_routes.py` backend tasks precede frontend tasks (T009-T016 before T017-T020)
- Core endpoint before download endpoint (T011 before T013)
- Blueprint registration (T015) before any frontend can call the endpoints
- Grouper save update (T016) can run in parallel with T017-T019

### Parallel Opportunities

- T001 and T002 (fixture files) can run in parallel
- T003 (settings tests) can run in parallel with T001/T002 after T004 is unblocked
- T005, T006, T007, T008 (all US1 tests) can run in parallel — different test classes
- T009-T014 (generate_routes.py functions) are sequential within the same file
- T015, T016 (server.py changes) can run in parallel with T017-T019 (HTML/JS changes)
- T021 (US2 tests) can run in parallel with T024 (US3 tests) after US1 complete
- T027, T028 (polish) can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# All US1 test tasks can run in parallel (same file, but independent test classes):
T005: Write GenerationJob + _sanitize_error tests in tests/unit/test_generate_routes.py
T006: Write POST /generate/<hash> tests in tests/unit/test_generate_routes.py
T007: Write GET /generate/<hash>/status tests in tests/unit/test_generate_routes.py
T008: Write GET /generate/<hash>/download/<job_id> tests in tests/unit/test_generate_routes.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (fixtures)
2. Complete Phase 2: Foundational (settings.py)
3. Complete Phase 3: US1 (generate endpoint + UI tab + poll + download)
4. **STOP and VALIDATE**: Open the library, click a song, Generate tab shows, click Generate, .xsq downloads
5. US1 is independently valuable — no terminal required for generation

### Incremental Delivery

1. Phase 1 + 2 → Fixtures + settings module ready
2. US1 → Full generate-and-download flow → **MVP: core value delivered**
3. US2 → Form pre-populated from metadata → Better UX
4. US3 → History and re-download → Repeat-use convenience
5. Polish → Tests green, CSS polished

### Parallel Team Strategy

After US1 complete:
- Developer A: US2 (backend validation + JS pre-population)
- Developer B: US3 (history endpoint + JS history rendering)
- Both merge independently, then Polish phase

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at each checkpoint to validate story independently
- The library API already returns `genre` and `analysis_exists` per song — no extra metadata endpoint needed
- `generate_sequence()` caches hierarchy by MD5 — re-runs for a known song are fast (cache hit)
- Use daemon threads for background generation so server shutdown doesn't hang
