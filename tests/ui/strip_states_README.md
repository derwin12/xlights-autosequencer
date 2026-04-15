# Spec 045 Acceptance Oracle — Workflow Strip & Detail Panel

This document is the static acceptance oracle for the Phase 1 wayfinding work
in spec 045. Each fixture entry in `strip_states.json` is rendered by
`applyStripState(entry)` in `src/review/static/dashboard.js`. The tables
below describe the expected `data-state` attribute per step and the expected
badge/banner/overflow behavior. Reviewers confirm manually via
`quickstart.md`; a future JS runner can automate against the same oracle.

The per-song workflow strip has 4 steps (FR-006 removed the Layout step):

| Idx | `data-step` | Label           |
| --- | ----------- | --------------- |
| 1   | `upload`    | Upload          |
| 2   | `review`    | Review          |
| 3   | `story`     | Story           |
| 4   | `generate`  | Generate        |

The `data-state` vocabulary is `complete | active | incomplete | blocked`.
When no row is expanded the strip renders with `data-state="neutral"` on
every step (all grey).

## Strip state per fixture (US1)

| Fixture                              | Step 1 (upload) | Step 2 (review) | Step 3 (story) | Step 4 (generate) |
| ------------------------------------ | --------------- | --------------- | -------------- | ----------------- |
| `fresh_upload_no_analysis`           | incomplete      | incomplete      | incomplete     | incomplete        |
| `analyzed_no_story_layout_ok`        | complete        | complete        | active         | incomplete        |
| `analyzed_with_story_never_generated`| complete        | complete        | complete       | active            |
| `fully_generated`                    | complete        | complete        | complete       | complete          |
| `layout_missing_blocks_generate`     | complete        | complete        | complete       | blocked           |

## Banner visibility & Generate-control disabled state per fixture (US2)

The Zone A setup banner is driven by the global `layout_configured` field
(same on every entry). The same field drives
`document.body.dataset.layoutConfigured`, which CSS uses to visually disable
every Generate control (strip step 4 + overflow-menu `[data-action="generate"]`).

| Fixture                              | Banner visible? | Body attr                     | Generate disabled? |
| ------------------------------------ | --------------- | ----------------------------- | ------------------ |
| `fresh_upload_no_analysis`           | No              | `layoutConfigured="true"`     | No                 |
| `analyzed_no_story_layout_ok`        | No              | `layoutConfigured="true"`     | No                 |
| `analyzed_with_story_never_generated`| No              | `layoutConfigured="true"`     | No                 |
| `fully_generated`                    | No              | `layoutConfigured="true"`     | No                 |
| `layout_missing_blocks_generate`     | Yes             | `layoutConfigured="false"`    | Yes                |

When the banner is visible, hovering a Generate control must surface a
tooltip referencing the banner instruction (FR-005).

## Detail panel structure (US3)

The detail-template must render exactly one `data-action="open"` primary
button and exactly one `.overflow-menu` element. The overflow menu contains
exactly 6 `role="menuitem"` children with `data-action` values in this order:

1. `preview`  (Preview Generation)
2. `story`    (Story Review)
3. `phonemes` (Phonemes)
4. `generate` (Generate Sequence)
5. `reanalyze` (Re-analyze)
6. `delete`   (Delete)

The canonical primary-action helper is `openSong(hash)` — spec 046 will
retarget it from `/timeline?hash=<hash>` to `/song/<hash>` in this single
place (SC-004, SC-008). Verify exactly one canonical definition exists:

```bash
grep -nE '^\s*function openSong\(' src/review/static/dashboard.js
# must return exactly one line matching `function openSong(hash) {`
```

The sibling helper `openSongTool(hash, tool, storyPath)` is deliberately
named differently so it is trivial to distinguish by regex — spec 046 does
not retarget it.

## Lifecycle badges (US4)

Per FR-011, the Phase 1 vocabulary is `Analyzed | Generated | Stale`. The
token `Briefed` is reserved but MUST NOT appear anywhere in dashboard.js or
the rendered page. `grep 'Briefed' src/review/static/dashboard.js` must
return no matches.

Replacement rules (only one lifecycle badge shown per row):

- `Stale` replaces both `Analyzed` and `Generated` (source file hash differs
  from library index entry).
- `Generated` replaces `Analyzed` (completed generation exists for this
  source hash).
- `Analyzed` shown when analysis artifact exists and the row is neither
  `Generated` nor `Stale`.

| Fixture                              | Lifecycle badge |
| ------------------------------------ | --------------- |
| `fresh_upload_no_analysis`           | (none)          |
| `analyzed_no_story_layout_ok`        | Analyzed        |
| `analyzed_with_story_never_generated`| Analyzed        |
| `fully_generated`                    | Generated       |
| `layout_missing_blocks_generate`     | Analyzed        |

A stale fixture (`is_stale: true` on top of any analyzed/generated row)
replaces the badge with `Stale`.

## Route reachability (US5 — SC-005)

Every route reachable today must continue to return 200 OK:

- `/timeline`
- `/story-review`
- `/phonemes-view`
- `/grouper`
- `/themes/`
- `/variants/`

Curl walk:

```bash
for path in /timeline /story-review /phonemes-view /grouper /themes/ /variants/; do
  curl -sI "http://localhost:5173$path" | head -1
done
```

Each deep page must expose a "Back to Library" affordance via `navbar.js`
whose anchor links to `/`.
