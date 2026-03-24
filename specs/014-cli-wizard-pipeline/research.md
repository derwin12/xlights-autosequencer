# Research: Interactive CLI Wizard & Pipeline Optimization

**Branch**: `014-cli-wizard-pipeline` | **Date**: 2026-03-24

---

## R1: Interactive Terminal Library for Python CLI Wizards

**Decision**: Use `questionary` (built on `prompt_toolkit`) for interactive terminal menus.

**Rationale**:
- Provides arrow-key navigable `select`, `checkbox`, and `confirm` prompts out of the box
- Built on `prompt_toolkit` which handles raw terminal input, ANSI escape codes, and TTY detection
- Graceful fallback: `questionary` raises `KeyboardInterrupt` on Ctrl-C (clean exit)
- TTY detection: `prompt_toolkit` exposes `is_tty()` for non-interactive fallback
- Active maintenance, widely used in Python CLI tools (copier, nox, etc.)
- Click-compatible: can coexist with Click without conflict

**Alternatives considered**:
- `InquirerPy`: Similar feature set, but less active maintenance
- `rich` + manual keypress handling: More control but significantly more code
- `curses`/`blessed`: Too low-level; would require building all prompt types from scratch
- `simple-term-menu`: Lightweight but lacks multi-step wizard flow and confirm screens

---

## R2: Parallelization Strategy for Algorithm Execution

**Decision**: Thread-based parallelism for local (librosa) algorithms; overlap local execution with the subprocess batch; split subprocess batch into independent groups when stems allow.

**Rationale — Current bottleneck analysis**:

The pipeline currently runs in this order:
1. Audio load (once)
2. Stem separation (once, if enabled)
3. Local librosa algorithms — **sequential** loop (8 algorithms)
4. Subprocess vamp/madmom batch — **sequential** within subprocess (14 algorithms)
5. Phoneme analysis (sequential, after stems)
6. Song structure / Genius (sequential)

**Parallelization opportunities identified**:

| Opportunity | Speedup Estimate | Complexity |
|-------------|-----------------|------------|
| Local librosa algorithms in parallel threads | 2-3x for local phase | Low |
| Overlap local execution with subprocess batch | Significant (they share no state) | Medium |
| Start full-mix algorithms before stem separation completes | Moderate (unblocks ~5 algos earlier) | Medium |
| Phoneme analysis concurrent with non-vocal algorithms | Moderate (whisperx is slow) | Low |
| Genius lyrics fetch concurrent with analysis | Minor (network I/O) | Low |

**Dependency graph (DAG)**:

```
audio_load ──┬──→ [full-mix local] librosa_onsets, bass, mid, treble, harmonic_peaks
             │     (parallel threads, no stem dependency)
             │
             ├──→ [full-mix subprocess] qm_segments, qm_tempo
             │     (no stem dependency, can start immediately)
             │
             ├──→ stem_separation ──┬──→ [drums-stem local] librosa_beats, librosa_bars, librosa_drums
             │                      │     (parallel threads)
             │                      │
             │                      ├──→ [drums-stem subprocess] qm_beats, qm_bars, beatroot,
             │                      │     qm_onsets_complex, qm_onsets_hfc, qm_onsets_phase,
             │                      │     madmom_beats, madmom_downbeats
             │                      │
             │                      ├──→ [vocals-stem subprocess] pyin_notes, pyin_pitch_changes
             │                      │
             │                      ├──→ [piano-stem subprocess] chordino_chords, nnls_chroma
             │                      │
             │                      └──→ phoneme_analysis (whisperx on vocals stem)
             │
             └──→ genius_lyrics_fetch (network, independent)

all_tracks_complete ──→ score_all ──→ assemble_result
```

**Threading vs. multiprocessing**:
- Librosa algorithms are CPU-bound but release the GIL during numpy/C operations → threads give real parallelism for the numeric portions
- Subprocess algorithms already run in a separate process → no GIL concern
- `concurrent.futures.ThreadPoolExecutor` for local algorithms (simple, well-tested)
- For subprocess algorithms: could launch 2-3 separate subprocess batches (full-mix vs drums-stem vs vocals/piano-stem) in parallel — each gets its own vamp_runner process

**Alternatives considered**:
- `multiprocessing.Pool` for local algorithms: Higher overhead (pickle serialization of large audio arrays), more complex error handling, and librosa already does well with thread parallelism via numpy
- `asyncio`: Not a natural fit for CPU-bound audio processing; adds complexity without benefit
- Single subprocess with internal parallelism: Would require rewriting vamp_runner.py significantly

---

## R3: Pipeline Redundancy Analysis

**Decision**: The current pipeline has two areas of redundant/suboptimal work that should be restructured.

**Finding 1 — Audio loading is NOT redundant** (good):
- `runner.run()` calls `load(audio_path)` exactly once (line 63)
- The subprocess batch receives the file path and re-loads audio independently (unavoidable — separate process)
- No fix needed here

**Finding 2 — Subprocess batch is monolithic** (suboptimal):
- All vamp/madmom algorithms are sent to a single subprocess call
- This means full-mix vamp algorithms (qm_segments, qm_tempo) wait for stem-dependent ones
- **Fix**: Split subprocess into groups by stem dependency, launch in parallel:
  - Group 1: full-mix (qm_segments, qm_tempo) — can start immediately
  - Group 2: drums-stem (qm_beats, qm_bars, beatroot, 3x onsets, madmom) — after stems
  - Group 3: vocals-stem (pyin_notes, pyin_pitch_changes) — after stems
  - Group 4: piano-stem (chordino, nnls_chroma) — after stems

**Finding 3 — Stem separation blocks ALL algorithms** (suboptimal):
- Currently in cli.py, `stems = sep.separate(audio_path)` runs before `runner.run()`
- This means all 8 local librosa algorithms wait for stem separation (~30-60s with demucs)
- The 5 full-mix algorithms (librosa_onsets, bass, mid, treble, harmonic) don't need stems
- **Fix**: Start full-mix algorithms immediately after audio load; wait for stems only before stem-dependent algorithms

**Finding 4 — Scoring runs inline per-track** (minor):
- `score_track()` is called per algorithm in the loop (line 85)
- This is fine — scoring is fast (~1ms per track) and doesn't need restructuring

**Finding 5 — Phoneme analysis is correctly sequenced** (good):
- Phoneme analysis runs after all timing tracks are complete
- It depends only on the vocals stem, not on timing tracks
- **Optimization**: Could run concurrently with non-vocal algorithms (stems → phonemes in parallel with stems → drums/piano algorithms)

---

## R4: Wizard Step Ordering and Configuration Flow

**Decision**: The wizard presents steps in this order, with smart defaults and conditional steps.

**Wizard flow**:

```
Step 1: Cache Check (auto-detected)
    → Shows cache status: "Found (2 hours ago, valid)" / "Found (stale — file changed)" / "Not found"
    → Options: Use cache / Regenerate / Skip cache
    → If "Use cache" selected and cache is valid → skip to result display

Step 2: Analysis Scope
    → Options: Full analysis (all algorithms + stems + phonemes)
             / Quick analysis (librosa only, no stems)
             / Custom (choose which groups)
    → Default: Full analysis

Step 3: Algorithm Groups (only if "Custom" in Step 2)
    → Checkbox list: [x] Librosa, [x] Vamp plugins, [x] Madmom, [ ] Stems, [ ] Phonemes
    → Show which are available (vamp venv present? madmom importable?)

Step 4: Whisper Model (only if phonemes enabled)
    → Select: tiny (fastest) / base (default, balanced) / small / medium / large-v2 (highest accuracy)
    → Each shows: size, estimated time, "cached locally" badge if downloaded

Step 5: Confirm & Run
    → Summary of all selections
    → "Press Enter to start analysis, Esc to cancel"
```

**Rationale**: Steps are ordered by decision impact (cache skips everything, scope determines which subsequent steps appear). Conditional steps keep the wizard short for common paths.

---

## R5: Multi-Track Progress Display

**Decision**: Use a live-updating terminal display with per-algorithm status lines during parallel execution.

**Design**:
```
Analyzing: Highway to Hell (3:28)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45%

  stem separation     ████████████████████  done (42s)
  librosa_beats       ████████████████░░░░  running...
  librosa_bars        ████████████████░░░░  running...
  librosa_onsets      ████████████████████  done (3s)  → 847 marks
  bass                ████████████████████  done (2s)  → 124 marks
  mid                 ░░░░░░░░░░░░░░░░░░░░  waiting (needs stems)
  qm_beats            ░░░░░░░░░░░░░░░░░░░░  waiting (subprocess)
  phonemes            ░░░░░░░░░░░░░░░░░░░░  waiting (needs vocals)
```

**Implementation approach**: Use ANSI escape codes for in-place line updates. `rich.live` or manual `\033[A` cursor movement. Falls back to simple line-by-line output in non-TTY mode.

**Alternatives considered**:
- `tqdm` with multiple bars: Doesn't handle variable-length labels well
- `rich.progress` with multiple tasks: Good fit, but adds a dependency; acceptable since `questionary` already pulls in `prompt_toolkit`
- Manual ANSI codes: Portable but tedious; `rich` is better

**Decision**: Use `rich` for progress display. It's a widely-used, zero-config library that handles terminal capability detection, fallback, and live multi-line updates. Combined with `questionary` for prompts, this gives a polished terminal UX.

---

## R6: Non-Interactive Fallback

**Decision**: When stdin is not a TTY, skip all interactive prompts and use defaults (or CLI-flag overrides). Print a one-line notice: "Non-interactive mode: using defaults. Use --help for flag options."

**Detection**: `sys.stdin.isatty()` — standard, works in pipes, CI, and cron.

**Flag parity (FR-014)**: Every wizard selection maps to an existing or new CLI flag:

| Wizard Step | CLI Flag |
|-------------|----------|
| Cache control | `--no-cache` (existing), new `--use-cache` / `--skip-cache-write` |
| Analysis scope | `--algorithms` (existing), `--stems/--no-stems` (existing), `--phonemes/--no-phonemes` (existing) |
| Whisper model | `--phoneme-model` (existing) |
