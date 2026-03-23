# Research: Configurable Quality Scoring

**Branch**: `011-quality-score-config` | **Date**: 2026-03-22

---

## Decision 1: Scoring Architecture — Category-Aware Weighted Sum

**Decision**: Replace the single global density+regularity formula with a category-aware weighted scoring system. Each algorithm belongs to a scoring category (beats, bars, onsets, segments, pitch, harmony) that defines expected target ranges per criterion. Criteria scores reflect how well the measured value falls within the category's expected range rather than a single global ideal.

**Rationale**: The current scorer (`scorer.py`) uses a fixed 0.6 density + 0.4 regularity formula with a single "good" density range (250–1000 ms intervals). This penalizes segment tracks (few marks by design) and rewards only mid-tempo beat patterns. Category-aware targets let each algorithm type define what "good" looks like.

**Alternatives considered**:
- Per-algorithm individual targets (rejected: 22 separate configs is unmanageable for users)
- Machine learning scoring (rejected: out of scope per spec)
- Single global formula with adjustable weights (rejected: doesn't solve the segment/beat disparity)

---

## Decision 2: Scoring Criteria Set

**Decision**: Five scoring criteria:

| Criterion | Measured Value | Description |
|-----------|---------------|-------------|
| `density` | marks per second | How frequently timing marks occur |
| `regularity` | 1 - coefficient of variation of inter-mark intervals | How consistent the spacing between marks is |
| `mark_count` | total number of marks in the track | Absolute count of timing events |
| `coverage` | fraction of song duration containing marks (first mark to last mark / total duration) | How much of the song the track spans |
| `min_gap` | proportion of inter-mark intervals >= 25 ms | Fraction of intervals that meet the minimum actionable gap |

**Rationale**: Density and regularity are carried forward from the current scorer. Mark count, coverage, and min_gap are new criteria addressing spec requirements FR-002, FR-002a, and FR-002b. The criteria set is fixed (no plugin extensibility per spec assumptions).

**Alternatives considered**:
- Including "spectral contrast" or "energy variance" (rejected: not directly relevant to lighting usefulness)
- Making min_gap a hard filter instead of a scored criterion (rejected: spec says it contributes to score, with thresholds available for hard filtering)

---

## Decision 3: Category Definitions and Target Ranges

**Decision**: Six built-in scoring categories with default target ranges:

| Category | Algorithms | Density (marks/s) | Regularity | Mark Count | Coverage |
|----------|-----------|-------------------|------------|------------|----------|
| beats | qm_bar_beat_beats, beatroot_beats, librosa_beats, madmom_rnn_beats, madmom_rnn_downbeats | 1.0–4.0 | 0.6–1.0 | 100–800 | 0.8–1.0 |
| bars | qm_bar_beat_bars, librosa_bars | 0.2–1.0 | 0.6–1.0 | 20–200 | 0.7–1.0 |
| onsets | qm_onset_*, librosa_onset, librosa_hpss_drums | 1.0–8.0 | 0.0–0.6 | 100–2000 | 0.7–1.0 |
| segments | qm_segmenter | 0.01–0.1 | 0.0–0.5 | 4–30 | 0.5–1.0 |
| pitch | pyin_note_events, pyin_pitch_changes | 0.5–4.0 | 0.1–0.7 | 50–500 | 0.5–1.0 |
| harmony | chordino_chord_changes, nnls_chroma_peaks, librosa_hpss_harmonic | 0.2–2.0 | 0.1–0.6 | 20–400 | 0.5–1.0 |

An algorithm not found in any category mapping falls back to a `general` default category with broad ranges (density 0.1–5.0, regularity 0.0–1.0, mark_count 10–1000, coverage 0.3–1.0).

**Rationale**: Categories group algorithms by output type (what they detect), not by library (how they detect). Target ranges are derived from observed output characteristics across a variety of songs. Users can override both category assignments and target ranges.

**Alternatives considered**:
- Finer-grained categories (e.g., "fast_beats" vs "slow_beats") — rejected for simplicity; users can customize ranges per category
- Library-based grouping — rejected because the same concept (e.g., beat tracking) spans multiple libraries

---

## Decision 4: Score Computation Formula

**Decision**: For each criterion, compute a criterion score (0.0–1.0) based on how well the measured value falls within the category's target range:

1. If value is within [min, max] range → 1.0
2. If value is below min → linear falloff from 1.0 at min to 0.0 at 0 (or a defined floor)
3. If value is above max → linear falloff from 1.0 at max to 0.0 at 2× max (capped)

The overall score is a weighted sum of criterion scores, normalized to [0.0, 1.0]:
```
score = sum(weight_i * criterion_score_i) / sum(weight_i)
```

Default weights: density=0.25, regularity=0.25, mark_count=0.15, coverage=0.15, min_gap=0.20.

**Rationale**: Linear interpolation outside target ranges is simple, predictable, and explainable. The formula preserves backward compatibility when all weights are at defaults and categories approximate the old behavior. Min_gap gets 0.20 weight because sub-25ms intervals are a real hardware defect.

**Alternatives considered**:
- Gaussian/bell-curve scoring around target center (rejected: harder to explain to users)
- Binary pass/fail per criterion (rejected: loses granularity)
- Exponential decay outside range (rejected: over-penalizes minor deviations)

---

## Decision 5: Diversity Filter Algorithm

**Decision**: When `--top N` is used, apply a greedy diversity filter after scoring:

1. Sort all tracks by score descending
2. For each candidate track, compare against already-selected tracks:
   - For each pair, compute the proportion of marks in the candidate that align with marks in a selected track within ±tolerance_ms (default 50 ms)
   - If this proportion >= similarity_threshold (default 0.90), the candidate is "near-identical" — skip it and record which selected track it duplicates
3. Select the next highest-scoring non-duplicate track
4. Repeat until N tracks are selected or all tracks exhausted

**Rationale**: Greedy selection is O(N×M×K) where N=candidates, M=selected, K=marks — efficient for 22 tracks. The mark-alignment approach directly measures timing similarity regardless of algorithm name or library.

**Alternatives considered**:
- Correlation-based similarity (rejected: more complex, less interpretable)
- Clustering all tracks then picking one per cluster (rejected: harder to explain which track was skipped and why)
- Name-based deduplication (rejected: different algorithms can produce identical timing)

---

## Decision 6: Configuration File Format

**Decision**: TOML format for scoring configuration files. Schema:

```toml
# Criterion weights (must sum to > 0, all >= 0)
[weights]
density = 0.25
regularity = 0.25
mark_count = 0.15
coverage = 0.15
min_gap = 0.20

# Thresholds (optional, tracks outside these are excluded from ranked output)
[thresholds]
min_mark_count = 5
min_coverage = 0.1
max_density = 20.0

# Diversity filter settings
[diversity]
tolerance_ms = 50
threshold = 0.90

# Minimum gap settings
[min_gap]
threshold_ms = 25

# Category target overrides (only override what you want to change)
[categories.beats]
density_min = 1.5
density_max = 3.5
regularity_min = 0.7
```

**Rationale**: TOML is human-readable, supports comments (important for self-documenting configs per FR-005), is part of the Python standard library (tomllib in 3.11+), and is simpler than YAML for flat key-value configuration.

**Alternatives considered**:
- JSON (rejected: no comments, less human-friendly for hand-editing)
- YAML (rejected: more complex parser, whitespace-sensitive, not in stdlib)
- Python dataclass with JSON schema (rejected: not user-editable in a text editor without understanding Python)

---

## Decision 7: Profile Storage

**Decision**: Profiles are stored as TOML files in `~/.config/xlight/scoring/` (user-global) or `.scoring/` (project-local, checked into git). Profile name = filename without extension. Project-local profiles take precedence over user-global profiles with the same name. A `default.toml` file is generated on first use with all defaults and comments explaining each field.

**Rationale**: Filesystem-based profiles are simple, portable (copy the file to share), and require no database. The `~/.config/xlight/` path follows XDG conventions on macOS/Linux.

**Alternatives considered**:
- SQLite profile database (rejected: overkill for a handful of config files)
- Single JSON file with all profiles (rejected: harder to share individual profiles)
