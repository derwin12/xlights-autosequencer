# Implementation Plan: Song Library Sequence Generation

**Branch**: `034-library-sequence-gen` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/034-library-sequence-gen/spec.md`

## Summary

Add a web front-end to the existing sequence generation pipeline so users can generate `.xsq` files directly from the song library detail panel, without using the CLI. Layout groups are configured once per installation via the grouper; the generate feature reads them automatically. Generation runs in a background thread with polling-based progress feedback.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend)
**Primary Dependencies**: Flask 3+ (web server), existing `src/generator/plan.py` + `src/generator/xsq_writer.py`, `src/library.py` — no new dependencies
**Storage**: `~/.xlight/settings.json` (layout path), in-memory `_jobs` dict (generation state), `tempfile.mkdtemp()` (generated `.xsq` files)
**Testing**: pytest (backend unit + integration), manual browser test
**Target Platform**: Local Flask server (same as existing review UI)
**Project Type**: Web service (adding routes to existing Flask app)
**Performance Goals**: Generation completes within 60 seconds for a 3-minute song (SC-002)
**Constraints**: Must not require new pip packages; fully offline operation
**Scale/Scope**: Single-user local server; in-memory session state is acceptable

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | ✅ Pass | Generation calls `generate_sequence()` which uses existing audio analysis; audio is the source of truth |
| II. xLights Compatibility | ✅ Pass | `write_xsq()` already produces valid xLights `.xsq` output; no change to the writer |
| III. Modular Pipeline | ✅ Pass | New Flask blueprint in `generate_routes.py` is isolated; no changes to generator pipeline stages |
| IV. Test-First Development | ✅ Pass | Test tasks precede implementation tasks in tasks.md |
| V. Simplicity First | ✅ Pass | Polling instead of SSE; no new dependencies; reuses `generate_sequence()` unchanged |

**Complexity Tracking**: No violations. Simpler alternatives selected throughout (polling > SSE, temp files > permanent archive, settings.json > complex discovery).

## Project Structure

### Documentation (this feature)

```text
specs/034-library-sequence-gen/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── generate_api.md  # Generation endpoint contracts
│   └── settings_api.md  # Settings/grouper save change
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code

```text
src/review/
├── generate_routes.py         # NEW: Flask blueprint for generation endpoints
├── server.py                  # MODIFIED: register generate blueprint, add settings.json write in grouper save
└── static/
    ├── story-review.html      # MODIFIED: add "Generate" tab button + content container
    └── story-review.js        # MODIFIED: add renderGenerateTab(), poll logic, download trigger

src/
└── settings.py                # NEW: read/write ~/.xlight/settings.json

tests/
├── unit/
│   └── test_generate_routes.py    # NEW: unit tests for generate blueprint
└── integration/
    └── test_generate_integration.py  # NEW: end-to-end generate → download test

tests/fixtures/generate/
├── mock_layout.xml            # NEW: minimal xLights layout fixture
└── mock_settings.json         # NEW: settings fixture pointing to mock_layout
```

## Implementation Notes

### settings.py

Thin module for `~/.xlight/settings.json`:

```python
def load_settings() -> dict:
    """Read ~/.xlight/settings.json; return {} if missing."""

def save_settings(updates: dict) -> None:
    """Merge updates into ~/.xlight/settings.json, creating if needed."""

def get_layout_path() -> Path | None:
    """Return Path from settings layout_path, or None if not set."""
```

### generate_routes.py Blueprint

Flask blueprint at `/generate` prefix:

```python
generate_bp = Blueprint("generate", __name__)

# In-memory job store (server lifetime)
_jobs: dict[str, GenerationJob] = {}
_temp_dir: Path = Path(tempfile.mkdtemp(prefix="xlight_gen_"))

@generate_bp.route("/<source_hash>", methods=["POST"])
def start_generation(source_hash): ...

@generate_bp.route("/<source_hash>/status", methods=["GET"])
def job_status(source_hash): ...

@generate_bp.route("/<source_hash>/download/<job_id>", methods=["GET"])
def download_sequence(source_hash, job_id): ...

@generate_bp.route("/<source_hash>/history", methods=["GET"])
def generation_history(source_hash): ...

@generate_bp.route("/settings", methods=["GET"])
def generation_settings(): ...
```

### Background Thread Pattern

```python
def _run_generation(job: GenerationJob, config: GenerationConfig) -> None:
    try:
        job.status = "running"
        output_path = generate_sequence(config)
        job.output_path = output_path
        job.status = "complete"
    except Exception as e:
        job.error_message = _sanitize_error(e)
        job.status = "failed"

# Start in POST handler:
t = threading.Thread(target=_run_generation, args=(job, config), daemon=True)
t.start()
```

`_sanitize_error(e)` maps known exception types to user-readable messages; falls back to a generic message without exposing the traceback.

### Frontend (story-review.js)

New `renderGenerateTab(song)` function:

1. Fetch `GET /generate/settings` — if `layout_configured == false`, show "Set up groups in the grouper" message with link.
2. If song has no analysis (`song.has_analysis == false`), show disabled state with explanation.
3. Otherwise render the generation form: genre `<select>`, occasion `<select>`, transition `<select>` — pre-populated from `song.genre`.
4. On "Generate" click: `POST /generate/<source_hash>`, store `job_id`, disable button, show spinner.
5. Poll `GET /generate/<source_hash>/status?job_id=<id>` every 2 seconds.
6. On `status == "complete"`: trigger download via `window.location = /generate/<hash>/download/<job_id>`, re-enable button, refresh history.
7. On `status == "failed"`: show error message from `error` field.

### server.py Changes

1. Register blueprint: `app.register_blueprint(generate_bp, url_prefix="/generate")`
2. In the grouper save handler (`POST /grouper/save`), after saving edits, call `save_settings({"layout_path": str(layout_path)})`.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `generate_sequence()` is slow (>60s) | Hierarchy is cached by MD5; typical re-run is fast. If slow, the polling UI still works — user just waits. |
| Thread leak if server restarts mid-generation | Daemon threads die with the process; no cleanup needed. |
| Temp dir fills up over long session | Generation files are small (<10MB each); acceptable. Could add LRU eviction in a future pass. |
| `layout_path` in settings.json becomes stale | Generate endpoint validates path exists; returns 409 with "reconfigure" message if missing. |
| Multiple concurrent generations for same song | Each job gets a unique job_id; `_jobs` dict supports multiple entries per source_hash. |
