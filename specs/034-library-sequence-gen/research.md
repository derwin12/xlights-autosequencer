# Research: Song Library Sequence Generation

**Feature**: 034-library-sequence-gen
**Date**: 2026-04-09

---

## R1: Existing Generation Pipeline

**Decision**: Reuse `generate_sequence(config: GenerationConfig)` from `src/generator/plan.py` unchanged.

**Findings**:
- `generate_sequence()` is the single top-level entry point (line 256). It orchestrates: run/cache hierarchy analysis → parse layout → generate groups → load libraries → `build_plan()` → `write_xsq()` → return `Path` to `.xsq`.
- `GenerationConfig` (`src/generator/models.py:117`) requires `audio_path: Path` and `layout_path: Path`. Optional: `genre`, `occasion`, `transition_mode`, `output_dir`.
- `write_xsq()` (`src/generator/xsq_writer.py:209`) writes the `.xsq` XML to `output_path` and returns `None`.

**Rationale**: No pipeline changes needed — this feature is purely a web front-end.

**Alternatives considered**: Calling `build_plan()` + `write_xsq()` directly to avoid the hierarchy re-run overhead. Rejected: `generate_sequence()` already caches hierarchy results via MD5-keyed JSON files adjacent to the MP3, so re-running is fast (cache hit). Maintaining the same call path avoids duplication.

---

## R2: Layout Path — How to Get It in the Web Context

**Decision**: Persist the "active layout path" in `~/.xlight/settings.json` when the user saves their grouper configuration. The generate endpoint reads this setting.

**Findings**:
- `GenerationConfig` requires `layout_path: Path` — the path to the xLights `xlights_rgbeffects.xml` file.
- The grouper in `server.py` uses `layout_path` as a query parameter passed per-request. There is no globally persisted "current layout path" in the codebase today.
- Grouper edits are stored as `<md5>_grouping_edits.json` adjacent to the layout file. The layout path itself is stored inside the edits file (`edits.layout_path`).
- The grouper "Export Groups" endpoint already saves an export file. We will also update the grouper "Save" endpoint to write the layout path to `~/.xlight/settings.json`.

**Rationale**: A single settings file for the installation-wide active layout path is the minimal, correct approach. It matches the spec's assumption that layout groups are "one-time per installation" — the user picks a layout file once via the grouper, and all subsequent generations use it automatically.

**Alternatives considered**:
- Scanning for the most-recently modified `*_grouping_edits.json` across all drives. Rejected: fragile, order-dependent, depends on filesystem modification time.
- Requiring the user to pass the layout path on each generation request. Rejected: contradicts the spec's one-time setup requirement.
- Using the in-memory `_grouper_edits` dict. Rejected: server restarts lose state; only works if grouper was used in the same session.

---

## R3: Long-Running Operation Pattern (SSE vs. polling)

**Decision**: Use a background thread with polling via `GET /generate/<source_hash>/status` (JSON), not SSE.

**Findings**:
- The existing SSE pattern in `server.py` (`_progress_generator`, `AnalysisJob`) is complex and tightly coupled to the analysis workflow. It uses a module-level `_current_job` singleton, which limits concurrent use.
- Generation for a typical 3-minute song completes in 5-30 seconds (mostly in the cached hierarchy path). Real-time streaming is not critical.
- A simple polling endpoint (`/generate/<source_hash>/status` returning `{status, progress_pct, error}`) is sufficient and much simpler to implement correctly.
- The frontend polls every 2 seconds until `status == "complete"` or `"failed"`.

**Rationale**: Polling is simpler than SSE for this use case. SSE connections have reconnect/timeout complexity; polling is robust and stateless. The spec only requires "a progress indicator" — not real-time streaming.

**Alternatives considered**: SSE mirroring the analysis pattern. Rejected: over-engineered for a 5-30 second operation; the singleton `_current_job` pattern would conflict with concurrent library use.

---

## R4: In-Session Storage for Generated Files

**Decision**: Store generated `.xsq` files in a `tempfile.mkdtemp()` directory that persists for the server process lifetime. Track them in a module-level dict keyed by `(source_hash, job_id)`.

**Findings**:
- The spec requires re-download within the same server session (SC-005, FR-009). No permanent archive needed.
- Flask's `send_file()` can serve any path the server process can read.
- `generate_sequence()` writes the `.xsq` to a configurable `output_dir`. We point it to the temp directory.
- The `GenerationJob` data class holds: `job_id`, `source_hash`, `status`, `output_path`, `error_message`, `options`, `created_at`.

**Rationale**: Temp directory approach is simple, OS-managed, and avoids polluting the user's music library folder with generated files during preview/iteration.

**Alternatives considered**: Writing `.xsq` next to the MP3 file. Rejected: clutters the user's music library; might conflict with file names from CLI-generated sequences.

---

## R5: Song Metadata — How to Pre-Populate Form Fields

**Decision**: Load the song's `_hierarchy.json` (or `_story.json`) to extract `genre` and `title`/`artist` for pre-populating the generation form.

**Findings**:
- `LibraryEntry` (in `src/library.py`) stores `analysis_path` pointing to the hierarchy JSON, plus `title`, `artist`.
- The hierarchy JSON (`HierarchyResult`) contains `song_profile` which has `genre` and `tempo_bpm`.
- `GenerationConfig.genre` defaults to `"pop"` and `GenerationConfig.occasion` defaults to `"general"`.
- The song story JSON (if it exists alongside the hierarchy) also has `song.genre`.

**Rationale**: Pre-populate `genre` from `hierarchy.song_profile.genre` if available. Show it as the default in the UI so users can override if needed.

---

## R6: Where to Add the "Generate" UI

**Decision**: Add a new "Generate" tab to the existing flyout panel in `story-review.html` / `story-review.js`.

**Findings**:
- The flyout in `story-review.html` currently has 3 tabs: Details, Moments, Themes (lines 44-73 of the HTML).
- Each tab has a `<div class="flyout-content" data-tab-content="...">` container populated by a JS render function.
- Adding a new tab requires: (1) one HTML `<button class="flyout-tab">`, (2) one empty content div, (3) one render function in the JS, (4) one case in `renderActiveTab()`.
- The "Generate" tab is song-level (not section-level), so it renders based on the selected song in the library, not the current section.

**Rationale**: A dedicated tab keeps the generation UI separate from the metadata/moments/themes tabs, matching the spec's "Generate Sequence section" language.

---

## R7: Generation Routes Blueprint

**Decision**: Create `src/review/generate_routes.py` as a new Flask blueprint registered at `/generate` prefix.

**Findings**:
- Existing pattern: `story_routes.py` and `variant_routes.py` are registered as blueprints in `server.py`.
- The generate blueprint needs: `POST /generate/<source_hash>`, `GET /generate/<source_hash>/status`, `GET /generate/<source_hash>/download/<job_id>`.
- History (P3) is served by `GET /generate/<source_hash>/history`.
- The blueprint receives the SCAN_DIR and settings path via Flask `app.config`.

**Rationale**: Follows the established blueprint pattern; keeps generation logic isolated from the main server.
