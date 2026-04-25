# UI Flow Regression Tests

Browser-driven acceptance tests for the review UI. Opt-in via `pytest -m ui`
or through the acceptance gate (`xlight-evaluate gate`).

## First-time setup

```bash
# 1. Install the UI test extras
pip install -e ".[ui-tests]"

# 2. Install the Chromium browser
playwright install chromium

# 3. Build the frontend bundle that Flask serves
cd src/review/frontend
npm ci
npm run build
cd -

# 4. Download the CC0 corpus (used by the flow tests for a real upload)
python -m tests.validation.download_fixtures
```

## Running

```bash
# All UI flows, verbose
pytest -m ui -v

# A single flow
pytest tests/ui/flows/test_upload_flow.py -v

# Through the acceptance gate (includes analyzer + generator)
xlight-evaluate gate
```

UI tests are excluded from a bare `pytest` invocation
(see `pyproject.toml` → `addopts`) so developers without Playwright installed
don't hit import errors on unrelated work.

## Flow coverage

| File | Markers | What it verifies |
|---|---|---|
| `test_upload_flow.py` | `ui` | Drag-drop / file-pick upload → `POST /api/v1/import` succeeds → analyze screen renders |
| `test_analyze_flow.py` | `ui` | Analysis screen renders and survives without crash; metadata banner stays visible |
| `test_view_flow.py` | `ui` | Library ↔ analyze round-trip keeps song rows and state coherent |
| `test_export_flow.py` | `ui` | Export screen renders one of its known states (form or guard) |
| `test_content_flow.py` | `ui`, `content` | Uploads → triggers real analyzer → asserts UI-displayed section count / title / duration match `tests/fixtures/cc0_music/manifest.json` values within tolerance |
| `test_multi_song_flow.py` | `ui` | Seeds two fixtures via API → navigates via Chrome "Library" tab between distinct song-row contexts → verifies library state survives round-trips |
| `test_metadata_edit_flow.py` | `ui` | Uploads → edits `metadata-artist` on banner → Tab to trigger save → awaits PATCH response → asserts `metadata-saved` indicator + persistence via `/api/v1/library` |
| `test_folder_filter_flow.py` | `ui` | (a) Folder-toggle-unfiled click hides/reveals song row; (b) filter pills (All/Imported/Analyzed) update `data-active` on click |

All flows are marked `@pytest.mark.slow` and use `@pytest.mark.flaky(reruns=2)`
for 3-strike flake tolerance per the spec.

### Smoke flows vs the content flow

The first four are **smoke tests** — they verify the UI doesn't crash and the
expected elements render. They do NOT run the real analyzer pipeline, so they're
fast (~4s each) but only catch "broken screen" regressions.

`test_content_flow.py` is the **content-validation flow** — it uploads a fixture,
waits for the real analyzer to complete, and asserts the displayed data matches
the manifest. This is the only flow that catches regressions in how backend
analyzer output plumbs through to UI rendering.

### Content flow capability requirement

The content flow requires section-detecting algorithms (`madmom` or `vamp`).
Without either installed — most commonly because the `.venv-vamp` sidecar
environment doesn't exist — the test **skips cleanly** rather than producing a
false regression report.

If you see `SKIPPED` for `test_content_flow_analyzer_populates_ui` with the
message "Section detection requires madmom or vamp...", you have two options:

- **Intended path — use the devcontainer.** The repo ships a `.devcontainer/`
  setup that installs `.venv-vamp` correctly. Inside it, the content flow runs
  for real against the full algorithm stack.
- **Host-local fix — rebuild `.venv-vamp`.** Create a fresh Python 3.11 venv
  (madmom requires ≤ 3.11 and numpy<2) and install the optional deps:
  ```bash
  rm -rf .venv-vamp
  /opt/homebrew/bin/python3.11 -m venv .venv-vamp
  .venv-vamp/bin/pip install -e ".[madmom,vamp]"
  # Plus the Vamp plugin .dylib files in ~/Library/Audio/Plug-Ins/Vamp/
  # (see repo root CLAUDE.md for the list)
  ```

CI is expected to run the content flow — the gate's capability check makes the
skip cheap for developers who haven't set up the sidecar venv yet, without
silently hiding regressions on CI where the stack IS installed.

### Gate mode → flow selection

The acceptance gate (`xlight-evaluate gate`) selects flows by marker:

| Gate invocation | pytest selector | Flows run |
|---|---|---|
| `xlight-evaluate gate --quick` | `-m "ui and content"` | Content flow only (~1 min) |
| `xlight-evaluate gate` | `-m ui` | All five flows (~3 min) |
| `xlight-evaluate gate --skip-ui` | _(UI suite skipped)_ | None |

## Server setup

`conftest.py` starts a single Flask server (via `create_app(testing=True)`)
on a dynamic port for the whole session. The server serves both the API
routes and the built frontend from `src/review/frontend/dist/`. No separate
Vite dev server is started.

If `src/review/frontend/dist/index.html` is missing, all UI tests skip with
a clear reason. Same for a missing CC0 corpus.

## Selectors

Tests use `data-testid` attributes already present in the React components
(`library-screen`, `analyze-screen`, `metadata-banner`, `file-input`,
`library-empty-drop`, `song-row-<id>`, `export-form`, etc.). These are
behavior-oriented, so UI refactors that don't change user-facing structure
won't break the tests.

## Debugging flakes

Playwright ships with a trace viewer:

```bash
# Run with trace capture on failure
pytest -m ui --tracing=retain-on-failure

# Open a captured trace
playwright show-trace test-results/<test>/trace.zip
```

The trace shows every action, network call, and DOM snapshot — usually
enough to pinpoint the flake source (timing, missing element, network lag).

## Retries

Per the spec, UI tests retry up to 3 times total (1 initial + 2 retries
via `@pytest.mark.flaky(reruns=2)`). A test is considered passing if any
attempt succeeds. Analyzer and generator suites do NOT retry — failures
there are tolerance bugs, not flakes.
