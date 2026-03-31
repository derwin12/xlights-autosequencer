# Song Story Tool — Specification

## Purpose

A single tool that answers "what IS this song?" — taking raw audio and producing a curated, human-reviewed narrative that everything downstream consumes. It replaces the scattered analysis-to-generator handoff with one clear contract.

## Problem Statement

Today the pipeline has a data cliff:
- The analyzer produces rich per-stem data (energy curves, onsets, interactions, solos, spectral features)
- The generator boils it all down to one number per section (energy_score 0-100) and one label (ethereal/structural/aggressive)
- The user has no opportunity to see or correct the interpretation before effects are placed

The song story tool fills this gap. It sits between raw analysis and sequence generation, producing an interpretation of the song that is both machine-readable (for the generator) and human-readable (for the user to review and correct).

## Two Phases

### Phase 1: Compute (Automatic)

Input: MP3 file path
Output: Draft song story JSON

Pipeline:
1. Load audio, separate into stems (drums, bass, vocals, guitar, piano, other)
2. Run per-stem feature extraction (RMS, onsets, spectral, MFCCs, beats)
3. Run full-mix feature extraction (same + HPSS, chroma, frequency bands)
4. Detect section boundaries using stem-weighted novelty + vocal activity
5. Classify each section's role (intro, verse, chorus, bridge, etc.)
6. Profile each section (energy, texture, dominant stem, active stems)
7. Detect and classify dramatic moments (isolated spike, sustained plateau, cascade, etc.)
8. Detect the global energy arc shape (ramp, arch, valley, etc.)
9. Assemble into song story JSON

### Phase 2: Review (Interactive)

Input: Draft song story JSON + original MP3
Output: Reviewed/approved song story JSON

Interface (browser-based, Flask + Canvas + Web Audio):
- Audio playback with waveform/timeline visualization
- Sections displayed as labeled blocks on the timeline
- Current section highlights during playback, showing its classification and character
- User can:
  - Rename section roles (e.g., "verse" → "pre_chorus")
  - Adjust section boundary times (drag edges)
  - Merge adjacent sections
  - Split a section at a timestamp
  - Override energy level classification
  - Mark/unmark dramatic moments as significant
  - Add free-text notes to any section
  - Flag sections for special treatment ("this is THE moment of the song")
- Export produces the final reviewed song story JSON

The reviewed JSON is the single source of truth for downstream tools. If the user didn't review it, the draft is used as-is.

---

## Output Contract: Song Story JSON

### Top Level

```jsonc
{
  // ── Identity ──
  "schema_version": "1.0.0",
  "song": {
    "title": "string",
    "artist": "string",           // from ID3 tags or filename
    "file": "/path/to/song.mp3",
    "duration_seconds": 209.07,
    "duration_formatted": "03:29.065"
  },

  // ── Global Character ──
  "global": {
    "tempo_bpm": 152.0,
    "tempo_stability": "steady",  // "steady" (<5% CV), "variable" (5-15%), "free" (>15%)
    "key": "C major",
    "key_confidence": 0.84,
    "energy_arc": "arch",         // ramp|arch|flat|valley|sawtooth|bookend
    "vocal_coverage": 0.65,       // fraction of song duration with active vocals
    "harmonic_percussive_ratio": 2.45,
    "onset_density_avg": 2.1,     // onsets per second, song-wide average
    "stems_available": ["drums", "bass", "vocals", "guitar", "piano", "other"]
  },

  // ── The Story: Sections ──
  "sections": [
    // See Section Object below
  ],

  // ── Dramatic Moments (song-wide, classified) ──
  "moments": [
    // See Moment Object below
  ],

  // ── Continuous Data (for value curves) ──
  "stems": {
    // See Stem Curves below
  },

  // ── Review State ──
  "review": {
    "status": "draft",            // "draft" (auto-generated) | "reviewed" (user approved)
    "reviewed_at": null,          // ISO timestamp when user approved
    "reviewer_notes": null        // free-text overall notes
  }
}
```

### Section Object

Each section is a meaningful chunk of the song — typically 8-15 sections for a 3-5 minute song. Not micro-segments from beat-level analysis, but the sections a human would describe: "intro, verse 1, pre-chorus, chorus, verse 2..."

```jsonc
{
  "id": "s01",                    // stable ID for references and overrides
  "role": "verse",                // intro|verse|pre_chorus|chorus|post_chorus|
                                  // bridge|instrumental_break|climax|
                                  // ambient_bridge|outro|interlude
  "role_confidence": 0.75,        // how confident the classifier was (0-1)
  "start": 13.75,                 // seconds
  "end": 36.94,                   // seconds
  "start_fmt": "00:13.750",
  "end_fmt": "00:36.943",
  "duration": 23.19,

  // ── What It Sounds Like ──
  "character": {
    "energy_level": "medium",     // low|medium|high
    "energy_score": 58,           // 0-100 normalized
    "energy_trajectory": "rising",// rising|falling|stable|oscillating
    "texture": "harmonic",        // harmonic|percussive|balanced
    "hp_ratio": 3.24,
    "onset_density": 1.7,         // onsets per second in this section
    "spectral_brightness": "bright" // dark|neutral|bright
  },

  // ── Who's Playing ──
  "stems": {
    "vocals_active": true,
    "dominant_stem": "vocals",    // which stem has highest average RMS
    "active_stems": ["drums", "bass", "vocals", "guitar", "other"],
    "stem_levels": {              // relative RMS per stem, normalized 0-1 within section
      "drums": 0.35,
      "bass": 0.42,
      "vocals": 0.85,
      "guitar": 0.15,
      "piano": 0.05,
      "other": 0.60
    }
  },

  // ── How It Should Feel (lighting guidance) ──
  "lighting": {
    "active_tiers": [1, 2, 4, 6],          // which tiers the framework recommends
    "brightness_ceiling": 0.60,             // 0-1, max brightness for this section
    "theme_layer_mode": "base_mid",         // base_only|base_mid|full|variant
    "use_secondary_theme": false,           // true if non-vocal + user assigned secondary
    "transition_in": "quick_build",         // how to enter this section
                                            // hard_cut|quick_fade|crossfade|snap_on|quick_build
    "moment_count": 6,                      // dramatic moments in this section
    "moment_pattern": "scattered",          // dominant pattern: isolated|plateau|cascade|scattered
    "beat_effect_density": 0.7              // 0-1, how many beats should trigger effects
  },

  // ── User Overrides (populated during review) ──
  "overrides": {
    "role": null,                 // user can override the classified role
    "energy_level": null,         // user can override energy classification
    "notes": null,                // free-text: "this is where the guitar riff kicks in"
    "is_highlight": false         // user flags this as THE moment of the song
  }
}
```

### Moment Object

Dramatic moments, classified by their temporal pattern. Only the significant ones — not every 97th-percentile blip, but the ones that should drive visual events.

```jsonc
{
  "id": "m001",
  "time": 45.836,
  "time_fmt": "00:45.836",
  "section_id": "s04",           // which section this belongs to

  // ── What Happened ──
  "type": "energy_drop",         // energy_surge|energy_drop|percussive_impact|
                                 // brightness_spike|tempo_change|silence|
                                 // vocal_entry|vocal_exit|texture_shift|handoff
  "stem": "full_mix",            // which stem this was detected on
  "intensity": 1.84,             // raw intensity value
  "description": "Sudden energy decrease",

  // ── How It Behaves in Context ──
  "pattern": "isolated",         // isolated|plateau|cascade|double_tap|breathing
  "rank": 3,                     // importance rank within the song (1 = most important)

  // ── User Override ──
  "dismissed": false             // user can dismiss moments they don't want to trigger effects
}
```

### Stem Curves

Continuous per-stem data sampled at regular intervals, used for value curve routing downstream. The generator binds these to effect parameters (bass RMS → fire height, vocal RMS → wash brightness, etc.).

```jsonc
{
  "sample_rate_hz": 2,           // samples per second (0.5s intervals)
  "drums":  { "rms": [0.01, 0.02, ...] },
  "bass":   { "rms": [0.03, 0.04, ...] },
  "vocals": { "rms": [0.00, 0.00, 0.05, ...] },
  "guitar": { "rms": [0.01, 0.01, ...] },
  "piano":  { "rms": [0.00, 0.00, ...] },
  "other":  { "rms": [0.04, 0.05, ...] },
  "full_mix": {
    "rms": [0.05, 0.06, ...],
    "spectral_centroid_hz": [1800, 2100, ...],
    "harmonic_rms": [0.03, 0.04, ...],
    "percussive_rms": [0.02, 0.02, ...]
  }
}
```

---

## Section Classification Logic

### Merging Micro-Segments into Meaningful Sections

The raw analysis may produce 20-40 boundary points. The song story collapses these into 8-15 sections that a human would recognize. Merge rules:

1. **Minimum section duration**: 4 seconds. Any section shorter than this is merged with its neighbor (prefer merging with the more similar neighbor by energy/texture).
2. **Same-role merge**: Adjacent sections classified with the same role AND similar energy (within 15 points) are merged. Two consecutive "verse" sections that sound the same become one verse.
3. **Vocal continuity**: If vocals are continuously active across a boundary, and neither side has a significant energy change (>0.15 normalized), merge. Vocal phrases shouldn't be split into separate sections.
4. **Target count**: Aim for 8-15 sections. If above 15, increase the merge threshold. If below 8, lower it (allow smaller energy differences to create boundaries).

### Role Assignment

Uses the three-signal approach from the framework doc:

**Primary — Vocal activity**:
- No vocals + position < 15% → intro
- No vocals + position > 85% → outro
- No vocals + drums active → instrumental_break
- No vocals + drums quiet → ambient_bridge

**Secondary — Energy relative to vocal sections**:
- Vocal energy > 75th percentile of all vocal sections → chorus candidate
- Vocal energy < 40th percentile → verse candidate
- Energy rising into next section → pre_chorus
- Energy just dropped from chorus → post_chorus

**Tertiary — Repetition**:
- If a section's MFCC profile matches a previously classified section (cosine similarity > 0.85), inherit that role. Second occurrence of a chorus melody = another chorus.

**Override — Global peak**:
- The section with the highest sustained energy (not just a single spike) that also has vocals active → climax

### Energy Arc Detection

Sample energy at 10 evenly-spaced points through the song. Compute the shape:

| Test | Condition | Arc |
|------|-----------|-----|
| Monotonic increase | Each sample > previous (within tolerance) | ramp |
| Peak in middle 40-70% | Max sample is in positions 4-7, endpoints lower | arch |
| Low variance | Standard deviation of samples < 10% of mean | flat |
| Dip in middle | Min sample is in positions 3-7, endpoints higher | valley |
| Multiple peaks | 2+ local maxima with >20% drops between them | sawtooth |
| Low endpoints, active middle | Samples 0-1 and 8-9 below 30th percentile | bookend |

### Moment Classification

For each dramatic moment, look at temporal neighbors of the same type:

```
window = same-type moments within ±5 seconds
if len(window) == 1:
  pattern = "isolated"
elif len(window) == 2 and time_gap < 0.5s:
  pattern = "double_tap"
elif len(window) >= 3 and all above 75th percentile:
  if intensity spread < 20% of max: pattern = "plateau"
  elif monotonically increasing: pattern = "cascade"
  else: pattern = "plateau"
else:
  pattern = "scattered"
```

### Moment Ranking

Not all moments are equal. Rank by:

1. **Intensity percentile** within its type (a 99th-percentile energy surge outranks a 97th-percentile one)
2. **Type weight**: silence (1.0) > energy_drop (0.9) > vocal_entry (0.85) > energy_surge (0.8) > percussive_impact (0.7) > brightness_spike (0.5) > texture_shift (0.4) > tempo_change (0.3)
3. **Isolation bonus**: Isolated moments get a 1.5x multiplier (they stand out more perceptually)
4. **Section role bonus**: Moments at section boundaries get a 1.3x multiplier

Final rank = sort by `intensity_percentile * type_weight * pattern_multiplier * boundary_multiplier`, take top 20-30 for the song.

---

## Review Interface

### Layout

```
+------------------------------------------------------------------+
| Song Story: Magic [feat. David Archuleta]         [Export] [Save] |
+------------------------------------------------------------------+
|                                                                    |
|  [Play] [Pause]  00:45.2 / 03:29.1    [<< Prev Section] [Next >>]|
|                                                                    |
|  ┌──────────────────────────────────────────────────────────────┐  |
|  │ ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁  (waveform)                                │  |
|  │ |intro|  verse 1   | chorus  |brk|  verse 2  | climax |outro│  |
|  │       ↑ playhead                                              │  |
|  └──────────────────────────────────────────────────────────────┘  |
|                                                                    |
|  ┌─ Current Section ──────────────────────────────────────────┐   |
|  │  VERSE 1  (00:13.7 → 00:36.9)  23.2s                      │   |
|  │                                                             │   |
|  │  Energy: MEDIUM (58/100, rising)                            │   |
|  │  Texture: harmonic (H/P 3.24)                               │   |
|  │  Vocals: ACTIVE, dominant                                   │   |
|  │  Active stems: drums bass vocals guitar other               │   |
|  │  Onset density: 1.7/sec                                     │   |
|  │                                                             │   |
|  │  Lighting: Tiers 1,2,4,6 | Ceiling 60% | base_mid layers   │   |
|  │  Transition in: quick_build | 6 moments (scattered)         │   |
|  │                                                             │   |
|  │  [Rename Role ▼]  [Split Here]  [Merge →]  [★ Highlight]   │   |
|  │  Notes: ________________________________________            │   |
|  └─────────────────────────────────────────────────────────────┘   |
|                                                                    |
|  ┌─ Stems ────────────────────────────────────────────────────┐   |
|  │  drums   ▁▁▃▅▅▅▅▅▃▁▁  (mini RMS waveform per stem)        │   |
|  │  bass    ▁▂▄▅▅▅▅▄▃▂▁                                       │   |
|  │  vocals  ▁▁▁▃▆█▇▅▃▁▁  ← dominant                          │   |
|  │  guitar  ▁▁▁▁▂▂▂▁▁▁▁                                       │   |
|  │  piano   ▁▁▁▁▁▁▁▁▁▁▁                                       │   |
|  │  other   ▂▃▄▅▅▅▅▅▄▃▂                                       │   |
|  └─────────────────────────────────────────────────────────────┘   |
|                                                                    |
|  ┌─ Moments in Section ──────────────────────────────────────┐    |
|  │  00:21.1  brightness_spike  vocals   3.51  isolated  [x]  │    |
|  │  00:25.8  energy_surge      full_mix 1.07  isolated  [x]  │    |
|  │  00:29.5  percussive_impact drums    8.89  double_tap[x]  │    |
|  │  00:29.8  percussive_impact drums   13.63  double_tap[x]  │    |
|  │  ...                                              [x]=keep │    |
|  └─────────────────────────────────────────────────────────────┘   |
+--------------------------------------------------------------------+
```

### Interactions

| Action | What Happens |
|--------|-------------|
| Click a section on the timeline | Jumps playback there, shows section details |
| Drag section boundary | Adjusts start/end times, re-profiles the affected sections |
| "Rename Role" dropdown | Changes section role, which updates lighting recommendations |
| "Split Here" button | Splits current section at playhead position, creates two sections |
| "Merge →" button | Merges current section with the next one |
| "Highlight" toggle | Marks section as the user-designated peak moment |
| Dismiss moment (x) | Marks a dramatic moment as dismissed (won't trigger effects) |
| Notes field | Free-text annotation stored in overrides |
| Export button | Writes final reviewed JSON with review.status = "reviewed" |

### What Changes When User Edits

When the user changes a section role:
- `lighting.active_tiers` recalculates based on the role table from the framework
- `lighting.brightness_ceiling` updates
- `lighting.theme_layer_mode` updates
- The section's `overrides.role` is set (preserving the original classification)

When the user splits/merges sections:
- Feature profiles (energy, texture, stems) are recomputed for the affected sections
- Moment assignments are re-bucketed by section
- IDs are reassigned

When the user adjusts a boundary:
- Both adjacent sections are re-profiled
- Moments near the boundary may shift between sections

---

## CLI Interface

```bash
# Phase 1: Generate draft song story
xlight-analyze story <audio.mp3> [--output story.json]

# Phase 2: Review in browser
xlight-analyze story-review <story.json> [--port 5174]

# Pipeline: generate + open review immediately
xlight-analyze story <audio.mp3> --review
```

The `story` command:
1. Checks for cached stems (`.stems/<md5>/`)
2. Runs stem separation if needed (demucs htdemucs_6s)
3. Runs per-stem + full-mix feature extraction
4. Runs section detection, classification, moment detection
5. Writes song story JSON
6. If `--review` flag, launches Flask review server and opens browser

The `story-review` command:
1. Loads an existing song story JSON
2. Serves the review UI at localhost
3. On export, writes the reviewed JSON (same path or user-specified)

---

## Downstream Contract

The song story JSON is the input for sequence generation. The generator should:

1. Read `sections[].role` and `sections[].lighting` to determine tier activation, brightness, and theme layer mode
2. Read `sections[].stems` to route per-stem curves to effect parameters
3. Read `moments[]` (excluding dismissed ones) to place event-triggered effects
4. Read `moments[].pattern` to decide between sustained vs. one-shot effects
5. Read `global.energy_arc` to set headroom strategy
6. Read `global.tempo_stability` to decide beat-sync tightness
7. Read `stems` curves for value curve binding (bass → fire height, etc.)
8. Respect `sections[].overrides` — any user override takes precedence over computed values

The generator never re-derives energy scores or section roles. The song story is the single source of truth.

---

## What This Replaces

| Current Pipeline Step | Replaced By |
|----------------------|-------------|
| `run_orchestrator()` → HierarchyResult | Song story Phase 1 (incorporates orchestrator + stem analysis + classification) |
| `derive_section_energies()` | Song story `sections[].character.energy_score` |
| `select_themes()` mood_tier input | Song story `sections[].role` + `sections[].lighting.theme_layer_mode` |
| `place_effects()` energy-only density | Song story `sections[].lighting` (active_tiers, brightness_ceiling, moment_pattern, beat_effect_density) |
| Manual `--theme-override` CLI flags | Review UI role/override editing |

The song story doesn't replace the theme system, the effect catalog, or the XSQ writer. It replaces the **interpretation layer** — the part that decides what each section of the song IS and how it should be treated.

---

## Open Questions

1. **Should the song story include beat/bar grid data?** The generator needs beat times for T4 chase placement. Include them in the story, or let the generator access them separately from the analysis cache?

2. **Should the stem curves be in the story JSON or referenced as separate files?** For a 5-minute song at 2Hz, each curve is ~600 floats — manageable inline. At higher sample rates (20Hz) it gets large (6000 floats per stem × 7 stems = 42,000 values).

3. **Should the review UI show the lighting tier recommendations visually?** E.g., a stack of tier bars that light up/dim based on the section's active_tiers. This would help users understand the downstream impact of their role choices.

4. **Should there be a "confidence threshold" below which sections are automatically flagged for review?** E.g., any section with role_confidence < 0.5 gets a warning icon in the review UI.

5. **How does this interact with the existing `xlight-analyze review` command?** That shows raw timing tracks. This shows interpreted song structure. They serve different purposes. Should they be separate tools or modes of the same review UI?
