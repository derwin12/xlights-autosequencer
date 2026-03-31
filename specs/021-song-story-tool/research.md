# Research: Song Story Tool

**Feature**: 021-song-story-tool | **Date**: 2026-03-30

## R1: Section Boundary Detection Strategy

**Decision**: Reuse existing boundaries from HierarchyResult.sections (produced by SegmentinoAlgorithm or QMSegmenterAlgorithm), supplemented by vocal activity transitions detected from the vocals stem energy curve.

**Rationale**: The orchestrator already runs segmentation algorithms that produce 20-40 boundary points. Adding vocal-activity-based boundaries (vocal entry/exit points from stem RMS threshold crossings) captures structure that purely spectral segmenters miss. The merger then collapses these into 8-15 meaningful sections.

**Alternatives considered**:
- Running a new segmentation algorithm (e.g., MSAF or custom novelty function): Rejected because existing Vamp segmenters are already well-tuned and cached. Adding another algorithm increases computation time without clear quality gain.
- Using only QM boundaries without vocal augmentation: Rejected because instrumental breaks and vocal entries are critical structural cues that QM segmenters don't reliably distinguish.

## R2: Section Role Classification Approach

**Decision**: Three-signal classifier as described in stem-lighting-framework.md. Primary signal = vocal activity, secondary = energy percentile rank among vocal sections, tertiary = MFCC cosine similarity for repetition.

**Rationale**: Vocal presence/absence is the strongest predictor of section type (intro vs verse vs instrumental break). Energy rank among vocal sections distinguishes verse (lower) from chorus (higher). MFCC similarity catches repeated sections without needing explicit pattern matching.

**Alternatives considered**:
- ML-based section classifier (e.g., fine-tuned model on SALAMI dataset): Rejected per Simplicity First principle — the three-signal heuristic is interpretable, testable with fixtures, and doesn't require training data or model weights.
- Energy-only classification (current approach): Rejected because it collapses to just three tiers (ethereal/structural/aggressive), losing the nuanced role distinctions that drive lighting decisions.

## R3: Dramatic Moment Detection

**Decision**: Combine existing L0 data (energy_impacts, energy_drops, gaps from HierarchyResult) with new detectors for vocal_entry, vocal_exit, texture_shift, and handoff. Classify temporal patterns (isolated, plateau, cascade, double_tap, scattered) by windowed neighbor analysis.

**Rationale**: L0 data already captures energy surges/drops and silence gaps. The missing moment types (vocal events, texture shifts) can be cheaply derived from stem RMS curves and harmonic/percussive ratio. Temporal pattern classification adds interpretive value for the generator (sustained effects vs one-shots).

**Alternatives considered**:
- Librosa onset_detect with custom filters per moment type: Rejected because onset detection catches too many events. We need semantically meaningful moments, not every transient.
- Manual moment annotation only (no auto-detection): Rejected because users expect a reasonable starting point; manual-only is too tedious.

## R4: Re-Profiling Strategy for Review Edits

**Decision**: When the user edits section boundaries (split, merge, drag), re-extract features from raw audio + stem arrays for the affected time ranges. Audio and stems are loaded into memory once at review session start.

**Rationale**: Re-profiling requires computing RMS, onset density, spectral features, and stem levels for new time ranges. With audio already in memory, this is fast (sub-second for a single section). Loading from disk on every edit would be too slow.

**Alternatives considered**:
- Pre-compute features at fine granularity and aggregate on the fly: Rejected because it requires a large pre-computed index (every 100ms × multiple features × 7 stems) with marginal speed benefit over direct computation.
- Skip re-profiling, let user manually adjust energy/texture: Rejected because it defeats the purpose of automated profiling and makes the review UI less useful.

## R5: Song Story File Location and Caching

**Decision**: Store as `<audio_stem>_story.json` adjacent to the audio file (same directory as existing `_hierarchy.json` cache). Keyed by MD5 hash of audio content for identity.

**Rationale**: Consistent with existing caching patterns (stems in `.stems/<md5>/`, hierarchy in `_hierarchy.json`). Adjacent storage makes it easy to find the story for a given audio file. MD5 keying (already computed by the orchestrator) ensures cache validity.

**Alternatives considered**:
- Centralized story store in `~/.xlight/stories/`: Rejected because it breaks locality — the user expects song-related files near the song.
- Embed story inside the hierarchy JSON: Rejected because the story has a different lifecycle (it can be reviewed/edited independently, and re-generation of the hierarchy should not overwrite a reviewed story).

## R6: Review Server Architecture

**Decision**: Add a new Flask blueprint (`story_routes.py`) to the existing review server. Routes serve the story review SPA and provide JSON API endpoints for load, save, export, and re-profile operations. Audio is streamed from disk; stem arrays are loaded into memory at session start.

**Rationale**: The existing review server already handles audio serving, SSE progress streaming, and static file serving. Adding a blueprint is the minimal-change approach. A separate server would duplicate audio serving and CORS configuration.

**Alternatives considered**:
- Separate Flask app on a different port: Rejected per Simplicity First — duplicates infrastructure and confuses the user with two review commands.
- Electron/Tauri desktop app: Rejected — massive new dependency for a tool that only needs a browser tab.

## R7: Generator Integration Strategy

**Decision**: Modify `plan.py` to accept an optional song story JSON path. When provided, skip `derive_section_energies()` and `select_themes()` in their current form, reading section roles, energy scores, and lighting guidance directly from the story. When no story exists, fall back to the current pipeline.

**Rationale**: Gradual migration. The generator can work with or without a song story, so the user isn't forced to generate a story for every song immediately. Once the story workflow is validated, the fallback can be deprecated.

**Alternatives considered**:
- Hard cutover (require song story for all generation): Rejected because it would break existing workflows during the transition period.
- Adapter layer that converts story JSON to SectionEnergy objects: Rejected — unnecessary abstraction. The generator can read the JSON dict directly.
