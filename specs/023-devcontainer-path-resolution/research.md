# Research: Devcontainer Path Resolution

**Feature**: 023-devcontainer-path-resolution
**Date**: 2026-03-30

## R1: How to Detect Devcontainer Environment

**Decision**: Check for the `XLIGHTS_HOST_SHOW_DIR` environment variable. If set, the process is running inside the devcontainer.

**Rationale**: This env var is already defined in `devcontainer.json` (`containerEnv` section) and is specific to this project. It's more reliable than generic signals like checking for `/.dockerenv` because it also carries the host path needed for mapping. Falls back cleanly: if the var is unset, assume host/local environment.

**Alternatives considered**:
- Check for `/.dockerenv` file — generic, doesn't provide host path info, could false-positive in non-devcontainer Docker usage.
- Check `REMOTE_CONTAINERS` or `CODESPACES` env vars — VS Code-specific, not guaranteed across all devcontainer runtimes.
- Read `devcontainer.json` at runtime — fragile, file may not be at a known path from inside the container.

## R2: What Paths Need Translation

**Decision**: Only one mount mapping needs translation:
- Container: `/home/node/xlights/` ↔ Host: `$XLIGHTS_HOST_SHOW_DIR/`

The workspace mount (`/workspace`) is the project source code, not user data — paths within it are not stored in analysis output.

**Rationale**: Analysis of the codebase shows that all user-facing persistent paths (analysis JSON, library entries, stem manifests) reference files in the xLights show directory. The `~/.xlight/` directory is on a named Docker volume (not bind-mounted) and should not contain cross-environment references.

**Alternatives considered**:
- Map all mounts generically — over-engineered; only one mount carries user audio data.
- Map `~/.xlight/` too — it's a named volume, not visible from the host, so mapping is impossible.

## R3: Relative Path Strategy

**Decision**: Store paths relative to the audio file's parent directory. For library index entries, store paths relative to the show directory root (the mount point).

**Rationale**: Adjacent-file relative paths (e.g., `./song/song_hierarchy.json` relative to `song.mp3`) are already the natural output layout. The show directory relative path (e.g., `2024/Christmas/song.mp3`) is stable across environments because the mount point maps the same directory tree.

**Alternatives considered**:
- Store only absolute paths with translation on load — fragile, requires translation everywhere paths are read.
- Store only relative paths — breaks backward compatibility; existing analysis JSON has absolute paths.
- Store both absolute and relative — chosen approach. Absolute path is for current-session convenience; relative path is the durable cross-environment reference.

## R4: Backward Compatibility for Existing Analysis Cache

**Decision**: On load, if a relative path field is missing (pre-023 JSON), fall back to the absolute path. If the absolute path doesn't resolve, attempt to find the analysis by content hash via the library index. No migration of existing files.

**Rationale**: Existing analysis JSON files use absolute paths and have `source_hash` fields. The MD5-based cache lookup (`AnalysisCache.is_valid()` in `src/cache.py`) already validates by hash, not path. Adding a relative path field to new writes is additive and non-breaking.

**Alternatives considered**:
- Run a migration script to add relative paths to all existing JSON — disruptive, touches user data files without user action.
- Require re-analysis — unacceptable; stem separation alone takes 10+ minutes per song.

## R5: Library Deduplication Strategy

**Decision**: Key library entries by `source_hash`. On `upsert()`, if an entry with the same hash exists, update the path fields rather than creating a duplicate. Add `relative_source_file` and `relative_analysis_path` fields.

**Rationale**: `Library.find_by_hash()` already exists and is used for lookups. The duplication problem only occurs when the same file is accessed via different absolute paths (container vs host). Keying by hash naturally deduplicates.

**Alternatives considered**:
- Key by filename — collisions (multiple songs named `song.mp3`).
- Key by relative path — requires knowing the show directory root, which may not always be determinable.
- Periodic dedup pass — reactive rather than preventive; user sees duplicates until cleanup runs.

## R6: Error Message for Cross-Environment Paths

**Decision**: When a path doesn't exist and matches a known cross-environment pattern (e.g., starts with `/Users/` inside the container, or starts with `/home/node/xlights/` on the host), suggest the mapped equivalent path in the error message.

**Rationale**: The most common mistake is copy-pasting a host path into the container terminal. A targeted suggestion is more useful than a generic "file not found" error.

**Alternatives considered**:
- Auto-translate the path silently — risky; could mask genuine missing-file errors.
- Generic "file not found" with no suggestion — unhelpful for the specific devcontainer use case.
