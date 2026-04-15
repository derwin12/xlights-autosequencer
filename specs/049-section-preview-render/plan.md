# Implementation Plan: Section Preview Render

**Branch**: `049-section-preview-render` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/049-section-preview-render/spec.md`

## Summary

Adds a short-section preview render to the Preview tab of the per-song workspace.
A single **Preview** click runs the real generator (`build_plan` → `place_effects` →
`write_xsq`) scoped to one 10–20s section and returns a downloadable `.xsq` that
references the original MP3 with a time offset — no audio re-encoding, no clipped
media files. The preview uses the live (possibly unsaved) Brief so users can evaluate
Brief tweaks in seconds instead of waiting for a full-song render.

**This is the highest-impact, highest-effort phase of the web-UI UX overhaul.** Every
earlier phase (wayfinding, workspace shell, Brief, decision-ordering) is primarily UI
plumbing. Phase 5 introduces new rendering behavior, a new async job surface, and
cancellation semantics on an in-process thread-based job runner. The Technical Context
below calls out the three risk areas explicitly.

Key design decisions (confirmed by spec clarifications):

- **Scoped-full-path, not a parallel pipeline.** First implementation runs `build_plan`
  end-to-end against the full song, then filters `SectionAssignment` to the target
  index before placement and serialization. A clean `section_filter: int | None`
  parameter on `build_plan` is a follow-up after spec 048 lands.
- **Supersede concurrency.** A new Preview request for the same song cancels any
  in-flight job. Never queue, never parallel. Cancellation uses a
  `threading.Event` cooperatively polled at pipeline stage boundaries; the legacy
  `Thread` is abandoned (not joined) and its artifact is discarded.
- **MP3-reference-with-offset audio.** Preview `.xsq` points at the original MP3
  path with `start_offset_ms` = section start and sequence duration = previewed
  window. `write_xsq` gains optional `scoped_duration_ms` and `audio_offset_ms`
  parameters.
- **In-browser visualization (US5) is deferred.** P3 stretch in the spec; not
  attempted in first implementation.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend)
**Primary Dependencies**: Flask 3+ (existing), click 8+ (existing), existing
generator pipeline (`src/generator/plan.py`, `src/generator/xsq_writer.py`). No new deps.
**Storage**: In-memory `_preview_jobs` dict + `tempfile.mkdtemp(prefix="xlight_preview_")`
for `.xsq` artifacts. Bounded in-memory LRU cache keyed by
`(song_hash, section_index, brief_hash)`.
**Testing**: pytest — new unit tests for picker and job lifecycle, one integration
test end-to-end.
**Target Platform**: Linux devcontainer / macOS host (Flask dev server).
**Project Type**: Web (backend Flask + JS frontend).
**Performance Goals**: POST-to-`done` ≤ 10s wall-clock for a typical 3-minute song
on the reference hardware (SC-001). Representative-section picker must be pure and
unit-testable (no I/O).
**Constraints**:
- MUST NOT pollute the full-render output directory (FR-010).
- MUST NOT leave the cancelled-job artifact visible to the user (FR-009).
- MUST NOT regress `/api/generation-preview/<hash>` (FR-014, SC-007).
**Scale/Scope**: One song at a time per preview request. Cache bounded to
~16 entries (LRU). Cancellation is per-song only.

**Three risk areas** flagged for extra care during implementation:

1. **Cancellation of an in-flight pipeline.** `build_plan` is not structured to
   check a cancel flag mid-iteration today. We introduce a small cooperative
   cancel hook (see Implementation Approach, Change 4) that is polled at four
   well-defined boundaries: before `select_themes`, between sections inside the
   `place_effects` loop, before `apply_transitions`, and before `write_xsq`. A
   cancelled job's thread is allowed to exit naturally (daemon=True); we do not
   hard-kill a Python thread. The superseded job is dropped from
   `_preview_jobs` the instant the new request arrives, so the UI never polls
   it again.
2. **XSQ writer offset support.** `write_xsq` currently computes
   `sequenceDuration` from `plan.song_profile.duration_ms` and assumes the
   effect timeline starts at 0. A scoped preview needs both a custom duration
   **and** all placements shifted so section start becomes t=0 in the output.
   The audio offset is conveyed via a new `audio_offset_ms` attribute in the
   XSQ `<head>` (xLights `mediaOffset` equivalent); we audit xLights compat
   in `research.md`.
3. **Representative-section picker correctness.** A bad default turns the
   feature into a novelty (SC-003). Separate `pick_representative_section`
   into a pure function over `list[SectionEnergy]` so the ranking rules are
   fully unit-testable against fixtures from the 5 reference songs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | ✅ PASS | Preview reuses the existing hierarchy analysis. No new audio ingest path. Audio authoritatively drives section boundaries; the only new thing is *which* section the preview covers. |
| II. xLights Compatibility | ✅ PASS | Preview artifact is the same `.xsq` schema full generation emits. Section-scoped `sequenceDuration` + `mediaOffset` are documented xLights 2024+ attributes (verified in research.md). |
| III. Modular Pipeline | ✅ PASS | New module `src/generator/preview.py` isolates preview-specific logic (picker, job runner, cancellation). `plan.py` and `xsq_writer.py` get additive parameters, not structural changes. Full-render path is unaffected. |
| IV. Test-First Development | ✅ PASS | Tests written first: `test_preview_section_picker.py` (ranking rules against fixture sections), `test_preview_job.py` (supersede cancellation, cache hit, failure surface), `test_section_preview.py` (end-to-end HTTP flow). All three fail before implementation; each drives exactly one change. |
| V. Simplicity First | ⚠️ JUSTIFY | Cooperative cancellation adds a `CancelToken` concept — the first non-trivial cross-module coordination primitive. Justification: the supersede clarification is a hard requirement, and a pure supersede without cancellation means the orphan job keeps burning CPU (~30s) and can race-overwrite the cache. A flag with four poll points is the minimum solution; anything less violates FR-009. |

No other violations. Complexity Tracking table below covers the cancel token.

### Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|------------|--------------------------------------|
| `CancelToken` (threading.Event wrapper) | FR-009 supersede semantics | Dropping the job from `_preview_jobs` without cancel lets the orphan thread keep computing for ~30s, racing with the new job on cache writes and wasting CPU. |
| `preview.py` as a new module | Keep preview behavior separate from full generation | Inlining into `plan.py` drifts preview behavior into every full-render codepath; the isolation guards against leaking preview-specific shortcuts. |

## Project Structure

### Documentation (this feature)

```text
specs/049-section-preview-render/
├── plan.md              # This file
├── research.md          # Phase 0 — cancellation strategy, XSQ offset audit, picker rationale
├── data-model.md        # Phase 1 — PreviewJob / PreviewRequest / PreviewResult / cache key
├── quickstart.md        # Phase 1 — verification walkthrough
└── tasks.md             # Phase 2 output (/speckit.tasks) — NOT written by this plan
```

### Source Code (affected files)

```text
src/
├── generator/
│   ├── preview.py              # NEW — pick_representative_section(), run_section_preview(),
│   │                           #       PreviewJob, CancelToken, _PreviewCache (LRU)
│   ├── plan.py                 # ADD optional section_filter param to build_plan() — follow-up
│   │                           #   after spec 048; first cut filters post-hoc in preview.py
│   └── xsq_writer.py           # ADD optional scoped_duration_ms + audio_offset_ms params;
│                               #   shift placement start/end when offset is set
│
└── review/
    ├── server.py               # REGISTER preview_bp
    ├── preview_routes.py       # NEW — POST /api/song/<hash>/preview (launch),
    │                           #       GET /api/song/<hash>/preview/<job_id> (status),
    │                           #       GET /api/song/<hash>/preview/<job_id>/download (artifact)
    └── static/
        ├── song-workspace.html # MODIFY — Preview-tab DOM (from spec 046): dropdown, button,
        │                       #   result pane, error pane, stale marker
        └── song-workspace.js   # MODIFY — Preview-tab handler: POST, poll, render result,
                                #   stale detection on Brief change

tests/
├── unit/
│   ├── test_preview_section_picker.py   # NEW — ranking rules from User Story 3
│   └── test_preview_job.py              # NEW — lifecycle, supersede cancel, cache hit
└── integration/
    └── test_section_preview.py          # NEW — POST → poll → download → validate .xsq
```

**Structure Decision**: New isolated preview module under `src/generator/preview.py`
plus a new Flask blueprint under `src/review/preview_routes.py` (mirrors the
`generate_routes.py` pattern from spec 034). `plan.py` and `xsq_writer.py` receive
small additive parameters only; no structural changes.

## Implementation Approach

### Change 1: Representative-Section Picker (`src/generator/preview.py`)

Pure function:

```python
def pick_representative_section(sections: list[SectionEnergy]) -> int:
    """Return index of the representative section per User Story 3 rules."""
```

Ranking rules (in order):

1. **Candidates**: sections with `duration >= 4000ms` AND `role not in {intro, outro}`.
2. **High-energy tier**: among candidates with `energy_score >= 50`, pick the one
   with the highest `energy_score`. On ties, prefer roles in
   `{chorus, drop, climax}`; further ties broken by earliest start.
3. **Longest fallback**: if no candidate has energy ≥ 50, return the longest
   candidate (by `end_ms - start_ms`).
4. **Degenerate fallback**: if no candidate exists (only intro/outro or all < 4s),
   return the first section with `duration >= 4000ms` regardless of role.
5. **Ultimate fallback**: if no section meets any criterion, return `0`.

All rules are covered by unit tests against fixture section lists derived from
five reference songs (verse-heavy, chorus-heavy, EDM, ballad, instrumental).

### Change 2: Cancellation Primitive (`src/generator/preview.py`)

```python
class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
    def cancel(self) -> None: self._event.set()
    def is_cancelled(self) -> bool: return self._event.is_set()
    def raise_if_cancelled(self) -> None:
        if self._event.is_set(): raise PreviewCancelled()
```

`PreviewCancelled` is a module-local exception, caught exactly in
`_run_preview` (the thread target). The token is polled at four boundaries
inside `run_section_preview`:

- after `build_plan` returns, before filtering to the target section;
- between sections in the `place_effects` loop (only meaningful if spec 048's
  `section_filter` lands; until then, the filter step is the only poll);
- before `apply_transitions`;
- before `write_xsq`.

Granularity is deliberately coarse — we do not poll inside tight inner loops
where the overhead would dominate. The worst-case "orphan work" between poll
points is one `place_effects` call (~1–3s), which is acceptable given the
overall 10s budget.

### Change 3: Supersede Dispatcher (`src/review/preview_routes.py`)

State:

```python
_preview_jobs: dict[str, PreviewJob] = {}      # job_id -> job
_active_by_song: dict[str, str] = {}           # song_hash -> active job_id
_dispatch_lock = threading.Lock()              # guards both dicts
_preview_cache = _PreviewCache(max_entries=16)  # LRU in preview.py
_preview_dir: Path = Path(tempfile.mkdtemp(prefix="xlight_preview_"))
```

POST `/api/song/<hash>/preview`:

1. Acquire `_dispatch_lock`.
2. Compute `brief_hash = sha256(canonical_json(brief))[:16]`.
3. Check `_preview_cache`: if hit, return cached result immediately (no job
   launched).
4. If `_active_by_song[hash]` exists, cancel its token and forget it from
   `_active_by_song` (the superseded job remains in `_preview_jobs` briefly so
   its status can be inspected, but it is no longer the "current" job for the
   song). Its artifact path will never be returned to a client.
5. Create `PreviewJob(job_id=uuid4(), ...)`, register it, mark as active,
   launch a daemon `Thread` pointed at `_run_preview`, release the lock,
   return `202 {"job_id": ...}`.

GET `/api/song/<hash>/preview/<job_id>` returns status + metadata +
download URL (when `done`).

GET `/api/song/<hash>/preview/<job_id>/download` streams the `.xsq`. Refuses
if the job has been superseded (returns 410 Gone) to close the race where a
browser held an old `job_id`.

### Change 4: Scoped `write_xsq` (`src/generator/xsq_writer.py`)

Add two optional keyword parameters to `write_xsq`:

- `scoped_duration_ms: int | None = None` — override the `sequenceDuration`
  element. When set, the sequence header reports this instead of
  `plan.song_profile.duration_ms`.
- `audio_offset_ms: int | None = None` — when set, (a) emit a `mediaOffset`
  element in `<head>` with this value, and (b) shift every `EffectPlacement.start_ms`
  / `end_ms` by `-audio_offset_ms` at serialization time so the output
  timeline starts at 0.

Both default to `None`, so full-render callsites are unchanged. Preview invokes
with `scoped_duration_ms = clamped_window_ms` and
`audio_offset_ms = section.start_ms`. `research.md` documents the xLights
`mediaOffset` compatibility audit.

### Change 5: First-Cut Post-Hoc Filter (`src/generator/preview.py`)

Until spec 048 lands, `run_section_preview`:

1. Calls `build_plan(config, ...)` — full plan, all sections.
2. Picks `target = assignments[section_index]`.
3. Constructs a new `SequencePlan` with `sections=[target]` and the same
   layout/groups/models.
4. Calls `write_xsq(plan, output_path, audio_path=config.audio_path,
   scoped_duration_ms=window_ms, audio_offset_ms=target.section.start_ms)`.

Steps 1–3 throw away `place_effects` work for non-target sections. The
cancellation token covers the wasted-work window. Once spec 048 is in,
`build_plan(section_filter=section_index)` short-circuits the outer loop and
the post-hoc filter collapses to a single-section selection.

### Change 6: Frontend Wiring (`song-workspace.html` / `song-workspace.js`)

The Preview tab (shell from spec 046) gains:

- Section `<select>` populated from the song's sections (label + timestamps +
  energy score), auto-selected to the picker's choice.
- **Preview** button → POST → poll every 500ms → render result pane with
  metadata, download link, and any warnings.
- Brief-change listener flips a `.stale` class on the result pane within
  500ms of any Brief edit (SC-005). Does not auto-re-preview in first cut
  (debounced auto-preview is User Story 4 P2, deferred).
- Error pane with human-readable message on `failed` jobs. On error, the
  previous result's download link is removed (FR-013).

### Out-of-Scope (deferred)

- User Story 5 (in-browser canvas visualization) — P3 stretch, not in first
  implementation.
- Debounced auto-re-preview (User Story 4 acceptance #4) — manual
  **Re-preview** button is sufficient for the core loop.
- `build_plan(section_filter=...)` — follow-up after spec 048; first
  implementation uses post-hoc filter.

## Phase 2 Handoff

`/speckit.tasks` will derive an ordered task list from this plan, with a
natural split:

1. Tests first (picker, job, integration) — all failing.
2. `preview.py` skeleton (picker + CancelToken + dataclasses).
3. `xsq_writer.py` scoped params.
4. `preview_routes.py` blueprint + registration.
5. `run_section_preview` wiring.
6. Frontend wiring.
7. End-to-end validation against quickstart.md.

Each step maps to a single test or small code change per the Constitution's
Test-First principle.
