# Data Model: Interactive CLI Wizard & Pipeline Optimization

**Branch**: `014-cli-wizard-pipeline` | **Date**: 2026-03-24

---

## New Entities

### WizardConfig

Captures all user selections from the interactive wizard. Produced by the wizard UI, consumed by the analysis orchestrator.

**Fields**:
- `audio_path` (string, required): Absolute path to the input audio file
- `cache_strategy` (enum: "use_existing" | "regenerate" | "skip_write"): How to handle the analysis cache
- `algorithm_groups` (set of strings): Which algorithm libraries to include — subset of {"librosa", "vamp", "madmom"}
- `use_stems` (boolean): Whether to run stem separation
- `use_phonemes` (boolean): Whether to run vocal phoneme analysis
- `whisper_model` (string): Whisper model name ("tiny", "base", "small", "medium", "large-v2"); only meaningful when use_phonemes is true
- `use_structure` (boolean): Whether to run song structure detection
- `use_genius` (boolean): Whether to fetch Genius lyrics

**Relationships**:
- 1:1 with an analysis run — each WizardConfig produces exactly one analysis execution
- Maps directly to existing CLI flags (FR-014)

---

### PipelineStep

Represents a single unit of work in the restructured analysis pipeline with explicit dependency declarations.

**Fields**:
- `name` (string, required): Unique identifier (e.g., "audio_load", "stem_separation", "librosa_beats")
- `phase` (enum: "setup" | "analysis" | "post"): Pipeline phase this step belongs to
- `depends_on` (list of strings): Names of steps that must complete before this step can start
- `status` (enum: "pending" | "waiting" | "running" | "done" | "failed" | "skipped"): Current execution state
- `started_at` (timestamp, nullable): When execution began
- `completed_at` (timestamp, nullable): When execution finished
- `mark_count` (integer, nullable): Number of timing marks produced (for algorithm steps)
- `error` (string, nullable): Error message if status is "failed"

**Relationships**:
- Many PipelineSteps form one DependencyGraph (directed acyclic graph)
- Each algorithm-type PipelineStep wraps one Algorithm instance
- Status transitions: pending → waiting → running → done/failed; or pending → skipped

---

### CacheStatus

Read-only snapshot of the analysis cache state for a given audio file. Displayed in the wizard's cache step.

**Fields**:
- `exists` (boolean): Whether a cached result file exists on disk
- `is_valid` (boolean): Whether the source_hash in the cache matches the current audio file's MD5
- `age_seconds` (integer, nullable): Seconds since the cache file was last modified (null if not exists)
- `cache_path` (string, nullable): Absolute path to the cached JSON file (null if not exists)
- `track_count` (integer, nullable): Number of timing tracks in the cached result
- `has_phonemes` (boolean): Whether the cached result includes phoneme data
- `has_structure` (boolean): Whether the cached result includes song structure data

**Relationships**:
- 1:1 with an audio file path
- Derived from existing AnalysisCache + AnalysisResult deserialization

---

### WhisperModelInfo

Describes a single Whisper model variant for display in the wizard.

**Fields**:
- `name` (string): Model identifier ("tiny", "base", "small", "medium", "large-v2")
- `description` (string): One-line trade-off summary
- `is_cached` (boolean): Whether the model files exist in the local Whisper cache directory
- `approximate_size_mb` (integer): Approximate download size in megabytes

**Relationships**:
- Read-only; derived from the whisperx/faster-whisper model cache directory
- Selected model name stored in WizardConfig.whisper_model

---

## Modified Entities

### AnalysisResult (existing — extended)

**New field**:
- `pipeline_stats` (object, optional): Execution statistics from the parallelized pipeline
  - `total_wall_clock_ms` (integer): Total wall-clock time from start to finish
  - `total_cpu_ms` (integer): Sum of all individual step durations
  - `parallelism_ratio` (float): cpu_ms / wall_clock_ms — >1.0 indicates effective parallelism
  - `step_timings` (list of objects): Per-step name + duration_ms pairs

**Rationale**: Enables benchmarking SC-002 (30% speedup target) and gives the user visibility into where time was spent.

---

## Dependency Graph (Static Declaration)

The pipeline dependency graph is defined as a static adjacency list. Each algorithm step declares its dependencies:

```
audio_load          → []                          (root — no dependencies)
stem_separation     → [audio_load]                (needs loaded audio)
genius_fetch        → [audio_load]                (needs audio metadata only)

# Full-mix algorithms (no stem dependency)
librosa_onsets      → [audio_load]
bass                → [audio_load]
mid                 → [audio_load]
treble              → [audio_load]
harmonic_peaks      → [audio_load]
qm_segments         → [audio_load]
qm_tempo            → [audio_load]

# Drums-stem algorithms
librosa_beats       → [stem_separation]
librosa_bars        → [stem_separation]
librosa_drums       → [stem_separation]
qm_beats            → [stem_separation]
qm_bars             → [stem_separation]
beatroot_beats      → [stem_separation]
qm_onsets_complex   → [stem_separation]
qm_onsets_hfc       → [stem_separation]
qm_onsets_phase     → [stem_separation]
madmom_beats        → [stem_separation]
madmom_downbeats    → [stem_separation]

# Vocals-stem algorithms
pyin_notes          → [stem_separation]
pyin_pitch_changes  → [stem_separation]
phoneme_analysis    → [stem_separation]

# Piano-stem algorithms
chordino_chords     → [stem_separation]
nnls_chroma         → [stem_separation]

# Post-processing
score_all           → [all algorithm steps]
assemble_result     → [score_all, genius_fetch, phoneme_analysis]
```

When stems are disabled, stem-dependent algorithms either fall back to full_mix (depends_on becomes [audio_load]) or are skipped entirely per user configuration.
