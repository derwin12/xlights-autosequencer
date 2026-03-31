# Data Model: Song Story Tool

**Feature**: 021-song-story-tool | **Date**: 2026-03-30

## Entity Overview

```
SongStory (1)
├── SongIdentity (1)
├── GlobalProperties (1)
├── Preferences (1) — user-set creative direction
├── Section (8-15 per song)
│   ├── SectionCharacter (1 per section)
│   ├── SectionStems (1 per section)
│   ├── SectionLighting (1 per section)
│   └── SectionOverrides (1 per section)
├── Moment (20-30 per song)
├── StemCurves (1, contains 7 curve arrays)
└── ReviewState (1)
```

## Entities

### SongStory

Top-level container for the complete song interpretation.

| Field | Type | Description |
|-------|------|-------------|
| schema_version | string | Format version (initially "1.0.0") |
| song | SongIdentity | Audio file identity and metadata |
| global | GlobalProperties | Song-wide musical properties |
| preferences | Preferences | User-set creative direction (song-wide defaults) |
| sections | Section[] | Ordered list of song sections (8-15 typical) |
| moments | Moment[] | Ranked dramatic moments (20-30 typical) |
| stems | StemCurves | Continuous per-stem data for value curves |
| review | ReviewState | Draft/reviewed status and notes |

**Identity**: Keyed by MD5 hash of audio file content (stored in `song.source_hash`).
**Lifecycle**: Created as "draft" by automatic pipeline → optionally saved during review → exported as "reviewed".

### SongIdentity

| Field | Type | Description |
|-------|------|-------------|
| title | string | From ID3 tags or filename |
| artist | string | From ID3 tags or "Unknown" |
| file | string | Absolute path to source audio file |
| source_hash | string | MD5 hash of audio file content |
| duration_seconds | float | Total duration |
| duration_formatted | string | "MM:SS.mmm" formatted duration |

### GlobalProperties

| Field | Type | Description |
|-------|------|-------------|
| tempo_bpm | float | Estimated tempo |
| tempo_stability | enum | "steady" (<5% CV), "variable" (5-15%), "free" (>15%) |
| key | string | Estimated key (e.g., "C major") |
| key_confidence | float | 0-1 confidence in key estimation |
| energy_arc | enum | ramp, arch, flat, valley, sawtooth, bookend |
| vocal_coverage | float | Fraction of song with active vocals (0-1) |
| harmonic_percussive_ratio | float | Song-wide average H/P ratio |
| onset_density_avg | float | Onsets per second, song-wide average |
| stems_available | string[] | List of available stem names |

**Derivation**:
- `tempo_bpm`: From HierarchyResult.estimated_bpm
- `tempo_stability`: Computed from beat interval coefficient of variation
- `key`: From QMKeyAlgorithm or essentia_features
- `energy_arc`: Computed by energy_arc.py from 10-point energy sampling
- `vocal_coverage`: Ratio of frames where vocals stem RMS > threshold
- `harmonic_percussive_ratio`: From full-mix HPSS analysis
- `onset_density_avg`: From full-mix onset count / duration

### Preferences

Song-wide creative direction set by the user during review. These are defaults — per-section overrides take precedence when set.

| Field | Type | Description |
|-------|------|-------------|
| mood | string or null | Global mood override: "ethereal", "structural", "aggressive", "dark" (null = auto-derive per section) |
| theme | string or null | Global theme lock: force one theme for the whole song (null = auto-select per section) |
| focus_stem | string or null | Global focus stem: "drums", "bass", "vocals", "guitar", "piano", "other" (null = auto from per-section dominant_stem). Boosts the visual weight of this stem's house zone across all sections. |
| intensity | float | Global visual intensity scaler 0.0-2.0 (default 1.0). Multiplied with per-section brightness_ceiling. |
| occasion | string | "general", "christmas", "halloween" (default "general"). Filters available theme pool. |
| genre | string or null | Genre hint for theme selection (null = auto-detect from ID3 tags). |

**Initialization**: All fields start at null/default when the story is first generated. The user sets them during review.

**Precedence**: Per-section overrides > song-wide preferences > auto-derived values. For example:
- Section has `overrides.theme = "Inferno"` → uses Inferno regardless of `preferences.theme`
- Section has `overrides.theme = null`, `preferences.theme = "Aurora"` → uses Aurora
- Both null → auto-select based on mood/genre/occasion

### Section

| Field | Type | Description |
|-------|------|-------------|
| id | string | Stable ID (e.g., "s01", "s02") |
| role | enum | intro, verse, pre_chorus, chorus, post_chorus, bridge, instrumental_break, climax, ambient_bridge, outro, interlude |
| role_confidence | float | 0-1 classifier confidence |
| start | float | Start time in seconds |
| end | float | End time in seconds |
| start_fmt | string | "MM:SS.mmm" formatted start |
| end_fmt | string | "MM:SS.mmm" formatted end |
| duration | float | Duration in seconds |
| character | SectionCharacter | Energy, texture, spectral properties |
| stems | SectionStems | Per-stem activity within this section |
| lighting | SectionLighting | Recommended lighting parameters |
| overrides | SectionOverrides | User review overrides |

**Constraints**:
- Sections are contiguous: section[n].end == section[n+1].start
- No gaps or overlaps
- Minimum duration: 4 seconds
- Ordered by start time

**State transitions**:
- Created by automatic classifier → edited during review (split, merge, rename, boundary adjust) → exported as final

**ID reassignment on structural edits**: When sections are split, merged, or reordered, all section IDs are reassigned sequentially ("s01", "s02", ...). All `Moment.section_id` references are re-bucketed to match the new IDs based on the moment's timestamp falling within each section's time range.

### SectionCharacter

| Field | Type | Description |
|-------|------|-------------|
| energy_level | enum | low, medium, high |
| energy_score | int | 0-100 normalized energy |
| energy_peak | int | 0-100 peak energy within section |
| energy_variance | float | Energy variance within section (high = dynamic, low = wall of sound or quiet sustain) |
| energy_trajectory | enum | rising, falling, stable, oscillating |
| texture | enum | harmonic, percussive, balanced |
| hp_ratio | float | Harmonic/percussive ratio for this section |
| onset_density | float | Full-mix onsets per second in this section |
| spectral_brightness | enum | dark, neutral, bright |
| spectral_centroid_hz | int | Average spectral centroid frequency in Hz |
| spectral_flatness | float | 0-1, where 0=tonal (clean sounds) and 1=noisy (chaotic/textured) |
| local_tempo_bpm | float | Local tempo estimated from beats within this section |
| dominant_note | string | Most energetic pitch class from chroma analysis (e.g., "F#", "C") |
| frequency_bands | dict[string, BandEnergy] | Per-band energy breakdown (sub_bass, bass, low_mid, mid, upper_mid, presence, brilliance) |

**Derivation**:
- `energy_score`: Average of full_mix energy curve frames within section bounds
- `energy_peak`: Max energy curve frame within section bounds
- `energy_variance`: Variance of energy curve frames (from Phase 4A)
- `energy_level`: 0-33=low, 34-66=medium, 67-100=high
- `energy_trajectory`: Linear regression slope of energy frames within section
- `texture`: hp_ratio > 2.0=harmonic, < 0.5=percussive, else balanced
- `spectral_brightness`: Based on spectral centroid percentile (dark <33rd, bright >66th)
- `spectral_centroid_hz`: Mean spectral centroid within section (from Phase 4B)
- `spectral_flatness`: Mean spectral flatness within section (from Phase 4B)
- `local_tempo_bpm`: 60 / mean(beat_intervals) for beats within section (from Phase 4G)
- `dominant_note`: argmax of mean chroma vector within section (from Phase 4E)
- `frequency_bands`: Per-band mean and relative energy within section (from Phase 4F)

### BandEnergy

| Field | Type | Description |
|-------|------|-------------|
| mean | float | Average energy in this band within the section |
| relative | float | Band energy relative to overall section energy (shows which bands dominate) |

Bands: sub_bass (20-60Hz), bass (60-250Hz), low_mid (250-500Hz), mid (500-2kHz), upper_mid (2k-4kHz), presence (4k-6kHz), brilliance (6k-20kHz)

### SectionStems

| Field | Type | Description |
|-------|------|-------------|
| vocals_active | bool | Whether vocals are present in this section |
| dominant_stem | string | Stem with highest average RMS |
| active_stems | string[] | Stems with RMS above activity threshold |
| stem_levels | dict[string, float] | Per-stem relative RMS, normalized 0-1 within section |
| onset_counts | dict[string, int] | Per-stem onset count within section time range |
| leader_stem | string | Stem that holds leadership for the longest duration in this section |
| leader_transitions | LeaderTransition[] | Moments where the dominant stem changes within this section |
| solos | SoloRegion[] | Solo regions (8s+ where one stem dominates) that overlap this section |
| drum_pattern | DrumPattern or null | Kick/snare/hihat onset summary (null if drums inactive) |
| tightness | string or null | Kick-bass rhythmic sync: "unison", "independent", "mixed" (null if drums or bass inactive) |
| handoffs | HandoffEvent[] | Melodic stem transitions within this section (e.g., vocals→guitar) |
| chords | ChordChange[] | Chord changes within this section's time range |
| other_stem_class | string or null | Classification of "other" stem: "spatial", "timing", "ambiguous" (null if other stem inactive) |

**Derivation**:
- `vocals_active`: True if vocals stem average RMS > vocal activity threshold
- `dominant_stem`: argmax of average RMS across stems
- `active_stems`: Stems with average RMS > 10% of max stem RMS in section
- `stem_levels`: Each stem's average RMS divided by the section's max stem RMS
- `onset_counts`: Count of L4 events per stem within section [start, end)
- `leader_stem`: From InteractionResult.leader_track — count frames per stem in section, pick majority
- `leader_transitions`: Filter InteractionResult.leader_track.transitions to section time range
- `solos`: Filter HierarchyResult.solos entries whose [time_ms, time_ms+duration_ms] overlaps section
- `drum_pattern`: From L4 drums events — count kick/snare/hihat onsets, compute ratios and density
- `tightness`: From InteractionResult.tightness — average tightness windows overlapping section
- `handoffs`: Filter InteractionResult.handoffs to section time range
- `chords`: Filter L6 chords TimingTrack marks to section time range
- `other_stem_class`: From InteractionResult.other_stem_class (global, copied per section)

### LeaderTransition

| Field | Type | Description |
|-------|------|-------------|
| time | float | Timestamp in seconds |
| from_stem | string | Previous dominant stem |
| to_stem | string | New dominant stem |

### SoloRegion

| Field | Type | Description |
|-------|------|-------------|
| stem | string | Which stem is soloing |
| start | float | Solo start time in seconds |
| end | float | Solo end time in seconds |
| prominence | float | 0-1, how dominant the stem was during the solo |

### DrumPattern

| Field | Type | Description |
|-------|------|-------------|
| kick_count | int | Number of kick drum onsets in section |
| snare_count | int | Number of snare onsets in section |
| hihat_count | int | Number of hihat onsets in section |
| total_density | float | Total drum onsets per second |
| dominant_element | string | "kick", "snare", or "hihat" — whichever has the most onsets |
| style | string | "driving" (high kick density), "fills" (high snare density), "riding" (high hihat density), "sparse" (low total density), "balanced" |

**DrumPattern.style derivation**:
- total_density < 1.0/sec → "sparse"
- kick_count > 50% of total → "driving"
- snare_count > 40% of total → "fills"
- hihat_count > 60% of total → "riding"
- else → "balanced"

### HandoffEvent

| Field | Type | Description |
|-------|------|-------------|
| time | float | Handoff midpoint in seconds |
| from_stem | string | Stem that drops out |
| to_stem | string | Stem that enters |
| confidence | float | 0-1, based on gap duration (1.0 = seamless, 0.0 = large gap) |

### ChordChange

| Field | Type | Description |
|-------|------|-------------|
| time | float | Timestamp in seconds |
| chord | string | Chord label (e.g., "Cmaj7", "Am", "F#dim") |

### SectionLighting

| Field | Type | Description |
|-------|------|-------------|
| active_tiers | int[] | Which tiers (1-8) should be active |
| brightness_ceiling | float | 0-1 max brightness for this section |
| theme_layer_mode | enum | base_only, base_mid, full, variant |
| use_secondary_theme | bool | True for non-vocal sections with user-assigned secondary |
| transition_in | enum | hard_cut, quick_fade, crossfade, snap_on, quick_build |
| moment_count | int | Number of moments in this section |
| moment_pattern | enum | isolated, plateau, cascade, scattered (dominant pattern) |
| beat_effect_density | float | 0-1 how many beats should trigger effects |

**Derivation**: Pure function of `section.role` + `section.character.energy_level`. See lighting_mapper.py.

### SectionOverrides

| Field | Type | Description |
|-------|------|-------------|
| role | string or null | User-overridden role (null = use classified role) |
| energy_level | string or null | User-overridden energy level |
| mood | string or null | User-overridden mood tier: "ethereal", "structural", "aggressive", "dark" (null = auto-derive from energy_level + key) |
| theme | string or null | User-assigned theme name for this section (null = auto-select based on mood/genre/occasion). One of the 21 built-in themes or a custom theme name. |
| focus_stem | string or null | User-designated focus stem for this section: "drums", "bass", "vocals", "guitar", "piano", "other" (null = auto from dominant_stem). Boosts the visual weight of the associated house zone. |
| intensity | float or null | Visual intensity scaler 0.0-2.0 (null = 1.0 default). Multiplies brightness_ceiling. Values <1.0 calm it down, >1.0 push it harder. |
| notes | string or null | Free-text annotation |
| is_highlight | bool | User-designated peak moment of the song |

**How overrides affect downstream generation**:
- `mood` → determines which themes are eligible (ethereal pool, structural pool, aggressive pool, dark pool)
- `theme` → forces a specific theme, skipping mood-based selection entirely
- `focus_stem` → generator boosts the house zone mapped to this stem (vocals=center, drums=roofline, bass=ground, guitar=arches/sides) by increasing brightness and tier priority for groups in that zone
- `intensity` → multiplied with `lighting.brightness_ceiling` to produce final brightness; clipped to [0.0, 1.0]

### Moment

| Field | Type | Description |
|-------|------|-------------|
| id | string | Stable ID (e.g., "m001") |
| time | float | Timestamp in seconds |
| time_fmt | string | "MM:SS.mmm" formatted |
| section_id | string | Which section this belongs to |
| type | enum | energy_surge, energy_drop, percussive_impact, brightness_spike, tempo_change, silence, vocal_entry, vocal_exit, texture_shift, handoff |
| stem | string | Source stem (or "full_mix") |
| intensity | float | Raw intensity value |
| description | string | Human-readable description |
| pattern | enum | isolated, plateau, cascade, double_tap, scattered |
| rank | int | Importance rank (1 = most important) |
| dismissed | bool | User can dismiss to exclude from generation |

**Constraints**:
- Moments are ordered by time
- Rank is unique within the song (1 to N)
- Dismissed moments are preserved in the file but excluded from downstream generation

**Ranking formula**: `intensity_percentile * type_weight * pattern_multiplier * boundary_multiplier`
- Type weights: silence=1.0, energy_drop=0.9, vocal_entry=0.85, energy_surge=0.8, percussive_impact=0.7, handoff=0.6, brightness_spike=0.5, texture_shift=0.4, tempo_change=0.3

**Moment type derivations**:
- `energy_surge`, `energy_drop`, `percussive_impact`, `brightness_spike`: From HierarchyResult.energy_impacts and energy_drops (L0 data)
- `silence`: From HierarchyResult.gaps
- `vocal_entry`: Vocals stem RMS crosses above activity threshold
- `vocal_exit`: Vocals stem RMS crosses below activity threshold
- `texture_shift`: Harmonic/percussive ratio changes significantly (>0.5) within a 1-second window
- `handoff`: Dominant stem changes between consecutive analysis windows (from HierarchyResult.interactions leader_transitions, if available; omitted when interaction data is absent)
- `tempo_change`: Beat interval changes by >10% between adjacent windows
- Pattern multiplier: isolated=1.5, all others=1.0
- Boundary multiplier: at section boundary=1.3, not=1.0

### StemCurves

| Field | Type | Description |
|-------|------|-------------|
| sample_rate_hz | int | Fixed at 2 (0.5-second intervals) |
| drums | CurveData | Drums stem curves |
| bass | CurveData | Bass stem curves |
| vocals | CurveData | Vocals stem curves |
| guitar | CurveData | Guitar stem curves |
| piano | CurveData | Piano stem curves |
| other | CurveData | Other stem curves |
| full_mix | FullMixCurveData | Full mix curves (extended) |

**CurveData**: `{ rms: float[] }` — one RMS value per 0.5-second interval.

**FullMixCurveData**: `{ rms: float[], spectral_centroid_hz: float[], harmonic_rms: float[], percussive_rms: float[] }`

**Derivation**: Downsample existing ValueCurve data (typically 10 fps) to 2Hz by averaging frames within each 0.5-second window.

### ReviewState

| Field | Type | Description |
|-------|------|-------------|
| status | enum | "draft" (auto-generated), "reviewed" (user exported) |
| reviewed_at | string or null | ISO timestamp when user clicked Export |
| reviewer_notes | string or null | Free-text overall notes |

**State transitions**: draft → (user saves edits, stays draft) → (user exports) → reviewed

## File Architecture: Two-File Split

The song story uses a **two-file architecture** to separate auto-generated data from user edits:

### Base Story File: `<audio_stem>_story.json`

Contains only the auto-generated interpretation. **Never modified by user actions.** Re-running `xlight-analyze story` overwrites this file (with force flag if it exists).

Contents: `schema_version`, `song`, `global`, `sections` (with auto-classified roles, character, stems, lighting — but `overrides` all null), `moments` (all `dismissed=false`), `stems`, `review` (status="draft"), `preferences` (all defaults).

### Edits File: `<audio_stem>_story_edits.json`

Contains only user modifications — everything the user changed during review. **Created on first Save, updated on subsequent saves.** Export merges base + edits into the final output.

```json
{
  "schema_version": "1.0.0",
  "source_hash": "<md5>",
  "base_story_hash": "<md5 of base _story.json at time of first edit>",
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp",

  "preferences": { ... },

  "section_edits": [
    {
      "section_id": "s03",
      "action": "rename",
      "original_role": "verse",
      "new_role": "pre_chorus",
      "overrides": { "mood": "structural", "theme": "Inferno", "focus_stem": "guitar", "intensity": 1.2, "notes": "guitar riff kicks in here" }
    },
    {
      "section_id": "s05",
      "action": "split",
      "split_time": 45.2,
      "original_start": 38.0,
      "original_end": 55.0
    },
    {
      "section_id": "s07",
      "action": "merge",
      "merged_with": "s08"
    },
    {
      "section_id": "s04",
      "action": "boundary",
      "original_end": 36.94,
      "new_end": 38.00
    },
    {
      "section_id": "s02",
      "action": "override",
      "overrides": { "is_highlight": true }
    }
  ],

  "moment_edits": [
    { "moment_id": "m005", "dismissed": true },
    { "moment_id": "m012", "dismissed": true }
  ],

  "reviewer_notes": "The chorus detection was spot on but verses 2 and 3 were labeled as bridges"
}
```

### Why Two Files?

1. **Algorithm feedback**: By diffing the edits against the base, we can see exactly where the classifier was wrong — which roles the user corrected, which moments were false positives, which boundaries were moved. This data can feed back into tuning classification thresholds.
2. **Re-generation safety**: If the user re-runs the analysis (with updated algorithms or parameters), the base story updates but the edits file is preserved. The review UI can show "your edits from last time" and let the user re-apply or discard them.
3. **Clean separation of concerns**: The base file is reproducible (same audio + same config = same output, per constitution principle I). The edits file is the human layer.

### Export Produces a Merged File

When the user clicks Export, the system merges base + edits into a final `<audio_stem>_story_reviewed.json` with:
- `review.status = "reviewed"`
- All section edits applied (splits, merges, renames, overrides)
- All moment dismissals applied
- Preferences set
- The reviewed file is what the generator consumes

### File Layout

```
/music/
├── Magic.mp3
├── Magic_hierarchy.json         # existing analysis cache
├── Magic_story.json             # base auto-generated story (never user-modified)
├── Magic_story_edits.json       # user edits only (created on first Save)
├── Magic_story_reviewed.json    # merged final output (created on Export)
└── .stems/<md5>/                # existing stem cache
```

## Relationships

- SongStory 1:N Section (ordered, contiguous)
- SongStory 1:N Moment (ordered by time)
- Section 1:N Moment (via section_id)
- SongStory 1:1 StemCurves
- SongStory 1:1 ReviewState
- SongStory 1:1 Preferences
- SongStory 1:1 GlobalProperties
- SongStory 1:1 SongIdentity
- Base Story 1:0..1 Edits File (edits reference base via source_hash + base_story_hash)
