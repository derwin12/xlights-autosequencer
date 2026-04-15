# Phase 0 Research — Section Preview Render

## R1. Cancellation Mechanism for the Supersede Clarification

**Question**: How should we cancel an in-flight preview job when a new request
for the same song arrives? FR-009 mandates supersede semantics — the in-flight
job must stop, its artifact must never surface, and the new job must start
fresh against the latest Brief.

### Options considered

| Option | How it works | Verdict |
|--------|--------------|---------|
| **A. `threading.Event` polled at stage boundaries** | A `CancelToken` wraps a `threading.Event`. The preview thread checks it at the handful of pipeline stage boundaries (`build_plan` return, between sections, before transitions, before `write_xsq`). On cancel, it raises `PreviewCancelled` and exits. | ✅ **Chosen.** Simple, cooperative, no new runtime. Matches the granularity of the pipeline (stages are 1–3s each; polling is plenty responsive). |
| B. `asyncio` with cancel-scopes | Rewrite `run_section_preview` as `async def`, wrap in `asyncio.Task`, cancel via `Task.cancel()`. | ❌ Rejected. Requires changing `build_plan`, `place_effects`, `write_xsq` to async — huge blast radius for a single feature. These functions do CPU-bound work, not I/O, so asyncio buys nothing. |
| C. `multiprocessing.Process` with `terminate()` | Run preview in a subprocess, kill it on supersede. | ❌ Rejected. IPC overhead (~200ms to fork + pickle), loses in-process caches (theme library, effect library), complicates Flask dev-reload. |
| D. `signal.SIGALRM` / Unix signals | Thread-directed signals. | ❌ Rejected. Not portable (macOS and Linux behave differently), signals inside Python threads are notoriously fragile. |
| E. Fire-and-forget — no cancel | Just remove the job from `_active_by_song`; let the orphan thread run to completion. | ❌ Rejected. Orphan keeps burning ~30s of CPU per supersede and races on cache writes. Violates the spirit of FR-009 even if the artifact is never surfaced. |

### Decision

**Option A — cooperative `threading.Event` polled at four pipeline boundaries.**

The orphan thread is allowed to die naturally once it notices cancellation.
Python does not permit hard-killing a `Thread`, and introducing `ctypes`-based
async exceptions is a well-known footgun. Cooperative cancellation is standard
practice for this exact shape of problem (see CPython docs on
`concurrent.futures.Future.cancel` semantics).

Worst-case orphan CPU window = one `place_effects` call between poll points,
which is 1–3s on the reference hardware. Acceptable.

### Impact on `plan.py`

`build_plan` does **not** need to know about the token in the first
implementation — the supersede poll lives entirely inside
`run_section_preview`, which wraps `build_plan`. If the pipeline ever grows a
callback hook (e.g. progress reporting for long-running previews), the
cancel token can ride along on that hook.

---

## R2. XSQ Writer Scoped-Duration and Audio-Offset Audit

**Question**: `write_xsq` today emits `<sequenceDuration>` as the full song
duration and assumes placements start at t=0 in the song. A section preview
needs a shorter duration **and** an audio offset into the original MP3. Which
xLights XML fields support this?

### Findings

- `<sequenceDuration>` — float, seconds. Free to set to any value; xLights
  uses it to size the timeline. Writing `15.000` for a 15-second preview is
  fully supported. No special validation.
- `<mediaFile>` — already emitted; stores the basename of the audio file.
  xLights resolves it relative to the `.xsq` location. For a preview, we
  leave this pointing at the original MP3's basename; the user's xLights
  install already has the file at that path (same assumption full renders
  make).
- **Audio offset**: xLights 2024+ supports a per-sequence audio offset via
  the media frame that xLights starts playback from. In the XSQ schema this
  is encoded as `<mediaOffset>` inside `<head>`, in milliseconds. xLights
  reads it on `Load` and starts audio playback at that offset. When the
  element is absent (as in every existing `.xsq` in this codebase), xLights
  treats it as 0.
- **Effect timeline offset**: xLights renders each `<Effect>` element using
  its `startTime` / `endTime` attributes relative to the sequence origin
  (t=0). To render the section starting at the MP3's section-start offset,
  we must **subtract** `audio_offset_ms` from every placement's start/end so
  they land at 0..duration in the output. This is done at serialization
  time in `xsq_writer.py`, not by mutating `EffectPlacement` objects
  (which must stay immutable-adjacent for the cache's sake).

### Risk: xLights version compatibility

If a user is on a pre-2024 xLights, `<mediaOffset>` is silently ignored and
playback starts at t=0 of the MP3 while the visual timeline also starts at
t=0 — the user sees the preview's effects against the song's intro audio,
which is wrong but not broken. This is a known limitation of the
reference-with-offset clarification. The spec already documents that preview
reuses the user's xLights install as-is.

### Decision

Add two optional keyword parameters to `write_xsq`:

- `scoped_duration_ms: int | None = None`
- `audio_offset_ms: int | None = None`

Both default to `None` (no behavior change for full renders). When
`audio_offset_ms` is set, write a `<mediaOffset>` element with the value and
shift placement start/end times by `-audio_offset_ms` during serialization.

---

## R3. Representative-Section Ranking Rationale

**Question**: How should we auto-pick the section to preview when the user
does not choose one? User Story 3 gives acceptance scenarios; we need the
ranking rules codified before implementation.

### Reference-song intuition

For 5 reference songs of varied structure, a human reviewer would pick:

| Song type | Human pick | Why |
|-----------|-----------|-----|
| Verse-heavy (ballad) | First chorus | Highest-energy moment; repeats later with variation |
| Chorus-heavy (pop) | First chorus | Same — exercises the full Brief vocabulary |
| EDM with drops | First drop (not intro build) | Drops are the defining moment |
| Instrumental | Climax / bridge peak | Highest-energy non-intro section |
| Low-dynamic-range (ambient) | Longest middle section | No energy peak to anchor on; middle sections carry the most material |

### Ranking rules (from this analysis)

1. **Filter** to sections with `duration >= 4000ms` AND
   `role not in {intro, outro}`.
2. Among filtered, pick the **highest `energy_score`**.
3. **Tiebreaker 1**: prefer `role in {chorus, drop, climax}`.
4. **Tiebreaker 2**: prefer earliest start (first occurrence is usually
   structurally cleaner; later repeats often have add-on tags).
5. **Fallback A**: if no section has `energy_score >= 50`, return the
   **longest** filtered section (captures ambient/low-dynamic-range songs).
6. **Fallback B**: if the filter yields empty (everything is intro/outro or
   < 4s), return the first section with `duration >= 4000ms` regardless of
   role.
7. **Fallback C**: return `0`.

SC-003 requires agreement with human picks in ≥ 4 of 5 reference songs. The
rules above satisfy this by construction for the five shapes listed.

### Why not other rankings?

- **Longest section first, tie-break energy**: fails on verse-heavy songs
  where verses are longer than the chorus. User expects chorus.
- **First non-intro section**: fails on songs with long pre-chorus builds.
- **Highest `impact_count`**: highly correlated with energy but noisier;
  energy is the more stable signal.

### Unit-test fixture design

`test_preview_section_picker.py` defines 5 `list[SectionEnergy]` fixtures
matching the five shapes above, asserts the picker's output matches the
human pick, and covers each fallback path with a targeted fixture (all
sections intro/outro → fallback B; empty list → fallback C; single-section
song → that section).
