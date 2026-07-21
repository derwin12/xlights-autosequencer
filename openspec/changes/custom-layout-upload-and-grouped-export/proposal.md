# Proposal: custom layout upload and grouped export

## Why

xOnset currently reads exactly one layout — `layout/xlights_rgbeffects.xml`,
committed to the repo checkout. `src/review/api/v1/layout.py`'s own module
docstring says it plainly: "there is no per-session upload/replace; every
song exports against this one layout." A test even asserts the absence of
an upload route (`tests/review/test_api_layout.py::test_no_upload_endpoint`).

In practice this means every user who wants to sequence their own show has
to either fork the repo to swap in their own layout file, or edit the
checkout directly on whatever machine is running the container. Neither is
what a "drop a song in and get a sequence out" tool should require.

Separately, and independently discovered while working around the first
problem: the Export screen's download package is internally inconsistent.
The generator places effects against synthetic Power Groups — tier-prefixed
names like `06_PROP_Arch`, `08_HERO_X` (see `docs/xlight-grouping-design.md`)
— that only mean something in xLights once they exist as real `<modelGroup>`
elements. That injection step exists (`src/grouper/writer.py:inject_groups`)
and is exercised by the `xlight-analyze group-layout` CLI command
(`src/cli_old.py`), but `src/review/api/v1/export.py`'s
`download_export_package` never calls it — it zips the raw, ungrouped layout
file straight off disk. The result: a downloaded `.xsq` whose group-targeted
effects have nothing to attach to when imported into xLights, and no error,
warning, or log line anywhere that tells the user why. Discovered by manually
tracing through the export code after a real import produced no visible
change in xLights — group-targeted effects were silently no-ops.

## What Changes

### 1. Layout is now user-replaceable, not fixed

- `GET /api/v1/layout` — unchanged response shape, but now resolves to an
  uploaded override if one exists, else falls back to the repo-committed
  file (same behavior as before when nothing's been uploaded).
- `POST /api/v1/layout` (new) — accepts a multipart upload of
  `xlights_rgbeffects.xml` (required) and `xlights_networks.xml`
  (optional). Validated as parseable XML with at least one `<model>`
  element before being accepted; a bad upload returns 400 and never
  becomes active.
- `DELETE /api/v1/layout` (new) — removes the uploaded override, reverting
  to the committed file.
- Storage: `~/.xlight/layout/` — outside the git checkout, so an upload
  survives `git pull` and doesn't need write access to the repo. Same
  `XLIGHT_STATE_HOME`-honoring convention as `src/settings.py` and
  `src/review/storage/paths.py`, for test isolation.
- Frontend: a new `LayoutUpload` component appears in place of the old
  "Layout Missing — add it to the repo and restart" message when no
  layout is active, and as a compact "replace / revert to repo default"
  control alongside the existing layout summary on the Export screen.

This removes `tests/review/test_api_layout.py::test_no_upload_endpoint` —
deliberately reversing what it asserted. That test encoded the old
"fixed, single layout" design decision directly; once the decision changes,
the test asserting its absence has to go with it.

### 2. Export ships a layout that's actually consistent with its `.xsq`

- `download_export_package` now runs the same parse → normalize →
  classify → `generate_groups` → `inject_groups` → `write_layout`
  pipeline `group-layout` already runs, against a scratch copy of the
  active layout (the source file on disk — repo-committed or uploaded —
  is never mutated by an export). The bundled `xlights_rgbeffects.xml` is
  the grouped copy, not the raw source.
- If grouping fails for any reason, the export falls back to the raw
  layout rather than failing the whole export — a failed injection
  shouldn't block getting the `.xsq` at all, it just means the auto-groups
  are missing (same behavior as before this change).
- A `X-Groups-Injected` response header reports how many groups were
  added, and the Export screen shows a permanent note next to the
  Download Package button explaining that the bundle includes an updated
  layout file that needs to replace the user's own before opening the
  sequence — turning a silent gap into an explicit, visible step.

## What Does NOT Change

- The Power Groups scheme itself (8 tiers, `AUTO_PREFIXES`, `generate_groups`'
  classification logic) — untouched. This proposal only wires existing,
  tested machinery into the export path; it doesn't change what groups get
  generated or how.
- `xlight-analyze group-layout` (the CLI command) — still works exactly as
  before, in-place on a user-specified file. Not superseded by this change;
  it's still the right tool for permanently updating a show's own
  `xlights_rgbeffects.xml` outside the web UI.
- Per-song layouts. This is one active layout at a time (upload replaces
  it globally, same scope as the committed-file model it replaces) — not a
  layout picker per song. A genuinely per-song layout would need threading
  a layout reference through `Library`/`LibraryEntry` (see design.md), which
  is a bigger change than what's needed to fix the two problems above.
- `src/settings.py`'s existing `~/.xlight/settings.json` `layout_path` —
  that's a separate, installation-wide setting consumed by the CLI/
  `generator_runner`'s fallback path when no `layout_path` is passed
  explicitly. The web app's active-layout resolution (this change) and the
  CLI's settings-based fallback remain two independent paths, as they were
  before.

## Validation

- Backend: `tests/review/test_api_layout.py` rewritten (upload success/
  validation-failure cases, delete-reverts, delete-is-noop-when-nothing-
  uploaded) instead of asserting the route's absence. `tests/review/
  test_api_export.py` gains
  `test_download_package_injects_power_groups`, which imports/analyzes/
  themes a song end-to-end through the test client, downloads the
  package, and asserts the bundled `xlights_rgbeffects.xml` actually
  contains `<modelGroup>` elements with tier-prefixed names — a direct
  regression test for the bug this change fixes.
- Full existing suite re-run clean: `tests/review/`, `tests/unit/
  test_grouper_writer.py`, `tests/unit/test_grouper_groups.py` — 320
  passed, 1 pre-existing unrelated failure in `test_api_analysis.py`
  (confirmed pre-existing by reproducing on unmodified `main`, untouched
  by this change), 1 pre-existing skip.
- Frontend: `npm run build` (the actual production build, per README)
  succeeds. `tests/screens/Export.test.tsx` — 5 passed + 1 new passing
  test, 1 pre-existing unrelated failure (also reproduced on unmodified
  `main` — a stale `/render/i` button-name query against a button that's
  said "Generate Sequence" for a while now).
- Not run: the Playwright golden-screenshot suite
  (`tests/ui/flows/test_export_flow.py`) — it asserts on a set of
  `data-testid`s that are all preserved by this change (`layout-required`,
  `export-form`, etc.), but its golden screenshot for the "no layout"
  state will need regenerating since that block's content changed
  (upload form instead of static text). Flagging honestly rather than
  claiming full UI-suite coverage.
