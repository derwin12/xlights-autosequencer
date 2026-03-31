# Feature Specification: Devcontainer Path Resolution

**Feature Branch**: `023-devcontainer-path-resolution`
**Created**: 2026-03-30
**Status**: Draft
**Input**: User description: "Specification for how we handle working in a dev container versus local install. Solving pathing problems between host environment and dev container for analysis and MP3 files."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyze an MP3 from the Host xLights Directory (Priority: P1)

A user working inside the dev container wants to analyze an MP3 file that lives in their host machine's `~/xlights/` directory (mounted at `/home/node/xlights/` in the container). The system resolves the path correctly, runs analysis, and writes output files to a location accessible from both host and container without broken references.

**Why this priority**: This is the most common workflow — analyzing songs that are part of the user's xLights show directory. If paths break here, nothing else works.

**Independent Test**: Can be tested by running `xlight-analyze analyze /home/node/xlights/song.mp3` inside the container and verifying that the output JSON contains paths that resolve correctly from both the container and the host.

**Acceptance Scenarios**:

1. **Given** a user is inside the dev container and an MP3 exists at `~/xlights/show/song.mp3` on the host, **When** they run analysis on `/home/node/xlights/show/song.mp3`, **Then** the analysis completes and output files are written adjacent to the MP3 under the mounted path.
2. **Given** analysis output was generated inside the container, **When** the user opens the same xLights show directory on their host machine, **Then** the analysis JSON files are visible and contain paths that are valid from the host perspective (or are relative).
3. **Given** a user passes an absolute host-style path (e.g., `/Users/bob/xlights/song.mp3`) inside the container, **When** the system detects this path does not exist, **Then** it provides a clear error message suggesting the equivalent container path.

---

### User Story 2 - Load Previously Cached Analysis Across Environments (Priority: P1)

A user runs analysis locally (no container), then later opens the same project in the dev container (or vice versa). The system finds and reuses the cached analysis rather than re-analyzing, even though the absolute paths differ between environments.

**Why this priority**: Re-analysis is expensive (minutes per song). Cache invalidation due to path changes wastes time and confuses users who expect their previous work to be available.

**Independent Test**: Can be tested by generating analysis locally, then opening the container and requesting the same song — the system should find the cache hit via content hash, not absolute path.

**Acceptance Scenarios**:

1. **Given** analysis was previously run on the host machine for a song, **When** the user opens the dev container and requests analysis for the same song (same file content, different absolute path), **Then** the system recognizes the existing analysis via content hash and reuses it.
2. **Given** the analysis library index contains entries with host-absolute paths, **When** the library is loaded inside the container, **Then** entries with stale absolute paths are still locatable by falling back to content hash or relative path resolution.
3. **Given** a user switches between local and container workflows repeatedly, **When** they view the analysis library, **Then** they see a single entry per song (not duplicates from different environments).

---

### User Story 3 - Generate Sequences Referencing Correct Audio Paths (Priority: P2)

A user generates an xLights sequence (`.xsq`) inside the dev container. The sequence file must reference the audio file using a path that xLights on the host machine can resolve, since xLights runs natively on the host (not in the container).

**Why this priority**: Sequence generation is the end goal of the pipeline. If the generated `.xsq` references a container-internal path, xLights on the host cannot find the audio and the sequence is broken.

**Independent Test**: Can be tested by generating a sequence in the container, then opening it in xLights on the host and verifying audio playback works.

**Acceptance Scenarios**:

1. **Given** a user generates a sequence inside the container for a song in the mounted xLights directory, **When** the `.xsq` file is opened in xLights on the host, **Then** the audio path in the sequence resolves correctly and playback works.
2. **Given** a user generates a sequence for a song outside the mounted xLights directory, **When** the system writes the `.xsq`, **Then** it warns the user that the audio path may not resolve on the host and suggests copying the file into the xLights show directory.

---

### User Story 4 - Stem Cache Accessible Across Environments (Priority: P2)

A user runs stem separation (demucs) inside the container. The resulting stem WAV files in `.stems/<md5>/` must be accessible when the user later works locally or in a fresh container session.

**Why this priority**: Stem separation is the most expensive operation (10+ minutes per song). Losing the cache due to path issues forces costly re-computation.

**Independent Test**: Can be tested by running stem separation in the container, then verifying the stems are accessible from the host filesystem and from a fresh container session.

**Acceptance Scenarios**:

1. **Given** stems were separated inside the container for a song in the mounted directory, **When** the user accesses the same directory from the host or a new container, **Then** the stem files are found and reused.
2. **Given** stems exist in `.stems/<md5>/` adjacent to the source audio, **When** the system looks up stems, **Then** it matches by content hash (MD5) regardless of the absolute path used to reference the source file.

---

### User Story 5 - Local-Only Workflow Remains Unaffected (Priority: P3)

A user who never uses a dev container and runs everything locally should experience no changes or regressions. Path resolution should work exactly as it does today when no container is detected.

**Why this priority**: Not all users use dev containers. The local workflow must remain the default and must not be complicated by container-awareness logic.

**Independent Test**: Can be tested by running the full pipeline locally and verifying all paths resolve as they do today with no new environment variables or configuration required.

**Acceptance Scenarios**:

1. **Given** a user is running locally (no container), **When** they run any CLI command, **Then** all paths behave identically to the current implementation with no extra configuration needed.
2. **Given** no container environment variables are set, **When** path resolution runs, **Then** no container-specific logic is triggered and no warnings are emitted.

---

### Edge Cases

- When a user passes a path from outside any mounted volume (e.g., `/tmp/song.mp3` inside the container), analysis proceeds normally but the system warns that cross-environment cache sharing and XSQ host path resolution are unavailable for this file.
- How does the system handle symlinks that cross the container/host boundary?
- What happens when the xLights show directory mount is missing or misconfigured?
- What if the same song exists at different paths in both the mounted and non-mounted areas?
- How does the system behave when `~/.xlight/` is on a named Docker volume (not a bind mount) and thus not visible from the host?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect whether it is running inside a dev container or on the host, using reliable environment signals (e.g., presence of container environment variables or filesystem markers).
- **FR-002**: System MUST resolve audio file paths to canonical absolute paths within the current environment before any processing.
- **FR-003**: System MUST use content-based hashing (MD5 of file content) as the primary cache key for analysis results and stem files, not absolute file paths.
- **FR-004**: System MUST store relative paths (relative to the audio file or show directory) in analysis output JSON and library index entries alongside any absolute paths.
- **FR-005**: System MUST use paths relative to the show directory (not absolute paths) when referencing audio files in `.xsq` sequence files, so they resolve correctly on any host without path translation.
- **FR-006**: System MUST provide a clear error message when a user provides a path that does not exist in the current environment, suggesting the equivalent path if a known mount mapping applies.
- **FR-007**: System MUST NOT require any manual configuration to work in either environment — detection and path mapping should be automatic based on known mount points and environment variables.
- **FR-008**: System MUST deduplicate library index entries for the same song across environments, keyed by content hash rather than file path.
- **FR-009**: System MUST preserve backward compatibility — existing analysis caches and library entries generated before this feature must remain usable.
- **FR-010**: System MUST fall back gracefully when path translation is not possible (e.g., files outside known mount points), with a warning to the user rather than a crash.
- **FR-011**: System MUST allow analysis of audio files located outside the mounted show directory, but MUST emit a warning that cross-environment cache reuse and XSQ host path resolution are unavailable for those files.

### Key Entities

- **PathContext**: Represents the current runtime environment (container or host), known mount mappings, and environment variables used for path translation.
- **ContentHash**: The MD5 hash of a file's content, used as the environment-independent identifier for audio files and their associated caches (analysis, stems, story).
- **MountMapping**: A mapping between a container path prefix and its corresponding host path prefix (e.g., `/home/node/xlights/` maps to the host's xLights show directory).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can analyze a song in the dev container and access the analysis results from the host without any manual path editing.
- **SC-002**: Cached analysis and stem files are reused when switching between container and local workflows for the same song, with zero re-computation.
- **SC-003**: Generated `.xsq` sequence files open correctly in host-native xLights with working audio playback on the first attempt.
- **SC-004**: The system correctly resolves paths in both environments without requiring any user-supplied configuration or environment variables beyond what the dev container already provides.
- **SC-005**: Local-only users experience no behavioral changes or new warnings after this feature is implemented.
- **SC-006**: Invalid cross-environment paths produce a helpful error message that includes the corrected path within 1 user action (no guessing required).

## Clarifications

### Session 2026-03-30

- Q: Which host operating systems must be supported for path translation? → A: macOS and Linux (both POSIX). Windows is out of scope.
- Q: What path format should .xsq files use to reference audio? → A: Relative to the show directory (e.g., `music/song.mp3`). No host path translation needed in sequence output.
- Q: Should analysis work for files outside the mounted show directory? → A: Yes, but warn that cache sharing and XSQ host paths won't work for unmounted paths.

## Assumptions

- The dev container configuration (`devcontainer.json`) defines the canonical mount points and environment variables (`XLIGHTS_HOST_SHOW_DIR`, `XLIGHTS_HOST_USER`). These are the authoritative source for path mappings.
- The xLights show directory is always bind-mounted at `/home/node/xlights/` inside the container. This is the primary location for audio files and analysis output.
- The `~/.xlight/` configuration directory inside the container lives on a named Docker volume and is NOT directly accessible from the host. Persistent user-facing output should go in the show directory, not `~/.xlight/`.
- Content hashing (MD5) is already used for stem caching and can be extended to analysis caching without conflict.
- xLights on the host is the only consumer of `.xsq` files — the container never runs xLights directly (arm64 uses SSH to host, amd64 uses xvfb but still references host paths).
- Supported host operating systems are macOS and Linux (both POSIX). Windows host environments are out of scope.
