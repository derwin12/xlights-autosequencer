# Quickstart: Devcontainer Path Resolution

**Feature**: 023-devcontainer-path-resolution

## What This Feature Does

Ensures audio files, analysis caches, and stem files work seamlessly when switching between the dev container and local host. Paths are stored in a portable format so analysis done in one environment is reusable in the other.

## Key Files

| File | Role |
|------|------|
| `src/paths.py` | **NEW** — PathContext: environment detection, path mapping, relative path helpers |
| `src/library.py` | **MODIFIED** — adds relative path fields, deduplicates by hash |
| `src/analyzer/orchestrator.py` | **MODIFIED** — stores relative path in HierarchyResult |
| `src/analyzer/stems.py` | **MODIFIED** — stores relative path in stem manifest |
| `src/cache.py` | **MODIFIED** — uses PathContext for path suggestions on cache miss |
| `tests/unit/test_paths.py` | **NEW** — PathContext unit tests |

## How It Works

1. **At startup**, `PathContext` checks for `XLIGHTS_HOST_SHOW_DIR` env var to detect container vs host.
2. **On write**, analysis results, library entries, and stem manifests store a `relative_source_file` alongside the existing absolute path.
3. **On read**, if the absolute path doesn't exist, the system tries the relative path resolved against the current environment's show directory.
4. **On error**, if a user provides a path that doesn't exist but matches a known cross-environment pattern, the error message suggests the correct path.

## Testing

```bash
# Run path resolution tests
pytest tests/unit/test_paths.py -v

# Run integration tests
pytest tests/integration/test_path_resolution.py -v
```

## Environment Variables

| Variable | Set By | Purpose |
|----------|--------|---------|
| `XLIGHTS_HOST_SHOW_DIR` | devcontainer.json | Host-side show directory path; presence indicates container environment |

No new environment variables are introduced. The feature uses the existing `XLIGHTS_HOST_SHOW_DIR` from `devcontainer.json`.
