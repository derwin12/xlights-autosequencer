# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# XLight AutoSequencer Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-22

## Active Technologies
- Python 3.11+ + demucs (new), vamp, librosa, madmom, click, Flask (008-stem-separation)
- JSON files (local filesystem); WAV stem files in `.stems/<md5>/` (008-stem-separation)
- Python 3.11+ + whisperx (faster-whisper + wav2vec2), nltk cmudict, existing deps (vamp, librosa, madmom, demucs, click, Flask) (009-vocal-phoneme-tracks)
- JSON files + `.xtiming` XML files (local filesystem) (009-vocal-phoneme-tracks)
- Python 3.11+ + click 8+, Flask 3+ (existing); no new dependencies (010-analysis-cache-library)
- JSON files — `_analysis.json` (existing, extended with `source_hash`); `~/.xlight/library.json` (new) (010-analysis-cache-library)
- Python 3.11+ + numpy (scoring math), tomllib (TOML config parsing, stdlib in 3.11+), click 8+ (CLI), pytest (testing) (011-quality-score-config)
- TOML files (scoring configs/profiles), JSON files (analysis output with score breakdowns) (011-quality-score-config)
- Python 3.11+ + vamp, numpy, click 8+ (all existing — no new deps) (005-vamp-parameter-tuning)
- JSON files (local filesystem); new `~/.xlight/sweep_configs/` directory (005-vamp-parameter-tuning)
- Python 3.11+ + numpy (signal processing, cross-correlation), librosa 0.10+ (audio features, onset detection), vamp (plugin host), click 8+ (CLI), xml.etree.ElementTree (stdlib, xLights XML export) (012-intelligent-stem-sweep)
- JSON files (analysis output), XML files (`.xtiming`, `.xvc` exports), WAV stem files in `.stems/<md5>/` (012-intelligent-stem-sweep)
- Python 3.11+ + `lyricsgenius` (new optional dep), `mutagen` (new lightweight dep), (013-genius-lyric-segments)
- JSON files — existing MD5-keyed `_analysis.json` cache; `song_structure` field (013-genius-lyric-segments)
- Python 3.11+ + click 8+ (CLI), questionary 2+ (interactive prompts, new), rich 13+ (progress display, new), concurrent.futures (stdlib, parallelism) (014-cli-wizard-pipeline)
- JSON files (existing `_analysis.json` cache, `~/.xlight/library.json`) (014-cli-wizard-pipeline)
- Python 3.11+ + librosa 0.10+, vamp (optional), madmom 0.16+ (optional), demucs/torch (optional), click 8+ (CLI), numpy (016-hierarchy-orchestrator)
- JSON files (hierarchy result), XML files (.xtiming export), WAV stems cached in `.stems/<md5>/` (016-hierarchy-orchestrator)
- Python 3.11+ + `xml.etree.ElementTree` (stdlib), `click` 8+ (existing) (017-xlights-layout-grouping)
- `xlights_rgbeffects.xml` — read and rewritten in-place (backup optional) (017-xlights-layout-grouping)
- Python 3.11+ + `json` (stdlib), `pathlib` (stdlib) — no new dependencies (018-effect-themes-library)
- `src/effects/builtin_effects.json` (built-in catalog), `~/.xlight/custom_effects/*.json` (custom overrides) (018-effect-themes-library)
- Python 3.11+ + `json` (stdlib), `pathlib` (stdlib), `src.effects` (feature 018) (019-effect-themes)
- `src/themes/builtin_themes.json` (built-in), `~/.xlight/custom_themes/*.json` (custom) (019-effect-themes)
- Python 3.11+ + click 8+ (CLI), questionary 2+ (wizard prompts), rich 13+ (progress/tables), mutagen (ID3 tags), xml.etree.ElementTree (stdlib, XSQ generation) (020-sequence-generator)
- `.xsq` XML files (output), JSON analysis cache (existing) (020-sequence-generator)
- Python 3.11+ + librosa 0.10+, vamp, madmom 0.16+, demucs (htdemucs_6s), Flask 3+, click 8+, numpy (021-song-story-tool)
- JSON files (song story output), WAV/MP3 stems in `.stems/<md5>/`, analysis cache (`_hierarchy.json`) (021-song-story-tool)
- Python 3.11+ + pathlib (stdlib), os (stdlib), hashlib (stdlib) — no new dependencies (023-devcontainer-path-resolution)
- JSON files (analysis cache, library index, stem manifests) (023-devcontainer-path-resolution)
- Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend) + Flask 3+ (web server), click 8+ (CLI), mutagen (ID3 tags), existing analysis pipeline (027-unified-dashboard)
- JSON files — `~/.xlight/library.json` (song library), `~/.xlight/custom_themes/*.json` (custom themes), `src/themes/builtin_themes.json` (built-in themes, read-only) (027-unified-dashboard)
- Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend) + Flask 3+ (web server), click 8+ (CLI), existing analysis pipeline (033-theme-variant-separation)
- JSON files (builtin_themes.json, variant builtins/*.json, custom themes/variants) (033-theme-variant-separation)
- Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend) + Flask 3+ (web server), existing `src/generator/plan.py` + `src/generator/xsq_writer.py`, `src/library.py` — no new dependencies (034-library-sequence-gen)
- `~/.xlight/settings.json` (layout path), in-memory `_jobs` dict (generation state), `tempfile.mkdtemp()` (generated `.xsq` files) (034-library-sequence-gen)
- Python 3.11+ + click 8+ (CLI), Flask 3+ (web server), existing generator pipeline (036-focused-effects-repetition)
- JSON files (theme definitions, effect definitions, variant library) (036-focused-effects-repetition)
- Python 3.11+ + Flask 3+ (web server), click 8+ (CLI), existing generator pipeline (038-palette-restraint)
- JSON files (theme definitions, variant library), XML files (.xsq output) (038-palette-restraint)
- Python 3.11+ + click 8+, Flask 3+, existing generator pipeline (037-duration-scaling)
- JSON files (effect definitions, analysis output), XML files (.xsq output) (037-duration-scaling)
- Python 3.11+ + No new dependencies — all existing generator pipeline (041-prop-type-affinity)
- N/A — no new data stored; changes are in-memory generation logic (041-prop-type-affinity)
- Python 3.11+ (backend), TypeScript 5+ / ES2022 (frontend) + Flask 3+ (backend web server, existing); React 18+, Zustand 4+, Vite 5+, TypeScript 5+ (frontend). No UI framework (no Tailwind, no shadcn/ui, no Chakra) — design tokens ported directly from [design_handoff_xonset/prototype/state.jsx](../../design_handoff_xonset/prototype/state.jsx) as CSS custom properties consumed by CSS Modules. (051-x-onset-frontend)
- JSON files on local disk under the user's state directory (`~/.xlight/library/` — library, sections, assignments, preferences, layout), and the existing hash-keyed analysis + stems caches under `.stems/<hash>/` and `_analysis.json` files. (051-x-onset-frontend)
- Python 3.11+ (backend, sidecar); TypeScript 5+ / ES2022 (frontend); Rust 1.75+ (Tauri shell, compiled as part of `tauri build`, not hand-written Rust feature code) + Tauri 2.x; existing Flask 3+, React 18+, Zustand 4+, Vite 5+ (frontend, unchanged); existing analyzer stack (librosa, madmom, vamp, torch, ffmpeg). New build-time only: `pyinstaller` 6+, `@tauri-apps/cli`, Apple `notarytool` (bundled with Xcode). (052-tauri-desktop-packaging)
- JSON on local disk. Existing `~/.xlight/` convention (library, custom themes, preferences) preserved and shared with the CLI. Existing `.stems/<hash>/` co-location with source audio preserved with fallback to `~/Library/Application Support/XLight/stems/<hash>/` when the source directory is not writable. (052-tauri-desktop-packaging)

- **Language**: Python 3.11+
- **Audio analysis**: vamp (Python host), librosa 0.10+, madmom 0.16+
- **Vamp plugin packs**: QM Vamp Plugins, BeatRoot, pYIN, NNLS Chroma/Chordino, Silvet
- **Web server**: Flask 3+ (local review UI)
- **CLI**: click 8+
- **Testing**: pytest
- **Storage**: JSON files (local filesystem)
- **System dependencies**: ffmpeg (MP3 loading), Vamp plugin .dylib files in `~/Library/Audio/Plug-Ins/Vamp/`

## Project Structure

```text
src/
├── analyzer/
│   ├── audio.py              # MP3 loading and AudioFile metadata
│   ├── result.py             # AnalysisResult, TimingTrack, TimingMark data classes
│   ├── runner.py             # Orchestrates all 22 algorithm runs
│   ├── scorer.py             # Quality scoring → quality_score per track
│   └── algorithms/
│       ├── base.py           # Abstract Algorithm interface
│       ├── vamp_beats.py     # QM bar-beat tracker + BeatRoot (Vamp)
│       ├── vamp_onsets.py    # QM onset detector x3 methods (Vamp)
│       ├── vamp_structure.py # QM segmenter + tempo tracker (Vamp)
│       ├── vamp_pitch.py     # pYIN note events + pitch changes (Vamp)
│       ├── vamp_harmony.py   # Chordino chord changes + NNLS chroma peaks (Vamp)
│       ├── librosa_beats.py  # librosa beat tracking + bar grouping
│       ├── librosa_bands.py  # librosa frequency band energy peaks
│       ├── librosa_hpss.py   # librosa HPSS drums + harmonic peaks
│       └── madmom_beat.py    # madmom RNN+DBN beat + downbeat tracking
├── cli.py                    # Click CLI entry point (xlight-analyze command)
├── export.py                 # JSON serialization / deserialization
└── review/
    ├── server.py             # Flask app (/, /analysis, /audio, /export routes)
    └── static/               # Vanilla JS + Canvas 2D + Web Audio API single-page UI

tests/
├── fixtures/                 # Short royalty-free audio files for deterministic tests
├── unit/                     # Per-algorithm unit tests
└── integration/              # End-to-end pipeline tests
```

## Commands

```bash
# Install dependencies
pip install vamp librosa madmom click pytest
brew install ffmpeg  # macOS
# Install Vamp plugin packs from vamp-plugins.org → ~/Library/Audio/Plug-Ins/Vamp/

# Run analysis
xlight-analyze analyze song.mp3

# View track summary
xlight-analyze summary song_analysis.json

# Export selected tracks
xlight-analyze export song_analysis.json --select beats,drums,bass

# Build the React review UI (required once before using `xlight-analyze review`;
# re-run after frontend changes). The built bundle under
# src/review/frontend/dist/ is git-ignored — rebuild locally, don't commit it.
cd src/review/frontend && npm install && npm run build && cd -

# Launch review UI (opens browser at localhost:5173)
xlight-analyze review song_analysis.json

# Run tests
pytest tests/ -v
```

## Segment Classification — Mandatory Changelog Rule

Any change to segment detection, section merging, or section role classification
**must** be logged in `docs/segment-classification-changelog.md` before the change
is considered complete. This includes changes to:

- `src/story/section_classifier.py`
- `src/story/section_merger.py`
- `src/story/builder.py` (section extraction, label handling, or post-processing)
- Any orchestrator code that affects what boundaries are passed to the story builder

**Append only — never remove old entries.** The log exists to prevent going in circles
on classification logic. Read it before making any changes to understand what has
already been tried and why.

### Boundary refinement (post-classification step)

After roles are assigned and merged, the story builder runs a lyric-anchored
boundary-refinement pass (`src/story/boundary_refinement.py`) that adjusts
section edges using audio-level vocal evidence. It consumes WhisperX forced
alignment word marks (already produced for Genius alignment) plus a
free-transcription word stream from `src/analyzer/free_transcription.py`
(WhisperX without Genius), and applies three targeted fixes in fixed order:
(1) merging short low-agreement `post_chorus` tails back into the preceding
chorus thought when the audio is continuous, (2) relabel-or-split of
"bridge" sections that actually contain the chorus's first-line distinctive
hook, and (3) splitting an instrumental lead-in off the front of a vocal
section when there is a long silence before the first audible word. Every
section gains a `boundary_refinements: list[str]` field (empty when nothing
fires); `_story.json` schema is `1.1.0`. See
`openspec/changes/lyric-anchored-boundary-refinement/` for the full design,
preconditions, and 16-song corpus results.

## Code Style

- Follow PEP 8
- Type hints on all public functions and class attributes
- Each algorithm class inherits from `base.Algorithm` and implements `run(audio_array, sample_rate) -> TimingTrack`
- Timestamps are always stored as integers (milliseconds) — never floats

## Recent Changes
- 052-tauri-desktop-packaging: Added Python 3.11+ (backend, sidecar); TypeScript 5+ / ES2022 (frontend); Rust 1.75+ (Tauri shell, compiled as part of `tauri build`, not hand-written Rust feature code) + Tauri 2.x; existing Flask 3+, React 18+, Zustand 4+, Vite 5+ (frontend, unchanged); existing analyzer stack (librosa, madmom, vamp, torch, ffmpeg). New build-time only: `pyinstaller` 6+, `@tauri-apps/cli`, Apple `notarytool` (bundled with Xcode).
- 051-x-onset-frontend: Added Python 3.11+ (backend), TypeScript 5+ / ES2022 (frontend) + Flask 3+ (backend web server, existing); React 18+, Zustand 4+, Vite 5+, TypeScript 5+ (frontend). No UI framework (no Tailwind, no shadcn/ui, no Chakra) — design tokens ported directly from [design_handoff_xonset/prototype/state.jsx](../../design_handoff_xonset/prototype/state.jsx) as CSS custom properties consumed by CSS Modules.
- 041-prop-type-affinity: Added Python 3.11+ + No new dependencies — all existing generator pipeline
  `htdemucs_6s` separates audio into 6 stems (drums, bass, vocals, guitar, piano, other).
  Algorithms route to their preferred stem via `Algorithm.preferred_stem` class attribute.
  Stems are MD5-cached in `.stems/<hash>/` adjacent to the source file. Each `TimingTrack`
  carries a `stem_source` field. The `summary` command shows a `Stem` column. The review UI
  shows a stem badge on each track lane. New module: `src/analyzer/stems.py`.

  madmom produce 22 named timing tracks from a single MP3. Quality-scored JSON output
  with `--top N` auto-selection and manual track selection/export via CLI.
  serves a single-page Canvas+Web Audio app for visualizing timing tracks, synchronized
  playback, Next/Prev/Solo focus navigation, and filtered JSON export.
  with no args shows an upload page; SSE streams per-algorithm progress; browser auto-navigates
  to timeline when done. Vamp/madmom toggles on upload page.

<!-- MANUAL ADDITIONS START -->

## Future Work / TODOs

### Intelligent Effect Rotation (Tier 6-7)
- Current implementation cycles through `_PROP_EFFECT_POOL` in round-robin order per group.
- Future improvement: weight effect selection by section energy, mood, and tempo. High-energy
  sections should favor Meteors/Shockwave/Strobe; low-energy sections should favor
  Ripple/Spirals/Wave. The rotation seed should incorporate variation_seed so repeated
  sections get different effect assignments.
- Consider per-prop-type affinity: arches look best with Chase/Wave, mini-trees with
  Spirals/Fire, candy canes with Single Strand/Bars.

### QM Segmenter Boundary Merging
- The `_merge_qm_boundaries` function uses a simple 2-second minimum gap to avoid
  micro-sections. A better approach would weight QM boundaries by the energy change
  across the boundary (from L5 energy curves) and only merge boundaries with significant
  energy transitions.

### Value Curves Integration
- Value curves (`generate_value_curves` in `src/generator/value_curves.py`) are currently
  disabled (Phase 1 comment in `build_plan`). These allow effect parameters to change
  over time within a single effect placement — e.g. speed ramps up toward a beat drop,
  brightness follows the energy curve, color mix shifts with chord changes.
- Priority parameters for value curves:
  - **Brightness**: follow L5 energy curve so effects breathe with the music
  - **Speed**: ramp up during builds, slow down during drops
  - **Color mix**: shift palette position to follow chord changes (L6 harmony)
  - **Effect-specific**: Fire height follows energy, Ripple movement follows beats
- xLights supports value curves via `VC_` prefixed parameters in the effect string.
  The `supports_value_curve` flag in `builtin_effects.json` marks which parameters
  can accept curves. See `src/generator/value_curves.py` for the existing framework.

### Prop Effect Suitability and Selection
- Currently all prop groups get effects from the same pool (`_PROP_EFFECT_POOL`) without
  considering what looks good on each prop type. This needs a suitability matrix:
  - **Arches/Candy Canes** (linear): Single Strand, Bars, Wave, Marquee work well.
    Shockwave/Ripple render poorly on 1D props.
  - **Matrices** (2D grids): Plasma, Butterfly, Fire, Pinwheel look great.
    Single Strand wastes the 2D resolution.
  - **Mini props** (stars, ornaments, low pixel): On/Off, Strobe, Twinkle are most
    effective. Complex effects are wasted on <50 pixel props.
  - **Deer/figures** (custom shapes): Shimmer, Color Wash, Twinkle preserve the shape.
    Directional effects (Bars, Wave) ignore the form factor.
- Implementation: add a `suitability` dict to each effect in `builtin_effects.json`
  mapping prop display types (SingleLine, Custom, Matrix, Tree, etc.) to a 0-1 score.
  Use these scores in `_build_effect_pool` to weight selection per group based on the
  dominant prop type in that group.
- Also consider prop pixel count: high-density props can handle complex effects,
  low-density props should get simpler ones.

### End-of-Song Fade Out
- Songs that end with a gradual energy decrease (detected via L5 energy curves
  and _drop tagged sections) should have a smooth visual fade-out rather than
  an abrupt cut. Implementation options:
  - Apply a brightness value curve that ramps from 100% to 0% over the final
    _drop section on all active tiers
  - Progressively kill upper tiers one by one (heroes first, then compounds,
    then props, then beats) as energy decreases, leaving only the dim background
    wash for the final seconds
  - Use the existing fade_out_ms field on EffectPlacement to add crossfade
    on the last effect in each group
- This ties into the value curves integration above — a brightness ramp on
  the final section would be the simplest and most effective approach.

### 3D Effects, Blending, and Multi-Layer Effects
- Current implementation places one effect per layer per group. xLights supports
  stacking multiple effect layers on a single model/group with blend modes
  (Additive, Subtractive, Mask, etc.) to create composite visuals.
- **Layer stacking**: place the base effect on layer 1, then add an accent effect
  on layer 2 with a blend mode. E.g. Color Wash (layer 1) + Twinkle (layer 2,
  Additive) creates a twinkling wash. The theme already defines multi-layer
  setups — this would render them as actual stacked layers in the XSQ instead
  of mapping them to different tier groups.
- **3D model awareness**: props with WorldPosZ (depth) or 3D model types could
  use depth-based effects — front props brighter than back props, or effects
  that sweep in the Z direction. The layout parser already reads WorldPosZ.
- **Buffer transforms**: xLights supports per-layer transforms (rotation, zoom,
  blur) via B_SLIDER parameters. Subtle rotation on Pinwheel or zoom pulses
  on Shockwave timed to beats would add visual depth.
- **Render style options**: beyond Per Model Default, explore Per Model Per Preview
  and Per Model Single Line for different prop types.

### Section Transition Boundary Cleanup
- Some section boundaries from the segmentino + QM merge produce awkward
  transitions where effects cut abruptly or overlap in unexpected ways.
  Issues to investigate:
  - **Snap precision**: `_snap_sections_to_bars` uses a window of half the
    median bar interval. Some boundaries may snap to the wrong bar, creating
    short (<2s) or overlapping sub-sections.
  - **Effect crossfade at boundaries**: currently effects end exactly at the
    section boundary and the next section's effects start immediately. Adding
    a short crossfade (fade_out_ms on the outgoing effect, fade_in_ms on the
    incoming) would smooth transitions.
  - **Theme change at boundaries**: when a section changes themes (e.g. A→N5),
    the color palette and effect type change instantly. A 500ms blend or brief
    "Off" gap between sections would create cleaner visual transitions.
  - **QM merge edge cases**: QM boundaries very close to bar lines may create
    sub-sections that are too short to render a full effect cycle. The current
    min_gap_ms=5000 may need tuning per song tempo.
  - Test with more songs to identify systematic boundary issues vs one-offs.

### Custom Per-Song Themes
- Allow users to create custom themes tailored to specific songs, beyond the
  21 built-in themes. Implementation:
  - Custom theme JSON files in `~/.xlight/custom_themes/*.json` (the theme
    library loader already supports this path from feature 019)
  - A `--theme` CLI flag on `generate` to force a specific theme for all sections
  - A `--theme-file` flag to load a one-off theme JSON for a song
  - Theme wizard: interactive prompts to build a theme by choosing mood, palette
    colors, accent colors, base effect, upper effects, and blend modes
  - Theme preview: render a 10-second sample of each section with the chosen
    theme so users can evaluate before committing to a full sequence
  - Song-theme mapping: a config file that remembers which custom theme to use
    for each song (keyed by audio hash or filename)

### Explore Advanced Visual Effects
- Investigate underused xLights effects that could add visual interest:
  - **Kaleidoscope**: mirrors and rotates the underlying effect to create
    symmetrical patterns. Works as a modifier layer (blend on top of a base
    effect). Could be powerful on matrices and large groups where symmetry
    reads well.
  - **Warp**: distorts the effect buffer with swirl/ripple/dissolve transforms.
    Combined with a base like Color Wash or Plasma, could create organic
    evolving visuals. Currently only used in Molten Metal (removed).
  - **Spirograph**: mathematical curve patterns that animate over time.
    Visually striking on matrices but untested in our pipeline.
  - **Galaxy / Swirl patterns**: using Pinwheel with high twist + Kaleidoscope
    overlay could simulate galaxy/vortex effects for dramatic moments.
  - **Music-reactive modifiers**: Kaleidoscope size or Warp intensity driven
    by beat energy or spectral flux, so the visual distortion pulses with
    the music.
- These are best used sparingly as accent effects on hero props or during
  high-energy impact sections rather than as base layer backgrounds.
- Test each on different prop types (1D strings, 2D matrices, custom shapes)
  to determine suitability before adding to the effect pool.

## Design-First Gate

Before writing or editing project code for any change that does **not** qualify as
trivial (criteria below), you must produce a written design and receive explicit
user approval. This exists because jumping to implementation too fast has produced
silent regressions in shared modules and shallow designs that missed obvious edges.

### Trivial-path carve-out

A change qualifies as trivial — and may skip the full design phase — only when
**all** of the following are true:

1. Modifies exactly one file.
2. Fewer than ~30 lines changed (added + removed combined).
3. You can state the root cause in one sentence: *"X happens because Y."*
4. Does NOT modify any public API signature, CLI command or flag, JSON/XML schema
   field, or any file under the shared modules listed below.

If any condition fails, the full gate applies.

### Shared modules (always require the full gate)

These modules are each imported by 32+ files outside themselves. A 10-line change
inside them can silently break many downstream callers, so size is not a safe
proxy for risk. Any change — regardless of line count — requires a design:

- `src/analyzer/`
- `src/effects/`
- `src/generator/`
- `src/review/`
- `src/themes/`

### Required contents of the design artifact

The design may be an OpenSpec change directory (`openspec/changes/<name>/` with
`proposal.md` + `design.md`) or an inline plan in the conversation. Either form
must cover:

- **Goal** — one sentence of what problem this solves.
- **Approach** — the chosen solution, with at least one **alternative considered**
  and a one-sentence rationale for rejecting it.
- **Files touched** — specific paths, with whether each is added/modified/removed.
- **Regression surface** — for every modified public symbol (module-level function,
  class method, CLI flag, schema field), list the callers found via grep across
  `src/` and `tests/`. State which are updated and which should be untouched.
- **Historical echoes** — scan `.wolf/buglog.json` and `.wolf/cerebrum.md`
  Do-Not-Repeat for entries matching the change's files, symbols, or topic.
  Reference matching bug IDs and summarize their fixes. No matches found should
  be stated explicitly, not omitted.

After producing the design, pause and wait for the user to approve before editing
any project file. Do not auto-proceed.

### Stress-testing the design

Use the `/pre-mortem` slash command (or the `pre-mortem` skill directly) to run
an adversarial pass over a design before implementation. The skill produces a
structured report: Regression surface, Hidden assumptions, Historical echoes,
Alternatives not considered, Test gap, and a Verdict. Use it when a design
touches shared modules, is architecturally ambiguous, or feels risky.

The pre-mortem is complementary to `/review-diff` and `/ultrareview`: pre-mortem
reviews the **plan** (pre-code); the others review the **diff** (post-code).
Running both at their respective stages is the recommended path for non-trivial
changes.

### Pre-merge acceptance gate

Before opening a pull request for any non-trivial change, run the acceptance
gate locally:

```bash
xlight-evaluate gate            # full gate (analyzer + generator + UI)  ~3-5 min
xlight-evaluate gate --quick    # quick mode: 1 fixture + content UI flow only
xlight-evaluate gate --skip-ui  # skip UI suite (e.g. when Playwright not installed)
```

CI runs the **cheap tier** automatically on every PR (unit tests, generator
quality check, UI smoke flows). The **expensive tier** (full analyzer pipeline
on the CC0 corpus, content-validating UI flow with real analysis) requires
the `.venv-vamp` sidecar with madmom/vamp installed and is intentionally
**not** run in CI — install complexity + runtime cost outweigh the benefit
on a fresh runner. Developers exercise that locally before opening a PR.

Exit codes from the gate, in priority order:

- `0` — all suites pass
- `6` — at least one suite detected a regression
- `4` — no baseline exists for one or more suites (run `xlight-evaluate
        snapshot-analyzer` first)
- `8` — infrastructure failure (Playwright missing, corpus download
        failed, etc.)

Adding a file to CI's `--ignore` list (in `.github/workflows/evaluate.yml`)
requires a paired entry in `docs/known-broken-tests.md` with diagnosis and
remediation plan. **No silent quarantine** — quarantined tests rot, and a
quarantine ratchet without a paired doc entry erodes the gate over time.

### Visual-quality microscope

The `microscope` subcommand group measures the visual quality of generated
sequences against a panel of CC0 fixtures. It is a developer tool, not part
of CI — run it locally when changing effect selection, palette, pacing, or
prop-pairing logic.

```bash
# Per-song run (writes microscope-out/microscope/<slug>/metrics.json)
xlight-evaluate microscope run path/to/song.mp3

# Whole panel (4 fixtures: funshine, maple_leaf_rag, nostalgic_piano,
# space_ambience) with optional --baseline diff
xlight-evaluate microscope panel --baseline tests/golden/microscope/

# Sensitivity gate — must pass before promoting any baseline. Writes
# tests/golden/microscope/sensitivity_passed.json on success.
xlight-evaluate microscope sensitivity

# Promote per-song metrics.json into tests/golden/microscope/<slug>/baseline.json.
# Refuses to run unless the sensitivity proof file exists and is at least as
# recent as the most-recent commit touching src/evaluation/metrics/,
# src/evaluation/xsq_reader.py, or src/effects/builtin_effects.json.
xlight-evaluate microscope baseline
```

When the metric registry changes (new metric, removed metric, definition
updated), the sensitivity proof's `metric_set_hash` no longer matches the
current registry — re-run `microscope sensitivity` before any
`microscope baseline`.

### Explicit override

If the user explicitly says "just do it," "skip the design," or similar, comply
and proceed directly to implementation. Note the skipped gate in the
end-of-session summary so the override is visible for future reference. The gate
is a default, not a wall.

## Engineering Principles

- **Favor real solutions over hacks.** Fix root causes, not symptoms. No `# HACK`,
  no `# TODO: fix this properly later`, no "temporary" workarounds that become permanent.
  If the right fix is too large for the current scope, say so — don't ship a band-aid.
- **Understand before changing.** Read the relevant code before proposing modifications.
  Trace the call chain. Check how existing callers use the function. Don't guess at behavior.
- **Don't over-engineer.** Solve the problem at hand. No speculative abstractions,
  premature generalization, or "just in case" parameters. Three similar lines are
  better than a clever helper used once.
- **Don't under-engineer either.** If the task requires proper error handling, tests,
  or data validation — do it. Cutting corners to save time creates debt that costs more later.
- **Keep changes minimal and focused.** A bug fix is a bug fix — don't refactor
  surrounding code, add type hints to untouched functions, or "improve" unrelated logic.
- **Test what matters.** Write tests for non-trivial logic, edge cases, and regressions.
  Don't write tests that just assert the implementation does what the implementation does.
- **Name things clearly.** Variable and function names should convey intent. If you need
  a comment to explain what a name means, the name is wrong.
- **No dead code.** Don't comment out code "for reference." Don't leave unused imports,
  variables, or functions. Git history exists for a reason.
- **Don't quarantine instead of fixing.** `pytest.mark.xfail`, `pytest.mark.skip`,
  and CI `--ignore` flags are forms of "temporary workaround that becomes permanent."
  When a test fails, fix the test or fix the code — don't paper over it. The only
  acceptable quarantine is one accompanied by a `docs/known-broken-tests.md` entry
  with diagnosis, remediation plan, and an explicit reason it can't be fixed now.

## Test Isolation Conventions

Recurring test-isolation traps in this repo, with the patterns that fix them:

- **Patch the consumer's import path, not the canonical module.** Some symbols
  are re-exported (`src.cli` re-exports from `src.cli_old`); patching the
  re-export does NOT affect callers that import the original. Find where the
  symbol is *read* (`_get_variant_lib()` reads `src.cli_old._variant_library_override`)
  and patch there. `monkeypatch.setattr(src.cli_old, "_variant_library_override", lib)`,
  not `src.cli`.
- **Reset module-level state between tests.** Modules that hold dicts or
  singletons at module scope (`_runs`, `_jobs`, `_library` in
  `src/review/api/v1/analysis.py` and `src/review/variant_routes.py`)
  accumulate across tests. Fixtures must clear them explicitly:
  `with _analysis_module._runs_lock: _analysis_module._runs.clear()`.
- **Don't read the developer's filesystem.** Tests that load variants/themes
  must override `custom_dir` to a `tmp_path` so they don't pick up
  `~/.xlight/custom_variants/` from the dev host. Tests that resolve show
  paths must `monkeypatch.setattr("src.paths.get_show_dir", ...)` rather
  than relying on `~/xLights/` existing.
- **`XLIGHT_STATE_HOME` for state-dir isolation.** The `app` fixture in
  `tests/review/conftest.py` sets `XLIGHT_STATE_HOME=tmp_path` so the
  library, settings, and stems caches are scoped to the test.
<!-- MANUAL ADDITIONS END -->
