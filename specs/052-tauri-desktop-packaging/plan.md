> **HISTORICAL — macOS scope dropped 2026-07-24.** This spec targeted macOS-only packaging and is kept for historical reference only (research/decisions may still be useful). The project is now Windows-only; see [`packaging/README.md`](../../packaging/README.md) for the current, actively-maintained build handbook.

# Implementation Plan: Tauri Desktop Packaging (macOS v1)

**Branch**: `052-tauri-desktop-packaging` | **Date**: 2026-04-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/052-tauri-desktop-packaging/spec.md`

## Summary

Package the existing React/Vite frontend + Flask Python analysis backend as a signed, notarized macOS application bundle (`.app` inside a `.dmg`) so non-technical users can install and use it without a terminal, Python, Node, or developer tooling. Approach: a Tauri shell hosts the React UI in a native WKWebView window and launches a PyInstaller-bundled Python/Flask process as a sidecar on a dynamically chosen localhost port. All runtime dependencies (Python interpreter, numpy, librosa, madmom, torch CPU, ffmpeg, Vamp plugin `.dylib`s) are bundled. Demucs stem-separation model weights (~170 MB) download on first stem-separation use rather than shipping in the installer — primarily because the weights are CC BY-NC 4.0 (non-commercial) and redistribution would require a separate Meta license. v1 targets macOS only (Apple Silicon + Intel as separate `.dmg` artifacts); Windows and Linux are deferred.

## Technical Context

**Language/Version**: Python 3.11+ (backend, sidecar); TypeScript 5+ / ES2022 (frontend); Rust 1.75+ (Tauri shell, compiled as part of `tauri build`, not hand-written Rust feature code)
**Primary Dependencies**: Tauri 2.x; existing Flask 3+, React 18+, Zustand 4+, Vite 5+ (frontend, unchanged); existing analyzer stack (librosa, madmom, vamp, torch, ffmpeg). New build-time only: `pyinstaller` 6+, `@tauri-apps/cli`, Apple `notarytool` (bundled with Xcode).
**Storage**: JSON on local disk. Existing `~/.xlight/` convention (library, custom themes, preferences) preserved and shared with the CLI. Existing `.stems/<hash>/` co-location with source audio preserved with fallback to `~/Library/Application Support/XLight/stems/<hash>/` when the source directory is not writable.
**Testing**: pytest (existing Python suite, unchanged); Vitest + React Testing Library (existing frontend suite, unchanged). New: Playwright (or `tauri-driver`) smoke test running against the built `.app` to verify sidecar startup, port discovery, and the analyze → review → generate path. Manual notarization verification.
**Target Platform**: macOS 12 Monterey and later (both Apple Silicon and Intel x86_64). Not universal binary in v1 — two separate `.dmg` downloads, one per architecture.
**Project Type**: Desktop app wrapping an existing web application (Option 2 web-application layout — frontend + backend already exist — plus a new `packaging/` root for Tauri shell and build scripts).
**Performance Goals**: Cold app launch <5s on a typical consumer Mac after first launch; analyze → review → generate flow for a 3-min MP3 completes within 15% of current dev-mode timing (per SC-002); weights download on first stem-separation completes and resumes cleanly on interrupted networks.
**Constraints**: Fully offline for core analyze/review/generate workflow after install. Signed and notarized with hardened runtime. Every embedded binary (Python interpreter, `.dylib`s, Vamp plugins) individually signed. Entitlement `com.apple.security.cs.disable-library-validation` required for Vamp `dlopen` from plugin directory. No Apple Silicon + Intel universal binary in v1 — separate builds keep each installer under ~1 GB.
**Scale/Scope**: Single-user desktop app. One running instance per user. Bundled installer per architecture ~700 MB–1 GB. First stem-separation downloads ~170 MB of `htdemucs_6s` model weights (one-time, cached in `~/Library/Application Support/XLight/models/`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution v1.0.0** — evaluated per principle:

### I. Audio-First Pipeline ✅
Packaging does not touch analysis logic. All existing algorithms, timing tracks, and reproducibility guarantees carry over unchanged. FR-004 explicitly requires byte-for-byte equivalent outputs.

### II. xLights Compatibility ✅
Sequence export (`.xsq` generation via `src/generator/xsq_writer.py`) is unchanged. Packaged app writes the same files as the current CLI/web flow.

### III. Modular Pipeline ✅
Packaging is a new outermost layer (Tauri shell + PyInstaller bundler) wrapping the existing pipeline. Stages communicate as today (frontend ↔ Flask HTTP). No stage is modified except for two small additions:
1. Vamp plugin path resolution gets an env-var override (`VAMP_PATH`) for bundled mode.
2. `.stems/<hash>/` path resolution gains a writable-fallback branch for sandbox-protected source directories.
Both are additive; the current dev-mode code paths still work.

### IV. Test-First Development ✅
New test surface (sidecar lifecycle, port discovery, path fallback, weights download, plugin discovery under bundled paths) is covered by tests in Phase 2. Contract-first for the sidecar startup handshake.

### V. Simplicity First ✅ (with one flag)
Scope is intentionally minimal: one bundler (PyInstaller), one shell (Tauri), one OS (macOS), two arch builds, no auto-update in v1, no universal binary in v1, no custom IPC layer (reuse existing Flask HTTP). The only speculative-feeling element is the sidecar handshake protocol — justified below.

### Technical Constraints evaluation

- **Offline operation (constitution)**: The constitution forbids cloud API calls "for audio analysis or sequence generation." The demucs-weights-on-first-use download is a one-time model-asset fetch, not a per-analysis API call — analysis itself runs locally. Flagging this in Complexity Tracking below to make the distinction explicit and avoid ambiguity in future reviews.
- **Performance baseline (3-min MP3 in <60s)**: Unaffected by packaging; sidecar startup adds ~1–2s to overall wall-clock for the first request only.
- **Input/output formats**: Unchanged.

**Gate result**: PASS. One documented soft-constraint clarification in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/052-tauri-desktop-packaging/
├── plan.md              # This file
├── research.md          # Phase 0 output — packaging/signing/weights decisions
├── data-model.md        # Phase 1 output — config, manifest, runtime state entities
├── quickstart.md        # Phase 1 output — build, sign, notarize, install walkthrough
├── contracts/
│   ├── sidecar-handshake.md    # How the frontend discovers the backend port
│   ├── weights-download.md     # First-use model download protocol
│   └── file-dialog-ipc.md      # Tauri <-> frontend native dialog contract
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
# Existing code — unchanged except for two targeted edits
src/
├── analyzer/            # unchanged
├── review/
│   ├── frontend/        # existing React/Vite app — minor changes:
│   │   └── src/
│   │       ├── lib/
│   │       │   ├── backendPort.ts        # NEW — reads port from Tauri init or env
│   │       │   └── nativeDialog.ts       # NEW — wraps Tauri dialog API, no-ops in dev
│   │       └── ...
│   └── server.py        # minor: binds to 127.0.0.1 on a dynamic port; prints port on stdout for sidecar handshake
├── generator/           # unchanged
├── cli.py               # unchanged (CLI remains developer-only)
└── packaging/           # NEW — all bundling/signing/notarization logic lives here
    ├── __init__.py
    ├── vamp_paths.py    # NEW — resolves VAMP_PATH env for bundled vs dev
    └── stems_paths.py   # NEW — writable-fallback for .stems/<hash>/ location

# New packaging root — sibling to src/ — holds Tauri shell and build tooling
packaging/
├── tauri/
│   ├── src-tauri/
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json       # bundle identifier, icons, sidecar binding
│   │   ├── build.rs
│   │   ├── entitlements.plist    # hardened-runtime + library-validation disable
│   │   └── src/
│   │       └── main.rs           # thin Rust: launch sidecar, pass port to webview
│   └── icons/                    # .icns + pngs for .app bundle
├── pyinstaller/
│   ├── backend.spec              # PyInstaller onedir spec for Flask + deps
│   ├── hooks/                    # hidden imports for librosa, madmom, torch, vamp
│   └── plugins/
│       └── vamp/                 # bundled Vamp plugin .dylib files (QM, BeatRoot, pYIN, Chordino, NNLS, Silvet)
├── scripts/
│   ├── build-backend.sh          # pyinstaller invocation
│   ├── sign-backend.sh           # codesign every .dylib + executable
│   ├── build-app.sh              # tauri build
│   ├── notarize.sh               # notarytool submit + staple
│   └── release.sh                # end-to-end: clean → build → sign → notarize → dmg
└── README.md                     # release engineer handbook

tests/
├── unit/                # existing — unchanged
├── integration/         # existing — unchanged
└── packaging/           # NEW
    ├── test_vamp_paths.py         # verify VAMP_PATH override logic
    ├── test_stems_paths.py        # verify writable-fallback logic
    ├── test_port_discovery.py     # verify sidecar port handshake
    └── smoke/
        └── test_app_launch.py     # Playwright/tauri-driver smoke test against built .app
```

**Structure Decision**: Option 2 (web application) extended with a new sibling `packaging/` directory. Rationale: packaging is a concern layer above the existing app, not a transformation of it. Putting it in its own root keeps build tooling, Tauri Rust code, PyInstaller specs, and shell scripts together and out of `src/`. The two tiny additions to `src/` (`vamp_paths.py`, `stems_paths.py`, one-line edits to `server.py`) remain with the code they affect so dev-mode behavior is preserved.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Soft deviation from "fully offline" constitution constraint (demucs weights download on first stem-separation) | `htdemucs_6s` weights are CC BY-NC 4.0 (non-commercial) — redistribution in a bundled app would require a separate Meta license we do not have. Secondary: users who never use stem separation never pay the ~170 MB download cost. The download happens once, over an explicit user prompt, and no subsequent analysis touches the network. | Bundling the weights: rejected — the non-commercial license forbids redistribution without a Meta agreement. Dropping stem separation entirely: rejected — it is a promised feature. |
| Sidecar handshake protocol (Flask prints chosen port on stdout; Rust parses first line before injecting into webview init script) | Binding to a fixed port collides with other apps or other instances. Random free port + handshake avoids that without adding a discovery service. | Fixed port (e.g., 5055): rejected because collisions are real (user may run dev Flask on 5000, other apps on 5055). Full IPC bridge replacing HTTP: rejected as a massive rewrite for zero user-visible benefit. |
| Separate arm64 and x86_64 `.dmg` artifacts in v1 (not universal) | Universal binaries require either building on an Apple Silicon Mac with `lipo`-merged universal Python (non-trivial) or two PyInstaller passes + manual merge. Two separate `.dmg` downloads is mechanically simpler for v1. | Universal binary: valid v1.1 optimization once the signing/notarization pipeline is proven. Not worth the setup cost for the first release. |

## Phase 0 and Phase 1 artifacts

See `research.md` (Phase 0), `data-model.md` / `contracts/*` / `quickstart.md` (Phase 1).
