# XLight packaging — Windows build handbook

This directory contains everything required to build a basic (unsigned)
Windows desktop build of XLight. macOS support was explored (see
`specs/052-tauri-desktop-packaging/`, kept for historical reference) and
dropped from scope on 2026-07-24 — this is now Windows-only.

This is a **basic, unsigned** build — no EV code-signing certificate yet, so
Windows SmartScreen will show an "unknown publisher" warning on first run.

## Layout

| Path | Purpose |
|---|---|
| `tauri/` | Tauri 2 native shell (Rust + minimal JS). Wraps the React frontend in a WebView2 window and spawns the Python sidecar. |
| `tauri/src-tauri/Cargo.toml` | Rust dependencies. |
| `tauri/src-tauri/src/main.rs` | Shell entry: spawn sidecar, discover backend port, emit to webview, clean shutdown (`taskkill /F`). |
| `tauri/src-tauri/tauri.conf.json` | Bundle identity, icons, resources, NSIS installer config. |
| `tauri/src-tauri/capabilities/main.json` | Tauri 2 permission capabilities (shell, dialog, event, narrow fs). |
| `tauri/src-tauri/icons/icon.ico` | Windows installer/taskbar icon. |
| `pyinstaller/backend.spec` | PyInstaller onedir spec for the Flask backend. |
| `pyinstaller/hooks/` | Hidden imports + data collection for madmom, torch, librosa, demucs. |
| `pyinstaller/plugins/vamp/x86_64-windows/` | Vamp plugin `.dll` files. |
| `scripts/build-backend.ps1` | PyInstaller build entry — produces `binaries/backend-x86_64-pc-windows-msvc/`. |
| `scripts/build-app.ps1` | Runs `cargo tauri build` and locates the NSIS installer. |
| `scripts/fetch-vamp-plugins.ps1` | Verify/obtain `.dll`s for QM, BeatRoot, pYIN, Chordino/NNLS, Silvet. |
| `src/packaging/platform_paths.py` | Single source of truth for the `%LOCALAPPDATA%\XLight` Application Support root (Python side; `main.rs` mirrors it for the Rust shell's own `TORCH_HOME` setup). |

## Building

Requires: Rust + `cargo-tauri`, Node/pnpm, Python 3.11 (`py -3.11` via the
official python.org installer, not the Microsoft Store version — madmom has
no 3.12+ wheels), and the NSIS bundler that `cargo tauri build` pulls in
automatically.

```powershell
.\packaging\scripts\fetch-vamp-plugins.ps1     # verify/obtain Vamp .dll files
.\packaging\scripts\build-backend.ps1          # PyInstaller onedir -> binaries\backend-x86_64-pc-windows-msvc\
.\packaging\scripts\build-app.ps1              # cargo tauri build -> NSIS installer
```

Produces an unsigned installer at
`packaging/tauri/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*-setup.exe`.

**Not yet done**: no signing, and this has not yet been built/run on a real
Windows machine end-to-end — the Rust/PyInstaller changes are
source-complete but unverified beyond local Python unit tests (no Rust
toolchain was available to compile-check `main.rs` in the environment this
was authored in). Build it once on a real machine and fix whatever the
compiler/PyInstaller turns up before relying on it.

## Dev vs packaged mode

The backend reads `XLIGHT_PACKAGED=1` to decide whether it's running inside the
bundle. Dev mode (`python -m src.review.cli` + `pnpm dev`) never sets it, so:

- Stem cache stays next to source audio (as today).
- `VAMP_PATH` is not overridden (uses the user's local plugin install).
- `TORCH_HOME` is not overridden (uses the user's default torch cache).

Packaged mode sets all three from the Rust launcher. See
`src/packaging/bundled_mode.py` for the detection helper.

## Vamp plugin source pinning

| Pack | Version | Upstream | Notes |
|---|---|---|---|
| QM Vamp Plugins | TBD | https://code.soundsoftware.ac.uk/projects/qm-vamp-plugins/ | Windows build needed. |
| BeatRoot | TBD | https://code.soundsoftware.ac.uk/projects/beatroot-vamp | |
| pYIN | TBD | https://code.soundsoftware.ac.uk/projects/pyin | |
| NNLS Chroma / Chordino | TBD | https://code.soundsoftware.ac.uk/projects/nnls-chroma | |
| Silvet | TBD | https://code.soundsoftware.ac.uk/projects/silvet | |

Record the exact version (or git SHA) and SHA256 of each `.dll` after the
first successful release.

## FR-008 scope note

Partial-write safety for `~/.xlight/library.json` and the analysis cache
inherits existing dev-mode behavior — not hardened by this feature. If a
future incident shows corruption on forced shutdown, open a separate spec
for atomic-write (write-to-temp + `os.replace`). This feature's FR-008
scope is limited to clean process shutdown (handled in the Tauri shell via
the window-destroyed event + `taskkill /F`).
