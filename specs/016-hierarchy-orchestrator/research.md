# Research: Hierarchy Orchestrator

**Feature**: 016-hierarchy-orchestrator
**Date**: 2026-03-25

## R1: Best-of Selection Strategy for Beats and Bars

**Decision**: Use interval regularity (coefficient of variation) as the primary metric, with onset correlation as tiebreaker.

**Rationale**: Batch validation on 22 songs showed all beat/bar trackers produce similar frequency (~2/s beats, ~0.5/s bars). The differentiator is consistency — a good beat track has evenly spaced marks. Coefficient of variation (std/mean of intervals) directly measures this. Lower CV = more regular = better beat track. When two tracks have similar CV, cross-correlate with onset density to prefer the track whose beats align with detected onsets.

**Alternatives considered**:
- Quality score from existing scorer.py — too generic, doesn't account for beat-specific quality
- User selection — violates zero-flag requirement
- Always pick a fixed algorithm (e.g., always madmom_beats) — misses cases where another tracker is better for a specific song

## R2: Energy Impact Derivation Thresholds

**Decision**: Use validated thresholds from batch analysis: >1.8x ratio for impacts, <0.55x for drops, in 1-second windows. Gaps: energy < 5/100 for >300ms.

**Rationale**: These thresholds were validated on 22 songs across rock, pop, and holiday genres. Energy impacts: 22/22 songs produced events (mean 12.2/song). Gaps: 18/22 songs had detectable gaps. Thresholds are hardcoded, not configurable — they work for the target genres and configurability would add flags.

**Alternatives considered**:
- Configurable thresholds via TOML — adds complexity, violates zero-flag, not needed for target genres
- Adaptive thresholds (percentile-based per song) — novelty peaks use this but energy impacts work better with absolute ratios

## R3: Capability Detection Approach

**Decision**: Import-based detection with graceful fallback. Try importing each library; if ImportError, mark capability as unavailable. For Vamp plugins specifically, also check that plugin files exist in the system plugin path.

**Rationale**: This is what the existing codebase already does (runner.py lines 289-363 use try/except ImportError). The orchestrator formalizes this into a capabilities dict returned at startup. No filesystem scanning for Python packages — import is the authoritative check.

**Alternatives considered**:
- `pkg_resources` / `importlib.metadata` — more brittle, doesn't catch broken installs
- Config file listing capabilities — requires manual maintenance, violates zero-flag

## R4: Cache Strategy for HierarchyResult

**Decision**: Reuse existing `AnalysisCache` pattern — MD5 hash of source file content as cache key. Cache the full HierarchyResult JSON. Invalidate when hash changes.

**Rationale**: The existing cache system (`src/cache.py`) already does this for AnalysisResult. Same approach works for HierarchyResult. The cache key is the file content hash, not the filename, so renaming a file doesn't invalidate.

**Alternatives considered**:
- Separate cache per hierarchy level — over-engineered, the whole analysis runs together
- mtime-based invalidation — less reliable than content hash (file can be replaced with same mtime)

## R5: Relationship Between HierarchyResult and Existing Code

**Decision**: HierarchyResult is a new dataclass that replaces AnalysisResult as the primary output. The orchestrator internally uses the existing AnalysisRunner and algorithm implementations but post-processes their output into the hierarchy structure. Existing algorithms return TimingTrack/ValueCurve as before — the orchestrator maps them into the right level.

**Rationale**: This preserves all existing algorithm code unchanged. The orchestrator is a new layer on top, not a rewrite of what's below. The AnalysisRunner still runs algorithms and returns tracks — the orchestrator just organizes and selects from those tracks.

**Alternatives considered**:
- Modify AnalysisRunner to produce HierarchyResult directly — tightly couples runner to hierarchy concept
- Keep both AnalysisResult and HierarchyResult — two competing output formats is confusing

## R6: Algorithm-to-Level Mapping

**Decision**: Hardcode the mapping in the orchestrator. Each hierarchy level knows which algorithms to request and which stems to route them to.

| Level | Algorithms | Stems |
|-------|-----------|-------|
| L0 | `bbc_energy` | full_mix (derive impacts/gaps from curve) |
| L1 | `segmentino` | full_mix |
| L2 | `qm_bars`, `librosa_bars`, `madmom_downbeats` | full_mix (or drums if available) |
| L3 | `qm_beats`, `librosa_beats`, `madmom_beats`, `beatroot_beats` | full_mix (or drums if available) |
| L4 | `aubio_onset`, `percussion_onsets` | per-stem (drums, bass, vocals, other, full_mix) |
| L5 | `bbc_energy`, `bbc_spectral_flux`, `amplitude_follower` | per-stem |
| L6 | `chordino_chords`, `qm_key` | full_mix (or guitar/piano if available) |

**Rationale**: This mapping comes directly from the validated musical analysis design doc. It was tested on 22 songs. The mapping is static — it doesn't change per song.

**Alternatives considered**:
- Dynamic mapping based on song characteristics — over-engineered for target genres
- Config file mapping — adds a file the user would need to maintain
