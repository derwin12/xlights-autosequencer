# Data Model: Devcontainer Path Resolution

**Feature**: 023-devcontainer-path-resolution
**Date**: 2026-03-30

## Entities

### PathContext

Runtime singleton that encapsulates environment detection and path mapping.

| Field | Type | Description |
|-------|------|-------------|
| in_container | bool | True if running inside the devcontainer |
| container_show_dir | str or None | Container-side mount path (`/home/node/xlights`), None if not in container |
| host_show_dir | str or None | Host-side show dir from `XLIGHTS_HOST_SHOW_DIR` env var, None if not in container |

**Behavior**:
- `is_in_show_dir(path) -> bool`: Returns True if the given path is under the show directory (container or host side, depending on environment).
- `to_relative(path) -> str or None`: Converts an absolute path to a show-directory-relative path. Returns None if the path is outside the show directory.
- `to_absolute(relative_path) -> str`: Converts a show-directory-relative path to an absolute path in the current environment.
- `suggest_path(missing_path) -> str or None`: If the path matches a known cross-environment prefix, returns the equivalent path for the current environment. Returns None if no mapping applies.

**Lifecycle**: Created once at CLI startup. Immutable after creation.

### LibraryEntry (modified)

Existing entity with two new fields:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| source_hash | str | existing | MD5 of audio file content (primary key) |
| source_file | str | existing | Absolute path to audio file |
| filename | str | existing | Basename of audio file |
| analysis_path | str | existing | Absolute path to analysis JSON |
| relative_source_file | str or None | **new** | Path relative to show directory |
| relative_analysis_path | str or None | **new** | Path relative to show directory |
| duration_ms | int | existing | Duration in milliseconds |
| estimated_tempo_bpm | float | existing | Estimated tempo |
| track_count | int | existing | Number of timing tracks |

**Identity rule**: Entries are uniquely identified by `source_hash`. On upsert, if a matching hash exists, the entry is updated (not duplicated).

**Backward compatibility**: `relative_source_file` and `relative_analysis_path` are nullable. Pre-023 entries loaded from JSON will have these as None. The system falls back to absolute paths when relative paths are absent.

### HierarchyResult (modified)

Existing entity with one new field:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| source_file | str | existing | Absolute path to source audio |
| source_hash | str | existing | MD5 of source audio content |
| relative_source_file | str or None | **new** | Path relative to show directory |

**Backward compatibility**: Nullable. Older JSON files without this field load normally.

### StemManifest (modified)

Existing JSON manifest with one new field:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| source_hash | str | existing | MD5 of source audio (cache key) |
| source_path | str | existing | Absolute path to source audio |
| relative_source_path | str or None | **new** | Path relative to show directory |
| model | str | existing | Demucs model name |
| stems | list[str] | existing | List of stem names |

**Backward compatibility**: Nullable. Stem cache validity is determined by `source_hash`, not paths.

## Relationships

```
PathContext (singleton)
    ├── used by → LibraryEntry (path translation on read/write)
    ├── used by → HierarchyResult (relative path generation on write)
    ├── used by → StemManifest (relative path generation on write)
    └── used by → CLI error handler (path suggestion on file-not-found)
```

## Validation Rules

- `source_hash` must be a 32-character hex string (MD5).
- `relative_source_file` must not start with `/` (must be relative).
- `relative_source_file` must not contain `..` components (must stay within show dir).
- `container_show_dir` is always `/home/node/xlights` when in container.
- `host_show_dir` comes from `XLIGHTS_HOST_SHOW_DIR` env var; if the var is set but empty, treat as not-in-container.
