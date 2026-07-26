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
| `scripts/build-app.ps1` | Stamps `packaging-manifest.json` (see below), runs `cargo tauri build`, locates the NSIS installer. |
| `scripts/generate-manifest.ps1` | Stamps `tauri/src-tauri/packaging-manifest.json` with a real `app_version` (git tag if HEAD is exactly on one, else `<base-version>+<short-sha>[-dirty]`), build timestamp, and commit. Called automatically by `build-app.ps1` — the checked-in file is just a static placeholder, never meant to be read as-is. |
| `scripts/fetch-vamp-plugins.ps1` | Verify/obtain `.dll`s for QM, BeatRoot, pYIN, Chordino/NNLS, Silvet. |
| `pyinstaller/patches/vamp-1.1.0-msvc-ssize_t.patch` | The `vamp` PyPI package has never been built with MSVC (uses POSIX `ssize_t`, undefined on MSVC). `build-backend.ps1` downloads the sdist, applies this one-header patch, and builds from the patched source — see the patch file and the script's own comments for the full story. |
| `src/packaging/platform_paths.py` | Single source of truth for the `%LOCALAPPDATA%\XLight` Application Support root (Python side; `main.rs` mirrors it for the Rust shell's own `TORCH_HOME` setup). |

## Building

Requires: Rust + `cargo-tauri`, Node/pnpm, Python 3.11 (`py -3.11` via the
official python.org installer, not the Microsoft Store version — madmom has
no 3.12+ wheels), and the NSIS bundler that `cargo tauri build` pulls in
automatically.

```powershell
.\packaging\scripts\fetch-vamp-plugins.ps1     # verify/obtain Vamp .dll files
.\packaging\scripts\build-backend.ps1          # PyInstaller onedir -> binaries\backend-x86_64-pc-windows-msvc\
.\packaging\scripts\build-app.ps1              # stamp manifest + cargo tauri build -> NSIS installer
```

Produces an unsigned installer at
`packaging/tauri/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*-setup.exe`.

**Verified working end-to-end (2026-07-25)** against a real Windows machine,
including a full analyze run (demucs stem separation + madmom beat/bar
tracking) on a real song through the packaged app. Not yet signed (no EV
cert).

### Environment gotchas hit building this for real (2026-07-25)

These cost real time to diagnose — read before assuming a build failure is a
real bug:

- **`py -3.11` can silently misbehave when invoked from a non-interactive
  shell/tool** (observed specifically running `build-backend.ps1` through an
  AI coding assistant's command-execution tool): the launcher's argument
  splatting can drop `-3.11`/`--version` and fall through to an interactive
  REPL of whatever the *default* `py` version is, which then crashes on
  console-width detection since there's no real console attached. Symptom:
  `build-backend.ps1` fails immediately with a huge Python REPL traceback
  pasted into the error, claiming the interpreter "reports" the traceback
  text as its version. **Fix**: skip the `py` launcher entirely — set
  `$env:PY311` to a direct path to a real Python 3.11 executable (e.g. a
  scoop/pyenv install: `$env:PY311 = "C:\path\to\python311\python.exe"`)
  before running `build-backend.ps1`. Confirmed the direct-path approach
  works reliably where `py -3.11` did not, in that same environment.
- **`cargo` may not be on `PATH`** in a non-interactive/tool-driven shell
  even when Rust is installed and works fine in a normal terminal. Fix:
  `$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"` before calling
  `build-app.ps1`.
- **PowerShell tool output pagers**: `tail`/`head` aren't real PowerShell
  cmdlets — use `Select-Object -Last N` / `-First N`, or `Get-Content -Tail
  N`.

### The algorithm-bundling bug (read this before touching backend.spec)

`src/analyzer/algorithms/registry.py` loads every algorithm module via
`importlib.import_module(module_path)` with `module_path` as a **runtime
string** from a list (`_ALGORITHM_DEFS`), not a literal `import` statement.
PyInstaller's static bytecode analyzer cannot follow that — it only bundles
modules it can see in the actual import graph. Before `backend.spec` called
`collect_submodules("src.analyzer.algorithms")` (added 2026-07-25), **none**
of `librosa_beats.py`, `madmom_beat.py`, the `vamp_*.py` modules, etc. were
ever bundled into the frozen exe, even though every *top-level* package
import (`madmom`, `demucs`, `librosa`...) succeeded fine and `SELF-TEST OK`
passed. Every single algorithm silently failed `_try_import` inside the
registry with **no exception ever printed anywhere** (the registry's `_add()`
helper returns `False` silently on a missing class), producing
`algorithms_run: []` for every song regardless of capabilities, which
cascaded into the story builder collapsing every song into one flat "intro"
section. This was extremely hard to diagnose precisely because nothing ever
errored — do not remove the `collect_submodules` call, and if you add a new
`src/analyzer/algorithms/*.py` file, it's picked up automatically (no
`backend.spec` edit needed). `bundled_entrypoint.py`'s `--self-test` now
directly exercises `get_algorithm_map()` for both librosa (always) and
madmom (when importable) so a regression here fails the build/self-test
instead of only surfacing as "no sections detected" at runtime.

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
