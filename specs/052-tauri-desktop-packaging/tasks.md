---

description: "Task list for Tauri desktop packaging (macOS v1)"
---

> **HISTORICAL — macOS scope dropped 2026-07-24.** This spec targeted macOS-only packaging and is kept for historical reference only (research/decisions may still be useful). The project is now Windows-only; see [`packaging/README.md`](../../packaging/README.md) for the current, actively-maintained build handbook.

# Tasks: Tauri Desktop Packaging (macOS v1)

**Input**: Design documents from `/specs/052-tauri-desktop-packaging/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — required by Constitution Principle IV (Test-First Development).

**Organization**: Tasks are grouped by user story. Each story is independently implementable and testable. MVP = US1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Per [plan.md](plan.md), Option 2 (web application) extended with a new `packaging/` root:

- Existing backend code: `src/` (mostly unchanged)
- Existing frontend: `src/review/frontend/`
- New packaging code (Python side): `src/packaging/`
- New Tauri shell + build tooling: `packaging/` (sibling to `src/`)
- Tests: `tests/packaging/` and `tests/integration/`

---

## Implementation progress (2026-04-22)

**Author-only pass from the Linux devcontainer is complete.** Every task
whose deliverable is source code is done. Tasks that literally require a
Mac (actual build, sign, notarize, smoke-test, benchmark) are marked
⛔ MAC — run `./packaging/scripts/release.sh <arch>` from the Mac host
against this worktree to execute them. A handful of 051-dependent wiring
tasks are marked ⏸️ DEFERRED pending the final 051 merge.

Python tests passing in this environment: **23 passed, 1 skipped** (smoke).

```
- [x]         …completed in this pass
- [ ] ⛔ MAC  …needs macOS host (build, sign, notarize, spctl)
- [ ] ⏸️ DEFERRED …small wiring tied to 051 UX or post-ship polish
```

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the new directories and install build-time tooling. No behavior yet.

- [x] T001 Create directory skeletons: `packaging/tauri/src-tauri/`, `packaging/tauri/icons/`, `packaging/pyinstaller/hooks/`, `packaging/pyinstaller/plugins/vamp/`, `packaging/scripts/`, `src/packaging/`, `tests/packaging/smoke/` (no content yet)
- [x] T002 [P] Add `pyinstaller>=6,<7` and `pytest-timeout` to `pyproject.toml` [dev] extras (dev-only — production wheels remain unchanged)
- [x] T003 [P] Initialize Tauri 2 project in `packaging/tauri/` via `pnpm create tauri-app` (accept defaults, name "XLight", identifier "com.xlight.autosequencer"); commit only the `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, `src-tauri/src/main.rs`, `package.json`, `pnpm-lock.yaml`
- [x] T004 [P] Add `@tauri-apps/plugin-shell`, `@tauri-apps/plugin-dialog`, `@tauri-apps/api` to `packaging/tauri/package.json`
- [x] T005 [P] Create `packaging/README.md` stub pointing at [quickstart.md](quickstart.md) for the release-engineer handbook

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Two-way infrastructure: backend helpers that both US1 (launch) and US2 (workflow) depend on, and their tests. No user story can proceed until this phase is complete.

**⚠️ CRITICAL**: All of Phase 2 must pass before any US1/US2/US3/US4 task begins.

### Tests (write first, confirm failing)

- [x] T006 [P] Write failing test `tests/packaging/test_stems_paths.py`: `resolve_stem_dir(source_path, hash)` returns source-adjacent path when writable, falls back to `~/Library/Application Support/XLight/stems/<hash>/` when `os.access(parent, os.W_OK)` is false
- [x] T007 [P] Write failing test `tests/packaging/test_port_discovery.py`: launches `python -m src.review.bundled_entrypoint` as subprocess with `XLIGHT_PACKAGED=1`, captures stdout, asserts a single line matching `^XLIGHT_BACKEND_PORT=(\d+)$` appears before the Flask server accepts connections
- [x] T008 [P] Write failing test `tests/packaging/test_models_paths.py`: `get_torch_home()` returns `~/Library/Application Support/XLight/models/torch-hub/` and creates the directory if missing
- [x] T009 [P] Write test `tests/packaging/test_vamp_path_env.py`: confirms existing `src/analyzer/capabilities.py:97` honors `VAMP_PATH`; fixture creates a temp dir with a fake `.dylib`, sets `VAMP_PATH`, asserts the path appears first in the search order (no code change — this pins existing behavior)

### Implementation

- [x] T010 [P] Create `src/packaging/__init__.py` (empty module marker)
- [x] T011 [P] Create `src/packaging/stems_paths.py` implementing `resolve_stem_dir(source_path: Path, audio_hash: str) -> Path` with writable-probe + fallback, making T006 pass
- [x] T012 [P] Create `src/packaging/models_paths.py` implementing `get_torch_home() -> Path` and `get_model_cache_root() -> Path`, making T008 pass
- [x] T013 [P] Create `src/packaging/bundled_mode.py` exposing `is_bundled() -> bool` (returns `os.environ.get("XLIGHT_PACKAGED") == "1"`) and `get_manifest() -> dict | None` (reads `Contents/Resources/packaging-manifest.json` via `sys._MEIPASS` when bundled, else returns None)
- [x] T014 Modify `src/analyzer/stems.py:38-62` to call `src.packaging.stems_paths.resolve_stem_dir` for path resolution when `bundled_mode.is_bundled()` is True; preserve exact current behavior otherwise
- [x] T015 Create `src/review/bundled_entrypoint.py` — new `main()` that (1) binds a probe socket on `127.0.0.1:0` to pick a free port, (2) closes the probe socket, (3) prints `XLIGHT_BACKEND_PORT=<port>\n` to stdout and flushes, (4) calls `create_app()` from `src.review.server`, (5) runs `app.run(host="127.0.0.1", port=<port>, debug=False, use_reloader=False)`; makes T007 pass
- [x] T016 Update `packaging/pyinstaller/backend.spec` (initial skeleton) to use `src.review.bundled_entrypoint` as the PyInstaller entry point (not the existing `src.review.cli`)

**Checkpoint**: Backend now has all the seams US1+US2 need. Existing dev-mode behavior (via `python -m src.review.cli`) is unchanged.

---

## Phase 3: User Story 1 — Install and launch without a terminal (Priority: P1) 🎯 MVP

**Goal**: A non-technical user double-clicks a signed `.dmg`, drags `XLight.app` to Applications, launches it, and sees the upload screen inside a native macOS window — no terminal, no Python, no setup.

**Independent Test**: Build `.dmg`, hand to a fresh macOS machine with no Python/Node/Homebrew. Double-click, install, launch. Upload screen appears within 5s of cold start after first launch. Gatekeeper accepts without warnings.

### Tests for User Story 1 (write first, confirm failing)

- [x] T017 [P] [US1] Write test `packaging/tauri/src-tauri/src/handshake_tests.rs` (Rust unit test) — parser accepts `XLIGHT_BACKEND_PORT=54321` amid prior log lines, rejects malformed lines, returns port as u16
- [x] T018 [P] [US1] Write test `packaging/tauri/src-tauri/src/handshake_tests.rs` — mock sidecar that exits before printing port line triggers `backend-startup-failed` event within 30s timeout
- [ ] ⛔ MAC T019 [P] [US1] Write failing smoke test `tests/packaging/smoke/test_app_launch.py` using `tauri-driver` or `pytest-playwright`: launches built `.app`, waits for `backend-ready` event, issues HTTP GET to `/api/v1/library/songs` via the discovered port, asserts HTTP 200

### Implementation — Tauri Rust shell

- [x] T020 [US1] Write `packaging/tauri/src-tauri/tauri.conf.json` with: `productName: "XLight"`, `identifier: "com.xlight.autosequencer"`, `bundle.macOS.signingIdentity` (env-expanded), `bundle.externalBin: ["binaries/backend"]`, `bundle.resources: ["../pyinstaller/plugins/vamp/**", "packaging-manifest.json"]`, `bundle.macOS.entitlements: "./entitlements.plist"`, `bundle.targets: ["dmg"]`
- [x] T021 [US1] Write `packaging/tauri/src-tauri/entitlements.plist` with: `com.apple.security.cs.disable-library-validation=true`, `com.apple.security.cs.allow-unsigned-executable-memory=true`, `com.apple.security.cs.allow-jit=true`, `com.apple.security.files.user-selected.read-write=true`
- [x] T022 [US1] Write `packaging/tauri/src-tauri/capabilities/main.json` granting: `core:default`, `shell:allow-execute`, `dialog:allow-open`, `dialog:allow-save`, `event:default`, `fs:allow-read-file`, `fs:allow-exists` (no broad fs write, no arbitrary shell)
- [x] T023 [US1] Implement `packaging/tauri/src-tauri/src/main.rs`: on app setup, `Command::new_sidecar("backend")` with env (`VAMP_PATH`, `TORCH_HOME`, `XLIGHT_PACKAGED=1`, `PYTHONUNBUFFERED=1`), spawn, loop reading `CommandEvent::Stdout` lines, parse port via regex `^XLIGHT_BACKEND_PORT=(\d+)$`, on match cache the port in a `Mutex<Option<u16>>` app state and `app.emit("backend-ready", port)`. Make T017 pass.
- [x] T024 [US1] In `main.rs`: 30-second handshake timeout; on timeout or early `CommandEvent::Terminated` during `waiting_for_port`, emit `backend-startup-failed` with captured stdout+stderr. Make T018 pass.
- [x] T025 [US1] In `main.rs`: register `#[tauri::command] get_backend_port(state) -> Option<u16>` reading cached port state (serves late frontend listeners)
- [x] T026 [US1] In `main.rs`: `on_window_event` or `on_exit` handler sends SIGTERM to sidecar `CommandChild`, waits up to 5s, then SIGKILL
- [x] T027 [US1] Place initial placeholder icons in `packaging/tauri/icons/` (`icon.icns`, `32x32.png`, `128x128.png`, `128x128@2x.png`) — real icons can replace later

### Implementation — Frontend integration

- [x] T028 [P] [US1] Create `src/review/frontend/src/lib/backendPort.ts`: `resolveBackendBase()` returns `"/api"` in `import.meta.env.DEV`, otherwise listens for Tauri `backend-ready` event AND invokes `get_backend_port` command as a race fallback, resolves to `http://127.0.0.1:<port>`
- [x] T029 [US1] Create `src/review/frontend/src/lib/apiClient.ts`: `apiUrl(path)` helper that reads the resolved base from a module singleton initialized once at app startup
- [x] T030 [US1] Replace hardcoded `/api` references across the frontend with `apiUrl(...)` calls. Files to audit: `src/review/frontend/src/screens/Drop.tsx`, `Analyze.tsx`, `Library.tsx`, `Theme.tsx`, `Timeline.tsx`, `store/sections.ts`, and any `fetch(` call sites. Dev mode continues to hit the Vite proxy via the `/api` fallback.
- [x] T031 [P] [US1] Write `src/review/frontend/src/lib/backendPort.test.ts`: mock Tauri event API, verify resolution via event, verify fallback via `invoke("get_backend_port")` when listener attaches after event fires
- [x] T031a [US1] Add `tauri-plugin-single-instance` to `packaging/tauri/src-tauri/Cargo.toml` and register in `main.rs` setup; on second-launch, focus the existing window instead of starting a duplicate process. Covers spec Edge Case "Multiple instances" — prevents two sidecars competing over `~/.xlight/library.json`.
- [x] T031b [P] [US1] Create `src/review/frontend/src/components/Splash/Splash.tsx` and wire into `src/review/frontend/src/App.tsx`: render a simple "Starting up…" view with a spinner whenever the backend base URL is unresolved. Hide as soon as `backend-ready` fires and `apiBase` is set. Covers FR-009 and the "First-launch extraction time" edge case — no blank silent window during startup.

### Implementation — PyInstaller backend bundle

- [x] T032 [US1] Write `packaging/pyinstaller/backend.spec`: onedir, entry `src.review.bundled_entrypoint`, `datas` includes `src/effects/builtin_effects.json`, `src/themes/builtin_themes.json`, madmom data files; `hiddenimports` includes `madmom.ml.nn.layers`, `madmom.audio.comb_filters`, `librosa.util.exceptions`, `torch._C`
- [x] T033 [P] [US1] Write `packaging/pyinstaller/hooks/hook-madmom.py`: `from PyInstaller.utils.hooks import collect_all`; `datas, binaries, hiddenimports = collect_all("madmom")`
- [x] T034 [P] [US1] Write `packaging/pyinstaller/hooks/hook-torch.py`: collect torch with `collect_all("torch")`; exclude CUDA components (CPU-only build)
- [x] T035 [P] [US1] Write `packaging/pyinstaller/hooks/hook-librosa.py` and `hook-demucs.py` as needed after first build iteration
- [x] T036 [US1] Write `packaging/scripts/build-backend.sh`: accepts `$1` as arch (`aarch64` or `x86_64`), creates `.build-venv-$ARCH/`, pip-installs backend deps from `pyproject.toml`, runs `pyinstaller packaging/pyinstaller/backend.spec --distpath packaging/tauri/src-tauri/binaries/ --workpath .build-pyinstaller/$ARCH --clean --noconfirm`, renames output to `backend-$ARCH-apple-darwin`, exits non-zero on failure

### Implementation — Vamp plugin bundling

- [x] T037 [US1] Write `packaging/scripts/fetch-vamp-plugins.sh`: documents (and when possible, downloads) the five macOS Vamp plugin packs; copies `.dylib` files into `packaging/pyinstaller/plugins/vamp/$ARCH/`. Fetch is manual for packs without stable URLs — script prints clear instructions if a pack is missing and exits non-zero.
- [ ] ⛔ MAC T038 [US1] Commit Vamp plugin binaries under `packaging/pyinstaller/plugins/vamp/aarch64/` and `x86_64/` (binary files, one per plugin pack — QM, BeatRoot, pYIN, Chordino/NNLS, Silvet)
- [ ] ⛔ MAC T039 [US1] Verify Tauri `bundle.resources` entry (T020) copies these into `Contents/Resources/vamp/` in the built `.app`; adjust `tauri.conf.json` if needed
- [x] T040 [US1] Update T023 `main.rs` to set `VAMP_PATH` to the absolute path of the resources' `vamp/` directory (resolved via Tauri's `path.resource_dir()`)

### Implementation — Signing

- [x] T041 [US1] Write `packaging/scripts/sign-backend.sh`: accepts `$1` arch, walks `packaging/tauri/src-tauri/binaries/` onedir bottom-up, runs `codesign --force --options runtime --entitlements packaging/tauri/src-tauri/entitlements.plist --sign "$SIGNING_IDENTITY"` on every `.dylib`, `.so`, and the main executable. Exits non-zero if `codesign --verify --deep --strict --verbose=2 <onedir>` fails.
- [x] T042 [US1] Write `packaging/scripts/build-app.sh`: accepts `$1` arch, runs `cargo tauri build --target $ARCH-apple-darwin`; after build, runs `codesign --display --verbose=4 <built-app>` to confirm Tauri re-signed the outer `.app` with the same identity; runs `spctl -a -vvv -t execute <built-app>` and exits non-zero if not accepted

### Implementation — Notarization and release

- [x] T043 [US1] Write `packaging/scripts/notarize.sh`: locates the built `.dmg` for the arch, runs `xcrun notarytool submit <dmg> --keychain-profile XLIGHT_NOTARY --wait`, on success runs `xcrun stapler staple <dmg>`, on failure dumps `xcrun notarytool log <submission-id>` JSON and exits non-zero
- [x] T044 [US1] Write `packaging/scripts/release.sh`: orchestrates `build-backend.sh` → `sign-backend.sh` → `build-app.sh` → `notarize.sh`; accepts `$1` arch; fails fast on any step failure; prints final `.dmg` path on success
- [x] T045 [US1] Populate `packaging-manifest.json` generation inside `release.sh` with `app_version` (from `pyproject.toml`), `build_timestamp`, `target_arch`, `frontend_commit`, `backend_commit`, `bundled_vamp_plugins`

### Smoke test

- [ ] ⛔ MAC T046 [US1] Implement `tests/packaging/smoke/test_app_launch.py` (deferred from T019): install and launch the built `.app` via `tauri-driver` or Playwright driving the WebView; wait for `backend-ready`; issue HTTP GET to `http://127.0.0.1:<port>/api/v1/library/songs`; assert HTTP 200 within 15s of launch. Ship as opt-in (requires a built `.app` present; skip if `XLIGHT_SMOKE_APP_PATH` env var is not set).
- [x] T047 [US1] Update `packaging/README.md` with the per-release checklist pointing at `release.sh` usage

**Checkpoint**: Running `./packaging/scripts/release.sh aarch64` produces a signed, notarized `.dmg`. Installing it and launching the `.app` opens the React upload screen in a WKWebView window. Core HTTP round-trip works. Analysis pipeline may or may not work yet — that's Phase 4.

---

## Phase 4: User Story 2 — Analyze, review, and generate sequences offline (Priority: P1)

**Goal**: The full existing workflow (analyze → review sections → edit boundaries → generate `.xsq`) runs inside the installed app with no network (except optional lyric fetch and the one-time stem-weights download).

**Independent Test**: On a machine with network disabled, launch installed app, drop a 3-min MP3, verify analysis completes, timeline renders, section boundary edit persists, generated `.xsq` is byte-equivalent to dev-mode output on the same input. Stem separation on first click shows license+download prompt (network required for this step only).

### Tests for User Story 2 (write first)

- [ ] ⛔ MAC T048 [P] [US2] Write failing test `tests/packaging/test_bundle_imports.py`: runs `packaging/tauri/src-tauri/binaries/backend-$ARCH-apple-darwin --self-test` subprocess (new CLI flag on bundled entrypoint), which imports every pipeline module (librosa, madmom, vamp, demucs, torch, soundfile, resampy, numpy, src.analyzer, src.story, src.generator) and exits 0 if all succeed
- [x] T049 [P] [US2] Write failing test `tests/packaging/test_weights_downloader.py`: mocks `dl.fbaipublicfiles.com` with local HTTP server, verifies (a) full download+verify+place, (b) resume from partial with `Range:` header, (c) SHA256 mismatch triggers delete+re-download, (d) 3-retry exponential backoff on network errors
- [ ] ⛔ MAC T050 [P] [US2] Write failing test `tests/integration/test_bundled_offline_flow.py` (skipped unless `XLIGHT_BUNDLED_APP` env set): launches the bundled entrypoint directly, hits analyze → library → section-edit → export endpoints against a fixture MP3, verifies outputs match a golden analysis JSON

### Implementation — PyInstaller completeness

- [x] T051 [US2] Add `--self-test` flag to `src/review/bundled_entrypoint.py`: when present, imports every module listed in T048 and exits 0/1 without starting Flask. Makes T048 pass after build.
- [ ] ⛔ MAC T052 [US2] Iterate on `packaging/pyinstaller/backend.spec` until T048 passes: add hidden imports for any module that PyInstaller missed (common candidates: `librosa.util.exceptions`, `sklearn.utils._cython_blas`, `scipy.sparse.csgraph._validation`, `soundfile`, `demucs.pretrained`)
- [x] T053 [US2] Ensure `TORCH_HOME` env set by Tauri launcher (T023) points at `~/Library/Application Support/XLight/models/torch-hub/` so demucs caches weights in the canonical location

### Implementation — Weights download flow

- [x] T054 [P] [US2] Create `src/packaging/weights_downloader.py`: class `WeightsDownloader(model_name)` with methods `download_with_progress(callback)` streaming shard-by-shard via `requests` with `Range:` resume, per-shard SHA256 verify against `.download-state.json`, atomic rename into torch hub path. Makes T049 pass.
- [x] T055 [US2] Create `src/packaging/model_manifest.json` listing known `htdemucs_6s` shard URLs and SHA256 hashes (static manifest bundled in `.app`)
- [x] T056 [US2] Create new Flask blueprint `src/review/api/v1/models.py`: `POST /api/v1/models/download` returning an SSE stream per `contracts/weights-download.md`; `GET /api/v1/models/<name>/status` for presence check
- [x] T057 [US2] Register `models` blueprint in `src/review/server.py` `create_app()`
- [ ] ⏸️ DEFERRED T058 [US2] Modify `src/review/api/v1/analysis.py` separate-stems endpoint: before running demucs, check `torch_home / "checkpoints" / <shard-files>` exist; if not, return HTTP 409 with `needs_download` payload per contract
      *Deferred: existing analyze endpoint is inline (not a separate /separate-stems route in 051). Weights API is ready; wire when 051's analyze flow is stable.*
- [x] T059 [P] [US2] Frontend: create `src/review/frontend/src/components/WeightsDownload/WeightsDownload.tsx` — modal with license note, download button, SSE-driven progress bar, cancel button
- [x] T060 [P] [US2] Frontend: create `src/review/frontend/src/store/weightsDownload.ts` — Zustand slice tracking per-shard progress, overall progress, error state
- [ ] ⏸️ DEFERRED T061 [US2] Frontend: intercept 409 from separate-stems call in existing stem-separation caller, open WeightsDownload modal, on completion retry the original request
      *Deferred: same as T058 — 409 intercept needs the separate-stems endpoint.*

### Offline verification

- [ ] ⛔ MAC T062 [US2] Manual check (document in `packaging/README.md`): with `networksetup -setairportpower en0 off`, launch installed `.app`, drop a fixture MP3, run full analyze → review → edit → generate flow; confirm Genius lyric-fetch degrades with a clear error rather than hanging
- [ ] ⛔ MAC T063 [US2] Automate T050 if feasible (CI runner with network restrictions); otherwise document as manual step

**Checkpoint**: Full analyze → review → generate works inside installed `.app`. First stem-separation prompts for a ~170 MB download with visible progress, resumes after interruption, verifies SHA256. Offline operation for the non-stem pipeline is confirmed.

---

## Phase 5: User Story 3 — Access files and save outputs via native dialogs (Priority: P2)

**Goal**: Replace the browser `<input type="file">` and browser download behavior with native macOS Open/Save dialogs and drag-and-drop from Finder. No more "downloads go to ~/Downloads" surprises.

**Independent Test**: In the installed app, click Open → native macOS Open dialog appears → pick an MP3 → analysis starts without a browser upload. Generate sequence → click Save → native macOS Save dialog appears → pick a folder → `.xsq` is written to that exact path. Drag an MP3 from Finder onto the app window → analysis starts.

### Tests for User Story 3 (write first)

- [x] T064 [P] [US3] Write failing test `src/review/frontend/src/lib/nativeDialog.test.ts`: in dev mode (`import.meta.env.DEV=true`), `nativeDialog.openAudio()` triggers a hidden `<input>` click; in production (Tauri mock), calls `tauri.dialog.open` with audio filter and returns the selected paths
- [x] T065 [P] [US3] Write failing test `tests/integration/test_import_by_path.py`: direct file path → `POST /api/v1/import/by-path` → analysis starts, library entry matches existing upload-based flow

### Implementation

- [x] T066 [US3] Create `src/review/frontend/src/lib/nativeDialog.ts`: exports `openAudio(opts)`, `saveSequence(opts)`, `relocateAudio(opts)`, `onDrop(callback)` with dev/prod branching per [contracts/file-dialog-ipc.md](contracts/file-dialog-ipc.md). Makes T064 pass.
- [x] T067 [P] [US3] Backend: new endpoint `POST /api/v1/import/by-path` in `src/review/api/v1/import_.py` accepting `{path: str}`, only available when `XLIGHT_PACKAGED=1`, invokes the same import pipeline as the existing multipart-upload endpoint but reads the file directly from disk. Makes T065 pass.
- [x] T068 [P] [US3] Backend: new endpoint `POST /api/v1/sequence/<song_id>/export-to-path` in `src/review/api/v1/analysis.py` (or a new `generation.py`) accepting `{path: str}`, writes the generated `.xsq` directly to that path; only available when `XLIGHT_PACKAGED=1`
- [x] T069 [US3] Frontend: replace `<input type="file">` usage in `src/review/frontend/src/screens/Drop.tsx` with `nativeDialog.openAudio` → posts to `/api/v1/import/by-path` in prod, falls back to multipart in dev
- [x] T070 [US3] Frontend: replace browser download of `.xsq` with `nativeDialog.saveSequence` followed by `POST /api/v1/sequence/<song_id>/export-to-path` in prod
- [x] T071 [US3] Wire Tauri `file-drop` event in `main.rs` → forward to webview as a custom event → `nativeDialog.onDrop` dispatcher passes paths to the Drop screen's import handler
- [ ] ⏸️ DEFERRED T072 [US3] Implement `nativeDialog.relocateAudio` and wire into the library UI: on "file not found" for an existing library entry, prompt user to locate the file; after relocation, re-verify MD5 matches stored `source_hash`, surface warning on mismatch
      *Deferred: relocate flow — 051 already has /api/v1/relocate; wire nativeDialog into that screen when 051 is fully merged and stable.*
- [x] T073 [P] [US3] Add `tauri-plugin-dialog` dependency to `packaging/tauri/src-tauri/Cargo.toml` and to frontend `package.json`; register in `main.rs` setup
- [x] T074 [US3] Confirm `tauri.conf.json` + `capabilities/main.json` grant exactly the dialog permissions needed (no broader fs access)

**Checkpoint**: Open/Save feel native. Finder drag-and-drop works. Dev-mode behavior unchanged. No broader fs permissions granted than needed.

---

## Phase 6: User Story 4 — Version label and update discovery (Priority: P3)

**Goal**: Users can see what version they have and find newer versions. Auto-update is explicitly deferred (per spec); v1 ships with a visible version label and a link to the download page.

**Independent Test**: Launch the installed app. Find the version label in the UI (e.g., About dialog or app footer). Click the "Check for updates" link → browser opens to the download page.

### Tests for User Story 4 (write first)

- [x] T075 [P] [US4] Write failing test `tests/packaging/test_manifest_endpoint.py`: `GET /api/v1/manifest` returns the contents of `packaging-manifest.json` when bundled, returns a dev-mode stub when not bundled

### Implementation

- [x] T076 [US4] Backend: new endpoint `GET /api/v1/manifest` in a new `src/review/api/v1/manifest.py` blueprint returning `src.packaging.bundled_mode.get_manifest()` or a dev stub `{app_version: "dev", target_arch: "<arch>", ...}`. Makes T075 pass.
- [x] T077 [P] [US4] Frontend: create `src/review/frontend/src/components/About/About.tsx` — dialog showing app version, target arch, build timestamp, link to download page, link to open-source credits (Vamp plugin licenses, demucs license, ffmpeg license)
- [x] T078 [P] [US4] Frontend: create `src/review/frontend/src/store/manifest.ts` — fetch `/api/v1/manifest` once on app start, expose via Zustand slice
- [x] T079 [US4] Frontend: add menu item or footer link in `src/review/frontend/src/components/Chrome/Chrome.tsx` that opens the About dialog
- [x] T080 [US4] Frontend: About dialog "Check for updates" button uses `@tauri-apps/plugin-shell` `open(download_url)` to launch the user's default browser

**Checkpoint**: Version transparency shipped. Update discovery is manual (browser-based). Auto-update remains a future feature.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] ⛔ MAC T081 [P] Verify SC-002 (<=15% slowdown vs dev): benchmark 3-minute fixture MP3 through analyze → generate in both modes; record results in `packaging/README.md`
- [ ] ⛔ MAC T082 [P] Verify SC-003 (byte-for-byte output equivalence): diff bundled-app `.xsq` against dev-mode `.xsq` for the same input; expect identical XML (modulo timestamps). Automate as `tests/packaging/test_output_parity.py`.
- [ ] ⛔ MAC T083 [P] Verify SC-004 (<5s cold launch after first): time launch → `backend-ready` across 5 runs on a baseline Mac
- [ ] ⛔ MAC T084 [P] Verify SC-005 (clean install succeeds): fresh macOS VM, install `.dmg`, launch, run canonical flow, uninstall — all without additional manual steps
- [ ] ⛔ MAC T085 [P] Verify SC-006 (data persists N→N+1): install v1, create library entries + custom themes + section edits, install v1.0.1 over the top (simulated by swapping `.app` in Applications), verify all data present
- [ ] ⛔ MAC T086 [P] Verify SC-007 (Gatekeeper acceptance): on a clean Mac, `spctl -a -vvv -t execute /Applications/XLight.app` must report "accepted"
- [ ] ⏸️ DEFERRED T087 [P] Populate `Contents/Resources/credits/` with GPL/LGPL source URLs for bundled Vamp plugins; link from About dialog
      *Deferred: credits page population (GPL source URLs) — deferred to first real release.*
- [ ] ⏸️ DEFERRED T088 [P] Update `docs/release.md` (or create it) with the per-release checklist cross-referencing [quickstart.md](quickstart.md)
      *Deferred: docs/release.md — quickstart.md already covers the walkthrough.*
- [ ] ⛔ MAC T089 Run the full [quickstart.md](quickstart.md) walkthrough end-to-end on both `aarch64` and `x86_64` and record any friction items as GitHub issues
- [ ] ⏸️ DEFERRED T090 Final: update `CLAUDE.md` Recent Changes section with a one-paragraph summary of what shipped
      *Deferred: CLAUDE.md Recent Changes — updated in the polish commit.*
- [ ] ⛔ MAC T091 Constitution §Development Workflow compliance: take a `.xsq` generated by the bundled app (not dev-mode) and manually import it into xLights; confirm it opens without errors and the timing tracks look identical to a dev-mode-generated sequence for the same input. Record pass/fail in `packaging/README.md`.
- [x] T092 Document FR-008 partial-write scope: in `packaging/README.md`, record that partial-write safety for `~/.xlight/library.json` and the analysis cache inherits existing dev-mode behavior and is not hardened by this feature. If a future incident shows corruption on forced shutdown, open a separate spec for atomic-write (write-to-temp + `os.replace`). This feature's FR-008 scope is limited to clean process shutdown (T026) — not transactional disk writes.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1. **BLOCKS all user stories.**
- **US1 (Phase 3)**: Depends on Phase 2. MVP.
- **US2 (Phase 4)**: Depends on Phase 2 (can technically start in parallel with US1, but the smoke test T046 needs US2 tasks T051–T053 to fully succeed, so practical ordering is US1 → US2).
- **US3 (Phase 5)**: Depends on Phase 2 and on US1 tasks T022 (capabilities config) + T023 (Tauri shell setup). Could otherwise be independent.
- **US4 (Phase 6)**: Depends on Phase 2 and on T045 (manifest generation). Otherwise independent of US1/US2/US3.
- **Polish (Phase 7)**: Depends on all shipping user stories being complete.

### Within Each User Story

- Tests written first, confirmed failing, then implementation.
- Models / pure helpers before services.
- Services / endpoints before frontend integration.
- Backend contract in place before frontend calls it.

### Parallel Opportunities

Within Phase 2: T006–T013 can run fully in parallel (different files, no ordering). T014–T016 depend on T011 and T015 respectively.

Within US1:
- T017, T018, T019 (tests) in parallel.
- T020, T021, T022 (config files) in parallel — different files.
- T023–T026 (main.rs work) sequential — same file.
- T028, T031 (frontend) in parallel with Rust work above.
- T032–T035 (PyInstaller spec and hooks) largely in parallel.
- T037–T038 (Vamp plugin fetch + commit) serialize per arch but two arches can run in parallel.
- T041–T042–T043–T044 (scripts) serialize because release.sh orchestrates them.

Within US2:
- T048, T049, T050 (tests) in parallel.
- T054, T059, T060 in parallel — different files.

Within US3:
- T064, T065 in parallel.
- T066, T067, T068 in parallel — different files, different layers.
- T069–T072 sequential within the frontend (may touch overlapping screens).

Within US4: T077, T078 in parallel.

Within Polish: T081–T088 all marked [P].

### Cross-story parallelism

Once Phase 2 is done, a team could run:
- Developer A: US1 (T017–T047)
- Developer B: US3 (T064–T074)
- Developer C: US4 (T075–T080)

US2 depends on US1 end-to-end (needs a working bundle), so typically follows US1.

---

## Parallel Example: Phase 2 Foundational

```bash
# Launch all foundational tests in parallel (T006–T009):
Task: "Write failing test tests/packaging/test_stems_paths.py for stems-path fallback logic"
Task: "Write failing test tests/packaging/test_port_discovery.py for bundled entrypoint port handshake"
Task: "Write failing test tests/packaging/test_models_paths.py for Application Support models dir"
Task: "Write test tests/packaging/test_vamp_path_env.py pinning existing VAMP_PATH behavior"

# Then launch all foundational implementation in parallel (T010–T013):
Task: "Create src/packaging/__init__.py"
Task: "Create src/packaging/stems_paths.py implementing resolve_stem_dir"
Task: "Create src/packaging/models_paths.py implementing get_torch_home, get_model_cache_root"
Task: "Create src/packaging/bundled_mode.py with is_bundled() and get_manifest()"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1: Setup (T001–T005)
2. Complete Phase 2: Foundational (T006–T016)
3. Complete Phase 3: US1 (T017–T047)
4. **Stop and validate**: install the `.dmg` on a fresh Mac. Verify the app launches, Gatekeeper is happy, upload screen appears. This is a demonstrable product — the app opens as a real macOS app.
5. Decide whether to continue to US2/US3/US4 or pause for user feedback.

### Incremental Delivery

1. Setup + Foundational → infrastructure ready
2. Add US1 → Validate on a real Mac → MVP shipped
3. Add US2 → Validate analyze/review/generate inside bundle → full-feature release candidate
4. Add US3 → Polish file interactions → v1.0 release
5. Add US4 → Visible version + update discovery → v1.0 final
6. Polish → perf, parity, data-migration verification → release

### Parallel Team Strategy

If more than one developer:
- Setup + Foundational together (sequential enough that parallelism doesn't help much).
- After Phase 2: one developer on US1 (the critical path), another on US3 (loosely coupled), a third on US4 and Polish prep.
- US2 starts once US1 produces a working `.app`.

---

## Notes

- [P] tasks = different files, no dependencies — safe to parallelize.
- [Story] label maps task to the spec user story for traceability.
- Constitution Principle IV (Test-First): every new non-trivial module has its failing test written first.
- The existing dev-mode workflow (`python -m src.review.cli` + `pnpm dev`) MUST continue to work at every checkpoint. Any foundational or US1 change that breaks dev mode is a regression.
- `~/.xlight/` is shared with the CLI — do not migrate it without a separate spec.
- Weights download is CC BY-NC 4.0: if the app's distribution becomes commercial, a separate Meta license is required. Surface license note in the UI (T059).
- Commit after each task or tight logical group. Use branch `052-tauri-desktop-packaging`.
- Branch hygiene: we are currently on `051-x-onset-frontend` with uncommitted work. **Before starting T001**, commit or stash 051 work and `git checkout 052-tauri-desktop-packaging`.
