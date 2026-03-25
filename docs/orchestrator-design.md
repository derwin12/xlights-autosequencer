# Orchestrator Design — Zero-Flag Analysis Pipeline

**Created**: 2026-03-25
**Status**: Implemented — `src/analyzer/orchestrator.py` (feature 016)

---

## 1. The Goal

```bash
xlight-analyze song.mp3
```

That's it. One argument, zero flags. The orchestrator makes all the decisions internally based on what it finds in the audio. Output is a complete hierarchical analysis organized by the 7 levels defined in the musical analysis design doc.

---

## 2. What the Orchestrator Replaces

Currently the user must choose:
- `--stems/--no-stems` → orchestrator auto-detects: if demucs is available, use stems
- `--algorithms` → orchestrator runs the right algorithms per hierarchy level
- `--no-vamp`, `--no-madmom` → orchestrator auto-detects what's installed
- `--phonemes`, `--phoneme-model` → orchestrator runs if whisperx is available
- `--structure`, `--genius` → orchestrator always runs segmentino (validated best)
- `--scoring-config`, `--scoring-profile` → orchestrator picks the best track per level, no scoring config needed
- `--top N` → replaced by hierarchy-level selection (one best per purpose)
- `--no-cache` → orchestrator uses cache by default, re-runs if source file changed

**14 flags → 0 flags.**

---

## 3. Pipeline Stages

```
MP3 in
  │
  ├─ Stage 1: Discover capabilities
  │   What's installed? (vamp, madmom, demucs, whisperx)
  │   Decide what we can run.
  │
  ├─ Stage 2: Load audio + stem separation
  │   Load MP3 once. If demucs available, separate stems. Cache stems.
  │
  ├─ Stage 3: Run algorithms (grouped by hierarchy level)
  │   Only run what's needed for each level. Not all 36.
  │   Route each algorithm to its best stem automatically.
  │
  ├─ Stage 4: Select best per level
  │   For each hierarchy level, pick the single best result.
  │   No flat ranked list — structured output.
  │
  ├─ Stage 5: Compute derived features
  │   Energy impacts (from bbc_energy curve)
  │   Gaps/silence (from energy curve)
  │   Interactions (leader, tightness, sidechain, handoffs)
  │
  ├─ Stage 6: Condition & export
  │   Downsample to 20 FPS, smooth, normalize 0-100
  │   Write .xtiming (timing marks) + .xvc (value curves)
  │
  └─ Output: HierarchyResult (JSON) + export files
```

---

## 4. Algorithm Selection Per Level

The orchestrator doesn't run all 36 algorithms. It runs a focused set per level:

| Level | Purpose | Algorithms to Run | Best-of Selection |
|-------|---------|-------------------|-------------------|
| **L0: Special Moments** | Impacts, gaps, novelty | `bbc_energy` (→ derive impacts + gaps) | N/A — derived, not selected |
| **L1: Structure** | Section boundaries | `segmentino` | Only one — no selection needed |
| **L2: Bars** | Bar boundaries | `qm_bars`, `librosa_bars`, `madmom_downbeats` | Pick the one with most regular intervals |
| **L3: Beats** | Beat positions | `qm_beats`, `librosa_beats`, `madmom_beats`, `beatroot_beats` | Pick by cross-correlation with onset density |
| **L4: Events** | Per-stem accents | `aubio_onset` (per stem), `percussion_onsets` (drums) | One track per stem, filter by density range |
| **L5: Energy** | Value curves | `bbc_energy` (per stem), `bbc_spectral_flux`, `amplitude_follower` | All — these are value curves, not competing |
| **L6: Harmony** | Chord/key changes | `chordino_chords`, `qm_key` | Both — different purposes (chord changes vs key) |

**Total: ~15 algorithm runs** (varies with stem count) instead of 36.

---

## 5. Data Model Changes

### New: `ValueCurve` (first-class type)

```python
@dataclass
class ValueCurve:
    name: str
    stem_source: str
    fps: int
    values: list[int]       # 0-100 per frame

    @property
    def duration_ms(self) -> int:
        return int(len(self.values) * 1000 / self.fps)
```

### Updated: `TimingMark` — add label

```python
@dataclass
class TimingMark:
    time_ms: int
    confidence: float | None = None
    label: str | None = None        # NEW: for segments (A, B, N1), chords (Am, G)
    duration_ms: int | None = None  # NEW: for segments with duration
```

### New: `HierarchyResult` — structured output

```python
@dataclass
class HierarchyResult:
    source_file: str
    duration_ms: int
    estimated_bpm: float

    # L0: Special Moments
    energy_impacts: list[TimingMark]     # time_ms + label ("impact"/"drop")
    gaps: list[TimingMark]               # time_ms + duration_ms

    # L1: Structure
    sections: list[TimingMark]           # time_ms + label (A, B, N1) + duration_ms

    # L2: Bars
    bars: TimingTrack                    # single best bar track

    # L3: Beats
    beats: TimingTrack                   # single best beat track

    # L4: Instrument Events (one per stem)
    events: dict[str, TimingTrack]       # stem_name → onset track

    # L5: Energy Curves
    energy_curves: dict[str, ValueCurve] # stem_name → energy curve
    spectral_flux: ValueCurve | None

    # L6: Harmony
    chords: TimingTrack | None           # chord change marks with labels
    key_changes: TimingTrack | None

    # Interactions (from stems)
    interactions: InteractionResult | None

    # Metadata
    stems_available: list[str]
    capabilities: dict[str, bool]        # what was installed/available
    warnings: list[str]
```

---

## 6. Capability Detection

At startup, the orchestrator checks what's available and adjusts:

```python
def detect_capabilities() -> dict[str, bool]:
    return {
        "vamp": _check_vamp_available(),
        "madmom": _check_madmom_available(),
        "demucs": _check_demucs_available(),
        "whisperx": _check_whisperx_available(),
        "genius": _check_genius_token(),
    }
```

| Capability | If Available | If Missing |
|------------|-------------|------------|
| **vamp** | Run all Vamp algorithms (segmentino, qm_bars, bbc_energy, etc.) | Fall back to librosa-only (beats, bars, onsets) |
| **madmom** | Include madmom_beats and madmom_downbeats in best-of selection | Skip — librosa/vamp cover these |
| **demucs** | Separate stems, run per-stem analysis | Full-mix only — still produces L0-L3 and L6 |
| **whisperx** | Add vocal transcription for future vocal-based features | Skip — not critical for current pipeline |
| **genius** | Add section names to L1 structure (overlay on segmentino) | Skip — segmentino labels are sufficient |

The user never needs to know or care what's installed. The orchestrator runs whatever it can and degrades gracefully.

---

## 7. Output Structure

```
song_name/
├── song_name_hierarchy.json     # HierarchyResult — the main output
├── song_name.xtiming            # All timing marks (beats, bars, sections, events)
├── valuecurves/
│   ├── energy_full_mix.xvc      # L5 energy curves
│   ├── energy_drums.xvc
│   ├── energy_bass.xvc
│   ├── energy_vocals.xvc
│   ├── spectral_flux.xvc
│   └── ...
└── stems/                       # Cached stems (if demucs ran)
    ├── drums.wav
    ├── bass.wav
    ├── vocals.wav
    └── other.wav
```

---

## 8. CLI Surface

```bash
# The only command most users need:
xlight-analyze song.mp3

# Optional: point at a directory to batch-process:
xlight-analyze /path/to/mp3s/

# Optional: just see what would run (no analysis):
xlight-analyze song.mp3 --dry-run

# Optional: force re-analysis (ignore cache):
xlight-analyze song.mp3 --fresh
```

**Two optional flags maximum.** Everything else is automatic.

---

## 9. What Stays, What Changes, What's New

### Stays (no changes needed)
- All 36 algorithm implementations in `src/analyzer/algorithms/`
- `conditioning.py` — downsample, smooth, normalize
- `xvc_export.py` — value curve XML generation
- `xtiming.py` — timing track XML generation
- `interaction.py` — leader, tightness, sidechain, handoffs
- `stems.py` — demucs separation + caching
- `audio.py` — MP3 loading

### Changes (modify existing)
- `result.py` — add `ValueCurve`, add `label`/`duration_ms` to `TimingMark`, add `HierarchyResult`
- `vamp_bbc.py` — store curve values in `ValueCurve` instead of fake timing marks
- `vamp_segmentation.py` — store labels and durations in `TimingMark`
- `vamp_harmony.py` — store chord names as labels

### New code
- `orchestrator.py` — the main pipeline: detect → load → analyze → select → derive → export
- New CLI command (or replace existing `analyze`) — single-argument entry point

### Deprecated (keep but don't maintain)
- `sweep.py`, `sweep_matrix.py` — parameter sweeping was a research tool, not needed in production pipeline
- `wizard.py` — replaced by zero-flag orchestrator
- `scorer.py`, `scoring_config.py` — replaced by per-level best-of selection
- `stem_inspector.py` — interactive stem review replaced by automatic stem usage

---

## 10. Implementation Notes (Post-Implementation)

### Per-stem algorithm routing
The vamp_runner subprocess uses `"algo_name:stem"` encoding (e.g. `"bbc_energy:drums"`) to run
a single algorithm on a specific stem. The orchestrator builds this list; vamp_runner splits on `:`,
overrides `preferred_stem`, and names the resulting track `"bbc_energy_drums"`.

### ValueCurve crossing the subprocess boundary
`TimingTrack.to_dict()` now serializes the dynamically-set `value_curve` attribute so it survives
the vamp_runner → orchestrator JSON round-trip. `from_dict()` restores it via `globals().get("ValueCurve")`.

### Track indexing in the orchestrator
Tracks are indexed by base algorithm name (stripping `_stem` suffix). L4 events are grouped by
`track.stem_source`, not by lookup key, to handle the `_stem` suffix format from vamp_runner.

### Cache path
Output goes to `{song_dir}/{song_name}/{song_name}_hierarchy.json`. For example,
`/mp3s/Thriller.mp3` → `/mp3s/Thriller/Thriller_hierarchy.json`.

### Review server adaptation
`src/review/server.py` includes `_adapt_hierarchy_for_ui(data)` which converts a
`HierarchyResult` dict into the flat `timing_tracks` list expected by the existing JS UI.
The full hierarchy is also passed as `data["hierarchy"]` for new UI features.

### Deviations from design
- The `.xvc` value curve XML export was not implemented (the design doc referenced `xvc_export.py`
  which was not created). Energy curves are stored in the `_hierarchy.json` as integer arrays.
- `energy_drops` was split out as its own top-level field (design had it inside `energy_impacts`).
- `HierarchyResult` includes `schema_version`, `source_hash` fields not in the original design sketch.
