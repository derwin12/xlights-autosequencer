# Design: custom layout upload and grouped export

## Goal

Let a user point xOnset at their own `xlights_rgbeffects.xml` without
editing the repo checkout, and make the Export download bundle a layout
file that's actually consistent with what the generated `.xsq` references.

## Approach

### Active-layout resolution (`src/review/api/v1/layout.py`)

`get_committed_layout()` becomes `get_active_layout()`. Resolution order:

```python
def _active_layout_xml_path():
    uploaded = get_uploaded_layout_xml_path()
    if uploaded.exists():
        return uploaded
    return get_committed_layout_xml_path()
```

The module-level cache (`_active_layout_cache`, unchanged mechanism) is now
invalidated explicitly by the upload/delete routes, rather than relying on
"only changes via a repo checkout + server restart" — the whole point is
that it changes at runtime now.

New path helpers in `src/paths.py`:

```python
def get_uploaded_layout_dir() -> Path:
    override = os.environ.get("XLIGHT_STATE_HOME")
    if override:
        return Path(override) / "layout"
    return Path.home() / ".xlight" / "layout"

def get_uploaded_layout_xml_path() -> Path:
    return get_uploaded_layout_dir() / "xlights_rgbeffects.xml"

def get_uploaded_networks_xml_path() -> Path:
    return get_uploaded_layout_dir() / "xlights_networks.xml"
```

Honoring `XLIGHT_STATE_HOME` matches the existing convention in
`src/settings.py`'s `_settings_path()` and `src/review/storage/paths.py` —
tests set this env var per-test via `monkeypatch` (see
`tests/review/conftest.py`), so uploads in tests never touch a real
`~/.xlight/`.

### Upload/delete routes

```python
@api_v1.route("/layout", methods=["POST"])
def upload_layout():
    upload = request.files.get("rgbeffects")
    # ... validate: file present, parses as XML, has >=1 <model> element
    # ... save to get_uploaded_layout_xml_path() (+ optional networks file)
    _invalidate_active_layout_cache()
    return jsonify(get_active_layout()), 200

@api_v1.route("/layout", methods=["DELETE"])
def delete_uploaded_layout():
    # ... unlink uploaded files if present
    _invalidate_active_layout_cache()
    return jsonify(get_active_layout() or {"layout": None}), 200
```

Only three call sites in `src/review/api/v1/export.py` needed updating
(`start_export`, `download_export_package`, `export_mapping`) — all were
already calling `get_committed_layout()` as an isolated import, not
threading a layout reference through multiple layers. No changes needed
in `src/generator/` at all: `run_generator(layout_path=...)` already takes
a plain path parameter (`src/evaluation/generator_runner.py:26`), so
"which file is active" is entirely decided before generation starts.

### Grouped export (`src/review/api/v1/export.py`)

```python
def _grouped_layout_copy(source_path: Path, dest_path: Path) -> int:
    try:
        layout_obj = parse_layout(source_path)
        normalize_coords(layout_obj.props)
        classify_props(layout_obj.props)
        groups = generate_groups(layout_obj.props)
        inject_groups(layout_obj.raw_tree, groups)
        write_layout(layout_obj, dest_path)
        return len(groups)
    except Exception:
        return 0
```

Same five-step pipeline `xlight-analyze group-layout` runs
(`src/cli_old.py:1745-1789`), just against a scratch temp path instead of
the source file in place — an export must never mutate the layout on disk
(uploaded or committed), only bundle a grouped copy. `download_export_package`
zips `layout_to_bundle` (the grouped copy if injection succeeded, else the
original) under the same arcname (`xlights_rgbeffects.xml`) so the zip
structure is unchanged either way.

Failure is swallowed to `0` groups rather than raising: an export the user
already waited on to render shouldn't fail at the very last step over a
grouping edge case in their particular layout — worst case they get the
pre-existing (already broken) behavior, not a new failure mode.

### Frontend (`Export.tsx`, new `LayoutUpload` component)

`LayoutUpload` (`src/review/frontend/src/components/LayoutUpload/`) is a
small self-contained form: two file inputs (rgbeffects required, networks
optional), an upload button, and — when `showRemove` is passed — a revert
button. It owns its own `uploading`/`error` state and calls
`onLayoutChange(layout | null)` on success, matching the existing
`PasteLyricsDialog` component's shape (fetch + JSON error handling, no
external state management library).

`Export.tsx` renders it two ways:
- Full form (with explanatory copy) in place of the old static "Layout
  Missing" text, when `!hasLayout`.
- Compact form (just the inputs + buttons) under the existing
  `layout-summary` block, so a layout can be replaced without first
  hitting the missing-state.

`onLayoutChange` bubbles up through a new optional `Export` prop of the
same name to `App.tsx`, which updates the same lifted `layoutId`/
`layoutXmlPath` state it already sets from the mount-time `GET /api/v1/layout`
fetch — no new state shape, just a second place that can set it.

## Non-goals (see proposal.md's "What Does NOT Change")

- Per-song layouts (would need a `Library`/`LibraryEntry` schema change —
  out of scope here).
- Changing what `generate_groups` classifies as a Power Group, or the tier
  scheme itself.
- Touching `src/cli_old.py`'s `group-layout` command or its tests — the
  export path now runs the same pipeline independently, not by refactoring
  the CLI command into a shared helper. Smaller diff, and the CLI command's
  own tests stay untouched.
