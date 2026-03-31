# Song Story JSON Contract

**Feature**: 021-song-story-tool | **Date**: 2026-03-30

This document defines the JSON structure that the song story tool produces and the sequence generator consumes. This is the single source of truth contract between interpretation and generation.

## File Location (Two-File Architecture)

| File | Purpose | Modified By |
|------|---------|-------------|
| `<audio_stem>_story.json` | Base auto-generated story | Story builder only (never by user) |
| `<audio_stem>_story_edits.json` | User edits (diffs from base) | Review UI Save button |
| `<audio_stem>_story_reviewed.json` | Merged final output | Review UI Export button |

Example: `/music/Magic.mp3` → `/music/Magic_story.json`, `/music/Magic_story_edits.json`, `/music/Magic_story_reviewed.json`

The generator looks for `_story_reviewed.json` first, falls back to `_story.json`.

## Schema Version

Current: `1.0.0`

The `schema_version` field is always present at the top level. Consumers MUST check this field and handle unknown versions gracefully (warn and attempt best-effort parsing, or reject).

## Top-Level Structure

```json
{
  "schema_version": "1.0.0",
  "song": { ... },
  "global": { ... },
  "preferences": { ... },
  "sections": [ ... ],
  "moments": [ ... ],
  "stems": { ... },
  "review": { ... }
}
```

All top-level keys are required. See [data-model.md](../data-model.md) for full field definitions.

## Consumer Contract (Generator)

The sequence generator MUST read the song story as follows:

### 1. Section Roles and Lighting

```
For each section in story["sections"]:
    role = section["overrides"]["role"] or section["role"]
    energy = section["overrides"]["energy_level"] or section["character"]["energy_level"]
    tiers = section["lighting"]["active_tiers"]
    brightness = section["lighting"]["brightness_ceiling"]
    layer_mode = section["lighting"]["theme_layer_mode"]
    transition = section["lighting"]["transition_in"]
    beat_density = section["lighting"]["beat_effect_density"]
```

The generator MUST NOT re-derive energy scores or section roles. The story is authoritative.

### 1b. Per-Section Stem Detail and Musical Character

```
For each section in story["sections"]:
    # Stem activity
    drum_style = section["stems"]["drum_pattern"]["style"]  # driving/fills/riding/sparse/balanced
    leader = section["stems"]["leader_stem"]
    tightness = section["stems"]["tightness"]  # unison/independent/mixed/null
    solos = section["stems"]["solos"]           # solo regions in this section
    handoffs = section["stems"]["handoffs"]     # melodic stem transitions

    # Musical character
    flatness = section["character"]["spectral_flatness"]  # 0=tonal, 1=noisy
    local_tempo = section["character"]["local_tempo_bpm"]
    dominant_note = section["character"]["dominant_note"]
    bands = section["character"]["frequency_bands"]  # per-band energy breakdown
    variance = section["character"]["energy_variance"]  # dynamic vs wall-of-sound

    # Use for effect selection:
    #   drum_style="driving" + tightness="unison" → heavy beat-sync effects
    #   solos present → spotlight hero tier on solo stem
    #   handoffs present → shift visual emphasis between zones
    #   high flatness → chaotic effects (shimmer, strobe)
    #   low flatness → clean effects (solid wash, chase)
    #   dominant bass bands → drive floor-level props
```

### 2. Dramatic Moments

```
For each moment in story["moments"]:
    if moment["dismissed"]: skip
    Use moment["type"] and moment["pattern"] to select effect type:
        - isolated → one-shot effect (flash, strobe burst)
        - plateau → sustained effect (hold brightness)
        - cascade → sequential effect (build across groups)
        - double_tap → double-trigger effect
        - scattered → ambient pulse
    Use moment["rank"] for priority when moments compete for visual resources.
```

### 3. Stem Curves for Value Curves

```
For value curve binding:
    bass_rms = story["stems"]["bass"]["rms"]
    vocal_rms = story["stems"]["vocals"]["rms"]
    drum_rms = story["stems"]["drums"]["rms"]
    ...

    Sample rate is story["stems"]["sample_rate_hz"] (always 2).
    Index into array: frame_index = floor(time_seconds * sample_rate_hz)
```

### 4. Global Properties

```
tempo = story["global"]["tempo_bpm"]
stability = story["global"]["tempo_stability"]
    → "steady": tight beat sync
    → "variable": loose beat sync
    → "free": no beat sync

arc = story["global"]["energy_arc"]
    → Headroom strategy (e.g., "ramp" → reserve brightness for end)
```

### 5. User Highlights

```
For each section where section["overrides"]["is_highlight"] == true:
    This is the user-designated peak moment.
    Override: max tiers, max brightness, hero effects.
```

### 6. Creative Preferences (three-level precedence)

```
For each section:
    # Mood: per-section > song-wide > auto-derived
    mood = section["overrides"]["mood"]
           or story["preferences"]["mood"]
           or derive_from(section["character"]["energy_level"], story["global"]["key"])

    # Theme: per-section > song-wide > auto-select by mood+genre+occasion
    theme = section["overrides"]["theme"]
            or story["preferences"]["theme"]
            or select_theme(mood, genre, occasion)

    # Focus stem: per-section > song-wide > section's dominant_stem
    focus = section["overrides"]["focus_stem"]
            or story["preferences"]["focus_stem"]
            or section["stems"]["dominant_stem"]
    → Boost house zone mapped to focus stem:
        vocals=center, drums=roofline, bass=ground,
        guitar=arches/sides, piano=accents, other=background

    # Intensity: per-section × song-wide (multiplicative)
    section_intensity = (section["overrides"]["intensity"] or 1.0)
    global_intensity = story["preferences"]["intensity"]  # default 1.0
    final_brightness = section["lighting"]["brightness_ceiling"]
                       * section_intensity * global_intensity
    final_brightness = clamp(final_brightness, 0.0, 1.0)

    # Occasion + Genre: song-wide only (no per-section override)
    occasion = story["preferences"]["occasion"]  # default "general"
    genre = story["preferences"]["genre"]         # default from ID3 tags
```

## Backward Compatibility

When no song story file exists for an audio file, the generator MUST fall back to the existing `derive_section_energies()` → `select_themes()` pipeline. The song story is optional during the transition period.

## Validation Rules

- `sections` must be non-empty
- Sections must be contiguous (section[n].end == section[n+1].start, within 1ms tolerance)
- All `section_id` references in moments must point to existing sections
- `moments` must be sorted by time
- `stems.sample_rate_hz` must equal 2
- All stem curve arrays must have the same length: `ceil(song.duration_seconds * 2)`
- `review.status` must be "draft" or "reviewed"
