# Implementation Plan: Song Story Tool

**Branch**: `021-song-story-tool` | **Date**: 2026-03-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/021-song-story-tool/spec.md`

## Summary

The Song Story Tool creates a unified interpretation layer between the analyzer (HierarchyResult) and the sequence generator. It replaces the current `derive_section_energies()` → `select_themes()` handoff — which collapses rich per-stem data into a single energy_score and mood_tier — with a structured, human-reviewable song story JSON. The tool has two phases: automatic interpretation (compute) and interactive browser-based review. The song story JSON becomes the single source of truth for all downstream generation.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: librosa 0.10+, vamp, madmom 0.16+, demucs (htdemucs_6s), Flask 3+, click 8+, numpy
**Storage**: JSON files (song story output), WAV/MP3 stems in `.stems/<md5>/`, analysis cache (`_hierarchy.json`)
**Testing**: pytest with royalty-free fixture audio files
**Target Platform**: macOS / Linux (local CLI tool)
**Project Type**: CLI tool + browser-based review UI (local Flask server)
**Performance Goals**: Story generation for a 3-minute MP3 in under 90 seconds (including stem separation if uncached); section edits in review UI complete in <2 seconds (SC-007)
**Constraints**: Fully offline operation; no cloud API calls
**Scale/Scope**: Single user, single song at a time; 8-15 sections per song; 20-30 dramatic moments

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | Song story derives all timing/classification from analyzed audio data. Manual overrides are post-processing only (review phase). Same input + same config = same draft output. |
| II. xLights Compatibility | PASS | Song story is an intermediate JSON format, not an xLights file. Downstream XSQ writer (unchanged) handles xLights compatibility. |
| III. Modular Pipeline | PASS | Song story is a new pipeline stage with well-defined input (HierarchyResult) and output (song story JSON). It does not modify the analyzer or XSQ writer — only replaces the interpretation layer in the generator. |
| IV. Test-First Development | PASS | Unit tests for section classifier, moment detector, energy arc detector. Integration test: MP3 → song story JSON with expected structure. Fixture-based. |
| V. Simplicity First | PASS | No speculative abstractions. Reuses existing infrastructure (stems.py, orchestrator.py, Flask review pattern). New code is focused: story builder, section classifier, moment classifier, review server routes. |

**Post-Phase 1 re-check**: All principles remain satisfied. The data model adds no unnecessary complexity — Song Story JSON is a flat structure with sections, moments, and stem curves derived directly from HierarchyResult.

## Project Structure

### Documentation (this feature)

```text
specs/021-song-story-tool/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── song-story-schema.md
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── story/                        # NEW — Song Story module
│   ├── __init__.py
│   ├── builder.py                # Top-level: HierarchyResult → SongStory JSON
│   ├── section_classifier.py     # Section role assignment (vocal/energy/repetition signals)
│   ├── section_merger.py         # Micro-segment merging into 8-15 meaningful sections
│   ├── moment_classifier.py      # Dramatic moment detection, classification, ranking
│   ├── energy_arc.py             # Global energy arc shape detection
│   ├── section_profiler.py       # Per-section character + stem profiling (energy, texture, drums, solos, leader, tightness, chords, bands)
│   ├── lighting_mapper.py        # Section role → lighting guidance (tiers, brightness, transitions)
│   ├── stem_curves.py            # Extract continuous 2Hz stem curves from ValueCurve data
│   └── models.py                 # Data classes: SongStory, Section, Moment, StemCurves, Preferences, etc.
├── review/
│   ├── server.py                 # MODIFIED — add story-review routes
│   ├── story_routes.py           # NEW — Flask blueprint for story review API
│   └── static/
│       ├── story-review.html     # NEW — Song story review SPA
│       ├── story-review.js       # NEW — Canvas + Web Audio review UI
│       └── story-review.css      # NEW — Review UI styles
├── generator/
│   ├── plan.py                   # MODIFIED — consume SongStory instead of raw HierarchyResult
│   ├── energy.py                 # DEPRECATED — replaced by story section_profiler
│   └── theme_selector.py         # MODIFIED — read role + lighting from story instead of mood_tier
├── cli.py                        # MODIFIED — add `story` and `story-review` commands

tests/
├── unit/
│   ├── test_section_classifier.py
│   ├── test_section_merger.py
│   ├── test_moment_classifier.py
│   ├── test_energy_arc.py
│   ├── test_section_profiler.py
│   ├── test_lighting_mapper.py
│   └── test_stem_curves.py
└── integration/
    └── test_story_pipeline.py    # MP3 → song story JSON end-to-end
```

**Structure Decision**: Single project structure. The song story module (`src/story/`) is a new pipeline stage that sits between the existing analyzer (`src/analyzer/`) and generator (`src/generator/`). The review UI extends the existing Flask server pattern. No new top-level directories needed beyond `src/story/`.

## Complexity Tracking

No constitution violations — table not required.

## Phase 0: Research Findings

See [research.md](research.md) for full details. Key decisions:

1. **Section boundary source**: Use existing `SegmentinoAlgorithm` / `QMSegmenterAlgorithm` boundaries from HierarchyResult.sections, supplemented by vocal activity boundaries from stem energy curves. No new boundary detection needed.

2. **Section role classification**: Three-signal approach from stem-lighting-framework.md. Primary: vocal activity from vocals stem RMS. Secondary: energy relative to vocal sections. Tertiary: MFCC-based repetition detection (cosine similarity > 0.85 inherits role).

3. **Moment detection**: Reuse existing HierarchyResult.energy_impacts and energy_drops (L0). Add vocal_entry/vocal_exit from vocals stem RMS threshold crossings. Add texture_shift from harmonic/percussive ratio changes. Classify temporal patterns by windowed neighbor analysis.

4. **Re-profiling on edit**: When user splits/merges/moves boundaries in review, re-extract features from the raw audio for affected time ranges. Requires the review server to have access to the audio file and the stem arrays (loaded once at review session start).

5. **Song story file location**: Store alongside existing analysis cache as `<audio_stem>_story.json`, keyed by MD5 hash of audio content.

## Phase 1: Design

### Data Model

See [data-model.md](data-model.md) for full entity definitions. Key entities:

- **SongStory**: Top-level container (global properties, preferences, sections, moments, stem curves, review state)
- **Preferences**: Song-wide creative direction (mood, theme, focus_stem, intensity, occasion, genre). Defaults populated at generation; user sets during review.
- **Section**: Role + time bounds + enriched character profile (energy with peak/variance, spectral brightness/centroid/flatness, local tempo, dominant note, frequency bands) + enriched stem profile (drum pattern, solos, leader stem/transitions, tightness, handoffs, chords, other_stem_class) + lighting guidance + user overrides (role, mood, theme, focus_stem, intensity, notes, highlight)
- **Moment**: Type + pattern + rank + stem source + dismissed flag
- **StemCurves**: Per-stem RMS arrays at 2Hz + full-mix RMS/spectral/harmonic/percussive

### Contracts

See [contracts/song-story-schema.md](contracts/song-story-schema.md) for the JSON contract that the generator consumes. Includes the three-level precedence chain for creative preferences (per-section override > song-wide preference > auto-derived).

### Two-File Architecture

User edits are stored separately from the auto-generated base story to preserve a clean diff for algorithm feedback:

| File | Purpose | Modified By |
|------|---------|-------------|
| `<stem>_story.json` | Base auto-generated story | Builder only (never by user) |
| `<stem>_story_edits.json` | User edits as structured diffs | Review UI Save |
| `<stem>_story_reviewed.json` | Merged final output | Review UI Export |

The generator looks for `_story_reviewed.json` first, falls back to `_story.json` (FR-029).

### Integration Points

1. **Input**: `run_orchestrator()` → `HierarchyResult` (unchanged)
2. **Song Story Builder**: `build_song_story(hierarchy: HierarchyResult, audio_path: str) -> dict` — new
3. **Review Server**: Flask blueprint with routes for load, save (writes edits file), export (merges base + edits), re-profile, preferences
4. **Generator Integration**: `plan.py` modified to accept song story JSON path; implements three-level precedence chain for preferences; applies focus_stem zone boosting
5. **CLI**: Two new commands (`story`, `story-review`) following existing click patterns

### Key Architectural Decisions

1. **Song story is JSON, not a Python object graph**: The file is the contract. The generator reads it as a dict, not by importing story module classes. This keeps the modules decoupled.

2. **Two-file split for algorithm feedback**: Auto-generated base is never modified by user actions. Edits are stored separately so the diff reveals classifier errors (wrong roles, false-positive moments, moved boundaries). This data can tune thresholds over time.

3. **Review server loads audio + stems into memory once**: When the review session starts, audio and stem arrays are loaded. This enables fast re-profiling (<2s) when the user splits/merges sections without re-reading files on each edit.

4. **Lighting mapper is a pure function**: `section_role + energy_level → lighting guidance`. No state, no side effects. Easy to test, easy to re-run when the user changes a section role.

5. **Three-level preference precedence**: Per-section override > song-wide preference > auto-derived. Intensity is multiplicative (section × global). The generator never needs to know which level set a value — it just reads the resolved result.

6. **Generator deprecates energy.py gradually**: Phase 1 keeps `derive_section_energies()` as a fallback for when no song story exists. Once song story is the default path, energy.py can be removed.
