> **HISTORICAL — macOS scope dropped 2026-07-24.** This spec targeted macOS-only packaging and is kept for historical reference only (research/decisions may still be useful). The project is now Windows-only; see [`packaging/README.md`](../../packaging/README.md) for the current, actively-maintained build handbook.

# Phase 0 Research: Tauri Desktop Packaging (macOS v1)

**Feature**: 052-tauri-desktop-packaging
**Date**: 2026-04-22

Each section records the decision, rationale, and alternatives considered — not tutorials.

---

## R1. Python bundling tool: PyInstaller 6.x (onedir)

**Decision**: PyInstaller 6.x in onedir mode, built as an executable targetable by Tauri's `externalBin` sidecar mechanism.

**Rationale**:
- Most mature option for bundling heavy scientific Python stacks (numpy, torch, librosa, madmom) on macOS.
- Onedir (not onefile) keeps the `.dylib` layout intact so every library can be signed individually — notarization requires each `.dylib` be signed, and onefile's runtime-unpacking defeats static signing.
- Ships well-known hooks for torch, numpy, librosa. Gaps (madmom Cython extensions, torchaudio) are handled with `--hidden-import` + `--collect-all` flags.

**Alternatives considered**:
- **py2app**: macOS-native and designed for `.app` bundles, but integrates poorly with Tauri's sidecar model (Tauri expects a plain executable, not a nested `.app` inside its own `.app`).
- **PyOxidizer**: elegantly embeds Python in a Rust binary, could even be embedded directly in the Tauri shell. Rejected for v1 as too novel — documentation is thinner, and the torch/madmom compatibility story is less proven than PyInstaller's.
- **briefcase (BeeWare)**: full app-packaging framework, but owns the UI layer. We already have a React UI; briefcase would fight Tauri.

**Sharp edges to budget for**:
- Torch: needs `--collect-all torch --copy-metadata torch`; `torch/lib/*.dylib` must each be signed individually (don't rely on `codesign --deep`).
- madmom: Cython C extensions require explicit `--hidden-import madmom.ml.nn.layers` and `--hidden-import madmom.audio.comb_filters`, plus `--collect-data madmom` for shipped model files. Build against the target Python version on the target architecture; pre-built madmom wheels have been spotty.
- Notarization rejections are usually either unsigned nested `.so`/`.dylib`s or `@rpath` references leaking outside the bundle — fix by signing every binary bottom-up.

---

## R2. Frontend shell: Tauri 2.x

**Decision**: Tauri 2.x (the current stable major) using the `tauri-plugin-shell` sidecar API.

**Rationale**:
- Native WKWebView on macOS — no Chromium to ship, small shell binary.
- Tauri 2's plugin architecture (shell, dialog, fs as separate plugins with explicit capabilities) maps well to our needs: we want shell (sidecar), dialog (native file pickers), and limited fs.
- Active development; Tauri 1 is in maintenance only.

**Sidecar wiring**:
- `externalBin` entry in `tauri.conf.json` points at the PyInstaller executable named per-target triple: `backend-aarch64-apple-darwin`, `backend-x86_64-apple-darwin`.
- At launch, Rust `main.rs` spawns the sidecar via `Command::sidecar("backend").spawn()`, reads `CommandEvent::Stdout` line-by-line, and extracts a port marker line emitted by Flask. Once the port is known, it is emitted to the webview via `app.emit("backend-ready", port)`.
- On app quit, Rust's shutdown handler sends SIGTERM to the sidecar `CommandChild`.

**Gotchas**:
- Tauri 1 → Tauri 2 migration moved `allowlist` to `capabilities` JSON files and moved shell/dialog to plugins. Any stale Tauri 1 snippet from tutorials will fail — lean on the official v2 migration guide (https://v2.tauri.app/start/migrate/from-tauri-1/).
- Tauri 2 resource layout: onedir Python lives under `Contents/Resources/_up_/` — confirm paths with a test build before wiring up the sign step.

---

## R3. Frontend ↔ Backend communication: preserve Flask HTTP on 127.0.0.1

**Decision**: Keep the existing Flask HTTP API. The sidecar binds to `127.0.0.1:0` (OS-chosen free port) and prints the port to stdout for the Tauri shell to capture.

**Rationale**:
- Zero backend rewrite. The entire existing HTTP surface (`/api/v1/*`, SSE streams, audio file serving) works unchanged.
- Fixed ports (e.g., `5000`, `5055`) collide with the user's own dev Flask, with other installed apps, and with a second instance of our app. OS-assigned free ports eliminate this.
- Handshake via stdout is stock — Tauri's shell plugin exposes the subprocess stdout as a stream; one line of text is the simplest contract.

**Alternatives considered**:
- **Full Tauri IPC replacing HTTP**: massive rewrite (every frontend fetch becomes an `invoke()`, every Flask route becomes a Rust command or a Python stdin/stdout RPC). Zero user-visible benefit.
- **Fixed port**: simpler handshake, but real-world collisions break the app for a user segment we can't predict.
- **Unix domain socket**: slightly lower latency, but the frontend runs inside WKWebView and cannot address a UDS — would still need an HTTP-over-UDS bridge.

**Protocol** (formalized in `contracts/sidecar-handshake.md`):
1. Flask `app.run(host="127.0.0.1", port=0)` — OS assigns port.
2. Before serving, print a single line: `XLIGHT_BACKEND_PORT=<port>\n` to stdout.
3. Rust reads lines until it matches that prefix, extracts port, emits `backend-ready` Tauri event with payload `{port}`.
4. Frontend `window.__TAURI__` listener on `backend-ready` sets `window.__XLIGHT_API_BASE = "http://127.0.0.1:<port>"`.
5. All frontend `fetch()` calls go through `apiUrl(path)` which returns `${window.__XLIGHT_API_BASE}${path}` in production and `"/api"+path` (Vite proxy) in dev.

---

## R4. Hardened runtime entitlements

**Decision**: Enable hardened runtime with the following entitlements:
- `com.apple.security.cs.disable-library-validation` — **required** for Vamp plugin `dlopen`
- `com.apple.security.cs.allow-unsigned-executable-memory` — required for torch / numba JIT code generation
- `com.apple.security.cs.allow-jit` — further allows JIT code if `allow-unsigned-executable-memory` is not sufficient
- `com.apple.security.files.user-selected.read-write` — for user-chosen audio files via native file picker
- `com.apple.security.files.downloads.read-write` — for the demucs weights cache path

**Rationale**:
- Hardened runtime's library validation requires loaded libraries to be signed by the same Team ID **and** either in the main bundle or system locations. Vamp plugins are in `Contents/Resources/vamp/`, not `Contents/MacOS/` or system dirs — validation rejects them even when we sign them with our own Developer ID. `disable-library-validation` unblocks this.
- Torch and numba allocate executable memory at runtime for JIT kernels. Without these entitlements, hardened runtime kills the process on first JIT.
- File access entitlements are needed for user-selected files (via native Open dialog) and for writing to the torch hub cache location.

**Alternatives considered**:
- **Sign Vamp plugins with our Team ID and skip `disable-library-validation`**: the plugins we bundle are third-party (QM, BeatRoot, pYIN, Chordino/NNLS, Silvet) and none of them ship with Developer ID signatures we can trust. Re-signing with our Team ID + same-Team library validation is theoretically possible but fragile — we'd have to guarantee every plugin is signed correctly before notarization, and any mis-signed plugin would cause silent load failure at runtime rather than a clear error. The entitlement is the cleaner path.

---

## R5. Vamp plugin bundling

**Decision**: Ship macOS-native `.dylib` builds of the five plugin packs we use, placed under `Contents/Resources/vamp/`. Sidecar launcher sets `VAMP_PATH` env var to the absolute path of that directory before invoking Flask.

**Plugin packs to bundle**:
- QM Vamp Plugins (qm-tempotracker, qm-barbeattracker, qm-onsetdetector, qm-segmenter, qm-keydetector)
- BeatRoot (beatroot)
- pYIN (pyin)
- NNLS Chroma + Chordino (nnls-chroma, chordino)
- Silvet (silvet)

**Implementation note**: `src/analyzer/capabilities.py:97` already honors `VAMP_PATH` and prepends it to the plugin search list. No code change needed — just set the env var from the Tauri sidecar launcher.

**Rationale**: Setting `VAMP_PATH` keeps plugin discovery inside the bundle, making the app self-contained. The existing search path still applies as a fallback, so users who have plugins installed locally won't be broken.

**Licensing**: QM Vamp Plugins, BeatRoot, pYIN, Chordino/NNLS, and Silvet are GPL or LGPL. Bundling GPL plugins with a redistributed app is permitted; we must surface the licenses in an About/Credits view and provide source (or a URL to source) per GPL §3.

---

## R6. Demucs model weights: first-use download

**Decision**: Do not bundle weights. On first stem-separation request, check for `htdemucs_6s` in the torch hub cache (`~/Library/Application Support/XLight/models/torch-hub/`), and if missing, prompt the user and download via a resumable HTTP client (not torch.hub's non-resumable fetcher).

**Key facts confirmed in research**:
- `htdemucs_6s` source: `https://dl.fbaipublicfiles.com/demucs/...` (four ~42 MB shards, ~170 MB total — substantially smaller than the ~1.5 GB I originally estimated).
- License: **CC BY-NC 4.0** (non-commercial). Redistribution of the weights in a bundled commercial app would require a separate Meta license. First-use download from the official URL sidesteps this entirely — the user's machine fetches the weights directly, the same way any other demucs consumer does.
- `torch.hub.load` does **not** resume partial downloads — a network interruption forces a full re-download.

**Implementation approach** (formalized in `contracts/weights-download.md`):
1. On first stem-separation request, backend checks for `htdemucs_6s` file set.
2. If missing, returns HTTP 409 with a JSON body `{needs_download: true, model: "htdemucs_6s", size_bytes: <known_size>}`.
3. Frontend surfaces a modal: "Stem separation needs a one-time ~170 MB download. Download now?" [Download] [Cancel]
4. On confirm, frontend POSTs to `/api/v1/models/download?name=htdemucs_6s`. Backend streams SSE progress events.
5. Backend downloads each shard via `requests` with `Range:` headers to a temp path in the cache directory, verifies SHA256 against hardcoded expected hashes, then atomically renames into place.
6. Partial files from interrupted downloads are detected on next attempt and resume from the last byte offset.

**Rationale for download over bundle** (even though weights are only ~170 MB):
- CC BY-NC 4.0 licensing makes bundling legally fraught for any future commercial distribution.
- Users who only ever use analyze/review/generate (no stem separation) never pay the cost.
- Model versions evolve; a URL-based fetch picks up any future version bump without requiring an installer rebuild.

---

## R7. User data directory: reuse existing `~/.xlight/` + add models subdir

**Decision**: Preserve the existing `~/.xlight/` convention used by the CLI for `library.json`, `settings.json`, `custom_themes/`, `logs/`, `custom_variants/`. Add one new sibling directory `~/Library/Application Support/XLight/models/` for the demucs weights cache and any other app-managed binary blobs. Do NOT migrate `~/.xlight/` into `Application Support` — that would break the CLI and the existing code's cross-platform `Path.home()` convention.

**Rationale**:
- The existing code (`src/library.py`, `src/settings.py`, `src/log.py`, `src/variants/library.py`) already uses `Path.home() / ".xlight"`. Not a sandbox-hardened path, but we're not opting into macOS App Sandbox for v1 (that would block many things we need, and spec did not call for it).
- The packaged app and the CLI share state — good: a user can install the packaged app, drop a file in, and then open a terminal and run a CLI command against the same library.
- `Application Support/XLight/models/` is standard for large, cache-like binary assets — separate from the small JSON config in `~/.xlight/`. Keeps the installer's uninstall clean: if a user deletes the `.app`, `Application Support/XLight/` can be cleaned up by hand, while `~/.xlight/` (which contains user data they may want to keep) is untouched.

**Code changes required**: None in the existing `~/.xlight/` paths. New file `src/packaging/models_paths.py` returns the `Application Support` location, used only by the weights-download module.

---

## R8. `.stems/<hash>/` path fallback

**Decision**: Add a writable-fallback branch in `src/analyzer/stems.py` (currently hardcodes `.stems/<hash>/` adjacent to the source MP3). If the source-adjacent path is not writable (e.g., macOS Music folder without Full Disk Access, iCloud-sideloaded folder, read-only volume), fall back to `~/Library/Application Support/XLight/stems/<hash>/`.

**Rationale**:
- Existing code (`src/analyzer/stems.py:38-62`) has no fallback — attempting to write to an unwritable source directory raises `RuntimeError`. For a packaged consumer app, this crashes the whole analyze flow when users drop files from Music or Desktop.
- Fallback is probe-then-write: attempt `os.access(parent, os.W_OK)` and a small test-write; on failure, redirect to the app's managed cache.
- The hash is stable (MD5 of source audio), so cached stems from one session are reusable in another regardless of which location they ended up in.

**Alternatives considered**:
- **Always write to the app-managed cache**: simpler, but breaks the CLI use case where users want stems next to the audio file for portability.
- **Require user to grant Full Disk Access**: poor UX — would need an in-app explainer and settings navigation.

---

## R9. Build artifacts: separate arm64 and x86_64 `.dmg` files

**Decision**: v1 produces two independently signed and notarized `.dmg` files: `XLight-<version>-arm64.dmg` and `XLight-<version>-x86_64.dmg`. The download page presents both with guidance (Apple Silicon vs Intel). Universal binary is deferred to v1.1 if demand warrants.

**Rationale**:
- Universal binaries require either building on an Apple Silicon Mac with `lipo`-merged universal Python (non-trivial to set up from scratch) or running two PyInstaller passes and manually merging. Neither adds v1 user value beyond "one download instead of two."
- Two separate builds make CI simpler (two independent matrix jobs), keep each installer smaller, and match how most Mac apps actually ship.

**Alternatives considered**:
- **Universal binary from day one**: correct long-term, but costly to set up for v1. The signing/notarization pipeline is the hard part; architecture merging is a later optimization.
- **Apple Silicon only** (drop Intel): fewer builds, but still-active Intel Mac users (2019–2020 vintage) would be excluded. Rosetta 2 works for CPU Python but torch MPS is off the table and performance on heavy audio/ML is noticeably worse.

---

## R10. Notarization pipeline: `notarytool` with staple

**Decision**: Use Xcode's `xcrun notarytool submit --wait` in the release script, immediately followed by `xcrun stapler staple` on the approved `.dmg`.

**Rationale**:
- `notarytool` replaced `altool` in 2023 and is the only supported path going forward.
- Realistic submission-to-approval time is 2–15 minutes for bundles of this size (a few hundred MB). `--wait` blocks the script cleanly.
- `stapler staple` embeds the notarization ticket in the `.dmg` so Gatekeeper accepts it offline.

**Pre-submission local checks** (in `sign-backend.sh` and `build-app.sh`):
1. `codesign --verify --deep --strict --verbose=2 <path>` — catches missing or mis-signed binaries.
2. `spctl -a -vvv -t execute <path>` — simulates Gatekeeper evaluation.
3. If either fails, fail the build rather than submitting.

**On rejection**: parse `notarytool log <submission-id>` JSON, not the human-readable message. Most common rejections for embedded Python are unsigned nested `.so` files and `@rpath` references leaking outside the bundle.

---

## R11. Tooling accounts and secrets

Items required before release engineering can actually ship a build. Not technical decisions, but prerequisites to flag to the user:

- **Apple Developer Program** membership ($99/year) — required for Developer ID certificate.
- **Developer ID Application** + **Developer ID Installer** certificates issued to the signing machine's keychain.
- **App-specific password** (or `notarytool`-stored credentials profile) for notarization API access.
- **Code-signing identity name** (the "Developer ID Application: ... (TEAMID)" string).
- A machine capable of building for both Apple Silicon and Intel — Apple Silicon Mac can cross-build for x86_64 via `arch -x86_64` + x86_64 Python, or use separate CI runners.

These belong in `quickstart.md` as prerequisites, not in the implementation tasks — the plan assumes they're present.

---

## Summary of resolved clarifications

No unresolved `NEEDS CLARIFICATION` remain. The two scope questions in the spec (OS scope, bundle strategy) were resolved by the user in conversation and recorded in `spec.md` (FR-013, FR-014, FR-015).
