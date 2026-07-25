> **HISTORICAL — macOS scope dropped 2026-07-24.** This spec targeted macOS-only packaging and is kept for historical reference only (research/decisions may still be useful). The project is now Windows-only; see [`packaging/README.md`](../../packaging/README.md) for the current, actively-maintained build handbook.

# Feature Specification: Tauri Desktop Packaging

**Feature Branch**: `052-tauri-desktop-packaging`
**Created**: 2026-04-22
**Status**: Draft
**Input**: User description: "I want to look at using Tauri to package up the web application into a executable or an application — probably better than Electron"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install and launch without a terminal (Priority: P1)

A non-technical user downloads a single installer for their operating system, runs it like any other desktop app, and launches the analyzer/review UI from their applications menu or dock. They never see a terminal, never run `pip install`, and never type a CLI command. On first launch, the familiar drop-file upload screen opens in a native window.

**Why this priority**: This is the entire point of packaging. Without it, the product is still developer-only. Every downstream capability (library management, section editing, sequence generation) only reaches non-technical users once they can install and launch the app.

**Independent Test**: Hand a built installer to someone with no Python, no Node, no Homebrew, and no command-line experience. They double-click the installer, accept defaults, launch the app, and see the upload screen. If that flow works end-to-end, the story is validated — even if other features regress temporarily.

**Acceptance Scenarios**:

1. **Given** a user with a clean machine (no Python, no Node, no project dependencies installed), **When** they run the downloaded installer and launch the app, **Then** the native application window opens showing the upload screen within a reasonable time on first launch.
2. **Given** the app is installed, **When** the user closes and relaunches it, **Then** the app starts faster than the first launch and restores their previously seen library and preferences.
3. **Given** the user launches the app, **When** they drop an audio file onto the upload screen, **Then** analysis runs and progresses exactly as it does in the current browser-based workflow, producing the same library entry and timeline view.

---

### User Story 2 - Analyze, review, and generate sequences offline (Priority: P1)

Once installed, the user performs the full existing workflow — drop an MP3, watch analysis progress, review sections and themes, edit boundaries, generate an `.xsq` sequence — entirely from the packaged app, with no browser, no `flask run`, no separate processes to start, and no internet connection required (except for optional lyric fetches).

**Why this priority**: The packaged app must preserve, not diminish, existing capability. If core flows regress or require extra setup, the packaging hasn't shipped a product — it has shipped a regression.

**Independent Test**: Install the packaged app on a machine with its network disabled (or only localhost). Walk through the canonical flow end-to-end: drop file → analyze → view timeline → adjust a section boundary → generate sequence → save `.xsq` to disk. All of this must work.

**Acceptance Scenarios**:

1. **Given** the packaged app is running, **When** the user performs the analyze → review → generate flow, **Then** outputs (analysis JSON, stems, sequences) are equivalent to those produced by the current dev setup for the same input.
2. **Given** no network connection, **When** the user runs analyze, review, and generate, **Then** all non-network-dependent features work; features that require the network (e.g. Genius lyric fetch) degrade gracefully with a clear message rather than hanging or erroring opaquely.
3. **Given** the user produced analysis output in a previous session, **When** they relaunch the app, **Then** their library, analysis cache, custom themes, and section edits are still present.

---

### User Story 3 - Access files and save outputs to chosen locations (Priority: P2)

The user drops files from Finder/Explorer, opens files via the OS's native file picker, and saves generated sequences, exports, and backups to arbitrary locations on their disk — using the OS-native file dialogs they already know, not browser upload dialogs or download-folder dumping.

**Why this priority**: A desktop app that only accepts drag-drop or saves to a hidden app-data folder feels strictly worse than the browser version. Native file integration is what justifies the packaging over "just run it in a browser."

**Independent Test**: Use the packaged app to open an MP3 via the native Open dialog, then export an `.xsq` sequence to a user-chosen folder. Both operations must succeed without any browser download behavior.

**Acceptance Scenarios**:

1. **Given** the user clicks an Open action, **When** the OS file picker appears, **Then** they can select any readable audio file on their system and the app analyzes it.
2. **Given** the user generates a sequence, **When** they click Save/Export, **Then** a native Save dialog appears and the file is written to the location they choose.
3. **Given** a file path referenced in the library no longer exists (user moved or deleted it), **When** the user tries to open that entry, **Then** the app shows a clear "file not found" state and offers to re-locate the file, rather than silently failing.

---

### User Story 4 - Update to newer versions (Priority: P3)

When a new version of the app is released, the user is notified from within the app and can update with one click (or at minimum, is pointed to a download link and can install the new version without losing their library or settings).

**Why this priority**: Not required for initial shipping, but important for maintainability — without an update path, every bug fix requires users to manually find and reinstall the app. Can ship after P1/P2 are validated.

**Independent Test**: Publish two sequential versions. Install v1, then verify the user sees an update prompt or notification for v2, installs it, and their library and preferences are preserved.

**Acceptance Scenarios**:

1. **Given** a newer version is available, **When** the user launches the app (or checks for updates manually), **Then** they are informed of the new version and offered a path to install it.
2. **Given** the user updates to a newer version, **When** they launch the updated app, **Then** their library, analysis cache, custom themes, and section edits from the prior version are intact.

---

### Edge Cases

- **First-launch extraction time**: The installer is large and first launch may need to extract or warm up bundled assets (plugin binaries, JIT caches). The app must show visible progress during any one-time extraction rather than presenting a silent or unresponsive window.
- **First stem-separation download**: The first time a user triggers stem separation, the app must explicitly prompt for the one-time model-weights download, show clear progress, and let the user cancel or defer without corrupting state.
- **Interrupted stem-weights download**: If the network drops partway through downloading the stem-separation weights, the app must detect the partial file, discard it, and retry cleanly on the next attempt — not leave a corrupted model file that causes opaque runtime errors.
- **Apple Silicon vs Intel performance gap**: On Intel Macs the audio/ML pipeline will be slower than on Apple Silicon. The app must not present features as "broken" when they are simply slower on older hardware; progress indicators must be accurate across both architectures.
- **Missing optional dependencies at runtime**: Features that depend on optional tooling (e.g. stem separation models, Vamp plugin packs, Genius API keys) must degrade gracefully — disable the feature with a clear explanation, not crash.
- **Multiple instances**: If the user double-clicks the app icon twice, the system must either focus the existing window or allow a second instance cleanly — not leave two competing backend processes fighting over the same library file.
- **Gatekeeper and notarization**: Unsigned or un-notarized builds will be blocked by macOS Gatekeeper with an opaque "can't be opened" dialog. The build process must produce signed and notarized artifacts so real users can install without right-click-Open workarounds or security-override instructions.
- **Background processing during close**: If the user closes the window while an analysis is running, the app must either finish the job cleanly, cancel it cleanly, or prompt — not leak a background process or corrupt the cache.
- **Disk permissions**: On macOS, access to the user's Music folder may trigger a permission prompt. The app must handle denial without crashing.
- **Sandboxed write locations**: Existing on-disk conventions (`~/.xlight/library.json`, `.stems/<hash>/` co-located with source audio) must continue to work. If the user adds a file from a protected macOS folder (Music, Desktop, iCloud Drive) where writing sidecar stem folders is blocked, the app must fall back to a user-data location rather than silently failing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST ship as a single installable artifact per supported operating system that a non-technical user can install by double-clicking, without any terminal, package manager, or developer tool.
- **FR-002**: The installed app MUST launch a native OS window (title bar, dock/taskbar icon, app menu) and present the existing upload/library/timeline UI inside that window — not inside a user-launched browser.
- **FR-003**: The installed app MUST perform all existing analysis workflows (audio upload, stem separation, timing analysis, theme generation, section editing, sequence export) without requiring the user to separately start a server, run a CLI command, or keep a terminal open.
- **FR-004**: The installed app MUST produce the same analysis outputs, sequences, and exports as the current dev-mode workflow for equivalent inputs — packaging MUST NOT change analysis results or file formats.
- **FR-005**: The installed app MUST persist user data (library index, analysis cache, custom themes, section edits, preferences) across app restarts and across version upgrades, using a location appropriate to the host OS.
- **FR-006**: The installed app MUST use native OS file dialogs for opening audio files and saving generated sequences, and MUST support drag-and-drop from the OS file manager onto the app window.
- **FR-007**: The installed app MUST NOT require an internet connection to perform the core analyze → review → generate workflow. Features that legitimately need the network — lyric fetch, and a one-time first-use download of stem-separation model weights (see FR-015) — MUST either degrade gracefully with an informative message or, in the case of the one-time weights download, prompt explicitly before accessing the network. No feature may hang or error opaquely when offline.
- **FR-008**: The installed app MUST handle being closed mid-job without leaking background processes, leaving partial writes to the library, or corrupting the cache.
- **FR-009**: The installed app MUST, on first launch, either start within a reasonable time using bundled assets, or clearly communicate any one-time setup progress (download, extraction) with visible status — not present a silent or unresponsive window.
- **FR-010**: The build and release process MUST produce artifacts that pass the host OS's default code-signing / notarization / gatekeeping requirements so users can install without manually overriding security warnings. *(If signing infrastructure is not yet available, an interim documented bypass is acceptable only for a limited developer preview, not for general release.)*
- **FR-011**: The installed app MUST provide a way for users to discover the current version and learn about newer versions (either in-app update prompt or a visible version label with a link to the download page).
- **FR-012**: The installed app MUST be removable via the host OS's normal uninstall mechanism, and uninstalling MUST NOT delete the user's library or cached analyses unless the user explicitly opts in.
- **FR-013**: The system MUST ship a macOS application bundle as the v1 target, covering both Apple Silicon and Intel machines (either via a universal binary or separate downloads). Windows and Linux are explicitly out of scope for v1 and will be revisited based on user demand.
- **FR-014**: The installer MUST include a complete, self-contained Python analysis runtime — interpreter plus every native dependency required for the default analyze → review → generate workflow (including but not limited to vamp, Vamp plugin binaries, madmom, librosa, numpy, torch, and ffmpeg). After install, the default workflow MUST run fully offline with no additional downloads. Users MUST NOT be required to install Python, pip packages, or any system audio libraries themselves.
- **FR-015**: Large machine-learning model weights used only for stem separation (demucs `htdemucs_6s` and similar) MAY be downloaded on first use rather than bundled in the installer, provided that: (a) the download is triggered only when the user first invokes a feature that requires the weights, (b) progress is visible with an explicit user confirmation before the download begins, (c) the download location is reused across app updates so users do not re-download on every upgrade, and (d) the absence of weights never blocks the non-stem-separation workflow.

### Key Entities

- **Packaged application**: The installable artifact per OS. Contains the frontend UI, a mechanism to run the analysis backend, and any bundled assets. Versioned; signed for distribution.
- **User data directory**: OS-appropriate per-user location holding the library index, analysis cache references, custom themes, section edits, and preferences. Must survive app upgrades and normal uninstalls.
- **Bundled / sidecar backend runtime**: Whatever mechanism runs the existing Python analysis pipeline inside the packaged app — interpreter, dependencies, and native binaries. The frontend interacts with it the same way it currently interacts with the local backend server.
- **Native file associations**: OS-level registrations that let the app handle audio file drops and (optionally) sequence file double-clicks.

## Assumptions

- The existing React/Vite frontend and the existing Flask backend remain the source of truth for UI and analysis logic. Packaging wraps them; it does not rewrite them.
- macOS is the only v1 target. Owner develops on macOS and cannot realistically test Windows or Linux. Cross-platform support is deferred to a future release driven by actual user demand, not speculation.
- The v1 macOS build must cover both Apple Silicon and Intel — Intel Macs (roughly 2019–2020 vintage) are still in active use and Rosetta is not an acceptable performance fallback for a heavy audio/ML workload.
- The installer is expected to be in the several-hundred-MB to ~1 GB range with the bundled Python runtime + Vamp plugins + ffmpeg + torch (CPU) but *without* stem-separation model weights. This is a deliberate tradeoff in favor of a reasonable installer size and first-launch experience for the common path.
- Stem separation is a secondary workflow, not the primary one. It is acceptable for it to require a one-time download of model weights on first invocation, as long as the core analyze → review → generate flow is fully offline from install onward.
- Existing on-disk conventions (`~/.xlight/library.json`, `~/.xlight/custom_themes/`, `.stems/<hash>/` co-located with audio files) are preserved. Paths adapt to each OS's home directory convention but semantics stay the same.
- Auto-update infrastructure (signing keys, update server) is not yet in place. P3 auto-update may be deferred to a follow-up feature; a visible version label with a manual download link is acceptable for v1.
- The analysis pipeline's native dependencies (ffmpeg, Vamp plugin `.so`/`.dll`/`.dylib` files, madmom C extensions, demucs/torch) are the hard part of packaging. Whatever approach is chosen must solve them, not sidestep them.
- Only one packaged app instance is expected to run per user at a time. Multi-instance support is out of scope.
- The existing xLights-related CLI commands (`xlight-check`, render flows, etc.) remain developer-only tools; they are not part of the packaged product unless the user explicitly includes them later.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A non-technical user, given only the installer file, can install the app and reach the upload screen in under 5 minutes on a typical consumer machine, without reading documentation and without using a terminal.
- **SC-002**: For a 3-minute audio file on a typical consumer machine, the end-to-end flow (drop file → analyze → view timeline → generate sequence → save `.xsq`) inside the packaged app completes within the same time envelope as the current dev-mode workflow, with no more than a 15% slowdown attributable to packaging overhead.
- **SC-003**: 100% of analysis outputs (timing tracks, sections, themes, sequences) produced by the packaged app match the outputs produced by the current dev-mode workflow for the same input — byte-for-byte where the format is deterministic and structurally where it is not.
- **SC-004**: The packaged app launches from cold start in under 5 seconds after the first launch on a typical consumer machine (first launch may take longer if bundled assets need extraction).
- **SC-005**: Installing, launching, running the canonical workflow, and uninstalling the packaged app on a fresh machine (no Python, no Node, no dev tools) succeeds with zero additional manual steps on each supported OS.
- **SC-006**: Library data, custom themes, and section edits from version N are visible and usable in version N+1 after upgrade — zero data loss across supported-version upgrades.
- **SC-007**: The installer passes the host OS's default security checks (macOS Gatekeeper, Windows SmartScreen) without requiring the user to manually override warnings — or, if this cannot be achieved for the initial release, the workaround is documented clearly enough that a non-technical user can follow it in under 2 minutes.
