# Data Model: Hierarchy Orchestrator

**Feature**: 016-hierarchy-orchestrator
**Date**: 2026-03-25

## Entity Overview

```
HierarchyResult (root output)
├── L0: SpecialMoments
│   ├── energy_impacts: [TimingMark]
│   ├── energy_drops: [TimingMark]
│   └── gaps: [TimingMark]
├── L1: Structure
│   └── sections: [TimingMark]       (with label + duration_ms)
├── L2: Bars
│   └── bars: TimingTrack            (single best)
├── L3: Beats
│   └── beats: TimingTrack           (single best)
├── L4: Events
│   └── stems: {stem_name → TimingTrack}
├── L5: EnergyCurves
│   ├── curves: {stem_name → ValueCurve}
│   └── spectral_flux: ValueCurve?
├── L6: Harmony
│   ├── chords: TimingTrack?         (with labels)
│   └── key_changes: TimingTrack?    (with labels)
├── Interactions: InteractionResult?
└── Metadata
    ├── capabilities: {str → bool}
    ├── stems_available: [str]
    ├── algorithms_run: [str]
    └── warnings: [str]
```

## Entities

### TimingMark (modified)

Existing entity with two new optional fields.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| time_ms | int | yes | Timestamp in milliseconds |
| confidence | float? | no | Algorithm confidence (0.0–1.0) |
| label | str? | no | **NEW**: Semantic label — segment name (A, B, N1), chord (Am, G), event type (impact, drop) |
| duration_ms | int? | no | **NEW**: Duration for segments. Marks without duration are point events. |

**Identity**: time_ms within a track (no two marks at same timestamp)
**Validation**: time_ms >= 0, duration_ms > 0 when present

### TimingTrack (unchanged)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | str | yes | Track identifier |
| algorithm_name | str | yes | Which algorithm produced this |
| element_type | str | yes | "beat", "bar", "onset", "structure", "chord", "key" |
| marks | [TimingMark] | yes | Ordered by time_ms ascending |
| quality_score | float | yes | 0.0–1.0 |
| stem_source | str | yes | "full_mix", "drums", "bass", "vocals", "other" |

### ValueCurve (new)

A continuous time-series of normalized values. Replaces the fake TimingMark lists used by bbc_energy et al.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | str | yes | Curve identifier (e.g., "energy_drums") |
| stem_source | str | yes | Which stem this curve was derived from |
| fps | int | yes | Frame rate (typically 20) |
| values | [int] | yes | 0–100 per frame. Length = duration_s × fps |

**Identity**: name (unique within a HierarchyResult)
**Validation**: all values in 0–100 range, fps > 0, len(values) > 0
**Derived property**: duration_ms = len(values) × 1000 / fps

### HierarchyResult (new)

The structured output replacing AnalysisResult. One field per hierarchy level.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| schema_version | str | yes | "2.0.0" (breaking change from AnalysisResult v1) |
| source_file | str | yes | Path to input MP3 |
| source_hash | str | yes | MD5 of file content (cache key) |
| duration_ms | int | yes | Song duration |
| estimated_bpm | float | yes | Detected tempo |
| energy_impacts | [TimingMark] | yes | L0: sudden energy increases (label="impact") |
| energy_drops | [TimingMark] | yes | L0: sudden energy decreases (label="drop") |
| gaps | [TimingMark] | yes | L0: silence periods (label="gap", with duration_ms) |
| sections | [TimingMark] | yes | L1: structural segments (label=A/B/N1, with duration_ms) |
| bars | TimingTrack? | no | L2: single best bar track (null if unavailable) |
| beats | TimingTrack? | no | L3: single best beat track (null if unavailable) |
| events | {str: TimingTrack} | yes | L4: stem_name → onset track. At least "full_mix". |
| energy_curves | {str: ValueCurve} | yes | L5: stem_name → energy curve. At least "full_mix" when available. |
| spectral_flux | ValueCurve? | no | L5: spectral change rate curve |
| chords | TimingTrack? | no | L6: chord changes with labels (null if unavailable) |
| key_changes | TimingTrack? | no | L6: key changes with labels (null if unavailable) |
| interactions | InteractionResult? | no | Stem interactions (null if <2 stems) |
| stems_available | [str] | yes | List of stems that were available |
| capabilities | {str: bool} | yes | What tools were detected |
| algorithms_run | [str] | yes | Which algorithms actually executed |
| warnings | [str] | yes | Human-readable warnings (empty list if none) |

**Identity**: source_hash (one result per unique file content)
**Validation**: schema_version must be "2.0.0", at least one of bars/beats/events must be non-empty

### Capabilities (new)

Simple dict, not a separate dataclass.

| Key | Type | Description |
|-----|------|-------------|
| vamp | bool | Vamp Python package + plugins available |
| madmom | bool | madmom package available |
| demucs | bool | demucs + torch available |
| whisperx | bool | whisperx available (for future use) |
| genius | bool | GENIUS_API_TOKEN env var set (for future use) |

### InteractionResult (existing, unchanged)

Reused from existing `src/analyzer/result.py`. Contains:
- leader_track (LeaderTrack)
- tightness (TightnessResult)
- sidechained_curves ([SidechainedCurve])
- handoffs ([HandoffEvent])

## State Transitions

HierarchyResult has no state machine — it's computed once and cached. The orchestrator pipeline is a linear flow:

```
detect capabilities → load audio → separate stems (if demucs)
    → run algorithms per level → select best per level
    → derive L0 features → compute interactions
    → assemble HierarchyResult → cache → export .xtiming
```

## Serialization

HierarchyResult serializes to JSON via `to_dict()` / `from_dict()` methods following the existing pattern in result.py. Schema version "2.0.0" distinguishes from the old AnalysisResult format.

Cache reads check schema_version — if it's not "2.0.0", the cache is invalidated and re-analyzed (handles upgrade from old format).
