> **HISTORICAL — macOS scope dropped 2026-07-24.** This spec targeted macOS-only packaging and is kept for historical reference only (research/decisions may still be useful). The project is now Windows-only; see [`packaging/README.md`](../../packaging/README.md) for the current, actively-maintained build handbook.

# Quickstart: Building and Shipping the macOS Desktop App

**Feature**: 052-tauri-desktop-packaging
**Audience**: release engineer (you or a maintainer) building the first signed and notarized `.dmg`.

This is a dry walkthrough of the pipeline the plan introduces. Before any step: `.specify/memory/constitution.md` v1.0.0 is the governing constitution; this feature passes its gates (see `plan.md` Constitution Check).

## Prerequisites (one-time per signing machine)

1. **Apple Developer Program** membership active ($99/yr).
2. **Xcode Command Line Tools** installed: `xcode-select --install`.
3. **Developer ID Application certificate** in the local keychain. Export the identity name: `security find-identity -v -p codesigning` → copy the `"Developer ID Application: <Name> (TEAMID)"` string.
4. **notarytool credentials profile** stored with:
   ```bash
   xcrun notarytool store-credentials XLIGHT_NOTARY \
     --apple-id <your-apple-id> \
     --team-id <TEAMID> \
     --password <app-specific-password>
   ```
5. **Rust toolchain**: `rustup` with stable (`rustup default stable`). Install Tauri CLI: `cargo install tauri-cli --version "^2.0"`.
6. **Python 3.11+** available via `pyenv` or system, matching the version you intend to ship (pick one — 3.11 is the current `pyproject.toml` target).
7. **Node 20+** and **pnpm** (or npm) for the frontend.
8. **Vamp plugin `.dylib` files** for the bundled packs (QM, BeatRoot, pYIN, Chordino/NNLS, Silvet) placed into `packaging/pyinstaller/plugins/vamp/` — one copy per target architecture. See `packaging/README.md` (created in task phase) for where to obtain each.

## Per-release build

### 1. Clean and select target architecture

```bash
cd /path/to/xlight-autosequencer
# For this release cycle, pick one:
export XLIGHT_TARGET_ARCH=aarch64   # Apple Silicon
# or
export XLIGHT_TARGET_ARCH=x86_64    # Intel
```

### 2. Build frontend

```bash
cd src/review/frontend
pnpm install --frozen-lockfile
pnpm run build
cd ../../..
```

Produces `src/review/frontend/dist/` — static assets Tauri will bundle.

### 3. Build Python sidecar via PyInstaller

```bash
./packaging/scripts/build-backend.sh $XLIGHT_TARGET_ARCH
```

This script:
- Creates/activates a venv under `.build-venv-$ARCH/`.
- Installs backend deps from `pyproject.toml` (pinned).
- Runs `pyinstaller packaging/pyinstaller/backend.spec` with `--target-arch $ARCH`.
- Copies `packaging/pyinstaller/plugins/vamp/$ARCH/*.dylib` into the onedir under `_vamp/`.
- Renames the resulting executable to `backend-$ARCH-apple-darwin` per Tauri's sidecar naming.
- Output: `packaging/tauri/src-tauri/binaries/backend-$ARCH-apple-darwin` (and the onedir resources).

### 4. Sign every binary inside the Python bundle

```bash
./packaging/scripts/sign-backend.sh $XLIGHT_TARGET_ARCH
```

This script:
- Walks the onedir, finds every `.dylib`, `.so`, and the main executable.
- Signs each bottom-up with `codesign --force --options runtime --entitlements packaging/tauri/src-tauri/entitlements.plist --sign "Developer ID Application: …"`.
- Verifies with `codesign --verify --deep --strict --verbose=2`.
- Fails the build on any verification error — do not proceed to Tauri build until this is clean.

### 5. Build the Tauri `.app`

```bash
cd packaging/tauri
pnpm install --frozen-lockfile   # installs @tauri-apps/cli and plugins
cargo tauri build --target $XLIGHT_TARGET_ARCH-apple-darwin
cd ../..
```

Produces `packaging/tauri/src-tauri/target/$ARCH-apple-darwin/release/bundle/macos/XLight.app` and a `.dmg` next to it.

Tauri performs signing itself using `tauri.conf.json > bundle.macOS.signingIdentity`. Verify it picked up the same identity as step 4:
```bash
codesign --display --verbose=4 packaging/tauri/src-tauri/target/$ARCH-apple-darwin/release/bundle/macos/XLight.app
```

### 6. Notarize

```bash
./packaging/scripts/notarize.sh $XLIGHT_TARGET_ARCH
```

This script:
- Locates the `.dmg` produced in step 5.
- Submits: `xcrun notarytool submit <dmg> --keychain-profile XLIGHT_NOTARY --wait`.
- On success: `xcrun stapler staple <dmg>`.
- On rejection: dumps `notarytool log <submission-id>` and fails.

Realistic wait: 2–15 minutes per submission.

### 7. Verify and publish

```bash
# Verify the stapled ticket is attached
xcrun stapler validate packaging/tauri/src-tauri/target/*/release/bundle/dmg/XLight-*.dmg

# Simulate a fresh install
hdiutil attach <dmg>
cp -R /Volumes/XLight/XLight.app /tmp/xlight-test/
spctl -a -vvv -t execute /tmp/xlight-test/XLight.app
# Expected: accepted source=Notarized Developer ID
```

Upload the `.dmg` to the download host, update the download page with version and checksum, update the in-app `packaging-manifest.json` URL references if needed.

### 8. Repeat for the other architecture

Run steps 1–7 again with the opposite `XLIGHT_TARGET_ARCH`. You end up with two `.dmg` files: `XLight-<version>-arm64.dmg` and `XLight-<version>-x86_64.dmg`.

## Developer local workflow (no packaging)

Developers working on features do NOT run the packaging pipeline. They use:

```bash
# Terminal 1 — backend
python -m src.review.cli --host 127.0.0.1 --port 5000

# Terminal 2 — frontend
cd src/review/frontend && pnpm dev
```

This path is unchanged by this feature. The sidecar handshake only activates when `XLIGHT_PACKAGED=1` is set; dev mode leaves it unset and uses the existing fixed-port behavior.

## Smoke test checklist (before declaring a release ready)

1. Install `.dmg` on a clean macOS VM (or a Mac you control) — no `~/.xlight/`, no prior install.
2. App launches from Finder without a Gatekeeper warning.
3. Upload screen appears within 5 seconds.
4. Drop a known MP3 — analysis progresses and completes.
5. Timeline view renders with sections and themes.
6. Edit a section boundary — change persists after app restart.
7. Generate and save an `.xsq` via native Save dialog.
8. Click "Separate Stems" on a song — license + download prompt appears, download completes, stems are generated.
9. Quit the app — no orphan Python process (check Activity Monitor).
10. Relaunch — library entry is still present.

Any failure is a blocker.

## Troubleshooting (common first-release issues)

- **"App is damaged and can't be opened"** on user machines: stapling was skipped or failed. Re-run step 7 verification. The `.dmg` must be stapled, not just the `.app` inside it.
- **Backend doesn't start inside the bundled app** (blank window after launch): usually a PyInstaller hidden-import miss or a signing failure on a nested `.dylib`. Check Console.app for the sidecar's stdout/stderr capture.
- **Vamp plugins not found** (error like "No plugin qm-vamp-plugins:qm-barbeattracker"): `VAMP_PATH` isn't being set by the Tauri launcher, or the `.dylib`s didn't make it into `Contents/Resources/vamp/`. Verify both.
- **Notarization rejects for "insufficient permissions" on embedded file**: one of the nested `.dylib`s or `.so`s wasn't signed with `--options runtime`. Re-run `sign-backend.sh` — it iterates explicitly rather than relying on `codesign --deep`.
- **Stem separation hangs on first click**: weights download started but the UI missed the SSE progress stream. Check browser devtools network tab — the stream should be visible.

## Status

All Phase 1 artifacts exist: `plan.md`, `research.md`, `data-model.md`, three contracts in `contracts/`, and this `quickstart.md`. Ready for `/speckit.tasks`.
