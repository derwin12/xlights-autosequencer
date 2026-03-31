# Stem-Enhanced Lighting Framework

A generalized framework for translating stem-enhanced song analysis into lighting strategy. This sits between the analysis pipeline (Phase 1-6) and the sequence generator (effect_placer → xsq_writer), replacing the current energy-only section classification with stem-aware structural understanding.

## Overview

The existing pipeline classifies sections by energy score (0-100) → mood tier (ethereal/structural/aggressive) → theme selection. This works but misses structural cues that humans rely on: when vocals enter/exit, which instrument leads, whether a section is a verse or a bridge.

This framework adds three layers on top:

```
Stem-Enhanced Analysis (per-stem features, vocal activity, leader tracking)
       ↓
[1] Section Role Classification  →  intro / verse / chorus / bridge / break / climax / outro
[2] Lighting Strategy Rules      →  tier activation, theme application, effect selection, moment handling
[3] Cross-Section Principles     →  headroom, breathing, bookending, spatial storytelling
       ↓
Sequence Generator (effect_placer.py, xsq_writer.py)
```

---

## 1. Section Role Classification

The existing `structure.py` uses vocal coverage clustering and position heuristics. The stem-enhanced analysis provides much richer signals. Classification should use ALL of these signals together, weighted by reliability.

### 1A. Primary Signal: Vocal Activity Pattern

Vocal presence is the strongest structural signal in popular music. Humans organize songs around voice.

| Vocal Pattern                                              | Likely Role            | Confidence |
| ---------------------------------------------------------- | ---------------------- | ---------- |
| No vocals, song position < 15%                             | **intro**              | High       |
| No vocals, song position > 85%                             | **outro**              | High       |
| No vocals, mid-song, drums active                          | **instrumental break** | High       |
| No vocals, mid-song, drums quiet                           | **ambient bridge**     | Medium     |
| Vocals present, lower energy than adjacent vocal sections  | **verse**              | Medium     |
| Vocals present, higher energy than adjacent vocal sections | **chorus**             | Medium     |
| Vocals present, unique melody (not repeated elsewhere)     | **bridge**             | Medium     |
| Vocals present, very high energy, drums dominant           | **climax**             | Medium     |

Implementation: Compare each section's `vocals_active` flag and vocal RMS against the song-wide vocal RMS distribution. Sections where vocal RMS > 75th percentile of all vocal-active sections are chorus candidates. Sections below 50th percentile are verse candidates.

### 1B. Secondary Signal: Energy Level + Trajectory

Energy alone can't distinguish verse from chorus (a loud verse and a quiet chorus exist). But energy TRAJECTORY — whether energy is rising, falling, or plateaued relative to neighbors — is informative.

| Energy Pattern            | Modifier                                              |
| ------------------------- | ----------------------------------------------------- |
| Rising into next section  | current = **pre-chorus** or **build**                 |
| Sudden drop from previous | current = **breakdown** or **verse return**           |
| Plateau at maximum        | current = **climax** or **sustained chorus**          |
| Plateau at minimum        | current = **intro**, **outro**, or **ambient bridge** |
| Oscillating (up-down-up)  | current = **verse** (breathing pattern)               |

Compute energy trajectory as: `(section_energy - previous_section_energy) / max_song_energy`. Values > +0.15 = rising, < -0.15 = falling, else = stable.

### 1C. Tertiary Signal: Stem Activation Changes

When new stems enter or exit, structure changes. These are the most reliable boundary-type indicators.

| Stem Change                          | Structural Meaning                                           |
| ------------------------------------ | ------------------------------------------------------------ |
| Drums enter (were silent)            | **Song kicks in** — verse start, chorus start, or post-intro |
| Drums exit (were present)            | **Breakdown** — bridge, ambient section, or pre-outro        |
| Bass enters / doubles energy         | **Section escalation** — pre-chorus → chorus, verse → chorus |
| Bass drops out                       | **Thin section** — bridge, breakdown, or stripped verse      |
| Guitar/piano becomes dominant        | **Instrumental feature** — solo, break, or bridge            |
| "Other" (synth/pad) becomes dominant | **Atmospheric section** — intro, outro, ambient bridge       |
| All stems active + high energy       | **Full band** — chorus or climax                             |
| Only 1-2 stems active                | **Stripped** — intro, outro, or intimate verse               |

### 1D. Combined Classification Algorithm

```
For each section:
  1. Set role = "unknown"
  2. If vocals_active == false:
       If position < 15%: role = "intro"
       Elif position > 85%: role = "outro"
       Elif drums_active and energy > 60th percentile: role = "instrumental_break"
       Elif energy < 30th percentile: role = "ambient_bridge"
       Else: role = "interlude"
  3. If vocals_active == true:
       If energy_trajectory == "plateau_max": role = "climax"
       Elif section_energy > 75th percentile of vocal sections: role = "chorus"
       Elif section_energy < 40th percentile of vocal sections: role = "verse"
       Elif energy_trajectory == "rising": role = "pre_chorus"
       Elif previous_role == "chorus" and energy dropped: role = "post_chorus"
       Else: role = "verse" (default for vocal sections)
  4. Override: if section is the global energy maximum AND vocals active: role = "climax"
  5. Override: if section matches a previous section's MFCC profile: inherit that role
     (repeated verses get the same label, repeated choruses get the same label)
```

### 1E. Energy Arc Shape

Classify the overall song energy arc to inform global strategy:

| Arc Shape    | Description                        | Example Songs                      | Global Strategy                                                                     |
| ------------ | ---------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------- |
| **Ramp**     | Steady build from quiet to loud    | Many EDM tracks, orchestral builds | Progressive tier activation, save maximum for final 20%                             |
| **Arch**     | Build → peak → decline             | Most pop songs, ballads            | Peak brightness at 60-75% through song, mirror intro/outro                          |
| **Flat**     | Consistent energy throughout       | Punk, uptempo dance                | Vary effects and theme variants to avoid monotony, energy is constant               |
| **Valley**   | Loud → quiet → loud                | Songs with a breakdown bridge      | Use the valley for maximum contrast — stripped lighting makes the return hit harder |
| **Sawtooth** | Repeated build-drop cycles         | EDM, electronic, some rock         | Each cycle should escalate slightly — cycle 2 brighter than cycle 1                 |
| **Bookend**  | Quiet start and end, active middle | Most popular music                 | Mirror intro/outro theme application, build toward center                           |

Detection: Sample energy at 10 evenly-spaced points through the song. Fit to each pattern template. Best fit determines arc shape.

---

## 2. Lighting Strategy Rules

### 2A. Tier Activation by Section Role

Not every section needs every tier. The number of active tiers should scale with structural importance.

| Section Role           | Active Tiers       | Brightness Ceiling | Notes                                                                                         |
| ---------------------- | ------------------ | ------------------ | --------------------------------------------------------------------------------------------- |
| **intro**              | T1, T2             | 40%                | Atmosphere only. Reserve upper tiers for vocal entry.                                         |
| **verse**              | T1, T2, T4, T6     | 60%                | Add beat chase and prop effects. Movement but not spectacle.                                  |
| **pre_chorus**         | T1, T2, T4, T6, T7 | 70%                | Compound tier activates. Energy is building.                                                  |
| **chorus**             | T1-T8 all          | 85%                | Everything on. The payoff for the build.                                                      |
| **climax**             | T1-T8 all at max   | 95%                | The single loudest section. Held brightness, not flashing.                                    |
| **post_chorus**        | T1, T2, T4         | 50%                | Quick cooldown. Upper tiers fade out over 1-2 seconds.                                        |
| **bridge**             | T1, T2, T8         | 55%                | Sparse. One hero effect + base wash. Use theme variant for contrast.                          |
| **instrumental_break** | T1, T4, T6, T7     | 75%                | No vocals = different character. Beat and prop tiers active. No hero (save for vocal return). |
| **ambient_bridge**     | T1 only            | 30%                | Nearly dark. Single slow wash. Maximum contrast setup.                                        |
| **interlude**          | T1, T2             | 45%                | Brief transitional. Base theme layer only, minimal movement.                                  |
| **outro**              | T1, T2 (fading)    | 30% → 0%           | Mirror intro. Fade to black over section duration.                                            |

### 2B. Theme Application by Section Role

Colors and palettes are owned by the **theme system** — the user picks a theme (or set of themes) for a song, and the theme defines all palettes, accent colors, and layer combinations. The framework does NOT prescribe colors. Instead, it tells the theme system HOW to apply the user's chosen theme to each section.

#### Theme Modulation by Section Role

The theme's palette and layers are the baseline. The framework modulates how aggressively they're applied:

| Section Role           | Theme Application                                                  | Palette Usage                                                         |
| ---------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------- |
| **intro**              | Theme base layer only, dimmed. No accent palette yet.              | Primary palette at low saturation/brightness.                         |
| **verse**              | Theme base + middle layers. Accent palette appears on T6.          | Primary palette dominates, accent punctuates.                         |
| **chorus**             | Full theme — all layers active. Accent palette on T6-T8.           | Both palettes at full saturation.                                     |
| **climax**             | Full theme at maximum intensity.                                   | Accent palette may override primary on upper tiers.                   |
| **bridge**             | Theme variant layers (if available). Different look, same palette. | Use `theme.variants[0]` for visual contrast without palette change.   |
| **instrumental_break** | Theme variant layers OR user's secondary theme (if assigned).      | If user assigned a second theme, switch here. Otherwise use variants. |
| **outro**              | Mirror intro — theme base layer only, fading.                      | Return to primary palette at diminishing brightness.                  |

#### Multi-Theme Support

Some songs warrant more than one theme. The framework supports an optional secondary theme for non-vocal sections:

| Config                        | Behavior                                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Single theme** (default)    | One theme for the whole song. Variants used for contrast at bridges/breaks.                                       |
| **Primary + secondary theme** | Primary theme for vocal sections, secondary for instrumental sections. Transition at vocal entry/exit boundaries. |
| **Per-section override**      | User explicitly assigns a theme to a specific section role (e.g., "use Inferno for all choruses").                |

The theme transition happens at the section boundary, using the transition style from 2E (hard cut, crossfade, etc.).

### 2C. Effect Selection by Section Role + Stem Character

Not every effect fits every section. The section role and active stems should constrain the effect pool.

#### Base Layer (T1-T2) Effects

| Section Role       | Recommended Effects        | Avoid                                                        |
| ------------------ | -------------------------- | ------------------------------------------------------------ |
| intro / outro      | Color Wash, Twinkle        | Strobe, Fire, Shimmer, anything aggressive                   |
| verse              | Color Wash, Wave           | Strobe, Shockwave                                            |
| chorus             | Color Wash (bright), Bars  | Nothing off limits                                           |
| climax             | Color Wash at max, or Fire | Twinkle (too gentle)                                         |
| bridge             | Plasma, Butterfly          | Bars, Strobe (too rhythmic)                                  |
| instrumental_break | Plasma, Color Wash         | Use theme variant or secondary theme for contrast with verse |

#### Beat Layer (T4) Effects

| Dominant Stem              | Beat Effect         | Timing Source      | Notes                                               |
| -------------------------- | ------------------- | ------------------ | --------------------------------------------------- |
| Drums strong + steady      | Single Strand chase | Full-mix beat grid | Classic roofline chase. Speed matches BPM.          |
| Drums strong + fills       | Meteors             | Drums-stem onsets  | Onset-triggered gives cleaner timing than full-mix. |
| Drums weak/absent          | Skip T4 or Twinkle  | N/A                | No rhythmic pulse = no beat visual.                 |
| Bass driving (drums quiet) | Bars (slow, upward) | Bass-stem onsets   | Slower, heavier movement following bass rhythm.     |

#### Prop/Compound Layer (T6-T8) Effects

| Section Character            | Effect Pool                      | Notes                                              |
| ---------------------------- | -------------------------------- | -------------------------------------------------- |
| High energy, drums dominant  | Shockwave, Meteors, Strobe, Fire | Impact-driven. Each drum hit = visual event.       |
| High energy, vocals dominant | Ripple, Spirals, Pinwheel        | Flowing, continuous. Follows vocal melody contour. |
| Medium energy, balanced      | Fire, Spirals, Bars, Wave        | Mixed pool. Rotate per group.                      |
| Low energy, atmospheric      | Twinkle, Butterfly               | Gentle, sparse. Low count/density.                 |
| Instrumental solo            | Galaxy, Pinwheel (fast), Spirals | Showcase effects. Speed matches onset density.     |

### 2D. Moment Type Classification

The analysis produces dramatic moments (energy surges/drops, percussive impacts, brightness spikes, etc.). These need classification before they drive lighting — not all moments should trigger the same response.

#### Sustained Plateau vs. Isolated Spike vs. Cascade

Look at the temporal distribution of moments, not just individual values:

| Pattern               | Detection                                                                 | Lighting Response                                                                                            |
| --------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Isolated spike**    | No same-type moment within ±3 seconds                                     | Single event trigger: one Shockwave, one Strobe flash, one brightness pulse.                                 |
| **Sustained plateau** | 3+ same-type moments within a 10-second window, all above 75th percentile | Sustained effect: hold maximum brightness/speed for the duration. Don't retrigger — keep the engine running. |
| **Cascade**           | 3+ moments of escalating intensity within 5 seconds                       | Ramp effect: brightness or speed increases with each hit. Use value curves.                                  |
| **Double-tap**        | Two strong moments within 0.5 seconds                                     | Enhanced single event: brighter/wider Shockwave, or two rapid Strobe flashes.                                |
| **Breathing**         | Alternating surges and drops at regular intervals                         | Modulate brightness up/down with the pattern. Use value curves on T1 brightness.                             |

Implementation:

```
For each moment M:
  window = all moments of same type within M.time ± 5 seconds
  if len(window) == 1: M.pattern = "isolated"
  elif len(window) >= 3 and all above 75th percentile:
    if max(window) - min(window) intensity < 20% of max: M.pattern = "plateau"
    elif intensities are monotonically increasing: M.pattern = "cascade"
    else: M.pattern = "plateau"
  elif len(window) == 2 and time gap < 0.5s: M.pattern = "double_tap"
  else: M.pattern = "cluster"
```

#### Per-Stem Moment Routing

Moments from different stems should drive different visual targets:

| Source Stem | Visual Target                                    | Effect Type                                           |
| ----------- | ------------------------------------------------ | ----------------------------------------------------- |
| drums       | Roofline chase, shockwaves on matrices and props | Impact-driven (Shockwave, Strobe, Meteors)            |
| bass        | Fire height, low-prop brightness, sub-bass glow  | Intensity-driven (Fire height curve, Bars speed)      |
| vocals      | Hero prop, center-stage props, brightness pulses | Brightness-driven (overall brightness modulation)     |
| guitar      | Arches, horizontal props, directional movement   | Movement-driven (Wave, Spirals, Single Strand)        |
| piano       | Matrix effects, gentle accents                   | Pattern-driven (Ripple, Butterfly, Plasma)            |
| other/synth | Background wash, ambient overlay                 | Atmosphere-driven (Color Wash shift, Twinkle density) |

### 2E. Transition Handling

Section boundaries need special attention. An abrupt cut from chorus to verse looks wrong. A slow fade during an energy surge looks wrong. The transition style should match the energy delta.

| Energy Change at Boundary     | Transition Style                                                                  | Duration    |
| ----------------------------- | --------------------------------------------------------------------------------- | ----------- |
| Large drop (> 0.3 normalized) | **Hard cut** — kill upper tiers instantly, base theme layer transitions in 1 beat | 200-400ms   |
| Moderate drop (0.1-0.3)       | **Quick fade** — upper tiers fade over 2-4 beats                                  | 1-2 seconds |
| Stable (< 0.1 change)         | **Crossfade** — old effects fade out as new fade in                               | 2-4 seconds |
| Moderate rise (0.1-0.3)       | **Quick build** — new tiers activate one per beat                                 | 1-2 seconds |
| Large rise (> 0.3)            | **Snap on** — all new tiers activate simultaneously on the downbeat               | 1 beat      |

Special case — **silence region at boundary**: If there's a detected silence gap (>300ms) at the section boundary, use it. All effects end at silence start, new effects begin at silence end. The darkness between is the transition.

---

## 3. Cross-Section Principles

These apply to all songs regardless of genre or structure.

### 3A. Headroom Reservation

Never run at 100% brightness for more than one section. If the song has a clear climax, the sections leading to it should be at 70-85% so the climax step-up is perceptible.

```
max_brightness_section = section with highest energy_score
for each section:
  if section == max_brightness_section:
    brightness_ceiling = 0.95
  elif section.energy_score > 80th percentile:
    brightness_ceiling = 0.85
  else:
    brightness_ceiling = energy_score / 100.0
```

For songs with sustained plateaus (e.g., the entire second half is high energy), don't reserve headroom for a peak that doesn't exist. If the top 3 sections are within 5% energy of each other, treat them all as the plateau and set them all to 90%.

### 3B. Breathing Pattern

Within a section, lighting should breathe with the music. Constant brightness looks dead. Modulate base-tier brightness using the vocal RMS envelope (for vocal sections) or the full-mix RMS envelope (for instrumental sections).

```
breathing_depth = 0.15  # ±15% of section brightness
breathing_source = vocal_rms if vocals_active else full_mix_rms

value_curve = normalize(breathing_source, 0, 1) * breathing_depth
T1_brightness = section_brightness + value_curve - (breathing_depth / 2)
```

This creates subtle pulsing that makes the show feel alive without being distracting.

### 3C. Bookending

The first and last sections of the song should share a visual identity — same theme, same layer selection, similar tier activation. This creates narrative closure.

```
if sections[0].role == "intro" and sections[-1].role == "outro":
  sections[-1].theme = sections[0].theme
  sections[-1].active_tiers = sections[0].active_tiers
  sections[-1].theme_layer_mode = "base_only"  # same as intro
```

The outro should feel like a return to the beginning, not a new idea.

### 3D. Repetition Variation

When a section role repeats (Verse 1, Verse 2, Verse 3), each occurrence should be recognizably the same but not identical.

| Occurrence | Variation                                                                                     |
| ---------- | --------------------------------------------------------------------------------------------- |
| 1st        | Base theme, base layers, base effects                                                         |
| 2nd        | Same theme, variant layers (from theme.variants[0]), ±5% parameter tweak                      |
| 3rd        | Same theme, variant layers (from theme.variants[1]), reverse directions (Left→Right, Up→Down) |
| 4th+       | Cycle through variants                                                                        |

This is already partially implemented in `effect_placer.py` via `variation_seed`. The framework should ensure the seed increments per role occurrence, not per section index.

### 3E. Spatial Storytelling via Leader Tracking

The leader track (which stem dominates at each moment) can drive which ZONE of the house is most active. This creates spatial movement that follows the music.

Map stems to house zones based on typical prop placement:

| Stem   | House Zone              | Typical Props                        |
| ------ | ----------------------- | ------------------------------------ |
| vocals | Center / front          | Matrix, mega tree, main display      |
| drums  | Roofline / top          | Roofline strings, eaves              |
| bass   | Ground / bottom         | Bushes, pathway lights, ground-level |
| guitar | Left side OR arches     | Arches, left-bank strings            |
| piano  | Right side OR accents   | Mini trees, accent props             |
| other  | Everywhere (background) | All props at low intensity           |

When the leader transitions from vocals → guitar, the visual emphasis should shift from center to the arches/sides. This requires the leader_transitions data from the stem analysis and zone-aware brightness modulation.

```
For each frame (at leader_track.fps):
  leader = leader_track.frames[frame]
  for zone in house_zones:
    if zone.stem_affinity == leader:
      zone.brightness_multiplier = 1.0
    elif zone.stem_affinity in active_stems:
      zone.brightness_multiplier = 0.6
    else:
      zone.brightness_multiplier = 0.3
```

### 3F. Stem-Specific Value Curves

Rather than driving ALL effects from the full-mix energy curve, route per-stem energy curves to the effects they match best:

| Effect Parameter      | Driven By                 | Why                                                               |
| --------------------- | ------------------------- | ----------------------------------------------------------------- |
| Fire height           | bass stem RMS             | Bass energy = flame intensity. Sub-bass makes fire feel grounded. |
| Shockwave speed/size  | drums stem onset strength | Drum hits = expanding rings. Stronger hit = bigger ring.          |
| Color Wash brightness | vocal stem RMS            | Wash breathes with the singer. Brighter when vocals are loud.     |
| Meteor count          | drums stem onset density  | More drum events = more meteors falling.                          |
| Spiral/Pinwheel speed | full-mix tempo curve      | Rotation follows the rhythmic pulse.                              |
| Ripple frequency      | guitar stem onset density | Guitar picking density = ripple density.                          |
| Plasma movement       | other stem RMS            | Pad/synth energy = organic plasma movement.                       |
| Strobe rate           | drums stem onset density  | Fast drumming = faster strobe. Slow section = no strobe.          |

### 3G. Silence as a Tool

When the analysis detects silence regions (>300ms), use them. A brief blackout during a musical silence is one of the most powerful lighting moments — the audience feels the emptiness both aurally and visually.

```
For each silence_region:
  if duration > 300ms and duration < 2000ms:
    # Brief silence: hard blackout
    set all tiers to Off at silence.start
    restore previous state at silence.end
  elif duration > 2000ms:
    # Extended silence: fade to black over 500ms at start
    # hold black for duration
    # new section lighting begins at silence.end
```

### 3H. Genre-Aware Defaults

The framework should have sensible defaults that shift by genre:

| Genre Signal                                   | Default Adjustments                                                                 |
| ---------------------------------------------- | ----------------------------------------------------------------------------------- |
| High vocal coverage (>70% of song)             | Vocal RMS drives most value curves. Theme breathes with the singer.                 |
| Low vocal coverage (<20%)                      | Instrumental focus. Effect variety and theme variants matter more.                  |
| High onset density throughout (>3/sec average) | Reduce per-onset triggering (would be overwhelming). Use sustained effects instead. |
| Low onset density (<1/sec average)             | Every onset matters. Trigger effects on each one.                                   |
| High harmonic-percussive ratio (>3.0)          | Prioritize flowing effects (Wave, Spirals, Butterfly). Reduce impact effects.       |
| Low H/P ratio (<1.0)                           | Heavy percussion. Impact effects dominate (Shockwave, Strobe, Meteors).             |
| Steady tempo (CV < 5%)                         | Tight beat-synced chases work well.                                                 |
| Variable tempo (CV > 15%)                      | Avoid tight beat sync — use onset triggers instead.                                 |

---

## 4. Data Requirements

### Input: Stem-Enhanced Analysis JSON

The framework expects this structure (produced by the stem-enhanced analysis script):

```
{
  "duration_seconds": float,
  "global_tempo_bpm": float,
  "stems_used": ["drums", "bass", "vocals", "guitar", "piano", "other"],

  "sections": [
    {
      "start": float,
      "end": float,
      "energy": { "level": str, "average": float, "db_avg": float },
      "texture": { "character": str, "hp_ratio": float },
      "spectral": { "brightness": str },
      "rhythm": { "onset_density_per_sec": float },
      "vocals_active": bool,
      "dominant_stem": str,
      "stem_energy": { "<stem>": { "average": float, "active": bool } },
      "leader_transitions": [ { "time": float, "from_stem": str, "to_stem": str } ],
      "dramatic_moments": [ { "time": float, "type": str, "stem": str, "intensity": float } ]
    }
  ],

  "vocal_regions": [ { "start": float, "end": float, "type": "vocal_on"|"vocal_off" } ],
  "leader_transitions": [ { "time": float, "from_stem": str, "to_stem": str } ],
  "energy_timeline": [ { "time": float, "rms": float, "stem_*_rms": float } ],
  "silence_regions": [ { "start": float, "end": float } ]
}
```

### Output: Enhanced SectionAssignment

The framework produces an enriched section plan:

```
{
  "section_role": str,           // intro, verse, chorus, bridge, etc.
  "energy_arc_position": str,    // rising, falling, plateau, valley
  "active_tiers": [int],         // which tiers should be active
  "brightness_ceiling": float,   // 0.0 to 1.0
  "theme_layer_mode": str,       // "base_only", "base_mid", "full", "variant"
  "use_secondary_theme": bool,   // true for non-vocal sections when secondary theme assigned
  "moment_patterns": {           // classified moment types
    "isolated_spikes": [...],
    "sustained_plateaus": [...],
    "cascades": [...],
    "double_taps": [...]
  },
  "value_curve_routing": {       // which stem drives which parameter
    "fire_height": "bass",
    "wash_brightness": "vocals",
    "shockwave_trigger": "drums",
    ...
  },
  "transition_style": str,       // hard_cut, quick_fade, crossfade, snap_on
  "variation_seed": int           // for repeated section roles
}
```

---

## 5. Integration with Existing Pipeline

This framework slots into the existing generator pipeline at two points:

### Replace: `energy.py` → `derive_section_energies()`

Currently derives `SectionEnergy` with just energy_score + mood_tier + impact_count. Replace with a richer classification that includes section_role, active_tiers, theme_layer_mode, and moment_patterns from the stem analysis.

### Enhance: `effect_placer.py` → `place_effects()`

Currently maps theme layers to tiers uniformly. Enhance to:

1. Respect `active_tiers` from the framework (don't place effects on tiers the framework says should be off)
2. Use `theme_layer_mode` to control which theme layers are active per section
3. Use `moment_patterns` to decide between event-triggered vs. sustained effects
4. Use `value_curve_routing` to bind per-stem energy curves to effect parameters
5. Use `transition_style` to handle section boundary crossfades

### New: `section_classifier.py`

A new module that takes the stem-enhanced analysis JSON and produces the enhanced SectionAssignment output. This is the core of the framework — the classification logic from sections 1 and 2 above.

### New: `moment_classifier.py`

A new module that takes the raw dramatic_moments list and produces classified moment patterns (isolated/plateau/cascade/double_tap). This feeds into effect_placer to determine whether a section gets event-triggered shockwaves or sustained fire.
