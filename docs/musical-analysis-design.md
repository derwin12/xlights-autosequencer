# Musical Analysis Design Document

**Created**: 2026-03-24
**Status**: Working design — captures research, findings, and decisions from analysis sessions
**Songs tested**: 22 songs — see [Appendix A](#appendix-a-batch-validation-song-list) for full list
**Initial analysis** (3 songs): Highway to Hell (AC/DC), Ghostbusters (Ray Parker Jr), You're A Mean One Mr. Grinch (Sabrina Carpenter/Lindsey Stirling)
**Batch validation** (22 songs): Rock, pop, holiday (Christmas + Halloween), instrumentals, mashups, classical remix
**Target genres**: Rock, pop, and holiday music (Halloween, Christmas). This tool produces a *starting point* for light sequencing, not a finished show — manual tweaking is expected and fine. We optimize for the common case, not every edge case. See Section 9 for known limitations outside the target genres.

---

## 1. Analysis Hierarchy for xLights

The fundamental insight: not all analysis serves the same purpose. Beats, structure, energy, and harmony each drive different lighting decisions. Treating them as a flat list of "timing tracks ranked by score" misses the point.

### Level 0: Special Moments (the "wow" triggers)

**Purpose**: Detect the moments in a song where something genuinely different happens — the moments a human listener would notice and respond to. These trigger one-shot or transition effects that make the light show feel alive rather than mechanical.

**What qualifies as a "special moment":**

| Moment Type | Detection Method | Validated? | Notes |
|-------------|-----------------|------------|-------|
| Energy impacts | RMS energy change >1.8x or <0.55x in 1-second windows | ✅ 22/22 songs | Range: 2-44 events/song, mean: 12.2. Universal across all target genres. |
| Gaps/silence | Near-silence (energy < 5/100) for >300ms | ✅ 18/22 songs | More common than initially thought. Only 4 songs had zero gaps (3 holiday, 1 mashup). |
| Novelty peaks | Chroma-based self-similarity deviation, top 90th percentile | ✅ All 3 songs | Relative ranking within a song works; absolute thresholds don't generalize. |
| Texture changes | Count of active stems crossing a threshold | ✅ Highway only (needs stems) | Going from 2→4 stems = build-up, 4→1 = breakdown. Concept is universal but requires stem separation. |
| Stem solos | One stem's energy >3x average of others | ✅ Highway only (needs stems) | Guitar solo detection worked perfectly. |

**Cross-song validation results (22 songs):**
- Energy impacts: **universal** — 22/22 songs, range 2-44 events, mean 12.2 per song
- Energy drops: **universal** — 22/22 songs, range 1-24 events, mean 6.5 per song
- Gaps: **present in most songs** (18/22) — originally thought to be genre-dependent but batch validation shows they're common. Songs without gaps: Like It's Christmas, Wizards in Winter, Wednesday mashup.
- Novelty: **works but needs relative thresholds** (top N% within the song, not absolute values)
- Texture/stem changes: **needs stems** — can't run on full mix alone

**Known limitations:**
- Novelty peaks use relative thresholds (top N%) so they always produce results, but on very repetitive tracks the "peaks" may not feel meaningful.
- Texture/stem changes require decent stem separation — dense live mixes with bleed may give unreliable stem counts.

### Level 1: Structure (scene boundaries)

**Purpose**: Divide the song into sections so you can assign different lighting scenes, color palettes, and effect groups to each section.

**Key finding**: After testing ensemble and augmentation approaches on 22 songs, **Segmentino alone is the best segmenter** for our target genres. See [Section 5: Structural Segmentation](#5-structural-segmentation) for full analysis.

**Segmentino repeat labels (A, B, N1, N2, etc.) are the most valuable structural feature** — they tell you which sections are musically identical and can share the same lighting design. This is more useful than knowing the section's name. Validated on 20/22 songs (91%).

### Level 2: Bars & Phrases (pattern organization)

**Purpose**: The organizational grid for repeating patterns. A 4-beat chase pattern needs bar boundaries to reset correctly. A build effect needs phrase boundaries (every 4 bars).

| Detection | Algorithms | Typical Frequency | Validated? |
|-----------|-----------|-------------------|------------|
| Bar boundaries (downbeats) | qm_bars, librosa_bars, madmom_downbeats | ~0.5/s at 120 BPM | ✅ All beat trackers agree |
| Phrase boundaries | Not currently detected | ~0.125/s (every 4 bars) | ❌ Gap — could derive from bars + energy |

**Bars are correctly detected** at ~0.5/s (every 2 seconds at 120 BPM). All bar-detection algorithms agree on this frequency, confirming the detection is reliable.

**Phrases are missing** — groups of 4 or 8 bars that form musical phrases. Could be derived from bar marks + energy contour (a phrase often starts with a dynamic change).

**Known limitations:**
- Assumes 4/4 time for bar grouping. Most rock/pop/holiday songs are 4/4 so this is fine for our target genres.
- Songs with tempo changes will have bar detection issues at the transition point — beats before and after are usually fine.

### Level 3: Beats (pulse)

**Purpose**: The heartbeat. Flash timing, chase step, on-beat sync.

| Detection | Typical Frequency | Notes |
|-----------|-------------------|-------|
| Beat positions | ~2/s at 120 BPM | All beat trackers agree. Pick ONE best tracker per song. |

**Key insight**: You want ONE best beat track, not all of them. The sweep's job at this level is to find which algorithm + stem combo gives the most accurate beats for THIS song.

**Known limitations:**
- When beat trackers disagree, we currently export all tracks and let the user pick. Could auto-select by confidence score in the future.
- Live recordings with tempo drift will have some beat misalignment — acceptable for a starting point.

### Level 4: Instrument Events (per-stem accents)

**Purpose**: Individual musical events that trigger one-shot effects — a snare hit, a guitar strum, a vocal entry.

**Critical finding: different algorithms produce different densities, and you need the RIGHT density for each use case.**

| Use Case | Ideal Frequency | Best Algorithm + Stem | Notes |
|----------|----------------|----------------------|-------|
| Drum hits (all) | 2-4/s | aubio_onset on drums (2.3/s), percussion_onsets on drums (1.7/s) | ✅ Correct density |
| Guitar strums | 1-3/s | qm_onsets_phase on guitar (2.7/s) | ✅ But qm_onsets_hfc on guitar = 3.4/s (borderline) |
| Bass notes | 1.5-2.5/s | qm_onsets_phase on bass (2.2/s) | ✅ Correct |
| Vocal entries | 0.3-1/s | aubio_onset on vocals (0.5/s) | ✅ Correct — one per phrase |
| Chord changes | 0.3-1/s | chordino_chords on guitar (0.7/s) | ✅ Correct |

**Algorithms that produce TOO MANY events for lighting:**
- librosa_onsets on guitar: 8/s (every pick of every strum — too granular)
- qm_onsets_complex on bass: 7.5/s (too dense)
- librosa_onsets on full_mix: 6/s (too dense)

**Fix**: Sweep onset sensitivity parameter at multiple levels to find the right density for each stem.

**Known limitations:**
- Frequency ranges (drum hits 2-4/s, guitar strums 1-3/s) are derived from rock songs — will need validation across more samples but should hold for target genres.
- Stem bleed can cause double-counted events. If results look too dense, falling back to full-mix analysis is fine.

### Level 5: Energy Curves (continuous automation)

**Purpose**: Drive xLights effect properties (brightness, size, speed, position) continuously over time. These are NOT timing events — they're value curves (`.xvc` files).

| Algorithm | Output | xLights Use |
|-----------|--------|------------|
| bbc_energy (per stem) | 0-100 value curve | Per-prop brightness — drum lights follow drum energy |
| bbc_spectral_flux | 0-100 value curve | Effect intensity — more spectral change = more visual complexity |
| amplitude_follower (per stem) | 0-100 value curve | Smooth brightness following (like a VU meter) |

**xLights value curve format**: `.xvc` files store percentage values (0-100) applied to any effect property. Users import them and assign to brightness, position, rotation, etc. Our 0-100 normalized output maps directly.

### Level 6: Harmonic Color (tonal mapping)

**Purpose**: Drive color selection based on harmonic content.

| Detection | Algorithm | Frequency | Use |
|-----------|-----------|-----------|-----|
| Chord changes | chordino_chords on guitar/piano | 0.7/s | Color change on each chord |
| Key changes | qm_key on full_mix | 0.2/s (structural) | Color palette shift |

**Known limitations:**
- Songs that stay on one or two chords produce very sparse chord change tracks — fewer color changes but not wrong.
- Complex jazz harmony is out of scope. Standard rock/pop/holiday chord progressions are handled well by Chordino.

---

## 2. Algorithms We're Using Wrong

### BBC Rhythm — Misclassified as Timing Marks

**What we did**: Treated 5168 items as timing marks (onset events).
**What it actually is**: A continuous rhythm strength curve at 172 values/second (every 5.8ms). Each item has a single float value measuring "how rhythmic is this moment."
**Fix**: Reclassify as a value curve. It measures rhythm intensity over time — could drive effect speed or pattern complexity.

### NNLS Chroma — Misclassified as Timing Marks

**What we did**: Treated 646 items as timing marks.
**What it actually is**: A 12-bin chroma matrix — 12 values per frame representing energy in each pitch class (C, C#, D, D#... B).
**Fix**: Either use as 12 value curves (one per pitch class for color mapping) or don't use directly — Chordino already processes it internally for chord detection.

### Onset Detectors at Default Sensitivity

**Problem**: Running onset detectors at default sensitivity produces the right density for some stems but too many events for others.
**Example**: `librosa_onsets` on drums = 2/s (correct for beats), but on guitar = 8/s (every pick, too dense for lighting).
**Fix**: Sweep the sensitivity parameter at multiple levels per stem:
- For drum hits: sensitivity 25-40
- For guitar strums: sensitivity 10-20
- For vocal entries: sensitivity 5-15
- The `minioi` (minimum inter-onset interval) parameter can also cap density (e.g., 200ms = max 5/s)

---

## 3. Stem Affinity — Universal vs Song-Specific

### Always True (physics of the instrument):
- **Beat trackers always work best on drums** — drums have the sharpest transients at beat positions
- **Chord detection always works best on guitar/piano** — they carry the harmonic content
- **Percussion onset detection always works best on drums** — purpose-built for broadband percussive events

### Song-Specific (depends on arrangement):
- **Bass onset detection**: Rhythmic in funk, sustained in ambient — onset count varies wildly
- **Guitar as beat source**: Works for rhythmic strumming (AC/DC), fails for legato playing (jazz ballad)
- **Energy curves**: Dynamic songs produce useful curves; wall-of-sound tracks produce flat curves
- **Vocal onset frequency**: Frequent in rap, sparse in opera

### Dual-Model Stem Separation: Open Question

Currently we run **two Demucs passes** per song:
1. `htdemucs_ft` (fine-tuned, 4-stem) — vocals, drums, bass, other. High-quality vocal isolation with `shifts=2`.
2. `htdemucs_6s` (6-stem) — adds guitar and piano separation from the "other" stem.

The 6-stem second pass was originally added to improve vocal alignment, but **this didn't pan out** — vocal quality comes from the fine-tuned model in pass 1, not from the 6-stem model. The guitar/piano separation is useful for chord detection and per-instrument onset analysis (Level 4), but doubles the processing time per song.

**Evaluation needed**: Run the batch validation with and without the 6-stem pass to measure whether guitar/piano stems meaningfully improve analysis quality for our target genres. If the improvement is marginal, dropping to a single 4-stem pass would cut stem separation time in half.

### Implication for the Sweep:
The affinity table gives good defaults. The sweep's real value is discovering **exceptions** — when a non-default stem gives better results for this particular song. That's why we sweep all applicable stems, not just the top 1.

---

## 4. The "Does the Name Matter?" Question

### Answer: No.

What matters for lighting is measurable properties, not section names:

| Property | How to detect | What it drives |
|----------|--------------|----------------|
| **Repeats?** | Segmentino labels (A=A=A) | Reuse the same lighting design |
| **Vocals active?** | Vocal stem energy > threshold | Spotlight on/off, lyric effects |
| **How many stems?** | Count stems above threshold | Effect complexity (1=simple, 4=full) |
| **Energy level?** | RMS relative to song median | Overall brightness/intensity |
| **Getting louder/quieter?** | Energy delta from previous section | Build-up or wind-down effects |
| **Something unique?** | Repeat count = 1 | Special one-time effects |

Calling it "Chorus" is shorthand for "repeating, vocals active, all stems playing, high energy." The measurable properties ARE the lighting decisions.

### When Genius labels ARE useful:
- Building a template library ("my standard Chorus lighting")
- Human readability in the UI
- Identifying instrumental sections (Guitar Solo, Interlude) that have no lyrics

---

## 5. Structural Segmentation

### Decision: Segmentino as sole segmenter

After batch testing on 22 songs, **Segmentino alone is the right approach**. The ensemble and augmentation approaches we tested did not improve results.

**Segmentino results (22 songs):**
- Mean 9.0 sections/song
- 20/22 songs (91%) have repeating section labels (A=A=A)
- Repeat labels are the most actionable feature — they tell you exactly which sections can share the same lighting design
- 2 failures: Super Mario Intro (28s jingle, 1 section) and Wednesday mashup (1 section). Both are expected — these aren't structured songs.

### What We Tested and Ruled Out

**Ensemble consensus (Segmentino + QM Segmenter tuned + QM Segmenter granular):**
Tested on all 22 songs with a 3-second consensus window. Result: only 43% of consensus boundaries had all three sources agreeing, and 16/22 songs had low agreement (<30%). The ensemble actually produced *fewer* usable boundaries than Segmentino alone in 14/22 songs. The three segmenters use similar spectral features but disagree on where boundaries fall, producing noise rather than reinforcement.

**Harmonic change augmentation (Segmentino + Chordino harmonic change peaks):**
Used Segmentino as backbone, then subdivided long sections (>15s) at Chordino harmonic change peaks (99th percentile). Blind-listened to 36 split clips across 4 songs (Highway to Hell, Christmas Dirtbag, Carol of the Bells, Squid Game). Result: **29% hit rate** (10/35 were real boundaries). Harmonic change values could not distinguish real from false splits — the ranges overlapped completely. It works on songs where Segmentino completely fails (Squid Game's 101s block → 4 good splits out of 8), but for songs where Segmentino already gets reasonable structure, the harmonic splits were mostly noise.

**QM Segmenter parameters** (reference from initial testing):

| Parameter | What it controls | Useful range |
|-----------|-----------------|-------------|
| `nSegmentTypes` | How many distinct section types to detect | 3-5 (fewer = cleaner structure) |
| `neighbourhoodLimit` | Minimum segment duration | 6-12 (8 gives ~10s minimum, 6 catches solos) |
| `featureType` | Which audio feature drives segmentation | 1 or 2 (3 works too, 4-5 produce nothing) |

### Known Limitation: Long Sections

Segmentino occasionally merges adjacent sections into one long block (e.g., Highway to Hell intro+verse = 54s). This affects ~30% of songs. For now, users can manually split these in xLights. This fits our "starting point, not perfection" design goal.

### Future: Vocal-Based Segmentation

If better subdivision of long sections is needed, the most promising unexplored approach is **vocal-based segmentation**:
- Choruses repeat the same (or very similar) lyrics — matching repeated vocal phrases would directly identify chorus boundaries
- Vocal absence marks instrumental breaks, intros, and solos
- This is independent of spectral-feature segmenters and captures what humans actually use to identify sections
- Requires vocal stem + transcription (WhisperX), which we already have in the pipeline

This would be a future enhancement, not a blocker for the current pipeline.

---

## 6. What Generalizes Across Songs

Batch validated on 22 songs: rock, pop, holiday (Christmas + Halloween), instrumentals, mashups, classical remix.

### Universal ✅ (validated on 22 songs)
- **Energy impacts** (sudden loudness changes) — 22/22 songs, range 2-44 events, mean 12.2/song
- **Energy drops** (sudden quieting) — 22/22 songs, range 1-24 events, mean 6.5/song
- **Beat/bar detection** — 22/22 songs in expected range (0.34-0.64 Hz bars)
- **Segmentino repeat labels** — 20/22 songs have repeating sections (91%)
- **Gaps/silence** — 18/22 songs have detectable gaps (>300ms silence). More common than initially expected.
- **Onset detection** — 19/22 songs produce usable onset density (1.0-5.0/s)

### Edge Cases Within Target Genres ⚠️
- **Segmentino on short/non-standard tracks** — Super Mario Intro (28s jingle) and Wednesday mashup produced only 1 segment with no repeats. Expected for these formats.
- **Onset density on electronic/percussive tracks** — Halloween Theme (6.9/s), Super Mario (6.1/s), Squid Game (5.0/s) are too dense at default sensitivity. Needs sensitivity tuning for electronic percussion.
- **Novelty peaks** — works but absolute thresholds vary. Use top N% within each song.

### Needs Stems (can't verify on full mix alone) 🔬
- **Texture changes** (stem count) — tested only on Highway. Concept is universal but requires stem separation.
- **Stem dominance** — tested only on Highway. Per-stem energy analysis needs isolated stems.

### Out of Scope (not tested, not targeted)
- Songs with no clear beat (ambient, classical)
- Songs with heavy compression (modern EDM where energy is nearly flat)
- Songs with extreme dynamic range (orchestral)

---

## 7. Recommended Architecture Changes

### Short-term (implement next):
1. **Fix bbc_energy JSON export** — `value_curve` data is computed but not serialized. `TimingTrack.to_dict()` drops the `value_curve` attribute. Energy impacts are confirmed universal (22/22 songs) but the values must be in the export for downstream use.
2. **Fix bbc_rhythm and nnls_chroma** — reclassify as value curves, not timing marks
3. **Add sensitivity sweeping** for onset detectors — sweep at multiple sensitivities per stem, especially for electronic/percussive tracks where default produces >5/s
4. **Categorize sweep results by purpose** in the UI — not one flat list

### Medium-term:
5. **Add phrase detection** — derive from bar marks + energy contour
6. **Add texture analysis** — count active stems per section (requires stems)
7. **Section classification by measurable properties** — not names, but energy/vocal/stem-count

### Long-term:
8. **Auto-generate lighting roadmap** — for each section, recommend: intensity level, which stems to follow, which effects to use, what repeats
9. **Template matching** — "this section has similar properties to a Chorus template" for users who want named presets

---

## 8. xLights Value Curve (.xvc) Format

From the xLights documentation:

- Value curves modify how effect attributes change over time
- Applied to **any effect property**: brightness, speed, size, color mix, position, rotation
- Range: **0-100** (percentage)
- Types: flat, ramp, sawtooth, or **custom** (arbitrary points — what we produce)
- Stored as `.xvc` files in the show's `valuecurves/` folder
- Users import them and assign to effect properties via a dialog

Our `bbc_energy` output (0-100 normalized values per frame) maps directly to the custom value curve type. One energy curve per stem = one brightness automation per light group.

**Known limitations:**
- Per-song normalization (0-100 maps to that song's min/max) means curves aren't comparable across songs — fine since each song gets its own light show.
- Very compressed tracks produce flatter curves — still usable, just less dramatic automation.

---

## 9. Known Limitations

This tool targets rock, pop, and holiday music — songs with steady tempo, clear beats, and verse-chorus structure. It produces a starting point for light sequencing, not a finished show. The limitations below are documented so we understand the boundaries, not because we need to solve them all.

### 9a. Out-of-Scope Genres (Expected to Produce Poor Results)

These genres fall outside our target and users should expect to do significant manual work or avoid them:

| Genre | Why It Doesn't Work Well |
|-------|------------------------|
| **Ambient / drone** | No clear beat — beat trackers hallucinate a pulse. No sections. Energy is flat. |
| **Free jazz** | Irregular phrases, complex harmony, tempo drift. Almost nothing in the hierarchy applies cleanly. |
| **Classical / orchestral** | Extreme dynamic range, tempo changes, through-composed structure, no stems in the rock sense. |
| **Heavily compressed EDM** | Flat energy curves, energy impacts don't trigger, "drops" are textural not dynamic. |
| **Prog rock with odd meters** | 5/4, 7/8 time signatures break bar grouping assumptions. Beats are fine, bars are wrong. |

### 9b. Edge Cases Within Target Genres (May Need Manual Tweaking)

These can occur in rock/pop/holiday songs and may produce imperfect results:

| Edge Case | What Happens | User Workaround |
|-----------|-------------|-----------------|
| **Medley or mashup** | Tempo/key analysis spans multiple songs — structure detection gets confused | Analyze each song section separately, or manually adjust section boundaries |
| **Live recording with tempo drift** | Beat grid drifts from performance — bars misalign over time | Use the best beat track and accept some drift, or trim to studio version |
| **Stem separation bleed** (dense mix) | Onset counts and energy curves pick up wrong instruments | Review stem quality; fall back to full-mix analysis for problem stems |
| **Song with a dramatic tempo change** (half-time breakdown, etc.) | Beat tracker picks one tempo and the other section is wrong | Manually split at the tempo change, or accept that one section's beats will be off |
| **Very short track** (<60s, jingle, intro) | Not enough data for meaningful structure or novelty analysis | Results are still usable for beats/onsets — just don't trust section boundaries |

### 9c. Thresholds — Current Defaults

Validated on 22 songs. Status column shows batch validation result.

| Threshold | Current Value | What It Controls | Validated? |
|-----------|--------------|-----------------|------------|
| Energy impact | >1.8x / <0.55x in 1s window | How dramatic a volume change must be to count as a "special moment" | ✅ 22/22 songs produce events (mean 12.2/song) |
| Silence detection | Energy < 5/100 for >300ms | What counts as a gap/silence | ✅ 18/22 songs have gaps — more common than expected |
| Bar frequency | 0.3-0.8 Hz | Expected bar detection rate | ✅ 22/22 songs in range |
| Onset density | 1.0-5.0/s usable range | Too dense = too many lighting events | ⚠️ 19/22 in range; 3 electronic/percussive tracks exceed 5/s |
| Novelty peaks | Top 90th percentile | How many novelty events surface (lower % = more events) | Not yet batch-validated |
| Stem solo | One stem >3x others | How dominant a stem must be to flag as a solo | Not yet batch-validated |
| Consensus window | 3 seconds | How close segmenter boundaries must be to count as "agreeing" | Not yet batch-validated |

---

## 10. Open Questions

1. **Should we sweep QM Segmenter parameters per song, or use fixed "good defaults"?** nSegmentTypes=3, neighbourhoodLimit=8 works well for Highway — need to confirm on more rock/pop/holiday samples before locking in as defaults.

2. **How do we handle songs where Genius isn't available?** The ensemble still works with just Segmentino + QM Segmenter. Genius adds names but isn't required for the measurable-property approach.

3. **What's the right sensitivity for onset detection per use case?** Batch validation confirmed 3/22 songs (all electronic/percussive) exceed 5/s at default sensitivity. Need to sweep sensitivity to bring Halloween Theme (6.9/s), Super Mario (6.1/s), and Squid Game (5.0/s) into usable range.

---

## Appendix A: Batch Validation Song List

22 songs validated on 2026-03-25. Algorithms run: `bbc_energy`, `qm_bars`, `segmentino`, `aubio_onset`.

| Song | Duration | Bars Hz | Segments | Repeats | Onset/s | Energy Events | Gaps | Notes |
|------|----------|---------|----------|---------|---------|---------------|------|-------|
| A Nonsense Christmas | 2:33 | 0.58 | 9 | yes | 3.3 | 8 | 4 | |
| Christmas Dirtbag | 4:12 | 0.43 | 7 | yes | 3.3 | 9 | 1 | |
| Halloween Theme - Main Title | 2:55 | 0.56 | 4 | yes | 6.9 | 8 | 4 | Onset too dense |
| Highway to Hell | 3:28 | 0.49 | 9 | yes | 2.4 | 8 | 6 | |
| Highway to Hell (guitars only) | 3:28 | 0.52 | 14 | yes | 1.1 | 44 | 28 | Isolated instrument — many gaps expected |
| Like It's Christmas | 3:21 | 0.61 | 16 | yes | 4.7 | 6 | 0 | |
| Santa Tell Me | 3:24 | 0.40 | 9 | yes | 3.1 | 7 | 4 | |
| Underneath the Tree | 3:50 | 0.34 | 5 | yes | 3.2 | 6 | 2 | |
| You're A Mean One, Mr. Grinch | 2:46 | 0.45 | 9 | yes | 3.5 | 14 | 6 | |
| Spooky, Scary Skeletons | 2:08 | 0.64 | 12 | yes | 3.6 | 6 | 1 | |
| Carol Of The Bells | 2:46 | 0.47 | 4 | yes | 2.7 | 17 | 5 | |
| Wizards in Winter (Instrumental) | 3:06 | 0.62 | 12 | yes | 3.9 | 21 | 0 | |
| Let It Go (Frozen) | 3:44 | 0.61 | 11 | yes | 2.7 | 12 | 2 | |
| Christmas Eve / Sarajevo 12:24 | 3:25 | 0.50 | 8 | yes | 1.5 | 3 | 2 | |
| Carmina Burana | 2:42 | 0.57 | 6 | yes | 2.3 | 8 | 2 | Classical remix |
| Do They Know It's Christmas | 4:32 | 0.48 | 12 | yes | 1.6 | 6 | 1 | |
| DJ Play a Christmas Song | 3:30 | 0.55 | 17 | yes | 3.0 | 12 | 1 | |
| All I Want For Christmas Is You | 4:02 | 0.62 | 10 | yes | 1.5 | 16 | 6 | |
| Ode to Joy remix - Epic | 3:02 | 0.58 | 11 | yes | 1.2 | 25 | 6 | Classical remix |
| Squid Game dance mix | 2:14 | 0.61 | 4 | yes | 5.0 | 22 | 4 | Onset borderline dense |
| Super Mario Bros Intro | 0:29 | 0.41 | 1 | NO | 6.1 | 2 | 1 | Short jingle — no structure expected |
| Wednesday mashup | 2:17 | 0.53 | 1 | NO | 2.7 | 8 | 0 | Mashup — no repeating structure expected |
